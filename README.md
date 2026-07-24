# AI Executor Evaluation Ledger

Public, controller-owned evidence for evaluating AI coding and operations executors across real project work.

## Purpose

This repository tracks whether an executor produces correct, safe, reviewable and efficient work. It is designed to answer practical questions such as:

- Which model is suitable for routine repository work, security remediation or production operations?
- How often does a model pass on the first attempt?
- How much controller intervention and repeated repair does it require?
- Does performance materially improve or regress over time?
- Are failures caused by the model, the prompt, the tools or the task environment?

## Control boundary

- The ChatGPT web controller is the sole routine editor of this ledger.
- Executors being evaluated must not clone, modify, update or rely on this repository.
- Executors may report facts, but they never grade themselves.
- Every score is assigned only after controller verification.
- Public entries are sanitised by construction. Secrets, private identities, provider credentials, private support identifiers and exploitable infrastructure details are prohibited.

## Files

- [`CONTROLLER_POLICY.md`](CONTROLLER_POLICY.md) - mandatory review and update workflow.
- [`SCORING_RUBRIC.md`](SCORING_RUBRIC.md) - fixed dimensions, weights and confidence rules.
- [`evaluations.jsonl`](evaluations.jsonl) - append-only structured source of truth.
- [`scorecard.md`](scorecard.md) - rolling aggregate by model and task class.
- [`model-policy.md`](model-policy.md) - current approved, conditional and prohibited uses.
- [`benchmarks/README.md`](benchmarks/README.md) - regression-detection approach.

## Review workflow

For every executor output brought to the controller:

1. Verify the actual repository, pull-request, issue and available provider state.
2. Classify the result as accepted, amend, hold or fail.
3. Grade the run using the fixed rubric.
4. Append one immutable JSONL entry.
5. Recalculate the scorecard and historical trend.
6. Update the model-use policy when evidence changes the safe operating boundary.
7. Reconcile the applicable project tracker.
8. Only then issue the next executor prompt.

ChatGPT web cannot receive completion webhooks from external executors. The user must bring each completion report into the controller conversation; grading is automatic from that point onward.

## Interpretation

One run is anecdotal. Model-level conclusions require comparable runs grouped by task class, difficulty, reasoning mode and tool environment. A decline is recorded as a suspected performance regression only after repeated comparable evidence; it is not labelled a provider-side model reduction without stronger proof.
