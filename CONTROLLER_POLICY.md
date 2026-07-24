# Controller Policy

## Mandatory sequence

No executor result is considered reviewed until both the central evaluation ledger and the applicable project tracker are reconciled.

For every executor completion report presented to the ChatGPT web controller:

1. Verify the claimed repository, branch, revision, pull request, review, CI, issue and available provider state.
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
- Controller-only editing is an operating policy rather than a separate cryptographic identity boundary.

## Evidence rules

A claimed PASS is not accepted without reviewable evidence appropriate to the task. Private controller evidence may include exact repository identities, revisions, operation identifiers and provider artifacts. The public ledger must store only sanitised summaries, opaque aliases and non-identifying assertions.

Missing evidence lowers the evidence score even when the final state appears safe.

## Public-data rules

Allowed:

- opaque project or subject aliases;
- model/provider labels and reasoning modes;
- sanitised task descriptions;
- scores, verified strengths, defects and controller effort;
- non-sensitive tool and workflow versions;
- prompt hashes when the prompt itself is not published.

Prohibited:

- repository owner names, repository names or owner/repository slugs;
- raw repository, issue, pull-request or commit URLs;
- user names, account logins, emails, user IDs or home-directory paths;
- raw commit revisions that can identify a project;
- provider project references, application/deployment/workspace/client identifiers or support case identifiers;
- tokens, passwords, API keys, private keys or connection strings;
- raw provider payloads containing sensitive metadata;
- detailed attack paths or exploitable infrastructure configuration;
- full prompts containing secrets or private operational details.

## Public-safety gate

- `python scripts/check_public_safety.py` must pass before a controller update is accepted.
- CI scans the tracked tree, structured JSONL and all added lines after the fixed safety baseline.
- A failed scan blocks merge or acceptance.
- The controller must still review sanitisation manually because pattern scanning cannot prove absence of every sensitive inference.

## Append-only requirement and privacy exception

`evaluations.jsonl` is append-only for ordinary evaluation changes. Existing records may not be silently changed.

A privacy redaction is the sole exception. When current public content contains identifying or sensitive metadata, the controller must remove it from the current tree, record a `redaction_notice`, and document the correction in the rolling tracker. Historical Git objects may still require separate repository-history remediation.

Non-privacy corrections require a new record with:

- `record_type: "correction"`;
- the affected `run_id`;
- the corrected fields;
- the reason and verification evidence.

## Prompt capture

For new runs, preserve privately:

- exact model/provider label;
- reasoning mode requested and observed;
- prompt SHA-256 where the exact prompt text is available;
- task class, difficulty and exact private revision binding;
- tool availability and material constraints.

Publish only the prompt hash, opaque subject alias and a non-identifying revision assertion.

## Regression handling

Do not call a single poor result a model regression or "nerf". Record:

- `suspected_regression` after repeated comparable real-work degradation;
- `probable_regression` only when comparable real work and stable benchmark results both decline under materially unchanged prompts and tools.

Every regression assessment must state alternative explanations such as task difficulty, context length, permissions, tool failures and environment drift.

## Automation limitation

ChatGPT web cannot receive immediate completion webhooks from external executors. The user must bring each executor report to the controller. Once presented, grading and ledger reconciliation are mandatory and should not require a separate request.
