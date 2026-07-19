# AI Meeting Scheduler

An AI-assisted meeting scheduling platform. A FastAPI backend handles
scheduling, availability, conflict detection, and best-effort Google
Calendar/Meet sync and email notifications; a React/TypeScript frontend
provides the UI, including a Gemini-powered text and voice scheduling
assistant.

## Project Status

- **Working local MVP.** All core scheduling, availability, conflict
  detection, resource booking, and AI (text/voice) scheduling flows run
  end-to-end locally and via Docker Compose.
- **Completed and validated:** Redis caching layer (real automated test
  suite, run in CI), the availability engine's timezone-aware logic
  (exercised by the same suite), and AI/Voice recipient resolution (real
  automated test suite, run locally — not yet wired into CI; see below).
  GitHub Actions CI itself runs successfully against real
  PostgreSQL/Redis service containers.
- **AI/Voice recipient resolution.** AI Text and Voice Scheduling extract
  email addresses mentioned in a natural-language request and resolve
  them authoritatively against PostgreSQL: an address matching a
  registered user becomes a participant (never duplicated as an external
  guest), everything else becomes an external guest. Explicit numeric
  participant IDs are still supported and are merged/deduplicated with
  any resolved IDs; extracted emails are normalized/deduplicated
  case-insensitively. Voice Scheduling inherits this exact behavior
  through its existing transcription → AI-text flow — no logic is
  duplicated. `SchedulerService` remains solely responsible for meeting
  persistence and (best-effort) notification delivery; a meeting with no
  participants/guests is still created successfully. Covered by 11
  focused automated tests
  (`backend/tests/test_ai_voice_recipient_resolution.py`) plus a
  one-time real local HTTP validation run against PostgreSQL and Redis —
  see [Testing & Validation](#testing--validation).
- **Implemented, wired end-to-end, but without automated test coverage:**
  authentication, meeting CRUD, recurring meetings, team/external-guest
  meetings, conflict detection, resource booking, KPI analytics, and the
  rest of the AI text/voice scheduling pipeline (Gemini's actual
  parsing/transcription, meeting summarization, follow-up drafting).
  Recipient resolution is the one part of the AI/Voice pipeline with
  automated coverage — see above. These work in manual/local testing but
  otherwise have no automated regression tests beyond the Redis and
  AI/Voice recipient-resolution suites. See the
  [feature matrix](#feature-matrix) for the reasoning behind each
  classification.
- **Best-effort external integrations:** Google Calendar sync, Google Meet
  links, and SMTP email notifications are all wrapped so a provider outage
  never blocks the core scheduling operation — see
  [Known Limitations](#known-limitations).
- **Not implemented:** Microsoft Outlook/Teams, Slack, WhatsApp, push
  notifications, automatic (as opposed to suggested) rescheduling, and any
  cloud/production deployment (GCP, Kubernetes). See
  [Roadmap](#roadmap).
- **Production limitations:** no secrets manager, no HTTPS termination, and
  no cloud deployment configuration exist yet — this is a local/Docker
  development setup, not a production deployment.

## Feature Matrix

| Feature | Status |
|---|---|
| Authentication (JWT) | ✅ Implemented, not automated-tested |
| Meeting CRUD | ✅ Implemented, not automated-tested |
| Recurring Meetings (weekly, up to 52 occurrences) | ✅ Implemented, not automated-tested |
| Team Meetings (multi-participant) | ✅ Implemented, not automated-tested |
| External Meetings/Guests | ✅ Implemented, not automated-tested |
| Availability Engine | ✅ Completed and validated |
| Conflict Detection | ✅ Implemented, not automated-tested |
| Time Zone Management | ✅ Implemented, not automated-tested |
| Resource Booking | ✅ Implemented, not automated-tested |
| AI Text Scheduling (Gemini) | ⚠️ Implemented — recipient resolution automated-tested locally (11 tests, not yet in CI); Gemini's own parsing not automated-tested |
| Voice Scheduling (Gemini transcription) | ⚠️ Implemented — inherits the same automated-tested recipient resolution (via mocked transcription); Gemini's own transcription not automated-tested |
| AI Scheduling Assistant (text + voice UI) | ✅ Implemented, not automated-tested |
| Auto Rescheduling | ❌ Not implemented — only a read-only "suggest slots" endpoint exists |
| Meeting Notes | ✅ Implemented, not automated-tested |
| Action Items | ✅ Implemented, not automated-tested |
| Meeting Summaries (Gemini) | ✅ Implemented, not automated-tested |
| Follow-up Generation (Gemini, draft only) | ✅ Implemented, not automated-tested |
| KPI Analytics | ✅ Implemented, not automated-tested |
| Google OAuth | ✅ Implemented, not automated-tested (needs live credentials) |
| Google Calendar sync | ⚠️ Best-effort — failures never block meeting operations |
| Google Meet links | ⚠️ Best-effort — comes free from Calendar event creation |
| Email Notifications (SMTP) | ⚠️ Best-effort — failures never block scheduling |
| Redis Caching | ✅ Completed and validated (real test suite, run in CI) |
| Docker (Compose) | ✅ Implemented — CI validates config only, not a live build |
| GitHub Actions CI | ✅ Completed and validated |
| Microsoft Outlook | ❌ Not implemented / planned |
| Microsoft Teams | ❌ Not implemented / planned |
| Slack | ❌ Not implemented / planned |
| WhatsApp | ❌ Not implemented / planned |
| Push Notifications | ❌ Not implemented / planned |
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

| Category | Variables |
|---|---|
| Database | `DATABASE_URL`, `SQLALCHEMY_ECHO` |
| Auth (JWT) | `SECRET_KEY` (required, no default — generate with `openssl rand -hex 32`), `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES` |
| AI (Gemini) | `GEMINI_API_KEY` (optional — AI endpoints return 503 when absent), `GEMINI_MODEL` |
| Google | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`, `FRONTEND_URL` |
| Email (SMTP) | `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USERNAME`, `EMAIL_PASSWORD`, `EMAIL_FROM`, `EMAIL_USE_SSL`, `EMAIL_TIMEOUT_SECONDS` |
| Redis | `REDIS_URL` (optional), `REDIS_SOCKET_TIMEOUT_SECONDS`, `REDIS_CONNECT_TIMEOUT_SECONDS` |
| CORS / pagination | `CORS_ORIGINS`, `DEFAULT_PAGE_SIZE`, `MAX_PAGE_SIZE` |

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

Full instructions live in [DOCKER.md](DOCKER.md). Summary:

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
- Backend health check: `http://localhost:8000/health`
- The `backend` container runs `alembic upgrade head` automatically before
  starting Uvicorn.
- The Postgres volume (`postgres_data`) persists across `docker compose
  down` / `up` cycles; only `down -v` deletes it.
- `VITE_API_URL` is baked into the frontend's static bundle at *build*
  time (Vite inlines env vars at build time, not runtime) — changing it
  requires `docker compose up -d --build` again.

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
  Redis test suite (`python -m unittest tests.test_redis_cache`), and does
  a Redis ping/set/get smoke test. The AI/Voice recipient-resolution
  suite (`tests.test_ai_voice_recipient_resolution`) is not part of this
  job yet — see [Testing & Validation](#testing--validation).
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
- **Backend automated tests — Redis caching** —
  `backend/tests/test_redis_cache.py`, a real `unittest` suite (16
  tests) covering cache hit/miss, TTL, malformed-JSON purge, prefix
  invalidation, per-user isolation, and graceful degradation when Redis
  is unavailable or unconfigured. Run in CI.
- **Backend automated tests — AI/Voice recipient resolution** —
  `backend/tests/test_ai_voice_recipient_resolution.py`, a real
  `unittest` suite (11 tests) exercising `AIMeetingService` and
  `SchedulerService`'s real orchestration logic end-to-end, with only
  Gemini, Google Calendar, and SMTP mocked at the provider boundary.
  Covers: registered-participant email resolution, external-guest email
  resolution, mixed recipients, case-insensitive email deduplication,
  explicit numeric participant IDs, participant/email overlap
  deduplication, no-recipient scheduling, invalid-extracted-email
  handling, SMTP-failure isolation, and the same behavior inherited by
  Voice Scheduling via mocked transcription. **Not currently run in
  CI** — see [GitHub Actions CI](#github-actions-ci); run it locally
  with `python -m unittest tests.test_ai_voice_recipient_resolution -v`
  from `backend/`.
- **Real local HTTP validation (AI/Voice recipient resolution)** — a
  one-time manual validation run (not an automated/repeatable suite)
  that exercised the actual FastAPI app in-process against a real local
  PostgreSQL and a real local Redis instance, with Gemini, Google
  Calendar, and SMTP mocked at the provider boundary (never called
  live). All of the following passed, with all temporary rows/cache
  keys cleaned up afterward: registered-participant AI-text scheduling,
  external-guest AI-text scheduling, mixed-recipient AI-text scheduling,
  registered-participant Voice scheduling, external-guest Voice
  scheduling, no-recipient scheduling, SMTP-failure isolation, and a
  manual `/scheduler/schedule` regression check.
- **Redis-focused / live Postgres+Redis validation** — CI runs
  migrations and the Redis suite against real service containers, not
  mocks.
- **Frontend build/typecheck** — `npm run build` and `npx tsc -b --force`
  run in CI; there is no frontend test suite.
- **Docker validation** — CI runs `docker compose config` only (parses
  and resolves the compose file); it does not build images or start
  containers. A full local `docker compose up -d --build` should be run
  manually before relying on the Docker setup.
- **Not covered by automation** (manual/browser verification only):
  Google Calendar/Meet sync, real email delivery (inbox verification),
  Gemini's actual parsing/transcription accuracy, and Voice Scheduling's
  real microphone capture (requires a live browser + hardware). These
  require live credentials/hardware and are exercised by hand during
  development — not by CI, and not by the recipient-resolution suite
  above (which mocks Gemini entirely).
- **GitHub Actions** — validated by actually running on GitHub's hosted
  runners on every push/PR to `main`, not just locally. It currently
  validates backend (static checks + Redis suite), frontend
  (build/typecheck), and Docker Compose config only — the AI/Voice
  recipient-resolution suite is not yet wired into `ci.yml`.

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

- Microsoft Outlook/Teams, Slack, WhatsApp, and push notifications are
  not implemented.
- There is no automatic rescheduling — `GET
  /scheduler/meetings/{id}/reschedule-suggestions` only returns candidate
  slots; applying one is a manual action.
- Google Calendar sync, Google Meet links, and email notifications are
  all best-effort: a provider failure is logged but never blocks the
  underlying meeting operation, which means a user can have a meeting
  recorded in the app without a corresponding calendar event or email
  actually having been delivered.
- Beyond the Redis cache-aside suite and the AI/Voice recipient-resolution
  suite (recipient extraction/resolution only — not Gemini's own
  parsing/transcription), there is no automated test coverage for
  authentication, meeting CRUD, general scheduling, conflict detection,
  meeting summarization, or follow-up drafting.
- No production secrets manager, HTTPS termination, or cloud deployment
  configuration exists — this project is validated for local/Docker
  development only.
- `GET /google/login` accepts the access token as a `?token=` query
  parameter (in addition to the standard `Authorization` header) because
  a full-page browser redirect cannot attach a header. See
  [Security Notes](#security-notes).

## Roadmap

- Microsoft Outlook / Teams integration
- Slack integration
- WhatsApp integration
- Push notifications
- GCP deployment
- Kubernetes
- Analytics platform integrations (Metabase, Power BI, Looker Studio)
- Production hardening: secrets management, HTTPS, broader automated
  test coverage

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
