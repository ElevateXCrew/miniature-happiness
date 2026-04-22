# AGENTS

## Current State

- Phases 1-6 are implemented (backend orchestration, admin panel, worker portal, RBAC, realtime).
- Post-Phase-6 stabilization is applied (dashboard fail-soft, availability recovery, role/section consistency).
- Availability flow persistence safeguard is active: successful availability checks now auto-link/create a draft booking for the active session, and explicit client confirmation is server-gated before review submission.
- Admin booking decisions now route through agent runtime with conversation continuity: admin approve/reject/cancel triggers an internal agent decision instruction, and Alysha sends the client-facing decision message in-context.
- Admin Live Chat now supports explicit conversation-history clearing per session via admin-only action, with audit logging.
- Collection anti-repeat guard is improved: runtime now pre-captures the next required field from inbound text before LLM generation to reduce duplicate re-asking.
- Collection anti-hallucination guard is active: runtime now blocks out-of-order or unsupported `update_booking_field` saves unless the value is present in the current client inbound text.
- Advisory guard tool is active: runtime now exposes `advisory_check_booking_field_update` for pre-checks while retaining hard server-side enforcement on `update_booking_field`.
- Post-decision continuity guard is active: when admin confirms/rejects/cancels and active draft linkage is cleared, runtime now replies from latest session booking status instead of falling into a "lost booking draft" re-collection loop.
- Age capture hardening is active: client age is only accepted from explicit age statements (not inferred from unrelated numbers like times).
- Context-aware plain-age reply is active: when the next required field is `client_age` and Alysha's last outbound message was an age question, a plain numeric reply like "25" is accepted by the pre-capture path without requiring cue phrases like "I am" or "years old". Out-of-order saves and plain numbers in non-age contexts remain blocked.
- One-on-one confirmation parsing now accepts short confirmations like `ok/okay/fine` to avoid repeated alone-policy re-asks.
- Collection tone hardening is active: booking collection starts with a soft consent line before ordered questions.
- Conversational collection hardening is active: runtime now lets GPT-led chat collect required booking details naturally using full session history and live booking context, without rigid server-side consent/bulk prompt intercepts.
- Cross-channel tone parity is active: SMS and WhatsApp now use the same natural booking collection flow and response style, while media sharing remains WhatsApp-only.
- Interest gate hardening is active: runtime now rejects availability checks when no active draft exists and the client's inbound message does not clearly express booking intent.
- Duration collection hardening is active: availability pre-check defaults no longer auto-fill booking duration unless the client explicitly provided duration in inbound text.
- Incall address timing rule is enforced: address is shared in final confirmation summary, not immediately after incall selection.
- Worker mobile client-relay now routes through agent runtime so client-facing text is Alysha-natural instead of raw relay text.
- Twilio inbound media is now downloaded and stored under backend `media/<client_phone>/...`, and admin panel media list prefers served local copies.
- Admin Media section is now active: it lists all saved media grouped by client phone number, and newly received media appears under the same client number on refresh.
- Image-aware inbound guard is active: when media arrives, runtime receives attachment context in inbound text so Alysha can respond naturally.
- WhatsApp media acknowledgment is now explicit: when client sends media, Alysha responds with a short receipt/photo acknowledgment in-context, and inbound media is marked receipt-true for booking/media context continuity.
- Worker mobile chat-first execution is active: `POST /worker/messages` now supports query, command, client relay, and free-form agent chat intents with structured `executed_actions` in response.
- Runtime facade split is now active: worker chat/relay paths use a worker runtime facade and worker prompt policy, while client inbound and admin decision messaging use a client runtime facade over shared core logic.
- Worker realtime stream now carries worker-targeted chat and operation updates (`worker.chat_reply`, `worker.operation.completed`) plus worker-owned booking lifecycle updates.
- Admin delete-history now clears full session artifacts: messages, linked media, linked notifications, and linked bookings (including draft/confirmed), then resets session state.
- Current backend verification snapshot: 79 passing tests.
- Active workstream: production bug triage, regression hardening, and launch governance closeout.

## Read First (Order)

1. `IMPLEMENTAION_PLAN.md`
2. `docs/STATE_MACHINE.md`
3. `docs/API_ENDPOINTS.md`
4. `docs/WORKFLOWS.md`
5. `docs/ADMIN_PANEL_SPEC.md`
6. `docs/MOBILE_APP_API_INTEGRATION.md`
7. `AI Booking Assistant_ Features and Flow.md`

## Non-Negotiables

- Assistant always represents `Alysha` and stays concise (1-2 lines unless summary required).
- Booking field order remains: `datetime -> booking_type -> duration -> outcall_address(if outcall) -> age(18+) -> ethnicity(mandatory) -> size -> alone_policy -> final confirmation`.
- Backend state machine is source of truth; do not move logic into prompts/UI.
- Client identity is canonical by `clients.phone_e164`.
- RBAC has only two roles: `admin`, `worker`.
- Admin section toggles must enforce both UI hide and backend `403`.

## Bug-Fix Priorities

1. Booking correctness and safety (state transitions, slot conflict, confirmations).
2. Auth/RBAC correctness (no unauthorized access).
3. Messaging reliability (dedup, out-of-order, retry/dead-letter, reminders).
4. Admin/worker UX resilience (fail-soft loads, realtime consistency).

## Required Verification After Changes

Backend (run in `backend/`):
- `ruff check .`
- `mypy app`
- `pytest`
- `python -m pytest tests/test_phase6_track4_realtime.py -q`

Frontend (run in `frontend/`):
- `npm run build`

## Commands

Backend setup/dev:
- `pip install -e ".[dev]"`
- `pip install aiosqlite`
- `alembic upgrade head`
- `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`

Frontend setup/dev:
- `npm install`
- `npm run dev`
- `npm run build`

Seed admin user:
- `cd backend && python -m app.scripts.seed_users`

## Documentation Hygiene Rule

If behavior changes, update in same patch:
- `AGENTS.md`
- `IMPLEMENTAION_PLAN.md`
- `docs/API_ENDPOINTS.md`
- `docs/WORKFLOWS.md`
- `AI Booking Assistant_ Features and Flow.md`
