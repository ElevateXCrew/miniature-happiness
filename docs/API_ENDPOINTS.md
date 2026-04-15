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

- `GET /admin/bookings`
- `GET /admin/bookings/{booking_id}`
- `POST /admin/bookings/{booking_id}/approve`
- `POST /admin/bookings/{booking_id}/reject`
- `POST /admin/bookings/{booking_id}/cancel`
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
- `GET /admin/bookings/{booking_id}/media`
- `POST /admin/media/{media_id}/mark-receipt`

## Notification APIs

- `POST /notifications/dispatch`
- `POST /notifications/reminders/run`

## Realtime Sync

- `GET /events/admin/stream` (SSE or websocket equivalent)
