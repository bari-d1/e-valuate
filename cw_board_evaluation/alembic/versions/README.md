# Alembic versions

## Committed baseline (CI-friendly)

This repo includes **`2fb54b7b8545_baseline_initial_schema.py`**, generated with `--autogenerate` against an **empty** Postgres database so `alembic upgrade head` creates the full schema.

To regenerate a clean autogenerate diff locally (rare), use `scripts/reset_baseline_db.py` to wipe a throwaway DB, then run `alembic revision --autogenerate` with `DATABASE_URL` pointing at that DB.

---

## Why `upgrade head` must have a real baseline

- **`alembic upgrade head` on an empty database** only works if the chain of revisions’ `upgrade()` functions **create every table** (and constraints) your app needs.
- **`alembic stamp head`** only records a revision in `alembic_version`; it **does not** create tables. Use it when the schema already exists and you are adopting Alembic without re-running DDL.

For **CI** (fresh Postgres, empty DB), you want **Option A** below so the first migration is a full **create** from your models.

---

## Option A — Real baseline for greenfield / CI (recommended)

**Goal:** One committed revision that builds the full schema from `app.db.models`. Then every environment (including CI) runs:

```bash
alembic upgrade head
```

**Steps (run once on a developer machine):**

1. Use a **database with no application tables** (new database or drop all `public` tables / recreate schema).

   ```text
   # Example: new DB
   createdb cw_board_eval_baseline
   ```

2. Point Alembic at it and autogenerate:

   ```powershell
   $env:DATABASE_URL = "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/cw_board_eval_baseline"
   alembic revision --autogenerate -m "baseline_initial_schema"
   ```

3. **Review** the new file under `alembic/versions/`:
   - Remove anything that does not belong (e.g. stray drops).
   - Ensure Postgres-only details match what you want in production.

4. **Test from empty DB:**

   ```powershell
   alembic upgrade head
   ```

   Start the app (or run a smoke test) and confirm tables exist and the app runs.

5. **Commit** the revision file to git.

**CI job (conceptual):**

```yaml
# After Postgres service is up and DATABASE_URL points at an empty database:
- run: pip install -r requirements.txt
- run: alembic upgrade head
- run: pytest  # or start API and hit /health
```

---

## Option B — Existing DB already created with `create_all()` / `init_db()`

**Goal:** Stop using `create_all` for that environment **without** re-applying DDL that would fail (tables already exist).

1. Create an **empty** revision (no DDL):

   ```powershell
   alembic revision -m "baseline_existing_db"
   ```

2. Edit the file so `upgrade()` and `downgrade()` are empty (`pass`) **only if** the current DB schema already matches `models.py` exactly.

3. Mark the database as migrated **without** running `upgrade`:

   ```powershell
   alembic stamp head
   ```

From then on, new migrations are normal: `alembic revision --autogenerate -m "..."` and `alembic upgrade head`.

**Important:** Option B does **not** help a **new** empty CI database unless you also adopt **Option A** for the first revision. For CI, either:

- use **Option A**’s baseline migration on empty DB, or  
- run `create_all` in CI **and** `alembic stamp head` to the same revision as production (keeps version table in sync but duplicates two ways to create schema — usually worse than a single baseline migration).

---

## Option C — Hybrid (common in teams)

1. Add a **full** baseline via Option A and commit it.
2. For one legacy database that already had tables: run `alembic stamp <baseline_revision_id>` once so it matches git without running the baseline’s `upgrade()` (only if schema truly matches; otherwise run `upgrade` on a restored copy and fix drift first).

---

## Commands reference

| Command | Effect |
|--------|--------|
| `alembic upgrade head` | Apply all pending migrations’ `upgrade()` |
| `alembic stamp head` | Set `alembic_version` to `head` **without** running migrations |
| `alembic current` | Show revision applied to connected DB |
| `alembic history` | List revision files |

---

## Pitfall: autogenerate against a “dirty” DB

If you run `--autogenerate` against a DB that already has partial or old schema, Alembic emits **deltas** (ALTER/DROP), not a clean baseline. For a **baseline** file, always use an **empty** database (or a dedicated throwaway DB).
