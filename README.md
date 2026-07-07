# Alysha Booking Assistant

AI-powered booking management system for independent companion services. Clients book via SMS or WhatsApp through natural conversation with **Alysha** — an LLM-driven assistant — while admins and workers manage operations through a realtime web panel.

## System Architecture

```
                    ┌─────────────────────────────┐
                    │   Next.js Admin/Worker UI   │
                    │  (role-aware, SSE realtime) │
                    └──────────┬──────────────────┘
                               │ HTTP / SSE
┌──────────┐    Twilio     ┌───▼──────────────────┐
│  Client  │◄───Webhooks──►│   FastAPI Backend    │
│ SMS/WA   │               │                      │
│          │◄──Twilio───►  │  Agent Runtime +     │
│          │   Gateway     │  19 Deterministic    │
│          │               │  Tools (OpenAI GPT)  │
└──────────┘               │                      │
                           │  Booking State Mach. │
                           │  RBAC Auth + SSE     │
                           │  Notification Engine │
                           └──────────┬───────────┘
                                      │
                           ┌──────────▼───────────┐
                           │  PostgreSQL / SQLite  │
                           │  (11 tables, Alembic) │
                           └──────────────────────┘
```

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11, FastAPI 0.136, SQLAlchemy 2.0 async |
| AI | OpenAI GPT-4o-mini (tool-calling), deterministic fallback |
| Messaging | Twilio SMS + WhatsApp (dual-channel persona) |
| Database | PostgreSQL (prod), SQLite (dev) via Alembic migrations |
| Frontend | Next.js 16, React 19, TypeScript 5, CSS Modules |
| Auth | Custom JWT (PBKDF2 + HMAC-SHA256), two-role RBAC |
| Realtime | Server-Sent Events (SSE) with auto-reconnect |
| Quality | Ruff, mypy, pytest (103 tests), GitHub Actions CI |

## Project Structure

```
├── backend/               # FastAPI application
│   ├── app/
│   │   ├── api/routers/   # 11 endpoint modules (auth, admin, worker, twilio, etc.)
│   │   ├── core/          # Config, logging, metrics
│   │   ├── db/            # SQLAlchemy engine, base
│   │   ├── models/        # 11 ORM models
│   │   ├── services/      # Business logic (agent runtime, booking, auth, etc.)
│   │   ├── tools/         # 19 LLM-callable deterministic tools
│   │   └── scripts/       # Utility scripts
│   ├── alembic/           # 4 migration versions
│   └── tests/             # 10 test suites
├── frontend/              # Next.js web panel
│   └── src/
│       ├── app/           # Pages (dashboard, bookings, sessions, media, etc.)
│       ├── components/    # UI component library
│       ├── context/       # Auth + SSE context providers
│       ├── hooks/         # Realtime refresh hooks
│       └── lib/           # API client, admin API wrappers
├── prompts/               # LLM system instructions
│   ├── alysha_context.md  # Alysha identity, rates, policies
│   ├── whatsapp.txt       # WhatsApp channel persona (emoji/flirty)
│   ├── sms.txt            # SMS channel persona (plain/text)
│   └── worker.txt         # Worker internal chat persona
└── docs/                  # Comprehensive documentation (12 files)
```

## Key Features

- **Dual-Channel Booking**: Clients book via SMS or WhatsApp; Alysha conducts natural conversation with channel-appropriate tone
- **Deterministic State Machine**: Backend enforces booking lifecycle (Draft → Pending Review → Confirmed/Rejected/Cancelled/Completed) — LLM handles language, backend owns truth
- **19 LLM Tools**: ToolRunner provides get/set booking fields, availability checks, slot reservation, review submission, media attachment, notification scheduling, and worker commands
- **Admin Panel**: Dashboard KPIs, booking queue with filters, booking detail + timeline, media/receipt review, live session monitor, notification center, agent pause/resume
- **Worker Portal**: Chat-first mobile interface, booking approval workflow, availability commands (free-now/block), client relay with Alysha-natural text
- **RBAC**: Two roles (admin/worker), per-section permission toggles enforced server-side (403) and in UI (hidden routes)
- **Realtime SSE**: Admin and worker event streams for live booking, notification, and permission-update sync
- **Reliability**: Idempotency, out-of-order message detection, retry with exponential backoff, dead-letter queue, booking field guardrails (hallucination blocking, age/ethnicity enforcement, confirmation routing)
- **Media Handling**: WhatsApp media download, local storage by client phone, receipt classification, admin media panel with grouping

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 20+
- PostgreSQL (recommended) or SQLite (dev)

### Backend

```bash
cd backend
pip install -e ".[dev]"
pip install aiosqlite
cp .env.example .env   # configure DATABASE_URL, OPENAI_API_KEY, TWILIO_* etc.
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local  # NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev
```

Open `http://localhost:3000` and log in with default credentials:

| Role | Email | Password |
|---|---|---|
| Admin | `admin@alysha.local` | `admin123` |
| Worker | `worker@alysha.local` | `worker123` |

### Twilio Webhook Configuration

Point your Twilio SMS and WhatsApp webhooks to:

```
https://your-domain.com/webhooks/twilio/sms
https://your-domain.com/webhooks/twilio/whatsapp
```

## Development

### Quality Gates

```bash
# Backend (from backend/)
ruff check .
mypy app
pytest
python -m pytest tests/test_phase6_track4_realtime.py -q

# Frontend (from frontend/)
npm run build
```

### Documentation

All behavior changes must update:
- `AGENTS.md`
- `IMPLEMENTAION_PLAN.md`
- `docs/API_ENDPOINTS.md`
- `docs/WORKFLOWS.md`
- `AI Booking Assistant_ Features and Flow.md`

## Documentation Index

| File | Contents |
|---|---|
| `docs/ARCHITECTURE.md` | Stack overview, component boundaries, design rules |
| `docs/API_ENDPOINTS.md` | Full endpoint contracts with request/response examples |
| `docs/DB_SCHEMA.md` | Table definitions, indexes, enums |
| `docs/STATE_MACHINE.md` | Conversation/booking states, transitions, guards |
| `docs/WORKFLOWS.md` | 11 critical workflows (booking, outcall, reminders, etc.) |
| `docs/TOOL_CATALOG.md` | 20 deterministic tool descriptions |
| `docs/ADMIN_PANEL_SPEC.md` | 9 screen modules, acceptance criteria |
| `docs/MOBILE_APP_API_INTEGRATION.md` | Worker mobile app integration contract |
| `docs/KNOWLEDGE_GRAPH.md` | Bug triage map, symptom-to-file mapping |
| `IMPLEMENTAION_PLAN.md` | Phase execution plan, scope locks, current status |

## License

Proprietary — all rights reserved.
