# Deployment Guide

This covers taking the app from `docker-compose.yml` (local/dev) to a
real production deployment. It assumes familiarity with the local
setup in [README.md](README.md) (see its "Docker Setup" section)
already.

## 1. Infrastructure choices

`docker-compose.yml` in this repo is a **local/staging convenience**,
not a production topology (it runs Postgres and Redis as sidecar
containers with a single replica of everything, no failover). For
production:

- **Database**: use a managed PostgreSQL (RDS, Cloud SQL, Azure
  Database for PostgreSQL, etc.) with automated backups and
  point-in-time recovery enabled, rather than the `postgres` service
  in `docker-compose.yml`. Point `DATABASE_URL` at it.
- **Redis**: use a managed Redis (ElastiCache, Memorystore, etc.), or
  run without Redis entirely - it's optional infrastructure
  everywhere in this app (see `app/core/cache.py`); every cached read
  falls back to PostgreSQL when `REDIS_URL` is unset or unreachable.
- **Backend/frontend containers**: the two application images
  (`backend/Dockerfile`, `frontend/Dockerfile`) are what you actually
  deploy - to a container platform of your choice (ECS, Cloud Run,
  Kubernetes, etc.). `docker-compose.yml` only orchestrates them
  locally.
- **TLS**: neither container terminates HTTPS itself - put a load
  balancer/reverse proxy in front of both that terminates TLS and
  forwards plain HTTP internally (this is why `Strict-Transport-Security`
  is already sent by both the backend and `frontend/nginx.conf` -
  browsers only start honoring it once they've received it over an
  actual HTTPS connection, which happens once your TLS-terminating
  proxy is in place).

## 2. Required environment variables

See [`backend/.env.example`](backend/.env.example) for the complete,
authoritative list. At minimum, production needs:

- `DATABASE_URL` pointing at your managed Postgres
- `SECRET_KEY` - a real, unique secret (`openssl rand -hex 32`), never
  the one used in local dev or CI
- `EMAIL_HOST`/`EMAIL_PORT`/`EMAIL_USERNAME`/`EMAIL_PASSWORD`/`EMAIL_FROM`
- `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`/`GOOGLE_REDIRECT_URI` (and
  `GOOGLE_LOGIN_REDIRECT_URI` if "Sign in with Google" is enabled -
  both need to be registered as redirect URIs on the same OAuth
  client, using your real production domain)
- `CORS_ORIGINS` set to your real frontend origin(s) - never `*`
- `FRONTEND_URL` set to your real frontend origin
- `ENVIRONMENT=production`, `LOG_FORMAT=json` (structured logs for
  whatever log aggregator you use), `LOG_LEVEL=INFO`

The app **fails fast at startup** with a clear message listing
exactly which required variables are missing (see
`app/core/config.py`) rather than starting in a broken state - if a
deployment's container exits immediately, check its logs for a
`FATAL: Missing required environment variable(s): ...` line first.

Every other integration (Outlook, Zoom, Slack, WhatsApp, Push, Gemini
AI, Redis) is optional - leaving its variables unset disables that
one feature (typically a 503 from its endpoints) without affecting
anything else. See each one's setup section in
[README.md](README.md).

## 3. Database migrations

Run `alembic upgrade head` (from `backend/`, with `DATABASE_URL`
pointed at production) as part of your deploy process, before
traffic is routed to new instances. The backend Docker image already
does this automatically on container start
(`CMD ["sh", "-c", "alembic upgrade head && uvicorn ..."]`) - if
you're running multiple backend replicas, make sure only one
migration run happens concurrently (e.g. a dedicated migration step/job
in your deploy pipeline, or accept that Alembic's own locking makes a
second concurrent `upgrade head` a safe no-op/wait rather than a race).

**Migration safety**: every migration in `backend/alembic/versions/`
this session added is purely additive (new tables/columns, all
nullable or with a server-side default) - none of them lock or
rewrite an existing table's data, so they're safe to run against a
live database with traffic. CI (`.github/workflows/ci.yml`) already
verifies there is exactly one Alembic head on every push/PR.

**Backup strategy**: use your managed database provider's automated
backups (RDS automated snapshots, Cloud SQL automated backups, etc.)
with point-in-time recovery enabled. If self-hosting Postgres instead,
schedule `pg_dump` (or `pg_basebackup` + WAL archiving for
point-in-time recovery) on a cron, stored somewhere other than the
same host. Always take a manual backup/snapshot immediately before
running a migration in production.

**Seed data**: `backend/scripts/seed_db.py` creates one demo user for
local/staging use - it is not part of any deploy path and should not
be run against production (it's meant for a fresh local/demo
database only).

