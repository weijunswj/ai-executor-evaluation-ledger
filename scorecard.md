# Executor Scorecard

Updated: 29 July 2026, 04:29

This scorecard is generated from controller-verified records in `evaluations.jsonl`. Aggregate scores use the complete append-only history. Public project references use opaque aliases. Correction records relabel existing runs and do not count as additional formal runs.

<!-- GENERATED:SCORECARD-RUNS:START -->
## Summary score table

| Model | Formal runs | Average /5 | First-pass acceptance | Safe final state verified | Integrity/control flags | Evidence level |
|---|---:|---:|---:|---:|---:|---|
| Claude Opus 5 | 3 | 4.63 | 0% | 3/3 applicable | 9 | Provisional across mixed tasks |
| GPT-5.6 Sol | 32 | 4.55 | 19% | 31/32 applicable | 104 | Useful operating baseline |
| Qwen3.7 Plus | 13 | 4.31 | 15% | 12/13 applicable | 27 | Useful operating baseline |
| MiniMax M3 | 5 | 4.18 | 0% | 5/5 applicable | 12 | Provisional across mixed tasks |
| DeepSeek V4 Pro | 19 | 3.90 | 5% | 19/19 applicable | 59 | Useful operating baseline |
| Gemini 3.1 Pro | 3 | 3.44 | 0% | 3/3 applicable | 11 | Provisional across mixed tasks |
| MiMo 2.5 Pro | 4 | 3.02 | 0% | 3/4 applicable | 12 | Provisional across mixed tasks |

## Formal evaluated runs

Newest first. This table displays at most 30 formal evaluation runs.

| Reviewed | Model | Task class | Difficulty | Verdict | Score /5 | First-pass | Safe final state |
|---|---|---|---|---|---:|---:|---|
| 29 Jul 2026 04:29 | DeepSeek V4 Pro | Storage And Identity Remediation | Medium | AMEND | 4.42 | No | Verified |
| 29 Jul 2026 04:29 | DeepSeek V4 Pro | Post Merge Remediation | Medium | PASS | 4.88 | Yes | Verified |
| 29 Jul 2026 01:51 | DeepSeek V4 Pro | Ux Remediation | Medium | AMEND | 4.55 | No | Verified |
| 28 Jul 2026 17:03 | DeepSeek V4 Pro | Ux Remediation | Medium | AMEND | 4.34 | No | Verified |
| 28 Jul 2026 16:23 | Qwen3.7 Plus | Implementation Amendment | High | AMEND | 4.63 | No | Verified |
| 28 Jul 2026 15:48 | Qwen3.7 Plus | Production Admission | High | AMEND | 4.08 | No | Verified |
| 28 Jul 2026 15:47 | Claude Opus 5 | Exact Head Review | High | PASS | 4.88 | No | Verified |
| 28 Jul 2026 15:22 | Qwen3.7 Plus | Security Incident Containment | High | AMEND | 3.43 | No | Not controller-verified |
| 28 Jul 2026 15:22 | Qwen3.7 Plus | Production Admission | High | AMEND | 3.96 | No | Verified |
| 28 Jul 2026 15:21 | Qwen3.7 Plus | Implementation Amendment | High | AMEND | 3.48 | No | Verified |
| 28 Jul 2026 14:38 | GPT-5.6 Sol | Concurrency Recovery Remediation | High | AMEND | 4.12 | No | Verified |
| 28 Jul 2026 14:36 | Gemini 3.1 Pro | Security Remediation | High | AMEND | 2.89 | No | Verified |
| 28 Jul 2026 13:20 | Gemini 3.1 Pro | Complex Repository Change | High | AMEND | 3.76 | No | Verified |
| 28 Jul 2026 13:18 | Qwen3.7 Plus | Product Remediation | Medium | AMEND | 4.38 | No | Verified |
| 28 Jul 2026 12:43 | Gemini 3.1 Pro | Security Remediation | High | AMEND | 3.66 | No | Verified |
| 28 Jul 2026 11:58 | Claude Opus 5 | Security Remediation | High | AMEND | 4.47 | No | Verified |
| 28 Jul 2026 11:51 | Qwen3.7 Plus | Security Remediation | Medium | ACCEPTED | 4.90 | Yes | Verified |
| 28 Jul 2026 11:00 | GPT-5.6 Sol | Security Remediation | High | AMEND | 4.43 | No | Verified |
| 28 Jul 2026 10:58 | Qwen3.7 Plus | Complex Repository Change | Medium | AMEND | 4.47 | No | Verified |
| 28 Jul 2026 10:58 | Qwen3.7 Plus | Security Remediation | High | ACCEPTED | 4.91 | Yes | Verified |
| 28 Jul 2026 09:14 | Qwen3.7 Plus | Security Remediation | Medium | AMEND | 4.61 | No | Verified |
| 28 Jul 2026 09:14 | Qwen3.7 Plus | Application Remediation | High | AMEND | 4.36 | No | Verified |
| 28 Jul 2026 09:14 | Qwen3.7 Plus | Security Remediation | High | AMEND | 4.63 | No | Verified |
| 28 Jul 2026 07:39 | GPT-5.6 Sol | Security Remediation | High | AMEND | 4.33 | No | Verified |
| 28 Jul 2026 02:25 | Claude Opus 5 | Research | High | PASS | 4.55 | No | Verified |
| 28 Jul 2026 02:22 | MiniMax M3 | Repository Recovery | High | AMEND | 4.48 | No | Verified |
| 28 Jul 2026 02:22 | MiniMax M3 | Security Remediation | High | AMEND | 4.62 | No | Verified |
| 28 Jul 2026 01:42 | MiniMax M3 | Complex Repository Change | High | AMEND | 3.02 | No | Verified |
| 28 Jul 2026 00:11 | GPT-5.6 Sol | Security Review | High | ACCEPTED | 4.88 | Yes | Verified |
| 27 Jul 2026 17:17 | MiniMax M3 | Product Remediation | High | AMEND | 4.35 | No | Verified |

