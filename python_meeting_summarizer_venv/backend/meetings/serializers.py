from pathlib import Path

from rest_framework import serializers

from .models import ActionItem, EmailLog, Meeting, Reminder, UnresolvedQuestion

MAX_AUDIO_SIZE = 25 * 1024 * 1024
ALLOWED_AUDIO_EXTENSIONS = {'.mp3', '.mp4', '.mpeg', '.mpga', '.m4a', '.wav', '.webm'}


class UnresolvedQuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = UnresolvedQuestion
        fields = ('id', 'question')


class ActionItemSerializer(serializers.ModelSerializer):
    assigned_to_name = serializers.SerializerMethodField()

    def validate(self, attrs):
        request = self.context.get('request')
        if not request:
            return attrs

        user = request.user
        meeting = attrs.get('meeting', getattr(self.instance, 'meeting', None))
        assignee = attrs.get('assigned_to', getattr(self.instance, 'assigned_to', None))
        if meeting and user.role == user.Role.MEMBER and meeting.created_by_id != user.id:
            raise serializers.ValidationError({'meeting': 'You can only add tasks to your own meetings.'})
        if meeting and user.role != user.Role.MEMBER and meeting.created_by.organization != user.organization:
            raise serializers.ValidationError({'meeting': 'The meeting must belong to your organization.'})
        if assignee and assignee.organization != user.organization:
            raise serializers.ValidationError({'assigned_to': 'The assignee must belong to your organization.'})
        if user.role == user.Role.MEMBER and assignee and assignee.id != user.id:
            raise serializers.ValidationError({'assigned_to': 'Members can only assign tasks to themselves.'})
        return attrs

    class Meta:
        model = ActionItem
        fields = (
            'id', 'meeting', 'description', 'assigned_to', 'assigned_to_name', 'deadline',
            'status', 'priority', 'reminder_sent', 'created_at',
        )
        read_only_fields = ('id', 'reminder_sent', 'created_at')

    def get_assigned_to_name(self, item):
        return item.assigned_to.get_full_name() or item.assigned_to.username


class MeetingSerializer(serializers.ModelSerializer):
    action_items = ActionItemSerializer(many=True, read_only=True)
    unresolved_questions = UnresolvedQuestionSerializer(many=True, read_only=True)

    class Meta:
        model = Meeting
        fields = (
            'id', 'title', 'created_by', 'audio_file', 'transcript', 'summary',
            'decisions', 'productivity_score', 'status', 'processing_error',
            'created_at', 'action_items',
            'unresolved_questions',
        )
        read_only_fields = (
            'id', 'created_by', 'summary', 'decisions', 'productivity_score',
            'status', 'processing_error', 'created_at',
        )

    def validate_audio_file(self, value):
        if value.size > MAX_AUDIO_SIZE:
            raise serializers.ValidationError('Audio files must be 25 MB or smaller.')
        if Path(value.name).suffix.lower() not in ALLOWED_AUDIO_EXTENSIONS:
            raise serializers.ValidationError('Use an MP3, MP4, MPEG, MPGA, M4A, WAV, or WebM audio file.')
        return value

    def validate_transcript(self, value):
        if len(value) > 100_000:
            raise serializers.ValidationError('Transcript and notes must be 100,000 characters or fewer.')
        return value.strip()

    def validate(self, attrs):
        if not self.instance and not attrs.get('audio_file') and not attrs.get('transcript', '').strip():
            raise serializers.ValidationError({
                'transcript': 'Provide an audio recording or paste a transcript or meeting notes.'
            })
        return attrs


class EmailLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailLog
        fields = ('id', 'action_item', 'recipient', 'subject', 'body', 'status', 'sent_at')
        read_only_fields = ('id', 'sent_at')


class EmailDraftSerializer(serializers.Serializer):
    subject = serializers.CharField(max_length=255)
    body = serializers.CharField(max_length=20_000)


class ReminderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reminder
        fields = ('id', 'action_item', 'scheduled_time', 'type', 'sent')
        read_only_fields = ('id',)
