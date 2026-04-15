# IMPLEMENTAION_PLAN

This plan is the execution blueprint for building the AI-powered booking assistant for a UK-based escort agency with a single worker (`Alysha`), dual client channels (Twilio SMS + Twilio WhatsApp), FastAPI orchestration, OpenAI LLM, PostgreSQL, and Next.js admin panel.

## Scope Locks (Agreed)

- Worker model: single active worker (`Alysha`) for now.
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

## Phase 1 (Base Foundation) - Mandatory First Phase

Goal: establish deterministic backend foundation that all later features depend on.

### Step-by-step

1. Bootstrap FastAPI project structure (`app/` with modular routers and services).
2. Configure PostgreSQL connection, migrations, and base models.
3. Implement normalized client identity with unique `phone_e164`.
4. Implement core entities: client, worker, conversation_session, booking, booking_media, notification, audit_event.
5. Implement enums/state fields for conversation and booking lifecycle.
6. Implement transaction-safe slot availability logic with 15-minute buffer.
7. Implement idempotency support for inbound message events.
8. Add internal service interfaces for deterministic tools (no LLM required yet).
9. Add health/readiness endpoints and baseline logging.

### Exit criteria

- DB migrations run cleanly.
- Deterministic booking lifecycle works via API tests without LLM.
- Double booking is blocked by backend logic.
- Session and booking state transitions are persisted and queryable.

## Phase 2 (Channels + Agent Orchestration)

Goal: connect Twilio channels to agent orchestration and tool execution.

### Step-by-step

1. Implement Twilio webhooks for SMS and WhatsApp.
2. Parse inbound payloads and normalize phone to E.164.
3. Resolve/create client profile from phone.
4. Load channel-specific system instruction text files.
5. Build LLM orchestration layer with strict tool-calling pattern.
6. Implement assistant responses constrained by style/persona rules.
7. Enforce field collection order from backend state machine.
8. Implement cross-channel continuity by phone identity.
9. Persist complete conversation history with tool call traces.

### Exit criteria

- Same client can start on SMS and continue on WhatsApp.
- "Hi" starts casual short flow; booking flow starts only on intent.
- Availability checks are tool-driven and deterministic.

## Phase 3 (Booking Lifecycle + Admin Panel + Worker Commands)

Goal: end-to-end booking approval workflow with admin and worker control surfaces.

### Step-by-step

1. Build Next.js admin authentication shell and booking queue UI.
2. Implement admin booking actions (approve/reject/cancel/edit).
3. Build worker command endpoints (mobile-app-ready API).
4. Implement event broadcasting (websocket/SSE) for admin sync updates.
5. Implement client-facing status messaging after decisions.
6. Add timeline view per booking (messages, media, status changes).
7. Add worker commands like "free now" and "complete early".

### Exit criteria

- Admin actions update booking state and client is informed.
- Worker actions sync admin panel in near real-time.
- Worker command endpoints are stable and documented for mobile app integration.

## Phase 4 (Media + Incall/Outcall Rules + Notifications)

Goal: enforce booking-type-specific logic and complete media/notification operations.

### Step-by-step

1. Implement media ingestion and storage metadata (link to client and booking or pending session).
2. Implement incall/outcall branch rules:
   - Incall: send location at allowed stage.
   - Outcall: require client address + transport advance + receipt.
3. Build notification center backend for admin.
4. Implement booking reminder scheduler at T-20 minutes.
5. Implement channel-specific reminder templates.
6. Ensure outcall reminders use "I am about to arrive" style and incall uses "Are you coming" style.

### Exit criteria

- Media appears in admin panel under correct client/booking context.
- Outcall cannot proceed to ready state without required advance flow.
- 20-minute reminders trigger correctly for all parties.

## Phase 5 (Reliability Hardening + UAT + Launch Readiness)

Goal: stabilize behavior under real-world messaging conditions and edge cases.

### Step-by-step

1. Add message deduplication and out-of-order handling.
2. Add retry queues and dead-letter handling for failed outbound sends.
3. Add comprehensive audit logs for booking state transitions and tool executions.
4. Add edge-case test matrix execution (channel switch, edits after summary, race conditions).
5. Add dashboards/metrics (pending reviews, failed tool calls, reminder failures).
6. Conduct UAT and produce go-live checklist.

### Exit criteria

- No duplicate booking creation from webhook retries.
- Slot conflicts remain blocked under concurrent requests.
- Core scenarios and edge cases pass UAT.

## Build Order Checklist (Immediate Next Actions)

1. Create backend project skeleton and migrations.
2. Implement DB schema from `docs/DB_SCHEMA.md`.
3. Implement state machine from `docs/STATE_MACHINE.md`.
4. Implement tool service contracts from `docs/TOOL_CATALOG.md`.
5. Implement API routes from `docs/API_ENDPOINTS.md`.
6. Integrate channel instructions from `prompts/*.txt`.
