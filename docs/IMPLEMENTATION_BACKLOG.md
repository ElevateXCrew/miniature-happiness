# Implementation Backlog (Phase 6 Active)

This backlog is ordered and dependency-aware for Admin Panel + RBAC delivery.

## 0) Backend Auth and RBAC Foundation (Do First)

- [ ] Add DB migration for `users` and `worker_section_permissions`.
- [ ] Add `user_role` and `section_key` enums to model layer.
- [ ] Implement auth service (password verification, JWT access, refresh token flow).
- [ ] Add auth endpoints: `/auth/login`, `/auth/refresh`, `/auth/logout`, `/auth/me`.
- [ ] Add RBAC permission service and section evaluator.
- [ ] Add admin endpoints to manage worker section permissions.
- [ ] Add audit events for permission changes.

## 1) Backend Authorization Guards

- [ ] Add reusable dependencies for role checks (`admin`, `worker`).
- [ ] Add section guard dependency (ex: `require_section("live_chat")`).
- [ ] Enforce `403` on disabled worker sections across protected APIs.
- [ ] Add `/ui/sections` endpoint returning effective section map.
- [ ] Add tests for unauthorized access and permission toggles.

## 2) Next.js Auth and App Shell

- [ ] Scaffold Next.js app with login and protected layouts.
- [ ] Add session bootstrap flow (`/auth/me` + `/ui/sections`).
- [ ] Implement token refresh handling.
- [ ] Build role-aware sidebar/menu.
- [ ] Add route guards for role + section visibility.

## 3) Admin Panel Screens

- [ ] Dashboard (pending review, notification/risk highlights).
- [ ] Booking queue with filters and pagination.
- [ ] Booking detail with lifecycle actions.
- [ ] Booking timeline (message/media/audit/notification stream).
- [ ] Media and receipt review panel.
- [ ] Active sessions and live monitoring panel.
- [ ] Agent pause/resume controls.
- [ ] Notification center.
- [ ] Worker access management screen.

## 4) Worker Portal Screens

- [ ] Worker home with upcoming bookings.
- [ ] Worker action controls (approve/reject/complete-early/free-now).
- [ ] Worker reminders/notifications panel.
- [ ] Permission-aware section visibility across worker UI.

## 5) Realtime Integration

- [ ] Connect admin UI to `/events/admin/stream`.
- [ ] Handle `Last-Event-ID` resume logic.
- [ ] Reflect booking/notification/permission updates without full reload.

## 6) QA and Launch Gate

- [ ] Backend quality gate: `ruff check .` -> `mypy app` -> `pytest`.
- [ ] RBAC regression tests (UI hidden + API `403`).
- [ ] E2E workflow checks for admin review lifecycle.
- [ ] E2E check: disable `live_chat` for worker and verify immediate enforcement.
- [ ] Extend UAT checklist with Phase 6 auth/RBAC/admin-panel scenarios.
