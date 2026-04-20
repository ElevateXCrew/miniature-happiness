# AGENTS

## Current State

- Phases 1-6 are implemented (backend orchestration, admin panel, worker portal, RBAC, realtime).
- Post-Phase-6 stabilization is applied (dashboard fail-soft, availability recovery, role/section consistency).
- Availability flow persistence safeguard is active: successful availability checks now auto-link/create a draft booking for the active session, and explicit client confirmation is server-gated before review submission.
- Admin booking decisions now route through agent runtime with conversation continuity: admin approve/reject/cancel triggers an internal agent decision instruction, and Alysha sends the client-facing decision message in-context.
- Admin Live Chat now supports explicit conversation-history clearing per session via admin-only action, with audit logging.
- Collection anti-repeat guard is improved: runtime now pre-captures the next required field from inbound text before LLM generation to reduce duplicate re-asking.
- Collection anti-hallucination guard is active: runtime now blocks out-of-order or unsupported `update_booking_field` saves unless the value is present in the current client inbound text.
- One-on-one confirmation parsing now accepts short confirmations like `ok/okay/fine` to avoid repeated alone-policy re-asks.
- Collection tone hardening is active: booking collection starts with a soft consent line before ordered questions.
- Incall address timing rule is enforced: address is shared in final confirmation summary, not immediately after incall selection.
- Current backend verification snapshot: 43 passing tests.
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
