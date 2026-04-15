# Implementation Backlog (Agent-Ready)

## Backend (FastAPI)

- [ ] Initialize project structure and dependency management.
- [ ] Add environment config with pydantic settings.
- [ ] Add DB engine/session layer.
- [ ] Add Alembic migrations.
- [ ] Create all core models from `docs/DB_SCHEMA.md`.
- [ ] Implement repositories/services for clients, sessions, bookings.
- [ ] Implement slot checker with 15-minute buffer logic.
- [ ] Implement Twilio webhook routers.
- [ ] Implement LLM orchestration service and tool runner.
- [ ] Implement media ingestion service.
- [ ] Implement notifications and reminder scheduler.
- [ ] Add worker command endpoints.
- [ ] Add admin endpoints and status controls.

## Frontend (Next.js Admin)

- [ ] Setup app shell and auth placeholder.
- [ ] Booking queue and filters.
- [ ] Booking detail view with timeline.
- [ ] Media/receipt panel.
- [ ] Notification center.
- [ ] Agent pause/resume controls.
- [ ] Realtime sync subscription.

## QA and Reliability

- [ ] Unit tests for state transitions.
- [ ] Integration tests for webhook -> booking flow.
- [ ] Concurrency tests for slot conflicts.
- [ ] Reminder timing tests.
- [ ] Twilio retry/idempotency tests.
- [ ] Channel handoff tests (SMS -> WhatsApp media).
