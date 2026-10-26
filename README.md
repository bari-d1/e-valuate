# e-valuate

Board evaluation app: FastAPI backend (`cw_board_evaluation/`) and React + Vite frontend (`cw-board-ui/`).

## Run the app (macOS)

```bash
./dev.sh
```

Open http://127.0.0.1:5173/consultant. Ctrl+C stops everything.

`dev.sh` starts the backend on port 8000 and the frontend on port 5173, and applies any pending database migrations. On first run it also creates the Python environment (`cw_board_evaluation/.venv-mac`) and installs frontend dependencies.

## First-time setup

Requires Python 3.14, Node.js and PostgreSQL (`brew install python@3.14 node postgresql@18`).

1. Start Postgres: `brew services start postgresql@18`
2. Create `cw_board_evaluation/.env` with `DATABASE_URL`, `OPENAI_API_KEY` and the email settings. Never commit this file.
3. Create the database user and database named in `DATABASE_URL`, for example:
   ```bash
   psql -d postgres -c "CREATE ROLE postgres LOGIN CREATEDB PASSWORD '<password>';"
   createdb -O postgres cw_board_eval
   ```
4. Run `./dev.sh` once so it creates the Python environment and runs migrations, then stop it with Ctrl+C.
5. Seed demo data:
   ```bash
   cd cw_board_evaluation
   .venv-mac/bin/python scripts/seed_reference_data.py
   .venv-mac/bin/python scripts/seed_demo_environment.py eval-002
   ```
   The consultant UI opens evaluation `eval-002` by default.

## Windows

See [cw_board_evaluation/SETUP.md](cw_board_evaluation/SETUP.md).

## Test baseline

Recorded 2026-10-22 on branch `chore/groundwork` (base `22b5392`), Python 3.14.5, PostgreSQL 18.

| Run | Passed | Failed | Skipped |
|---|---|---|---|
| Default: `pytest` from `cw_board_evaluation/` | 27 | 0 | 11 |
| With integration tests: `RUN_INTEGRATION_TESTS=1` | 38 | 0 | 0 |

The 11 tests skipped by default are the integration tests (marker `integration`); they only run when `RUN_INTEGRATION_TESTS=1`.

**Known failures:** none. Any failing test from here on is a regression.

**Warning before running integration tests:** they drop and recreate every table in the database named by `DATABASE_URL`. `app/api/questions.py` and `app/util/initialiseLLM.py` load `cw_board_evaluation/.env` with `override=True`, which replaces a `DATABASE_URL` you set on the command line with the one in `.env`. If `.env` points at your dev database, the integration tests will wipe it. The baseline above was run from a checkout with no `.env`:

```bash
createdb -h localhost cw_board_eval_test   # once
RUN_INTEGRATION_TESTS=1 \
DATABASE_URL=postgresql+psycopg://localhost:5432/cw_board_eval_test \
.venv-mac/bin/python -m pytest -q
```

## Smoke test baseline

Recorded 2026-10-22 on branch `chore/groundwork` (base `22b5392`). Fresh database migrated to head and seeded, backend and frontend started as `dev.sh` does, then the journey was driven in headless Chrome. OpenAI key configured.

**Seeding:** `seed_demo_environment.py eval-002` on its own creates the evaluation and questions but **no tracks, tasks or responses** ("template missing"). It needs `seed_reference_data.py` to run first, as in First-time setup above. In that order: 12 participants, 10 questions, 28 tasks, 86 demo answers.

### Consultant

| Step | Result |
|---|---|
| List evaluations | Works: `eval-002` listed |
| Open the demo evaluation (Select) | Works |
| Participants | Works: 12 shown |
| Questions | Works: 10 shown |
| Tracks and assignments | Works: 3 active tracks, 28 tasks (10 completed, 18 not started) |
| Responses | Works: 86 rows, CSV/Excel download buttons present |
| Generate report | **Works only via in-app navigation.** Opening `/consultant/analysis/report` directly or refreshing it leaves *Generate + Load Latest* disabled with "Add questions first." (the check uses questions held in memory, filled by visiting Questions first). Reached through the sidebar (Questions, then Report) it generated the AI report. |
| Export DOCX | Works: valid `.docx` downloaded (~38 KB) |

Every consultant page logs `404 GET /api/v1/evaluations/{id}/report` until a report exists (lookup for a latest report; harmless but noisy).

### Member

| Step | Result |
|---|---|
| Open invite link (hub) | **Breaks on a fresh checkout:** "Could not open hub: Unexpected token '<' … is not valid JSON". `src/api/portalApi.js` uses `VITE_API_BASE_URL` (default empty), so requests go to the Vite server, which returns HTML; there is no Vite proxy. Works once `VITE_API_BASE_URL=http://127.0.0.1:8000` is set (an untracked `cw-board-ui/.env` does this on the original dev machine; it is not in the repo or this README). |
| Hub | Works (with the variable set): 2 tasks, one completed, one to do |
| Answer questions | Works: 10/10 answered (8 ratings, 2 comments) |
| Submit | Works: task marked `responded` on the server |
| Thank-you page | Works |