## Task-class aggregates

| Model | Task class | Difficulty | Runs | Average /5 | First-pass acceptance | Confidence |
|---|---|---|---:|---:|---:|---|
| Claude Opus 5 | Architecture Proposal | High | 1 | 4.35 | 100% | Anecdotal |
| Claude Opus 5 | Complex Repository Change | High | 5 | 3.63 | 0% | Provisional |
| Claude Opus 5 | Exact Head Review | High | 1 | 4.88 | 0% | Anecdotal |
| Claude Opus 5 | Research | High | 1 | 4.55 | 0% | Anecdotal |
| Claude Opus 5 | Security Remediation | High | 1 | 4.47 | 0% | Anecdotal |
| DeepSeek V4 Pro | Architecture Proposal | High | 1 | 4.14 | 100% | Anecdotal |
| DeepSeek V4 Pro | Complex Repository Change | High | 6 | 3.39 | 0% | Moderate |
| DeepSeek V4 Pro | Documentation_Remediation | Low | 1 | 4.08 | 0% | Anecdotal |
| DeepSeek V4 Pro | Hosted Product Uat | High | 1 | 3.15 | 0% | Anecdotal |
| DeepSeek V4 Pro | Hosted Product Uat | Medium | 1 | 4.85 | 100% | Anecdotal |
| DeepSeek V4 Pro | Incident Diagnosis | High | 1 | 4.80 | 100% | Anecdotal |
| DeepSeek V4 Pro | Migration | Critical | 2 | 3.19 | 0% | Anecdotal |
| DeepSeek V4 Pro | Post Merge Remediation | Medium | 1 | 4.88 | 100% | Anecdotal |
| DeepSeek V4 Pro | Production Deployment | High | 1 | 4.55 | 100% | Anecdotal |
| DeepSeek V4 Pro | Production Operations | High | 4 | 4.35 | 75% | Provisional |
| DeepSeek V4 Pro | Research | High | 6 | 3.91 | 17% | Moderate |
| DeepSeek V4 Pro | Security Architecture Audit | High | 1 | 3.85 | 0% | Anecdotal |
| DeepSeek V4 Pro | Security Remediation | High | 9 | 3.97 | 0% | Moderate |
| DeepSeek V4 Pro | Security Review | High | 2 | 3.49 | 0% | Anecdotal |
| DeepSeek V4 Pro | Storage And Identity Remediation | Medium | 1 | 4.42 | 0% | Anecdotal |
| DeepSeek V4 Pro | Ux Remediation | Medium | 2 | 4.45 | 0% | Anecdotal |
| GPT-5.6 Sol | Architecture | Medium | 1 | 4.49 | 0% | Anecdotal |
| GPT-5.6 Sol | Architecture Proposal | High | 1 | 3.71 | 0% | Anecdotal |
| GPT-5.6 Sol | Complex Repository Change | Critical | 1 | 4.82 | 100% | Anecdotal |
| GPT-5.6 Sol | Complex Repository Change | High | 4 | 4.34 | 25% | Provisional |
| GPT-5.6 Sol | Concurrency Recovery Remediation | High | 1 | 4.12 | 0% | Anecdotal |
| GPT-5.6 Sol | Database Access Control | High | 1 | 4.86 | 100% | Anecdotal |
| GPT-5.6 Sol | Hosted Product Uat | Medium | 1 | 4.20 | 0% | Anecdotal |
| GPT-5.6 Sol | Implementation | High | 1 | 4.53 | 0% | Anecdotal |
| GPT-5.6 Sol | Implementation | Medium | 1 | 4.12 | 0% | Anecdotal |
| GPT-5.6 Sol | Production Admission | Medium | 1 | 4.85 | 100% | Anecdotal |
| GPT-5.6 Sol | Production Deployment | Critical | 1 | 4.81 | 0% | Anecdotal |
| GPT-5.6 Sol | Production Operations | High | 1 | 4.78 | 0% | Anecdotal |
| GPT-5.6 Sol | Production Recovery | High | 1 | 4.88 | 100% | Anecdotal |
| GPT-5.6 Sol | Recovery Protocol Remediation | High | 1 | 4.72 | 0% | Anecdotal |
| GPT-5.6 Sol | Research | High | 9 | 4.34 | 11% | Moderate |
| GPT-5.6 Sol | Security Architecture | High | 1 | 4.68 | 0% | Anecdotal |
| GPT-5.6 Sol | Security Audit | High | 1 | 4.70 | 100% | Anecdotal |
| GPT-5.6 Sol | Security Remediation | Critical | 1 | 4.60 | 0% | Anecdotal |
| GPT-5.6 Sol | Security Remediation | High | 14 | 4.46 | 7% | Useful operating baseline |
| GPT-5.6 Sol | Security Review | High | 1 | 4.88 | 100% | Anecdotal |
| Gemini 3.1 Pro | Complex Repository Change | High | 1 | 3.76 | 0% | Anecdotal |
| Gemini 3.1 Pro | Security Remediation | High | 2 | 3.28 | 0% | Anecdotal |
| MiMo 2.5 Pro | Architecture Proposal | High | 1 | 4.40 | 100% | Anecdotal |
| MiMo 2.5 Pro | Complex Repository Change | High | 3 | 3.34 | 0% | Provisional |
| MiMo 2.5 Pro | Complex Repository Change | Medium | 1 | 3.26 | 0% | Anecdotal |
| MiMo 2.5 Pro | Documentation Remediation | Medium | 1 | 4.81 | 0% | Anecdotal |
| MiMo 2.5 Pro | Incident Diagnosis | High | 3 | 3.47 | 0% | Provisional |
| MiMo 2.5 Pro | Production Deployment | High | 1 | 2.25 | 0% | Anecdotal |
| MiMo 2.5 Pro | Provider Operation | High | 5 | 3.55 | 0% | Provisional |
| MiMo 2.5 Pro | Routine Repository Change | Low | 1 | 4.60 | 0% | Anecdotal |
| MiMo 2.5 Pro | Routine Repository Change | Medium | 2 | 1.85 | 0% | Anecdotal |
| MiMo 2.5 Pro | Security Remediation | High | 5 | 3.50 | 0% | Provisional |
| MiniMax M3 | Complex Repository Change | High | 1 | 3.02 | 0% | Anecdotal |
| MiniMax M3 | Product Remediation | High | 1 | 4.35 | 0% | Anecdotal |
| MiniMax M3 | Repository Recovery | High | 1 | 4.48 | 0% | Anecdotal |
| MiniMax M3 | Security Remediation | High | 2 | 4.54 | 0% | Anecdotal |
| Qwen3.7 Plus | Application Remediation | High | 1 | 4.36 | 0% | Anecdotal |
| Qwen3.7 Plus | Bounded_Documentation_Implementation | Medium | 1 | 4.18 | 0% | Anecdotal |
| Qwen3.7 Plus | Complex Repository Change | Medium | 1 | 4.47 | 0% | Anecdotal |
| Qwen3.7 Plus | Implementation Amendment | High | 2 | 4.05 | 0% | Anecdotal |
| Qwen3.7 Plus | Product Remediation | Medium | 1 | 4.38 | 0% | Anecdotal |
| Qwen3.7 Plus | Production Admission | High | 2 | 4.02 | 0% | Anecdotal |
| Qwen3.7 Plus | Security Incident Containment | High | 1 | 3.43 | 0% | Anecdotal |
| Qwen3.7 Plus | Security Remediation | High | 2 | 4.77 | 50% | Anecdotal |
| Qwen3.7 Plus | Security Remediation | Medium | 2 | 4.76 | 50% | Anecdotal |

