# Executor Scorecard

Updated: 24 July 2026 (SGT)

This scorecard is generated from controller-verified records in `evaluations.jsonl`. Scores are meaningful only within comparable task classes and difficulty.

## Formal evaluated runs

| Model | Task class | Difficulty | Runs | Average /5 | First-pass acceptance | Safe final state verified | Integrity/control flags | Confidence |
|---|---|---|---:|---:|---:|---:|---:|---|
| Xiaomi MiMo 2.5 Pro | Production deployment | High | 1 | 2.25 | 0% | 0% | 5 | Anecdotal |

## Latest formal evaluation

### Xiaomi MiMo 2.5 Pro - SKR Stage A deployment

- Run ID: `2026-07-24-mimo-2-5-pro-skr-stage-a-001`
- Result: **HOLD**
- Weighted score: **2.25/5**
- First-pass accepted: **No**
- Safe final state: reported, but not independently proven in the terminal evidence
- Principal strengths:
  - stopped without claiming hosted verification or OAuth UAT passed;
  - did not roll back when the new revision reportedly never activated.
- Principal defects:
  - evidence identifiers and build error omitted;
  - three deployment attempts without documented diagnosis;
  - Google OAuth client evidence not proven;
  - tracker bodies claimed updated but remained stale;
  - tracker encoding corruption.

## Historical backfill status

Sol Medium, Sol High and other prior executor work have not yet been converted into formal per-run records. Earlier conversational estimates are not included in aggregate scores because the exact prompts, task boundaries and controller evidence have not yet been normalised.

Backfill should use only verifiable historical runs with recoverable repository, pull-request, issue and review evidence. Missing fields must remain explicit rather than inferred.

## Regression status

No model currently has enough comparable formal runs for a regression determination.

- MiMo 2.5 Pro: 1 production-deployment run - anecdotal only.
- Sol Medium: formal backfill pending.
- Sol High: formal backfill pending.

## Next decision point

MiMo 2.5 Pro must complete a strictly read-only evidence-recovery and build-diagnosis run before receiving another mutating production task. The result will be recorded as a separate evaluation rather than overwriting the first run.
