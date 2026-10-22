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