## Latest formal evaluations

Newest first. This section displays at most 30 formal evaluation runs.

### DeepSeek V4 Pro - Storage And Identity Remediation

- Reviewed: **29 Jul 2026 04:29**
- Run ID: `skr-structured-quote-ux-url-fallback-canonical-identity-closure-20260729-15`
- Subject alias: `spacekonceptrental`
- Result: **AMEND**
- Weighted score: **4.42/5**
- First-pass accepted: **No**
- Safe final state: **Verified**
- Principal strengths:
  - Closed the same-reference wrong-subkind consumption defect in both setup-to-rental and rental-to-setup directions.
  - Preserved the accepted storage-failure, last-known-state, dismissal and non-resurrection behaviour.
  - Stayed within the exact two-file scope and produced genuine RED/GREEN evidence plus green exact-head CI.
- Principal defects:
  - The canonical server-owned identity uses first-match lookup and does not fail closed when multiple exact slug-and-kind matches exist, contrary to the unambiguous-identity Design Lock.
  - URL seeding retains an optional independent subkind derivation instead of making the shared canonical identity the sole authority.

### DeepSeek V4 Pro - Post Merge Remediation

- Reviewed: **29 Jul 2026 04:29**
- Run ID: `sqag-post-merge-instruction-and-ci-doc-closure-20260729-21`
- Subject alias: `sqag`
- Result: **PASS**
- Weighted score: **4.88/5**
- First-pass accepted: **Yes**
- Safe final state: **Verified**
- Principal strengths:
  - Made only the three authorised instruction, documentation and focused-test changes on one exact-parent commit.
  - Restored explicit current-turn approval for issue and pull-request metadata writes while preserving read-only inspection.
  - Restored the precise managed-memory confidentiality wording and corrected the current PostgreSQL 17 CI documentation.
  - Produced focused regression coverage and exact-head CI success across every required job.
- Principal defects:
  - none recorded

### DeepSeek V4 Pro - Ux Remediation

- Reviewed: **29 Jul 2026 01:51**
- Run ID: `skr-structured-quote-ux-summary-removal-resync-and-reload-dismissal-closure-20260729-14`
- Subject alias: `public-web-app-a`
- Result: **AMEND**
- Weighted score: **4.55/5**
- First-pass accepted: **No**
- Safe final state: **Verified**
- Principal strengths:
  - Closed both Run-14 storage and fallback-remount defects with guarded resynchronisation and mounted-lifecycle dismissal state.
  - Added genuine fallback props, URL-source fixtures and read-then-fail storage regressions while preserving the complete existing suite.
  - Kept the amendment to two intended files and passed all exact-head CI jobs without live-system operations or secret exposure.
- Principal defects:
  - Fallback consumption matches only the stored URL reference and does not require the row subkind to match canonical fallback identity.
  - A stale or forged same-slug rental/setup discriminator can therefore consume and suppress the legitimate fallback despite being rendered unavailable.
  - The focused tests do not cover a same-reference wrong-subkind row or prove that the correct canonical fallback remains eligible after that invalid row is removed.

### DeepSeek V4 Pro - Ux Remediation

- Reviewed: **28 Jul 2026 17:03**
- Run ID: `skr-structured-quote-ux-summary-removal-failure-closure-20260728-13`
- Subject alias: `public-web-app-a`
- Result: **AMEND**
- Weighted score: **4.34/5**
- First-pass accepted: **No**
- Safe final state: **Verified**
- Principal strengths:
  - Returned and consumed the summary-removal transaction result with bounded accessible failure feedback.
  - Preserved unrelated and manual rows on successful removal and suppressed false success events on verified failure paths.
  - Kept the amendment to two intended files and passed complete exact-revision validation.
- Principal defects:
  - A URL-sourced row already present at mount does not initialise fallback-consumed state, so later removal can re-seed the same fallback.
  - A failed removal whose actual bytes cannot be re-read is converted into an empty visible selection rather than preserving last-known state and reporting storage unavailability.
  - The claimed fallback-removal regressions omit actual fallback context and use a catalogue-source fixture, so they do not prove the locked path.

