# Database Schema (PostgreSQL)

This schema is implementation-oriented and optimized for deterministic state tracking.

## Conventions

- Internal primary keys: UUID (`id`).
- External client identity key: `phone_e164` (unique).
- All timestamps in UTC.
- Soft deletes only when explicitly needed.

## Tables

### workers

- `id` (uuid, pk)
- `name` (text, not null) -> default seeded value: `Alysha`
- `is_active` (boolean, not null, default true)
- `timezone` (text, not null, default `Europe/London`)
- `created_at` (timestamptz, not null)
- `updated_at` (timestamptz, not null)

### clients

- `id` (uuid, pk)
- `phone_e164` (text, not null, unique)
- `display_name` (text, null)
- `is_blocked` (boolean, not null, default false)
- `created_at` (timestamptz, not null)
- `updated_at` (timestamptz, not null)

Indexes:
- unique index on `phone_e164`

### conversation_sessions

- `id` (uuid, pk)
- `client_id` (uuid, fk clients.id, not null)
- `worker_id` (uuid, fk workers.id, not null)
- `state` (enum, not null)
- `active_booking_id` (uuid, fk bookings.id, null)
- `last_channel` (enum: `sms`, `whatsapp`, `worker_app`, `admin_panel`)
- `last_inbound_at` (timestamptz, null)
- `created_at` (timestamptz, not null)
- `updated_at` (timestamptz, not null)

Unique guidance:
- one active session per `(client_id, worker_id)`.

### messages

- `id` (uuid, pk)
- `session_id` (uuid, fk conversation_sessions.id, not null)
- `direction` (enum: `inbound`, `outbound`, not null)
- `channel` (enum: `sms`, `whatsapp`, `worker_app`, `admin_panel`, not null)
- `sender_type` (enum: `client`, `agent`, `worker`, `admin`, `system`, not null)
- `body` (text, null)
- `twilio_message_sid` (text, unique, null)
- `raw_payload` (jsonb, null)
- `created_at` (timestamptz, not null)

### bookings

- `id` (uuid, pk)
- `client_id` (uuid, fk clients.id, not null)
- `worker_id` (uuid, fk workers.id, not null)
- `session_id` (uuid, fk conversation_sessions.id, not null)
- `status` (enum, not null)
- `booking_type` (enum: `incall`, `outcall`, null while draft)
- `scheduled_start_at` (timestamptz, null)
- `duration_minutes` (integer, null)
- `scheduled_end_at` (timestamptz, generated or maintained, null)
- `client_age` (integer, null)
- `client_ethnicity` (text, null)
- `client_name` (text, null)
- `outcall_address` (text, null)
- `incall_address_sent_at` (timestamptz, null)
- `price_total_gbp` (numeric(10,2), null)
- `advance_required_gbp` (numeric(10,2), null)
- `advance_received` (boolean, not null, default false)
- `awaiting_review_from` (enum: `admin`, `worker`, `none`, default `none`)
- `confirmed_at` (timestamptz, null)
- `cancelled_at` (timestamptz, null)
- `completed_at` (timestamptz, null)
- `created_at` (timestamptz, not null)
- `updated_at` (timestamptz, not null)

Indexes:
- `(worker_id, scheduled_start_at)`
- `(client_id, status)`

### booking_media

- `id` (uuid, pk)
- `client_id` (uuid, fk clients.id, not null)
- `booking_id` (uuid, fk bookings.id, null)
- `session_id` (uuid, fk conversation_sessions.id, not null)
- `channel` (enum: `sms`, `whatsapp`, not null)
- `media_type` (text, null)
- `twilio_media_sid` (text, null)
- `source_url` (text, not null)
- `storage_url` (text, null)
- `is_receipt` (boolean, not null, default false)
- `created_at` (timestamptz, not null)

### notifications

- `id` (uuid, pk)
- `booking_id` (uuid, fk bookings.id, null)
- `target_type` (enum: `admin`, `worker`, `client`, not null)
- `target_ref` (text, not null)
- `channel` (enum: `in_app`, `sms`, `whatsapp`, `push`, `system`, not null)
- `template_key` (text, not null)
- `payload` (jsonb, not null)
- `status` (enum: `queued`, `sent`, `failed`, not null)
- `send_at` (timestamptz, not null)
- `sent_at` (timestamptz, null)
- `created_at` (timestamptz, not null)

### audit_events

- `id` (uuid, pk)
- `entity_type` (text, not null)
- `entity_id` (uuid, not null)
- `event_type` (text, not null)
- `actor_type` (enum: `agent`, `admin`, `worker`, `system`, not null)
- `actor_ref` (text, null)
- `metadata` (jsonb, not null)
- `created_at` (timestamptz, not null)

### inbound_idempotency

- `id` (uuid, pk)
- `provider` (enum: `twilio`, not null)
- `external_id` (text, not null)
- `processed_at` (timestamptz, not null)
- `result_ref` (text, null)

Unique:
- `(provider, external_id)`

## Mandatory Enums

- `conversation_state`: `IDLE`, `COLLECTING`, `AWAITING_CLIENT_CONFIRMATION`, `WAITING_REVIEW`, `PAUSED`, `HANDOFF`, `ERROR_REVIEW`
- `booking_status`: `DRAFT`, `PENDING_REVIEW`, `CONFIRMED`, `REJECTED`, `CANCELLED`, `COMPLETED`
