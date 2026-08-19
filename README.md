# AI Executor Evaluation Ledger

Public, controller-owned evidence for evaluating AI coding and operations executors across real project work.
Used in conjunction with [LLM WEB CUSTOM INSTRUCTIONS SET](https://github.com/weijunswj/Custom-Instruction-Framework-For-Web-based-LLMs/blob/main/CUSTOM_INSTRUCTIONS.md).

> **Controller sessions:** read [`CONTROLLER_QUICKSTART.md`](CONTROLLER_QUICKSTART.md) before editing. Append one JSONL record; do not hand-edit generated score sections.

<!-- GENERATED:README-SCORES:START -->
## AI Model Recommendations & Operational Guidance

**Recorded comparable evidence:** 86 runs | **Queued comparable evidence:** 0 runs | **Available comparable evidence:** 86 runs

### Tested Model Summary & Like-for-Like Analysis

- **Claude Opus 5**: 14 recorded, 0 queued, 13 independent subject(s), 0 exact matched cohort(s); 14 recorded run(s) excluded for unknown exact dimensions; like-for-like score: **not available**.
- **GPT-5.6 Luna**: 55 recorded, 0 queued, 32 independent subject(s), 0 exact matched cohort(s); 55 recorded run(s) excluded for unknown exact dimensions; like-for-like score: **not available**.
- **GPT-5.6 Sol**: 17 recorded, 0 queued, 13 independent subject(s), 0 exact matched cohort(s); 17 recorded run(s) excluded for unknown exact dimensions; like-for-like score: **not available**.

> [!NOTE]
> No strongest model is declared unless exact matched coverage and task mix meet the published threshold. Status: `insufficient_comparable_evidence`. Queued evidence is provisional and excluded from official score comparison.

## Summary model scores

This is the primary at-a-glance tracker. Aggregate scores use the complete append-only history in [`evaluations.jsonl`](evaluations.jsonl), not only the 30 runs displayed in [`scorecard.md`](scorecard.md).

| Model | Formal runs | Average /5 | First-pass acceptance | Safe final state verified | Evidence level |
|---|---:|---:|---:|---:|---:|
| GPT-5.6 Sol | 17 | 4.99 | 65% | 17/17 applicable | Useful operating baseline |
| GPT-5.6 Luna | 55 | 4.97 | 49% | 55/55 applicable | Useful operating baseline |
| Claude Opus 5 | 14 | 4.96 | 79% | 14/14 applicable | Useful operating baseline |

## Task-class scorecard

| Model | Task class | Difficulty | Runs | Average /5 | First-pass acceptance | Confidence |
|---|---|---|---:|---:|---:|---|
| Claude Opus 5 | Architecture Lock Micro Review | High | 1 | 5.00 | 100% | Anecdotal |
| Claude Opus 5 | Architecture Proposal | High | 1 | 4.35 | 100% | Anecdotal |
| Claude Opus 5 | Architecture Validation | High | 1 | 4.82 | 0% | Anecdotal |
| Claude Opus 5 | Complex Repository Change | High | 6 | 3.87 | 17% | Moderate |
| Claude Opus 5 | Controlled Live Operation | High | 1 | 5.00 | 0% | Anecdotal |
| Claude Opus 5 | Exact Head Gate 4 Review | High | 2 | 5.00 | 100% | Anecdotal |
| Claude Opus 5 | Fresh Exact Head G4 | High | 1 | 4.98 | 100% | Anecdotal |
| Claude Opus 5 | Live Host Provisioning | High | 1 | 4.95 | 100% | Anecdotal |
| Claude Opus 5 | Live Operation Admission | High | 1 | 4.99 | 0% | Anecdotal |
| Claude Opus 5 | Live Runtime Alignment | High | 1 | 4.86 | 100% | Anecdotal |
| Claude Opus 5 | Live Runtime Recovery Validation | High | 1 | 5.00 | 100% | Anecdotal |
| Claude Opus 5 | Repository Implementation | High | 1 | 4.96 | 100% | Anecdotal |
| Claude Opus 5 | Repository Rebaseline Revalidation | High | 1 | 5.00 | 100% | Anecdotal |
| Claude Opus 5 | Security Review | High | 1 | 5.00 | 100% | Anecdotal |
| DeepSeek V4 Pro | Architecture Proposal | High | 1 | 4.14 | 100% | Anecdotal |
| DeepSeek V4 Pro | Complex Repository Change | High | 1 | 2.75 | 0% | Anecdotal |
| DeepSeek V4 Pro | Hosted Product Uat | High | 1 | 3.50 | 0% | Anecdotal |
| DeepSeek V4 Pro | Hosted Product Uat | Medium | 1 | 4.89 | 100% | Anecdotal |
| DeepSeek V4 Pro | Incident Diagnosis | High | 1 | 4.87 | 100% | Anecdotal |
| DeepSeek V4 Pro | Production Deployment | High | 1 | 4.59 | 100% | Anecdotal |
| DeepSeek V4 Pro | Production Operations | High | 4 | 4.41 | 75% | Provisional |
| DeepSeek V4 Pro | Research | High | 6 | 3.97 | 17% | Moderate |
| DeepSeek V4 Pro | Security Architecture Audit | High | 1 | 4.01 | 0% | Anecdotal |
| DeepSeek V4 Pro | Security Remediation | High | 2 | 3.92 | 0% | Anecdotal |
| DeepSeek V4 Pro | Security Review | High | 2 | 3.49 | 0% | Anecdotal |
| GPT-5.6 Luna | Bounded G3 Retirement | Critical | 1 | 5.00 | 100% | Anecdotal |
| GPT-5.6 Luna | Bounded Test Orchestration Repair | High | 1 | 5.00 | 100% | Anecdotal |
| GPT-5.6 Luna | Canonical Ci Revalidation | High | 1 | 4.98 | 0% | Anecdotal |
| GPT-5.6 Luna | Database Privilege Contract Amendment | Critical | 1 | 5.00 | 100% | Anecdotal |
| GPT-5.6 Luna | Dependency Maintenance | Medium | 1 | 5.00 | 100% | Anecdotal |
| GPT-5.6 Luna | Expected Head Merge Canonical Verification | High | 1 | 5.00 | 0% | Anecdotal |
| GPT-5.6 Luna | Live Activation Preflight | Critical | 1 | 5.00 | 0% | Anecdotal |
| GPT-5.6 Luna | Live Activation Safety Gate | Critical | 1 | 5.00 | 0% | Anecdotal |
| GPT-5.6 Luna | Live Configuration Containment | High | 1 | 5.00 | 0% | Anecdotal |
| GPT-5.6 Luna | Live Configuration Transaction | High | 1 | 5.00 | 0% | Anecdotal |
| GPT-5.6 Luna | Live Dns Edge Closure | High | 1 | 5.00 | 100% | Anecdotal |
| GPT-5.6 Luna | Live Hosting Baseline Preparation | High | 1 | 5.00 | 100% | Anecdotal |
| GPT-5.6 Luna | Live Processor Transaction | Critical | 7 | 4.96 | 0% | Moderate |
| GPT-5.6 Luna | Live Production Readonly Classification | High | 1 | 5.00 | 100% | Anecdotal |
| GPT-5.6 Luna | Live Readonly Adjudication | Critical | 2 | 4.98 | 100% | Anecdotal |
| GPT-5.6 Luna | Live Readonly Adjudication | High | 1 | 5.00 | 100% | Anecdotal |
| GPT-5.6 Luna | Live Readonly Drift Classification | High | 1 | 5.00 | 0% | Anecdotal |
| GPT-5.6 Luna | Live Readonly Lifecycle Classification | High | 1 | 5.00 | 0% | Anecdotal |
| GPT-5.6 Luna | Live Readonly Scope Classification | High | 2 | 5.00 | 50% | Anecdotal |
| GPT-5.6 Luna | Live Target Authority Disambiguation | High | 1 | 5.00 | 0% | Anecdotal |
| GPT-5.6 Luna | Production Diagnostic | High | 2 | 5.00 | 50% | Anecdotal |
| GPT-5.6 Luna | Production Readonly Authentication Diagnostic | Medium | 1 | 5.00 | 100% | Anecdotal |
| GPT-5.6 Luna | Production Readonly Diagnostic | High | 5 | 5.00 | 100% | Provisional |
| GPT-5.6 Luna | Receipt Contract Repair | High | 5 | 5.00 | 40% | Provisional |
| GPT-5.6 Luna | Runtime Contract Uplift | Medium | 1 | 5.00 | 100% | Anecdotal |
| GPT-5.6 Luna | Security Control Plane Amendment | High | 1 | 5.00 | 100% | Anecdotal |
| GPT-5.6 Luna | Security Remediation | Critical | 10 | 4.89 | 40% | Moderate |
| GPT-5.6 Luna | Test Remediation | High | 1 | 5.00 | 0% | Anecdotal |
| GPT-5.6 Luna | Test Stability Repair | High | 1 | 5.00 | 100% | Anecdotal |
| GPT-5.6 Sol | Complex Repository Change | High | 2 | 4.44 | 50% | Anecdotal |
| GPT-5.6 Sol | Exact Head G4 Review | High | 1 | 5.00 | 100% | Anecdotal |
| GPT-5.6 Sol | Exact Head Gate 4 Review | Critical | 4 | 5.00 | 0% | Provisional |
| GPT-5.6 Sol | Exact Head Gate4 Review | Medium | 1 | 5.00 | 100% | Anecdotal |
| GPT-5.6 Sol | Final Exact Head G4 | High | 1 | 5.00 | 100% | Anecdotal |
| GPT-5.6 Sol | Fresh Exact Head G4 | Critical | 2 | 5.00 | 100% | Anecdotal |
| GPT-5.6 Sol | Fresh Exact Head Runtime Contract Review | High | 1 | 5.00 | 100% | Anecdotal |
| GPT-5.6 Sol | Hosted Product Uat | Medium | 1 | 4.20 | 0% | Anecdotal |
| GPT-5.6 Sol | Independent Final Review | High | 1 | 5.00 | 100% | Anecdotal |
| GPT-5.6 Sol | Receipt Contract Review | High | 1 | 5.00 | 100% | Anecdotal |
| GPT-5.6 Sol | Research | High | 6 | 4.29 | 17% | Moderate |
| GPT-5.6 Sol | Security Audit | High | 1 | 4.74 | 100% | Anecdotal |
| GPT-5.6 Sol | Security Control Plane Independent Review | High | 1 | 5.00 | 0% | Anecdotal |
| GPT-5.6 Sol | Security Remediation | High | 2 | 3.80 | 0% | Anecdotal |
| GPT-5.6 Sol | Security Review | Critical | 2 | 4.92 | 50% | Anecdotal |
| GPT-5.6 Sol | Security Review | High | 2 | 5.00 | 100% | Anecdotal |
| MiMo 2.5 Pro | Architecture Proposal | High | 1 | 4.53 | 100% | Anecdotal |
| MiMo 2.5 Pro | Complex Repository Change | High | 2 | 3.38 | 0% | Anecdotal |
| MiMo 2.5 Pro | Complex Repository Change | Medium | 1 | 3.26 | 0% | Anecdotal |
| MiMo 2.5 Pro | Incident Diagnosis | High | 3 | 3.47 | 0% | Provisional |
| MiMo 2.5 Pro | Production Deployment | High | 1 | 2.25 | 0% | Anecdotal |
| MiMo 2.5 Pro | Provider Operation | High | 5 | 3.56 | 0% | Provisional |
| MiMo 2.5 Pro | Routine Repository Change | Low | 1 | 4.60 | 0% | Anecdotal |
| MiMo 2.5 Pro | Security Remediation | High | 5 | 3.52 | 0% | Provisional |

These tables are generated from the append-only ledger. Do not edit them manually.
<!-- GENERATED:README-SCORES:END -->

## Purpose

This repository tracks whether an executor produces correct, safe, reviewable and efficient work. Public records use opaque aliases and exclude repository owners, repository names, user names, raw project URLs, provider identifiers, secrets and private operational details.

## Control boundary

- The ChatGPT web controller is the sole routine editor of this ledger.
- Executors being evaluated must not clone, modify, update or rely on this repository.
- Executors may report facts, but they never grade themselves.
- Every score is assigned only after controller verification.
- Public entries are sanitised by construction.
- After every merged ledger update, the controller tells the user the exact appended model, run ID, verdict and score.

## Public-safety CI

Every pull request and push to `main` runs fail-closed checks over:

- the complete tracked tree;
- structured JSONL keys and values;
- every line added in every commit after the public-safety baseline;
- append-only evaluation history relative to the pull-request base;
- deterministic README and scorecard generation.

The scanner rejects common credentials, private keys, emails, user-home paths, repository URLs/slugs, identity fields, provider identifiers, UUIDs and credential-bearing URLs or assignments by default. Any exception must be an exact, boundary-checked documentation URL in the scanner allowlist. CI reduces accidental disclosure risk but does not replace controller review.

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
5. Record the exact provider and canonical base model.
6. Let the controller-branch workflow regenerate the README and scorecard.
7. Update the model-use policy when evidence changes the safe operating boundary.
8. Reconcile the applicable private project tracker.
9. Merge the ledger update through required safety checks.
10. Tell the user which model was appended.
11. Only then issue the next executor prompt.

ChatGPT web cannot receive completion webhooks from external executors. The user must bring each completion report to the controller conversation; grading is automatic from that point onward.

## Interpretation

One task-class run is anecdotal. Three comparable runs provide provisional evidence, not a stable baseline. Model-level conclusions require comparable runs grouped by task class, difficulty and tool environment. Mixed-task evidence can inform task fit but cannot establish improvement or regression.