### Qwen3.7 Plus - Implementation Amendment

- Reviewed: **28 Jul 2026 16:23**
- Run ID: `skr-structured-quote-ux-storage-and-fallback-state-closure-20260728-12`
- Subject alias: `public-web-app-a`
- Result: **AMEND**
- Weighted score: **4.63/5**
- First-pass accepted: **No**
- Safe final state: **Verified**
- Principal strengths:
  - Closed nine interacting browser-storage, fallback, validation and status defects in one bounded amendment.
  - Preserved accepted setup identity and manual-only fallback behaviour while adding genuine regression coverage.
  - Passed complete local validation and exact-head hosted checks with no live-system operation or secret exposure.
- Principal defects:
  - The visible summary-row removal path still discards the transaction result.
  - A removal write, read-back, dispatch or restoration failure therefore remains silent and lacks explicit actual-state resynchronisation.
  - Failure regressions cover catalogue increment and decrement but not the visible summary removal control.

### Qwen3.7 Plus - Production Admission

- Reviewed: **28 Jul 2026 15:48**
- Run ID: `sqag-direct-operator-membership-and-config-reconciliation-20260728-18`
- Subject alias: `private-quote-service-a`
- Result: **AMEND**
- Weighted score: **4.08/5**
- First-pass accepted: **No**
- Safe final state: **Verified**
- Principal strengths:
  - Safely replaced pooled operator authority with direct target-bound authority without password mutation or exposure.
  - Reconciled current database roles, ownership, direct grants, and membership ADMIN, INHERIT, and SET options.
  - Recovered current hosting identity, revision, health, and rollback limitations without production mutation.
- Principal defects:
  - Built a broad environment inventory from source references instead of the canonical hosted internal-alpha template.
  - Included deprecated or forbidden authentication variables and misclassified required object-storage settings as optional.
  - Treated a CI-only Node version as a production application blocker without build evidence and did not obtain provider-side OAuth metadata.

### Claude Opus 5 - Exact Head Review

- Reviewed: **28 Jul 2026 15:47**
- Run ID: `6a3d5523-45a9-46f3-9b1f-dd0016eac160`
- Subject alias: `business-automation-a`
- Result: **PASS**
- Weighted score: **4.88/5**
- First-pass accepted: **No**
- Safe final state: **Verified**
- Principal strengths:
  - Completed a full exact-head static review against the controller design lock and independently traced all three historical findings through their final implementations and tests.
  - After a fail-closed environmental stop, recreated an authorised detached review worktree and produced exact local evidence: approval 418, focused 580, contract 70 with all four real JSON Schema tests executed, full repository 1263, and 25 of 25 concurrency cycles green.
  - Reconciled every skip count across local, hosted Windows and Ubuntu evidence, verified protected blobs and test-only remediation scope, preserved the unrelated primary checkout byte-for-byte, and submitted one exact-head COMMENT review without resolving threads or claiming acceptance.
- Principal defects:
  - The first pass could not complete local validation because the review worktree and expected local objects were absent; it correctly stopped and required one bounded controller continuation rather than weakening the evidence standard.
  - The original private flake-hunting harness was unavailable, so the continuation transparently used 25 consecutive runs of the full concurrency set and retained that provenance limitation.

### Qwen3.7 Plus - Security Incident Containment

- Reviewed: **28 Jul 2026 15:22**
- Run ID: `swooshz-host-environment-stale-credential-containment-20260728-01`
- Subject alias: `shared-platform-a`
- Result: **AMEND**
- Weighted score: **3.43/5**
- First-pass accepted: **No**
- Safe final state: **Not controller-verified**
- Principal strengths:
  - Located the likely stale local credential source without causing an additional exposure.
  - Distinguished the current machine-level projection from a conflicting repository-local projection.
  - Confirmed that proposed replacement placeholders were empty and not usable authority.
- Principal defects:
  - Claimed PASS without identifying the exposed credential's role, exact target or authentication validity.
  - Recommended rotating an unrelated service credential without evidence that it was exposed.
  - Recommended changing canonical variable contracts despite finding no repository authority for the proposed replacement names.

### Qwen3.7 Plus - Production Admission

- Reviewed: **28 Jul 2026 15:22**
- Run ID: `sqag-production-inspection-authority-recovery-20260728-17`
- Subject alias: `private-quote-service-a`
- Result: **AMEND**
- Weighted score: **3.96/5**
- First-pass accepted: **No**
- Safe final state: **Verified**
- Principal strengths:
  - Recovered read-only provider and hosting access without exposing secrets or mutating production systems.
  - Identified stale deployment provenance, unhealthy runtime state, missing runtime configuration and absent target roles.
  - Collected useful ownership, grant and default-authority evidence for the production database.
- Principal defects:
  - Persisted a pooled operator connection despite the locked direct and non-pooled authority requirement.
  - Overstated PostgreSQL role-attribute inheritance without reporting per-membership SET and INHERIT options.
  - Reported runtime-configuration totals that did not reconcile and classified the minimum log setting inconsistently.

### Qwen3.7 Plus - Implementation Amendment

- Reviewed: **28 Jul 2026 15:21**
- Run ID: `skr-structured-quote-ux-setup-identity-and-url-fallback-closure-20260728-11`
- Subject alias: `public-web-app-a`
- Result: **AMEND**
- Weighted score: **3.48/5**
- First-pass accepted: **No**
- Safe final state: **Verified**
- Principal strengths:
  - Implemented one catalogue-authoritative setup classifier across listing, detail and quote validation paths.
  - Suppressed URL fallback over non-empty manual-only structured drafts while preserving stored bytes.
  - Completed focused and full validation with successful exact-head hosted checks.
- Principal defects:
  - The terminal packet reported only two active review threads although ten material threads were unresolved at controller review.
  - Five applicable defects already existed on or before the starting head but were omitted from the run inventory.
  - Three fresh exact-head findings remain in fallback dismissal, guarded storage access and manual-row status reporting.

