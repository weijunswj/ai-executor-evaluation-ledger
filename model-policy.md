# Model-Use Policy

Updated: 24 July 2026 (SGT)

This policy translates verified evaluation evidence into current operating boundaries. It does not claim that any model is permanently good or bad; permissions should tighten or loosen as comparable evidence accumulates.

## Xiaomi MiMo 2.5 Pro

Evidence level: **Provisional across 3 formal mixed-task runs; one run per task class**

Observed scores:

- production deployment, high difficulty: **2.25/5**;
- routine repository change, low difficulty: **4.60/5**;
- incident diagnosis, high difficulty: **3.63/5**.

### Approved

- Strictly read-only repository and provider inspection.
- Narrow evidence recovery with no live mutation.
- Bounded low-risk repository configuration changes in a branch.
- Mechanical implementation with exact file and behaviour scope.

### Conditional

- Complex repository repair when the controller supplies explicit invariants, negative tests and stop conditions.
- Tracker comments and bodies only when the controller independently checks the resulting content and encoding.
- Incident diagnosis only when exact log or API evidence is available; inferred root causes must be labelled as hypotheses.

### Not currently approved

- Autonomous production deployment or provider mutation.
- Repeated operational retries without new evidence.
- Independent tracker-body authority.
- Authentication, database, DNS or environment mutation.
- Declaring an exact root cause or PASS gate from repository inspection alone when direct provider evidence is missing.
- Broad fail-open repairs that weaken provenance, revision binding or safety assertions.

### Current promotion condition

Before MiMo receives another mutating production task, it must complete at least one bounded high-difficulty repository repair with:

- exact failing behaviour reproduced;
- secure invariants preserved rather than bypassed;
- complete tests for positive, negative and mismatch cases;
- exact-head continuous integration;
- no corrupted or premature tracker updates;
- an independently accepted controller review.

The next eligible task is the Project A build-provenance repair. Deployment and provider configuration remain separate and prohibited during that repair.

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
- private project tracker reconciliation;
- evaluation-ledger update before the next prompt.