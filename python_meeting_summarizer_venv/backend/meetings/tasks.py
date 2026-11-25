import logging
from datetime import date, timedelta

from celery import shared_task
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import ActionItem, EmailLog, Meeting, Reminder, UnresolvedQuestion
from .services.email_service import draft_followup_email, send_email
from .services.llm_service import analyze_transcript
from .services.rag_service import retrieve_relevant_context
from .services.whisper_service import transcribe_audio

logger = logging.getLogger(__name__)


def _meeting_participants(meeting):
    User = get_user_model()
    if meeting.created_by.organization:
        participants = User.objects.filter(organization=meeting.created_by.organization)
    else:
        participants = User.objects.filter(id=meeting.created_by_id)
    return list(participants.order_by('username'))


def _resolve_owner(owner_name, participants, meeting):
    if not owner_name:
        return meeting.created_by
    requested = owner_name.strip().casefold()
    for participant in participants:
        identifiers = {
            participant.username.casefold(),
            participant.email.casefold(),
            participant.get_full_name().casefold(),
        }
        if requested in identifiers:
            return participant
    return meeting.created_by


@shared_task
def process_meeting(meeting_id):
    """Transcribe and analyze a meeting, storing all generated records atomically."""
    meeting = Meeting.objects.select_related('created_by').get(id=meeting_id)
    meeting.status = Meeting.Status.PROCESSING
    meeting.processing_error = ''
    meeting.save(update_fields=['status', 'processing_error'])

    try:
        if meeting.audio_file and not meeting.transcript:
            meeting.transcript = transcribe_audio(meeting.audio_file.path)
        if not meeting.transcript.strip():
            raise ValueError('The meeting has no transcript to analyze.')

        participants = _meeting_participants(meeting)
        participant_data = [{
            'username': user.username,
            'name': user.get_full_name(),
            'email': user.email,
        } for user in participants]
        analysis = analyze_transcript(
            meeting.transcript,
            participants=participant_data,
            context=retrieve_relevant_context(meeting),
        )

        with transaction.atomic():
            meeting.summary = analysis['summary']
            meeting.decisions = '\n'.join(analysis['decisions'])
            meeting.productivity_score = analysis['productivity_score']
            meeting.status = Meeting.Status.COMPLETED
            meeting.processing_error = ''
            meeting.save(update_fields=[
                'transcript', 'summary', 'decisions', 'productivity_score',
                'status', 'processing_error',
            ])
            meeting.unresolved_questions.all().delete()
            meeting.action_items.all().delete()

            for question in analysis['unresolved_questions']:
                UnresolvedQuestion.objects.create(meeting=meeting, question=question)

            today = timezone.localdate()
            for item in analysis['action_items']:
                deadline = date.fromisoformat(item['deadline']) if item.get('deadline') else None
                status = (
                    ActionItem.Status.OVERDUE
                    if deadline and deadline < today
                    else ActionItem.Status.PENDING
                )
                ActionItem.objects.create(
                    meeting=meeting,
                    description=item['task'].strip(),
                    assigned_to=_resolve_owner(item.get('owner'), participants, meeting),
                    deadline=deadline,
                    priority=(item.get('priority') or 'medium').lower(),
                    status=status,
                )
        return str(meeting.id)
    except Exception:
        logger.exception('Meeting processing failed for meeting %s', meeting_id)
        Meeting.objects.filter(id=meeting_id).update(
            status=Meeting.Status.FAILED,
            processing_error='Meeting processing failed. Check service configuration and worker logs.',
        )
        raise


@shared_task
def draft_followups(meeting_id):
    """Create reviewable follow-up drafts for a meeting's action items."""
    meeting = Meeting.objects.get(id=meeting_id)
    drafts = []
    for item in meeting.action_items.select_related('assigned_to'):
        content = draft_followup_email(
            owner_name=item.assigned_to.get_full_name() or item.assigned_to.username,
            meeting_title=meeting.title,
            task=item.description,
            deadline=str(item.deadline or 'Not specified'),
        )
        draft, _ = EmailLog.objects.get_or_create(
            action_item=item,
            status='draft',
            defaults={
                'recipient': item.assigned_to.email,
                'subject': content['subject'],
                'body': content['body'],
            },
        )
        drafts.append(str(draft.id))
    return drafts


@shared_task
def send_deadline_reminders():
    """Remind owners one day before deadlines and escalate overdue work."""
    today = timezone.localdate()
    due_soon = list(
        ActionItem.objects.select_related('assigned_to', 'meeting__created_by').filter(
            deadline=today + timedelta(days=1),
            reminder_sent=False,
        ).exclude(status=ActionItem.Status.DONE)
    )
    reminded = 0
    for item in due_soon:
        sent = send_email(
            item.assigned_to.email,
            subject=f'Reminder: "{item.description[:50]}" is due tomorrow',
            body=f'This is a reminder that your action item is due on {item.deadline}.',
        )
        Reminder.objects.create(
            action_item=item,
            scheduled_time=timezone.now(),
            type=Reminder.Type.DEADLINE,
            sent=sent,
        )
        if sent:
            item.reminder_sent = True
            item.save(update_fields=['reminder_sent'])
            reminded += 1

    overdue = list(
        ActionItem.objects.select_related('assigned_to', 'meeting__created_by').filter(
            deadline__lt=today,
        ).exclude(status=ActionItem.Status.DONE)
    )
    escalated = 0
    for item in overdue:
        if item.status != ActionItem.Status.OVERDUE:
            item.status = ActionItem.Status.OVERDUE
            item.save(update_fields=['status'])
        if item.reminders.filter(type=Reminder.Type.ESCALATION, sent=True).exists():
            continue

        organization = item.meeting.created_by.organization
        managers = get_user_model().objects.filter(
            role=get_user_model().Role.MANAGER,
            organization=organization,
        ).exclude(email='')
        if not organization:
            managers = managers.filter(id=item.meeting.created_by_id)
        recipients = list(managers.values_list('email', flat=True))
        if not recipients:
            continue
        sent = send_email(
            recipients,
            subject=f'Overdue action item: {item.description[:50]}',
            body=(
                f'{item.assigned_to.get_full_name() or item.assigned_to.username} has an overdue task '
                f'from "{item.meeting.title}": {item.description} (due {item.deadline}).'
            ),
        )
        Reminder.objects.create(
            action_item=item,
            scheduled_time=timezone.now(),
            type=Reminder.Type.ESCALATION,
            sent=sent,
        )
        if sent:
            escalated += 1

    return {'reminded': reminded, 'escalated': escalated}
