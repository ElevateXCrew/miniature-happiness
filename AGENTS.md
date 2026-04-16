# AGENTS

## Current Repo Reality

- **Phase 1 + Phase 2 + Phase 3 Complete:** deterministic backend, Twilio SMS/WhatsApp orchestration, admin lifecycle APIs, worker sync flows, and client decision messaging are implemented.
- Conversation flow now supports cross-channel continuity by `clients.phone_e164` and persists inbound/outbound message history with tool traces.
- Current backend test status: **24 passing tests**.
- Next delivery target: **Phase 4** (media rules + incall/outcall enforcement + reminder operations hardening).

## Source-of-Truth Files (Read First)

- `IMPLEMENTAION_PLAN.md` (note spelling; this is the main phased execution plan)
- `docs/DB_SCHEMA.md` (data model and enums)
- `docs/STATE_MACHINE.md` (authoritative lifecycle/transition rules)
- `docs/TOOL_CATALOG.md` (LLM-callable deterministic backend tools)
- `docs/API_ENDPOINTS.md` (initial API contract for backend/admin/worker/mobile bridge)
- `docs/WORKFLOWS.md` (critical end-to-end behavior)
- `prompts/sms.txt` and `prompts/whatsapp.txt` (channel-specific agent behavior)
- `AI Booking Assistant_ Features and Flow.md` (original long-form requirements)

## Non-Negotiable Product Constraints

- Single worker persona is `Alysha`; assistant always speaks as Alysha.
- Two client channels: Twilio SMS and Twilio WhatsApp with separate prompt instructions.
- Replies should be short (1-2 lines) unless summary/detail is required.
- Mandatory booking field order: `datetime -> age(18+) -> ethnicity(mandatory) -> duration -> name(optional)`.
- Outcall requires address + advance payment + receipt flow.
- If client starts on SMS and media is needed, route them to WhatsApp on same number.
- Backend state machine is source of truth; LLM handles language/tool invocation only.

## Phase 1 Summary (Completed)

**Goal:** Build deterministic FastAPI foundation with PostgreSQL, normalized state machine, and all core business logic testable via API and unit tests (no LLM/Twilio integration).

**Accomplishments (16/16 tests passing, 0 lint errors):**
- ✅ Full FastAPI project with modular routers and services
- ✅ PostgreSQL async connection + Alembic async migrations (SQLite + PostgreSQL compatible)
- ✅ All 8 SQLAlchemy models: Worker, Client, ConversationSession, Booking, Message, BookingMedia, Notification, AuditEvent, InboundIdempotency
- ✅ All 14 enums (ConversationState, BookingStatus, Channel, Duration, etc.)
- ✅ 8 repositories with transaction-safe queries
- ✅ AvailabilityService: 15-minute buffer conflict detection with suggested alternatives
- ✅ BookingService: State machine with validation, field collection, transition guards, re-check logic
- ✅ MediaService: Media ingestion and receipt classification
- ✅ NotificationService: Reminder scheduling (T-20 minutes with type-specific templates)
- ✅ WorkerService: Worker command parsing and availability overrides
- ✅ ToolRunner: All 19 tools as callable async functions returning structured results
- ✅ 6 API routers: health, admin (booking approve/reject/cancel/edit, pause/resume), worker, media, notifications, events (SSE stub)
- ✅ Initial Alembic migration with all tables, indexes, constraints
- ✅ Test suite: 5 availability tests, 6 booking state machine tests, 3 idempotency tests, 2 health tests

**Key Technical Decisions:**
- Use `sa.Uuid(as_uuid=True, native_uuid=False)` for cross-dialect UUID support (PostgreSQL + SQLite)
- In-memory SQLite (`sqlite+aiosqlite:///:memory:`) for fast unit tests without live DB
- Tool layer returns `{"ok": True, ...}` or `{"ok": False, "error": "..."}` for consistent LLM orchestration
- Booking state machine enforces strict field collection order via `REQUIRED_FIELD_ORDER` with validation guards
- Slot availability re-checked at both `submit_for_review()` and final `set_status(..., CONFIRMED)` transitions
- 15-minute buffer applies to both sides of proposed slot; conflict gap can start exactly at buffer boundary

**Relevant Directories:**
- `backend/app/models/` — 8 SQLAlchemy models + 14 enums
- `backend/app/repositories/` — 8 repository classes
- `backend/app/services/` — orchestration + business services (booking, availability, media, notifications, worker, agent runtime, twilio gateway)
- `backend/app/tools/tool_runner.py` — 19 callable tools
- `backend/app/api/routers/` — core/admin/worker/media/notifications/events + twilio + agent
- `backend/alembic/versions/001_initial_schema.py` — Full initial migration
- `backend/tests/` — 24 tests covering availability, state machine, idempotency, health, phase-2 orchestration, and phase-3 lifecycle coverage

