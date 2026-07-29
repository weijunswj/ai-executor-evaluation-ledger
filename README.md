# AI Executor Evaluation Ledger

Public, controller-owned evidence for evaluating AI coding and operations executors across real project work.
Used in conjunction with [LLM WEB CUSTOM INSTRUCTIONS SET](https://github.com/weijunswj/Custom-Instruction-Framework-For-Web-based-LLMs/blob/main/CUSTOM_INSTRUCTIONS.md).

> **Controller sessions:** read [`CONTROLLER_QUICKSTART.md`](CONTROLLER_QUICKSTART.md) before editing. Append one JSONL record; do not hand-edit generated score sections.

<!-- GENERATED:README-SCORES:START -->
## AI Model Recommendations & Operational Guidance

**Official Recorded Gated Evidence:** 58 runs | **Queued Intake:** 0 runs | **Total Available:** 58 runs

### Tested Model Summary & Like-for-Like Analysis

- **GPT-5.6 Sol**: Average Score **4.52/5** across 25 recorded run(s) (8 independent subject/task family). First-pass acceptance: **16%**.
- **Claude Opus 5**: Average Score **4.51/5** across 2 recorded run(s) (1 independent subject/task family). First-pass acceptance: **0%**.
- **Qwen3.7 Plus**: Average Score **4.26/5** across 13 recorded run(s) (3 independent subject/task family). First-pass acceptance: **15%**.
- **DeepSeek V4 Pro**: Average Score **3.87/5** across 18 recorded run(s) (4 independent subject/task family). First-pass acceptance: **0%**.

> [!NOTE]
> Recommendations are strictly grounded in empirical recorded `gated_v1` evidence. Queued intake is provisional and does not alter official recorded rankings.

## Summary model scores

This is the primary at-a-glance tracker. Aggregate scores use the complete append-only history in [`evaluations.jsonl`](evaluations.jsonl), not only the 30 runs displayed in [`scorecard.md`](scorecard.md).

| Model | Formal runs | Average /5 | First-pass acceptance | Safe final state verified | Evidence level |
|---|---:|---:|---:|---:|---:|
| GPT-5.6 Sol | 25 | 4.52 | 16% | - | Useful operating baseline |
| Claude Opus 5 | 2 | 4.51 | 0% | - | Anecdotal |
| Qwen3.7 Plus | 13 | 4.26 | 15% | - | Useful operating baseline |
| DeepSeek V4 Pro | 18 | 3.87 | 0% | - | Useful operating baseline |

## Task-class scorecard

| Model | Task class | Difficulty | Runs | Average /5 | First-pass acceptance | Confidence |
|---|---|---|---:|---:|---:|---|
| Claude Opus 5 | Architecture Proposal | High | 1 | 4.35 | 100% | Anecdotal |
| Claude Opus 5 | Complex Repository Change | High | 5 | 3.63 | 0% | Provisional |
| Claude Opus 5 | Research | High | 1 | 4.55 | 0% | Anecdotal |
| Claude Opus 5 | Security Remediation | High | 1 | 4.47 | 0% | Anecdotal |
| DeepSeek V4 Pro | Architecture Proposal | High | 1 | 4.14 | 100% | Anecdotal |
| DeepSeek V4 Pro | Complex Repository Change | High | 6 | 3.39 | 0% | Moderate |
| DeepSeek V4 Pro | Hosted Product Uat | High | 1 | 3.15 | 0% | Anecdotal |
| DeepSeek V4 Pro | Hosted Product Uat | Medium | 1 | 4.85 | 100% | Anecdotal |
| DeepSeek V4 Pro | Incident Diagnosis | High | 1 | 4.80 | 100% | Anecdotal |
| DeepSeek V4 Pro | Migration | Critical | 2 | 3.19 | 0% | Anecdotal |
| DeepSeek V4 Pro | Production Admission | High | 1 | 4.36 | 0% | Anecdotal |
| DeepSeek V4 Pro | Production Deployment | High | 1 | 4.55 | 100% | Anecdotal |
| DeepSeek V4 Pro | Production Operations | High | 4 | 4.35 | 75% | Provisional |
| DeepSeek V4 Pro | Provider Admission | High | 1 | 4.52 | 0% | Anecdotal |
| DeepSeek V4 Pro | Research | High | 6 | 3.91 | 17% | Moderate |
| DeepSeek V4 Pro | Security Architecture Audit | High | 1 | 3.85 | 0% | Anecdotal |
| DeepSeek V4 Pro | Security Remediation | High | 9 | 3.97 | 0% | Moderate |
| DeepSeek V4 Pro | Security Review | High | 2 | 3.49 | 0% | Anecdotal |
| DeepSeek V4 Pro | Ux Remediation | Medium | 2 | 4.45 | 0% | Anecdotal |
| GPT-5.6 Sol | Architecture Proposal | High | 1 | 3.71 | 0% | Anecdotal |
| GPT-5.6 Sol | Complex Repository Change | Critical | 1 | 4.82 | 100% | Anecdotal |
| GPT-5.6 Sol | Complex Repository Change | High | 4 | 4.34 | 25% | Provisional |
| GPT-5.6 Sol | Concurrency Recovery Remediation | High | 1 | 4.12 | 0% | Anecdotal |
| GPT-5.6 Sol | Database Access Control | High | 1 | 4.86 | 100% | Anecdotal |
| GPT-5.6 Sol | Hosted Product Uat | Medium | 1 | 4.20 | 0% | Anecdotal |
| GPT-5.6 Sol | Implementation | Medium | 2 | 4.38 | 0% | Anecdotal |
| GPT-5.6 Sol | Production Operations | High | 1 | 4.78 | 0% | Anecdotal |
| GPT-5.6 Sol | Production Recovery | High | 1 | 4.88 | 100% | Anecdotal |
| GPT-5.6 Sol | Recovery Protocol Remediation | High | 1 | 4.72 | 0% | Anecdotal |
| GPT-5.6 Sol | Research | High | 9 | 4.34 | 11% | Moderate |
| GPT-5.6 Sol | Security Architecture | High | 1 | 4.68 | 0% | Anecdotal |
| GPT-5.6 Sol | Security Audit | High | 1 | 4.70 | 100% | Anecdotal |
| GPT-5.6 Sol | Security Remediation | High | 12 | 4.45 | 8% | Useful operating baseline |
| MiMo 2.5 Pro | Architecture Proposal | High | 1 | 4.40 | 100% | Anecdotal |
| MiMo 2.5 Pro | Complex Repository Change | High | 2 | 3.23 | 0% | Anecdotal |
| MiMo 2.5 Pro | Complex Repository Change | Medium | 1 | 3.26 | 0% | Anecdotal |
| MiMo 2.5 Pro | Incident Diagnosis | High | 3 | 3.47 | 0% | Provisional |
| MiMo 2.5 Pro | Production Deployment | High | 1 | 2.25 | 0% | Anecdotal |
| MiMo 2.5 Pro | Provider Operation | High | 5 | 3.55 | 0% | Provisional |
| MiMo 2.5 Pro | Routine Repository Change | Low | 1 | 4.60 | 0% | Anecdotal |
| MiMo 2.5 Pro | Security Remediation | High | 5 | 3.50 | 0% | Provisional |
| Qwen3.7 Plus | Application Remediation | High | 1 | 4.36 | 0% | Anecdotal |
| Qwen3.7 Plus | Complex Repository Change | Medium | 1 | 4.47 | 0% | Anecdotal |
| Qwen3.7 Plus | Credential Containment | High | 1 | 3.58 | 0% | Anecdotal |
| Qwen3.7 Plus | Implementation Amendment | High | 2 | 4.05 | 0% | Anecdotal |
| Qwen3.7 Plus | Product Remediation | Medium | 1 | 4.38 | 0% | Anecdotal |
| Qwen3.7 Plus | Production Admission | High | 2 | 4.02 | 0% | Anecdotal |
| Qwen3.7 Plus | Security Incident Containment | High | 1 | 3.43 | 0% | Anecdotal |
| Qwen3.7 Plus | Security Remediation | High | 2 | 4.77 | 50% | Anecdotal |
| Qwen3.7 Plus | Security Remediation | Medium | 2 | 4.76 | 50% | Anecdotal |

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
