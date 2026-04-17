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

## Phase 6 Track 4 Addendum (Admin Panel + RBAC Realtime)

### Additional Preconditions

- Frontend build passes in `frontend/`:
  - `npm run build`
- Backend includes realtime stream endpoints:
  - `GET /events/admin/stream`
  - `GET /events/worker/stream`

### Realtime + RBAC UAT Matrix (Must Pass)

1. Admin realtime booking sync
   - Keep `Dashboard`, `Bookings`, and `Live Chat` open in admin UI.
   - Trigger booking approve/reject/complete from a second session.
   - Expected: pages refresh automatically without manual reload.

2. Notification lifecycle realtime sync
   - Trigger `/notifications/dispatch/run` with queued notifications.
   - Expected: notification center status chips update from `queued` to `sent`/`retry_pending`/`dead_letter` without manual refresh.

3. Worker permission propagation
   - Keep worker logged in with `live_chat` enabled.
   - From admin settings, disable `live_chat` for that worker.
   - Expected: worker sections refresh immediately; disabled actions/views are blocked without re-login.

4. Stream RBAC guards
   - Attempt `GET /events/admin/stream` with worker token.
   - Attempt `GET /events/worker/stream` with admin token.
   - Expected: both return `403`.

5. Worker-targeted permission stream filtering
   - Connect worker A to `/events/worker/stream`.
   - Update permissions for worker B, then worker A.
   - Expected: worker A receives only worker A permission event.

### Phase 6 Launch Sign-off

- [x] Backend tests include Track 4 realtime/RBAC regression coverage and pass.
- [ ] Worker/admin realtime stream behavior validated in staging.
- [ ] Permission toggles propagate instantly to active worker sessions.
- [ ] Product + Engineering approval captured for admin panel launch.
