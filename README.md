# AI Meeting Scheduler

An AI-assisted meeting scheduling platform. A FastAPI backend handles
scheduling, availability, conflict detection, and best-effort Google
Calendar/Meet sync and email notifications; a React/TypeScript frontend
provides the UI, including a Gemini-powered text and voice scheduling
assistant.

## Project Status

- **Feature-complete and production-readiness-hardened.** All core
  scheduling, availability, conflict detection, resource booking,
  recurring meetings, real-time updates, AI (text/voice) scheduling,
  and analytics flows run end-to-end locally and via Docker Compose.
  See [DEPLOYMENT.md](DEPLOYMENT.md) for what's actually required to
  deploy this to a real production environment (managed database,
  TLS termination, production OAuth credentials — none of that is
  automated by this repo).
- **Automated backend test suite**: the full suite in `backend/tests/`
  (auth, meeting CRUD, conflict detection on both create and update,
  recurring series, every calendar/notification integration, OAuth
  flows, analytics, rate limiting, WebSockets, background jobs) runs
  in CI on every push/PR against real PostgreSQL and Redis service
  containers — see [Testing & Validation](#testing--validation) for
  the exact command and current results.
- **Integrations implemented**: Google Calendar + Google Meet sync,
  "Sign in with Google" login (separate from Calendar OAuth), Microsoft
  Outlook/Teams, Zoom, Slack, and WhatsApp/Web-Push notifications.
  Every one of these except Google Calendar OAuth is optional — its
  endpoints return a clean error (not a crash) when unconfigured, and
  core scheduling is unaffected either way.
- **AI features**: Gemini-powered text and voice scheduling (with
  recipient resolution against real registered users vs. external
  guests), meeting summaries, action items, follow-up drafting, and
  AI insights on the Analytics page.
- **Recurring meetings**: true series (daily/weekly/monthly cadence,
  "this and following" edit/cancel), plus a separate auto-reschedule
  feature that finds and applies the first open slot within a
  configurable window.
- **Real-time updates**: WebSocket-based live updates when a meeting
  is created, updated, or cancelled, invalidating the relevant
  dashboard/analytics data on every connected client.
- **Analytics**: a full Analytics page (trend charts, duration/
  utilization/productivity, reschedule/cancellation/resource/guest/
  notification/integration analytics, AI insights, CSV/Excel/PDF
  export) in addition to the Dashboard's KPI summary.
- **Best-effort external integrations:** every calendar sync and
  notification channel is wrapped so a provider outage never blocks
  the core scheduling operation — see
  [Known Limitations](#known-limitations).
- **Not implemented:** GCP/Kubernetes deployment automation and BI-tool
  integrations (Metabase/Power BI/Looker Studio) — see
  [Roadmap](#roadmap). These are genuinely out of scope, not stale
  claims left over from an earlier version of this document.
- **Production posture:** fail-fast environment validation, structured
  JSON logging with request-ID correlation, `/health/live`,
  `/health/ready`, and `/metrics` endpoints, baseline security
  headers, rate limiting, and non-root/resource-limited Docker images
  are all in place — see [DEPLOYMENT.md](DEPLOYMENT.md) for what
  still needs your own infrastructure (managed Postgres with backups,
  a TLS-terminating proxy, a secrets manager, production OAuth
  redirect URIs).

## Feature Matrix

| Feature | Status |
|---|---|
| Authentication (JWT) | ✅ Implemented, automated-tested |
| Meeting CRUD (incl. conflict detection on create and update) | ✅ Implemented, automated-tested |
| Recurring Meetings (daily/weekly/monthly series, edit/cancel "this and following") | ✅ Implemented, automated-tested |
| Team Meetings (multi-participant) | ✅ Implemented, automated-tested |
| External Meetings/Guests | ✅ Implemented, automated-tested |
| Availability Engine | ✅ Completed and validated |
| Conflict Detection | ✅ Implemented, automated-tested |
| Time Zone Management | ✅ Implemented, automated-tested |
| Resource Booking | ✅ Implemented, automated-tested |
| AI Text Scheduling (Gemini) | ⚠️ Implemented and automated-tested (recipient resolution); Gemini's own parsing is not automated-tested (requires live credentials) |
| Voice Scheduling (Gemini transcription) | ⚠️ Implemented, inherits the same automated-tested recipient resolution; Gemini's own transcription is not automated-tested |
| AI Scheduling Assistant (text + voice UI) | ✅ Implemented, automated-tested |
| Auto Rescheduling | ✅ Implemented, automated-tested — finds and applies the first open slot within a configurable window |
| Meeting Notes | ✅ Implemented, automated-tested |
| Action Items | ✅ Implemented, automated-tested |
| Meeting Summaries (Gemini) | ✅ Implemented, automated-tested |
| Follow-up Generation (Gemini, draft only) | ✅ Implemented, automated-tested |
| Analytics Dashboard + Analytics page | ✅ Implemented, automated-tested |
| Google OAuth (Calendar) | ✅ Implemented, automated-tested (needs live credentials for real sync) |
| "Sign in with Google" (login) | ✅ Implemented, automated-tested |
| Google Calendar sync | ⚠️ Best-effort — failures never block meeting operations |
| Google Meet links | ⚠️ Best-effort — comes free from Calendar event creation |
| Microsoft Outlook / Teams | ✅ Implemented, automated-tested — optional, needs live credentials |
| Zoom | ✅ Implemented, automated-tested — optional, needs live credentials |
| Slack | ✅ Implemented, automated-tested — optional, needs live credentials |
| WhatsApp | ✅ Implemented, automated-tested — optional, needs live credentials |
| Web Push Notifications | ✅ Implemented, automated-tested — optional, needs VAPID keys |
| Email Notifications (SMTP) | ⚠️ Best-effort — failures never block scheduling |
| WebSockets / real-time updates | ✅ Implemented, automated-tested |
| Rate Limiting | ✅ Implemented, automated-tested |
| Redis Caching | ✅ Completed and validated (real test suite, run in CI) |
| Docker (Compose) | ✅ Implemented — non-root images, resource limits; CI validates config only, not a live build |
| GitHub Actions CI | ✅ Completed and validated |
| Production readiness (health/readiness/metrics, structured logging, security headers, fail-fast config) | ✅ Implemented — see [DEPLOYMENT.md](DEPLOYMENT.md) |
| GCP Deployment | ❌ Not implemented / planned |
| Kubernetes | ❌ Not implemented / planned |
| Metabase / Power BI / Looker Studio | ❌ Not implemented / planned |

## Architecture

- **Frontend** — React 19 + TypeScript, built with Vite, styled with
  Tailwind CSS, served via nginx in Docker.
- **Backend** — FastAPI (Python 3.12), SQLAlchemy ORM, Alembic migrations.
- **Database** — PostgreSQL (source of truth for all data).
- **Cache** — Redis, optional cache-aside layer in front of PostgreSQL for
  meetings/availability/resources/KPI reads.
- **AI layer** — Google Gemini (`google-genai` SDK) for natural-language
  and voice-audio parsing, meeting summarization, action-item extraction,
  and follow-up drafting.
- **Google Calendar/Meet** — OAuth-based Calendar event creation carries a
  Google Meet link (`hangoutLink`) automatically; no separate Meet API.
- **Email** — SMTP (e.g. Gmail) for meeting invite/update/cancellation
  notifications.
- **Docker Compose** — orchestrates postgres, redis, backend, and frontend
  containers for local development.
- **GitHub Actions CI** — backend, frontend, and Docker Compose config
  validation on every push/PR to `main`.

### Scheduling Flow

```
User input (form or AI text/voice)
  → API request
  → AI parsing (Gemini) + recipient resolution, when using the AI
    assistant (email addresses extracted from the text are resolved
    against PostgreSQL: registered users → participant IDs, everyone
    else → external guests)
  → Availability + conflict validation
  → Meeting persistence (PostgreSQL)
  → Google Calendar/Meet sync (best-effort)
  → Email notification to participants/guests (best-effort)
  → Redis cache invalidation (meetings/availability/KPI)
  → KPI counters updated
```

## Repository Structure

```
AI_Meeting_Scheduler/
├── backend/
│   ├── app/
│   │   ├── api/            # FastAPI routers (one file per resource)
│   │   ├── auth/            # JWT + password hashing
│   │   ├── calendar/         # Google OAuth flow + Calendar client
│   │   ├── core/             # Settings, Redis cache, exception handlers
│   │   ├── db/                # SQLAlchemy session/engine setup
│   │   ├── models/            # ORM models
│   │   ├── repositories/       # Data-access layer
│   │   ├── schemas/             # Pydantic request/response schemas
│   │   ├── services/             # Business logic
│   │   └── main.py                # FastAPI app + router registration
│   ├── alembic/versions/            # Database migrations
│   ├── tests/
│   │   ├── test_redis_cache.py                    # Automated test suite (run in CI)
│   │   └── test_ai_voice_recipient_resolution.py  # AI/Voice recipient-resolution suite (run locally, not yet in CI)
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── api/            # Axios API clients, one per backend resource
│   │   ├── components/     # Layout, shared, and UI components
│   │   ├── hooks/          # useAuth, useVoiceRecorder
│   │   ├── pages/          # Route-level pages (Dashboard, AIAssistant, ...)
│   │   └── App.tsx
│   ├── Dockerfile
│   ├── nginx.conf
│   └── .env.example
├── docker-compose.yml
├── DOCKER.md
├── .env.docker.example
└── .github/workflows/ci.yml
```

## Local Development Prerequisites

- Python 3.12+
- Node.js 20+ and npm
- PostgreSQL 16 (or use the Docker Compose `postgres` service — see
  [Docker Setup](#docker-setup))
- Redis (optional — see [Redis Setup](#redis-setup))
- A Google Cloud OAuth client, if you want Calendar/Meet integration
  (see [Google OAuth Setup](#google-oauth-setup))
- An SMTP account, if you want email notifications
  (see [Email Setup](#email-setup))
- A Gemini API key, if you want AI text/voice scheduling
  (see [Environment Variables](#environment-variables))

## Backend Local Setup

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

pip install -r requirements.txt

copy .env.example .env        # Windows
# cp .env.example .env        # macOS/Linux
# then fill in real values — see Environment Variables below

alembic upgrade head
python run.py
```

Backend runs at `http://127.0.0.1:8000` (interactive docs at `/docs`).

## Frontend Local Setup

```bash
cd frontend
copy .env.example .env        # Windows
# cp .env.example .env        # macOS/Linux

npm install
npm run dev
```

Frontend runs at `http://localhost:5173` and expects `VITE_API_URL` (in
`frontend/.env`) to point at the backend, e.g. `http://localhost:8000`.

## PostgreSQL Setup

The backend expects a running PostgreSQL 16 instance and a `DATABASE_URL`
in `backend/.env` (e.g.
`postgresql+psycopg2://user:password@localhost:5432/dbname`). Create the
database and user yourself, then run `alembic upgrade head` from
`backend/` to create the schema. If you're running via Docker Compose, the
`postgres` service and schema migration are handled for you automatically
— see [Docker Setup](#docker-setup).

## Redis Setup

Redis is **optional infrastructure**, not a hard dependency:

- If `REDIS_URL` in `backend/.env` is unset, blank, or the Redis instance
  is unreachable, caching is silently disabled and every read falls back
  directly to PostgreSQL. This is a supported configuration, not a
  degraded one — the app starts and runs normally either way.
- To enable caching locally: run Redis yourself (`redis-server`, a local
  container, etc.) and set `REDIS_URL=redis://localhost:6379/0`.
- Under Docker Compose, the `redis` service is started automatically and
  wired up for you.

## Environment Variables

Two `.env` files are involved for non-Docker local development (Docker
Compose has its own root `.env` — see [Docker Setup](#docker-setup)).
Copy the `.example` files and fill in real values; **never commit an
actual `.env` file** (`.gitignore` already excludes `.env` / `**/.env`).

**`backend/.env`** (copy from `backend/.env.example`):

See [`backend/.env.example`](backend/.env.example) for the authoritative,
fully-commented list (every variable `app/core/config.py` reads, which
ones are required vs. optional, and which commonly-expected variables
are deliberately *not* used by this app and why). Summary:

| Category | Variables |
|---|---|
| Database | `DATABASE_URL` (required), `SQLALCHEMY_ECHO` |
| Auth (JWT) | `SECRET_KEY` (required, no default — generate with `openssl rand -hex 32`), `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES` |
| Rate limiting | `AUTH_RATE_LIMIT` — applied only to login/register/Google login |
| AI (Gemini) | `GEMINI_API_KEY` (optional — AI endpoints return 503 when absent), `GEMINI_MODEL` |
| Google (Calendar + login) | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI` (Calendar connect), `GOOGLE_LOGIN_REDIRECT_URI` ("Sign in with Google" — a separate callback path on the same OAuth client), `FRONTEND_URL` |
| Outlook / Teams (optional) | `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET`, `MICROSOFT_REDIRECT_URI`, `MICROSOFT_TENANT_ID`, `MICROSOFT_SCOPES` |
| Zoom (optional) | `ZOOM_CLIENT_ID`, `ZOOM_CLIENT_SECRET`, `ZOOM_REDIRECT_URI`, `ZOOM_SCOPES` |
| Slack (optional) | `SLACK_CLIENT_ID`, `SLACK_CLIENT_SECRET`, `SLACK_REDIRECT_URI`, `SLACK_SCOPES` |
| WhatsApp (optional) | `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_API_VERSION` |
| Push / VAPID (optional) | `VAPID_PRIVATE_KEY`, `VAPID_PUBLIC_KEY`, `VAPID_CLAIM_EMAIL` |
| Email (SMTP) | `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USERNAME`, `EMAIL_PASSWORD`, `EMAIL_FROM`, `EMAIL_USE_SSL`, `EMAIL_TIMEOUT_SECONDS` |
| Redis | `REDIS_URL` (optional), `REDIS_SOCKET_TIMEOUT_SECONDS`, `REDIS_CONNECT_TIMEOUT_SECONDS` |
| CORS / pagination | `CORS_ORIGINS`, `DEFAULT_PAGE_SIZE`, `MAX_PAGE_SIZE` |
| Logging / environment | `LOG_LEVEL`, `LOG_FORMAT` (`text` or `json`), `ENVIRONMENT` (informational) |

**`frontend/.env`** (copy from `frontend/.env.example`):

| Category | Variables |
|---|---|
| Frontend | `VITE_API_URL` — base URL of the FastAPI backend, no trailing slash |

## Alembic Migrations

Run from `backend/`, with `backend/.env` configured:

```bash
alembic upgrade head        # apply all migrations
alembic heads                # confirm a single head (CI enforces this)
alembic revision --autogenerate -m "description"   # create a new migration
alembic downgrade -1          # roll back one migration
```

## Docker Setup

```bash
copy .env.docker.example .env      # Windows, repo root
# cp .env.docker.example .env      # macOS/Linux
# then fill in Postgres credentials/ports

copy backend\.env.example backend\.env   # Windows
# cp backend/.env.example backend/.env   # macOS/Linux
# then fill in SMTP/Google/JWT/Gemini values

docker compose up -d --build       # build and start everything
docker compose down                 # stop
docker compose down -v               # stop and wipe the Postgres volume
```

- Frontend: `http://localhost:5173`
- Backend API: `http://localhost:8000`
- Backend health check: `http://localhost:8000/health` (also
  `/health/live` and `/health/ready` — see [DEPLOYMENT.md](DEPLOYMENT.md)
  for the difference); Prometheus metrics at `/metrics`.
- The `backend` container runs `alembic upgrade head` automatically before
  starting Uvicorn.
- The Postgres volume (`postgres_data`) persists across `docker compose
  down` / `up` cycles; only `down -v` deletes it.
- `VITE_API_URL` is baked into the frontend's static bundle at *build*
  time (Vite inlines env vars at build time, not runtime) — changing it
  requires `docker compose up -d --build` again.
- The `backend` image runs uvicorn as a dedicated non-root `app` user.
  The `frontend` image's nginx master process starts as root (needed
  to bind port 80) and drops its worker processes to the `nginx` user
  — this is `nginx:1.27-alpine`'s own built-in behavior, unchanged by
  this project. `docker-compose.yml` sets CPU/memory limits on all
  four services.
- For a real production deployment (managed database, TLS, secrets
  management, etc. rather than this local `docker-compose.yml`), see
  [DEPLOYMENT.md](DEPLOYMENT.md).

## Google OAuth Setup

1. Create an OAuth 2.0 Client ID in
   [Google Cloud Console](https://console.cloud.google.com/) (Web
   application type).
2. Add `http://localhost:8000/google/callback` as an authorized redirect
   URI (this must exactly match `GOOGLE_REDIRECT_URI` in `backend/.env`).
3. Put the client ID/secret into `backend/.env` as `GOOGLE_CLIENT_ID` /
   `GOOGLE_CLIENT_SECRET`. **These are your own credentials — this repo
   does not ship or supply real Google credentials.**
4. Connection flow: the frontend's Settings page links to
   `GET /google/login`, which redirects the browser to Google's consent
   screen, then back to `GET /google/callback`, which exchanges the code,
   stores credentials, and redirects to `{FRONTEND_URL}/settings`.
5. Once connected, meeting create/update/delete operations attempt to
   sync a corresponding Google Calendar event (with a Meet link) as a
   best-effort side effect — see [Known Limitations](#known-limitations).

## Outlook OAuth Setup

1. Register an app in [Azure AD App registrations](https://portal.azure.com)
   (Azure Active Directory → App registrations → New registration).
2. Add `http://localhost:8000/outlook/callback` as a redirect URI (Web
   platform) — must exactly match `MICROSOFT_REDIRECT_URI` in `backend/.env`.
3. Under API permissions, add the Microsoft Graph delegated scopes
   `Calendars.ReadWrite` and `OnlineMeetings.ReadWrite` (the latter is
   needed for Microsoft Teams meetings — see step 5).
4. Put the client ID/secret into `backend/.env` as `MICROSOFT_CLIENT_ID` /
   `MICROSOFT_CLIENT_SECRET`. `MICROSOFT_TENANT_ID=common` (the default)
   allows both work/school and personal Microsoft accounts to sign in.
5. Microsoft Teams meetings are not a separate integration to configure —
   they reuse this same Outlook connection: `POST /teams/sync/{meeting_id}`
   marks an existing Outlook-synced event as a Teams meeting. A user who
   connected Outlook before `OnlineMeetings.ReadWrite` was added will get a
   400 asking them to reconnect once, rather than failing silently.
6. Optional: `/outlook` and `/teams` endpoints return 503 when these
   variables are absent or blank — nothing else in the app is affected.

## Zoom OAuth Setup

1. Register a **User-managed app** (Authorization Code Grant) at
   [Zoom App Marketplace → Develop](https://marketplace.zoom.us/develop/create).
2. Add `http://localhost:8000/zoom/callback` as the redirect URL — must
   exactly match `ZOOM_REDIRECT_URI` in `backend/.env`.
3. Under Scopes, add `meeting:write:meeting`, `meeting:read:meeting`, and
   `user:read:user`.
4. Put the client ID/secret into `backend/.env` as `ZOOM_CLIENT_ID` /
   `ZOOM_CLIENT_SECRET`.
5. Optional: `/zoom` endpoints return 503 when absent or blank.

## Slack OAuth Setup

1. Create a Slack app at [api.slack.com/apps](https://api.slack.com/apps).
2. Under OAuth & Permissions → Redirect URLs, add
   `http://localhost:8000/slack/callback` — must exactly match
   `SLACK_REDIRECT_URI` in `backend/.env`.
3. Under OAuth & Permissions → Bot Token Scopes, add `chat:write` (the
   only scope this integration needs — `chat.postMessage` accepts a
   Slack user ID directly as the `channel` parameter to DM that user, so
   no channel-selection or `im:write` scope is required).
4. Put the client ID/secret into `backend/.env` as `SLACK_CLIENT_ID` /
   `SLACK_CLIENT_SECRET`.
5. Each user connects their own Slack account from the frontend's
   Settings page; notifications are sent as a direct message to that
   user, not to a shared channel. There is no single static bot token to
   configure — the per-user access token from the OAuth flow is stored
   in the database instead.
6. Optional: `/slack` endpoints return 503 when absent or blank.

## WhatsApp Setup

1. Create a Meta app with the WhatsApp product added at
   [developers.facebook.com/apps](https://developers.facebook.com/apps).
2. From the WhatsApp → API Setup page, copy a (temporary or permanent)
   access token and the test/production phone number ID.
3. Put these into `backend/.env` as `WHATSAPP_ACCESS_TOKEN` /
   `WHATSAPP_PHONE_NUMBER_ID`.
4. Each user enters their own recipient phone number on the frontend's
   Settings page (stored in `whatsapp_settings`, not in `backend/.env`).
   While the Meta app is in development mode, only numbers explicitly
   added as testers under WhatsApp → API Setup can receive messages —
   `POST /whatsapp/test`'s error message surfaces this exact cause
   (Meta error code 131030) when it's what's blocking a test send.
5. Optional: `/whatsapp` send/test endpoints return 503 when absent or
   blank.

## Push Notifications Setup

1. Generate a VAPID key pair: `vapid --gen` (installed transitively via
   `pywebpush`, already in `backend/requirements.txt`).
2. Put the pair into `backend/.env` as `VAPID_PRIVATE_KEY` /
   `VAPID_PUBLIC_KEY`, and set `VAPID_CLAIM_EMAIL` to a real contact
   address (required by the Web Push protocol as a "who to contact
   about this subscription" identifier for push services).
3. From the frontend's Settings page, "Enable push notifications"
   registers the service worker (`frontend/public/sw.js`) and subscribes
   the browser — each subscription is stored per-user in
   `push_subscriptions`, so a user can have one per browser/device.
4. Requires a browser that supports the Push API (all evergreen
   desktop/mobile browsers do; note that push requires a secure context —
   HTTPS in production, though `localhost` is exempted for local dev).
5. Optional: push sends are always best-effort (never raise) and
   silently no-op when the VAPID keys are absent or blank.

## Email Setup

- Configure SMTP in `backend/.env` (`EMAIL_HOST`, `EMAIL_PORT`,
  `EMAIL_USERNAME`, `EMAIL_PASSWORD`, `EMAIL_FROM`, `EMAIL_USE_SSL`). The
  example values target Gmail SMTP (port 587, STARTTLS).
- `POST /email/test` sends a test email to your own account, useful for
  verifying SMTP configuration.
- Meeting create/update/cancel operations notify participants and
  external guests by email.
- All email sending is **best-effort**: failures are logged but never
  raise, so an SMTP outage never blocks a scheduling operation.

## Redis Caching

- Cached: meetings list, availability list, resources list/detail, and
  KPI analytics reads.
- Cache-aside pattern: reads check Redis first, fall back to PostgreSQL
  on a miss (or on any Redis error), and populate the cache afterward.
- Keys are scoped per user, so one user's cached data is never returned
  to another.
- Invalidation happens on the relevant write (create/update/delete)
  by deleting the affected key prefix.
- PostgreSQL remains the source of truth at all times; Redis is a
  read-through optimization only — see [Redis Setup](#redis-setup) for
  the fallback behavior when Redis is absent or unreachable.

## GitHub Actions CI

Defined in [`.github/workflows/ci.yml`](.github/workflows/ci.yml).
Triggers on every push and pull request targeting `main`. Three jobs:

- **Backend** — spins up real `postgres:16-alpine` and `redis:7-alpine`
  service containers, installs dependencies, asserts exactly one Alembic
  head, runs `alembic upgrade head` against the live Postgres container,
  compiles all Python (`compileall`), imports the FastAPI app, runs the
  **full backend test suite** (`python -m unittest discover -s tests -p
  "test_*.py"` — every file in `backend/tests/`, not just the Redis
  suite), and does a Redis ping/set/get smoke test. Runs on Python 3.12.
- **Frontend** — `npm ci`, `npm run build`, `npx tsc -b --force`
  (type-check only; no frontend test suite exists yet).
- **Docker Compose Config** — writes a placeholder `.env`/`backend/.env`
  and runs `docker compose config` (validates the compose file parses
  and resolves; does not build or run containers).

All SMTP/Google/Gemini values used in CI are explicit placeholders
(`*.invalid` domains, `ci-placeholder-*` strings) — **no external
production credentials or real secrets are required or used by CI.**

## Testing & Validation

What's actually verified, and how:

- **Backend static checks** — `python -m compileall app` and a FastAPI
  app import, both run in CI on every push/PR.
- **Backend automated test suite** — the full contents of
  `backend/tests/` (30+ files covering auth, meeting CRUD, conflict
  detection on create and update, recurring series, resource booking,
  every calendar/notification integration and its OAuth flow, AI/Voice
  recipient resolution, analytics, rate limiting, WebSockets,
  background jobs, and reschedule history), run via
  `python -m unittest discover -s tests -p "test_*.py" -v` from
  `backend/`. Runs in full in CI, against real PostgreSQL and Redis
  service containers on Python 3.12. Locally on Python 3.10 there is
  one known, pre-existing, unrelated failure
  (`test_auto_reschedule_success_via_http`) caused by
  `datetime.fromisoformat()` not accepting a trailing `Z` until Python
  3.11 — it does not occur in CI.
- **Frontend build/typecheck** — `npm run build` and `npx tsc -b --force`
  run in CI; there is no frontend component/unit test suite, and no
  browser-automation (Playwright/Cypress) suite exists yet.
- **Docker validation** — CI runs `docker compose config` only (parses
  and resolves the compose file); it does not build images or start
  containers. Both Dockerfiles and the full `docker compose up -d
  --build` flow have been verified manually (see
  [DEPLOYMENT.md](DEPLOYMENT.md)) but are not part of the automated CI
  pipeline.
- **Not covered by automation** (manual/browser verification only):
  Google Calendar/Meet sync against real Google accounts, real
  Outlook/Zoom/Slack/WhatsApp/Push delivery (each mocked at the
  provider boundary in tests), real email delivery (inbox
  verification), Gemini's actual parsing/transcription accuracy, and
  Voice Scheduling's real microphone capture (requires a live browser
  + hardware). These require live credentials/hardware and are
  exercised by hand during development, not by CI.
- **GitHub Actions** — validated by actually running on GitHub's hosted
  runners on every push/PR to `main`, not just locally.

## API Overview

Grouped by router (see `backend/app/api/`). Full interactive docs at
`/docs` once the backend is running.

**Auth** (`/auth`)
- `POST /auth/register`, `POST /auth/login`, `GET /auth/me`

**Users** (`/users`)
- `GET /users/`, `GET /users/{id}`, `PUT /users/{id}`,
  `PUT /users/{id}/password`, `DELETE /users/{id}`

**Meetings** (`/meetings`)
- `POST /meetings/`, `GET /meetings/`, `GET /meetings/{id}`,
  `PUT /meetings/{id}`, `DELETE /meetings/{id}`,
  `GET /meetings/search`, `GET /meetings/filter/status`,
  `GET /meetings/filter/date`, `GET /meetings/filter/range`

**Meeting Participants**
- `POST /meetings/{id}/participants`, `GET /meetings/{id}/participants`,
  `PUT /participants/{id}`, `DELETE /participants/{id}`

**Availability** (`/availability`)
- `POST /availability/`, `GET /availability/`,
  `PUT /availability/{id}`, `DELETE /availability/{id}`

**Resources** (`/resources`)
- `POST /resources/`, `GET /resources/`, `GET /resources/{id}`,
  `PUT /resources/{id}`

**Scheduler** (`/scheduler`)
- `POST /scheduler/schedule` (full validated scheduling, incl. recurring),
  `POST /scheduler/suggest-slots`,
  `GET /scheduler/meetings/{id}/reschedule-suggestions`

**AI** (`/ai`)
- `POST /ai/schedule-text`, `POST /ai/schedule-voice`,
  `POST /ai/meetings/{id}/summary`, `POST /ai/meetings/{id}/follow-up`

**Meeting Intelligence**
- `GET /meetings/{id}/notes`, `GET /meetings/{id}/summary`,
  `GET /meetings/{id}/action-items`, `PATCH /action-items/{id}`

**Analytics** (`/analytics`)
- `GET /analytics/kpis`

**Google** (`/google`)
- `GET /google/status`, `DELETE /google/disconnect`,
  `GET /google/login`, `GET /google/callback`

**Email** (`/email`)
- `POST /email/test`

## Known Limitations

- `GET /scheduler/meetings/{id}/reschedule-suggestions` returns
  candidate slots without applying one; `POST /scheduler/meetings/{id}
  /auto-reschedule` is the separate endpoint that actually finds and
  applies the first open slot within a window. Both exist — they're
  different operations (preview vs. apply), not a missing feature.
- Google Calendar/Outlook/Teams/Zoom sync, Google Meet links, and
  every notification channel (email, Slack, WhatsApp, push) are all
  best-effort: a provider failure is logged but never blocks the
  underlying meeting operation, which means a user can have a meeting
  recorded in the app without a corresponding calendar event or
  notification actually having been delivered.
- No frontend component/unit test suite or browser-automation
  (Playwright/Cypress) suite exists yet — frontend verification is
  `tsc`/`vite build` plus manual testing.
- No production secrets manager, HTTPS termination, or cloud
  deployment automation (GCP/Kubernetes) exists in this repo — see
  [DEPLOYMENT.md](DEPLOYMENT.md) for what a real production deployment
  needs to add on top of what's here.
- No refresh-token flow: access tokens are short-lived
  (`ACCESS_TOKEN_EXPIRE_MINUTES`, default 30 minutes) with no renewal
  path; an expired token requires signing in again.
- `GET /google/login` accepts the access token as a `?token=` query
  parameter (in addition to the standard `Authorization` header) because
  a full-page browser redirect cannot attach a header. See
  [Security Notes](#security-notes).

## Roadmap

- GCP deployment automation
- Kubernetes
- Analytics platform integrations (Metabase, Power BI, Looker Studio)
- Refresh-token flow
- Frontend component/unit and browser-automation test suites
- Content-Security-Policy tuned to this app's actual asset origins
  (deliberately not added yet — see [DEPLOYMENT.md](DEPLOYMENT.md) §6)

## Security Notes

- Never commit a real `.env` file (`.gitignore` already excludes
  `.env` and `**/.env`).
- Rotate any credential that is ever exposed or suspected compromised
  (JWT `SECRET_KEY`, Google OAuth client secret, SMTP password, Gemini
  API key).
- Use a proper secrets manager in production instead of `.env` files.
- Use HTTPS in production for OAuth redirect URIs and any endpoint that
  handles access tokens.
- `GET /google/login` accepts the JWT access token via a `?token=` query
  parameter as well as the `Authorization` header, specifically to
  support the full-page browser redirect to Google's consent screen
  (which cannot attach a header). Query parameters can end up in browser
  history/server logs — be aware of this tradeoff if extending this flow.
- Authentication uses JWT bearer tokens only (no cookies), so CSRF
  protection does not apply — there is no ambient credential a
  third-party site could ride on.
- Every response carries baseline security headers
  (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`,
  `Permissions-Policy`, `Strict-Transport-Security`) — see
  `backend/app/core/security_headers.py` and `frontend/nginx.conf`.
  A `Content-Security-Policy` header is deliberately *not* set: the
  API docs (`/docs`) load Swagger UI assets from a CDN and the
  frontend uses inline styles in a few chart components plus Google
  Fonts from a CDN, so a CSP needs to be scoped to this app's actual
  asset origins rather than added generically.
- `/auth/login`, `/auth/register`, and the Google login endpoints are
  rate-limited (`AUTH_RATE_LIMIT`, default 5/minute per IP) against
  brute-force attempts.
- See [DEPLOYMENT.md](DEPLOYMENT.md) for the full production security
  checklist, including TLS termination (not handled by either
  container directly) and secrets-management guidance.

## Contributing / Development Workflow

```
main
  → feature branch (feature/<name>)
  → local validation (backend compile/import, frontend build/typecheck,
     relevant tests)
  → pull request
  → GitHub Actions CI (backend, frontend, docker-validate)
  → merge to main
```

## Author

**Allwyn Jeffo Raj**
GitHub: https://github.com/Allwyn00744
