# Executor Scorecard

Updated: 26 July 2026, 23:40 SGT

This scorecard is generated from controller-verified records in `evaluations.jsonl`. Aggregate scores use the complete append-only history. Public project references use opaque aliases. Correction records relabel existing runs and do not count as additional formal runs.

<!-- GENERATED:SCORECARD-RUNS:START -->
## Summary score table

| Model | Formal runs | Average /5 | First-pass acceptance | Safe final state verified | Integrity/control flags | Evidence level |
|---|---:|---:|---:|---:|---:|---|

## Formal evaluated runs

Newest first. This table displays at most 30 formal evaluation runs.

| Reviewed | Model | Task class | Difficulty | Verdict | Score /5 | First-pass | Safe final state |
|---|---|---|---|---|---:|---:|---|
| 26 Jul 2026 23:40 SGT | DeepSeek V4 Pro | Security Remediation | High | ACCEPTED | 4.34 | No | Verified |
| 26 Jul 2026 23:40 SGT | DeepSeek V4 Pro | Security Review | High | AMEND | 3.49 | No | Verified |
| 26 Jul 2026 23:20 SGT | GPT-5.6 Sol | Security Audit | High | ACCEPTED | 4.74 | Yes | Verified |
| 26 Jul 2026 22:19 SGT | GPT-5.6 Sol | Research | High | AMEND | 4.32 | No | Verified |
| 26 Jul 2026 21:46 SGT | GPT-5.6 Sol | Research | High | AMEND | 4.09 | No | Verified |
| 26 Jul 2026 21:45 SGT | GPT-5.6 Sol | Research | High | ACCEPTED | 4.73 | Yes | Verified |
| 26 Jul 2026 21:42 SGT | GPT-5.6 Sol | Hosted Product Uat | Medium | AMEND | 4.20 | No | Verified |
| 26 Jul 2026 21:42 SGT | DeepSeek V4 Pro | Security Review | High | AMEND | 3.48 | No | Verified |
| 26 Jul 2026 21:42 SGT | DeepSeek V4 Pro | Security Remediation | High | AMEND | 3.49 | No | Verified |
| 26 Jul 2026 21:38 SGT | DeepSeek V4 Pro | Production Operations | High | ACCEPTED | 4.85 | Yes | Verified |
| 26 Jul 2026 21:25 SGT | DeepSeek V4 Pro | Research | High | AMEND | 3.38 | No | Verified |
| 26 Jul 2026 21:18 SGT | DeepSeek V4 Pro | Hosted Product Uat | Medium | ACCEPTED | 4.89 | Yes | Verified |
| 26 Jul 2026 20:56 SGT | DeepSeek V4 Pro | Hosted Product Uat | High | AMEND | 3.50 | No | Verified |
| 26 Jul 2026 20:55 SGT | DeepSeek V4 Pro | Production Operations | High | ACCEPTED | 4.72 | Yes | Verified |
| 26 Jul 2026 20:47 SGT | GPT-5.6 Sol | Research | High | AMEND | 4.19 | No | Verified |
| 26 Jul 2026 20:46 SGT | GPT-5.6 Sol | Research | High | AMEND | 4.13 | No | Verified |
| 26 Jul 2026 20:31 SGT | GPT-5.6 Sol | Research | High | AMEND | 4.28 | No | Verified |
| 26 Jul 2026 20:24 SGT | DeepSeek V4 Pro | Production Deployment | High | ACCEPTED | 4.59 | Yes | Verified |
| 26 Jul 2026 20:22 SGT | DeepSeek V4 Pro | Production Operations | High | AMEND | 3.84 | No | Verified |
| 26 Jul 2026 20:12 SGT | DeepSeek V4 Pro | Research | High | AMEND | 3.83 | No | Verified |
| 26 Jul 2026 20:05 SGT | DeepSeek V4 Pro | Production Operations | High | ACCEPTED | 4.23 | Yes | Verified |
| 26 Jul 2026 20:04 SGT | DeepSeek V4 Pro | Security Architecture Audit | High | AMEND | 4.01 | No | Verified |
| 26 Jul 2026 20:03 SGT | DeepSeek V4 Pro | Incident Diagnosis | High | ACCEPTED | 4.87 | Yes | Verified |
| 26 Jul 2026 19:54 SGT | DeepSeek V4 Pro | Complex Repository Change | High | AMEND | 2.75 | No | Verified |
| 26 Jul 2026 19:22 SGT | GPT-5.6 Sol | Security Remediation | High | AMEND | 3.93 | No | Verified |
| 26 Jul 2026 19:18 SGT | GPT-5.6 Sol | Security Remediation | High | AMEND | 3.67 | No | Verified |
| 26 Jul 2026 19:12 SGT | GPT-5.6 Sol | Complex Repository Change | High | ACCEPTED | 4.77 | Yes | Verified |
| 26 Jul 2026 19:05 SGT | GPT-5.6 Sol | Complex Repository Change | High | AMEND | 4.11 | No | Verified |
| 26 Jul 2026 18:20 SGT | DeepSeek V4 Pro | Research | High | PASS | 4.42 | Yes | Verified |
| 26 Jul 2026 15:32 SGT | Claude Opus 5 | Complex Repository Change | High | AMEND | 4.24 | No | Verified |

## Task-class aggregates

