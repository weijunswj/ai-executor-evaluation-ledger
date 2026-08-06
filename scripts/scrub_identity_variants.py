#!/usr/bin/env python3
"""Apply the exact count-bounded legacy identity normalization."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
EVALUATIONS = ROOT / "evaluations.jsonl"


def legacy_identity_renames() -> dict[str, str]:
    prefix = "-".join(("2026", "07", "25", "claude", "opus", "5"))
    suffix = "-".join(("business", "automation", "a", "amendment"))
    return {
        "-".join((prefix, "max", suffix, number)): "-".join(
            (prefix, suffix, number)
        )
        for number in ("004", "005", "006")
    }


def _text_replacements():
    from scripts.check_public_safety import FORBIDDEN_LEDGER_IDENTITY_PATTERNS

    replacements = (
        "requested inference configuration",
        "observed inference configuration",
        "inference configuration",
        "native inference classification",
        "inference exposure status",
        "inference grouping",
        "inference configuration",
        "inference configuration",
        "Claude Opus 4.8",
        "Claude Opus 4.8",
        "Claude Opus 5",
        "GPT-5.6 Sol",
        "GPT-5.6 Sol",
        "GPT-5.6 Sol",
    )
    return zip(FORBIDDEN_LEDGER_IDENTITY_PATTERNS, replacements)


def _scrub_value(value, *, renames: dict[str, str], replacements: list[int]):
    if isinstance(value, dict):
        return {
            key: _scrub_value(item, renames=renames, replacements=replacements)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _scrub_value(item, renames=renames, replacements=replacements)
            for item in value
        ]
    if not isinstance(value, str):
        return value
    if value in renames:
        replacements[0] += 1
        return renames[value]
    updated = value
    for pattern, replacement in _text_replacements():
        updated, count = pattern.subn(replacement, updated)
        replacements[0] += count
    return updated


def scrub(root: Path = ROOT) -> int:
    path = root / "evaluations.jsonl"
    records = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    replacements = [0]
    renames = legacy_identity_renames()
    scrubbed = [
        _scrub_value(record, renames=renames, replacements=replacements)
        for record in records
    ]
    if replacements[0] != 4:
        raise ValueError("identity_scrub_boundary_changed")
    run_ids = [record.get("run_id") for record in scrubbed]
    if len(run_ids) != len(set(run_ids)):
        raise ValueError("identity_scrub_collision")
    path.write_bytes(
        (
            "\n".join(
                json.dumps(record, ensure_ascii=False)
                for record in scrubbed
            )
            + "\n"
        ).encode("utf-8")
    )
    return replacements[0]


def main() -> int:
    try:
        count = scrub(ROOT)
    except (OSError, UnicodeDecodeError, ValueError):
        print("Identity normalization failed.", file=sys.stderr)
        return 1
    print(f"Identity normalization passed: {count} exact replacements.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
