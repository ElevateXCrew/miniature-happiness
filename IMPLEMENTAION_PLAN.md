# IMPLEMENTAION_PLAN

This file is the single execution source of truth for project planning.

## Current Status

- Phase 1 through Phase 5 are complete on backend scope.
- Deterministic FastAPI orchestration, Twilio SMS/WhatsApp flows, booking lifecycle, media rules, reminders, reliability hardening, and metrics are implemented.
- Backend quality gate is green: `ruff check .`, `mypy app`, and `pytest` pass.
- Phase 6 Track 4 implementation is complete: admin/worker realtime SSE sync, permission refresh propagation, and Track 4 regression/UAT coverage are added.

## Scope Locks (Agreed)

- Worker model: single active worker persona (`Alysha`) for now.
- Channels: SMS and WhatsApp with separate system instructions.
- Persona: assistant always speaks as Alysha; never as "an AI assistant".
- Reply style: short, natural, 1-2 lines unless detail is explicitly required.
- Booking field order: `datetime -> age (18+) -> ethnicity (mandatory) -> duration -> name (optional)`.
- Booking decision flow:
  - Admin approve/reject: updates booking status.
  - Worker approve/reject: updates booking status and syncs admin panel instantly.
- Media behavior:
  - Media can be received and linked to client/booking.
  - If client is on SMS and media is needed, ask to send media on WhatsApp using same number.
- Reminders: 20 minutes before booking to admin, worker, and client with type-specific wording.
- Auth model: role-based with exactly two roles (`admin`, `worker`) using JWT access/refresh tokens.
- Admin can toggle worker section access (example: disable `live_chat`, worker cannot see/use it).

## Completed Phases (1-5)

### Phase 1 (Base Foundation) - Complete

Goal: deterministic backend foundation with DB schema, state machine, and tool contracts.

### Phase 2 (Channels + Agent Orchestration) - Complete

Goal: Twilio SMS/WhatsApp ingestion and LLM orchestration with deterministic fallback.

### Phase 3 (Lifecycle + Sync + Decisions) - Complete

Goal: admin/worker action APIs, timeline/sync, and client decision messaging.

### Phase 4 (Media + Booking Branch Rules) - Complete

Goal: receipt/media enrichment, outcall/incall enforcement, and reminder template hardening.

### Phase 5 (Reliability + UAT Prep) - Complete

Goal: dedup, out-of-order handling, retries/dead-letter, metrics, race-condition coverage.

## Phase 6 (Admin Panel + RBAC + Worker Portal) - Complete (Launch Hardening Active)

Goal: deliver production-grade Next.js control panel and worker portal with server-enforced role/section permissions.

This phase directly implements the admin expectations in `AI Booking Assistant_ Features and Flow.md` sections:
- Admin Review
- Admin Controls
- Pause/Resume Behavior
- Reminder Behavior
- Live visibility of ongoing conversations.

### Track 0 - Auth and RBAC foundation (must run first)

1. Add auth entities and migrations (`users`, `worker_section_permissions`).
2. Implement JWT login/refresh/logout/me endpoints.
3. Implement permission service for section-level access checks.
4. Add audit events for all permission changes.
5. Add backend guards so disabled sections return `403` even on direct API call.

Exit criteria:
- Admin and worker authentication works with JWT access + refresh.
- Worker effective sections are queryable via API.
- Disabled section requests are denied server-side.

### Track 1 - Next.js shell, role-aware routing, and guarded navigation

1. Scaffold Next.js app with authenticated layouts.
2. Build role-aware sidebar and route guards.
3. Fetch effective section permissions at login/session restore.
4. Hide worker-disabled sections from navigation and routes.

Exit criteria:
- Admin sees all sections.
- Worker only sees allowed sections.
- Disabled route navigation is blocked in UI.

### Track 2 - Admin core screens and controls

1. Dashboard with pending reviews and reliability highlights.
2. Booking queue with filters (`status`, `offset`, `limit`).
3. Booking detail + timeline (messages, media, audit, notifications).
4. Media/receipt review panel.
5. Active sessions monitor + pause/resume controls.
6. Notification center (pending review/reminder/retry/dead-letter visibility).

Exit criteria:
- Admin can run full booking lifecycle from UI.
- Receipt inspection and conversation timeline are available per booking.
- Agent pause/resume controls work from panel.

### Track 3 - Worker portal (permission-aware)

1. Worker home and upcoming bookings screen.
2. Worker actions: approve/reject, complete early, free-now availability command.
3. Worker notifications/reminders view.
4. Enforce section toggles from admin (for dashboard/live chat/etc).

Exit criteria:
- Worker can complete allowed operational actions.
- Worker cannot see or execute disabled sections/actions.

### Track 4 - Realtime sync and launch hardening

1. Integrate admin SSE stream for booking/notification/status updates.
2. Push permission-change refresh signal to worker sessions.
3. Add RBAC negative tests and end-to-end UI permission tests.
4. Extend UAT launch checklist for admin panel and auth/rbac flows.

Exit criteria:
- Worker/admin decisions sync in near real time.
- Permission changes propagate immediately.
- RBAC and panel workflows pass regression/UAT.

Status: Complete.

## Phase 6 Execution Order (Do Not Skip)

1. Implement backend auth + RBAC data model and APIs.
2. Add backend authorization guards on protected endpoints.
3. Build Next.js authenticated app shell and route/menu guards.
4. Implement admin screens and worker portal features.
5. Integrate SSE sync and notification updates.
6. Run full quality gate and UAT checklist updates.

## Immediate Next Actions

1. Run full backend + frontend quality gate before release candidate cut.
2. Execute Phase 6 realtime/RBAC UAT matrix in staging.
3. Capture product + engineering launch sign-off for panel release.