| Model | Task class | Difficulty | Runs | Average /5 | First-pass acceptance | Confidence |
|---|---|---|---:|---:|---:|---|
| Claude Opus 5 | Architecture Proposal | High | 1 | 4.35 | 100% | Anecdotal |
| Claude Opus 5 | Complex Repository Change | High | 5 | 3.66 | 0% | Provisional |
| DeepSeek V4 Pro | Architecture Proposal | High | 1 | 4.14 | 100% | Anecdotal |
| DeepSeek V4 Pro | Complex Repository Change | High | 1 | 2.75 | 0% | Anecdotal |
| DeepSeek V4 Pro | Hosted Product Uat | High | 1 | 3.50 | 0% | Anecdotal |
| DeepSeek V4 Pro | Hosted Product Uat | Medium | 1 | 4.89 | 100% | Anecdotal |
| DeepSeek V4 Pro | Incident Diagnosis | High | 1 | 4.87 | 100% | Anecdotal |
| DeepSeek V4 Pro | Production Deployment | High | 1 | 4.59 | 100% | Anecdotal |
| DeepSeek V4 Pro | Production Operations | High | 4 | 4.41 | 75% | Provisional |
| DeepSeek V4 Pro | Research | High | 6 | 3.97 | 17% | Moderate |
| DeepSeek V4 Pro | Security Architecture Audit | High | 1 | 4.01 | 0% | Anecdotal |
| DeepSeek V4 Pro | Security Remediation | High | 2 | 3.92 | 0% | Anecdotal |
| DeepSeek V4 Pro | Security Review | High | 2 | 3.49 | 0% | Anecdotal |
| GPT-5.6 Sol | Complex Repository Change | High | 2 | 4.44 | 50% | Anecdotal |
| GPT-5.6 Sol | Hosted Product Uat | Medium | 1 | 4.20 | 0% | Anecdotal |
| GPT-5.6 Sol | Research | High | 6 | 4.29 | 17% | Moderate |
| GPT-5.6 Sol | Security Audit | High | 1 | 4.74 | 100% | Anecdotal |
| GPT-5.6 Sol | Security Remediation | High | 2 | 3.80 | 0% | Anecdotal |
| MiMo 2.5 Pro | Architecture Proposal | High | 1 | 4.53 | 100% | Anecdotal |
| MiMo 2.5 Pro | Complex Repository Change | High | 2 | 3.38 | 0% | Anecdotal |
| MiMo 2.5 Pro | Complex Repository Change | Medium | 1 | 3.26 | 0% | Anecdotal |
| MiMo 2.5 Pro | Incident Diagnosis | High | 3 | 3.47 | 0% | Provisional |
| MiMo 2.5 Pro | Production Deployment | High | 1 | 2.25 | 0% | Anecdotal |
| MiMo 2.5 Pro | Provider Operation | High | 5 | 3.56 | 0% | Provisional |
| MiMo 2.5 Pro | Routine Repository Change | Low | 1 | 4.60 | 0% | Anecdotal |
| MiMo 2.5 Pro | Security Remediation | High | 5 | 3.52 | 0% | Provisional |

## Latest formal evaluations

Newest first. This section displays at most 30 formal evaluation runs.

### DeepSeek V4 Pro - Security Remediation

- Reviewed: **26 Jul 2026 23:40 SGT**
- Run ID: `2026-07-26-deepseek-v4-pro-shared-platform-a-hostname-contract-amendment-006`
- Subject alias: `shared-platform-a`
- Result: **ACCEPTED**
- Weighted score: **4.34/5**
- First-pass accepted: **No**
- Safe final state: **Verified**
- Principal strengths:
  - closed every prior controller finding with bounded source and test changes
  - updated all stale provider-evidence integration fixtures and passed the complete hosted test workflow
  - enforced exact provider identity, per-label bounds, final authority bounds and independent pooled-label overflow rejection
  - preserved the no-production-access boundary and merged through an exact-head guard
- Principal defects:
  - the executor declared PASS while exact-head continuous integration was still pending
  - the claimed complete changed-file list described only the amendment delta rather than all files in the change
  - the pull-request and issue text contained escape and control-character corruption that required controller repair

### DeepSeek V4 Pro - Security Review

- Reviewed: **26 Jul 2026 23:40 SGT**
- Run ID: `2026-07-26-deepseek-v4-pro-private-quote-service-a-role-design-amendment-003`
- Subject alias: `private-quote-service-a`
- Result: **AMEND**
- Weighted score: **3.49/5**
- First-pass accepted: **No**
- Safe final state: **Verified**
- Principal strengths:
  - preserved the no-live-mutation boundary and destroyed the disposable test environment
  - replaced blanket runtime grants with mostly explicit object-level privileges
  - materially proved that trigger invocation does not require direct caller execute privilege
  - retained no-login-first creation and a rollback runtime role
- Principal defects:
  - the declared sole-authority manifest still disagrees with staged SQL for a publication table
  - the maintenance SQL omits read access to forensic child tables that repository retention logic queries
  - the target public privilege posture is not fully implemented by the proposed revokes
  - provider-administrator membership revocation remains bundled into the runtime-role plan despite explicit scope exclusion
  - directly authenticated denial of role assumption was inferred rather than executed
  - the terminal PASS claim is unsupported while these privilege and scope contradictions remain

### GPT-5.6 Sol - Security Audit

- Reviewed: **26 Jul 2026 23:20 SGT**
- Run ID: `2026-07-26-gpt-5-6-sol-public-web-app-a-production-dependency-audit-005`
- Subject alias: `public-web-app-a`
- Result: **ACCEPTED**
- Weighted score: **4.74/5**
- First-pass accepted: **Yes**
- Safe final state: **Verified**
- Principal strengths:
  - kept the audit strictly read-only and preserved a clean exact-main repository state
  - separated direct framework, transitive build-tool and optional native-runtime exposure instead of treating the audit summary as sufficient evidence
  - checked repository configuration and call sites against each advisory prerequisite while still requiring remediation of vulnerable installed code
  - produced a proportionate patch, override and native-compatibility remediation order with explicit uncertainty
  - replaced the authoritative security-gate issue body with a detailed current-state record rather than relying on comments
