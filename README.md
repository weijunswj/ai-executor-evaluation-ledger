# AI Executor Evaluation Ledger

Public, controller-owned evidence for evaluating AI coding and operations executors across real project work.

## Current scorecard

This is the primary human-readable tracker. The structured source of truth is [`evaluations.jsonl`](evaluations.jsonl); the expanded historical view is [`scorecard.md`](scorecard.md).

| Model | Task class | Difficulty | Runs | Average /5 | First-pass acceptance | Safe final state verified | Confidence |
|---|---|---|---:|---:|---:|---:|---|
| Xiaomi MiMo 2.5 Pro | Production deployment | High | 1 | 2.25 | 0% | 0% | Anecdotal |

### Current task-fit summary

| Model | Approved use | Current restriction |
|---|---|---|
| Xiaomi MiMo 2.5 Pro | Strictly read-only diagnosis and evidence recovery | No autonomous production mutation |
| Sol Medium | Routine implementation, tests, documentation and bounded configuration | No autonomous production mutation |
| Sol High | Complex implementation, security/auth repair and production diagnosis | Production operations still require exact gates and controller verification |

The controller updates this table after every formally reviewed executor run. No GitHub issue is used as a parallel tracker.

## Purpose

This repository tracks whether an executor produces correct, safe, reviewable and efficient work. Public records use opaque project aliases and exclude repository owners, repository names, user names, raw project URLs, provider identifiers, secrets and private operational details.

## Control boundary

- The ChatGPT web controller is the sole routine editor of this ledger.
- Executors being evaluated must not clone, modify, update or rely on this repository.
- Executors may report facts, but they never grade themselves.
- Every score is assigned only after controller verification.
- Public entries are sanitised by construction.

## Public-safety CI

Every pull request and push to `main` runs a zero-dependency fail-closed scanner over:

- the complete tracked tree;
- structured JSONL keys and values;
- every line added in every commit after the public-safety baseline.

The scanner rejects common credentials, private keys, emails, user-home paths, repository URLs/slugs, identity fields, provider identifiers, UUIDs and credential-bearing URLs or assignments. CI reduces accidental disclosure risk but does not replace controller review.

## Files

- [`evaluations.jsonl`](evaluations.jsonl) - append-only structured source of truth, subject to privacy redaction.
- [`scorecard.md`](scorecard.md) - expanded rolling aggregate and historical trend.
- [`model-policy.md`](model-policy.md) - current approved, conditional and prohibited uses.
- [`CONTROLLER_POLICY.md`](CONTROLLER_POLICY.md) - mandatory review and update workflow.
- [`SCORING_RUBRIC.md`](SCORING_RUBRIC.md) - fixed dimensions, weights and confidence rules.
- [`benchmarks/README.md`](benchmarks/README.md) - regression-detection approach.
- [`scripts/check_public_safety.py`](scripts/check_public_safety.py) - local and CI disclosure gate.

## Review workflow

For every executor output brought to the controller:

1. Verify the actual repository, pull-request and available provider state.
2. Classify the result as accepted, amend, hold or fail.
3. Grade the run using the fixed rubric.
4. Append one immutable JSONL entry.
5. Recalculate the README scorecard and expanded historical view.
6. Update the model-use policy when evidence changes the safe operating boundary.
7. Reconcile the applicable private project tracker.
8. Only then issue the next executor prompt.

ChatGPT web cannot receive completion webhooks from external executors. The user must bring each completion report into the controller conversation; grading is automatic from that point onward.

## Interpretation

One run is anecdotal. Model-level conclusions require comparable runs grouped by task class, difficulty, reasoning mode and tool environment. A decline is recorded as a suspected performance regression only after repeated comparable evidence.