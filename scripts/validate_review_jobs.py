#!/usr/bin/env python3
"""Validate review-job JSON against the canonical schema."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schema" / "review-job.schema.json"

try:
    import jsonschema
except ImportError:
    jsonschema = None  # type: ignore[assignment]


def load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_job(job: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if jsonschema is None:
        return errors
    validator = jsonschema.Draft202012Validator(schema)
    for error in validator.iter_errors(job):
        path = ".".join(str(p) for p in error.absolute_path) if error.absolute_path else "$"
        errors.append(f"{path}: {error.message}")
    return errors


def canonicalise(job: dict[str, Any], schema: dict[str, Any]) -> bytes:
    errors = validate_job(job, schema)
    if errors:
        raise ValueError("Job fails schema validation: " + "; ".join(errors))
    return json.dumps(job, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def accepted_body_sha256(job: dict[str, Any], schema: dict[str, Any]) -> str:
    canonical = canonicalise(job, schema)
    return hashlib.sha256(canonical).hexdigest()


def parse_job(text: str) -> dict[str, Any]:
    job = json.loads(text)
    if not isinstance(job, dict):
        raise ValueError("Job must be a JSON object")
    return job


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate review-job JSON")
    parser.add_argument("input", nargs="?", help="JSON file to validate (stdin if omitted)")
    parser.add_argument("--hash", action="store_true", help="Print accepted_body_sha256")
    parser.add_argument("--canonical", action="store_true", help="Print canonical JSON to stdout")
    args = parser.parse_args()

    try:
        schema = load_schema()
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Schema load failed: {exc}", file=sys.stderr)
        return 1

    if args.input:
        text = Path(args.input).read_text(encoding="utf-8")
    else:
        text = sys.stdin.read()

    try:
        job = parse_job(text)
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"Parse failed: {exc}", file=sys.stderr)
        return 1

    errors = validate_job(job, schema)
    if errors:
        print(f"Validation failed ({len(errors)} errors):", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    if args.canonical:
        sys.stdout.buffer.write(canonicalise(job, schema))
        return 0

    if args.hash:
        print(accepted_body_sha256(job, schema))
        return 0

    print(f"Valid: {job['review_job_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