- Principal defects:
  - the complete npm audit JSON was not preserved in a controller-readable public-safe artefact, so the exact advisory aggregation count was accepted from the executor receipt rather than independently replayed

### GPT-5.6 Sol - Research

- Reviewed: **26 Jul 2026 22:19 SGT**
- Run ID: `2026-07-26-gpt-5-6-sol-repository-security-gate-gate1-amendment-002`
- Subject alias: `repository-security-gate-a`
- Result: **AMEND**
- Weighted score: **4.32/5**
- First-pass accepted: **No**
- Safe final state: **Verified**
- Principal strengths:
  - selected one first-party GitHub App publisher and defined signed dispatch OIDC terminal-report artifact and expected-source check authority
  - removed the repository-security-gate pull-request-target design in favour of protected default-branch dispatch
  - provided a detailed property map from all seven broad suites into purpose-built protected invariants or retained ordinary checks
  - preserved mandatory CodeQL and code-quality controls and normal-merge current-main integration
  - kept the repository clean and performed no App ruleset provider consumer credential or live-system mutation
- Principal defects:
  - the proposed auto-sync replacement remains a candidate-controlled pull-request workflow rather than protected default-branch or App-dispatched authority
  - the seven retained broad suites are called required even though Validate and Validate Toolkit are not bound as required expected-source checks in the current ruleset

### GPT-5.6 Sol - Research

- Reviewed: **26 Jul 2026 21:46 SGT**
- Run ID: `2026-07-26-gpt-5-6-sol-external-control-plane-gate1-amendment-001`
- Subject alias: `external-control-plane-a`
- Result: **AMEND**
- Weighted score: **4.09/5**
- First-pass accepted: **No**
- Safe final state: **Verified**
- Principal strengths:
  - selected an independent first-party authority service rather than retaining connector or process-local authority
  - defined signed compare-and-swap inventory and catalogue records with rollback detection and hardware-rooted service keys
  - separated parent revocation from the exact already-started operation's truthful terminalisation authority
  - removed connector self-authentication of action semantics through independently promoted catalogue records
  - selected a concrete Windows broker implementation and prohibited pathname, environment and unsupported-platform fallbacks
  - preserved a clean repository and performed no provider, consumer, credential, service, broker or production mutation
- Principal defects:
  - incrementing one physical hardware counter for every authority mutation lacks an exact throughput, rate-limit, queue and prepared-row recovery contract
  - the Windows broker does not atomically bind the authorised existing destination identity to the later replacement operation
  - a crash after output publication but before local consumption and authority-service acknowledgement has no durable restart or idempotent reconciliation state machine
  - the required cross-platform broker decision was replaced with an unapproved exclusion of every POSIX governed-output host
  - macOS enrolment names hardware-backed key storage without selecting an exact production-supported remote-attestation API and verification chain
  - service-key compromise and state-loss recovery rely on undefined trusted checkpoints and matching backups

### GPT-5.6 Sol - Research

- Reviewed: **26 Jul 2026 21:45 SGT**
- Run ID: `2026-07-26-gpt-5-6-sol-workflow-compatibility-gate1-amendment-001`
- Subject alias: `workflow-compatibility-a`
- Result: **ACCEPTED**
- Weighted score: **4.73/5**
- First-pass accepted: **Yes**
- Safe final state: **Verified**
- Principal strengths:
  - defined immutable one-record journal segments with exact framing, bounded rescue attempts and raw-object tail seals
  - selected a stable target-scoped journal root outside every renamed payload root and used only supported public runtime APIs
  - made logical retirement authoritative while keeping physical cleanup truthful, resumable and non-authoritative
  - bounded successful terminal history with alternating checkpoints, cumulative roots and explicit residue limits
  - preserved phase progression, destructive-boundary revalidation, one healthy classification and normal-merge current-main integration
  - kept the repository clean and performed no installed-cache, consumer, credential, provider or live-system action
- Principal defects:
  - none recorded

### GPT-5.6 Sol - Hosted Product Uat

- Reviewed: **26 Jul 2026 21:42 SGT**
- Run ID: `2026-07-26-gpt-5-6-sol-public-web-app-a-rendered-walkthrough-004`
- Subject alias: `public-web-app-a`
- Result: **AMEND**
- Weighted score: **4.20/5**
- First-pass accepted: **No**
- Safe final state: **Verified**
- Principal strengths:
  - used a real rendered browser and covered every required route at all required viewports plus narrow reflow
  - identified five concrete P2 product and accessibility repair lanes with reproduction details
  - kept login submission provider deployment database and tracked-file mutation boundaries intact
  - reported browser capability limits instead of claiming complete keyboard or developer-tools coverage
- Principal defects:
  - did not re-read live provenance through an allowed separate read-only mechanism after in-app navigation was blocked
  - could not complete reliable Tab and Shift-Tab traversal
  - screenshot paths were local-only and unavailable to independent controllers
  - deleted local branches and attached worktrees despite a read-only walkthrough scope

### DeepSeek V4 Pro - Security Review

- Reviewed: **26 Jul 2026 21:42 SGT**
- Run ID: `2026-07-26-deepseek-v4-pro-private-quote-service-a-role-design-amendment-002`
- Subject alias: `private-quote-service-a`
- Result: **AMEND**
- Weighted score: **3.48/5**
- First-pass accepted: **No**
- Safe final state: **Verified**
- Principal strengths:
  - preserved the strict no-mutation boundary and produced a detailed execution-context inventory
  - correctly separated web runtime retention maintenance and migration authority into three roles
  - identified current public database schema and routine privilege excess
  - kept provider-admin role removal outside immediate runtime cutover
