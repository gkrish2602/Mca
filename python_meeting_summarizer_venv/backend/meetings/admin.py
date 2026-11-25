from django.contrib import admin

from .models import ActionItem, EmailLog, Meeting, Reminder, UnresolvedQuestion

admin.site.register(Meeting)
admin.site.register(ActionItem)
admin.site.register(UnresolvedQuestion)
admin.site.register(EmailLog)
admin.site.register(Reminder)

