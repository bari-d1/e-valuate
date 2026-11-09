# Testing

## Running the tests

From `cw_board_evaluation/`:

```bash
# Unit tests only (no database needed)
.venv-mac/bin/python -m pytest -q

# Everything, including integration tests (needs PostgreSQL)
createdb -h localhost -U postgres cw_board_eval_test   # once
RUN_INTEGRATION_TESTS=1 \
DATABASE_URL="postgresql+psycopg://postgres:<password>@localhost:5432/cw_board_eval_test" \
.venv-mac/bin/python -m pytest -q
```

**Integration tests drop and recreate every table.** They refuse to run unless the
database name ends in `_test`, so they cannot touch `cw_board_eval` (dev data).

## End-to-end smoke test

With the app running (`../dev.sh`), from `cw_board_evaluation/`:

```bash
.venv-mac/bin/python scripts/e2e_smoke.py
```

It creates an evaluation, adds questions, invites two people, generates tasks, submits one
director's form through the portal, and checks the report is refused because the evaluation
has no completed analysis (reports are built only from approved findings).
Each run adds a new "E2E Test Plc" evaluation to the app's database.

## Recorded baseline

| Date | Branch / commit | Result |
|---|---|---|
| 2026-10-21 | `groundwork` | 38 passed (27 unit, 11 integration), 0 failed, 0 skipped |
| 2026-10-21 | `groundwork`, fresh clone | `./dev.sh` set up and seeded an empty database; `e2e_smoke.py` passed |
| 2026-10-27 | `feature/question-bank` | 340 passed (unit and integration), 0 failed, 0 skipped |
| 2026-10-27 | `feature/assembly` | 382 passed (unit and integration), 0 failed, 0 skipped |
| 2026-10-27 | `fix/kestrel-qa` | 386 passed (unit and integration), 0 failed, 0 skipped |
| 2026-10-28 | `feature/consultant-review` | 402 passed (unit and integration), 0 failed, 0 skipped |
| 2026-10-28 | `feature/participant-portal` | 416 passed (unit and integration), 0 failed, 0 skipped |
| 2026-10-28 | `feature/tracking-reminders` | 433 passed (unit and integration), 0 failed, 0 skipped |
| 2026-10-28 | `feature/analysis` | 451 passed (unit and integration), 0 failed, 0 skipped |
| 2026-11-06 | `fix/practice-gap` | 453 passed (unit and integration), 0 failed, 0 skipped |
| 2026-11-06 | `fix/configurable-thresholds` | 464 passed (unit and integration), 0 failed, 0 skipped |
| 2026-11-06 | `fix/evidence-required` | 467 passed (unit and integration), 0 failed, 0 skipped |
| 2026-11-06 | `fix/report-from-findings` | 472 passed (unit and integration), 0 failed, 0 skipped |

## Known failures

None. Any test that fails from here on is a regression — fix it or record it here
with the reason before merging.

## Not covered

- The React frontend (`cw-board-ui`) has no automated tests.
- `e2e_smoke.py` uses the older questionnaire, so it only checks the report is refused without a completed
  analysis. Reports and the Word file are covered by `tests/test_reporting.py` (no OpenAI calls).
