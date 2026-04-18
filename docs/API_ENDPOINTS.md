# API Endpoints (Initial Contract)

## Auth and Session (Phase 6)

- `POST /auth/login`
  - Returns access token + refresh token and basic user profile.
- `POST /auth/refresh`
  - Rotates/refreshes access token.
- `POST /auth/logout`
  - Invalidates refresh token/session.
- `GET /auth/me`
  - Returns current authenticated user and role.

## UI Capability APIs (Phase 6)

- `GET /ui/sections`
  - Returns effective section visibility for current user.
  - Admin receives full access map.
  - Worker receives admin-configured section map.

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
  - Returns `duplicate` and `replayed` flags for idempotent/replay-safe inbound handling.
  - Enforces deterministic booking persistence guards: successful availability checks ensure a draft booking is linked to the active session, and explicit client confirmation cannot progress without a persisted draft.
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

### Admin User/Permission Management (Phase 6)

- `GET /admin/users/workers`
- `GET /admin/users/{user_id}/section-permissions`
- `PUT /admin/users/{user_id}/section-permissions`
  - Enables/disables worker section access (`live_chat`, `dashboard`, etc.).
  - Must emit audit event and realtime sync event.

## Worker APIs (Mobile-ready)

- `GET /worker/bookings/upcoming`
- `POST /worker/bookings/{booking_id}/approve`
- `POST /worker/bookings/{booking_id}/reject`
- `POST /worker/bookings/{booking_id}/complete-early`
- `POST /worker/availability/free-now`
- `POST /worker/availability/block`
- `POST /worker/messages`

Notes:
- Worker endpoints require authenticated user role `worker` or admin override.
- If admin disables a section, related worker endpoints must return `403`.
- Full request/response integration guide is in `docs/MOBILE_APP_API_INTEGRATION.md`.

## Media APIs

- `POST /media/twilio/ingest`
  - Returns enriched media metadata (`booking_id`, `channel`, `media_type`, `twilio_media_sid`, `is_receipt`, `source_url`).
- `GET /admin/bookings/{booking_id}/media`
- `POST /admin/media/{media_id}/mark-receipt`

## Notification APIs

- `POST /notifications/dispatch`
- `POST /notifications/reminders/run`
  - If `booking_id` provided: schedules reminders for that booking only.
  - If omitted: schedules reminders for confirmed bookings in the T-20 window and dispatches due queue.
- `POST /notifications/dispatch/run`
  - Runs outbound dispatch for all due queued/retry-pending notifications.
  - Applies retry backoff and dead-letter transitions on failure.

## Reliability/Metrics APIs

- `GET /metrics`
  - Returns counters and operational gauges:
    - `pending_reviews`
    - `queued_due_notifications`
    - `failed_tool_calls`
    - `reminder_failures`

## Realtime Sync

- `GET /events/admin/stream` (SSE or websocket equivalent)
- `GET /events/worker/stream` (SSE)

Notes:
- Stream now emits booking lifecycle and worker sync events with incremental `id` for resume via `Last-Event-ID`.
- Admin stream emits booking lifecycle, worker command, permission, and notification lifecycle events.
- Worker stream is role-guarded (`worker` only) and emits only worker-targeted permission updates.
- Both streams send a connection event (`admin_stream.connected`, `worker_stream.connected`) and keepalive comments.
