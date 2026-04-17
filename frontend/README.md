# Alysha Booking Admin Frontend

Next.js 16 admin/worker interface for the Alysha Booking Assistant platform.

This app provides:
- login and session bootstrap
- role-aware sidebar and route guards
- protected admin and worker sections
- API integration with backend auth + RBAC endpoints

## Prerequisites

- Node.js 20+
- Backend API running (default: `http://localhost:8000`)

## Setup

From this directory:

```bash
cd frontend
```

Install dependencies:

```bash
npm install
```

Create local env config (already added in this workspace):

```bash
# frontend/.env.local
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Run

Development server:

```bash
npm run dev
```

Open:
- `http://localhost:3000`

Production build:

```bash
npm run build
```

Production start:

```bash
npm run start
```

## Backend Dependency

The frontend calls backend APIs from `src/lib/api.ts` using:
- `NEXT_PUBLIC_API_URL` if set
- fallback: `http://localhost:8000`

Make sure backend is up and healthy:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/ready
```

## Auth and Seeded Credentials

This frontend relies on backend auth endpoints:
- `POST /auth/login`
- `POST /auth/refresh`
- `POST /auth/logout`
- `GET /auth/me`
- `GET /ui/sections`

If backend startup seeding is enabled (default), use:
- admin: `admin@alysha.local` / `admin123`
- worker: `worker@alysha.local` / `worker123`

If you seeded users with `python -m app.scripts.seed_users`, credentials may differ based on your env overrides.

## Notes

- Build verification in this workspace passes successfully.
- If you see a Next.js workspace root warning (multiple lockfiles), it is non-blocking. You can silence it later by configuring `turbopack.root` in `next.config.ts`.