- Principal defects:
  - GRANT SELECT INSERT ON ALL TABLES gives the runtime INSERT on the migration ledger and retention-control tables despite explicit negative assertions
  - the staged SQL grants runtime DELETE on a retention-authorisation table that the capability matrix marks read-only
  - default SELECT and INSERT on every future table contradict the selected explicit per-migration strategy and can overgrant future administrative objects
  - the disposable trigger test plan does not yet prove the claimed runtime EXECUTE requirement for existing triggers
  - the cutover plan depends on SQL assertions that would fail against the grants proposed earlier in the same packet

### DeepSeek V4 Pro - Security Remediation

- Reviewed: **26 Jul 2026 21:42 SGT**
- Run ID: `2026-07-26-deepseek-v4-pro-shared-platform-a-hostname-contract-repair-005`
- Subject alias: `shared-platform-a`
- Result: **AMEND**
- Weighted score: **3.49/5**
- First-pass accepted: **No**
- Safe final state: **Verified**
- Principal strengths:
  - implemented the correct provider-attested proxy-host and region-identity architecture rather than widening label counts
  - included both new fields in normalised immutable identity and phase-drift fingerprints
  - preserved the no-production-access boundary and bounded draft pull-request scope
  - added useful legacy shard mismatch missing-field and drift tests
- Principal defects:
  - the packet and authoritative issue report a head that does not equal the actual pull-request head
  - complete continuous integration fails because the disposable PostgreSQL activation fixture lacks the new mandatory provider fields
  - the region grammar accepts a DNS label ending in a hyphen when provider region and proxy host agree
  - the shard label and final pooled authority lack complete DNS label and total-length enforcement

### DeepSeek V4 Pro - Production Operations

- Reviewed: **26 Jul 2026 21:38 SGT**
- Run ID: `2026-07-26-deepseek-v4-pro-shared-platform-a-provider-hostname-admission-004`
- Subject alias: `shared-platform-a`
- Result: **ACCEPTED**
- Weighted score: **4.85/5**
- First-pass accepted: **Yes**
- Safe final state: **Verified**
- Principal strengths:
  - revalidated exact repository, merged pull request and continuous-integration identities
  - admitted the provider API key without printing it and proved all exact provider target identities
  - identified the precise five-label-only contract branch that rejects the real shard-qualified provider hostname
  - stopped before connection-URI retrieval, canonical environment write, Docker, Bitwarden, database connection or role mutation
  - returned complete zero-mutation and cleanup evidence
- Principal defects:
  - the proposed repair focused on permitting a six-label shape rather than binding endpoint host and pooled-host derivation to provider-attested proxy_host and region_id fields

### DeepSeek V4 Pro - Research

- Reviewed: **26 Jul 2026 21:25 SGT**
- Run ID: `2026-07-26-deepseek-v4-pro-governance-tooling-a-architecture-reset-006`
- Subject alias: `governance-tooling-a`
- Result: **AMEND**
- Weighted score: **3.38/5**
- First-pass accepted: **No**
- Safe final state: **Verified**
- Principal strengths:
  - bound the packet to the exact public head and current main and respected the strict no-mutation boundary
  - correctly replaced the prior contradictory rebase direction with normal-merge integration on the existing branch
  - added explicit missing finding fixtures and broadened the side-effect and hosted-check inventories
  - reported the absence of a repository Public Safety command and the failing hosted validation checks honestly
- Principal defects:
  - compound-command parsing, reusable-workflow resolution, recursion tracking and package-root installation authority remained non-executable
  - the replacement graph used an edge direction and termination rule that reject a valid original-to-replacement chain
  - the detector mutation proof did not require exact equality to the expected multiset minus the target tuples
  - semantic reachability depended on a placeholder interception that would not replace detector-local destructured emitter references and could pass with zero calls
  - generated parity retained conflicting isolated and active-checkout write paths with no complete output-region manifest
  - the claimed sentinel count covered families rather than every listed entry point and included invalid or non-portable open-flag assumptions
  - the exact default CodeQL language and required check identity were not bound
  - the packet claimed no unresolved decisions despite explicit placeholders, malformed blast-radius paths and contradictory execution contracts

### DeepSeek V4 Pro - Hosted Product Uat

- Reviewed: **26 Jul 2026 21:18 SGT**
- Run ID: `2026-07-26-deepseek-v4-pro-public-web-app-a-browser-capability-003`
- Subject alias: `public-web-app-a`
- Result: **ACCEPTED**
- Weighted score: **4.89/5**
- First-pass accepted: **Yes**
- Safe final state: **Verified**
- Principal strengths:
  - revalidated the exact hosted revision and provenance before capability admission
  - explicitly inventoried browser binaries, automation, screenshots, developer-tools and accessibility-tree capabilities
  - correctly distinguished text-only HTTP tooling from rendered-browser evidence
  - returned the exact required blocked verdict rather than repeating unsupported visual claims
  - performed no login, submission, provider, database, deployment, repository or GitHub mutation
- Principal defects:
  - none recorded

### DeepSeek V4 Pro - Hosted Product Uat

- Reviewed: **26 Jul 2026 20:56 SGT**
- Run ID: `2026-07-26-deepseek-v4-pro-public-web-app-a-http-walkthrough-002`
- Subject alias: `public-web-app-a`
- Result: **AMEND**
- Weighted score: **3.50/5**
- First-pass accepted: **No**
- Safe final state: **Verified**
- Principal strengths:
  - revalidated the exact hosted provenance and principal public/admin-boundary route statuses
  - kept the run read-only with no login, quote, admin, provider, database, deployment or GitHub mutation
  - identified genuine content and product-flow gaps from public HTML
  - correctly preserved the unauthenticated admin boundary and Google admission hold
