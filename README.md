# AI Executor Evaluation Ledger

Public, controller-owned evidence for evaluating AI coding and operations executors across real project work.

> **Controller sessions:** read [`CONTROLLER_QUICKSTART.md`](CONTROLLER_QUICKSTART.md) before editing. Append one JSONL record; do not hand-edit generated score sections.

<!-- GENERATED:README-SCORES:START -->
## Summary model scores

This is the primary at-a-glance tracker. Aggregate scores use the complete append-only history in [`evaluations.jsonl`](evaluations.jsonl), not only the 30 runs displayed in [`scorecard.md`](scorecard.md).

| Model | Reasoning level | Formal runs | Average /5 | First-pass acceptance | Safe final state verified | Evidence level |
|---|---|---:|---:|---:|---:|---:|
| Claude Opus 4.8 High | High | 3 | 3.41 | 0% | 3/3 applicable | Provisional |
| Claude Opus 4.8 Ultra High | ultra-high | 1 | 3.23 | 0% | 1/1 applicable | Anecdotal |
| Claude Opus 5 | Max | 1 | 3.90 | 0% | 1/1 applicable | Anecdotal |
| Claude Opus 5 | not-exposed | 2 | 4.20 | 50% | 2/2 applicable | Anecdotal |
| Claude Opus 5 Max | Max | 3 | 3.39 | 0% | 3/3 applicable | Provisional |
| DeepSeek V4 Pro | High | 1 | 4.14 | 100% | 1/1 applicable | Anecdotal |
| DeepSeek V4 Pro | Not exposed | 12 | 4.02 | 42% | 12/12 applicable | Useful operating baseline |
| GPT-5.6 Sol | Not exposed | 5 | 4.14 | 20% | 5/5 applicable | Provisional across mixed tasks |
| MiMo 2.5 Pro | Default | 19 | 3.51 | 5% | 9/18 applicable | Useful operating baseline |

## Task-class scorecard

| Model | Reasoning level | Task class | Difficulty | Runs | Average /5 | First-pass acceptance | Confidence |
|---|---|---|---|---:|---:|---:|---|
| Claude Opus 4.8 High | High | Complex Repository Change | High | 3 | 3.41 | 0% | Provisional |
| Claude Opus 4.8 Ultra High | ultra-high | Complex Repository Change | High | 1 | 3.23 | 0% | Anecdotal |
| Claude Opus 5 | Max | Complex Repository Change | High | 1 | 3.90 | 0% | Anecdotal |
| Claude Opus 5 | not-exposed | Architecture Proposal | High | 1 | 4.35 | 100% | Anecdotal |
| Claude Opus 5 | not-exposed | Complex Repository Change | High | 1 | 4.05 | 0% | Anecdotal |
| Claude Opus 5 Max | Max | Complex Repository Change | High | 3 | 3.39 | 0% | Provisional |
| DeepSeek V4 Pro | High | Architecture Proposal | High | 1 | 4.14 | 100% | Anecdotal |
| DeepSeek V4 Pro | Not exposed | Complex Repository Change | High | 1 | 2.75 | 0% | Anecdotal |
| DeepSeek V4 Pro | Not exposed | Hosted Product Uat | High | 1 | 3.15 | 0% | Anecdotal |
| DeepSeek V4 Pro | Not exposed | Incident Diagnosis | High | 1 | 4.80 | 100% | Anecdotal |
| DeepSeek V4 Pro | Not exposed | Production Deployment | High | 1 | 4.55 | 100% | Anecdotal |
| DeepSeek V4 Pro | Not exposed | Production Operations | High | 3 | 4.20 | 67% | Provisional |
| DeepSeek V4 Pro | Not exposed | Research | High | 4 | 4.12 | 25% | Provisional |
| DeepSeek V4 Pro | Not exposed | Security Architecture Audit | High | 1 | 3.85 | 0% | Anecdotal |
| GPT-5.6 Sol | Not exposed | Architecture Review | High | 1 | 4.24 | 0% | Anecdotal |
| GPT-5.6 Sol | Not exposed | Complex Repository Change | High | 2 | 4.44 | 50% | Anecdotal |
| GPT-5.6 Sol | Not exposed | Security Remediation | High | 2 | 3.80 | 0% | Anecdotal |
| MiMo 2.5 Pro | Default | Architecture Proposal | High | 1 | 4.40 | 100% | Anecdotal |
| MiMo 2.5 Pro | Default | Complex Repository Change | High | 2 | 3.23 | 0% | Anecdotal |
| MiMo 2.5 Pro | Default | Complex Repository Change | Medium | 1 | 3.26 | 0% | Anecdotal |
| MiMo 2.5 Pro | Default | Incident Diagnosis | High | 3 | 3.47 | 0% | Provisional |
| MiMo 2.5 Pro | Default | Production Deployment | High | 1 | 2.25 | 0% | Anecdotal |
| MiMo 2.5 Pro | Default | Provider Operation | High | 5 | 3.55 | 0% | Provisional |
| MiMo 2.5 Pro | Default | Routine Repository Change | Low | 1 | 4.60 | 0% | Anecdotal |
| MiMo 2.5 Pro | Default | Security Remediation | High | 5 | 3.50 | 0% | Provisional |

These tables are generated from the append-only ledger. Do not edit them manually.
<!-- GENERATED:README-SCORES:END -->

## Current task-fit summary

| Model | Approved use | Current restriction |
|---|---|---|
| Xiaomi MiMo 2.5 Pro | Bounded low-risk repository changes; read-only diagnosis and evidence recovery | Tracker writes require controller checks; exact root-cause claims require direct evidence; no autonomous production mutation |
| Claude Opus 4.8 High | Complex repository implementation in isolated branches with strong exact-head evidence | No autonomous acceptance for atomicity, cleanup, durable-state or write-capable paths; a further same-domain repair requires stronger reasoning and another exact-head review |
| Claude Opus 4.8 Ultra High | Narrow high-risk remediation in isolated draft branches with explicit negative tests | No autonomous acceptance for durable-state or write-capable paths; a same-domain P1 survived and the next repair requires Max reasoning plus exact-head review |
| GPT-5.6 Sol Medium | Routine implementation, tests, documentation and bounded configuration | No autonomous production mutation |
| GPT-5.6 Sol High | Complex implementation, security/auth repair and production diagnosis | Production operations still require exact gates and controller verification |

Observed MiMo pattern so far:

- strong on narrow mechanical repository configuration;
- reasonably safe at respecting explicit mutation prohibitions;
- inconsistent in tracker-body quality;
- less reliable when exact operational diagnosis requires unavailable logs;
- unsuitable for autonomous production mutation at present.

Observed Claude Opus 4.8 High pattern so far:

- strong revision, test and draft-state evidence;
- consistently respects the no-live-operation boundary;
- implements substantial cross-language changes effectively;
- has required three controller amendment cycles on the same filesystem durability boundary;
- green tests and continuous integration have not been sufficient for independent acceptance.

Observed Claude Opus 4.8 Ultra High pattern so far:

- closed the specifically named silent-unlink defect with a clear state model and focused tests;
- preserved exact-head evidence, draft state and zero live-system actions;
- still missed ledger-persistence failure after package publication;
- left a same-domain P1 that can bypass durable single-use state;
- one run is anecdotal and does not justify autonomous acceptance.

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

One task-class run is anecdotal. Three comparable runs provide provisional evidence, not a stable baseline. Model-level conclusions require comparable runs grouped by task class, difficulty, reasoning level and tool environment. Mixed-task evidence can inform task fit but cannot establish improvement or regression.