### GPT-5.6 Sol - Concurrency Recovery Remediation

- Reviewed: **28 Jul 2026 14:38**
- Run ID: `workflow-compatibility-a-gate3-amendment-20260728-05`
- Subject alias: `workflow-compatibility-a`
- Result: **AMEND**
- Weighted score: **4.12/5**
- First-pass accepted: **No**
- Safe final state: **Verified**
- Principal strengths:
  - Completed exact orphan-C20 checkpoint publication, exact checkpoint reuse and restart-safe compaction without duplicate C20 authority.
  - Replaced unbounded journal name materialisation with cumulative incremental enumeration, immediate hard-limit rejection and bounded final topology revalidation.
  - Preserved exact target-lock fencing, the accepted destructive-delete boundary and the constant-three-proof phase-70 design while producing comprehensive local and hosted validation.
- Principal defects:
  - The central lock-artifact retirement primitive still performs a pathname unlink after its final exact proof, so a substituted quarantine generation can be deleted without authority.
  - Manifest-bound backup cleanup independently retains the same proof-to-pathname-delete race for files and requires equivalent exact-generation fencing for directory retirement.
  - The cleanup-manifest byte ceiling is first enforced after winner installation, allowing an admitted long-path tree to create a repeatable post-install recovery wedge.
  - The documented reused-PID lease guarantee is not implemented; numeric PID reuse can retain a stale target lock indefinitely unless process identity is strengthened or the contract is explicitly corrected.

### Gemini 3.1 Pro - Security Remediation

- Reviewed: **28 Jul 2026 14:36**
- Run ID: `2026-07-28-governance-tooling-a-gate3-remediation-023`
- Subject alias: `governance-tooling-a`
- Result: **AMEND**
- Weighted score: **2.89/5**
- First-pass accepted: **No**
- Safe final state: **Verified**
- Principal strengths:
  - Preserved the existing draft branch, normal descendant history and inert unmerged state.
  - Implemented occurrence ordinals that retain duplicate non-token states within the wrapper evaluation path.
  - Kept all four required hosted validation workflows green at the reviewed head.
- Principal defects:
  - Reinterpreted the locked association-aware cache contract as caller-oblivious, causing swapped caller-to-state associations to share the same production memo key.
  - Allowed invocation-local wrapper occurrence identity to remain on restored states and influence global downstream state reduction.
  - Changed only one committed test assertion; the claimed T1-T11 suite was not committed, existing success and failure oracles still derive from production events, and the revised hit assertion remains self-confirming.
  - Reported the full local suite as affected only by unrelated flakes without independently establishing that classification.

### Gemini 3.1 Pro - Complex Repository Change

- Reviewed: **28 Jul 2026 13:20**
- Run ID: `2026-07-28-governance-tooling-a-gate3-remediation-022`
- Subject alias: `governance-tooling-a`
- Result: **AMEND**
- Weighted score: **3.76/5**
- First-pass accepted: **No**
- Safe final state: **Verified**
- Principal strengths:
  - Used one ordinary descendant commit limited to the authorised workflow-inventory production and test files.
  - Stopped overwriting incoming wrapper caller identity with the token-free state fingerprint and made ordinary state reduction caller-aware for distinct callers.
  - Preserved draft, unmerged and inert scope while all four required hosted workflows completed successfully at the reviewed head.
- Principal defects:
  - Production unique-state and observation maps still collapse two identical caller-and-state records, so required multiplicity is not preserved through the real graph and cache paths.
  - The expected-token oracle is reconstructed from production-emitted miss events and omits caller occurrence identity, allowing equal-state callers or duplicate pairs to overwrite one another.
  - Tests retain non-exact count assertions, helper-only permutation and multiplicity coverage, a stale removed-field reference and no reported mutation-sensitivity proof.

### Qwen3.7 Plus - Product Remediation

- Reviewed: **28 Jul 2026 13:18**
- Run ID: `skr-structured-quote-ux-manual-remove-failure-closure-20260728-10`
- Subject alias: `public-web-app-a`
- Result: **AMEND**
- Weighted score: **4.38/5**
- First-pass accepted: **No**
- Safe final state: **Verified**
- Principal strengths:
  - Implemented bounded user-visible failure handling for manual removal while resynchronising the displayed selection from actual browser storage.
  - Added genuine read-back mismatch, event-dispatch, restoration-failure and successful-removal regressions through the production form adapter.
  - Kept the amendment to two authorised files and passed the complete exact-revision CI workflow.
- Principal defects:
  - The final packet incorrectly reported only two unresolved review threads and stated that no further action was needed despite a fresh automated review containing additional merge-blocking findings.
  - The run did not reconcile the newly reported inconsistent setup classification or phantom URL fallback over manual-only drafts.

### Gemini 3.1 Pro - Security Remediation

- Reviewed: **28 Jul 2026 12:43**
- Run ID: `2026-07-28-governance-tooling-a-gate3-remediation-021`
- Subject alias: `governance-tooling-a`
- Result: **AMEND**
- Weighted score: **3.66/5**
- First-pass accepted: **No**
- Safe final state: **Verified**
- Principal strengths:
  - Produced two ordinary descendant commits on the existing draft branch without rebase, force-push, activation or merge.
  - Replaced locale-sensitive manifest ordering with a shared ordinal comparator and introduced a shared repository-path authority.
  - Updated the locked test manifest and restored terminal green Validate, Validate toolkit, package-packs and package-skills results at the final exact head.
- Principal defects:
  - The production wrapper path still overwrites incoming caller identity with a token-free state fingerprint before paired cache-key construction, and graph-level token-free deduplication can collapse caller identity or multiplicity.
  - The new cache-hit assertion derives expected and actual restored tokens from the same cached state, so it cannot detect restoration of the wrong caller identity.
  - The initial completion report claimed hosted acceptance before the required workflows were green and omitted the subsequent manifest-only correction needed to restore them.

