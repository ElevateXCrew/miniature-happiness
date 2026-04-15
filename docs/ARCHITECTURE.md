# Architecture Overview

## Primary Stack

- Backend orchestration: FastAPI
- LLM provider: OpenAI API
- Messaging channels: Twilio SMS and Twilio WhatsApp
- Database: PostgreSQL
- Admin panel: Next.js
- Future worker app: mobile client calling worker APIs

## High-Level Components

1. Channel Ingestion Layer
   - Twilio webhooks for SMS/WhatsApp.
   - Payload normalization and idempotency checks.

2. Orchestration Layer (Agent Runtime)
   - Loads channel instruction prompt.
   - Loads Alysha persona constraints.
   - Invokes LLM with tool access.
   - Persists message and tool execution trace.

3. Deterministic Tooling Layer
   - Availability checks with 15-minute buffer.
   - Booking/session state updates.
   - Media linkage to client/booking.
   - Notification scheduling.

4. Persistence Layer
   - Relational schema for clients, sessions, bookings, media, notifications, audit.

5. Presentation/Control Layer
   - Next.js admin panel for review, monitoring, and control.
   - Worker API endpoints (mobile-ready) for command and booking actions.

## Core Design Rules

- LLM handles language, not business truth.
- Backend state machine is source of truth.
- Every tool action is validated and audited.
- Booking conflicts are checked transactionally.
- Client identity is unified by normalized phone (`phone_e164`).
