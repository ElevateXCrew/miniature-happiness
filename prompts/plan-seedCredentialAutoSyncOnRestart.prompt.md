## Plan: Seed Credential Auto-Sync On Restart

Enable deterministic seed credential synchronization so admin and worker email/password are updated from .env whenever the app restarts, and keep the same behavior in the manual seeding script. The approach reuses existing startup seed hooks, adds explicit sync logic (including role-based lookup when email changes), and invalidates active refresh sessions on password updates.

**Steps**
1. Define sync contract and invariants (blocking step)
- Confirm invariant: one canonical seeded admin account (role=admin) and one canonical seeded worker account (role=worker with worker_id linkage), both must match configured seed email/password after sync.
- Confirm conflict rule: if target seed email is already used by another account, fail safely with clear logging and skip destructive reassignment.

2. Add repository helpers for role-based seeded-user lookup and safe credential updates (depends on 1)
- Extend user repository with focused helpers used by both startup and script flows:
- get user by role (admin/worker), independent of current email.
- update user email (with uniqueness guard handling).
- update password hash and clear current_refresh_jti to force re-login.
- Keep create path unchanged for first-run seeding.

3. Implement startup auto-sync in app lifespan seeding (depends on 2)
- In startup hook logic, for admin and worker independently:
- Resolve existing seeded user by role first; fallback by configured email if needed.
- If configured email differs, update to configured email.
- If configured password does not verify against stored hash, re-hash and update.
- Preserve worker linkage for worker user and keep role integrity checks.
- Keep transaction boundaries and failure-safe logging consistent with current startup behavior.

4. Apply same sync logic in manual seed script (parallel with 3 after 2)
- Reuse the same repository helpers/decision flow so python -m app.scripts.seed_users produces identical outcomes as restart-based sync.
- Avoid duplicating business logic by extracting a shared sync routine if practical.

5. Add observability and audit trail for credential drift corrections (parallel with 4)
- Emit structured logs for each action: created, email-updated, password-updated, skipped (conflict), no-change.
- Add audit events for system-driven updates (email/password) to support governance and incident review.

6. Add regression tests for restart and script paths (depends on 3 and 4)
- Test startup sync updates password when env password changes.
- Test startup sync updates email when env email changes.
- Test worker sync keeps worker_id linkage intact.
- Test email-collision case is handled safely (no destructive overwrite).
- Test manual script mirrors startup behavior.

7. Documentation and runbook updates (depends on 6)
- Update docs to state seeded credentials are now reconciled on restart and via seed script.
- Document operational side effect: password sync revokes active refresh sessions (users re-login).
- Add exact env key guidance and precedence.

**Relevant files**
- e:/company-projects/miniature-happiness/backend/app/main.py — extend lifespan seed flow (_seed_default_users) to run role-based reconciliation and updates.
- e:/company-projects/miniature-happiness/backend/app/scripts/seed_users.py — align manual command behavior with startup reconciliation.
- e:/company-projects/miniature-happiness/backend/app/repositories/user_repo.py — add role lookup and safe update helpers (email/password/refresh token invalidation).
- e:/company-projects/miniature-happiness/backend/app/services/auth_service.py — reuse hash_password and verify_password for secure password drift detection.
- e:/company-projects/miniature-happiness/backend/app/models/user.py — confirm fields affected by sync (email, password_hash, current_refresh_jti, role, worker_id).
- e:/company-projects/miniature-happiness/backend/app/repositories/audit_repo.py — record system-driven credential update events.
- e:/company-projects/miniature-happiness/backend/tests/test_phase6_auth_rbac.py — add auth/credential sync regression coverage.
- e:/company-projects/miniature-happiness/backend/tests/conftest.py — add fixtures/env overrides for startup-sync test scenarios.
- e:/company-projects/miniature-happiness/AGENTS.md — document behavior change per repo documentation hygiene rule.
- e:/company-projects/miniature-happiness/IMPLEMENTAION_PLAN.md — update implemented behavior note.
- e:/company-projects/miniature-happiness/docs/API_ENDPOINTS.md — clarify no API endpoint required; sync occurs at startup/script.
- e:/company-projects/miniature-happiness/docs/WORKFLOWS.md — update operator workflow for credential rotation via .env.
- e:/company-projects/miniature-happiness/AI Booking Assistant_ Features and Flow.md — update feature behavior summary.

**Verification**
1. Backend static and type checks:
- Run ruff check . from backend/
- Run mypy app from backend/
2. Unit/integration tests:
- Run pytest from backend/
- Run python -m pytest tests/test_phase6_track4_realtime.py -q from backend/ (required project gate)
- Run targeted auth/seed tests for new sync behavior.
3. Manual functional verification:
- Start app with baseline seed env; verify seeded users created.
- Change admin/worker seed email/password in .env; restart app; verify login works only with new credentials and old refresh token/session is invalidated.
- Run python -m app.scripts.seed_users with changed env; verify same reconciliation outcomes.

**Decisions**
- Included scope: synchronize both email and password for seeded admin and worker to .env values.
- Included scope: apply behavior in both startup seeding and manual seed script.
- Included scope: invalidate refresh token state on password change for security.
- Excluded scope: adding new public API endpoints for credential mutation.
- Excluded scope: changing RBAC model or adding additional user roles.

- Deployment config note: no in-repo YAML changes required for this workspace; only ensure VPS runtime env injection (for example service file or compose env) includes chosen keys.
**Further Considerations**
1. Email conflict handling recommendation: fail safely and log (recommended) instead of auto-merging/deleting another account.
2. Password sync policy recommendation: always hash+update only on verify mismatch to avoid unnecessary writes.
3. Startup resilience recommendation: continue app startup on non-critical sync error, but emit high-severity logs and audit entry.