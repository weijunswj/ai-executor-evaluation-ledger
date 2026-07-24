# Controller Ledger Quickstart

Use this sequence for every executor result.

## One source of truth

Append exactly one new JSON object as one new final line in `evaluations.jsonl`.

Do not:

- rewrite or delete an existing evaluation line;
- replace the whole JSONL file with a partial copy;
- edit the generated score tables or detailed-run sections by hand;
- shorten `GPT-5.6 Sol Medium` or `GPT-5.6 Sol High`;
- guess a reasoning level that the provider did not expose;
- instruct the evaluated executor to touch this repository.

## Required fields

Record the exact public-safe:

- model label;
- observed reasoning level, or `not-exposed`;
- run ID;
- reviewed timestamp;
- task class and difficulty;
- verdict and score;
- verified strengths and defects;
- integrity/control flags;
- opaque subject alias.

Never publish repository identities, user identities, raw revisions, provider identifiers, secrets or private operational evidence.

## Web-controller workflow

1. Create a branch named `controller/ledger-<short-purpose>` from current `main`.
2. Append the new JSONL line only.
3. The `Rebuild ledger views` workflow regenerates `README.md` and `scorecard.md` on the controller branch.
4. Update `model-policy.md` only when the evidence changes the safe task boundary.
5. Open a pull request.
6. Merge only after `Public safety` passes. It verifies disclosure safety, append-only JSONL and generated-view consistency.
7. After merge, tell the user:

```text
Ledger appended: <model> | reasoning: <level-or-not-exposed> | <run-id> | <verdict> | <score>/5
```

Do not issue the next executor prompt before the ledger and applicable private project tracker are reconciled.

## Local equivalent

```text
python scripts/rebuild_views.py
python scripts/check_public_safety.py
python scripts/rebuild_views.py --check
```

The complete history remains in `evaluations.jsonl`. Human-readable run displays retain only the newest 30 formal evaluations.
