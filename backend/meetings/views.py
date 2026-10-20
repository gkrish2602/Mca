from django.db.models import Avg, Count, Q
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import ActionItem, EmailLog, Meeting, Reminder
from .serializers import ActionItemSerializer, EmailLogSerializer, MeetingSerializer, ReminderSerializer
from .tasks import process_meeting


class MeetingViewSet(viewsets.ModelViewSet):
    serializer_class = MeetingSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role in (user.Role.ADMIN, user.Role.MANAGER):
            return Meeting.objects.all().order_by('-created_at')
        return Meeting.objects.filter(created_by=user).order_by('-created_at')

    def perform_create(self, serializer):
        meeting = serializer.save(created_by=self.request.user)
        process_meeting.delay(str(meeting.id))

    @action(detail=False, methods=['get'])
    def analytics(self, request):
        """Team productivity dashboard summary."""
        qs = self.get_queryset()
        action_items = ActionItem.objects.filter(meeting__in=qs)
        return Response({
            'total_meetings': qs.count(),
            'avg_productivity_score': action_items.aggregate(avg=Avg('meeting__productivity_score'))['avg'],
            'total_action_items': action_items.count(),
            'completed_action_items': action_items.filter(status=ActionItem.Status.DONE).count(),
            'overdue_action_items': action_items.filter(status=ActionItem.Status.OVERDUE).count(),
        })


class ActionItemViewSet(viewsets.ModelViewSet):
    serializer_class = ActionItemSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role in (user.Role.ADMIN, user.Role.MANAGER):
            return ActionItem.objects.all().order_by('deadline')
        return ActionItem.objects.filter(
            Q(assigned_to=user) | Q(meeting__created_by=user)
        ).distinct().order_by('deadline')


class EmailLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = EmailLogSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = EmailLog.objects.all().order_by('-sent_at')


class ReminderViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ReminderSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = Reminder.objects.all().order_by('-scheduled_time')

