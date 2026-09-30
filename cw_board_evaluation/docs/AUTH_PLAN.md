# Minimal consultant authentication (pre-pilot plan)

This document describes consultant authentication for pilot deployments.

**Implemented (Option A):** static API key via `CONSULTANT_API_KEY` / header `X-Consultant-Key`. See `app/api/deps/auth.py` and `SETUP.md`. When the env var is **unset**, auth is off (local dev). Member portal routes remain public-by-token.

## Goals

- Only authenticated consultants can call mutating `/api/v1/*` endpoints (except the member portal).
- Board members continue to use **assignment tokens** only (`/api/v1/portal/{token}`) — no login required for MVP pilot.
- Avoid scope creep: no multi-tenant SSO, no RBAC matrix in v1.

## Non-goals (pilot)

- OAuth / SAML for enterprise clients
- Per-evaluation permission grants
- Participant accounts / passwords

## Recommended approach: API key or JWT (consultant-only)

### Option A — Static API key (fastest, ~1–2 days)

| Item | Detail |
|------|--------|
| Mechanism | `X-Consultant-Key: <secret>` on consultant requests |
| Storage | `CONSULTANT_API_KEY` in server env; optional `VITE_CONSULTANT_API_KEY` in UI `.env` (dev only) |
| Enforcement | FastAPI dependency on `evaluations`, `questions`, `reports`, `assignments` routers |
| Portal | **Excluded** — token URLs remain public-by-secret-link |
| Pros | Trivial to implement and test |
| Cons | Single shared secret; rotate manually |

### Option B — JWT login (better pilot, ~1 week)

| Item | Detail |
|------|--------|
| Mechanism | `POST /api/v1/auth/login` → `{ access_token }`; `Authorization: Bearer` on consultant routes |
| Users | Table `consultant_users` (email, password_hash, active) — seed one admin |
| Passwords | `bcrypt` or `argon2` via `passlib` |
| Token | Short-lived access JWT (e.g. 8h) signed with `JWT_SECRET` |
| UI | Login page at `/consultant/login`; store token in `sessionStorage` |
| Pros | Individual accounts, auditable `created_by` on reports |
| Cons | More moving parts |

**Recommendation:** Start with **Option A** for internal pilot; move to **Option B** before client-facing hosting.

## Route policy

| Area | Auth in pilot |
|------|----------------|
| `GET /health` | Public |
| `GET/POST /api/v1/portal/*` | Public (token = credential) |
| All other `/api/v1/*` | Consultant auth required |
| `GET /api/v1/debug/*` | Disabled in production (`DEBUG_ROUTERS=0`) |

## Implementation checklist

1. Add `app/api/deps/auth.py` with `require_consultant()` dependency.
2. Apply dependency at router level for `evaluations`, `questions`, `reports`, `assignments`.
3. Frontend: attach header in `apiRequest()` (`AppLegacy.jsx`).
4. Return `401` with clear message; UI redirect to login (Option B) or settings hint (Option A).
5. Document env vars in `SETUP.md`.
6. Add integration test: portal works without key; `POST /evaluations` returns 401 without key.

## Security notes for pilot

- Use HTTPS in production; never send API keys over plain HTTP.
- CORS: restrict `allow_origins` to known consultant UI host(s) (`app/main.py`).
- Rate-limit portal token endpoints to reduce brute-force risk.
- Mailpit only in dev; production SMTP with SPF/DKIM.
- Rotate `CONSULTANT_API_KEY` / `JWT_SECRET` via deployment secrets manager.

## Dependencies

- Unify responses on `assignment_id` (done) — analytics/reporting assume assignment-scoped data.
- Workflow order fix (done) — reduces misconfigured pilots.

## Estimated effort

| Option | Effort | Risk |
|--------|--------|------|
| A — API key | Small (1–2 days) | Shared secret leakage |
| B — JWT login | Medium (5–7 days) | Auth bugs, session handling |

## Acceptance criteria (pilot-ready auth)

- [ ] Unauthenticated `POST /api/v1/evaluations` returns 401
- [ ] Portal submit still works with valid assignment token and no consultant header
- [ ] Consultant UI sends credential on all non-portal API calls
- [ ] `SETUP.md` documents required env vars
- [ ] At least one integration test covers 401 vs 200
