# Model-Use Policy

Updated: 26 July 2026, 00:26 SGT

This policy translates verified evaluation evidence into current operating boundaries. It does not claim that any model is permanently good or bad; permissions should tighten or loosen as comparable evidence accumulates.

## Xiaomi MiMo 2.5 Pro

Reasoning level: **Provider default across 19 formal runs**

Evidence level: **Useful mixed-task operating baseline across 19 formal runs; provisional across 3 comparable incident-diagnosis runs, 5 provider-operation runs, 5 security-remediation runs and 3 complex-repository-change runs; anecdotal across 1 high-difficulty architecture-proposal run**

Observed scores:

- production deployment, high difficulty: **2.25/5**;
- routine repository change, low difficulty: **4.60/5**;
- incident diagnosis, high difficulty: **3.47/5** across 3 runs;
- provider operation, high difficulty: **3.55/5** across 5 runs;
- security remediation, high difficulty: **3.50/5** across 5 runs;
- complex repository change, medium difficulty: **3.26/5** across 1 run;
- complex repository change, high difficulty: **3.23/5** across 2 runs;
- architecture proposal, high difficulty: **4.40/5** across 1 run;
- mixed-task average: **3.51/5**;
- first-pass acceptance: **5.26%**;
- verified safe final state: **9/18 applicable runs**.

### Approved

- Strictly read-only repository or provider inspection where direct evidence is available.
- No-mutation architecture packets that surface root causes, viable options, trade-offs, blast radius and unresolved decisions for independent controller lock.
- Narrow mechanical repository changes with exact file scope and mandatory controller review.
- Low-risk overflow work that does not block release, mutate production or control authentication, data or deployment boundaries.

### Conditional

- Architecture proposals are advisory inputs; the controller must correct and lock authority, state, metadata and failure semantics before implementation.
- Provider-setting conclusions must inspect the exact versioned schema relation and actual instance row; absence from a top-level response or adjacent table is not evidence that a setting does not exist.
- Draft-only mechanical implementation of a controller lock requires explicit owner authorisation and complete exact-head review; it is not independent design or acceptance authority.
- Tracker writes require immediate controller fetch-back and correction.
- Root-cause conclusions must be bounded to direct evidence and labelled as hypotheses where proof is incomplete.
- Green tests and continuous integration are supporting evidence only.
- Policy, schema and audit work must use executable parity and mutation-sensitive exact oracles rather than code-string presence or candidate-authored self-certification.
- A same-root material finding after a locked implementation returns the task to architecture rather than another ordinary amendment.

### Not currently approved

- Further MiMo implementation of the current governance trust boundary without a revised controller lock, explicit owner reauthorisation and a fresh exact-head review.
- Authentication, database, migration, DNS, environment, certificate or deployment mutation.
- Declaring provider admission PASS while required setting-row, migration, privilege or authentication-client evidence remains blocked.
- Autonomous merge, deployment, rollback or provider operation.
- Independent tracker-body, design-lock or policy/schema acceptance authority.
- Treating generated views, derived metadata, parity scripts or candidate-authored tests as independent authority.

### Current evidence

Across 19 formal mixed-task runs, MiMo consistently respected explicit no-mutation boundaries and was strongest on narrow mechanical work. One run achieved first-pass acceptance: the no-mutation governance architecture packet. Repeated implementation defects include premature PASS claims, incomplete negative-path coverage, tracker corruption, unsupported root-cause conclusions, trust-boundary drift and adversarial tests that do not isolate the claimed boundary.

The latest provider-admission amendment again preserved the zero-mutation boundary and recovered useful host evidence, but inspected the wrong provider schema relation, misclassified an invalid buildpack override, contradicted its own authority count and proposed an overbroad write before mandatory provider gates were complete.

The governance Gate 3 implementation made real progress by executing the canonical schema through Ajv, separating structural profile from lifecycle state and deriving required dimensions from policy. Gate 4 nevertheless found the same root defect in a lower layer: semantic parity and finding tests remain self-certifying, body-derived relationship and acceptance authority remains bypassable, and amendment or replacement lifecycle semantics remain partly documentary. Side-effect and diagnostic proof also remain incomplete.

### Current disposition

MiMo remains approved as a bounded investigator, no-mutation architecture-option generator and low-risk mechanical implementer. It is not independently authoritative for security, durability, policy/schema, authentication or production architecture. For the current governance PR, use a narrow architecture reset and a revised controller lock; a stronger owner-approved executor should perform the next implementation by default.

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

Evidence level: **Provisional - 3 formal high-difficulty complex-repository-change runs**

Observed scores:

- fourth amendment: **3.15/5**;
- fifth amendment: **3.38/5**;
- sixth amendment: **3.65/5**;
- comparable average: **3.39/5**;
- first-pass acceptance: **0%**;
- verified safe draft state: **3/3**.

### Approved

- Narrow high-risk repository remediation in an isolated branch or worktree.
- Exact-head code, test and continuous-integration evidence for independent controller review.
- Draft pull-request and tracker updates with no live-system mutation.
- Directional durable-state redesign where every committed boundary remains independently reviewed.