- Principal defects:
  - the required real-browser desktop, tablet and mobile walkthrough was not performed
  - no screenshots or rendered-layout evidence were produced
  - overflow, touch targets, focus, keyboard navigation, colour contrast, image presentation and layout shifts were explicitly unobserved but the run still returned PASS
  - mixed-content, broken-asset, hydration and network assertions were stronger than the reported text/HTTP evidence supported
  - the summary claimed ten public and three admin-boundary routes while the route table and categories did not reconcile
  - empty production catalogue content was labelled an expected MVP state despite the programme requirement for an actual company alpha rather than demo readiness

### DeepSeek V4 Pro - Production Operations

- Reviewed: **26 Jul 2026 20:55 SGT**
- Run ID: `2026-07-26-deepseek-v4-pro-shared-platform-a-canonical-operator-source-003`
- Subject alias: `shared-platform-a`
- Result: **ACCEPTED**
- Weighted score: **4.72/5**
- First-pass accepted: **Yes**
- Safe final state: **Verified**
- Principal strengths:
  - revalidated exact repository and continuous-integration identities before credential inspection
  - inspected the canonical operator file as data and proved the exact key was absent without printing file contents or values
  - distinguished the nonblank API key and blank unrelated placeholder from the missing operator connection URL
  - stopped before provider, database, Docker, Bitwarden, password, role, deployment or configuration mutation
  - returned complete zero-mutation and cleanup evidence
- Principal defects:
  - the proposed next step relied on manual operator installation even though the existing provider API key can support a bounded read-only official connection-URI recovery path

### GPT-5.6 Sol - Research

- Reviewed: **26 Jul 2026 20:47 SGT**
- Run ID: `2026-07-26-gpt-5-6-sol-repository-security-gate-gate1-reset-001`
- Subject alias: `repository-security-gate-a`
- Result: **AMEND**
- Weighted score: **4.19/5**
- First-pass accepted: **No**
- Safe final state: **Verified**
- Principal strengths:
  - preserved the independently verified separation between protected authority and candidate data
  - correctly replaced broad ordinary tests with a purpose-built protected-invariant direction
  - separated advisory post-promotion simulation from enforcement authority
  - defined a staged promotion sequence that keeps the required ruleset disabled until protected success
  - kept repository, ruleset, provider and consumer systems untouched
- Principal defects:
  - the packet leaves first-party App publication and retained-trigger suppression as materially different live alternatives
  - the active auto-sync dangerous-trigger finding remains unresolved and would still block a protected pass
  - the App-to-workflow-to-sealed-report-to-required-check authority and failure protocol is incomplete
  - the proposal would remove existing mandatory CodeQL and code-quality controls without a separate evidence-backed policy change
  - the security properties removed with the seven broad suites are not mapped exhaustively to exact protected invariant IDs
  - current-main integration does not explicitly preserve the reviewed branch through a normal merge

### GPT-5.6 Sol - Research

- Reviewed: **26 Jul 2026 20:46 SGT**
- Run ID: `2026-07-26-gpt-5-6-sol-external-control-plane-gate1-reset-001`
- Subject alias: `external-control-plane-a`
- Result: **AMEND**
- Weighted score: **4.13/5**
- First-pass accepted: **No**
- Safe final state: **Verified**
- Principal strengths:
  - independently confirmed all eight exact-head admission and authority defects
  - defined one canonical environment and risk authority with exact unknown-by-default action admission
  - replaced alias-only target matching and duplicated approval references with complete canonical authority
  - separated start, observation and terminal receipt concepts and preserved cross-route parity
  - kept repository, provider, credential and consumer systems untouched
- Principal defects:
  - the selected signed monotonic authority remains an unspecified external service without an exact protocol, key lifecycle or recovery model
  - the Windows handle-relative filesystem broker remains a category rather than a selected buildable trust boundary
  - approval revocation before terminalization can prevent truthful evidence for an already-started external operation
  - connector-supplied action catalogues lack an independent provenance and rollback authority
  - the proposed rebase integration would rewrite the heavily reviewed branch instead of normally merging current main

### GPT-5.6 Sol - Research

- Reviewed: **26 Jul 2026 20:31 SGT**
- Run ID: `2026-07-26-gpt-5-6-sol-workflow-compatibility-gate1-reset-001`
- Subject alias: `workflow-compatibility-a`
- Result: **AMEND**
- Weighted score: **4.28/5**
- First-pass accepted: **No**
- Safe final state: **Verified**
- Principal strengths:
  - independently reproduced the four exact-head transaction and performance defects and accurately mapped their call paths
  - proposed one coherent transaction-state-machine direction rather than four isolated patches
  - made phase-30 winner recognition explicit, added final destructive-boundary tree validation and removed the duplicate healthy classification
  - kept plugin refresh, installed-cache repair and consumer-repository helper propagation as separate authority domains
  - preserved a clean repository, made zero GitHub mutations and accessed no installed cache or live system
- Principal defects:
  - the append-only journal contract simultaneously treats a torn final append as a recoverable durable prefix and malformed evidence, leaving crash recovery undefined
  - the journal's exact stable placement and supported write-through adapter were not selected, so its authority and durability boundary are not implementable yet
  - retirement depends on preferred handle-bound Windows operations without selecting a supported implementation or a complete logical-retirement fallback
  - permanent journal tombstones are only count-bounded and can eventually exhaust future repair authority without an exact safe retention or compaction contract

### DeepSeek V4 Pro - Production Deployment

