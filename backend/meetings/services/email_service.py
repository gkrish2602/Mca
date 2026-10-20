"""Follow-up email drafting and sending via SendGrid (or SMTP fallback)."""
from django.conf import settings

FOLLOWUP_TEMPLATE = """Hi {owner_name},

This is a follow-up on the action item assigned to you during "{meeting_title}":

  Task: {task}
  Deadline: {deadline}

Please let us know if you have any questions.

Best,
Real-Time AI Meeting Summarizer
"""


def draft_followup_email(owner_name: str, meeting_title: str, task: str, deadline: str) -> dict:
    body = FOLLOWUP_TEMPLATE.format(owner_name=owner_name, meeting_title=meeting_title, task=task, deadline=deadline)
    return {'subject': f'Follow-up: {task[:60]}', 'body': body}


def send_email(recipient: str, subject: str, body: str) -> bool:
    if not settings.SENDGRID_API_KEY:
        # Scaffold mode: log instead of sending until SENDGRID_API_KEY is configured.
        print(f'[email stub] to={recipient} subject={subject!r}')
        return False

    import sendgrid  # imported lazily so the package is optional until configured
    from sendgrid.helpers.mail import Mail

    sg = sendgrid.SendGridAPIClient(settings.SENDGRID_API_KEY)
    message = Mail(from_email=settings.DEFAULT_FROM_EMAIL, to_emails=recipient, subject=subject, plain_text_content=body)
    response = sg.send(message)
    return response.status_code < 300
