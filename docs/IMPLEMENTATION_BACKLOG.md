# Implementation Backlog (Post-Phase 6 Launch Hardening)

This backlog is the execution queue after Phase 6 feature delivery.
Use it for launch readiness, regression safety, and handoff continuity.

## Status Snapshot

- Phase 6 Tracks 0-4 are implemented and integrated.
- Admin/worker realtime sync and RBAC propagation are implemented.
- Release-candidate quality gate is complete and green across backend/frontend checks.
- Remaining work is focused on UAT execution, release sign-off, and operational hardening.

## Completed Delivery Baseline (Do Not Re-open Without Product Direction)

- [x] Backend auth/RBAC foundation (users, section permissions, JWT auth APIs).
- [x] Backend role + section authorization guards with `403` enforcement.
- [x] Next.js auth shell with role-aware sidebar and route guards.
- [x] Admin panel core screens (dashboard, bookings, timeline, sessions, notifications, settings).
- [x] Worker portal and permission-gated operational actions.
- [x] Realtime SSE sync for admin/worker, including permission refresh propagation.
- [x] Track 4 regression coverage and UAT checklist addendum.

## 1) Release Candidate Quality Gate (High Priority)

- [x] Run backend gate in `backend/`: `ruff check .`, `mypy app`, `pytest`.
- [x] Run focused realtime regression: `python -m pytest tests/test_phase6_track4_realtime.py -q`.
- [x] Run frontend gate in `frontend/`: `npm run build` (must pass with 0 TypeScript errors).

## 2) Phase 6 UAT Execution (High Priority)

- [ ] Execute Phase 6 Track 4 realtime/RBAC UAT matrix in staging.
- [ ] Validate worker permission propagation during active sessions (no re-login).
- [ ] Validate stream RBAC guards and worker-target filtering behavior.

## 3) Release Governance and Documentation (Medium Priority)

- [ ] Capture Product + Engineering sign-off for launch.
- [ ] Keep `docs/API_ENDPOINTS.md` and `docs/WORKFLOWS.md` in sync with any release-critical behavior changes.
- [ ] Keep `AGENTS.md` and `IMPLEMENTAION_PLAN.md` aligned when status changes.

## 4) Post-Launch Monitoring Readiness (Medium Priority)

- [ ] Review retry/dead-letter behavior and notification queue health during staging soak.
- [ ] Confirm dashboards/alerts around `GET /metrics` counters are actionable for ops.

## 5) Future Scope Parking Lot (Low Priority)

- [ ] Define mobile worker app scope beyond current worker web portal.
- [ ] Evaluate additional realtime UX resilience (offline recovery, backpressure handling, stream diagnostics).
