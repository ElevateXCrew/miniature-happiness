# AGENTS

## Current Repo Reality

- **Phase 1 + Phase 2 + Phase 3 + Phase 4 + Phase 5 Complete:** deterministic backend, Twilio SMS/WhatsApp orchestration, admin lifecycle APIs, worker sync flows, client decision messaging, media enrichment, branch constraints, reminder hardening, and reliability controls are implemented.
- Conversation flow supports cross-channel continuity by `clients.phone_e164` and persists inbound/outbound message history with tool traces.
- Current backend test status: **40 passing tests**.
- Phase 5 reliability hardening is implemented (dedup/out-of-order handling, retry/dead-letter, metrics, resilience tests).
- **Phase 6 Track 0 complete:** backend JWT auth + RBAC schema/APIs and backend authorization guards are implemented.
- **Phase 6 Track 1 complete:** Next.js 14 frontend shell, auth flow, role-aware sidebar, and route guards are implemented at `frontend/`.
- **Phase 6 Track 2 complete:** Admin core screens implemented — dashboard (KPIs + recent activity), booking queue (filterable + paginated + inline actions), booking detail + timeline, media gallery + receipt marking, active sessions + pause/resume, notification center, and worker section access settings.
- **Phase 6 Track 3 complete:** Worker portal implemented — upcoming bookings with approve/reject/complete-early, Free Now availability command, Send Message to active chat, permission-gated views per admin section toggles.
- **Phase 6 Track 4 complete:** Realtime SSE sync integrated for admin and worker sessions, permission refresh propagation implemented, and Track 4 RBAC realtime regression + UAT checklist updates landed.
- **Current active workstream:** Phase 6 launch hardening and staged UAT sign-off.

## Source-of-Truth Files (Read First)

- `IMPLEMENTAION_PLAN.md` (note spelling; this is the main phased execution plan)
- `docs/DB_SCHEMA.md` (data model and enums)
- `docs/STATE_MACHINE.md` (authoritative lifecycle/transition rules)
- `docs/TOOL_CATALOG.md` (LLM-callable deterministic backend tools)
- `docs/API_ENDPOINTS.md` (initial API contract for backend/admin/worker/mobile bridge)
- `docs/WORKFLOWS.md` (critical end-to-end behavior)
- `docs/ADMIN_PANEL_SPEC.md` (screen-by-screen contract for Next.js admin/worker interfaces)
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
- Auth must be role-based with only two roles: `admin`, `worker`.
- Admin can toggle worker section access (for example `live_chat`); disabled sections must be blocked in both UI and backend APIs.

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
- `backend/app/api/routers/` — core/admin/worker/media/notifications/events + twilio + agent + metrics
- `backend/alembic/versions/001_initial_schema.py` — Full initial migration
- `backend/alembic/versions/002_phase5_reliability.py` — Phase 5 retry/dead-letter schema upgrade
- `backend/tests/` — 34 tests covering availability, state machine, idempotency, orchestration, lifecycle, and phase-5 reliability hardening

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

**Phase 4 Summary (Completed):**
- ✅ Media ingestion enrichment now links assets to active booking context and captures stronger media metadata
- ✅ Receipt classification flow implemented with deterministic booking linkage and admin/timeline visibility
- ✅ Outcall branch enforcement added: requires outcall address + positive advance amount before review
- ✅ Outcall confirmation hard-gated on `advance_received` plus receipt evidence
- ✅ Incall location lifecycle support added (`incall_address_sent_at`) via admin endpoint
- ✅ Reminder operations hardened with T-20 scheduler path, duplicate protection, and incall/outcall style hints
- ✅ API docs updated and regression coverage expanded to 29 passing backend tests

**Phase 5 Summary (Completed):**
- ✅ Inbound idempotency strengthened with DB-safe dedup handling and duplicate response replay support
- ✅ Out-of-order inbound event handling added to ignore stale events without regressing session flow
- ✅ Outbound retry queue flow added via notifications with exponential backoff and dead-letter status
- ✅ Failure telemetry expanded with counters for Twilio sends, tool calls, retries, dead letters, and transitions
- ✅ Metrics endpoint added (`GET /metrics`) exposing pending reviews, queued due notifications, failed tools, reminder failures
- ✅ Reminder scheduler now dispatches due notifications and reports delivery outcomes
- ✅ New migration (`002_phase5_reliability`) adds retry/dead-letter status support and retry metadata fields
- ✅ Reliability and race-condition test coverage added (`backend/tests/test_phase5_reliability.py`)
- ✅ UAT + launch checklist artifact added (`docs/PHASE5_UAT_LAUNCH_CHECKLIST.md`)

