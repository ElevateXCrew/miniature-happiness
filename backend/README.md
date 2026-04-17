# Alysha Booking Backend

FastAPI backend for the Alysha Booking Assistant.

This service provides:
- Deterministic booking workflow and state machine enforcement
- Twilio SMS and WhatsApp webhook orchestration
- Admin and worker APIs
- JWT auth with role-based access control (admin, worker)
- Operational reliability features (idempotency, retries, metrics)

## Requirements

- Python 3.11+
- PostgreSQL (recommended for full backend usage)
- Optional for local quick start: SQLite (already supported)

## Project Setup

Run from this folder:

```bash
cd backend
```

Create and activate virtual environment (if needed):

```bash
python -m venv ../.venv
../.venv/Scripts/activate
```

Install dependencies:

```bash
pip install -e ".[dev]"
pip install aiosqlite
```

## Environment Configuration

Copy the example env file:

```bash
copy .env.example .env
```

Then update `.env` values as needed.

### Database URL

- SQLite quick start:
  - `DATABASE_URL=sqlite+aiosqlite:///./alysha_booking.db`
- PostgreSQL:
  - `DATABASE_URL=postgresql+asyncpg://<user>:<password>@<host>:5432/<db_name>`

If you use PostgreSQL, ensure the host resolves correctly from your machine.

## Database Migration

For PostgreSQL (and recommended for persistent environments), run:

```bash
alembic upgrade head
```

## Run the Backend

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Health endpoints:
- `GET /health` returns `{ "status": "ok" }`
- `GET /ready` verifies database connectivity

## Auth Credential Seeding

There are two seed paths in this backend.

### 1. Automatic startup seeding (app startup)

On app startup, the backend attempts to seed:
- default worker (Alysha)
- default admin user
- default worker user

These values are controlled by env settings:
- `SEED_ADMIN_EMAIL` (default: `admin@alysha.local`)
- `SEED_ADMIN_PASSWORD` (default: `admin123`)
- `SEED_WORKER_EMAIL` (default: `worker@alysha.local`)
- `SEED_WORKER_PASSWORD` (default: `worker123`)

### 2. Manual seed script

You can manually seed an admin with:

```bash
python -m app.scripts.seed_users
```

Script env overrides:
- `ADMIN_EMAIL` (default in script: `admin@alysha.local`)
- `ADMIN_PASSWORD` (default in script: `changeme123`)

Important:
- The script defaults are not the same as startup seed defaults.
- If you use both methods, use explicit env vars to keep credentials consistent.

Example manual seed with explicit credentials:

```bash
set ADMIN_EMAIL=admin@alysha.local
set ADMIN_PASSWORD=admin123
python -m app.scripts.seed_users
```

## Auth Quick Check

Login example:

```bash
curl -X POST http://127.0.0.1:8000/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"admin@alysha.local\",\"password\":\"admin123\"}"
```

Get current user example (replace token):

```bash
curl http://127.0.0.1:8000/auth/me \
  -H "Authorization: Bearer <access_token>"
```

## Quality Commands

Run from `backend/`:

```bash
ruff check .
mypy app
pytest
```

Recommended CI order:
1. `pip install -e ".[dev]" && pip install aiosqlite`
2. `ruff check .`
3. `mypy app`
4. `pytest`

## Troubleshooting

- Error: `Application startup failed`
  - Check full traceback in terminal first.
- Error: `[Errno 11001] getaddrinfo failed`
  - Your `DATABASE_URL` host cannot be resolved.
  - Verify host, DNS, and PostgreSQL connection details.
- `GET /health` is OK but `GET /ready` fails
  - API process is running, but DB is not reachable.
