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
  - Enforces booking-intent gate before availability checks can start collection when no active draft exists.
  - Preserves duration collection order by not persisting default availability pre-check duration unless inbound client text explicitly includes duration.
  - Applies deterministic pre-capture for the next required booking field from inbound text before LLM generation to reduce repeated follow-up questions.
  - Applies anti-hallucination guards for booking collection: tool updates are rejected when a field is out-of-order or value is not supported by current inbound client text.
  - Exposes advisory pre-check tool `advisory_check_booking_field_update` for model planning, while keeping hard enforcement on `update_booking_field` before any persistence.
  - Applies post-decision continuity guard: if active draft linkage is cleared by admin decision transitions, runtime responds from latest session booking status rather than re-entering draft collection with a "lost draft" prompt.
  - Age extraction accepts only explicit age statements (for example "I am 24" / "24 years old") to avoid inferred values from unrelated numbers.
  - One-on-one confirmation parser accepts short positive replies (`ok`, `okay`, `fine`) to prevent repeated re-asking.
  - Incall address is shared at final confirmation summary stage, not immediately after incall selection.
  - When inbound media is present, attachment context is injected into runtime inbound text so Alysha can respond naturally to image-only messages.
  - On WhatsApp inbound media, runtime sends an explicit client-facing media acknowledgment in Alysha voice and marks the attachment as receipt-received in booking context.
- `POST /agent/send-message`
  - Internal endpoint for deterministic outbound dispatch.

## Admin Panel APIs

- `GET /admin/bookings` (supports `status`, `offset`, `limit` query params)
- `GET /admin/bookings/{booking_id}`
  - Includes `media_count` and `has_receipt` flags in booking detail payload.
- `GET /admin/bookings/{booking_id}/timeline`
- `GET /admin/media`
  - Returns all saved media entries with client phone metadata for admin media gallery grouping.
- `POST /admin/bookings/{booking_id}/approve`
- `POST /admin/bookings/{booking_id}/reject`
- `POST /admin/bookings/{booking_id}/cancel`
  - Decision message dispatch is agent-mediated: backend sends an internal admin action instruction to runtime, and Alysha sends the client-facing 1-2 line update in prior conversation context.
- `POST /admin/bookings/{booking_id}/incall-address-sent`
  - Marks `incall_address_sent_at` after a confirmed incall booking.
- `PATCH /admin/bookings/{booking_id}`
- `GET /admin/sessions/active`
- `DELETE /admin/sessions/{session_id}/messages`
  - Clears stored conversation messages for that session from admin live chat.
  - Also removes session-linked `bookings` (draft/pending/confirmed/etc.), linked `booking_media`, and linked `notifications`, then resets session state to `idle` and `active_booking_id=null`.
  - Admin-only action with audit event `messages.cleared`.
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

- Primary mobile path:
  - `POST /worker/messages`
    - Relay intent is agent-mediated: worker instruction is rewritten by worker runtime into natural Alysha client-facing text before Twilio send.
    - Free-form worker chat is routed through worker runtime policy (separate from client intake runtime), so short greetings/general chat return Alysha-style worker-assistant replies.
  - `GET /events/worker/stream`
- Optional direct action routes (kept for compatibility):
  - `GET /worker/bookings/upcoming`
  - `POST /worker/bookings/{booking_id}/approve`
  - `POST /worker/bookings/{booking_id}/reject`
  - `POST /worker/bookings/{booking_id}/complete-early`
  - `POST /worker/availability/free-now`
  - `POST /worker/availability/block`

Notes:
- Worker endpoints require authenticated user role `worker` or admin override.
- If admin disables a section, related worker endpoints must return `403`.
- `POST /worker/messages` keeps `worker_id` in request for compatibility, and backend enforces JWT worker identity match.
- Worker chat runtime path is isolated from Twilio/client intake runtime path.
- Full request/response integration guide is in `docs/MOBILE_APP_API_INTEGRATION.md`.

Example chat request (query intent):
```json
{
  "worker_id": "<worker_uuid>",
  "message_text": "What is my next booking time?"
}
```

Example chat response:
```json
{
  "success": true,
  "assistant_reply": "Your next booking is at 2026-04-18T20:00:00+00:00.",
  "message": "Your next booking is at 2026-04-18T20:00:00+00:00.",
  "executed_actions": [
    {
      "name": "booking.lookup_next",
      "ok": true,
      "booking_id": "<booking_uuid>",
      "scheduled_start_at": "2026-04-18T20:00:00+00:00",
      "duration_minutes": 60,
      "booking_type": "outcall"
    }
  ]
}
```

Example chat request (relay intent):
```json
{
  "worker_id": "<worker_uuid>",
  "message_text": "Tell him to wait outside the building. I will call him."
}
```

Example relay action entry:
```json
{
  "name": "client.message.send",
  "ok": true,
  "booking_id": "<booking_uuid>",
  "channel": "whatsapp",
  "sid": "SM123"
}
```

## Media APIs

- `POST /media/twilio/ingest`
  - Returns enriched media metadata (`booking_id`, `channel`, `media_type`, `twilio_media_sid`, `is_receipt`, `source_url`).
  - Media file is fetched from Twilio and stored locally under backend `media/<client_phone>/...` when retrieval succeeds.
  - Inbound media is persisted as receipt-received (`is_receipt=true`) for immediate booking/media context continuity.
- `GET /admin/bookings/{booking_id}/media`
  - Prefers local served media URL when `storage_url` exists.
- `GET /admin/media/{media_id}/content`
  - Streams locally stored media file for admin panel rendering.
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
- Worker stream is role-guarded (`worker` only) and emits worker-targeted updates for:
  - `worker.permissions.updated`
  - `worker.chat_reply`
  - `worker.operation.completed`
  - `booking.status_changed` for bookings belonging to the authenticated worker
- Both streams send a connection event (`admin_stream.connected`, `worker_stream.connected`) and keepalive comments.
