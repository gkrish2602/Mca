from rest_framework import serializers

from .models import ActionItem, EmailLog, Meeting, Reminder, UnresolvedQuestion


class UnresolvedQuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = UnresolvedQuestion
        fields = ('id', 'question')


class ActionItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActionItem
        fields = (
            'id', 'meeting', 'description', 'assigned_to', 'deadline',
            'status', 'priority', 'reminder_sent', 'created_at',
        )
        read_only_fields = ('id', 'reminder_sent', 'created_at')


class MeetingSerializer(serializers.ModelSerializer):
    action_items = ActionItemSerializer(many=True, read_only=True)
    unresolved_questions = UnresolvedQuestionSerializer(many=True, read_only=True)

    class Meta:
        model = Meeting
        fields = (
            'id', 'title', 'created_by', 'audio_file', 'transcript', 'summary',
            'decisions', 'productivity_score', 'created_at', 'action_items',
            'unresolved_questions',
        )
        read_only_fields = ('id', 'created_by', 'transcript', 'summary', 'decisions', 'productivity_score', 'created_at')


class EmailLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailLog
        fields = ('id', 'action_item', 'recipient', 'subject', 'body', 'status', 'sent_at')
        read_only_fields = ('id', 'sent_at')


class ReminderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reminder
        fields = ('id', 'action_item', 'scheduled_time', 'type', 'sent')
        read_only_fields = ('id',)
