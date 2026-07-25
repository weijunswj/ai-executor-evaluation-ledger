# Model-Use Policy

Updated: 25 July 2026, 12:05 SGT

This policy translates verified evaluation evidence into current operating boundaries. It does not claim that any model is permanently good or bad; permissions should tighten or loosen as comparable evidence accumulates.

## Xiaomi MiMo 2.5 Pro

Reasoning level: **Provider default across 10 formal runs**

Evidence level: **Moderate across 10 mixed-task formal runs**

Observed scores:

- production deployment, high difficulty: **2.25/5**;
- routine repository change, low difficulty: **4.60/5**;
- incident diagnosis, high difficulty: **3.34/5** across 2 runs;
- provider operation, high difficulty: **3.27/5** across 2 runs;
- security remediation, high difficulty: **3.30/5** across 4 runs;
- mixed-task average: **3.33/5**;
- first-pass acceptance: **0%**;
- verified safe final state: **4/9 applicable runs**.

### Approved

- Strictly read-only repository or provider inspection where direct evidence is available.
- Narrow mechanical repository changes with exact file scope and mandatory controller review.
- Low-risk overflow work that does not block release, mutate production or control authentication, data or deployment boundaries.

### Conditional

- Tracker writes require immediate controller fetch-back and correction.
- Root-cause conclusions must be labelled as hypotheses unless supported by direct logs or provider evidence.
- Green tests and continuous integration are supporting evidence only; they do not authorise self-acceptance.

### Not currently approved

- Further launch-critical implementation for the current SKR, SQAG or Platform programmes.
- Authentication, database, migration, DNS, environment, certificate or deployment mutation.
- Autonomous merge, deployment, rollback or provider operation.
- Independent tracker-body authority.
- Exact root-cause or PASS claims based on repository inspection without direct execution evidence.
- Further evaluation runs merely to extend the current sample; the agreed 10-run cap has been reached.

### Current evidence

Across 10 formal mixed-task runs, MiMo consistently respected explicit no-mutation boundaries and was strongest on narrow mechanical work. It produced useful partial repairs and evidence recovery, but no run achieved first-pass acceptance. Repeated defects included premature PASS claims, incomplete negative-path coverage, tracker corruption, stale-contract diagnosis and unsupported live root-cause conclusions.

The tenth run removed the named production debug path and correctly bound tests to the production validator, with clean trackers and green exact-head continuous integration. It still omitted six explicitly required negative matrix classes and left a reported local test failure unreconciled while claiming the matrix was complete.

### Current disposition

The evaluation cap is complete. MiMo remains available only as a bounded overflow executor for low-risk or read-only work. The next launch-critical repair must use the next owner-approved model and receive the same exact-head controller review.

## Claude Opus 4.8 High

Reasoning level: **High**

Evidence level: **Provisional - 3 formal high-difficulty complex-repository-change runs**

The first two append-only evaluation records used the incomplete label `Claude Opus 4.8`. Controller correction records identify them as **Claude Opus 4.8 High** with observed reasoning level `high`. The third run was recorded with the complete label. Correction records do not count as additional runs.

Observed scores:

- initial implementation: **3.53/5**;
- first amendment: **3.27/5**;
- second amendment: **3.43/5**;
- comparable average: **3.41/5**;
- first-pass acceptance: **0%**;
- verified safe draft state: **3/3**.

### Approved

- Complex repository implementation in an isolated branch or worktree.
- Multi-language contract and test changes with exact revision evidence.
- Draft pull-request preparation with no live-system mutation.
- Review remediation where every amended head receives independent controller review.

### Conditional

- Atomicity-sensitive, migration-adjacent or write-capable repository work only when the change remains draft and unmerged until exact-head acceptance.
- Package, ledger, cleanup and durable-state changes only with explicit race, crash, no-clobber and cleanup-failure tests.
- Green tests and continuous integration are supporting evidence, not an acceptance decision.
- A same-domain P1/P2 surviving a High-reasoning amendment requires escalation to the next owner-approved reasoning tier before further implementation.

### Not currently approved

