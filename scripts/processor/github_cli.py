"""Strict byte-oriented GitHub CLI command boundary."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Sequence

from scripts.processor.common import ProcessorError


def run_json_command(
    command: Sequence[str],
    *,
    repository_root: Path,
    failure_code: str,
) -> Any:
    """Run one JSON command without locale decoding or unsafe diagnostics."""

    result = subprocess.run(
        list(command),
        cwd=repository_root,
        capture_output=True,
        text=False,
        check=False,
    )
    if result.returncode != 0:
        raise ProcessorError(failure_code)
    try:
        decoded = result.stdout.decode("utf-8", errors="strict")
        return json.loads(decoded)
    except (UnicodeDecodeError, TypeError, ValueError):
        raise ProcessorError(failure_code)


def gh_json(
    repository_root: Path,
    args: Sequence[str],
    *,
    failure_code: str,
    paginate: bool = False,
) -> Any:
    """Run ``gh api`` and parse JSON only after strict UTF-8 decoding."""

    command = ["gh", "api", *args]
    if paginate:
        command.extend(["--paginate", "--slurp"])
    return run_json_command(
        command,
        repository_root=repository_root,
        failure_code=failure_code,
    )
