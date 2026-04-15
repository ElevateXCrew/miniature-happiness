# Agent Tool Catalog (Deterministic Backend Tools)

These are backend-executed tools callable by the LLM orchestration layer.

## Identity and Session

1. `get_or_create_client_by_phone(phone_e164)`
   - Returns canonical client profile.

2. `get_or_create_active_session(client_id, worker_id, channel)`
   - Returns active conversation session.

## Booking Data Collection

3. `get_required_next_field(booking_id)`
   - Returns next missing field based on enforced order.

4. `update_booking_field(booking_id, field_name, field_value)`
   - Validates and updates one field atomically.

5. `validate_booking_fields(booking_id)`
   - Returns completeness and any validation errors.

## Availability and Slot Management

6. `check_availability(worker_id, start_at, duration_minutes)`
   - Returns availability and alternatives.
   - Must enforce 15-minute buffer.

7. `reserve_tentative_slot(booking_id)`
   - Optional hold to reduce race conditions.

8. `release_slot(booking_id, reason)`
   - Releases tentative/locked slot.

## Lifecycle Actions

9. `submit_booking_for_review(booking_id, reviewer)`
   - Moves booking to `PENDING_REVIEW`, creates notifications.

10. `set_booking_status(booking_id, status, actor_type, actor_ref, note)`
    - Controlled status transition with audit log.

11. `complete_booking_early(booking_id, actor_ref)`
    - Marks booking completed and frees slot for future bookings.

## Channel and Messaging

12. `send_client_message(client_id, channel, text, context)`
    - Outbound message through selected channel.

13. `route_media_request_to_whatsapp(client_id)`
    - Sends instruction to continue media sharing on WhatsApp.

## Media

14. `attach_media_to_session_or_booking(client_id, session_id, media_payload)`
    - Stores media metadata and links to booking if determinable.

15. `mark_media_as_receipt(media_id, booking_id)`
    - Sets receipt classification.

## Notifications and Reminders

16. `create_notification(target_type, target_ref, template_key, payload, send_at)`
    - Queue notification for admin/worker/client.

17. `schedule_booking_reminders(booking_id, minutes_before=20)`
    - Creates reminder notifications for all parties.

## Worker Commands (Mobile-ready)

18. `process_worker_command(worker_id, message_text)`
    - Parses and executes worker intents (free now, adjust timing, etc.).

19. `set_worker_availability_override(worker_id, from_at, to_at, mode)`
    - Blocks/unblocks calendar windows.
