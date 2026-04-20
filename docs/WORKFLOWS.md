# Critical Workflows

## 1) New Booking via Client Chat

1. Inbound message arrives on SMS/WhatsApp webhook.
2. Normalize phone, resolve client, load active session.
3. Agent sends short natural response (Alysha persona).
4. On booking intent, create/update draft booking.
5. Collect required fields in strict order.
6. Run availability tool before confirming proposed slot.
7. Persist/link a draft booking to the active session when availability succeeds (deterministic guard).
8. Summarize details and request explicit confirmation.
9. On explicit yes, move to `PENDING_REVIEW` and notify admin + worker.
10. Tell client to wait briefly.
11. On approval/rejection/cancel event, route an internal decision instruction through agent runtime.
12. Alysha sends a short client-facing decision message that keeps continuity with recent conversation tone.
13. Finalize state and emit admin sync events.

## 2) Outcall Flow with Advance and Receipt

1. Booking type set to `outcall`.
2. Collect outcall address.
3. Request advance payment for transport.
4. If on SMS, ask client to send media via WhatsApp same number.
5. Receive receipt image and attach to booking/session.
6. Mark receipt and expose in admin panel.
7. Continue to review stage.

## 3) Worker "Free Now" Command

1. Worker sends command through worker API.
2. Agent runtime interprets intent using worker command tool.
3. Backend marks active booking complete early (if valid).
4. Slot is released immediately.
5. Admin panel receives sync event.
6. Future availability checks reflect freed slot.

## 4) T-20 Reminder Flow

1. Scheduler scans upcoming confirmed bookings.
2. Creates reminders for admin, worker, client.
3. Client template differs by booking type (incall vs outcall).
4. Notification status tracked and retried on failure.

## 5) Admin Toggles Worker Section Access

1. Admin opens worker access controls in panel.
2. Admin disables a section (example: `live_chat`) for a worker user.
3. Backend updates `worker_section_permissions` and writes audit event.
4. Backend emits realtime permission update event.
5. Worker UI hides disabled section immediately.
6. Any direct API call to disabled section returns `403`.

## 6) Admin/Worker Login and Guarded Navigation

1. User logs in via `/auth/login` and receives JWT access + refresh tokens.
2. UI calls `/auth/me` and `/ui/sections` during session bootstrap.
3. Admin receives full navigation; worker receives permission-limited navigation.
4. Route guards block unauthorized pages before render.
5. Backend authorization still enforces role/section checks for all protected APIs.

## 7) Worker Decision Sync to Admin Panel

1. Worker approves/rejects/completes a booking from worker interface.
2. Backend updates booking state and creates deterministic notifications.
3. Admin SSE stream emits booking update event.
4. Admin queue/detail/timeline refreshes without manual reload.

## 8) Dashboard Fail-Soft Behavior

1. Dashboard requests metrics, bookings, and notifications independently.
2. If one endpoint fails, available widgets still render.
3. Failed widget shows inline error state and retry action.
4. Operators can continue core review actions without full-page failure.

## 9) Availability Error Recovery

1. Agent/tool receives malformed or ambiguous datetime input.
2. Backend returns deterministic validation error (no unhandled exception path).
3. Agent replies with short recovery prompt asking for clear date/time.
4. Booking flow continues after corrected input without state corruption.
