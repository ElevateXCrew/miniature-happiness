# Admin Panel Specification (Phase 6)

This document is the implementation contract for Next.js admin/worker web surfaces.

## Scope

- Role-based auth with two roles only: `admin`, `worker`.
- Admin can manage worker section visibility.
- Worker cannot access disabled sections in UI or API.
- Admin panel supports full booking review operations defined in `AI Booking Assistant_ Features and Flow.md`.

## Roles and Section Access

- `admin`
  - Full access to all sections and worker access controls.
- `worker`
  - Access only to sections enabled by admin.

Section keys:
- `dashboard`
- `live_chat`
- `bookings`
- `timeline`
- `media`
- `notifications`
- `schedule`
- `settings`

## Screen Modules

## 1) Auth

- Login screen (email + password).
- Session bootstrap on app load (`/auth/me`, `/ui/sections`).
- Refresh token flow.

Dependencies:
- `POST /auth/login`
- `POST /auth/refresh`
- `POST /auth/logout`
- `GET /auth/me`
- `GET /ui/sections`

Acceptance:
- Admin and worker can login and persist session.
- Unauthorized users are redirected to login.

## 2) Admin Dashboard

- KPI cards: pending reviews, queued due notifications, reminder failures, failed tools.
- Recent booking and notification activity.

Dependencies:
- `GET /metrics`
- `GET /admin/bookings`
- `GET /admin/notifications`

Acceptance:
- Dashboard reflects backend counters and recent operational state.

## 3) Booking Queue

- Filter by status, pagination (offset/limit), searchable list.
- Quick actions (approve/reject/cancel).

Dependencies:
- `GET /admin/bookings`
- `POST /admin/bookings/{booking_id}/approve`
- `POST /admin/bookings/{booking_id}/reject`
- `POST /admin/bookings/{booking_id}/cancel`

Acceptance:
- Actions update row status and trigger client decision messaging pipeline.

## 4) Booking Detail and Timeline

- Booking detail panel (core fields, review metadata, financial flags).
- Timeline with messages, media, audit events, notifications.
- Edit booking fields and mark incall address sent.

Dependencies:
- `GET /admin/bookings/{booking_id}`
- `GET /admin/bookings/{booking_id}/timeline`
- `PATCH /admin/bookings/{booking_id}`
- `POST /admin/bookings/{booking_id}/incall-address-sent`

Acceptance:
- Timeline is complete and ordered.
- Booking edits are reflected in backend state machine rules.

## 5) Media and Receipt Review

- Media gallery per booking.
- Receipt badge and manual "mark receipt" action.

Dependencies:
- `GET /admin/bookings/{booking_id}/media`
- `POST /admin/media/{media_id}/mark-receipt`

Acceptance:
- Receipt visibility and classification are available to admin quickly.

## 6) Active Sessions and Live Chat Monitor

- Active sessions list.
- Live conversation view for admin monitoring.
- Pause/resume automation controls.

Dependencies:
- `GET /admin/sessions/active`
- `POST /admin/agent/pause`
- `POST /admin/agent/resume`
- `GET /events/admin/stream`

Acceptance:
- Admin can monitor ongoing conversations and pause/resume safely.

## 7) Notification Center

- Show queued, sent, retry_pending, dead_letter notifications.
- Trigger manual dispatch/reminder runs if required.

Dependencies:
- `GET /admin/notifications`
- `POST /notifications/dispatch/run`
- `POST /notifications/reminders/run`

Acceptance:
- Admin can identify and act on retry/dead-letter conditions.

## 8) Worker Access Management

- Worker list and per-worker section toggle UI.
- Immediate propagation of changed permissions.

Dependencies:
- `GET /admin/users/workers`
- `GET /admin/users/{user_id}/section-permissions`
- `PUT /admin/users/{user_id}/section-permissions`

Acceptance:
- Disabling `live_chat` hides worker section and blocks related API with `403`.

## 9) Worker Portal

- Worker home with upcoming bookings.
- Worker decision actions and operational commands.
- Views are permission-gated by admin section map.

Dependencies:
- `GET /worker/bookings/upcoming`
- `POST /worker/bookings/{booking_id}/approve`
- `POST /worker/bookings/{booking_id}/reject`
- `POST /worker/bookings/{booking_id}/complete-early`
- `POST /worker/availability/free-now`
- `POST /worker/messages`

Acceptance:
- Worker can only perform actions in enabled sections.

## Realtime Behavior

- Subscribe to `GET /events/admin/stream` for booking, notification, and permission update events.
- UI should reconcile events idempotently and support resume by `Last-Event-ID`.

## Testing Requirements

- Route guard tests (admin vs worker).
- Permission toggle tests (UI hidden + API 403).
- Booking lifecycle UI tests (approve/reject/cancel/edit).
- Timeline/media rendering tests.
- Realtime update tests.
