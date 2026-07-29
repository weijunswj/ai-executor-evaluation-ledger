# Source Watch Operator Prompt Instructions

> **Operating instructions for the connected ChatGPT scheduled task to execute Source Watch ledger updates via GitHub Actions.**

## Workflow Steps

1. **State Discovery:**
   - Fetch open draft PRs on `weijunswj/ai-executor-evaluation-ledger`.
   - Inspect PR body for byte-zero ownership marker `<!-- ledger-source-watch:v1 -->`.
   - Read embedded JSON metadata (`mode`, `base_sha`, `expected_head_sha`, `mutable_state`, `review_freeze_state`).

2. **Intake Processing:**
   - Fetch and paginate comments on issue `#142`.
   - Execute `scripts/processor/intake_parser.py` on candidate comments.
   - Separate admitted evaluations from terminal dispositions (`already_recorded`, `duplicate`, `malformed`, `owner_withdrawn`).

3. **Plan Evaluation:**
   - Run `SourceWatchPlanner` from `scripts/processor/source_watch.py`.
   - If action is `UPDATE_EXISTING_PR`: append batch to existing PR branch.
   - If action is `CREATE_NEW_DRAFT_PR`: create new branch `gemini/ledger-integrated-processor-v1`, open draft PR with title `Implement integrated ledger Source Watch processor` and header `<!-- ledger-source-watch:v1 -->`.
   - If action is any `REFUSE_*` or `NO_WORK`: stop without mutating git state.

4. **Output Generation & Validation:**
   - Run `scripts/rebuild_views.py` to regenerate `README.md`, `scorecard.md`, and `analysis/model-recommendation.json`.
   - Run `python -m unittest discover -s tests`.
   - Verify byte-for-byte idempotency.

5. **Post-Merge Execution:**
   - Upon canonical merge to `main`, trigger `.github/workflows/post-merge-cleanup.yml`.
   - Post-merge cleanup deletes verified `#142` comments and writes tracked cleanup receipts (`ledger/receipts/cleanup/<batch-id>.json`).
