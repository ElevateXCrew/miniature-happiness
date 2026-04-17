# Implementation Backlog (Post-Stabilization)

This backlog is now bug-fix and operations focused. Major feature tracks are complete.

## Current Baseline (Complete)

- [x] Phase 1-5 deterministic backend delivery.
- [x] Phase 6 Tracks 0-4 (auth/RBAC, admin panel, worker portal, realtime sync).
- [x] Phase 6 stabilization pass (dashboard fail-soft, availability recovery, role/section consistency).
- [x] Release-candidate quality gate and UAT execution evidence captured.

## Priority 1: Ongoing Defect Triage and Regression Safety

- [ ] Keep weekly regression run green:
  - backend: `ruff check .`, `mypy app`, `pytest`
  - focused realtime: `python -m pytest tests/test_phase6_track4_realtime.py -q`
  - frontend: `npm run build`
- [ ] For each user-reported bug, add or update at least one regression test before closing.
- [ ] Track recurring failure patterns (tool failures, retry/dead-letter growth, dashboard load errors).

## Priority 2: Launch Governance and Operations

- [ ] Keep launch decision record current with approvals and rollback owner.
- [ ] Keep alert thresholds tuned for `GET /metrics` counters.
- [ ] Run production-like smoke checks after every hotfix deployment.

## Priority 3: Documentation Hygiene

- [ ] Keep `AGENTS.md` current with exact test counts and active workstream.
- [ ] Keep `docs/API_ENDPOINTS.md` and `docs/WORKFLOWS.md` in sync with behavior changes.
- [ ] Keep `AI Booking Assistant_ Features and Flow.md` aligned with real behavior expectations for bug-fixing agents.

## Priority 4: Deferred Scope (Do Not Start Without Product Direction)

- [ ] Mobile worker app implementation (beyond current worker web portal).
- [ ] Advanced realtime resilience features (offline replay UX, stream diagnostics tooling).
