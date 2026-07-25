# Scheduled Review

This directory contains the scheduled reviewer's permanent operating contract and durable batch state.

## Structure

```
scheduled-review/
  RULES.md                 Rulebook (authority, reread every run)
  README.md                This file
  batches/                 Active and historical batch manifests
    <batch_id>/
      manifest.json         Batch manifest (public-safe)
      results/              Per-job sealed results (public-safe)
        <review_job_id>.json
  completed/               Completed batch archives (convenience copies)
  blocked/                 Blocked job documentation (convenience copies)
```

## Authority

`scheduled-review/RULES.md` is the complete instruction set for the scheduled reviewer. It is reread from `main` at the start of every scheduled run and must not be modified by the reviewer.

Batch manifests under `batches/` are the authoritative record of each batch's state. Issue labels and PR labels are convenience UI state only.

## Public/private boundary

Files in this directory tree, and on any batch branch, must never contain:

- Private intake repository identity or URL.
- Private source repository slugs, URLs, or paths.
- Private issue numbers or pull request URLs.
- Private file paths or completion-report locations.
- User identities, emails, or home directory paths.
- Credentials, tokens, or secrets.

Only opaque `review_job_id` values, accepted body hashes, public-safe subject aliases, and sanitised findings may appear.