### Claude Opus 5 - Security Remediation

- Reviewed: **28 Jul 2026 11:58**
- Run ID: `2026-07-28-claude-opus-5-business-automation-a-amendment-009-gate3-001`
- Subject alias: `business-automation-a`
- Result: **AMEND**
- Weighted score: **4.47/5**
- First-pass accepted: **No**
- Safe final state: **Verified**
- Principal strengths:
  - Implemented the locked admission, trusted-parent and truthful-cleanup architecture with restart, reconciliation and mutation evidence while preserving the no-live-system boundary.
  - Used mutation and concurrency evidence to find and correct a genuine final-state reporting defect instead of dismissing it as a flaky test.
  - Stopped after bounded CI attempts, kept the pull request draft and unmerged, preserved local workspace state and reported the remaining red job without claiming acceptance.
- Principal defects:
  - Exact-head Ubuntu CI remains red because six tests still use harnesses or fault injections that no longer match the descriptor-relative POSIX interfaces.
  - Final POSIX validation is incomplete and four POSIX-only mutations survived on the Windows development host pending hosted Linux execution.
  - Two avoidable CI repair attempts were consumed by an invalid workflow-context placement and a capability gate that was incompatible with patched functions.

### Qwen3.7 Plus - Security Remediation

- Reviewed: **28 Jul 2026 11:51**
- Run ID: `sqag-postgresql17-fixed-error-category-20260728-15`
- Subject alias: `private-quote-service-a`
- Result: **ACCEPTED**
- Weighted score: **4.90/5**
- First-pass accepted: **Yes**
- Safe final state: **Verified**
- Principal strengths:
  - Replaced arbitrary exception-class output with one fixed public failure category across both affected failure paths.
  - Added dynamically named exception sentinels that prove class names are not emitted for connection or query failures.
  - Kept the amendment to one commit and the exact two authorised files, with complete successful exact-head CI evidence.
- Principal defects:
  - none recorded

### GPT-5.6 Sol - Security Remediation

- Reviewed: **28 Jul 2026 11:00**
- Run ID: `workflow-compatibility-a-gate3-amendment-20260728-04`
- Subject alias: `workflow-compatibility-a`
- Result: **AMEND**
- Weighted score: **4.43/5**
- First-pass accepted: **No**
- Safe final state: **Verified**
- Principal strengths:
  - Closed the assigned fresh-tree deletion defect by requiring exact authorised evidence and status at the destructive boundary.
  - Introduced one closed target-lock artifact inventory authority with process-stop, malformed-artifact and namespace regressions.
  - Completed the full bridge suite and all repository-owned exact-head hosted checks with detailed boundedness evidence.
- Principal defects:
  - Lock-artifact retirement still revalidates one object and then unlinks the pathname, permitting a replacement in the final proof-to-delete window to be removed without authority.
  - Orphan recovery skips journals already at C20 before publishing the missing terminal checkpoint and compaction authority.
  - Journal inventory materialises and sorts an unbounded directory entry set before enforcing the locked entry ceiling.

### Qwen3.7 Plus - Complex Repository Change

- Reviewed: **28 Jul 2026 10:58**
- Run ID: `skr-structured-quote-ux-production-adapter-and-deferral-closure-20260728-09`
- Subject alias: `public-web-app-a`
- Result: **AMEND**
- Weighted score: **4.47/5**
- First-pass accepted: **No**
- Safe final state: **Verified**
- Principal strengths:
  - Wired true storage-key removal into the second production adapter and resynchronised failed manual-add state from actual storage.
  - Removed the hypothetical recipe resolver, cast and recipe-only types from production quote paths while preserving explicit manual-review deferral.
  - Kept the change repository-only and passed exact-head website, repository, production-audit and tracked-file checks.
- Principal defects:
  - The manual-removal failure branch resynchronises state but exposes no bounded user-visible error.
  - The claimed manual-removal failure test uses normal storage and proves successful removal rather than a failure path.
  - The declared dispatch-failure test seam is not wired or exercised.

### Qwen3.7 Plus - Security Remediation

- Reviewed: **28 Jul 2026 10:58**
- Run ID: `platform-runtime-grant-contract-nonblock-loop-scope-20260728-19`
- Subject alias: `shared-platform-a`
- Result: **ACCEPTED**
- Weighted score: **4.91/5**
- First-pass accepted: **Yes**
- Safe final state: **Verified**
- Principal strengths:
  - Replaced closure-bound outer-scope traversal with explicit scope propagation for non-block loop bodies.
  - Added genuine safe-shadow and real-authority rejection controls across classic, in, of, destructured and nested loop forms.
  - Preserved the complete locked authority contract and passed exact-head repository, build, test and container validation.
- Principal defects:
  - none recorded

### Qwen3.7 Plus - Security Remediation

- Reviewed: **28 Jul 2026 09:14**
- Run ID: `sqag-postgresql17-assertion-output-safety-20260728-14`
- Subject alias: `private-quote-service-a`
- Result: **AMEND**
- Weighted score: **4.61/5**
- First-pass accepted: **No**
- Safe final state: **Verified**
- Principal strengths:
  - Removed environment-derived connection values and raw driver messages from expected assertion failures.
  - Added focused sentinel-redaction coverage and preserved the real disposable PostgreSQL 17 version check.
  - Exact-head CI passed secret scanning, dependency audits, the complete application validation and browser smoke lanes.
- Principal defects:
  - The connection failure path still emits an arbitrary exception class name rather than a fixed or allowlisted public category.
  - The focused tests use a built-in Exception and do not prove that a dynamically named exception class is redacted.

### Qwen3.7 Plus - Application Remediation