- One-prompt autonomous merge for high-risk repository changes.
- Self-approval based on test or continuous-integration success alone.
- Autonomous production mutation.
- Skipping a fresh exact-head review after a same-domain amendment.
- Claiming residue-free cleanup when deletion errors are suppressed or cleanup is merely best effort.
- Treating successful publication as ordinary success while a second PII-bearing temporary pathname may remain unaccounted for.

### Current evidence

The initial run delivered a strong core implementation but required three material corrections. The first amendment closed those findings while introducing a same-root atomic-publication defect. The second amendment restored atomic no-replace publication and added focused race/failure tests, but cleanup still silently suppressed temporary-file deletion failures while claiming no stale temporary remained.

All three runs maintained exact revision evidence, green continuous integration, a verified safe draft state and zero live-system actions. None achieved first-pass acceptance. The three-run sample is provisional evidence of strong implementation and evidence discipline combined with weak convergence at filesystem atomicity and cleanup boundaries.

### Promotion condition

Before this task class can be treated as independently merge-ready, Claude Opus 4.8 High must:

- preserve atomic no-replace publication and strict no-clobber behaviour;
- test every materially different post-publication failure boundary rather than only the immediate defect named by review;
- preserve an already-published final package and never delete or alter a competing final path;
- ensure every published package has durable, non-bypassable single-use state;
- provide a bounded recovery/evidence contract when immediate cleanup or state persistence cannot be completed;
- close the same-root durability defect without introducing another atomicity, cleanup or evidence defect;
- receive an accepted exact-head controller review;
- maintain zero unauthorised live-system actions.

The required Ultra High escalation was performed and is evaluated separately below. High reasoning remains insufficient for independent acceptance of this durable-state task.

## Claude Opus 4.8 Ultra High

Reasoning level: **Ultra High**

Evidence level: **Anecdotal - 1 formal high-difficulty complex-repository-change run**

Observed score:

- third amendment: **3.23/5**;
- first-pass acceptance: **0%**;
- verified safe draft state: **1/1**.

### Approved

- Narrow high-risk repository remediation in an isolated branch or worktree.
- Exact-head implementation and test evidence for controller review.
- Draft pull-request updates with no live-system mutation.
- Explicit negative testing of the failure mode named by the controller.

### Conditional

- Atomicity, cleanup, package and ledger work only while draft and unmerged.
- Every post-publication side effect must be paired with a durable, non-bypassable state transition.
- Persistence-failure tests must cover open, write, flush and fsync failures, not only unlink or publication failures.
- Green tests and continuous integration remain supporting evidence only.

### Not currently approved

- Autonomous merge or self-acceptance of write-capable or durable-state changes.
- Assuming the append-only ledger is always writable after publication.
- Treating a generic exception or nonzero exit as sufficient protection when durable approval consumption is missing.
- Autonomous production mutation or package creation from private operational data.

### Current evidence

The Ultra High amendment correctly replaced silent unlink suppression with an explicit three-state publication and cleanup model. It added deterministic unlink-failure tests, preserved final and competing packages, kept the change draft and unmerged, and performed no live-system action.

However, the implementation still records approval consumption only after publication. If the ledger open, write, flush or fsync fails after the final package exists, no durable build event remains; a later invocation can use the same approval to mint another package at a fresh path. This is a same-domain P1 and a merge blocker. The completion report overstated durable single-use closure.

### Promotion condition

Before this task can be accepted, the next amendment must:

- make published-package consumption survive ledger open, write, flush and fsync failure;
- preserve the already-published final package and any stale temporary alias without rollback or broad cleanup;
- emit an explicit non-success, do-not-retry state rather than only a generic error;
- prove the same approval cannot mint another package at any fresh path after publication;
- add deterministic tests for ledger persistence failure after both clean publication and published-but-cleanup-incomplete publication;
- retain exact-head evidence, a draft unmerged state and zero unauthorised live-system actions;
- receive an accepted controller review.

Because a same-domain launch-blocking P1 survived the Ultra High repair, the next implementation used the owner-approved Max escalation and is evaluated separately below.

## Claude Opus 5 Max

Reasoning level: **Max**

Evidence level: **Anecdotal - 1 formal high-difficulty complex-repository-change run**

Observed score:

- fourth amendment: **3.15/5**;
- first-pass acceptance: **0%**;
- verified safe draft state: **1/1**.

### Approved

- Narrow high-risk repository remediation in an isolated branch or worktree.
- Exact-head code, test and continuous-integration evidence for independent controller review.
- Draft pull-request and tracker updates with no live-system mutation.
- Directional durable-state redesign where every committed boundary remains independently reviewed.

### Conditional

- Package, ledger, reservation and filesystem-durability changes only while draft and unmerged.
- Tests must model both fully lost appends and bytes-visible-but-durability-unconfirmed appends.
- Partial writes, malformed durable state, process restart and every acknowledgement persistence stage must be exercised with real files.
- Reservation reconciliation must require independent durable completion proof, not merely a readable ledger line.
- Green tests, mutation tests and continuous integration remain supporting evidence only.

### Not currently approved

- Autonomous merge or self-acceptance of durable-state or write-capable changes.
- Treating `flush` or `fsync` failure as proof that no bytes reached the ledger.
- Treating a parseable ledger event as durably committed solely because a later process can read it.
- Allowing malformed or partial append-only state to escape as an uncontrolled traceback.
- Autonomous production mutation or package creation from private operational data.

### Current evidence

The Max amendment introduced the correct write-ahead reservation direction, created it exclusively before atomic publication, added explicit reservation/publication/cleanup/ledger outcomes, preserved final and competing paths, retained a draft unmerged state, and performed no live-system action.

The repair nevertheless remains merge-blocked. Its negative-test helper deliberately prevents failed ledger bytes from reaching disk, including the fsync case. A real flush or fsync failure can leave a complete readable `build` line whose durability was never confirmed; the next process treats that line as reconciled and can reopen `--rebuild` under the same approval. A partial append can also leave malformed JSONL that is not converted into a controlled sanitised failure. This is a fourth same-domain non-convergent amendment and another P1.

### Promotion condition

Before this task can be accepted, a narrowly scoped Max amendment must:

- add a separate durable completion acknowledgement, or an equivalent mechanism, created only after the matching ledger event is durably confirmed;
- reconcile a reservation only when both the exact ledger event and its completion acknowledgement are valid;
- keep both plain build and `--rebuild` blocked after a full visible line plus flush/fsync failure, a partial append, or any acknowledgement persistence failure;
- handle malformed or partial ledger state with an explicit sanitised non-success and no traceback;
- test clean and cleanup-incomplete publication, process restart, acknowledgement tampering and every open/write/flush/fsync/directory-fsync failure;
- preserve the final package, reservation, strict no-clobber and zero-live-action boundaries;
- receive an accepted exact-head controller review.

Max is already the highest owner-approved tier. Further progress must come from tighter controller-specified invariants and adversarial tests, not from inventing a higher reasoning label.

## GPT-5.6 Sol Medium

Reasoning level: **Medium**

Evidence level: **Prior programme experience; formal run backfill pending**

### Provisional use

- Routine implementation, tests, documentation and bounded configuration changes.
- Independent exact-head review still required.

### Restrictions

- No autonomous production mutation.
- Security, authentication, migration and complex operational work should normally use GPT-5.6 Sol High.

## GPT-5.6 Sol High

Reasoning level: **High**

Evidence level: **Prior programme experience; formal run backfill pending**

### Provisional use

- Complex implementation, authentication/security repair, migration design and production diagnosis.
- Production operation only with exact gates, stop conditions and independent controller verification.

### Restrictions

- Not treated as one-prompt autonomous completion.
- Repeated same-root amendment cycles and incomplete evidence remain material evaluation concerns.

## Universal requirements

Regardless of model:

- exact private repository and revision binding;
- exact model label and observed reasoning level recorded when exposed;
- `not-exposed` used instead of guessing a reasoning level;
- public records use opaque subject aliases;
- no secret or private-identity disclosure;
- explicit mutation authorisation;
- independent controller review;
- complete evidence appropriate to the task;
- private project tracker reconciliation;
- evaluation-ledger update before the next prompt;
- user-facing confirmation of the appended model, reasoning level, run ID, verdict and score after the ledger update merges.