**Phase 6 Track 0 Summary (Completed):**
- ✅ Added auth/RBAC data model with `users` and `worker_section_permissions`.
- ✅ Added migration `003_phase6_auth_rbac` with `user_role` and `section_key` enums.
- ✅ Implemented JWT auth endpoints: `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me`.
- ✅ Implemented effective section API: `GET /ui/sections`.
- ✅ Added admin worker-permission APIs: `GET /admin/users/workers`, `GET /admin/users/{user_id}/section-permissions`, `PUT /admin/users/{user_id}/section-permissions`.
- ✅ Enforced backend guards for role + section checks (`403` on disabled worker sections).
- ✅ Added audit + realtime permission update emission on section toggles.
- ✅ Added Phase 6 regression coverage (`backend/tests/test_phase6_auth_rbac.py`) and kept quality gate green (`ruff`, `mypy`, `pytest`).

**Phase 6 Track 1 Summary (Completed):**
- ✅ Scaffolded Next.js 14 App Router frontend at `frontend/` (TypeScript, Vanilla CSS, no Tailwind).
- ✅ Premium dark design system: CSS custom properties, Inter font, violet accent palette, animations.
- ✅ `AuthContext` with login, logout, and session bootstrap via refresh token + `/auth/me` + `/ui/sections`.
- ✅ `AuthGuard` component: redirects unauthenticated users to `/login`; blocks disabled sections for workers.
- ✅ `apiFetch` client with Bearer token injection, automatic 401 → refresh → retry flow, and `ApiResponseError`.
- ✅ Role-aware `Sidebar`: admin sees all 8 sections; workers see only admin-enabled sections.
- ✅ `TopBar` with logout, `AppShell` layout with animated page transitions.
- ✅ Fully functional login page with glassmorphism card, animated ambient blobs, loading state, and error display.
- ✅ Protected route group (`(protected)/`) with `AuthGuard` + `AppShell` layout.
- ✅ Styled stub pages for all 8 sections: dashboard, bookings, sessions, media, notifications, schedule, settings, worker.
- ✅ `backend/app/scripts/seed_users.py` — seeds initial admin user for dev login testing.
- ✅ Build verified: `npm run build` passes with 0 TypeScript errors, 13 routes generated.

**Relevant Frontend Directories:**
- `frontend/src/app/` — Next.js App Router pages and layouts
- `frontend/src/components/auth/` — `LoginForm`, `AuthGuard`
- `frontend/src/components/layout/` — `Sidebar`, `TopBar`, `AppShell`
- `frontend/src/components/ui/` — `Button`, `Card`, `Badge`, `Spinner`, `SectionPlaceholder`
- `frontend/src/context/AuthContext.tsx` — global auth state
- `frontend/src/lib/api.ts` — fetch API client
- `frontend/src/types/index.ts` — shared TypeScript types
- `backend/app/scripts/seed_users.py` — dev admin seed script

**Phase 6 Track 2 Summary (Completed):**
- ✅ Dashboard page: live KPI cards (pending reviews, queued notifications, reminder failures, failed tools) + recent bookings table + recent notifications list.
- ✅ Booking queue page: status filter dropdown, paginated table (20/page), inline approve/reject/cancel actions per row, click-through to detail.
- ✅ Booking detail + timeline page: sticky detail panel with all booking fields, approve/reject/cancel header actions, mark incall address sent, tabbed timeline (messages/audit/notifications/media) and media gallery with mark-receipt.
- ✅ Active sessions page: session list with state badges, channel, active booking link; agent-wide pause/resume controls.
- ✅ Notification center page: full queue table with status badges, manual run-dispatch and run-reminders triggers.
- ✅ Settings page: worker list with per-section toggle grid; toggles save immediately to backend and reflect real-time.
- ✅ `src/lib/adminApi.ts` — typed wrapper for all Track 2 backend API calls.
- ✅ Build verified: `npm run build` passes with 0 TypeScript errors, 13 routes (including dynamic `/bookings/[id]`).

**Relevant Track 2 Frontend Directories:**
- `frontend/src/app/(protected)/dashboard/` — KPI dashboard
- `frontend/src/app/(protected)/bookings/` — booking queue + `[id]/` detail page
- `frontend/src/app/(protected)/sessions/` — live chat monitor
- `frontend/src/app/(protected)/notifications/` — notification center
- `frontend/src/app/(protected)/settings/` — worker access management
- `frontend/src/components/dashboard/` — KpiCard component
- `frontend/src/lib/adminApi.ts` — typed API helpers

**Phase 6 Track 3 Summary (Completed):**
- ✅ Worker portal page (`/worker`): upcoming bookings list with booking time, relative countdown, type/duration/name chips, approve/reject/complete-early action buttons, and link to admin booking detail.
- ✅ Worker Quick Commands sidebar: “Free Now” availability signal (gated on `schedule` section) and Send Message command (gated on `live_chat` section).
- ✅ Schedule page (`/schedule`): dedicated availability management with Free Now card, section-gated for workers.
- ✅ All worker actions call `/worker/` endpoints; worker_id is always sourced from `user.worker_id` in `AuthContext`.
- ✅ Section guards: components show “disabled” state instead of actions when admin has revoked access; no backend bypass possible.
- ✅ `src/lib/adminApi.ts` extended with `workerPortalApi` — upcomingBookings, approve, reject, completeEarly, freeNow, sendMessage.
- ✅ `src/types/index.ts` extended with `WorkerUpcomingBooking` and `WorkerCommandResult`.
- ✅ Build verified: `npm run build` passes with 0 TypeScript errors, 13 routes.

