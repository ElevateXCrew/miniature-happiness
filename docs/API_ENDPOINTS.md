# API Endpoints (Initial Contract)

## Health

- `GET /health`
- `GET /ready`

## Twilio Webhooks

- `POST /webhooks/twilio/sms`
- `POST /webhooks/twilio/whatsapp`

Notes:
- Verify Twilio signatures.
- Deduplicate by Twilio message SID.

## Agent Orchestration

- `POST /agent/process-incoming`
  - Internal endpoint for normalized inbound events.
- `POST /agent/send-message`
  - Internal endpoint for deterministic outbound dispatch.

## Admin Panel APIs

- `GET /admin/bookings` (supports `status`, `offset`, `limit` query params)
- `GET /admin/bookings/{booking_id}`
  - Includes `media_count` and `has_receipt` flags in booking detail payload.
- `GET /admin/bookings/{booking_id}/timeline`
- `POST /admin/bookings/{booking_id}/approve`
- `POST /admin/bookings/{booking_id}/reject`
- `POST /admin/bookings/{booking_id}/cancel`
- `POST /admin/bookings/{booking_id}/incall-address-sent`
  - Marks `incall_address_sent_at` after a confirmed incall booking.
- `PATCH /admin/bookings/{booking_id}`
- `GET /admin/sessions/active`
- `GET /admin/notifications`
- `POST /admin/agent/pause`
- `POST /admin/agent/resume`

## Worker APIs (Mobile-ready)

- `GET /worker/bookings/upcoming`
- `POST /worker/bookings/{booking_id}/approve`
- `POST /worker/bookings/{booking_id}/reject`
- `POST /worker/bookings/{booking_id}/complete-early`
- `POST /worker/availability/free-now`
- `POST /worker/availability/block`
- `POST /worker/messages`

## Media APIs

- `POST /media/twilio/ingest`
  - Returns enriched media metadata (`booking_id`, `channel`, `media_type`, `twilio_media_sid`, `is_receipt`, `source_url`).
- `GET /admin/bookings/{booking_id}/media`
- `POST /admin/media/{media_id}/mark-receipt`

## Notification APIs

- `POST /notifications/dispatch`
- `POST /notifications/reminders/run`
  - If `booking_id` provided: schedules reminders for that booking only.
  - If omitted: schedules reminders for confirmed bookings in the T-20 window and returns counts.

## Realtime Sync

- `GET /events/admin/stream` (SSE or websocket equivalent)

Notes:
- Stream now emits booking lifecycle and worker sync events with incremental `id` for resume via `Last-Event-ID`.
