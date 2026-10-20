from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from .models import ActionItem, Meeting, Reminder, UnresolvedQuestion
from .services.email_service import draft_followup_email, send_email
from .services.llm_service import analyze_transcript
from .services.whisper_service import transcribe_audio


@shared_task
def process_meeting(meeting_id):
    """Full pipeline: transcribe (if audio present) -> analyze -> store results."""
    meeting = Meeting.objects.get(id=meeting_id)

    if meeting.audio_file and not meeting.transcript:
        meeting.transcript = transcribe_audio(meeting.audio_file.path)

    analysis = analyze_transcript(meeting.transcript)
    meeting.summary = analysis.get('summary', '')
    meeting.decisions = '\n'.join(analysis.get('decisions', []))
    meeting.productivity_score = analysis.get('productivity_score')
    meeting.save()

    for question in analysis.get('unresolved_questions', []):
        UnresolvedQuestion.objects.create(meeting=meeting, question=question)

    for item in analysis.get('action_items', []):
        ActionItem.objects.create(
            meeting=meeting,
            description=item.get('task', ''),
            assigned_to_id=item.get('owner'),
            deadline=item.get('deadline'),
            priority=item.get('priority', 'medium'),
        )
    return str(meeting.id)


@shared_task
def draft_and_send_followups(meeting_id):
    meeting = Meeting.objects.get(id=meeting_id)
    for item in meeting.action_items.all():
        draft = draft_followup_email(
            owner_name=item.assigned_to.get_full_name() or item.assigned_to.username,
            meeting_title=meeting.title,
            task=item.description,
            deadline=str(item.deadline),
        )
        send_email(item.assigned_to.email, draft['subject'], draft['body'])


@shared_task
def send_deadline_reminders():
    """Celery beat task: runs hourly, reminds owners 24h before deadline and escalates overdue items."""
    tomorrow = timezone.now().date() + timedelta(days=1)
    due_soon = ActionItem.objects.filter(deadline=tomorrow, reminder_sent=False).exclude(status=ActionItem.Status.DONE)
    for item in due_soon:
        send_email(
            item.assigned_to.email,
            subject=f'Reminder: "{item.description[:50]}" is due tomorrow',
            body=f'This is a reminder that your action item is due on {item.deadline}.',
        )
        item.reminder_sent = True
        item.status = item.status
        item.save(update_fields=['reminder_sent'])
        Reminder.objects.create(action_item=item, scheduled_time=timezone.now(), type=Reminder.Type.DEADLINE, sent=True)

    overdue = ActionItem.objects.filter(deadline__lt=timezone.now().date()).exclude(status=ActionItem.Status.DONE)
    for item in overdue:
        item.status = ActionItem.Status.OVERDUE
        item.save(update_fields=['status'])
        Reminder.objects.create(action_item=item, scheduled_time=timezone.now(), type=Reminder.Type.ESCALATION, sent=True)

    return {'reminded': due_soon.count(), 'escalated': overdue.count()}
