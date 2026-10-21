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

## Recorded baseline

| Date | Branch / commit | Result |
|---|---|---|
| 2026-10-21 | `groundwork` | 38 passed (27 unit, 11 integration), 0 failed, 0 skipped |

## Known failures

None. Any test that fails from here on is a regression — fix it or record it here
with the reason before merging.

## Not covered

- The React frontend (`cw-board-ui`) has no automated tests.
- Report generation calls OpenAI and is not exercised by the suite.
