# Critical Workflows

## 1) New Booking via Client Chat

1. Inbound message arrives on SMS/WhatsApp webhook.
2. Normalize phone, resolve client, load active session.
3. Agent sends short natural response (Alysha persona).
4. On booking intent, create/update draft booking.
5. Collect required fields in strict order.
6. Run availability tool before confirming proposed slot.
7. Summarize details and request explicit confirmation.
8. On explicit yes, move to `PENDING_REVIEW` and notify admin + worker.
9. Tell client to wait briefly.
10. On approval/rejection event, notify client and finalize state.

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