- Reviewed: **28 Jul 2026 09:14**
- Run ID: `skr-structured-quote-ux-absence-restoration-and-recipe-deferral-20260728-08`
- Subject alias: `public-web-app-a`
- Result: **AMEND**
- Weighted score: **4.36/5**
- First-pass accepted: **No**
- Safe final state: **Verified**
- Principal strengths:
  - Implemented verified restoration of an originally absent storage key in the shared transaction and removed obsolete direct writers.
  - Replaced fabricated setup-piece presentation with explicit manual-review deferral and reconciled the relevant architecture and status documents.
  - Exact-head CI passed the website, repository, production-audit and tracked-file-safety jobs.
- Principal defects:
  - The quote form has a second production storage adapter that omits the new remove operation, so manual-selection failure paths cannot restore true absence.
  - The production quote path still casts catalogue rows to a fixture-only setupPieces shape and invokes the deferred recipe resolver.

### Qwen3.7 Plus - Security Remediation

- Reviewed: **28 Jul 2026 09:14**
- Run ID: `platform-runtime-grant-contract-nested-callable-scope-20260728-18`
- Subject alias: `shared-platform-a`
- Result: **AMEND**
- Weighted score: **4.63/5**
- First-pass accepted: **No**
- Safe final state: **Verified**
- Principal strengths:
  - Closed the inherited nested-callable scope defect for function, arrow, class, block and catch bodies while preserving the locked runtime authority.
  - Added focused positive and negative lexical-scope regressions and preserved the complete validator test suite.
  - Exact-head CI passed repository guardrails, typecheck, build, tests and the no-push container build.
- Principal defects:
  - A non-block for, for-in or for-of body is revisited with the outer scope instead of the constructed loop scope.
  - Loop-local shadowing can therefore be falsely classified as global authority despite the new loop-scope branch.

### GPT-5.6 Sol - Security Remediation

- Reviewed: **28 Jul 2026 07:39**
- Run ID: `workflow-compatibility-a-gate3-amendment-20260728-03`
- Subject alias: `workflow-compatibility-a`
- Result: **AMEND**
- Weighted score: **4.33/5**
- First-pass accepted: **No**
- Safe final state: **Verified**
- Principal strengths:
  - Closed the assigned live-owner mutual-exclusion defect with exact lock-authority fencing and real-process regression evidence.
  - Reduced high-cardinality cleanup to a constant number of complete winner proofs while retaining exact per-entry authority checks.
  - Restored exact winner authority on resumed installation cleanup and added supported-platform durability for authoritative auxiliary publication.
  - Provided comprehensive local and hosted exact-head evidence while preserving the unmerged and no-live-system boundary.
- Principal defects:
  - One destructive-delete boundary refreshes a tree classification without comparing it to the authorised staged evidence before recursive removal.
  - Strict cache inventory does not yet admit and adjudicate all exact target-lock recovery artifacts before lock-protocol cleanup can run.

### Claude Opus 5 - Research

- Reviewed: **28 Jul 2026 02:25**
- Run ID: `2026-07-28-claude-opus-5-business-automation-a-architecture-reset-009`
- Subject alias: `business-automation-a`
- Result: **PASS**
- Weighted score: **4.55/5**
- First-pass accepted: **No**
- Safe final state: **Verified**
- Principal strengths:
  - Proved all three exact-head filesystem and durable-state defects from source and tests, including the broader post-publication Windows admission gap.
  - Selected the correct fail-closed architecture: one append-only in-store admission fact written last, with absence remaining mechanically blocking across restart.
  - Defined truthful lost-race cleanup, explicit controlled reconciliation, narrowed platform support and extensive adversarial, restart and mutation matrices.
  - Preserved the draft unmerged state, existing business contracts and zero live or private-system action during the architecture work.
- Principal defects:
  - The proposed POSIX sequence claimed all post-admission operations could be directory-descriptor-relative even though the standard Python SQLite interface opens by pathname.
  - The trusted traversal anchor and enforceable local-filesystem boundary were not defined precisely enough for direct implementation.
  - Controlled reconciliation did not explicitly re-establish the applicable platform durability boundary before inserting admission state.
  - The packet did not fully separate zero-admission structural validation from one-admission operational validation, leaving a bootstrap circularity for implementation.

### MiniMax M3 - Repository Recovery

- Reviewed: **28 Jul 2026 02:22**
- Run ID: `sqag-main-worktree-recovery-postgresql17-pr-20260728-13`
- Subject alias: `private-quote-service-a`
- Result: **AMEND**
- Weighted score: **4.48/5**
- First-pass accepted: **No**
- Safe final state: **Verified**
- Principal strengths:
  - Recovered the existing worktree without rewriting local main or mutating the historical stash.
  - Preserved the legitimate Toolkit repair, retained all upstream commits and established a disposable PostgreSQL 17 CI lane with live version proof.
  - Passed fresh exact-head secret, dependency, application, database-integration and browser-smoke validation.
- Principal defects:
  - The new PostgreSQL version assertion prints environment-derived connection values and raw driver exceptions on failure.
  - Malformed port conversion can escape through an unhandled traceback containing the supplied value.
  - Focused output-redaction tests and a fresh exact-head review are required before merge.

### MiniMax M3 - Security Remediation

- Reviewed: **28 Jul 2026 02:22**
- Run ID: `platform-runtime-grant-contract-callable-wrapper-closure-20260728-17`
- Subject alias: `shared-platform-a`
- Result: **AMEND**
- Weighted score: **4.62/5**
- First-pass accepted: **No**
- Safe final state: **Verified**
- Principal strengths:
  - Closed the inherited callable-wrapper escape across concise and block-bodied callables, packaging forms and direct call-result receivers.
  - Preserved the locked source, operation, grant and OIDC identities and changed only the authorised validator and test files.
  - Passed fresh exact-head repository guardrails, typecheck, build, test and no-push container CI.
- Principal defects:
  - Nested function declarations and expressions are recursively inspected using the outer callable scope.
  - Valid nested parameters or locals that shadow the global object can therefore be falsely rejected.
  - A focused lexical-scope amendment and fresh exact-head review remain required before merge.

