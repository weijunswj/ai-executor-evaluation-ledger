# Regression Benchmarks

This directory documents the benchmark policy used alongside real production work.

## Purpose

Real tasks change over time, so a lower score does not by itself prove that a model changed. Stable benchmark categories provide a second signal for suspected performance regression.

## Public benchmark categories

The public repository may describe categories and scoring rules, but should not publish all fixed expected answers.

Recommended categories:

1. **PR defect review** - inspect a fixed diff containing planted correctness and security defects.
2. **Evidence reconciliation** - update a supplied tracker from a bounded evidence packet without inventing state.
3. **Deployment-log diagnosis** - identify the first decisive failure and avoid unsupported retries.
4. **Scope-control audit** - detect prohibited actions in an execution transcript.
5. **Exact-report generation** - produce required SHAs, IDs, commands, exit codes and statuses without leaking secrets.
6. **Disposable repository repair** - implement a bounded change in a fixture repository and satisfy exact tests.

## Hidden and refreshed variants

Because this ledger is public, fixed answers and complete hidden fixtures should not be committed here. Use private or freshly generated variants to reduce optimisation against known answers.

Public records may contain:

- benchmark category;
- fixture version or hash;
- provider and canonical base model;
- date;
- aggregate score;
- failure categories;
- controller effort.

They must not contain secrets or production credentials.

## Suggested cadence

Run comparable benchmarks:

- when a provider changes the visible model/version label;
- after three comparable real-work runs suggest degradation;
- after a major toolchain or prompt-policy change;
- after every ten comparable real-work runs;
- before expanding a model's production permissions after a prior restriction.

## Regression decisions

- **No conclusion:** fewer than three comparable real-work runs.
- **Suspected regression:** repeated comparable real-work decline meeting the threshold in `SCORING_RUBRIC.md`.
- **Probable regression:** comparable real-work and benchmark decline under materially unchanged prompts and tools.

Alternative explanations must always be recorded: harder tasks, missing permissions, context length, tool failure, repository drift, rate limits and provider outages.
