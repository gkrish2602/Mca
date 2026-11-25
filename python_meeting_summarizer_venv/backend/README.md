# Backend — Real-Time AI Meeting Summarizer

Django REST API for authenticated meeting capture, transcription and analysis, action-item tracking, email follow-ups, reminders, and team analytics.

## Architecture

```text
React / Vite
    │ JWT-authenticated REST requests
    ▼
Django REST Framework ── SQLite (default) / PostgreSQL
    │                           │
    │ transaction commit       └── meetings, tasks, reminders, email logs
    ▼
Celery worker ◄── Redis ── Celery Beat
    ├── OpenAI Whisper transcription (audio input)
    ├── meeting analysis (summary, decisions, owners, deadlines, questions)
    ├── lexical retrieval of relevant prior meeting notes
    └── SendGrid delivery (reviewed follow-ups, reminders, escalations)
```

### Meeting processing workflow

1. A signed-in user submits an audio recording or transcript/rough notes.
2. The API validates the input, saves the meeting as `queued`, and dispatches processing after the database transaction commits.
3. The worker transcribes audio when needed, retrieves relevant prior notes from the same organization, and requests structured JSON from the configured OpenAI model.
4. The worker validates the AI output and atomically saves the summary, decisions, open questions, and action items. Unknown owners are assigned to the meeting creator; unspecified deadlines remain empty.
5. The frontend polls meeting state and lets users retry failed jobs.
6. Users can edit a prepared follow-up email before sending it. Celery Beat checks deadlines hourly; reminders are only marked sent after successful delivery.

The analysis uses pretrained OpenAI models; this repository does not train a custom AI model. Prior-meeting retrieval uses lexical overlap over recent summaries, decisions, open questions, and tasks; it is a lightweight RAG step, not a vector database or pgvector implementation.

## Requirements

- Python 3.10+
- Redis 7+ for background processing and scheduled reminders
- OpenAI API key for actual transcription and analysis
- SendGrid API key and verified sender address for actual email delivery

SQLite is used by default. PostgreSQL is optional through environment settings.

## Windows development setup

Run these commands in PowerShell from the repository root:

```powershell
Set-Location .\python_meeting_summarizer_venv\backend
Copy-Item .env.example .env
..\Scripts\python.exe -m pip install -r requirements.txt
..\Scripts\python.exe manage.py migrate
..\Scripts\python.exe manage.py createsuperuser
```

Edit `.env` and set at least `OPENAI_API_KEY`. For email delivery also set `SENDGRID_API_KEY` and a verified `DEFAULT_FROM_EMAIL`. `.env` is loaded automatically and must not be committed.

If Redis is not already running, start it locally (for example with Docker Desktop):

```powershell
docker run --name meeting-redis -p 6379:6379 -d redis:7-alpine
```

Use separate PowerShell terminals, each from `python_meeting_summarizer_venv\backend`:

