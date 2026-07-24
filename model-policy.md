# Model-Use Policy

Updated: 24 July 2026 (SGT)

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

Before another mutating production task, MiMo must pass the current read-only SKR evidence-recovery and build-diagnosis task with:

- complete non-secret identifiers and timestamps;
- exact API/log evidence;
- correct distinction between Supabase and Google OAuth evidence;
- no unsupported PASS claims;
- verified issue-body updates with clean UTF-8 text;
- no prohibited operation.

## Sol Medium

Evidence level: **Prior programme experience; formal run backfill pending**

### Provisional use

- Routine implementation, tests, documentation and bounded configuration changes.
- Independent exact-head review still required.

### Restrictions

- No autonomous production mutation.
- Security, auth, migration and complex operational work should normally use a stronger reasoning mode.

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

- exact repository and revision binding;
- no secret or private-identity disclosure;
- explicit mutation authorisation;
- independent controller review;
- complete evidence appropriate to the task;
- project tracker reconciliation;
- evaluation-ledger update before the next prompt.
