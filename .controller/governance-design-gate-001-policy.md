## Xiaomi MiMo 2.5 Pro

Reasoning level: **Provider default across 16 formal runs**

Evidence level: **Useful mixed-task operating baseline across 16 formal runs; provisional across 3 comparable incident-diagnosis runs, 3 provider-operation runs and 5 security-remediation runs; anecdotal across 2 complex-repository-change runs and 1 high-difficulty architecture-proposal run**

Observed scores:

- production deployment, high difficulty: **2.25/5**;
- routine repository change, low difficulty: **4.60/5**;
- incident diagnosis, high difficulty: **3.47/5** across 3 runs;
- provider operation, high difficulty: **3.56/5** across 3 runs;
- security remediation, high difficulty: **3.50/5** across 5 runs;
- complex repository change: **3.16/5** across 2 runs;
- architecture proposal, high difficulty: **4.40/5** across 1 run;
- mixed-task average: **3.51/5**;
- first-pass acceptance: **6.25%**;
- verified safe final state: **8/15 applicable runs**.

### Approved

- Strictly read-only repository or provider inspection where direct evidence is available.
- No-mutation architecture packets that surface root causes, viable options, trade-offs, blast radius and unresolved decisions for independent controller lock.
- Narrow mechanical repository changes with exact file scope and mandatory controller review.
- Low-risk overflow work that does not block release, mutate production or control authentication, data or deployment boundaries.
- Substantial draft-only repository implementation may be attempted only when the owner expressly authorises the experiment and every revision receives full controller review.

### Conditional

- Architecture proposals are advisory inputs; the controller must correct and lock authority, state, metadata and failure semantics before implementation.
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
- Independent tracker-body or controller-design-lock authority.
- Exact root-cause or PASS claims based on repository inspection without direct execution evidence.
- Autonomous acceptance of governance, policy, schema, validation or audit trust boundaries.
- Treating generated views, caller-supplied derived metadata or candidate-authored tests as independent authority.
- Further MiMo repair of the current governance trust boundary without an explicit controller lock and owner-authorised Gate 3 implementation.

### Current evidence

Across 16 formal mixed-task runs, MiMo consistently respected explicit no-mutation boundaries and was strongest on narrow mechanical work. One run achieved first-pass acceptance: the no-mutation governance architecture packet. Repeated implementation defects still include premature PASS claims, incomplete negative-path coverage, tracker corruption, unsupported root-cause conclusions, trust-boundary drift and adversarial tests that do not isolate the claimed boundary.

The first governance implementation run produced a coherent module and broad test surface but left canonical policy/schema authority and derived-state self-certification P1s. Amendment 1 made useful local improvements yet both original trust boundaries survived. The runtime still partially reimplements schema and policy semantics, canonical and published surfaces visibly drift, a checklist contradiction test passes through an unrelated acceptance contradiction, complete children remain under-validated and the lifecycle contract is mainly documentary.

The subsequent Gate 1 architecture run was materially stronger. It correctly identified the missing policy-to-runtime authority link and semantic-parity contract, rejected another partial handwritten validator, proposed maintained JSON Schema execution, active side-effect interception and isolated adversarial tests, and preserved the exact no-mutation boundary. The controller still had to correct four design details: complete-child type/state conflation, branch-versus-PR metadata semantics, duplicate-ID classification and false coupling of module and policy version domains.

The latest provider preflight also stopped safely when authorisation and provider access were unavailable, but misclassified a Git-dirty checkout as clean and produced no direct provider proof. This reinforces that safe stopping and bounded architecture proposals are strengths while exact execution evidence and final design authority remain controller-owned.

### Current disposition

MiMo is approved as a bounded repository investigator and architecture-option generator, and may mechanically implement a controller-locked design on a draft branch. It is not independently authoritative for security, durability, policy/schema or production architecture. For the current governance PR, continue only under the exact Gate 2 design lock and review the resulting Gate 3 head before merge.

