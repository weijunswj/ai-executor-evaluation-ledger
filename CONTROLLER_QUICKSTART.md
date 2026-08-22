# Controller Ledger Quickstart

Use this sequence for every executor result.

## One source of truth

The permanent router/index is GitHub issue #142 plus its legacy segment-0. Successor intake segments are bounded operational issues, not lifecycle children.

For every future evaluation:

- read and parse the byte-zero `<!-- ledger-routing:v1 -->` object;
- record `router_revision`, `active_generation`, `active_issue_number`, source watermark and source snapshot;
- post exactly one intake to the declared active target;
- read the created comment back, reread #142, and compare revision/generation/target.

A successful GitHub write is not queued or canonical by itself. A stale-generation comment is `stale_route`, retained and auditable, excluded from source, and never silently pending. Do not fall back to #142 after cutover. Retry only after the stale first comment is deterministically ineligible; an exact processor receipt, not comment status, proves recording.

The direct `.controller-evaluation-intake.json` and `controller/evaluation-*` append route is retired and fail closed. Maintenance-controller branches remain available for unrelated maintenance.

## Required fields

Record the exact public-safe:

- provider and canonical base model;
- run ID;
- reviewed timestamp;
- task class and difficulty;
- verdict and score;
- verified strengths and defects;
- integrity/control flags;
- opaque subject alias.

Never publish repository identities, user identities, raw revisions, provider identifiers, secrets or private operational evidence.

## Summary-table eligibility

Generated model summaries include only models with at least one formal evaluation merged into `main`. Do not add zero-run placeholder rows or advertise planned backfills as formal evidence.

## Zero-pending gate

Once an executor completion report has been presented and controller-reviewed, that result is **ledger-pending** until its controller-owned ledger pull request passes required checks and merges.

Before issuing another executor prompt, the controller must:

1. append every reviewed ledger-pending result;
2. reconcile every applicable private project tracker;
3. merge the ledger update;
4. confirm the appended model, run ID, verdict and score to the user;
5. verify that the reviewed-but-unmerged queue is empty.

When reporting counts, always distinguish:

- **formal runs**: evaluation records already merged into `main`;
- **ledger-pending runs**: reviewed records not yet merged;
- **in-flight runs**: executor work not yet presented for controller review.

Never count ledger-pending or in-flight work as a formal run. If several reports arrive before reconciliation, append all reviewed results in one controller pull request or in sequential controller pull requests before issuing any further executor prompt. The user must not need to remind the controller.

## Web-controller workflow

1. Create or use a controller maintenance branch from current `main`; evaluation append branches are retired.
2. Immediately read #142 and resolve one exact router revision, generation and active issue.
3. Bind the intake and source snapshot to that authority; never silently hardcode #142 after cutover.
4. Post exactly one intake to the declared active target, then read back the exact comment.
5. Reread #142. If revision, generation or target changed, classify the first success as stale/authority-changed, never queued; do not optimistically retry.
6. A retry is permitted only after the stale first comment is deterministically ineligible for canonical admission and duplicate identity handling is fail closed.
7. The `Rebuild ledger views` workflow regenerates `README.md` and `scorecard.md` on the maintenance branch; open a pull request for the router/intake/processor path.
8. Merge only after `Public safety` and receipt/replay validation pass.
9. Fetch `main` after merge and verify exact run IDs, router generation and processor receipt authority.
10. After merge, tell the user:

```text
Ledger appended: <provider> | <canonical-base-model> | <run-id> | <verdict> | <score>/5
```

Do not issue the next executor prompt before the ledger and applicable private project tracker are reconciled.

## Local equivalent

```text
python scripts/rebuild_views.py
python scripts/check_public_safety.py
python scripts/rebuild_views.py --check
```

The complete history remains in `evaluations.jsonl`. Human-readable run displays retain only the newest 30 formal evaluations.