- Reviewed: **26 Jul 2026 20:24 SGT**
- Run ID: `2026-07-26-deepseek-v4-pro-public-web-app-a-source-commit-deployment-001`
- Subject alias: `public-web-app-a`
- Result: **ACCEPTED**
- Weighted score: **4.59/5**
- First-pass accepted: **Yes**
- Safe final state: **Verified**
- Principal strengths:
  - deployed the exact accepted revision and produced matching source-commit provenance without weakening repository validation
  - proved Node 24, mutation-disabled administration, automatic deployment disabled and the required public and unauthenticated-admin route behaviour
  - verified removed quote and workflow handoff variables were absent from the active runtime
  - replaced the stale prior container only after a successful build and required no rollback
  - performed no quote, admin, identity, application-database, DNS, TLS or repository mutation
- Principal defects:
  - the authorised native include-source-commit setting remained disabled and was replaced with a fixed SOURCE_COMMIT application environment value
  - the fixed revision value can become stale and mis-attest a later build unless it is updated atomically for every new target or replaced by native per-deployment source-revision injection

### DeepSeek V4 Pro - Production Operations

- Reviewed: **26 Jul 2026 20:22 SGT**
- Run ID: `2026-07-26-deepseek-v4-pro-shared-platform-a-operator-source-admission-002`
- Subject alias: `shared-platform-a`
- Result: **AMEND**
- Weighted score: **3.84/5**
- First-pass accepted: **No**
- Safe final state: **Verified**
- Principal strengths:
  - revalidated the exact repository main, merged pull request and accepted continuous-integration identity
  - checked the Process, User and Machine Windows environment scopes without exposing or transforming any value
  - stopped before provider access, database connection, Docker access, password generation, Bitwarden use or mutation
  - returned a complete zero-mutation statement and did not misrepresent any activation phase as started
- Principal defects:
  - the canonical shared operator source at %USERPROFILE%\.codex\.env was not inspected even though persistent Windows variables are not the default authority
  - absence from Process, User and Machine scopes was therefore misclassified as operator credential unavailability
  - controller injection or a manual paste path was proposed before exhausting the approved host-neutral operator environment authority

### DeepSeek V4 Pro - Research

- Reviewed: **26 Jul 2026 20:12 SGT**
- Run ID: `2026-07-26-deepseek-v4-pro-governance-tooling-a-architecture-reset-005`
- Subject alias: `governance-tooling-a`
- Result: **AMEND**
- Weighted score: **3.83/5**
- First-pass accepted: **No**
- Safe final state: **Verified**
- Principal strengths:
  - preserved the exact no-mutation boundary and correctly bound the packet to the unchanged pull-request head and advanced main
  - accurately identified the privileged-writeback validator conflict and the shallow workflow inventory root cause
  - provided useful architecture alternatives, a broad adversarial matrix and substantially improved replacement-chain and sentinel direction
  - reported the pull request as conflicting and retained the existing draft unmerged implementation authority
- Principal defects:
  - the proposed recursive inventory does not actually define executable traversal of local shell wrappers, compound package scripts or recursion-boundary workspace semantics
  - the mutation design does not first prove the immutable production entry, makes unrelated-tuple preservation conditional and explicitly retains a non-exact GOV015 expectation
  - the replacement graph and full body-authority algorithm omit material invariants while the packet leaves finding ownership as an unresolved controller decision
  - diagnostic parity relies on source regex and generated-surface parity mutates the active checkout instead of comparing isolated deterministic expected bytes
  - the integration sequence simultaneously permits rebase, forbids the required force update and requires descendant ancestry that a rebase cannot preserve
  - the side-effect plan lacks explicit numeric and string open-flag cases and complete deterministic asynchronous sentinels
  - the final validation matrix omits the repository's actual Public Safety proof and does not bind CodeQL claims to current required checks

### DeepSeek V4 Pro - Production Operations

- Reviewed: **26 Jul 2026 20:05 SGT**
- Run ID: `2026-07-26-deepseek-v4-pro-shared-platform-a-runtime-activation-preflight-001`
- Subject alias: `shared-platform-a`
- Result: **ACCEPTED**
- Weighted score: **4.23/5**
- First-pass accepted: **Yes**
- Safe final state: **Verified**
- Principal strengths:
  - revalidated the exact merged repository state and accepted continuous-integration result before attempting production access
  - stopped before provider access, database connection, password creation, secret-store write or any mutation
  - reported complete zero-mutation and temporary-resource state with no secret exposure
  - correctly identified the unavailable container runtime as a decisive activation-host blocker
- Principal defects:
  - absence from the current process environment was presented as absence of the operator credential without checking persistent user, machine or approved bootstrap sources
  - absence of one command-line client was presented as absence of all approved secret-store write capability
  - stale activation containers were reported absent even though the container daemon was unavailable and the inventory could not be observed
  - all three conditions were grouped as hardware or environment failures even though two were unresolved credential-source and tooling-admission questions

### DeepSeek V4 Pro - Security Architecture Audit

- Reviewed: **26 Jul 2026 20:04 SGT**
- Run ID: `2026-07-26-deepseek-v4-pro-private-quote-service-a-role-audit-001`
- Subject alias: `private-quote-service-a`
- Result: **AMEND**
- Weighted score: **4.01/5**
- First-pass accepted: **No**
- Safe final state: **Verified**
- Principal strengths:
  - proved the current application role lacks superuser, role-creation, database-creation, replication and row-security bypass authority
  - proved the runtime role owns no application objects and the migrator owns the canonical application tables and trigger functions
  - identified current excess data-modification grants on migration-ledger and append-only tables
  - kept the audit read-only with no password, grant, ownership, provider or deployment mutation and no secret exposure
