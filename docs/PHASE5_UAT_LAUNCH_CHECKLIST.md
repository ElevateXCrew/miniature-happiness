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

### Execution Evidence (2026-04-17)

- ✅ 1) Duplicate inbound webhook replay
   - Evidence: `backend/tests/test_phase2_orchestration.py::test_twilio_sms_webhook_parses_form_and_handles_duplicates` and `backend/tests/test_phase2_orchestration.py::test_agent_process_incoming_is_idempotent`.
   - Result: duplicate replay detected and no duplicate inbound persistence for same `MessageSid`.

- ✅ 2) Out-of-order inbound event
   - Evidence: `backend/tests/test_phase5_reliability.py::test_out_of_order_inbound_is_ignored`.
   - Result: stale message returns `response_text=None`; state does not regress.

- ✅ 3) Outbound send transient failure
   - Evidence: `backend/tests/test_phase5_reliability.py::test_notification_retry_and_dead_letter_flow` (first dispatch cycle).
   - Result: notification transitions to `retry_pending` and increments retry count.

- ✅ 4) Outbound retry exhaustion
   - Evidence: `backend/tests/test_phase5_reliability.py::test_notification_retry_and_dead_letter_flow` (second dispatch cycle).
   - Result: notification transitions to `dead_letter` after retry budget exhaustion.

- ✅ 5) Booking conflict race
   - Evidence: `backend/tests/test_phase5_reliability.py::test_race_condition_confirmation_conflict_still_blocked`.
   - Result: at most one booking confirms; conflicting confirmation is blocked.

- ✅ 6) Reminder scheduler resilience
   - Evidence: `backend/tests/test_phase3_lifecycle.py::test_reminder_scheduler_creates_t20_with_style_hints`.
   - Result: reminders scheduled and dispatch payload includes sent/failed/dead-lettered counts.

- ✅ 7) Tool failure telemetry
   - Evidence: `backend/tests/test_phase5_reliability.py::test_tool_failure_telemetry_increments_counter_and_writes_audit`.
   - Result: `tool_calls_failed_total` increments and `tool_execution_failed` audit metadata contains tool name/arguments/error.

## Launch Readiness Sign-off

- [ ] Migrations applied in staging and production (`alembic upgrade head`).
- [x] Full backend tests passing (`python -m pytest`).
- [x] Reliability counters visible on `GET /metrics`.
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

### Phase 6 Realtime/RBAC Execution Evidence (2026-04-17)

- ✅ 1) Admin realtime booking sync
   - Evidence: `backend/tests/test_phase6_track4_realtime.py::test_admin_stream_emits_booking_status_changed_on_approve`.
   - Result: `booking.status_changed` event emitted with confirmed status payload.

- ✅ 2) Notification lifecycle realtime sync
   - Evidence: `backend/tests/test_phase6_track4_realtime.py::test_admin_stream_emits_notification_created_and_status_changed`.
   - Result: `notification.created` and `notification.status_changed` events emitted during dispatch lifecycle.

- ✅ 3) Worker permission propagation
   - Evidence: `backend/tests/test_phase6_auth_rbac.py::test_admin_can_toggle_worker_section_and_worker_gets_403` and `backend/tests/test_phase6_track4_realtime.py::test_worker_stream_receives_own_permission_updates_only`.
   - Result: permission update enforced immediately and worker stream receives correct permission-target events.

- ✅ 4) Stream RBAC guards
   - Evidence: `backend/tests/test_phase6_track4_realtime.py::test_admin_and_worker_stream_role_guards`.
   - Result: cross-role stream access denied with `403`.

- ✅ 5) Worker-targeted permission stream filtering
   - Evidence: `backend/tests/test_phase6_track4_realtime.py::test_worker_stream_receives_own_permission_updates_only`.
   - Result: worker receives own permission event only; other worker updates filtered out.

### Phase 6 Launch Sign-off

- [x] Backend tests include Track 4 realtime/RBAC regression coverage and pass.
- [x] Worker/admin realtime stream behavior validated in automated regression suite.
- [x] Permission toggles propagate instantly in enforced API + worker stream regression paths.
- [ ] Product + Engineering approval captured for admin panel launch.

## Final Sign-off Notes (2026-04-17)

- Automated launch gates are green:
   - `ruff check .` ✅
   - `mypy app` ✅
   - `pytest` ✅ (`43 passed`)
   - `python -m pytest tests/test_phase6_track4_realtime.py -q` ✅ (`4 passed`)
   - `npm run build` ✅
- No open code regressions remain after launch execution fixes.
- External/governance items still require human completion before production go-live:
   - staging/prod migration confirmation,
   - ops monitoring/alert validation,
   - rollback drill confirmation,
   - Product + Engineering approval capture.
