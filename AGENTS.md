# AGENTS

## Current Repo Reality

- This repository is currently planning/spec-only (no FastAPI/Next.js code, no lockfiles, no CI, no build/test configs yet).
- Do not guess commands like `npm test` or `pytest` until manifests/configs are added.

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

## Implementation Order (Do Not Skip)

- Start with Phase 1 from `IMPLEMENTAION_PLAN.md` before channel/LLM/admin work.
- Implement DB schema + state machine + deterministic tool services first.
- Add Twilio/LLM orchestration only after deterministic backend behaviors are testable.

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