- Principal defects:
  - the audit explicitly left transitive memberships, column grants, direct routine grants and legacy-administrator explicit grants incomplete while claiming full admission
  - the proposed broad table grants would give migration-ledger insert authority to the online runtime
  - the proposed future default grants would recreate update and delete access on immutable tables and execute access on every future function
  - the replacement migration and recovery administration path was not proven before proposing membership revocation
  - the legacy provider-administrator finding was overstated without proving provider support or a material reduction in its existing authority
  - the proposed role creation installed login credentials before exact privilege validation instead of using a no-login-first sequence
  - provider utility ownership and provider-role removal were included outside the bounded runtime-role migration scope

### DeepSeek V4 Pro - Incident Diagnosis

- Reviewed: **26 Jul 2026 20:03 SGT**
- Run ID: `2026-07-26-deepseek-v4-pro-public-web-app-a-build-root-cause-001`
- Subject alias: `public-web-app-a`
- Result: **ACCEPTED**
- Weighted score: **4.87/5**
- First-pass accepted: **Yes**
- Safe final state: **Verified**
- Principal strengths:
  - recovered the exact post-build provenance failure and correctly separated it from the successful application build
  - proved the missing revision input through hosted configuration, build arguments and repository call-path evidence
  - eliminated the runtime-version, dependency, resource and network hypotheses with direct evidence
  - performed no repository, provider, deployment, database, identity or application-data mutation
- Principal defects:
  - the proposed rollback wording initially suggested reverting the required source-revision setting after any later build failure rather than only after evidence that the setting itself was defective

### DeepSeek V4 Pro - Complex Repository Change

- Reviewed: **26 Jul 2026 19:54 SGT**
- Run ID: `2026-07-26-deepseek-v4-pro-governance-tooling-a-dl-299-310-002-implementation-001`
- Subject alias: `governance-tooling-a`
- Result: **AMEND**
- Weighted score: **2.75/5**
- First-pass accepted: **No**
- Safe final state: **Verified**
- Principal strengths:
  - preserved the exact authorised branch and draft unmerged pull-request state
  - created distinct code-specific detector modules and materially improved canonical policy and diagnostic structure
  - maintained a clean worktree and performed no live, credential, consumer or production action
  - left prior controller reviews unresolved and updated the implementation tracker and pull-request body
- Principal defects:
  - exact-head Validate and Validate toolkit checks failed, including a direct conflict between the new privileged-workflow npm installation and the repository's trusted writeback validator
  - the workflow inventory is a flat handwritten scanner and does not recursively traverse reusable workflows, local composite actions, shell wrappers, package-script chains and dynamic execution as locked
  - the fixture manifest covers only twenty-three of twenty-seven governance codes and mutation sensitivity is demonstrated only for GOV014 rather than every code
  - replacement-chain enforcement does not prove body and structured agreement, unknown predecessor rejection, broken or cyclic chain detection or superseded reactivation
  - generated-surface parity and side-effect interception evidence remain incomplete against the controller lock
  - the terminal file ledger understated the cumulative pull-request scope and the required full validation sequence was not completed

### GPT-5.6 Sol - Security Remediation

- Reviewed: **26 Jul 2026 19:22 SGT**
- Run ID: `2026-07-26-gpt-5-6-sol-repository-security-gate-a-amendment-001`
- Subject alias: `repository-security-gate-a`
- Result: **AMEND**
- Weighted score: **3.93/5**
- First-pass accepted: **No**
- Safe final state: **Verified**
- Principal strengths:
  - closed the original candidate-self-certification bypass by executing enforcement-critical code only from a separate exact trusted checkout
  - moved active suppression authority out of candidate control and bound it to protected invariant closure and exact candidate inputs
  - preserved exact Git path case, scanner-specific finding identity and same-candidate ineligibility
  - reported the bootstrap state honestly as unverified with nine active findings and zero suppressions
  - kept the bootstrap explicitly non-enforcement and performed no live security, provider, deployment or consumer action
- Principal defects:
  - seven required Toolkit invariant tests exit nonzero in the actual unprivileged no-network read-only protected sandbox
  - the proposed protected gate workflow retains an unsuppressed high-severity dangerous-trigger finding against itself
  - no deterministic exact-tree simulation proves the expected post-promotion result after the candidate becomes protected authority

### GPT-5.6 Sol - Security Remediation

- Reviewed: **26 Jul 2026 19:18 SGT**
- Run ID: `2026-07-26-gpt-5-6-sol-external-control-plane-a-amendment-001`
- Subject alias: `external-control-plane-a`
- Result: **AMEND**
- Weighted score: **3.67/5**
- First-pass accepted: **No**
- Safe final state: **Verified**
- Principal strengths:
  - removed ordinary imported-code access to the production inventory-authority minting path
  - separated the exact standalone authority session and bound runtime, source, installation and inventory identities
  - preserved singular parent-bound WeakMap mint sites and rejected reconstructed or cross-copy authority objects
  - provided strong adversarial evidence and kept every live provider, credential, deployment and consumer boundary untouched
- Principal defects:
  - authenticated production aliases and case variants can bypass the generic Tier-2 mutation floor
  - prefix-based MCP read admission permits compound mutating action names beginning with a read verb
  - the authenticated receipt session expires after a fixed thirty seconds even when the authorised operation is still running
  - workflow compiler output containment is lexical and can follow a redirected output or ancestor outside the repository
  - inventory generation rollback protection is process-local and resets between short-lived authority invocations
  - the exported default registry paths disagree
  - target resolution cannot use account or organisation identity to disambiguate otherwise matching targets
  - top-level and canonical nested approval references are not required to match