**Relevant Track 3 Frontend Files:**
- `frontend/src/app/(protected)/worker/page.tsx` — worker home portal
- `frontend/src/app/(protected)/schedule/page.tsx` — availability management
- `frontend/src/lib/adminApi.ts` — `workerPortalApi` added

**Phase 6 Track 4 Summary (Completed):**
- ✅ Admin realtime sync integrated via authenticated SSE stream consumption and UI auto-refresh wiring for dashboard/bookings/sessions/notifications/settings.
- ✅ Worker realtime stream endpoint added (`GET /events/worker/stream`) with worker-only RBAC and worker-target filtering.
- ✅ Permission updates now propagate to active worker sessions, triggering immediate `/ui/sections` refresh without re-login.
- ✅ Notification lifecycle events (`notification.created`, `notification.status_changed`) now publish to realtime stream for queue/KPI freshness.
- ✅ Track 4 regression tests added (`backend/tests/test_phase6_track4_realtime.py`) covering stream RBAC guards and worker event-target filtering logic.
- ✅ Track 4 UAT + launch checklist addendum added to `docs/PHASE5_UAT_LAUNCH_CHECKLIST.md`.

## Implementation Order (Do Not Skip)

- Start with Phase 1 from `IMPLEMENTAION_PLAN.md` before channel/LLM/admin work.
- Implement DB schema + state machine + deterministic tool services first.
- Add Twilio/LLM orchestration only after deterministic backend behaviors are testable.
- **Phase 1 through Phase 5 are complete.** Phase 6 sequence status:
  1. ✅ Backend JWT auth + RBAC schema/API.
  2. ✅ Backend authorization guards (`403` on disabled sections).
  3. ✅ Next.js auth shell and role-aware route/menu guards (Track 1).
  4. ✅ Admin core screens — dashboard, bookings, sessions, notifications, settings (Track 2).
  5. ✅ Worker portal — upcoming bookings, worker actions, permission-gated views (Track 3).
   6. ✅ Realtime SSE sync + RBAC regression/UAT and launch checks (Track 4).

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
   - Status: phase ownership complete; keep for regressions only.

5. **phase4-reminder-template-agent**
   - Owns reminder scheduling and template correctness at T-20 for admin/worker/client.
   - Verifies incall/outcall wording divergence and channel mapping.
   - Must validate reminder behavior through both API-triggered and scheduler-triggered paths.
   - Status: phase ownership complete; keep for regressions only.

6. **phase5-reliability-agent**
   - Owns dedup/out-of-order handling, retry/dead-letter behavior, and failure metrics.
   - Adds resilience and race-condition tests before launch readiness.

7. **qa-regression-agent**
   - Maintains end-to-end regression matrix across SMS/WhatsApp handoff, booking edit paths, and conflict scenarios.
   - Enforces CI gate: lint + type check + tests with zero regressions.

## Agent Handoff Rules

- Every agent must read: `IMPLEMENTAION_PLAN.md`, `docs/STATE_MACHINE.md`, `docs/TOOL_CATALOG.md`, and `docs/WORKFLOWS.md` before coding.
- For Phase 6 work, also read `docs/ADMIN_PANEL_SPEC.md` and `docs/API_ENDPOINTS.md` before coding.
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

## Commands (frontend — run from `frontend/` directory)

### Install dependencies
```
npm install
```

### Run dev server
```
npm run dev
# → http://localhost:3000
```

### Build (type-check + compile)
```
npm run build
```

### Seed first admin user (requires live backend + DB)
```
cd backend && python -m app.scripts.seed_users
# Default: admin@alysha.local / changeme123
# Override: ADMIN_EMAIL=... ADMIN_PASSWORD=... python -m app.scripts.seed_users
```

### Frontend env
- `frontend/.env.local` — set `NEXT_PUBLIC_API_URL` (default: `http://localhost:8000`)

## Phase 6 Immediate Commands

### Backend (run from `backend/`)
1. `ruff check .`
2. `mypy app`
3. `pytest`
4. `python -m pytest tests/test_phase6_track4_realtime.py -q` (focused Track 4 realtime regression)

### Frontend (run from `frontend/`)
1. `npm run build` — verify TypeScript + compilation
2. `npm run dev` — start dev server

Phase 6 expectations:
- Backend quality gate (lint + types + tests) stays green throughout.
- Frontend `npm run build` must pass with 0 TypeScript errors before any PR merge.
- New admin screens (Track 2) must consume backend APIs via `src/lib/api.ts` only; no direct fetch calls in page components.
