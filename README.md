# AI Meeting Summarizer

A Django REST API backend for uploading meeting recordings, generating transcripts and summaries, managing action items, and scheduling deadline reminders.

The current project is a backend scaffold. It does not include a frontend, live meeting recording, or real-time streaming transcription.

## Features

- JWT registration, login, token refresh, and profile retrieval.
- Custom users with admin, manager, and member roles.
- Audio uploads and OpenAI Whisper transcription.
- Meeting analysis using GPT-4o mini.
- Summaries, decisions, unresolved questions, and productivity scores.
- Action-item management with assignees, deadlines, priorities, and statuses.
- Background processing with Celery and Redis.
- SendGrid email integration and scheduled deadline reminders.
- Meeting and action-item analytics.

## Technology Stack

| Component | Technology |
| --- | --- |
| Runtime | Python 3.10 or later |
| Backend | Django 5.2, Django REST Framework |
| Authentication | SimpleJWT |
| Database | SQLite by default; optional PostgreSQL |
| Background tasks | Celery |
| Broker and result backend | Redis |
| Transcription | OpenAI Whisper (`whisper-1`) |
| Meeting analysis | OpenAI GPT-4o mini |
| Email | SendGrid |

## Project Structure

```text
MeetingSummarizer/
|-- README.md
`-- backend/
    |-- manage.py
    |-- requirements.txt
    |-- db.sqlite3
    |-- accounts/
    |   |-- models.py
    |   |-- serializers.py
    |   |-- views.py
    |   |-- urls.py
    |   `-- migrations/
    |-- core/
    |   |-- settings.py
    |   |-- urls.py
    |   `-- celery.py
    `-- meetings/
        |-- models.py
        |-- serializers.py
        |-- views.py
        |-- urls.py
        |-- tasks.py
        |-- migrations/
        `-- services/
            |-- whisper_service.py
            |-- llm_service.py
            `-- email_service.py
```

## Prerequisites

- Python 3.10 or later with pip.
- PowerShell for the Windows commands below.
- Docker Desktop or another Redis installation.
- An OpenAI API key for actual transcription and analysis.
- A SendGrid API key and verified sender for actual email delivery.

API keys are optional for scaffold development: without them, the services return placeholder results or print email stub messages.

## Setup From Scratch

### 1. Open the Backend Directory

Open PowerShell in the project root:

```powershell
cd backend
```

### 2. Create and Activate a Virtual Environment

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If PowerShell prevents activation, use the environment's executable directly, for example:

```powershell
.\.venv\Scripts\python.exe manage.py check
```

### 3. Configure Environment Variables

The application reads environment variables directly. Although `python-dotenv` is a dependency, the current settings do not automatically load `.env` files.

Set the following in each terminal that needs them, especially the Celery worker terminal:

```powershell
$env:OPENAI_API_KEY="your-openai-api-key"
$env:SENDGRID_API_KEY="your-sendgrid-api-key"
$env:DEFAULT_FROM_EMAIL="verified-sender@example.com"
```

Never commit actual API keys or other secrets.

| Variable | Default or Purpose |
| --- | --- |
| `DJANGO_SECRET_KEY` | Development fallback; replace for deployment |
| `DJANGO_DEBUG` | `True`; use `False` for deployment |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:5173` |
| `OPENAI_API_KEY` | Enables real transcription and meeting analysis |
| `ANTHROPIC_API_KEY` | Declared in settings, but Claude integration is not implemented |
| `SENDGRID_API_KEY` | Enables SendGrid delivery |
| `DEFAULT_FROM_EMAIL` | `noreply@meetingsummarizer.local`; replace with a verified sender |
| `CELERY_BROKER_URL` | `redis://localhost:6379/0` |
| `CELERY_RESULT_BACKEND` | `redis://localhost:6379/0` |

Use `OPENAI_API_KEY` for the implemented AI integration. Setting only `ANTHROPIC_API_KEY` does not enable Claude and may cause analysis to fail.

### 4. Initialize the Database

SQLite is used by default. Apply the migration files included in the project:

```powershell
python manage.py migrate
python manage.py createsuperuser
```

For a fresh scaffold that has no initial migration files, generate them before migrating:

```powershell
python manage.py makemigrations accounts meetings
python manage.py migrate
```

Keep generated migration files in version control. Normal setup should apply existing migrations rather than regenerate them.

### 5. Start Redis

With Docker Desktop running:

```powershell
docker run --name meeting-redis -p 6379:6379 -d redis:7-alpine
```

If that container already exists:

```powershell
docker start meeting-redis
```

The example exposes Redis locally for development. Do not expose an unauthenticated Redis instance publicly.

### 6. Start Django, the Worker, and the Scheduler

Open three terminals in the backend directory and activate the virtual environment in each. Configure any required environment variables before starting the processes.

Terminal 1, Django:

```powershell
python manage.py runserver
```

Terminal 2, Celery worker:

```powershell
celery -A core worker --loglevel=info --pool=solo
```

Terminal 3, Celery Beat scheduler:

```powershell
celery -A core beat --loglevel=info
```

`--pool=solo` is a Windows development workaround. Celery does not officially support Windows; prefer WSL or Linux for reliable deployment. Run only one Beat scheduler for a given schedule.

- API directory: <http://127.0.0.1:8000/api/>
- Django administration: <http://127.0.0.1:8000/admin/>
- No homepage is configured at `/`, so a 404 there is expected.

## Optional PostgreSQL Setup

Create a PostgreSQL database and set these variables before running migrations and starting each relevant process:

```powershell
$env:POSTGRES_DB="meeting_summarizer"
$env:POSTGRES_USER="postgres"
$env:POSTGRES_PASSWORD="your-database-password"
$env:POSTGRES_HOST="localhost"
$env:POSTGRES_PORT="5432"
python manage.py migrate
```

Setting `POSTGRES_DB` switches the application from SQLite to PostgreSQL. It does not copy existing SQLite data.

## Authentication

All API endpoints except registration, login, and token refresh require a JWT access token:

```http
Authorization: Bearer <access_token>
```

Use trailing slashes in API URLs. Resource IDs are UUIDs.

### Register

`POST /api/auth/register/`

```json
{
  "username": "gokul",
  "email": "gokul@example.com",
  "password": "Use-A-Unique-Strong-Password!",
  "organization": "My Team"
}
```

The default role is `member`. Passwords must pass Django's configured validators.

### Log In

`POST /api/auth/login/`

```json
{
  "username": "gokul",
  "password": "Use-A-Unique-Strong-Password!"
}
```

The response includes `access` and `refresh` tokens. Access tokens currently last eight hours; refresh tokens last seven days.

### Refresh a Token

`POST /api/auth/login/refresh/`

```json
{
  "refresh": "<refresh_token>"
}
```

### Retrieve Your Profile

`GET /api/auth/me/` returns the authenticated user's ID, username, email, name, role, and organization.

## API Reference

Base URL: `http://127.0.0.1:8000`

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/auth/register/` | Register a user |
| POST | `/api/auth/login/` | Obtain JWT tokens |
| POST | `/api/auth/login/refresh/` | Refresh an access token |
| GET | `/api/auth/me/` | Retrieve the current profile |
| GET | `/api/` | Browse the router's endpoint directory |
| GET / POST | `/api/meetings/` | List or create meetings |
| GET / PUT / PATCH / DELETE | `/api/meetings/<uuid>/` | Retrieve, update, or delete a meeting |
| GET | `/api/meetings/analytics/` | Retrieve productivity statistics |
| GET / POST | `/api/action-items/` | List or create action items |
| GET / PUT / PATCH / DELETE | `/api/action-items/<uuid>/` | Retrieve, update, or delete an action item |
| GET | `/api/email-logs/` | List email logs |
| GET | `/api/email-logs/<uuid>/` | Retrieve an email log |
| GET | `/api/reminders/` | List reminder records |
| GET | `/api/reminders/<uuid>/` | Retrieve a reminder record |
| Browser | `/admin/` | Django administration using a staff account |

### Create a Meeting

Send `POST /api/meetings/` with multipart form data:

| Field | Description |
| --- | --- |
| `title` | Required meeting title |
| `audio_file` | Optional audio recording |

The creator is set to the authenticated user. Creation queues background processing immediately. A working Redis broker is required for queuing, and a Celery worker is required to process the task.

For example, from PowerShell using `curl.exe`:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/meetings/" -H "Authorization: Bearer <access_token>" -F "title=Weekly Planning" -F "audio_file=@C:/recordings/meeting.mp3"
```

Retrieve `/api/meetings/<uuid>/` after processing to inspect the transcript, summary, decisions, productivity score, action items, and unresolved questions. These generated fields are read-only through the meeting API. There is currently no processing-status field or dedicated retry endpoint.

### Create an Action Item

`POST /api/action-items/`

```json
{
  "meeting": "<meeting_uuid>",
  "description": "Prepare the release checklist",
  "assigned_to": "<user_uuid>",
  "deadline": "2026-12-01",
  "status": "pending",
  "priority": "medium"
}
```

Supported statuses are `pending`, `done`, and `overdue`. To mark an item complete, send `PATCH /api/action-items/<uuid>/`:

```json
{
  "status": "done"
}
```

### Analytics

`GET /api/meetings/analytics/` returns:

- `total_meetings`
- `avg_productivity_score`
- `total_action_items`
- `completed_action_items`
- `overdue_action_items`

The current average is calculated through action-item rows, so meetings with more action items have more weight and meetings with no action items do not contribute.

## Access Rules

- Members see meetings they created.
- Members see action items assigned to them or belonging to meetings they created.
- Admins and managers see all meetings and action items.
- Email-log and reminder querysets currently expose all records to any authenticated user.
- Organization values are stored but do not currently isolate data by organization.