### GPT-5.6 Sol - Complex Repository Change

- Reviewed: **26 Jul 2026 19:12 SGT**
- Run ID: `2026-07-26-gpt-5-6-sol-workflow-transport-a-amendment-001`
- Subject alias: `workflow-transport-a`
- Result: **ACCEPTED**
- Weighted score: **4.77/5**
- First-pass accepted: **Yes**
- Safe final state: **Verified**
- Principal strengths:
  - made dedicated workflow identity authoritative before live discovery and rejected missing recorded targets without same-name fallback
  - replaced automatic changed-existing-target mutation with a complete fail-closed manual-application batch
  - used exclusive creation for missing targets and repeatedly revalidated identity, mode, topology and bytes
  - made the replacement-race fixture deterministic without sleeps, timestamp assumptions or inode-reuse dependence
  - kept authoritative, generated Skill and Secure Installer helper copies byte-identical and passed exact-head hosted validation and code scanning
- Principal defects:
  - none recorded

### GPT-5.6 Sol - Complex Repository Change

- Reviewed: **26 Jul 2026 19:05 SGT**
- Run ID: `2026-07-26-gpt-5-6-sol-workflow-compatibility-a-amendment-001`
- Subject alias: `workflow-compatibility-a`
- Result: **AMEND**
- Weighted score: **4.11/5**
- First-pass accepted: **No**
- Safe final state: **Verified**
- Principal strengths:
  - implemented a detailed identity-bound evidence inventory and preserved strict repository-only scope
  - provided strong exact-head test, source-generated parity and hosted continuous-integration evidence
  - kept the pull request open and unmerged and performed no live n8n, provider or production operation
  - materially improved recovery adjudication and replacement detection across the compatibility bridge
- Principal defects:
  - phase-30 installed-winner recovery can bypass the required phase-40 verification transition
  - evidence retirement is not restart-safe and can leave an irrecoverable partially retired authority set
  - target bytes can change after admission and before displacement without one final exact-byte revalidation
  - healthy SessionStart repeatedly performs full-tree classification instead of using a bounded valid-state fast path

### DeepSeek V4 Pro - Research

- Reviewed: **26 Jul 2026 18:20 SGT**
- Run ID: `2026-07-26-deepseek-v4-pro-governance-tooling-a-architecture-reset-004`
- Subject alias: `governance-tooling-a`
- Result: **PASS**
- Weighted score: **4.42/5**
- First-pass accepted: **Yes**
- Safe final state: **Verified**
- Principal strengths:
  - preserved the exact authorised pull-request head and strict no-mutation boundary while producing a complete twenty-four-section packet
  - replaced broad detector aliases with one code-specific detector unit per finding code and separated immutable production assembly from the test-only registry
  - defined unchanged exact-oracle mutation proof typed fail-closed diagnostic context and representation-independent subject keys
  - carried forward body-derived authority implementation pull-request lifecycle side-effect interception semantic parity fixtures and full workflow dependency closure
  - provided an unusually complete path-level implementation blast radius and adversarial test matrix suitable for a controller-issued design lock
- Principal defects:
  - the packet recommends making canonical_parent_tracker schema-required even though the prior controller lock explicitly keeps missing or wrong canonical-parent identity as semantic governance findings
  - the independent test registry is not mechanically bound per code to the exact function references used by the production registry, so mutation coverage could drift into a test-only implementation
  - the duplicate-ID section says diagnostics name an internal canonical key even though the typed-context contract prohibits arbitrary identifier-derived strings and requires repository-level opaque output
  - string subject ordering uses localeCompare while claiming locale-independent Unicode code-point order; deterministic ordinal comparison is required
  - the lifecycle model introduces is_amendment_of and additional replacement semantics but the schema row in the blast radius does not include those required structural changes and GOV022 versus GOV027 overlap remains ambiguous
  - the parity contract incorrectly claims published and curated skill files are byte-identical although the published surface contains a generated provenance header and must be checked through the canonical transform
  - the side-effect contract does not completely specify read-versus-write fs.open flag classification and its DNS proof would risk real resolver activity instead of a controlled fake adapter
  - the workflow traversal and implementation paths contain minor internal naming and location inconsistencies that the controller lock must normalise before Gate 3

### Claude Opus 5 - Complex Repository Change

- Reviewed: **26 Jul 2026 15:32 SGT**
- Run ID: `2026-07-26-claude-opus-5-business-automation-a-amendment-008`
- Subject alias: `business-automation-a`
- Result: **AMEND**
- Weighted score: **4.24/5**
- First-pass accepted: **No**
- Safe final state: **Verified**
- Principal strengths:
  - closed the three Amendment 7 integrity findings with pure pre-open triage distinct read-only and writer paths complete global history validation and aware claim chronology
  - implemented separate Windows and POSIX no-replace publication paths with exact-head green CI on both operating systems
  - added broad cross-source hostile-state restart recovery concurrency and mutation evidence while keeping the change draft and unmerged
  - preserved the package business runner and live-system safety boundaries with zero private or production action
- Principal defects:
  - a second POSIX parent-directory fsync failure leaves a complete single-link final store with no durable uncertainty fact so a later ordinary reviewer command can accept and mutate state that the prior invocation classified controlled-recovery-only
  - destination-collision paths call temporary cleanup in a mode that suppresses every unlink failure and report only store_not_absent while the complete operation-owned temporary may remain
  - first-use creation recursively creates the authority-state parent before proving a stable pre-existing operator-controlled directory and does not validate redirected intermediate path components
  - the completion report claimed cleanup failures were never suppressed although the lost-race helper and its test deliberately preserve silent suppression
<!-- GENERATED:SCORECARD-RUNS:END -->
