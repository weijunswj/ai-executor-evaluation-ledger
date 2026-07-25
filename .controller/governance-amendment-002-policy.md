## Xiaomi MiMo 2.5 Pro

Reasoning level: **Provider default across 15 formal runs**

Evidence level: **Useful mixed-task operating baseline across 15 formal runs; provisional across 3 comparable incident-diagnosis runs, 3 provider-operation runs and 5 security-remediation runs; anecdotal across 2 complex-repository-change runs**

Observed scores:

- production deployment, high difficulty: **2.25/5**;
- routine repository change, low difficulty: **4.60/5**;
- incident diagnosis, high difficulty: **3.47/5** across 3 runs;
- provider operation, high difficulty: **3.56/5** across 3 runs;
- security remediation, high difficulty: **3.50/5** across 5 runs;
- complex repository change: **3.16/5** across 2 runs;
- mixed-task average: **3.45/5**;
- first-pass acceptance: **0%**;
- verified safe final state: **7/14 applicable runs**.

### Approved

- Strictly read-only repository or provider inspection where direct evidence is available.
- Narrow mechanical repository changes with exact file scope and mandatory controller review.
- Low-risk overflow work that does not block release, mutate production or control authentication, data or deployment boundaries.
- Substantial draft-only repository implementation may be attempted only when the owner expressly authorises the experiment and every revision receives full controller review.

### Conditional

- Tracker writes require immediate controller fetch-back and correction.
- Root-cause conclusions must be labelled as hypotheses unless supported by direct logs or provider evidence.
- Historical nonexistence claims must be bounded to the inspected state and evidence-retention window.
- Green tests and continuous integration are supporting evidence only; they do not authorise self-acceptance.
- Policy, schema, audit and generated-surface work must prove one trusted authority, reject candidate self-certification and isolate every adversarial oracle.
- Amendment cycles remain on the same implementation PR and each separately reviewed run receives its own evaluation packet.

### Not currently approved

- Further launch-critical implementation for the current private application programmes.
- Authentication, database, migration, DNS, environment, certificate or deployment mutation.
- Autonomous merge, deployment, rollback or provider operation.
- Independent tracker-body authority.
- Exact root-cause or PASS claims based on repository inspection without direct execution evidence.
- Autonomous acceptance of governance, policy, schema, validation or audit trust boundaries.
- Treating generated views, caller-supplied derived metadata or candidate-authored tests as independent authority.
- Further MiMo repair of the current governance trust boundary without an explicit owner decision accepting another non-convergent cycle.

### Current evidence

Across 15 formal mixed-task runs, MiMo consistently respected explicit no-mutation boundaries and was strongest on narrow mechanical work. No run achieved first-pass acceptance. Repeated defects include premature PASS claims, incomplete negative-path coverage, tracker corruption, unsupported root-cause conclusions, trust-boundary drift and adversarial tests that do not isolate the claimed boundary.

The first governance run produced a coherent module and broad test surface but left canonical policy/schema authority and derived-state self-certification P1s. Amendment 1 made useful local improvements yet both original trust boundaries survived. The runtime still partially reimplements schema and policy semantics, canonical and published surfaces visibly drift, a checklist contradiction test passes through an unrelated acceptance contradiction, complete children remain under-validated and the lifecycle contract is mainly documentary.

The latest provider preflight also stopped safely when authorisation and provider access were unavailable, but misclassified a Git-dirty checkout as clean and produced no direct provider proof. This reinforces that safe stopping is a strength while exact evidence and terminal claims still require controller correction.

### Current disposition

MiMo remains useful for bounded overflow and draft-only mechanical work. The current governance trust-boundary repair did not converge after Amendment 1. Continue that same draft change with a stronger owner-approved executor or a controller-specified redesign rather than another cosmetic MiMo cycle. Every material finding remains controller-owned and merge remains prohibited until a fresh exact-head review accepts the root-cause repairs.

