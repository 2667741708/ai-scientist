# Research Account And Login Design

This document records the login and account mechanism adapted from `D:\文件\灵山` into `open-coscientist/webapp/`.

## Lingshan Source References

The Lingshan project has a complete visitor/admin split:

| Area | Source file | Reusable idea |
| --- | --- | --- |
| Unified public login | `D:\文件\灵山\frontend\src\pages\LoginPage.vue` | One entry supports visitor login, registration, password reset, guest session, and admin submit. |
| Login form states | `D:\文件\灵山\frontend\src\components\auth\LoginForm.vue` | Mode switching, remember account, password visibility, loading state, field validation, error message. |
| Admin-only login | `D:\文件\灵山\frontend\src\pages\admin\AdminLogin.vue` | Separate administrator path with redirect guard and token persistence. |
| Route guards | `D:\文件\灵山\frontend\src\router\index.ts` | Admin routes require `admin_token`; visitor routes require `visitor_session_uuid`. |
| Admin auth service | `D:\文件\灵山\backend\app\services\auth_service.py` | PBKDF2 password hashing, HMAC bearer token, role/permission table, admin CRUD. |
| Visitor account service | `D:\文件\灵山\backend\app\services\visitor_account_service.py` | User account registration/login/session binding and activity profile. |
| Admin API | `D:\文件\灵山\backend\app\api\admin.py` | `require_admin_permission(...)` dependency protects sensitive admin endpoints. |
| Admin schema | `D:\文件\灵山\backend\app\schemas\admin.py` | Minimal request models for login, create user, status change, password reset. |
| Auth tests | `D:\文件\灵山\backend\tests\test_auth_service.py` | Success login, invalid password, disabled user, missing bearer token. |

## Adaptation For Open Co-Scientist

The research workbench should not copy the tourism vocabulary. The account model is reduced to two roles:

| Role | Product meaning | Permissions |
| --- | --- | --- |
| `researcher` | Ordinary graduate student / researcher | Research workspace, papers, tools, hypotheses, outputs. |
| `admin` | Lab or system administrator | Researcher permissions plus runtime readiness, model protocol settings, user management, service audit. |

## Backend Implementation

Current implementation:

- `backend/auth_store.py`
  - SQLite account table under `webapp/.auth/accounts.sqlite3` by default.
  - PBKDF2-HMAC-SHA256 password hash.
  - HMAC-signed bearer token with 24 hour TTL.
  - Seed admin from `COSCIENTIST_ADMIN_EMAIL` and `COSCIENTIST_ADMIN_PASSWORD`.
- `backend/app.py`
  - `POST /api/auth/register`
  - `POST /api/auth/login`
  - `GET /api/auth/me`
  - `POST /api/auth/logout`
  - `GET /api/auth/roles`
  - `GET /api/admin/users`
  - `POST /api/admin/users`
  - `PUT /api/admin/users/{account_id}/status`
  - `PUT /api/admin/users/{account_id}/password`

The first implementation protects account-management endpoints. The existing research APIs remain compatible with the current local workflow; future hardening can add `Depends(require_user)` to write endpoints after frontend clients consistently pass bearer tokens.

## Frontend Implementation

Current implementation:

- `src/lib/api/auth.ts`
  - Token persistence and authenticated fetch helpers.
  - Login, register, current account, logout, admin users API.
- `src/features/auth/auth-context.tsx`
  - React auth context.
  - Session refresh via `/api/auth/me`.
  - `signIn`, `register`, `signOut`.
- `src/features/auth/ProtectedRoute.tsx`
  - Redirects unauthenticated users to `/login`.
  - Blocks non-admin users from `/admin`.
- `src/pages/login/LoginPage.tsx`
  - Researcher login, researcher registration, admin login modes.
  - Loading, disabled, password visibility, error feedback, remember email.
- `src/app/router.tsx`
  - Protects the app shell and admin route.
- `src/app/layout/AppShell.tsx`
  - Shows current account and logout.
- `src/components/navigation/PrimaryNav.tsx`
  - Hides runtime readiness/admin nav from non-admin users.
- `src/pages/admin/AdminPage.tsx`
  - Admin account list, create account, enable/disable, reset temporary password.

## Current Local Seed Account

For local development, the backend seeds the first administrator from:

```text
COSCIENTIST_ADMIN_EMAIL
COSCIENTIST_ADMIN_PASSWORD
```

If not set, the local dev defaults are used. Production or shared deployment must set both environment variables and rotate the default password immediately.

## Future Hardening

Recommended next steps before multi-user production:

1. Add refresh-token or server-side session revocation.
2. Add audit log rows for login, user creation, status change, and password reset.
3. Gate write APIs with `require_user` and admin-only runtime settings with `require_permission("runtime:write")`.
4. Add email reset flow or integrate university SSO / OAuth / OIDC.
5. Add per-project membership if multiple research groups share one deployment.
