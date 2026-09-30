# Starting the application

Quick reference — **PostgreSQL must be running** before the API starts (the app stores all data there).

| Step | What | Command |
|------|------|---------|
| 0 | Start PostgreSQL | Your install (Windows service, Docker, etc.) — database `cw_board_eval` |
| 1 | First-time DB setup | See [First-time database setup](#first-time-database-setup) below |
| 2 | **Terminal 1 — API** | `python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000` (from activated venv) |
| 3 | **Terminal 2 — UI** | `npm run dev` (in `cw-board-ui`) |
| 4 | Open app | http://127.0.0.1:5173/consultant |

For a short overview and repo layout, see the [root README.md](../README.md). **This file** is the detailed run guide.

---

## Prerequisites (one-time)

1. **PostgreSQL** running with database `cw_board_eval`
2. **Python 3.14** — use project venv: `cw_board_evaluation\.venv314`
3. **Node.js** — for the React UI (`npm` on PATH)
4. Backend `.env` with `DATABASE_URL` (see `.env` example below)
5. Frontend `.env` with API URLs (see below)

### First-time database setup

```powershell
cd d:\Projects\ProjectBoardEvaluationLatest\cw_board_evaluation
.\.venv314\Scripts\Activate.ps1
pip install -r requirements.txt

alembic upgrade head
python scripts\seed_reference_data.py
python scripts\seed_demo_environment.py eval-002
python scripts\seed_demo_environment.py eval-demo-001
```

The consultant UI defaults to evaluation id **`eval-002`** (EMOK Express). Seeding `eval-002` avoids `Evaluation not found` errors.

---

## Every day: start backend + frontend

Use **two terminals**.

### Terminal 1 — Backend (FastAPI)

```powershell
cd d:\Projects\ProjectBoardEvaluationLatest\cw_board_evaluation
.\.venv314\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

If you see `uvicorn : The term 'uvicorn' is not recognized`, either activate the venv first (command above) or run without activating:

```powershell
.\.venv314\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

On another machine the venv folder may be `.venv` instead of `.venv314` — use whichever exists under `cw_board_evaluation`.

Check:

- Health: http://127.0.0.1:8000/health → `{"status":"ok"}`
- API docs: http://127.0.0.1:8000/docs

### Terminal 2 — Frontend (Vite / React)

```powershell
cd d:\Projects\ProjectBoardEvaluationLatest\cw-board-ui
npm.cmd run dev
```

Open: http://127.0.0.1:5173/consultant

---

## Environment files

**Backend** (`cw_board_evaluation\.env`):

```env
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/cw_board_eval
PARTICIPANT_PORTAL_BASE_URL=http://localhost:5173

# Optional — when set, consultant API routes require header X-Consultant-Key (same value).
# Leave unset for local dev with no auth. Member portal (/api/v1/portal/*) is never keyed.
# CONSULTANT_API_KEY=change-me-to-a-long-random-string
```

**Frontend** (`cw-board-ui\.env`):

```env
VITE_API_BASE=http://127.0.0.1:8000
VITE_API_BASE_URL=http://127.0.0.1:8000

# Required only if backend CONSULTANT_API_KEY is set (must match).
# VITE_CONSULTANT_API_KEY=change-me-to-a-long-random-string
```

---

## Optional: Mailpit (invite emails)

```powershell
cd d:\Projects\ProjectBoardEvaluationLatest\cw_board_evaluation
docker compose -f docker-compose.mailpit.yml up
```

SMTP on `localhost:1025` (if Docker is installed).

---

## Reseed demo data

```powershell
cd d:\Projects\ProjectBoardEvaluationLatest\cw_board_evaluation
.\.venv314\Scripts\python.exe scripts\seed_demo_environment.py eval-002
```

---

## Troubleshooting

| Problem | Fix |
|--------|-----|
| `Evaluation not found: eval-002` | Run `python scripts\seed_demo_environment.py eval-002` |
| `python` not found | Use full path or add Python 3.14 to PATH |
| `uvicorn` not recognized | Activate venv first, or use `.\.venv314\Scripts\python.exe -m uvicorn ...` |
| `npm` not found | Install Node.js; restart terminal |
| `npm` / scripts disabled (PowerShell) | Use `npm.cmd run dev` instead of `npm run dev`, or `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| Port 8000 in use | Stop other uvicorn or change port |
| UI shows **Failed to fetch** | Backend not running or crashed — see *Failed to fetch* section below |
| Old broken `.venv` | Use `.venv314` as documented |

---

## Integration tests (optional)

Requires PostgreSQL and a test database (default: `cw_board_eval_test` on localhost):

```powershell
$env:RUN_INTEGRATION_TESTS="1"
$env:DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/cw_board_eval_test"
.\.venv314\Scripts\python.exe -m pytest tests/ -v -m integration
```

Unit tests run without Postgres:

```powershell
.\.venv314\Scripts\python.exe -m pytest tests/ -v -m "not integration"
```

---

## Failed to fetch (UI cannot reach API)

**Failed to fetch** in the browser means the React app could not open an HTTP connection to the API at all (not the same as a 401/500 JSON error).

Checklist:

1. **Backend terminal still running?** You should see `Uvicorn running on http://127.0.0.1:8000`. If that window was closed or shows a traceback, restart:
   ```powershell
   cd cw_board_evaluation
   .\.venv314\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```
2. **Health in browser:** http://127.0.0.1:8000/health → `{"status":"ok"}`
3. **List evaluations in PowerShell:**
   ```powershell
   Invoke-RestMethod http://127.0.0.1:8000/api/v1/evaluations
   ```
4. **PostgreSQL running?** Create/list need the DB. If Postgres is stopped, the API may crash on first request — watch the **uvicorn terminal** for errors mentioning `connection refused` or `cw_board_eval`.
5. **Frontend `.env`:** `VITE_API_BASE_URL=http://127.0.0.1:8000` in `cw-board-ui\.env`. Restart `npm.cmd run dev` after changing `.env`.
6. **Browser DevTools → Network:** click List Evaluations; see if the request to `127.0.0.1:8000` is red (failed) or returns a status code.

### Where logs are

| What | Where |
|------|--------|
| API request/errors | **Terminal running uvicorn** (stdout). There is no log file by default. |
| React / Vite | **Terminal running npm** |
| Browser fetch details | **DevTools → Console / Network** (F12) |
| PostgreSQL | Your Postgres install logs (not this app) |

### Verify create evaluation manually

With backend + Postgres up:

```powershell
$body = @{
  evaluation_id = "eval-003"
  tenant_name = "Test Client"
  sector = "insurance"
  year = 2025
  regulators = @("NAICOM")
} | ConvertTo-Json

Invoke-RestMethod -Method POST -Uri "http://127.0.0.1:8000/api/v1/evaluations" `
  -ContentType "application/json" -Body $body

Invoke-RestMethod "http://127.0.0.1:8000/api/v1/evaluations"
```

You should see `eval-003` in the list. If POST works but the UI fails, the problem is browser/CORS/env; if POST fails here too, check Postgres and the uvicorn terminal.

---

## Member portal links (hub vs assignment)

Two token types — do not mix them up:

| Name | API field | Opens | When available |
|------|-----------|--------|----------------|
| **Hub token** | `hub_token` (DB: `participants.access_token`) | `http://localhost:5173/member/hub/{hub_token}` | Right after invite |
| **Assignment token** | `assignment_token` (DB: `assessment_assignments.access_token`) | `http://localhost:5173/member/{token}/questions` | After **Generate assignments** |

Consultant API notes:

- `hub_url` / `hub_token` — personal task hub (all questionnaires for that person).
- `first_assignment_portal_url` — first task questionnaire URL.
- `portal_url` — **deprecated** alias for `first_assignment_portal_url` only (never the hub).

Workflow:

1. **Invite** — register participants (email optional). Copy **hub** links from invite results or Participants list.
2. **Generate assignments** — creates task tokens; use **Send email** on generate or **Resend links** on Participants / Tracks.
3. Members open **hub** to pick tasks, or a **task** link for one questionnaire.

If a member opens a hub token on a task URL (`/member/{token}/questions`), the app redirects to `/member/hub/{token}`.
