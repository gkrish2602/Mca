import logging

from django.db import transaction
from django.db.models import Avg, Q
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import ActionItem, EmailLog, Meeting, Reminder
from .serializers import (
    ActionItemSerializer,
    EmailDraftSerializer,
    EmailLogSerializer,
    MeetingSerializer,
    ReminderSerializer,
)
from .services.email_service import draft_followup_email, send_email
from .tasks import process_meeting

logger = logging.getLogger(__name__)


def _enqueue_processing(meeting_id):
    try:
        process_meeting.delay(str(meeting_id))
    except Exception:
        logger.exception('Could not enqueue processing for meeting %s', meeting_id)
        Meeting.objects.filter(id=meeting_id).update(
            status=Meeting.Status.FAILED,
            processing_error='Could not queue meeting processing. Check Redis and the worker configuration.',
        )
        raise


def accessible_meetings(user):
    if user.role in (user.Role.ADMIN, user.Role.MANAGER) and user.organization:
        return Meeting.objects.filter(created_by__organization=user.organization)
    return Meeting.objects.filter(created_by=user)


def accessible_action_items(user):
    if user.role in (user.Role.ADMIN, user.Role.MANAGER) and user.organization:
        return ActionItem.objects.filter(meeting__created_by__organization=user.organization)
    return ActionItem.objects.filter(
        Q(assigned_to=user) | Q(meeting__created_by=user)
    ).distinct()


class MeetingViewSet(viewsets.ModelViewSet):
    serializer_class = MeetingSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return accessible_meetings(self.request.user).order_by('-created_at')

    def perform_create(self, serializer):
        meeting = serializer.save(created_by=self.request.user)
        transaction.on_commit(lambda: _enqueue_processing(meeting.id))

    def perform_update(self, serializer):
        input_changed = {'audio_file', 'transcript'} & serializer.validated_data.keys()
        if input_changed:
            updates = {
                'status': Meeting.Status.QUEUED,
                'summary': '',
                'decisions': '',
                'productivity_score': None,
                'processing_error': '',
            }
            if 'audio_file' in input_changed and 'transcript' not in input_changed:
                updates['transcript'] = ''
            meeting = serializer.save(**updates)
            meeting.action_items.all().delete()
            meeting.unresolved_questions.all().delete()
            transaction.on_commit(lambda: _enqueue_processing(meeting.id))
            return
        serializer.save()

    @action(detail=True, methods=['post'])
    def retry(self, request, pk=None):
        meeting = self.get_object()
        if meeting.status != Meeting.Status.FAILED:
            return Response(
                {'detail': 'Only meetings with failed processing can be retried.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        meeting.status = Meeting.Status.QUEUED
        meeting.processing_error = ''
        meeting.save(update_fields=['status', 'processing_error'])
        transaction.on_commit(lambda: _enqueue_processing(meeting.id))
        return Response(self.get_serializer(meeting).data, status=status.HTTP_202_ACCEPTED)

    @action(detail=False, methods=['get'])
    def analytics(self, request):
        meetings = self.get_queryset()
        action_items = ActionItem.objects.filter(meeting__in=meetings)
        today = timezone.localdate()
        return Response({
            'total_meetings': meetings.count(),
            'avg_productivity_score': meetings.aggregate(avg=Avg('productivity_score'))['avg'],
            'total_action_items': action_items.count(),
            'completed_action_items': action_items.filter(status=ActionItem.Status.DONE).count(),
            'overdue_action_items': action_items.filter(
                Q(status=ActionItem.Status.OVERDUE)
                | Q(deadline__lt=today)
            ).exclude(status=ActionItem.Status.DONE).count(),
        })


class ActionItemViewSet(viewsets.ModelViewSet):
    serializer_class = ActionItemSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return accessible_action_items(self.request.user).order_by('deadline', 'created_at')

    @action(detail=True, methods=['post'], url_path='draft-followup')
    def draft_followup(self, request, pk=None):
        item = self.get_object()
        recipient = item.assigned_to.email
        if not recipient:
            return Response(
                {'detail': 'The assigned user does not have an email address.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        content = draft_followup_email(
            owner_name=item.assigned_to.get_full_name() or item.assigned_to.username,
            meeting_title=item.meeting.title,
            task=item.description,
            deadline=str(item.deadline or 'Not specified'),
        )
        draft, _ = EmailLog.objects.get_or_create(
            action_item=item,
            status='draft',
            defaults={
                'recipient': recipient,
                'subject': content['subject'],
                'body': content['body'],
            },
        )
        return Response(EmailLogSerializer(draft).data, status=status.HTTP_200_OK)


class EmailLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = EmailLogSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return EmailLog.objects.filter(
            action_item__in=accessible_action_items(self.request.user)
        ).select_related('action_item').order_by('-sent_at', '-id')

    @action(detail=True, methods=['patch'], url_path='edit')
    def edit_draft(self, request, pk=None):
        email_log = self.get_object()
        if email_log.status != 'draft':
            return Response(
                {'detail': 'Only draft emails can be edited.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = EmailDraftSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        if not serializer.validated_data:
            return Response(
                {'detail': 'Provide an email subject or body to update the draft.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        for field, value in serializer.validated_data.items():
            setattr(email_log, field, value)
        email_log.save(update_fields=list(serializer.validated_data))
        return Response(self.get_serializer(email_log).data)

    @action(detail=True, methods=['post'])
    def send(self, request, pk=None):
        email_log = self.get_object()
        if email_log.status != 'draft':
            return Response(
                {'detail': 'Only draft emails can be sent.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        delivered = send_email(email_log.recipient, email_log.subject, email_log.body)
        if not delivered:
            email_log.status = 'failed'
            email_log.save(update_fields=['status'])
            return Response(
                {'detail': 'Email delivery failed. Check the SendGrid configuration and try again.'},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        email_log.status = 'sent'
        email_log.sent_at = timezone.now()
        email_log.save(update_fields=['status', 'sent_at'])
        return Response(self.get_serializer(email_log).data)


class ReminderViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ReminderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Reminder.objects.filter(
            action_item__in=accessible_action_items(self.request.user)
        ).order_by('-scheduled_time')
