from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from .models import ActionItem, Meeting, Reminder
from .serializers import MeetingSerializer
from .services.llm_service import validate_analysis
from .tasks import process_meeting, send_deadline_reminders

User = get_user_model()


class MeetingInputTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='member', password='Strong-pass-903!')

    def test_transcript_is_a_valid_meeting_input(self):
        serializer = MeetingSerializer(data={
            'title': 'Planning',
            'transcript': 'We agreed to prepare the launch plan.',
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_meeting_requires_audio_or_text(self):
        serializer = MeetingSerializer(data={'title': 'Planning'})
        self.assertFalse(serializer.is_valid())
        self.assertIn('transcript', serializer.errors)

    def test_meeting_rejects_unsupported_audio_extension(self):
        audio = SimpleUploadedFile('recording.exe', b'not audio')
        serializer = MeetingSerializer(data={'title': 'Planning', 'audio_file': audio})
        self.assertFalse(serializer.is_valid())
        self.assertIn('audio_file', serializer.errors)

    def test_public_registration_cannot_assign_a_privileged_role(self):
        from accounts.serializers import RegisterSerializer

        serializer = RegisterSerializer(data={
            'username': 'new-member',
            'email': 'new@example.com',
            'password': 'Strong-pass-903!x',
            'role': User.Role.ADMIN,
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        user = serializer.save()
        self.assertEqual(user.role, User.Role.MEMBER)

    @patch('meetings.views.process_meeting.delay')
    def test_transcript_meeting_is_queued_and_processing_is_dispatched(self, dispatch):
        client = APIClient()
        client.force_authenticate(self.user)
        with self.captureOnCommitCallbacks(execute=True):
            response = client.post(
                '/api/meetings/',
                {'title': 'Planning', 'transcript': 'Prepare the release plan.'},
                format='json',
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['status'], Meeting.Status.QUEUED)
        dispatch.assert_called_once_with(response.data['id'])

    def test_member_cannot_list_another_members_meetings(self):
        other = User.objects.create_user(username='other', password='Strong-pass-903!')
        Meeting.objects.create(title='Private planning', created_by=other, transcript='Private notes.')
        client = APIClient()
        client.force_authenticate(self.user)

        response = client.get('/api/meetings/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    @patch('meetings.views.process_meeting.delay', side_effect=RuntimeError('Redis unavailable'))
    def test_queue_failure_marks_saved_meeting_failed(self, _dispatch):
        client = APIClient()
        client.force_authenticate(self.user)
        with self.assertRaises(RuntimeError):
            with self.captureOnCommitCallbacks(execute=True):
                client.post(
                    '/api/meetings/',
                    {'title': 'Planning', 'transcript': 'Prepare the release plan.'},
                    format='json',
                )

        meeting = Meeting.objects.get(title='Planning')
        self.assertEqual(meeting.status, Meeting.Status.FAILED)
        self.assertIn('Redis', meeting.processing_error)


class MeetingProcessingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='member',
            password='Strong-pass-903!',
            organization='Research Team',
        )
        self.meeting = Meeting.objects.create(
            title='Planning',
            created_by=self.user,
            transcript='We will prepare the launch plan next week.',
        )

    @patch('meetings.tasks.analyze_transcript')
    def test_processing_stores_analysis_and_resolves_assignee(self, analyze):
        analyze.return_value = {
            'summary': 'The team planned a launch.',
            'decisions': ['Prepare a launch plan.'],
            'action_items': [{
                'task': 'Prepare the launch plan',
                'owner': 'member',
                'deadline': None,
                'priority': 'high',
            }],
            'unresolved_questions': ['What is the launch date?'],
            'productivity_score': 8,
        }

        process_meeting.run(str(self.meeting.id))

        self.meeting.refresh_from_db()
        item = self.meeting.action_items.get()
        self.assertEqual(self.meeting.status, Meeting.Status.COMPLETED)
        self.assertEqual(self.meeting.productivity_score, 8)
        self.assertEqual(item.assigned_to, self.user)
        self.assertIsNone(item.deadline)
        self.assertEqual(self.meeting.unresolved_questions.count(), 1)

    @patch('meetings.tasks.analyze_transcript', side_effect=RuntimeError('provider unavailable'))
    def test_failed_analysis_marks_meeting_failed_and_propagates_error(self, _analyze):
        with self.assertRaises(RuntimeError):
            process_meeting.run(str(self.meeting.id))

        self.meeting.refresh_from_db()
        self.assertEqual(self.meeting.status, Meeting.Status.FAILED)
        self.assertIn('worker logs', self.meeting.processing_error)

    def test_analysis_rejects_out_of_range_productivity_score(self):
        with self.assertRaises(ValueError):
            validate_analysis({
                'summary': 'Summary',
                'decisions': [],
                'action_items': [],
                'unresolved_questions': [],
                'productivity_score': 11,
            })


class ReminderTests(TestCase):
    @patch('meetings.tasks.send_email', return_value=False)
    def test_failed_delivery_does_not_mark_deadline_reminder_sent(self, send):
        owner = User.objects.create_user(username='owner', password='Strong-pass-903!')
        meeting = Meeting.objects.create(title='Planning', created_by=owner)
        item = ActionItem.objects.create(
            meeting=meeting,
            assigned_to=owner,
            description='Share the notes',
            deadline=timezone.localdate() + timedelta(days=1),
        )

        result = send_deadline_reminders.run()

        item.refresh_from_db()
        self.assertEqual(result['reminded'], 0)
        self.assertFalse(item.reminder_sent)
        self.assertFalse(item.reminders.get(type=Reminder.Type.DEADLINE).sent)
        send.assert_called_once()

    @patch('meetings.tasks.send_email', return_value=True)
    def test_overdue_tasks_escalate_to_organization_managers(self, send):
        owner = User.objects.create_user(
            username='owner',
            password='Strong-pass-903!',
            organization='Research Team',
        )
        User.objects.create_user(
            username='manager',
            password='Strong-pass-903!',
            email='manager@example.com',
            organization='Research Team',
            role=User.Role.MANAGER,
        )
        meeting = Meeting.objects.create(title='Planning', created_by=owner)
        item = ActionItem.objects.create(
            meeting=meeting,
            assigned_to=owner,
            description='Share the notes',
            deadline=timezone.localdate() - timedelta(days=1),
        )

        result = send_deadline_reminders.run()

        item.refresh_from_db()
        self.assertEqual(result['escalated'], 1)
        self.assertEqual(item.status, ActionItem.Status.OVERDUE)
        self.assertTrue(item.reminders.get(type=Reminder.Type.ESCALATION).sent)
        self.assertEqual(send.call_args.args[0], ['manager@example.com'])


class FollowUpApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='member',
            password='Strong-pass-903!',
            email='member@example.com',
        )
        self.meeting = Meeting.objects.create(title='Planning', created_by=self.user)
        self.item = ActionItem.objects.create(
            meeting=self.meeting,
            assigned_to=self.user,
            description='Prepare the launch plan',
            deadline=timezone.localdate() + timedelta(days=4),
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_action_item_can_create_a_reviewable_follow_up_draft(self):
        response = self.client.post(
            f'/api/action-items/{self.item.id}/draft-followup/',
            {},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'draft')
        self.assertEqual(response.data['recipient'], self.user.email)
        self.assertIn('Prepare the launch plan', response.data['body'])

    @override_settings(SENDGRID_API_KEY='')
    def test_email_without_provider_is_not_reported_as_sent(self):
        draft = self.client.post(
            f'/api/action-items/{self.item.id}/draft-followup/',
            {},
            format='json',
        ).data

        response = self.client.post(f'/api/email-logs/{draft["id"]}/send/', {}, format='json')

        self.assertEqual(response.status_code, 502)
        self.assertEqual(self.item.email_logs.get().status, 'failed')