### Conditional

- Package, ledger, reservation, reviewer-decision and filesystem-durability changes only while draft and unmerged.
- Reviewer authority and irreversible package intent must be joined by one transactional serialization boundary rather than a stale read followed by a later filesystem claim.
- Existing state stores must match the complete canonical schema and constraints; validating names alone is insufficient.
- Every authority timestamp must be timezone-aware and validated before comparison or hashing.
- Tests must model build-versus-decision interleavings, persistence failures, malformed durable state and hostile name-compatible schemas.
- Green tests, mutation tests and continuous integration remain supporting evidence only.

### Not currently approved

- Autonomous merge or self-acceptance of durable-state or write-capable changes.
- Treating an authority snapshot as current after releasing the transaction that produced it.
- Allowing a concurrent hold, rejection or pending decision to overtake a build before authorisation is exclusively claimed.
- Silently augmenting an existing empty, foreign or partial state database.
- Trusting trigger, index or table names without verifying their semantics and constraints.
- Accepting timezone-naive authority timestamps or allowing malformed state to escape as an uncontrolled exception.
- Autonomous production mutation or package creation from private operational data.

### Current evidence

Amendment 6 made substantial architectural progress: reviewer authority now requires a committed SQLite activation row, uncertain COMMIT returns are resolved by reopening the store, JSONL is audit-only, reservation collisions are truthful and supported audit shapes are checked. It still leaves a launch-blocking authority race because the build releases SQLite after reading approval and only later creates its filesystem reservation. A newer hold, rejection or pending decision can therefore overtake the stale snapshot. Canonical store validation also remains incomplete, and timezone-naive timestamps can escape the sanitised error path.

### Promotion condition

The next narrowly scoped Max amendment must atomically re-resolve the latest decision and insert an append-only build-authorisation claim in one SQLite transaction; serialize decision writers and build claims; retain the filesystem reservation; create schema only for a path proven absent; validate exact table, trigger, index, foreign-key, uniqueness and CHECK semantics; reject extra application objects; require timezone-aware decision, activation and audit timestamps; prove the boundaries through paused build-versus-decision interleavings and hostile-store tests; remain draft and unmerged; and receive an accepted exact-head controller review.

Max is already the highest owner-approved tier. Further progress must come from tighter transactional design and adversarial review, not a higher reasoning label.

## DeepSeek V4 Pro

Evidence level: **Anecdotal — 2 formal high-difficulty architecture and research runs**

Observed scores:

- scheduled batch-review architecture proposal: **4.14/5**;
- governance architecture reset: **3.94/5**;
- two-run average: **4.04/5**;
- first-pass acceptance: **50%**;
- verified safe final state: **2/2**.

### Approved

- Exact-revision, no-mutation repository architecture packets.
- Authority mapping, root-cause analysis, option comparison, threat modelling and adversarial test planning for controller adjudication.
- Narrow architecture resets that preserve the existing branch, pull request and mutation boundary.

### Conditional

- Architecture recommendations remain advisory and require an independent controller lock before implementation.
- Executable parity must be proven through a policy-keyed detector registry and independent exact oracles, not a second declared reachability list.
- Mutation-sensitive tests require an explicit test-only injection seam; preload string searches or inaccessible lexical monkeypatches are insufficient.
- Body-authority designs must encode replacement reason and supersession identity in canonical issue-body fields and cross-check structured data.
- Side-effect absence must use controlled local sentinels or fakes and must not depend on real external DNS or network effects.
- Workflow dependency closure requires deterministic installation or a mechanical dependency proof; documentation comments alone are insufficient.

### Not currently approved

- Independently locking or implementing security, privacy, append-only, lifecycle or trusted-workflow authority boundaries.
- Treating exported reachability metadata, candidate-authored fixture manifests or green tests as independent proof.
- Exposing transformed private issue identifiers in public diagnostics.
- Implementing the current governance reset until the controller replaces the incomplete architecture choices.

### Current evidence

The first run produced a useful scheduled-review architecture proposal but required controller replacement of private-source resolution, batch discovery, durable publication, trusted validation and recovery choices. The second run accurately diagnosed the surviving Toolkit governance defects and produced a strong inventory, authority map and blast radius. It still proposed a self-certified runtime reachability export, a mutation method that cannot patch the current lexical detectors, incomplete replacement-body and lifecycle semantics, unsafe real-effect side-effect probes, transformed caller identifiers in diagnostics and comment-only dependency control.

### Current disposition

DeepSeek V4 Pro remains approved for bounded no-mutation architecture investigation and option generation. Before implementation, the controller must lock the executable detector registry, exact oracle tuples, canonical replacement body fields, full lifecycle state machine, controlled side-effect harness, opaque diagnostic references and deterministic workflow dependencies. Provider-native reasoning is not part of future public model identity; earlier legacy metadata remains pending the dedicated base-model migration.

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
