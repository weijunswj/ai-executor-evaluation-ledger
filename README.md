# AI Executor Evaluation Ledger

Public, controller-owned evidence for evaluating AI coding and operations executors across real project work.

> **Controller sessions:** read [`CONTROLLER_QUICKSTART.md`](CONTROLLER_QUICKSTART.md) before editing. Append one JSONL record; do not hand-edit generated score sections.

<!-- GENERATED:README-SCORES:START -->
## Summary model scores

This is the primary at-a-glance tracker. Aggregate scores use the complete append-only history in [`evaluations.jsonl`](evaluations.jsonl), not only the 30 runs displayed in [`scorecard.md`](scorecard.md).

| Model | Reasoning level | Formal runs | Average /5 | First-pass acceptance | Safe final state verified | Evidence level |
|---|---|---:|---:|---:|---:|---:|
| Claude Opus 4.8 High | High | 2 | 3.40 | 0% | 2/2 applicable | Anecdotal |
| GPT-5.6 Sol Medium | Medium | 0 | - | - | - | Formal backfill pending |
| GPT-5.6 Sol High | High | 0 | - | - | - | Formal backfill pending |
| MiMo 2.5 Pro | Provider default | 3 | 3.49 | 0% | 0/2 applicable | Provisional across mixed tasks |

## Task-class scorecard

| Model | Reasoning level | Task class | Difficulty | Runs | Average /5 | First-pass acceptance | Confidence |
|---|---|---|---|---:|---:|---:|---|
| Claude Opus 4.8 High | High | Complex Repository Change | High | 2 | 3.40 | 0% | Anecdotal |
| MiMo 2.5 Pro | Provider default | Incident Diagnosis | High | 1 | 3.63 | 0% | Anecdotal |
| MiMo 2.5 Pro | Provider default | Production Deployment | High | 1 | 2.25 | 0% | Anecdotal |
| MiMo 2.5 Pro | Provider default | Routine Repository Change | Low | 1 | 4.60 | 0% | Anecdotal |

These tables are generated from the append-only ledger. Do not edit them manually.
<!-- GENERATED:README-SCORES:END -->

## Current task-fit summary

| Model | Approved use | Current restriction |
|---|---|---|
| Xiaomi MiMo 2.5 Pro | Bounded low-risk repository changes; read-only diagnosis and evidence recovery | Tracker writes require controller checks; exact root-cause claims require direct evidence; no autonomous production mutation |
| Claude Opus 4.8 High | Complex repository implementation in isolated branches with strong evidence | No autonomous acceptance for atomicity-sensitive or write-capable paths; exact-head review and amendment convergence required |
| GPT-5.6 Sol Medium | Routine implementation, tests, documentation and bounded configuration | No autonomous production mutation |
| GPT-5.6 Sol High | Complex implementation, security/auth repair and production diagnosis | Production operations still require exact gates and controller verification |

Observed MiMo pattern so far:

- strong on narrow mechanical configuration work;
- generally safe about prohibited mutations;
- inconsistent tracker hygiene;
- weaker when exact production diagnosis depends on missing logs;
- not yet approved for autonomous deployment or provider changes.

## Display retention

`evaluations.jsonl` retains the complete sanitised history. In `scorecard.md`, the `Formal evaluated runs` table and `Latest formal evaluations` section show only the newest 30 formal runs, newest first. When run 31 is added, only the oldest displayed row and detailed entry are removed; the underlying ledger record and aggregate history remain intact.

## Purpose

This repository tracks whether an executor produces correct, safe, reviewable and efficient work. Public records use opaque project aliases and exclude repository owners, repository names, user names, raw project URLs, provider identifiers, secrets and private operational details.

## Control boundary

- The ChatGPT web controller is the sole routine editor of this ledger.
- Executors being evaluated must not clone, modify, update or rely on this repository.
- Executors may report facts, but they never grade themselves.
- Every score is assigned only after controller verification.
- Public entries are sanitised by construction.
- After every merged ledger update, the controller tells the user the exact appended model, reasoning level, run ID, verdict and score.

## Public-safety CI

Every pull request and push to `main` runs fail-closed checks over:

- the complete tracked tree;
- structured JSONL keys and values;
- every line added in every commit after the public-safety baseline;
- append-only evaluation history relative to the pull-request base;
- deterministic README and scorecard generation.

The scanner rejects common credentials, private keys, emails, user-home paths, repository URLs/slugs, identity fields, provider identifiers, UUIDs and credential-bearing URLs or assignments. CI reduces accidental disclosure risk but does not replace controller review.

## Files

- [`CONTROLLER_QUICKSTART.md`](CONTROLLER_QUICKSTART.md) - mandatory minimal workflow for web-controller sessions.
- [`evaluations.jsonl`](evaluations.jsonl) - append-only structured source of truth, subject to privacy redaction.
- [`scorecard.md`](scorecard.md) - generated rolling summaries and newest 30 formal-run details.
- [`model-policy.md`](model-policy.md) - current approved, conditional and prohibited uses.
- [`CONTROLLER_POLICY.md`](CONTROLLER_POLICY.md) - full mandatory prompt-check, retention and user-confirmation policy.
- [`SCORING_RUBRIC.md`](SCORING_RUBRIC.md) - fixed dimensions, weights and confidence rules.
- [`benchmarks/README.md`](benchmarks/README.md) - regression-detection approach.
- [`scripts/rebuild_views.py`](scripts/rebuild_views.py) - deterministic README and scorecard generator and validator.
- [`scripts/check_public_safety.py`](scripts/check_public_safety.py) - local and CI disclosure gate.

## Review workflow

For every executor output brought to the controller:

1. Verify the actual repository, pull-request and available provider state.
2. Classify the result as accepted, amend, hold or fail.
3. Grade the run using the fixed rubric.
4. Append one immutable JSONL entry or explicit correction entry.
5. Record the exact model and observed reasoning level when exposed.
6. Let the controller-branch workflow regenerate the README and scorecard.
7. Update the model-use policy when evidence changes the safe operating boundary.
8. Reconcile the applicable private project tracker.
9. Merge the ledger update through required safety checks.
10. Tell the user which model and reasoning level were appended.
11. Only then issue the next executor prompt.

ChatGPT web cannot receive completion webhooks from external executors. The user must bring each completion report to the controller conversation; grading is automatic from that point onward.

## Interpretation

One task-class run is anecdotal. Model-level conclusions require comparable runs grouped by task class, difficulty, reasoning level and tool environment. Mixed-task evidence can inform task fit but cannot establish improvement or regression.
