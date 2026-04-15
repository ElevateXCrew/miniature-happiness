# State Machine and Transition Rules

## Principles

- Backend state machine is authoritative.
- LLM cannot directly set final statuses without tool validation.
- Any ambiguous input keeps state unchanged and asks clarification.

## Conversation States

- `IDLE`: no active collection.
- `COLLECTING`: gathering fields in required order.
- `AWAITING_CLIENT_CONFIRMATION`: summary sent; waiting for explicit yes.
- `WAITING_REVIEW`: submitted, waiting for admin/worker decision.
- `PAUSED`: automation paused.
- `HANDOFF`: manual handling active.
- `ERROR_REVIEW`: invalid or conflicting state requires intervention.

## Booking Statuses

- `DRAFT`
- `PENDING_REVIEW`
- `CONFIRMED`
- `REJECTED`
- `CANCELLED`
- `COMPLETED`

## Required Field Order

1. `scheduled_start_at`
2. `client_age` (must be >= 18)
3. `client_ethnicity` (mandatory)
4. `duration_minutes`
5. `client_name` (optional)

Then booking-type branch:

- `incall` -> send incall address at allowed stage.
- `outcall` -> require `outcall_address`, `advance_required_gbp`, and receipt flow.

## Transition Table (Core)

- `IDLE -> COLLECTING`
  - Trigger: booking intent detected.
  - Action: create/update draft booking.

- `COLLECTING -> AWAITING_CLIENT_CONFIRMATION`
  - Trigger: required fields complete + availability check passes.
  - Action: generate deterministic summary.

- `AWAITING_CLIENT_CONFIRMATION -> WAITING_REVIEW`
  - Trigger: explicit affirmative client confirmation.
  - Action: set booking status `PENDING_REVIEW`, notify admin and worker.

- `WAITING_REVIEW -> IDLE`
  - Trigger: booking `CONFIRMED` or `REJECTED` or `CANCELLED`.
  - Action: notify client; clear active collection context.

- `ANY -> PAUSED`
  - Trigger: admin pause command.

- `PAUSED -> previous`
  - Trigger: admin resume command; process queued messages in order.

- `CONFIRMED -> COMPLETED`
  - Trigger: worker/admin completion action or scheduled completion job.

## Mandatory Guards

- Re-check availability before moving to `PENDING_REVIEW`.
- Re-check availability before final confirmation to `CONFIRMED`.
- Enforce 15-minute buffer around all confirmed/pending bookings.
- Reject under-18 booking attempts.
- Reject attempts to skip mandatory ethnicity field.
