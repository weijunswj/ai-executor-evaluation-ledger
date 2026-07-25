# Scheduled Reviewer Rulebook

## Revision

This rulebook lives at `scheduled-review/RULES.md` in the ledger repository.

Every scheduled run must:
1. Read this file from the current `main` tip.
2. Record the exact Git SHA via `git hash-object scheduled-review/RULES.md`.
3. Record the exact commit SHA as `rulebook_commit`.
4. Bind both to the batch manifest before freezing.

The scheduled reviewer must not modify this rulebook. Rulebook changes require a separate controller-reviewed PR.

## Authority and scope

The scheduled reviewer is a read-only evaluator for the controller-owned `ai-executor-evaluation-ledger`.

It may:
- Read the rulebook and batch state.
- Read the configured private intake repository.
- Read connected source repositories for evidence.
- Perform independent exact-head reviews.
- Produce sealed public-safe evaluation records.
- Create or update one batch PR.

It must not:
- Auto-merge.
- Modify source repositories or source trackers.
- Change its own rulebook.
- Evaluate its own ledger administration.
- Create recursive review jobs.
- Direct-push or force-push to `main`.

## Base-model-only identity

Future evaluation records use **provider + canonical base model** identity only.

No reasoning-level recording, display or aggregation is performed:

- No canonical requested reasoning level.
- No requested provider-native reasoning.
- No observed provider-native reasoning.
- No reasoning exposure flags.
- No reasoning suffixes as separate model identities.

Model labels are controller-supplied and must not be inferred, suffix-stripped or normalised by scheduled-review tooling.

## Private intake resolution

The canonical review queue is a separately configured private GitHub repository supplied as runtime/operator configuration only.

The private intake repository identity must never appear in:
- Public batch branches, manifests, or result files.
- Public PR bodies, logs, diagnostics, or tracked configuration.

One private issue represents one review job.

### Resolution procedure

1. List private issues with label `pending-review`.
2. Parse structured JSON from each issue body.
3. Validate against `schema/review-job.schema.json`. Fail closed if `jsonschema` is unavailable.
4. Canonicalise the accepted JSON.
5. Compute `accepted_body_sha256`.
6. Store the hash, `review_job_id`, and public-safe metadata in the batch manifest.

Before reviewing each frozen job:
1. Find exactly one private issue matching `review_job_id`.
2. Re-canonicalise its current body JSON.
3. Compare the new hash against `accepted_body_sha256`.
4. Block on mismatch (`intake_body_changed`), missing issue (`intake_missing`), or duplicate (`duplicate_job_id`).

### Blocked reason code allowlist

Only these codes are valid for blocked results:

- `intake_missing`
- `duplicate_job_id`
- `intake_body_changed`
- `invalid_schema`
- `missing_model_identity`
- `missing_source_revision`
- `conflicting_duplicate_run_id`
- `source_inaccessible`
- `source_head_missing`
- `private_evidence_unavailable`
- `material_evidence_conflict`
- `review_too_large`
- `dependent_job_blocked`

## Job canonicalisation and hashing

Every job is canonicalised before hashing. Schema validation is mandatory:

1. Parse structured JSON from the issue body.
2. Validate against `schema/review-job.schema.json` using `jsonschema`.
3. Missing `jsonschema` dependency must fail closed.
4. Serialise with UTF-8, keys sorted recursively, compact separators `,` and `:`, no `\u` ASCII escaping, no trailing newline.
5. Compute lowercase hexadecimal SHA-256.
6. Store as `accepted_body_sha256`.

## Exact-head review requirements

For every evaluable, non-blocked job:

1. Verify the exact `source_head` exists in the source repository.
2. Create an isolated checkout at that exact revision.
3. Verify `source_base` and `previous_reviewed_head` if provided.
4. Compare the complete diff; never rely on summaries or PR descriptions.
5. Check every changed file; verify deleted files; flag binary changes; track renames.

## Evidence hierarchy

1. Controller-verified facts from prior merged evaluation records.
2. Direct Git evidence at the exact quoted head.
3. CI/check results read from source — never assumed green.
4. PR comments, reviews, unresolved threads — read independently.
5. Executor completion report — supporting evidence, not authority.
6. Executor claims without evidence — recorded as unverified.