## 4. Health, readiness, and metrics endpoints

| Endpoint | Purpose |
|---|---|
| `GET /health` | Existing basic liveness check - used by the Dockerfile `HEALTHCHECK` instruction and `docker-compose.yml`'s `depends_on: condition: service_healthy`. Always returns `{"status": "ok"}` if the process is up. |
| `GET /health/live` | Same semantics as `/health` - process is up, no dependency checks. Use for a container orchestrator's liveness probe (restarts the container on failure). |
| `GET /health/ready` | Checks the database (and Redis, only if `REDIS_URL` is configured) are actually reachable right now. Returns 503 with `{"status": "not ready", "checks": {...}}` when a dependency is down. Use for a readiness probe (pulls the instance out of load-balancer rotation without restarting it). |
| `GET /metrics` | Prometheus text-format exposition - request counts/latency histograms per method/path/status, plus Python process metrics. Not included in the OpenAPI schema. Point your Prometheus scrape config (or a compatible collector) at this. |

## 5. Logging

`LOG_FORMAT=json` (recommended for production) emits one JSON object
per log line via `app/core/logging_config.py`, including a
`request_id` field correlated across every log line emitted while
handling a given request (see `app/core/request_id.py` - the same ID
is also echoed back as an `X-Request-ID` response header, so a
client-reported issue can be traced to its exact server-side logs).
Point your log aggregator (CloudWatch Logs, Datadog, ELK, etc.) at
the container's stdout - nothing is written to a local file, so no
log rotation configuration is needed on the container itself.

## 6. Security posture (what's already in place vs. what needs your input)

**Already handled by the app, no action needed:**
- Passwords hashed with bcrypt (`passlib`), never stored/logged in
  plaintext.
- JWT bearer tokens (not cookies) - CSRF does not apply to this
  authentication model (there is no ambient credential a third-party
  site could ride on).
- Baseline security response headers on every response
  (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`,
  `Permissions-Policy`, `Strict-Transport-Security`) - see
  `app/core/security_headers.py` and `frontend/nginx.conf`.
- Rate limiting on login/register/Google-login (`AUTH_RATE_LIMIT`,
  default 5/minute per IP).
- CORS restricted to explicit origins (`CORS_ORIGINS`), wildcard
  origins are rejected even if misconfigured.
- Both Docker images run as non-root users (backend: a dedicated
  `app` user; frontend/nginx: the base image's built-in `nginx` user
  for worker processes).

**Requires your input / not applicable:**
- **TLS termination** - this app does not serve HTTPS directly; put a
  load balancer/reverse proxy in front of it that does (see §1).
- **Content-Security-Policy** - deliberately not set (see comments in
  `app/core/security_headers.py` and `frontend/nginx.conf`): the
  frontend uses inline styles in a few chart components and loads
  Google Fonts from a CDN, so a CSP needs to be built and tested
  against this app's specific asset origins rather than added
  generically. Recommended follow-up if you need it.
- **Refresh tokens** - this app issues short-lived access tokens only
  (`ACCESS_TOKEN_EXPIRE_MINUTES`, default 30 minutes) with no renewal
  path; an expired token requires signing in again. Adding a
  refresh-token flow would be a genuine authentication architecture
  change, out of scope for a production-readiness pass - flagged here
  as a known limitation rather than silently added.
- **Secrets management** - `backend/.env` is fine for a single-host
  deployment but isn't how you should hand secrets to a real
  orchestrator; use its native secrets mechanism (AWS Secrets
  Manager/Parameter Store, GCP Secret Manager, Kubernetes Secrets,
  etc.) to inject the same environment variables instead.

## 7. Pre-launch checklist

- [ ] `DATABASE_URL` points at a managed, backed-up Postgres instance
- [ ] `SECRET_KEY` is unique to this environment (not the dev/CI one)
- [ ] `CORS_ORIGINS` / `FRONTEND_URL` / every OAuth redirect URI use
      the real production domain, registered on each provider's app
      console
- [ ] `ENVIRONMENT=production`, `LOG_FORMAT=json`
- [ ] TLS terminates in front of both containers
- [ ] `alembic upgrade head` has been run against the production
      database
- [ ] A readiness probe is wired to `GET /health/ready` and a
      liveness probe to `GET /health/live` (or `GET /health` if your
      orchestrator only supports one probe)
- [ ] `GET /metrics` is scraped by your monitoring stack
- [ ] A database backup was taken immediately before the first deploy
- [ ] Every OAuth provider you actually use (Google required; Outlook/
      Zoom/Slack/WhatsApp/Push optional - see README.md) has its
      redirect URI registered for the production domain, not
      `localhost`
