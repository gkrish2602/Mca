import uuid

from django.conf import settings
from django.db import models


class Meeting(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='meetings')
    audio_file = models.FileField(upload_to='meeting_audio/', blank=True, null=True)
    transcript = models.TextField(blank=True, default='')
    summary = models.TextField(blank=True, default='')
    decisions = models.TextField(blank=True, default='')
    productivity_score = models.PositiveSmallIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class UnresolvedQuestion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name='unresolved_questions')
    question = models.TextField()

    def __str__(self):
        return self.question[:60]


class ActionItem(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        DONE = 'done', 'Done'
        OVERDUE = 'overdue', 'Overdue'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name='action_items')
    description = models.TextField()
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='action_items')
    deadline = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    priority = models.CharField(max_length=20, blank=True, default='medium')
    reminder_sent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.description[:60]


class EmailLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    action_item = models.ForeignKey(ActionItem, on_delete=models.CASCADE, related_name='email_logs')
    recipient = models.EmailField()
    subject = models.CharField(max_length=255)
    body = models.TextField()
    status = models.CharField(max_length=20, default='draft')
    sent_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f'{self.subject} -> {self.recipient}'


class Reminder(models.Model):
    class Type(models.TextChoices):
        DEADLINE = 'deadline', 'Deadline'
        ESCALATION = 'escalation', 'Escalation'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    action_item = models.ForeignKey(ActionItem, on_delete=models.CASCADE, related_name='reminders')
    scheduled_time = models.DateTimeField()
    type = models.CharField(max_length=20, choices=Type.choices, default=Type.DEADLINE)
    sent = models.BooleanField(default=False)

    def __str__(self):
        return f'{self.type} reminder for {self.action_item_id}'