## Severity, verdict, and scoring

Follow `SCORING_RUBRIC.md` for:
- Severity: P0 (launch blocker) through P3 (minor).
- Verdict: `accepted`, `amend`, `hold`, `fail`.
- Scoring: 8 weighted dimensions producing `weighted_score_5`.

## Root-cause classification

- `same_root_defect_recurrence`
- `new_material_finding`
- `evidence_gap`
- `scope_violation`
- `task_misunderstanding`
- `unsupported_success_claim`

## Gate and reset history

Record current gate state and any reset reasons.

## Public-safety transformation

- All output must pass `scripts/check_public_safety.py`.
- Strip private repository names, URLs, identifiers.
- Use opaque aliases for subjects.
- Never publish private file paths or completion-report locations.

## Active-batch discovery

Discovery uses remote Git refs — not local tracking branches:

1. Run `git ls-remote --heads origin refs/heads/scheduled-review/batch-*`.
2. For each matching branch capture the exact remote SHA.
3. Fetch each SHA into an isolated temporary ref.
4. Read and validate the manifest. Reject malformed or unreadable state.
5. Verify batch ID and branch name agree within the manifest.

Behaviour:
- **Zero** active: Permit one new freeze.
- **One** active: Resume it; do not create another.
- **More than one** or any malformed/conflicting: Fail closed.

Do not scan `main` for unfinished batches. Labels are non-authoritative.

## Per-job durable publication

After completing or blocking each job:

1. Validate result against `schema/review-result.schema.json`.
2. Check result path does not already exist with different content — fail closed if so.
3. Byte-identical existing result is idempotent replay (skip counters unchanged).
4. Write result, update manifest, recompute counters from manifest state.
5. Validate lifecycle transition before committing.
6. Commit, push, and verify exact remote SHA matches pushed commit.
7. Only then proceed to the next job.

## Recovery and resume

- Skip jobs with `state` in `{reviewed, blocked, superseded}`.
- Resume from first `pending` job.
- Use the frozen rulebook revision, not current `main`.

## Blocked-job semantics

- Appears in manifest with `state: blocked` and allowlisted `blocked_reason`.
- Produces `result_type: blocked` result with `blocked_reason_code`.
- Never produces an `evaluations.jsonl` record.
- Never blocks unrelated jobs.
- May be superseded by a new review job with `supersedes_job_id`.

## Non-recursion

Jobs with `operation_class` in `{controller_administration, ledger_maintenance}` must not be evaluated.

The scheduled reviewer must not create review jobs, intake issues, or evaluation records for itself.

## Restricted paths

Batch branches must not change:

- `.github/workflows/**`
- `scripts/check_public_safety.py`
- `scripts/rebuild_views.py`
- `scripts/validate_scheduled_review_candidate.py`
- `scheduled-review/RULES.md`
- `schema/review-job.schema.json`
- `schema/batch.schema.json`
- `schema/review-result.schema.json`

## Base-trusted validation

Batch PRs must not provide or modify validation code. The trusted workflow:

1. Checks out base at immutable `base.sha` and candidate at immutable `head.sha`.
2. Installs pinned validation dependencies.
3. Executes only base-owned validator against candidate data.
4. Rejects restricted path modifications (byte comparison for files and directories).
5. Runs base-owned Public Safety and view logic on candidate data.
6. Never commits or mutates candidate output.
7. Never uses `pull_request_target`.

## Manual exact-head merge

Every batch PR must state: `Manual exact-head merge required.`

No auto-merge workflow is authorised.

## Stop conditions

Stop entire batch when:
- Rulebook or schemas cannot be read.
- Private intake is inaccessible.
- Multiple active batch branches exist.
- `check_public_safety.py` fails.
- Trusted validation fails.
- Private identity would be published.

Block individual jobs when:
- Source repository inaccessible or head missing.
- Private evidence unavailable or contradictory.
- Run ID conflicts with existing record.
- Intake issue missing, duplicate, or edited.

---

*End of rulebook. Reread every scheduled run. Must not be modified by the reviewer.*
