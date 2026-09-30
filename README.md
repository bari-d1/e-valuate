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
