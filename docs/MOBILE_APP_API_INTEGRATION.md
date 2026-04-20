# Mobile App API Integration Guide

This document is the implementation contract for the worker mobile app.

It is written so coding agents can build the mobile client without reverse engineering backend routes.

## Scope

- Mobile app user role: `worker`.
- Auth model: JWT access token + refresh token.
- Worker can only access sections enabled by admin.
- Backend authorization is authoritative (expect `403` when section is disabled).

## Base URL and Headers

- Base URL: backend host (example: `http://localhost:8000`)
- Auth header for protected APIs:
  - `Authorization: Bearer <access_token>`
- Content-Type:
  - `Content-Type: application/json`

## Auth Endpoints

## 1) Login

- `POST /auth/login`

Request:
```json
{
  "email": "worker@example.com",
  "password": "your-password"
}
```

Response:
```json
{
  "access_token": "...",
  "refresh_token": "...",
  "token_type": "bearer",
  "user": {
    "id": "<user_uuid>",
    "email": "worker@example.com",
    "role": "worker",
    "worker_id": "<worker_uuid>"
  }
}
```

## 2) Refresh

- `POST /auth/refresh`

Request:
```json
{
  "refresh_token": "..."
}
```

Response: same shape as login (new token pair).

## 3) Logout

- `POST /auth/logout`

Request:
```json
{
  "refresh_token": "..."
}
```

Response:
```json
{
  "ok": true
}
```

## 4) Session Identity

- `GET /auth/me`

Response:
```json
{
  "id": "<user_uuid>",
  "email": "worker@example.com",
  "role": "worker",
  "worker_id": "<worker_uuid>"
}
```

## Section Access (RBAC)

## Effective Section Map

- `GET /ui/sections`

Response:
```json
{
  "sections": {
    "dashboard": true,
    "live_chat": false,
    "bookings": true,
    "timeline": true,
    "media": true,
    "notifications": true,
    "schedule": true,
    "settings": false
  }
}
```

Rules:
- Hide disabled sections in mobile navigation.
- Still handle backend `403` because permissions can change at runtime.

## Worker APIs (Mobile Core)

All worker APIs require:
- authenticated user role `worker` or `admin`.
- matching `worker_id` for worker role (backend enforces this).

### Primary Mobile Contract (Chat-first)

- `POST /worker/messages`
- `GET /events/worker/stream`

Use direct action routes only when the app explicitly needs one-shot operational calls.

## 1) Upcoming Bookings

- `GET /worker/bookings/upcoming?worker_id=<worker_uuid>`

Response:
```json
[
  {
    "id": "<booking_uuid>",
    "status": "CONFIRMED",
    "scheduled_start_at": "2026-04-18T20:00:00+00:00",
    "duration_minutes": 60,
    "booking_type": "outcall",
    "client_name": "John"
  }
]
```

Permission dependency: `bookings` section.

## 2) Approve Booking

- `POST /worker/bookings/{booking_id}/approve?worker_id=<worker_uuid>`

Response:
```json
{
  "booking_id": "<booking_uuid>",
  "status": "CONFIRMED"
}
```

Permission dependency: `bookings` section.

## 3) Reject Booking

- `POST /worker/bookings/{booking_id}/reject?worker_id=<worker_uuid>`

Response:
```json
{
  "booking_id": "<booking_uuid>",
  "status": "REJECTED"
}
```

Permission dependency: `bookings` section.

## 4) Complete Booking Early

- `POST /worker/bookings/{booking_id}/complete-early?worker_id=<worker_uuid>`

Response:
```json
{
  "booking_id": "<booking_uuid>",
  "status": "COMPLETED"
}
```

Permission dependency: `bookings` section.

## 5) Free Now Command

- `POST /worker/availability/free-now`

Request:
```json
{
  "worker_id": "<worker_uuid>",
  "message_text": "free now"
}
```

Response:
```json
{
  "success": true,
  "message": "Availability updated"
}
```

Permission dependency: `schedule` section.

## 6) Block Availability

- `POST /worker/availability/block`

