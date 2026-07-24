# Controller Policy

## Mandatory sequence

No executor result is considered reviewed until both the central evaluation ledger and the applicable project tracker are reconciled.

For every executor completion report presented to the ChatGPT web controller:

1. Verify the claimed repository, branch, SHA, pull request, review, CI, issue and available provider state.
2. Separate executor-reported facts from controller-verified facts.
3. Determine the operational verdict.
4. Grade the run using `SCORING_RUBRIC.md`.
5. Append exactly one record to `evaluations.jsonl`.
6. Recalculate `scorecard.md`.
7. Update `model-policy.md` when evidence changes the model's safe task boundary.
8. Reconcile the relevant project issue body and dated evidence comment.
9. Produce the next executor prompt only after steps 1-8 are complete.

## Editor boundary

- The ChatGPT web controller is the sole routine editor of this repository.
- Executors must not be instructed to update this ledger.
- Executor prompts should include: `Do not access, clone, modify or attempt to update the controller-owned executor evaluation ledger.`
- The repository must not be cloned into executor workspaces.
- The user remains the repository owner and can technically edit it; controller-only editing is an operating policy rather than a separate cryptographic identity boundary.

## Evidence rules

A claimed PASS is not accepted without reviewable evidence appropriate to the task. Evidence should include, where applicable:

- repository identity, branch and exact SHA;
- changed paths and exact diff scope;
- test commands, exit codes and CI run identifiers;
- deployment, job or operation identifiers;
- timestamps and final statuses;
- safe provider evidence and artifact hashes;
- tracker body verification after mutation;
- explicit confirmation of prohibited operations not performed.

Missing evidence lowers the evidence score even when the final state appears safe.

## Public-data rules

Allowed:

- public repository names and commit SHAs;
- public pull-request and issue numbers;
- model/provider labels and reasoning modes;
- sanitised task descriptions;
- scores, verified strengths, defects and controller effort;
- non-sensitive tool and workflow versions.

Prohibited:

- tokens, passwords, API keys or connection strings;
- private emails, user IDs, OAuth subjects or customer data;
- private support identifiers unless deliberately approved for publication;
- raw provider payloads containing sensitive metadata;
- detailed attack paths or exploitable infrastructure configuration;
- full prompts containing secrets or private operational details.

## Append-only requirement

`evaluations.jsonl` is append-only. Existing records may not be silently changed. Corrections require a new record with:

- `record_type: "correction"`;
- the affected `run_id`;
- the corrected fields;
- the reason and verification evidence.

## Prompt capture

For new runs, preserve:

- exact model/provider label;
- reasoning mode requested and observed;
- prompt SHA-256 where the exact prompt text is available;
- prompt version or controller conversation reference;
- task class, difficulty, repository and authorised SHA;
- tool availability and material constraints.

Historical runs may use `null` where exact prompt capture was not preserved.

## Regression handling

Do not call a single poor result a model regression or "nerf". Record:

- `suspected_regression` after repeated comparable real-work degradation;
- `probable_regression` only when comparable real work and stable benchmark results both decline under materially unchanged prompts and tools.

Every regression assessment must state alternative explanations such as task difficulty, context length, permissions, tool failures and environment drift.

## Automation limitation

ChatGPT web cannot receive immediate completion webhooks from external executors. The user must bring each executor report to the controller. Once presented, grading and ledger reconciliation are mandatory and should not require a separate request.
