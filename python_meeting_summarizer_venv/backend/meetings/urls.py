from rest_framework.routers import DefaultRouter

from .views import ActionItemViewSet, EmailLogViewSet, MeetingViewSet, ReminderViewSet

router = DefaultRouter()
router.register('meetings', MeetingViewSet, basename='meeting')
router.register('action-items', ActionItemViewSet, basename='action-item')
router.register('email-logs', EmailLogViewSet, basename='email-log')
router.register('reminders', ReminderViewSet, basename='reminder')

urlpatterns = router.urls