**Phase 2 Summary (Completed):**
- ✅ Twilio webhook ingestion routes for SMS and WhatsApp
- ✅ Internal `/agent/process-incoming` and `/agent/send-message` orchestration endpoints
- ✅ Channel-specific prompt loading from `prompts/sms.txt` and `prompts/whatsapp.txt`
- ✅ OpenAI orchestration runtime with deterministic fallback behavior
- ✅ Message persistence for inbound + outbound with tool trace metadata
- ✅ Cross-channel continuity via shared phone identity

**Phase 3 Summary (Completed):**
- ✅ Admin booking queue improvements (`status`, `offset`, `limit`) and richer booking detail payloads
- ✅ Booking timeline API with combined message/media/audit/notification history
- ✅ SSE admin sync event stream with resumable `Last-Event-ID` support and keepalive frames
- ✅ Worker action hardening with booking ownership checks + improved worker command handling
- ✅ Deterministic review/decision notifications plus client-facing decision messaging on active channel
- ✅ Phase 3 regression test module added (`backend/tests/test_phase3_lifecycle.py`)

**Next Phase (Phase 4):**
- Implement strict media ingestion enrichment and receipt classification behavior
- Enforce incall/outcall branch constraints (including outcall advance + receipt gating)
- Finalize reminder operations and channel/template correctness at T-20 across admin/worker/client

## Implementation Order (Do Not Skip)

- Start with Phase 1 from `IMPLEMENTAION_PLAN.md` before channel/LLM/admin work.
- Implement DB schema + state machine + deterministic tool services first.
- Add Twilio/LLM orchestration only after deterministic backend behaviors are testable.
- **Phase 1, Phase 2, and Phase 3 are complete.** Next: Proceed with Phase 4.

## AI Agent Roles for Phase 3+

Use these focused agent roles when parallelizing implementation work for upcoming phases.

1. **phase3-admin-lifecycle-agent**
   - Owns admin-side booking lifecycle behavior: queue APIs, detail/timeline payload shape, approval/rejection/cancellation/edit consistency.
   - Verifies all transitions respect `docs/STATE_MACHINE.md` and audit event creation.
   - Status: phase ownership complete; keep for regressions only.

2. **phase3-worker-sync-agent**
   - Owns worker command behavior and near real-time sync contracts (SSE/event payload shape + reliability).
   - Ensures worker actions immediately reflect in admin-facing state.
   - Status: phase ownership complete; keep for regressions only.

3. **phase3-client-notification-agent**
   - Owns deterministic client-facing status messaging after admin/worker decisions.
   - Keeps message tone aligned with Alysha persona and channel constraints.
   - Status: phase ownership complete; keep for regressions only.

4. **phase4-media-rules-agent**
   - Owns media ingestion enrichment and incall/outcall branch enforcement.
   - Implements strict outcall advance + receipt gating and WhatsApp handoff behavior.
   - Must verify media links appear correctly in booking timeline/admin detail surfaces.

5. **phase4-reminder-template-agent**
   - Owns reminder scheduling and template correctness at T-20 for admin/worker/client.
   - Verifies incall/outcall wording divergence and channel mapping.
   - Must validate reminder behavior through both API-triggered and scheduler-triggered paths.

6. **phase5-reliability-agent**
   - Owns dedup/out-of-order handling, retry/dead-letter behavior, and failure metrics.
   - Adds resilience and race-condition tests before launch readiness.

7. **qa-regression-agent**
   - Maintains end-to-end regression matrix across SMS/WhatsApp handoff, booking edit paths, and conflict scenarios.
   - Enforces CI gate: lint + type check + tests with zero regressions.

## Agent Handoff Rules

- Every agent must read: `IMPLEMENTAION_PLAN.md`, `docs/STATE_MACHINE.md`, `docs/TOOL_CATALOG.md`, and `docs/WORKFLOWS.md` before coding.
- Never bypass deterministic backend guards with prompt-only logic.
- Keep all secrets and deployment-specific values in `.env` only; no hardcoded credentials.
- Update tests alongside behavior changes and document new/changed endpoints in `docs/API_ENDPOINTS.md`.

## Data/Identity Rules

- Use internal UUID primary keys.
- Treat `clients.phone_e164` as unique canonical cross-channel identity.
- Enforce idempotency for inbound Twilio messages (by message SID).

## When Adding Real Code

- As soon as manifests/configs are added, update this file with exact run/test/lint/typecheck commands and command order.
- If executable config conflicts with docs, follow executable config and update docs.

## Commands (backend — run from `backend/` directory)

### Install dependencies
```
pip install -e ".[dev]"
pip install aiosqlite   # required for test suite (SQLite async driver)
```

### Run dev server
```
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Run migrations (requires live PostgreSQL)
```
alembic upgrade head
```

### Run tests
```
pytest
```

### Lint
```
ruff check .
```

### Type check
```
mypy app
```

### Command order for CI
1. `pip install -e ".[dev]" && pip install aiosqlite`
2. `ruff check .`
3. `mypy app`
4. `pytest`
