# Critical Workflows

## 1) New Booking via Client Chat

1. Inbound message arrives on SMS/WhatsApp webhook.
2. Normalize phone, resolve client, load active session.
3. Agent sends short natural response (Alysha persona).
4. If booking intent is unclear, keep chat natural and do not start collection tools yet.
5. On clear booking intent, create/update draft booking.
6. Collect required fields in strict order: datetime -> booking type -> duration -> outcall address(if outcall) -> age -> ethnicity -> size -> alone policy.
7. Start collection with a soft consent line before ordered questions.
8. Before LLM generation, runtime pre-captures the next required field from inbound text when possible.
9. Runtime blocks out-of-order/hallucinated field saves unless the value is present in current inbound text.
9a. Age is captured only from explicit age statements; runtime does not infer age from unrelated numeric text.
10. Run availability tool before confirming proposed slot.
11. Persist/link a draft booking to the active session when availability succeeds (deterministic guard), but keep duration empty unless client explicitly provided it.
12. Summarize details and request explicit confirmation.
13. For incall, include address only in final confirmation summary (not immediately after booking type).
14. On explicit yes (including short confirmations like ok/okay/fine where applicable), move to `PENDING_REVIEW` and notify admin + worker.
15. Tell client to wait briefly.
16. On approval/rejection/cancel event, route an internal decision instruction through agent runtime.
17. Alysha sends a short client-facing decision message that keeps continuity with recent conversation tone.
18. Finalize state and emit admin sync events.

## 2) Outcall Flow with Advance and Receipt

1. Booking type set to `outcall`.
2. Collect outcall address.
3. Request advance payment for transport.
4. If on SMS, ask client to send media via WhatsApp same number.
5. Receive receipt image and attach to booking/session.
5a. Fetch media from Twilio URL and store local copy under backend `media/<client_phone>/...`.
6. Mark receipt and expose in admin panel.
7. Continue to review stage.

## 2a) Admin Media Gallery Grouping

1. Admin opens Media section in panel.
2. Frontend calls `GET /admin/media`.
3. Backend returns all saved media rows with client phone metadata.
4. UI groups media by `client_phone_e164` and renders each group under that phone number.
5. New inbound media for an existing client appears under that same phone group on refresh.

## 3) Worker Client Relay (Mobile)

1. Worker sends relay command via `POST /worker/messages` (e.g. "tell client to ...").
2. Backend resolves current/next booking client and active session channel.
3. Worker runtime facade rewrites worker instruction into a natural Alysha client-facing message.
4. Twilio sends runtime-generated text to client.
5. Outbound message is persisted with `worker_instruction` metadata for traceability.
6. Worker receives operation result + assistant reply payload.

## 4) Worker "Free Now" Command

1. Worker sends chat prompt through `POST /worker/messages`.
2. Worker service classifies intent (`free now`, `done early`, `finished`).
3. Backend marks active booking complete early (if valid).
4. Slot is released immediately.
5. Worker stream emits `worker.operation.completed` and booking lifecycle updates.
6. Admin panel receives sync event.
7. Future availability checks reflect freed slot.

## 11) Worker Chat-first Mobile Flow

1. Worker app opens stream with `GET /events/worker/stream`.
2. Worker sends natural-language prompt to `POST /worker/messages`.
3. Backend resolves one of: query intent, command intent, or client relay intent.
4. Backend executes deterministic operation(s) and returns `assistant_reply` plus `executed_actions`.
5. Free-form worker chat uses worker runtime facade + worker prompt policy (separate from client intake runtime), so worker prompts are handled as worker-assistant chat.
6. Worker stream emits chat/operation updates:
	- `worker.chat_reply`
	- `worker.operation.completed`
	- `booking.status_changed` for worker-owned bookings
7. Unknown prompt receives a short natural fallback response (not a technical dead-end).
8. Optional direct action routes remain available for compatibility.

## 5) T-20 Reminder Flow

1. Scheduler scans upcoming confirmed bookings.
2. Creates reminders for admin, worker, client.
3. Client template differs by booking type (incall vs outcall).
4. Notification status tracked and retried on failure.

## 6) Admin Toggles Worker Section Access

1. Admin opens worker access controls in panel.
2. Admin disables a section (example: `live_chat`) for a worker user.
3. Backend updates `worker_section_permissions` and writes audit event.
4. Backend emits realtime permission update event.
5. Worker UI hides disabled section immediately.
6. Any direct API call to disabled section returns `403`.

## 7) Admin/Worker Login and Guarded Navigation

1. User logs in via `/auth/login` and receives JWT access + refresh tokens.
2. UI calls `/auth/me` and `/ui/sections` during session bootstrap.
3. Admin receives full navigation; worker receives permission-limited navigation.
4. Route guards block unauthorized pages before render.
5. Backend authorization still enforces role/section checks for all protected APIs.

## 8) Worker Decision Sync to Admin Panel

1. Worker approves/rejects/completes a booking from worker interface.
2. Backend updates booking state and creates deterministic notifications.
3. Admin SSE stream emits booking update event.
4. Admin queue/detail/timeline refreshes without manual reload.

## 9) Dashboard Fail-Soft Behavior

1. Dashboard requests metrics, bookings, and notifications independently.
2. If one endpoint fails, available widgets still render.
3. Failed widget shows inline error state and retry action.
4. Operators can continue core review actions without full-page failure.

## 10) Admin Live Chat History Clear

1. Admin opens Live Chat and selects a session.
2. Admin clicks Delete History and confirms the destructive action.
3. Backend clears `messages` rows for that session via admin-only endpoint.
4. Backend deletes linked session artifacts: `bookings`, `booking_media`, and `notifications` tied to those bookings.
5. Backend resets session state to `idle` with `active_booking_id=null`.
6. Backend writes audit event `messages.cleared` with deleted counts.
7. Chat panel refreshes to an empty history state for that session.

## 11) Availability Error Recovery

1. Agent/tool receives malformed or ambiguous datetime input.
2. Backend returns deterministic validation error (no unhandled exception path).
3. Agent replies with short recovery prompt asking for clear date/time.
4. Booking flow continues after corrected input without state corruption.
