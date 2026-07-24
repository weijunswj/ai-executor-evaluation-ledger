# Model-Use Policy

Updated: 24 July 2026, 22:55 SGT

This policy translates verified evaluation evidence into current operating boundaries. It does not claim that any model is permanently good or bad; permissions should tighten or loosen as comparable evidence accumulates.

## Xiaomi MiMo 2.5 Pro

Evidence level: **Anecdotal - 1 formal high-difficulty production-deployment run**

### Approved

- Strictly read-only repository and provider diagnosis.
- Narrow evidence recovery with no live mutation.
- Low-risk repository inspection under controller review.

### Conditional

- Narrow routine repository changes in a branch, with exact scope and independent review.
- Tracker comments only when the controller independently verifies the resulting body and encoding.

### Not currently approved

- Autonomous production deployment or provider mutation.
- Repeated operational retries without root-cause evidence.
- Independent tracker-body authority.
- Authentication, database, DNS or environment mutation without a stronger verified record.

### Promotion condition

Before another mutating production task, MiMo must pass the current Project A read-only evidence-recovery and build-diagnosis task with:

- complete non-secret identifiers and timestamps in private controller evidence;
- exact API/log evidence;
- correct distinction between authentication-provider evidence sources;
- no unsupported PASS claims;
- verified issue-body updates with clean UTF-8 text;
- no prohibited operation.

## Claude Opus 4.8

Evidence level: **Anecdotal - 2 formal high-difficulty complex-repository-change runs**

### Approved

- Complex repository implementation in an isolated branch or worktree.
- Multi-language contract and test changes with exact revision evidence.
- Draft pull-request preparation with no live-system mutation.
- Review remediation where every amended head receives independent controller review.

### Conditional

- Atomicity-sensitive, migration-adjacent or write-capable repository work only when the change remains draft and unmerged until exact-head acceptance.
- Package, ledger and durable-state changes only with explicit race, crash and no-clobber tests.
- Green tests and continuous integration are supporting evidence, not an acceptance decision.

### Not currently approved

- One-prompt autonomous merge for high-risk repository changes.
- Self-approval based on test or continuous-integration success alone.
- Autonomous production mutation.
- Skipping a fresh exact-head review after a same-domain amendment.

### Current evidence

The first evaluated run delivered a strong core implementation and complete revision/test evidence but required three material corrections. The first amendment closed those findings yet introduced a same-root atomic-publication defect. Both runs preserved a verified safe draft state and performed zero live-system actions, but neither achieved first-pass acceptance.

### Promotion condition

Before this task class can be treated as independently merge-ready, Claude Opus 4.8 must:

- implement atomic no-replace publication through a complete temporary file;
- prove race and failure cleanup without exposing partial final output;
- close the current same-root defect without introducing another atomicity or evidence defect;
- receive an accepted exact-head controller review;
- maintain zero unauthorised live-system actions.

## Sol Medium

Evidence level: **Prior programme experience; formal run backfill pending**

### Provisional use

- Routine implementation, tests, documentation and bounded configuration changes.
- Independent exact-head review still required.

### Restrictions

- No autonomous production mutation.
- Security, authentication, migration and complex operational work should normally use a stronger reasoning mode.

## Sol High

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
- public records use opaque subject aliases;
- no secret or private-identity disclosure;
- explicit mutation authorisation;
- independent controller review;
- complete evidence appropriate to the task;
- project tracker reconciliation;
- evaluation-ledger update before the next prompt.
