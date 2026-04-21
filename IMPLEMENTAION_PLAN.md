# IMPLEMENTAION_PLAN

This file is the single execution source of truth for project planning.

## Current Status

- Phase 1 through Phase 5 are complete on backend scope.
- Deterministic FastAPI orchestration, Twilio SMS/WhatsApp flows, booking lifecycle, media rules, reminders, reliability hardening, and metrics are implemented.
- Backend quality gate is green: `ruff check .`, `mypy app`, and `pytest` pass.
- Phase 6 Track 4 implementation is complete: admin/worker realtime SSE sync, permission refresh propagation, and Track 4 regression/UAT coverage are added.
- Phase 6 launch hardening release-candidate gate has been executed and is green (backend lint/types/tests, focused realtime regression, frontend build).
- Twilio webhook regression tests are aligned with current deterministic contract (empty TwiML response + orchestrator-managed outbound sends).
- Phase 6 stabilization pass is complete: dashboard fail-soft behavior, availability error recovery, role/section consistency checks, and targeted regression coverage were executed.
- Post-stabilization booking integrity guard is active: availability success now ensures a persisted draft booking is linked to session context before confirmation/review transitions.
- Worker mobile chat-first path is active: `/worker/messages` is the primary worker interaction endpoint with deterministic intent handling, Alysha-style free-form chat replies, and `executed_actions` response traces.
- Worker realtime visibility now includes worker-targeted chat/operation events and worker-owned booking status updates.
- Runtime path separation is active via facades: worker mobile chat/relay uses worker runtime policy, while client inbound/admin decision messaging uses client runtime policy over shared deterministic core services.
- Availability intent gating is active: runtime blocks availability checks from starting collection when no active draft exists and inbound text does not clearly indicate booking intent.
- Duration persistence guard is active: default availability check duration is not persisted into draft booking unless duration was explicitly stated by client inbound text.
- Advisory booking guard tool is active: runtime exposes a pre-check tool for field updates, while hard server-side enforcement remains mandatory on actual field mutation.
- Post-decision continuity guard is active: after admin booking decisions clear active draft linkage, runtime uses latest session booking status replies to avoid false "lost draft" prompts and collection restarts.
- Two-step collection guard is active: once availability has captured date/time, runtime enforces booking consent prompt, then one bulk message for remaining required fields, then one-by-one prompts only for any missing required fields.

## Scope Locks (Agreed)

- Worker model: single active worker persona (`Alysha`) for now.
- Channels: SMS and WhatsApp with separate system instructions.
- Persona: assistant always speaks as Alysha; never as "an AI assistant".
- Reply style: short, natural, 1-2 lines unless detail is explicitly required.
- Booking field order: `datetime -> booking_type -> duration -> outcall_address(if outcall) -> age(18+) -> ethnicity(mandatory) -> size -> alone_policy -> final confirmation`.
- Booking decision flow:
  - Admin approve/reject: updates booking status and routes a decision instruction through agent runtime so Alysha sends the client update in continuity with prior conversation.
  - Worker approve/reject: updates booking status and syncs admin panel instantly.
- Worker mobile interaction:
  - Primary path is chat-first (`POST /worker/messages` + worker SSE stream).
  - Optional direct action routes remain supported for compatibility (`/worker/bookings/*`, `/worker/availability/*`).
- Runtime isolation:
  - Worker routes must use worker runtime facade methods only.
  - Client/Twilio ingress and admin decision messaging must use client runtime facade methods only.
- Admin live chat moderation:
  - Admin can clear prior conversation history for a specific session from the Live Chat panel.
  - Clear-history action is admin-only and audit-logged.
  - Clear-history now removes full session artifacts (messages, media, linked notifications, and linked bookings including draft/confirmed) and resets the session to idle/no active booking.
- Conversation collection reliability:
  - Runtime pre-captures the next required booking field from inbound text before LLM generation to reduce repeated question loops.
  - Runtime blocks hallucinated/out-of-order booking field updates unless the value is supported by the current inbound text.
  - Runtime enforces booking-intent gating before availability tool usage can initialize collection on a new thread.
  - Runtime preserves mandatory duration questioning by not persisting default pre-check duration unless client text explicitly includes duration.
  - Age capture only accepts explicit age statements and rejects inferred numeric values from unrelated text.
  - One-on-one confirmations accept short replies like `ok/okay/fine` to avoid repeated prompts.
  - Incall address is sent at final confirmation stage (not immediately after booking type selection).
  - Runtime enforces a strict two-step booking intake after availability: consent question first, then one bulk request for remaining required details before one-by-one missing-field recovery.
- Worker mobile chat relay:
  - Worker `POST /worker/messages` relay intent now generates client-facing text through agent runtime, not raw passthrough text.
- Media behavior:
  - Media can be received and linked to client/booking.
  - Twilio media is fetched and stored locally per client phone folder (`media/<client_phone>/...`) with metadata persisted in `booking_media.storage_url`.
  - Admin media listing serves local stored copies via backend endpoint when available.
  - Admin media page groups all saved media by client phone and shows new inbound media under the same phone grouping.
  - WhatsApp inbound media triggers an explicit Alysha acknowledgment message (photo/screenshot received) in the same turn.
  - Inbound media is marked receipt-true at ingest so booking context immediately reflects payment receipt received.
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

1. Keep the quality gate green on every bug-fix patch (`ruff`, `mypy`, `pytest`, focused realtime regression, frontend `npm run build`).
2. Prioritize defects by production impact: booking lifecycle correctness > auth/RBAC access leaks > dashboard/realtime UX.
3. Keep docs synced for each bug-fix release (`AGENTS.md`, `docs/API_ENDPOINTS.md`, `docs/WORKFLOWS.md`, and `AI Booking Assistant_ Features and Flow.md` when behavior changes).
4. Maintain rollout governance artifacts (approvals, rollback owner, alert thresholds, and release evidence).
