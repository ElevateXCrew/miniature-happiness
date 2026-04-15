# AGENTS

## Current Repo Reality

- **Phase 1 Complete:** FastAPI backend fully implemented with PostgreSQL, all core business logic, 16 passing tests, zero lint errors.
- Backend is deterministic and testable; all state machine behaviors operational without LLM/Twilio integration.
- Ready for Phase 2: Twilio SMS/WhatsApp webhooks + OpenAI LLM orchestration.

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
- `backend/app/services/` — 5 service classes
- `backend/app/tools/tool_runner.py` — 19 callable tools
- `backend/app/api/routers/` — 6 API routers
- `backend/alembic/versions/001_initial_schema.py` — Full initial migration
- `backend/tests/` — 16 tests covering availability, state machine, idempotency, health

**Next Phase (Phase 2):**
- Implement Twilio SMS and WhatsApp webhooks
- Integrate OpenAI LLM orchestration layer
- Load channel-specific prompts (sms.txt, whatsapp.txt)
- Persist conversation history with tool call traces
- Implement cross-channel continuity (SMS → WhatsApp handoff)

## Implementation Order (Do Not Skip)

- Start with Phase 1 from `IMPLEMENTAION_PLAN.md` before channel/LLM/admin work.
- Implement DB schema + state machine + deterministic tool services first.
- Add Twilio/LLM orchestration only after deterministic backend behaviors are testable.
- **Phase 1 is complete.** Next: Proceed with Phase 2 (Twilio webhooks + LLM orchestration).

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
