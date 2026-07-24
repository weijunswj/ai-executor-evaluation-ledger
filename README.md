# AI Executor Evaluation Ledger

Public, controller-owned evidence for evaluating AI coding and operations executors across real project work.

## Summary model scores

This is the primary at-a-glance tracker. Aggregate scores use the complete append-only history in [`evaluations.jsonl`](evaluations.jsonl), not only the 30 runs displayed in [`scorecard.md`](scorecard.md).

| Model | Reasoning level | Formal runs | Average /5 | First-pass acceptance | Safe final state verified | Evidence level |
|---|---|---:|---:|---:|---:|---|
| Xiaomi MiMo 2.5 Pro | Provider default | 3 | 3.49 | 0% | 0/2 applicable | Provisional across mixed tasks |
| Claude Opus 4.8 High | High | 3 | 3.41 | 0% | 3/3 | Provisional |
| GPT-5.6 Sol Medium | Medium | 0 | - | - | - | Formal backfill pending |
| GPT-5.6 Sol High | High | 0 | - | - | - | Formal backfill pending |

## Task-class scorecard

| Model | Reasoning level | Task class | Difficulty | Runs | Average /5 | First-pass acceptance | Confidence |
|---|---|---|---|---:|---:|---:|---|
| Xiaomi MiMo 2.5 Pro | Provider default | Production deployment | High | 1 | 2.25 | 0% | Anecdotal |
| Xiaomi MiMo 2.5 Pro | Provider default | Routine repository change | Low | 1 | 4.60 | 0% | Anecdotal |
| Xiaomi MiMo 2.5 Pro | Provider default | Incident diagnosis | High | 1 | 3.63 | 0% | Anecdotal |
| Claude Opus 4.8 High | High | Complex repository change | High | 3 | 3.41 | 0% | Provisional |

The first two Claude records were corrected after merge to identify the executor configuration as **Claude Opus 4.8 High**. Correction records do not count as additional formal runs. The third comparable run was recorded with the complete model label and observed `high` reasoning level.

## Current task-fit summary

| Model | Approved use | Current restriction |
|---|---|---|
| Xiaomi MiMo 2.5 Pro | Bounded low-risk repository changes; read-only diagnosis and evidence recovery | Tracker writes require controller checks; exact root-cause claims require direct evidence; no autonomous production mutation |
| Claude Opus 4.8 High | Complex repository implementation in isolated branches with strong exact-head evidence | No autonomous acceptance for atomicity, cleanup, durable-state or write-capable paths; a further same-domain repair requires stronger reasoning and another exact-head review |
| GPT-5.6 Sol Medium | Routine implementation, tests, documentation and bounded configuration | No autonomous production mutation |
| GPT-5.6 Sol High | Complex implementation, security/auth repair and production diagnosis | Production operations still require exact gates and controller verification |

Observed MiMo pattern so far:

- strong on narrow mechanical configuration work;
- generally safe about prohibited mutations;
- inconsistent tracker hygiene;
- weaker when exact production diagnosis depends on missing logs;
- not yet approved for autonomous deployment or provider changes.

Observed Claude Opus 4.8 High pattern so far:

- strong revision, test and draft-state evidence;
- consistently respects the no-live-operation boundary;
- implements substantial cross-language changes effectively;
- has required three controller amendment cycles on the same filesystem durability boundary;
- green tests and continuous integration have not been sufficient for independent acceptance.

## Display retention

`evaluations.jsonl` retains the complete sanitised history. In `scorecard.md`, the `Formal evaluated runs` table and `Latest formal evaluations` section show only the newest 30 formal runs, newest first. When run 31 is added, only the oldest displayed row and detailed entry are removed; the underlying ledger record and aggregate history remain intact.

## Purpose

This repository tracks whether an executor produces correct, safe, reviewable and efficient work. Public records use opaque aliases and exclude repository owners, repository names, user names, raw project URLs, provider identifiers, secrets and private operational details.

## Control boundary

- The ChatGPT web controller is the sole routine editor of this ledger.
- Executors being evaluated must not clone, modify, update or rely on this repository.
- Executors may report facts, but they never grade themselves.
- Every score is assigned only after controller verification.
- Public entries are sanitised by construction.
- After every merged ledger update, the controller tells the user the exact appended model, reasoning level, run ID, verdict and score.

## Public-safety CI

Every pull request and push to `main` runs a zero-dependency fail-closed scanner over:

- the complete tracked tree;
- structured JSONL keys and values;
- every line added in every commit after the public-safety baseline.

The scanner rejects common credentials, private keys, emails, user-home paths, repository URLs/slugs, identity fields, provider identifiers, UUIDs and credential-bearing URLs or assignments. CI reduces accidental disclosure risk but does not replace controller review.

## Files

- [`evaluations.jsonl`](evaluations.jsonl) - append-only structured source of truth, subject to privacy redaction.
- [`scorecard.md`](scorecard.md) - rolling summaries and the newest 30 formal-run details.
- [`model-policy.md`](model-policy.md) - current approved, conditional and prohibited uses.
- [`CONTROLLER_POLICY.md`](CONTROLLER_POLICY.md) - mandatory prompt-check, display-retention and user-confirmation workflow.
- [`SCORING_RUBRIC.md`](SCORING_RUBRIC.md) - fixed dimensions, weights and confidence rules.
- [`benchmarks/README.md`](benchmarks/README.md) - regression-detection approach.
- [`scripts/check_public_safety.py`](scripts/check_public_safety.py) - local and CI disclosure gate.

## Review workflow

For every executor output brought to the controller:

1. Verify the actual repository, pull-request and available provider state.
2. Classify the result as accepted, amend, hold or fail.
3. Grade the run using the fixed rubric.
4. Append one immutable JSONL entry or explicit correction entry.
5. Record the exact model and observed reasoning level when exposed.
6. Recalculate the README summary and scorecard.
7. Update the model-use policy when evidence changes the safe operating boundary.
8. Reconcile the applicable private project tracker.
9. Merge the ledger update through required safety checks.
10. Tell the user which model and reasoning level were appended.
11. Only then issue the next executor prompt.

ChatGPT web cannot receive completion webhooks from external executors. The user must bring each completion report to the controller conversation; grading is automatic from that point onward.

## Interpretation

One task-class run is anecdotal. Three comparable runs provide provisional evidence, not a stable baseline. Model-level conclusions require comparable runs grouped by task class, difficulty, reasoning level and tool environment. Mixed-task evidence can inform task fit but cannot establish improvement or regression.
