from django.db import migrations


def mark_existing_summaries_completed(apps, schema_editor):
    Meeting = apps.get_model('meetings', 'Meeting')
    Meeting.objects.exclude(summary='').update(status='completed')


class Migration(migrations.Migration):

    dependencies = [
        ('meetings', '0002_meeting_processing_error_meeting_status_and_more'),
    ]

    operations = [
        migrations.RunPython(mark_existing_summaries_completed, migrations.RunPython.noop),
    ]