These are the current query rules, not a complete production authorization system. In particular, foreign-key assignments and privileged-role registration require additional restrictions.

## Main Functions and Classes

| Function or Class | Location | Responsibility |
| --- | --- | --- |
| `RegisterView` | `backend/accounts/views.py` | Create accounts |
| `RegisterSerializer.create()` | `backend/accounts/serializers.py` | Hash passwords and save users |
| `MeView.get()` | `backend/accounts/views.py` | Return the current profile |
| `MeetingViewSet.get_queryset()` | `backend/meetings/views.py` | Select accessible meetings |
| `MeetingViewSet.perform_create()` | `backend/meetings/views.py` | Save the meeting and queue processing |
| `MeetingViewSet.analytics()` | `backend/meetings/views.py` | Calculate dashboard statistics |
| `ActionItemViewSet.get_queryset()` | `backend/meetings/views.py` | Select accessible action items |
| `process_meeting()` | `backend/meetings/tasks.py` | Transcribe, analyze, and store meeting results |
| `draft_and_send_followups()` | `backend/meetings/tasks.py` | Draft and send task follow-up emails |
| `send_deadline_reminders()` | `backend/meetings/tasks.py` | Handle upcoming deadlines and overdue records |
| `transcribe_audio()` | `backend/meetings/services/whisper_service.py` | Call Whisper or return a placeholder |
| `analyze_transcript()` | `backend/meetings/services/llm_service.py` | Call GPT-4o mini or return placeholder analysis |
| `draft_followup_email()` | `backend/meetings/services/email_service.py` | Build follow-up email content |
| `send_email()` | `backend/meetings/services/email_service.py` | Send through SendGrid or print a stub |

## Background Workflow

1. An authenticated user creates a meeting.
2. Django saves it and queues `process_meeting()`.
3. The worker transcribes the audio if present and a transcript is not already stored.
4. The analysis service produces structured meeting results.
5. The worker stores the summary, decisions, score, questions, and action items.
6. Celery Beat schedules `send_deadline_reminders()` hourly.

Follow-up emails are not automatically triggered by meeting creation. The follow-up task exists but currently has no HTTP endpoint or automatic invocation in that workflow.

## Current Limitations

- Claude is not implemented despite the `ANTHROPIC_API_KEY` setting.
- Without API keys, transcription and analysis use placeholders and email is not delivered.
- AI-generated action-item owners must be valid existing user UUIDs, and deadlines must be valid dates; output is not robustly validated before saving.
- Updating a meeting's recording does not automatically queue reprocessing.
- Email sending does not currently populate `EmailLog` records.
- Overdue escalation creates reminder records but does not send escalation emails.
- Reminder records can be marked sent even when the email stub returns without delivery.
- Public registration accepts the `role` field, including privileged roles; restrict this before exposing the application.
- Uploaded media is served directly in debug mode without API authorization checks.
- Processing retries, failure tracking, idempotency, upload validation, and production-grade permissions need further implementation.

## Checks and Tests

From the backend directory:

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```

System checks and migration consistency checks do not substitute for behavioral tests. The test command runs whatever tests are implemented in the project.

## Troubleshooting

### Dependency on App With No Migrations: accounts

Generate initial migrations if they are missing, then apply them:

```powershell
python manage.py makemigrations accounts meetings
python manage.py migrate
```

Do not delete the database or fake migrations to bypass inconsistent history without understanding and backing up existing data.

### Cannot Open managr.py

The command uses `manage.py`, not `managr.py`:

```powershell
python manage.py runserver
```

### Meeting Creation Fails or Results Stay Empty

Check that Redis is running and that the Celery worker uses the same environment and database settings as Django. Broker failure can prevent queuing after the meeting has already been saved. Inspect worker errors before retrying creation, since another request can create a duplicate meeting.

### Authentication Fails

Use an access token, not a refresh token, in the `Authorization` header. Refresh expired access tokens through `/api/auth/login/refresh/`. Opening a protected endpoint in a browser alone does not attach a JWT header.

### Emails Are Not Delivered

Check the worker's `SENDGRID_API_KEY`, the verified sender address, and SendGrid responses. Without a configured key, email sending only prints a stub message.

## Deployment Notes

This scaffold requires security and reliability work before production use:

- Use a strong `DJANGO_SECRET_KEY` and `DJANGO_DEBUG=False`.
- Configure explicit allowed hosts and trusted frontend origins.
- Restrict privileged role assignment and enforce object and organization permissions.
- Protect uploaded recordings and validate file type and size.
- Use HTTPS, a production application server, and secure secret management.
- Deploy Redis and Celery on supported infrastructure and run one Beat scheduler.
- Add task failure monitoring, validated AI output, reliable delivery tracking, and backups.
- Review recording consent, retention, and third-party processing requirements before uploading real meeting data.