Request:
```json
{
  "worker_id": "<worker_uuid>",
  "from_at": "2026-04-18T18:00:00+00:00",
  "to_at": "2026-04-18T20:00:00+00:00"
}
```

Response:
```json
{
  "success": true,
  "message": "Availability blocked"
}
```

Permission dependency: `schedule` section.

## 7) Worker Message/Command

- `POST /worker/messages`

Request:
```json
{
  "worker_id": "<worker_uuid>",
  "message_text": "I am free now, clear slot"
}
```

Response:
```json
{
  "success": true,
  "assistant_reply": "Done. I marked your active booking complete and freed the slot.",
  "message": "Done. I marked your active booking complete and freed the slot.",
  "executed_actions": [
    {
      "name": "booking.complete_early",
      "ok": true,
      "booking_id": "<booking_uuid>",
      "status": "COMPLETED"
    }
  ]
}
```

Permission dependency: `live_chat` section.

Supported intent examples:

1. Query intent
```json
{
  "worker_id": "<worker_uuid>",
  "message_text": "What is my next booking time?"
}
```
Response includes `booking.lookup_next` in `executed_actions`.

2. Command intent
```json
{
  "worker_id": "<worker_uuid>",
  "message_text": "free now"
}
```
Response includes `booking.complete_early`.

3. Client relay intent
```json
{
  "worker_id": "<worker_uuid>",
  "message_text": "Tell him to wait outside the building. I will call him."
}
```
Response includes `client.message.send` when dispatch succeeds.

Unknown intent behavior:
- The endpoint returns a short natural Alysha fallback reply.
- The endpoint does not return a dead-end technical error for unrecognized chat prompts.

## Realtime (SSE)

## Worker Stream

- `GET /events/worker/stream`
- Header for resume:
  - `Last-Event-ID: <int>` (optional)

Notes:
- Keep connection open (SSE).
- Stream sends keepalive comments periodically.
- Worker receives worker-targeted events:
  - `worker.permissions.updated`
  - `worker.chat_reply`
  - `worker.operation.completed`
  - `booking.status_changed` for bookings owned by that worker

Example event envelope:
```json
{
  "id": 123,
  "type": "worker.operation.completed",
  "payload": {
    "worker_user_id": "<user_uuid>",
    "operation": "free_now",
    "ok": true,
    "message": "Done. I marked your active booking complete and freed the slot.",
    "executed_actions": [
      {
        "name": "booking.complete_early",
        "ok": true,
        "booking_id": "<booking_uuid>",
        "status": "COMPLETED"
      }
    ]
  },
  "timestamp": "2026-04-17T12:00:00+00:00"
}
```

Mobile behavior:
- On permission update event, re-fetch `/ui/sections` and re-render navigation/features.

## Error Handling Contract

- `401 Unauthorized`: access token missing/expired/invalid.
  - Attempt refresh once using `/auth/refresh`.
  - If refresh fails, force logout.
- `403 Forbidden`: role mismatch or section disabled.
  - Hide/disable feature in UI and show clear message.
- `404 Not Found`: booking/resource missing.
- `422 Unprocessable Entity`: invalid action for current state.
- `5xx`: transient backend issue; retry with backoff for safe read endpoints.

## Recommended Mobile Client Flow

1. Login (`/auth/login`) and store access+refresh securely.
2. Call `/auth/me`; ensure role is `worker`.
3. Call `/ui/sections`; build permission-aware navigation.
4. Fetch upcoming bookings.
5. Start SSE worker stream.
6. Send worker chat prompts to `/worker/messages` as the primary interaction path.
7. On `401`: refresh token and retry request once.
8. On permission change event: re-fetch `/ui/sections` and update UI immediately.

## QA Checklist for Mobile Integration

- Worker login/refresh/logout works.
- Disabled section is hidden in app and backend returns `403` when called directly.
- Upcoming bookings list loads.
- Approve/reject/complete-early actions work and state updates are reflected.
- Worker message query/command/relay intents execute successfully with `executed_actions`.
- Free-now direct route remains operational for compatibility.
- SSE reconnect + `Last-Event-ID` resume works.