### MiniMax M3 - Complex Repository Change

- Reviewed: **28 Jul 2026 01:42**
- Run ID: `2026-07-28-governance-tooling-a-gate3-remediation-016`
- Subject alias: `governance-tooling-a`
- Result: **AMEND**
- Weighted score: **3.02/5**
- First-pass accepted: **No**
- Safe final state: **Verified**
- Principal strengths:
  - Closed optional loader-chain handling and direct static require.resolve traversal in both dependency scanners.
  - Replaced the prior placeholder wrapper fixtures with real repeated Bash and PowerShell wrapper paths covering mutation, nesting and failure branches.
  - Preserved the existing branch and draft PR, used one ordinary commit and produced a verified non-writing current-base workflow run.
- Principal defects:
  - The inventory scanner now silently ignores malformed direct require calls because call-shape recognition is coupled to already-valid arguments.
  - Wrapper memoisation sorts caller tokens independently from state fingerprints, allowing different token-to-state pairings to collide.
  - The closure manifest was regenerated from CRLF-transformed worktree bytes and deterministically fails canonical LF synthetic-merge validation.
  - Token and cache tests remain largely tautological and do not prove actual cache hits or exact parent-token restoration.
  - Closure parser tests create temporary files inside the production manifest authority tree, creating cross-test nondeterminism.

### GPT-5.6 Sol - Security Review

- Reviewed: **28 Jul 2026 00:11**
- Run ID: `d0c73db8-2910-4104-9c32-932481707574`
- Subject alias: `workflow-compatibility-a`
- Result: **ACCEPTED**
- Weighted score: **4.88/5**
- First-pass accepted: **Yes**
- Safe final state: **Verified**
- Principal strengths:
  - Bound the review to the exact public head and current base, reconciled live checks and every review conversation, and preserved a strict no-mutation boundary.
  - Identified and independently substantiated a live-owner lock displacement defect that breaks target-scoped mutual exclusion.
  - Isolated the high-cardinality phase-70 cleanup path and connected its repeated complete winner validation to the observed Windows runtime failure.
  - Produced a complete crash-prefix, filesystem, boundedness and thread-adjudication packet with an accurate do-not-merge conclusion.
- Principal defects:
  - The monolithic bridge suite was stopped after exceeding the owned execution window, and an exploratory exclusion rerun lost its terminal summary, although both limitations were disclosed.
  - The phase-70 complexity conclusion is strongly supported by source and elapsed-time evidence but does not yet include a direct full-tree classification counter at the reviewed head.
  - The auto-sync run concluded successfully through its preflight while substantive checkout and write steps were skipped; the packet could distinguish that more explicitly from executed sync evidence.

### MiniMax M3 - Product Remediation

- Reviewed: **27 Jul 2026 17:17**
- Run ID: `skr-structured-quote-ux-g4-final-transaction-and-recipe-remediation-20260727-06`
- Subject alias: `public-web-app-a`
- Result: **AMEND**
- Weighted score: **4.35/5**
- First-pass accepted: **No**
- Safe final state: **Verified**
- Principal strengths:
  - Closed setup-identity hydration and exact server-derived reference-and-kind form acceptance at the reviewed head.
  - Removed the fabricated shared setup recipe and routed production catalogue and manual writes through a result-bearing transaction.
  - Preserved mixed-row order, failure-driven event suppression and passed fresh exact-head website and repository CI.
- Principal defects:
  - Production still has no server-owned setup-to-included-piece relation, public projection or repository mapping; the resolver input exists only in fixtures.
  - Restoration of an originally absent storage key writes an empty string instead of removing and verifying true absence.
  - The executor did not produce genuine starting-head RED execution for all new tests and retained dead storage helpers with future ordering risk.
<!-- GENERATED:SCORECARD-RUNS:END -->

## Current interpretation

### Xiaomi MiMo 2.5 Pro

MiMo currently appears:

- strong for narrow mechanical repository configuration;
- reasonably safe at respecting explicit mutation prohibitions;
- inconsistent in tracker-body quality;
- less reliable when exact operational diagnosis requires unavailable logs;
- unsuitable for autonomous production mutation at present.

### Claude Opus 4.8 High

Across three comparable high-difficulty runs, Claude Opus 4.8 High has consistently produced substantial implementation progress, exact revision/test evidence and a verified safe draft state. It has also required three controller amendment cycles on the same package-publication and cleanup boundary.

The third score is not evidence of a model regression: there is no stable earlier comparable window, and the score is broadly consistent with the first two. The repeated same-root defect is nevertheless a material convergence concern and now supports a provisional restriction on autonomous acceptance for atomicity, cleanup and durable-state work.

## Historical backfill status

GPT-5.6 Sol Medium, GPT-5.6 Sol High and other prior executor work have not yet been converted into formal per-run records. Earlier conversational estimates are excluded because exact prompts, task boundaries and controller evidence have not yet been normalised.

Backfill should use only verifiable historical runs. Public records must use opaque aliases and non-identifying revision assertions.

## Regression status

No model currently has enough stable-window evidence for a regression determination.

- Xiaomi MiMo 2.5 Pro: 3 mixed-task runs - provisional task-fit evidence, but one run per task class.
- Claude Opus 4.8 High: 3 comparable high-difficulty complex-repository-change runs - provisional evidence; repeated same-root durability defects recorded, but no regression classification.
- GPT-5.6 Sol Medium: formal backfill pending.
- GPT-5.6 Sol High: formal backfill pending.

## Next decision points

MiMo may perform bounded repository repair under exact scope and independent review. It remains prohibited from deploying or changing provider settings until the repair is accepted and all admission gates are independently re-established.

Claude Opus 4.8 High must repair the fail-open temporary-cleanup contract at a stronger reasoning level, prove unlink-failure behaviour on success and failure paths, and pass another exact-head review before the draft change may be accepted or merged.