```powershell
# Django API
..\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

```powershell
# Celery worker (solo pool is suitable for local Windows development)
..\Scripts\python.exe -m celery -A core worker --loglevel=info --pool=solo
```

```powershell
# One Celery Beat scheduler
..\Scripts\python.exe -m celery -A core beat --loglevel=info
```

The API is at <http://127.0.0.1:8000/api/> and Django admin is at <http://127.0.0.1:8000/admin/>. Without `OPENAI_API_KEY`, processing fails visibly rather than saving placeholder AI output. Without SendGrid, email delivery is marked failed rather than reported as sent.

## Environment variables

| Variable | Purpose |
| --- | --- |
| `DJANGO_SECRET_KEY` | Django signing secret; use a unique secret outside local development |
| `DJANGO_DEBUG` | Debug mode (`True` locally; set `False` in deployment) |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated permitted host names |
| `CORS_ALLOWED_ORIGINS` | Comma-separated frontend origins; defaults to both `localhost:5173` and `127.0.0.1:5173` |
| `OPENAI_API_KEY` | Required for Whisper transcription and meeting analysis |
| `OPENAI_MODEL` | Analysis model; defaults to `gpt-4o-mini` |
| `SENDGRID_API_KEY` | Enables email delivery |
| `DEFAULT_FROM_EMAIL` | Verified sender for SendGrid |
| `CELERY_BROKER_URL` | Redis broker; defaults to `redis://localhost:6379/0` |
| `CELERY_RESULT_BACKEND` | Redis result backend; defaults to `redis://localhost:6379/0` |
| `POSTGRES_DB` | Set to enable PostgreSQL instead of local SQLite |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT` | PostgreSQL connection settings |

`ANTHROPIC_API_KEY` is not used; the current AI integration is OpenAI.

## API

All routes below are under `/api/`. Except registration, login, and token refresh, routes require `Authorization: Bearer <access-token>`.

| Method | Route | Description |
| --- | --- | --- |
| `POST` | `auth/register/` | Create a member account |
| `POST` | `auth/login/` | Obtain JWT access and refresh tokens |
| `POST` | `auth/login/refresh/` | Refresh an access token |
| `GET` | `auth/me/` | Current user profile |
| `GET`, `POST` | `meetings/` | List or create meetings |
| `GET`, `PATCH`, `PUT`, `DELETE` | `meetings/<uuid>/` | Read or manage an accessible meeting |
| `POST` | `meetings/<uuid>/retry/` | Retry a meeting whose processing failed |
| `GET` | `meetings/analytics/` | Meeting and action-item metrics |
| `GET`, `POST` | `action-items/` | List or create accessible tasks |
| `PATCH` | `action-items/<uuid>/` | Update a task, including completion status |
| `POST` | `action-items/<uuid>/draft-followup/` | Create or retrieve an editable email draft |
| `GET` | `email-logs/` | List accessible follow-up email records |
| `PATCH` | `email-logs/<uuid>/edit/` | Edit a draft subject and/or body |
| `POST` | `email-logs/<uuid>/send/` | Send a draft through SendGrid |
| `GET` | `reminders/` | List accessible reminder records |

Meeting creation accepts multipart form data with a `title` and either:

- `audio_file`: MP3, MP4, MPEG, MPGA, M4A, WAV, or WebM, up to 25 MB; or
- `transcript`: transcript text or rough meeting notes, up to 100,000 characters.

Audio is not chunked, and Whisper does not provide speaker diarization through this implementation. AI owners are matched to users in the same organization; unmatched owners default to the meeting creator. A missing deadline stays unset.

## Roles and organization access

- New public registrations are always `member`; registration cannot grant manager/admin privileges.
- Admins can promote users and set roles/organizations in Django admin.
- Managers and admins with an organization can see that organization's meetings and tasks.
- Members can see meetings they created and tasks assigned to them or in their own meetings.
- Organizations are currently identified by a shared text value. There is no invitation or organization provisioning workflow; use controlled enrollment before exposing this to multiple tenants.

## Database and migrations

SQLite is the default local database. To use PostgreSQL, set `POSTGRES_DB` and connection variables in `.env`, then run:

```powershell
..\Scripts\python.exe manage.py migrate
```

Keep migration files in version control. Existing installations must apply migrations before starting the updated backend.

## Tests and checks

From `python_meeting_summarizer_venv\backend`:

```powershell
..\Scripts\python.exe manage.py check
..\Scripts\python.exe manage.py makemigrations --check --dry-run
..\Scripts\python.exe manage.py test meetings
```

## Deployment and privacy

Before production, set `DJANGO_DEBUG=False`, a unique secret key, explicit hosts/CORS origins, HTTPS, secure media storage, database backups, and monitoring for Celery failures. The development media route is only enabled in debug mode and is not an authenticated private-file service. Confirm consent, retention, and third-party AI/email processing requirements before using real recordings.
