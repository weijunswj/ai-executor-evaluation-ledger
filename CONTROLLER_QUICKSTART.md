# Controller Ledger Quickstart

Use this sequence for every executor result.

## One source of truth

Append exactly one new JSON object as one new final line in `evaluations.jsonl`.

Do not:

- rewrite or delete an existing evaluation line;
- replace the whole JSONL file with a partial copy;
- edit the generated score tables or detailed-run sections by hand;
- shorten `GPT-5.6 Sol Medium` or `GPT-5.6 Sol High`;
- guess a reasoning level that the provider did not expose;
- instruct the evaluated executor to touch this repository.

## Required fields

Record the exact public-safe:

- model label;
- observed reasoning level, or `not-exposed`;
- run ID;
- reviewed timestamp;
- task class and difficulty;
- verdict and score;
- verified strengths and defects;
- integrity/control flags;
- opaque subject alias.

Never publish repository identities, user identities, raw revisions, provider identifiers, secrets or private operational evidence.

## Summary-table eligibility

Generated model summaries include only model-and-reasoning groups with at least one formal evaluation merged into `main`. Do not add zero-run placeholder rows or advertise planned backfills as formal evidence.

## Zero-pending gate

Once an executor completion report has been presented and controller-reviewed, that result is **ledger-pending** until its controller-owned ledger pull request passes required checks and merges.

Before issuing another executor prompt, the controller must:

1. append every reviewed ledger-pending result;
2. reconcile every applicable private project tracker;
3. merge the ledger update;
4. confirm the appended model, reasoning level, run ID, verdict and score to the user;
5. verify that the reviewed-but-unmerged queue is empty.

When reporting counts, always distinguish:

- **formal runs**: evaluation records already merged into `main`;
- **ledger-pending runs**: reviewed records not yet merged;
- **in-flight runs**: executor work not yet presented for controller review.

Never count ledger-pending or in-flight work as a formal run. If several reports arrive before reconciliation, append all reviewed results in one controller pull request or in sequential controller pull requests before issuing any further executor prompt. The user must not need to remind the controller.

## Web-controller workflow

1. Create a branch named `controller/ledger-<short-purpose>` from current `main`.
2. Append the new JSONL line only, or append every reviewed ledger-pending line when reconciling a backlog.
3. The `Rebuild ledger views` workflow regenerates `README.md` and `scorecard.md` on the controller branch.
4. Update `model-policy.md` only when the evidence changes the safe task boundary.
5. Open a pull request.
6. Merge only after `Public safety` passes. It verifies disclosure safety, append-only JSONL and generated-view consistency.
7. Fetch `main` after merge and verify that the expected run IDs appear and the formal-run count increased by the number of appended evaluation records.
8. After merge, tell the user:

```text
Ledger appended: <model> | reasoning: <level-or-not-exposed> | <run-id> | <verdict> | <score>/5
```

Do not issue the next executor prompt before the ledger and applicable private project tracker are reconciled.

## Local equivalent

```text
python scripts/rebuild_views.py
python scripts/check_public_safety.py
python scripts/rebuild_views.py --check
```

The complete history remains in `evaluations.jsonl`. Human-readable run displays retain only the newest 30 formal evaluations.

## Scheduled-review submission

For executor runs eligible for the scheduled batch reviewer:

1. Create one private GitHub issue in the configured intake repository (not this public ledger).
2. Use the review-job JSON schema (`schema/review-job.schema.json`).
3. The issue body must contain only the structured JSON — no free-text narrative.
4. Label the issue `pending-review`.
5. The scheduled reviewer will discover, freeze, and review it in the next batch.
6. The private intake repository is not configured in this public repository.

Never place private repository identities, source URLs, file paths, user identities, or secrets in the public ledger. The private intake issue may contain real source references; the public batch manifest and results must not.
