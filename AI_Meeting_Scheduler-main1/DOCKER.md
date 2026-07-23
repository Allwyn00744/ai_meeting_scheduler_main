# Docker V1

Runs the full stack (PostgreSQL, Redis, FastAPI backend, React/Vite frontend
served via nginx) with one Docker Compose command.

## Prerequisites

- Docker Desktop (or Docker Engine + Compose plugin) running.
- `backend/.env` — copy from `backend/.env.example` and fill in real values
  (SMTP credentials, Google OAuth client ID/secret, `SECRET_KEY`, optional
  `GEMINI_API_KEY`). `DATABASE_URL` and `REDIS_URL` in this file are ignored
  under Docker — see `.env.docker.example` below.
- `.env` (repo root) — copy from `.env.docker.example` and fill in Postgres
  credentials and port mappings.

Neither `.env` file should ever be committed (`.gitignore` already excludes
`.env` / `**/.env`).

## Start

```
docker compose up -d --build
```

This builds the images, starts `postgres` and `redis`, waits for both to
report healthy, then starts `backend` (which runs `alembic upgrade head`
before starting Uvicorn) and `frontend`.

- Frontend: http://localhost:5173 (or `FRONTEND_PORT` if overridden)
- Backend API: http://localhost:8000 (or `BACKEND_PORT` if overridden)
- Backend health: http://localhost:8000/health

## Stop

```
docker compose down
```

Add `-v` to also delete the persistent PostgreSQL volume (`postgres_data`) —
only do this if you want to wipe the database.

## Restart (after code changes)

```
docker compose up -d --build
```

## Google OAuth (local development)

`GOOGLE_REDIRECT_URI` in `backend/.env` must be a URI registered in the
Google Cloud Console for your OAuth client. With the default port mapping
this is:

```
http://localhost:8000/google/callback
```

`FRONTEND_URL` (in either `backend/.env` or root `.env`) is where the
backend redirects the browser after the OAuth callback completes — it must
match wherever the frontend is actually reachable (default
`http://localhost:5173`).

## Notes

- Redis is optional infrastructure at the application level: if the `redis`
  container is ever unavailable, the backend falls back to querying
  PostgreSQL directly rather than failing requests (unchanged behavior).
- The frontend image bakes `VITE_API_URL` into the static bundle at *build*
  time (Vite inlines env vars at build time, not runtime) — changing it
  requires rebuilding the frontend image.
