# Controller Policy

## Mandatory prompt-check sequence

A **prompt check** means any executor completion report, amendment report, pull-request result, deployment result, review result, incident diagnosis or evidence packet presented to the ChatGPT web controller for judgement before the next executor prompt.

No prompt check is considered complete until both the central evaluation ledger and the applicable project tracker are reconciled.

For every prompt check:

1. Verify the claimed repository, branch, revision, pull request, review, CI, issue and available provider state.
2. Separate executor-reported facts from controller-verified facts.
3. Determine the operational verdict.
4. Grade the run using `SCORING_RUBRIC.md`.
5. Append exactly one new evaluation record to `evaluations.jsonl`, or an explicit correction record when correcting a prior non-privacy fact.
6. Record the exact provider and canonical base model.
7. Recalculate the README summary table and `scorecard.md`.
8. Update `model-policy.md` when evidence changes the model's safe task boundary.
9. Reconcile the relevant private project issue body and dated evidence comment.
10. Tell the user exactly which model was appended, together with the run ID, verdict and score.
11. Produce the next executor prompt only after steps 1-10 are complete.

The user must not need to separately request grading or ledger maintenance after presenting an executor result.

## Zero reviewed-but-unmerged queue

A result becomes **ledger-pending** as soon as the controller has reviewed it and assigned a verdict and score. Review text, project-tracker reconciliation or a stated provisional grade does not complete the prompt check by itself.

Before any new executor prompt is issued:

- every ledger-pending result must be appended through a controller-owned pull request;
- required checks must pass;
- the pull request must merge;
- the applicable project tracker must be authoritative;
- `main` must be fetched back and each expected run ID verified;
- the reviewed-but-unmerged queue must equal zero.

If multiple completion reports are presented before reconciliation, the controller must append all reviewed records in one bounded ledger pull request or finish sequential ledger pull requests before another executor prompt. A later completion report does not excuse an earlier pending record.

Run-count language is strict:

- **formal run** means an evaluation record merged into ledger `main`;
- **ledger-pending run** means controller-reviewed but not merged;
- **in-flight run** means executor work not yet presented for review.

Never state or imply that a ledger-pending or in-flight run is formal. Any model-cap, trend or task-fit statement must show the merged formal count and separately identify pending and in-flight counts when they exist.

The controller must check this gate without waiting for the user to notice a stale scorecard.

## Required user-facing confirmation

After each accepted ledger update, state this information plainly:

```text
Ledger appended: <provider> | <canonical-base-model> | <run-id> | <verdict> | <score>/5
```

When one pull request appends multiple evaluations, state one line per appended run.

Do not claim that a model was appended until the controller-owned ledger pull request has passed required checks and merged.

## Human-readable display retention

`evaluations.jsonl` remains append-only and retains the complete sanitised history for longitudinal and regression analysis.

The following `scorecard.md` sections display only the **30 newest formal evaluation runs**, newest first:

- `Formal evaluated runs`
- `Latest formal evaluations`

When a 31st formal evaluation is added:

- remove only the oldest displayed row and oldest displayed detailed evaluation from those two sections;
- do not remove, rewrite or truncate the corresponding `evaluations.jsonl` record;
- continue including the complete ledger history in aggregate scores, confidence calculations and regression analysis;
- do not count correction records as additional formal runs.

Every displayed formal run must show the exact model label and observed reasoning level when available.

## Model naming

Use these exact controller labels for the OpenAI Sol variants:

- `GPT-5.6 Sol Medium`
- `GPT-5.6 Sol High`

Do not shorten them to `Sol Medium` or `Sol High` in scorecards, policies or user-facing ledger confirmations.

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
- prompt hashes when the prompt itself is not published;
- the single scanner-allowlisted README link to the companion Custom Instructions document.

Prohibited:

- repository owner names, repository names or owner/repository slugs;
- all other raw repository, issue, pull-request or commit URLs;
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
- URL exceptions must be exact, boundary-checked, documentation-only allowlist entries; broad host or repository exemptions are prohibited.
- A failed scan blocks merge or acceptance.
- The controller must still review sanitisation manually because pattern scanning cannot prove absence of every sensitive inference.

## Append-only requirement and privacy exception

`evaluations.jsonl` is append-only for ordinary evaluation changes. Existing records may not be silently changed.

A privacy redaction is the sole exception. When current public content contains identifying or sensitive metadata, the controller must remove it from the current tree, record a `redaction_notice`, and document the correction. Historical Git objects may still require separate repository-history remediation.

Non-privacy corrections require a new record with:

- `record_type: "correction"`;
- the affected `run_id`;
- the corrected fields;
- the reason and verification evidence.

## Prompt capture

For new runs, preserve privately:

- exact model/provider label;
- requested and observed reasoning level;
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
