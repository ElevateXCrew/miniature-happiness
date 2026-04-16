# Phase 5 UAT and Launch Readiness Checklist

## Scope

This checklist covers final reliability hardening verification for:

- inbound deduplication and out-of-order handling,
- outbound retry queue and dead-letter behavior,
- failure telemetry/metrics,
- race-condition resilience across booking lifecycle.

## Environment Preconditions

- Twilio credentials and sender numbers configured in `.env`.
- `twilio_validate_signature=true` in non-local environments.
- DB migrated to include Phase 5 migration (`002_phase5_reliability`).
- Test command passes in backend workspace:
  - `python -m pytest`

## UAT Matrix (Must Pass)

1. Duplicate inbound webhook replay
   - Send same `MessageSid` twice.
   - Expected: second request marked `duplicate=true`; same response can be replayed (`replayed=true`).
   - Expected: no additional booking draft created.

2. Out-of-order inbound event
   - Send newer inbound event then an older timestamp event for same session.
   - Expected: stale event ignored (`response_text=null`), no state regression.

3. Outbound send transient failure
   - Force Twilio failure for outbound send.
   - Expected: notification moves to `retry_pending` with backoff and incremented `retry_count`.

4. Outbound retry exhaustion
   - Keep failing retries beyond configured max attempts.
   - Expected: notification transitions to `dead_letter`; failure visible in metrics.

5. Booking conflict race
   - Two conflicting pending bookings attempt confirmation.
   - Expected: at most one becomes `CONFIRMED`; conflict remains blocked.

6. Reminder scheduler resilience
   - Run `/notifications/reminders/run` with due confirmations.
   - Expected: reminders created and dispatch result includes sent/failed/dead-lettered counts.

7. Tool failure telemetry
   - Trigger at least one deterministic tool failure path.
   - Expected: failure counters increment and audit events include tool metadata.

## Launch Readiness Sign-off

- [ ] Migrations applied in staging and production (`alembic upgrade head`).
- [ ] Full backend tests passing (`python -m pytest`).
- [ ] Reliability counters visible on `GET /metrics`.
- [ ] Dead-letter queue monitoring reviewed by ops.
- [ ] Twilio delivery failure alert thresholds confirmed.
- [ ] Rollback plan documented and tested.
- [ ] Product + Engineering sign-off complete.

## Go-Live Recommendation

Proceed to launch only when all UAT matrix scenarios are green and no unresolved dead-letter growth trend is present for 24h in staging-like traffic.
