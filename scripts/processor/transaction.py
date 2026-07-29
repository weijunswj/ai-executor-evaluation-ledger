"""Isolated candidate-tree construction and rollback-safe replacement."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Dict, Iterable, Mapping, Optional

FailureHook = Optional[Callable[[str, str], None]]

GENERATED_OUTPUTS = (
    "evaluations.jsonl",
    "ledger/dispositions.jsonl",
    "README.md",
    "scorecard.md",
    "analysis/model-recommendation.json",
)


class CandidateTree:
    def __init__(self, root: Path, files: Mapping[str, bytes]):
        self._temporary = tempfile.TemporaryDirectory(prefix="ledger-candidate-")
        self.path = Path(self._temporary.name)
        for relative_path, content in files.items():
            target = self.path / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        self.files = dict(files)

    def close(self) -> None:
        self._temporary.cleanup()

    def __enter__(self) -> "CandidateTree":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()


def build_complete_candidate_tree(
    repository_root: Path,
    candidate_files: Mapping[str, bytes],
) -> CandidateTree:
    """Copy tracked source into an isolated tree, then overlay candidate bytes."""

    tree = CandidateTree(repository_root, {})
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=repository_root,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        tree.close()
        raise RuntimeError("candidate_source_unavailable")
    tracked_paths = [
        Path(item.decode("utf-8"))
        for item in result.stdout.split(b"\0")
        if item
    ]
    for relative in tracked_paths:
        source = repository_root / relative
        if not source.is_file():
            tree.close()
            raise RuntimeError("candidate_source_unavailable")
        destination = tree.path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    for relative_path, content in candidate_files.items():
        target = tree.path / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    tree.files = dict(candidate_files)
    return tree


def snapshot_tracked_files(repository_root: Path, relative_paths: Iterable[str]) -> Dict[str, Optional[bytes]]:
    snapshot: Dict[str, Optional[bytes]] = {}
    for relative_path in relative_paths:
        path = repository_root / relative_path
        snapshot[relative_path] = path.read_bytes() if path.exists() else None
    return snapshot


def _restore_snapshot(repository_root: Path, snapshot: Mapping[str, Optional[bytes]]) -> None:
    for relative_path, content in snapshot.items():
        target = repository_root / relative_path
        if content is None:
            if target.exists():
                target.unlink()
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)


def replace_tracked_files(
    repository_root: Path,
    candidate_files: Mapping[str, bytes],
    *,
    failure_hook: FailureHook = None,
) -> None:
    """Replace all outputs or restore every starting byte on any failure."""

    paths = tuple(candidate_files.keys())
    for relative_path in paths:
        target = repository_root / relative_path
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", relative_path],
            cwd=repository_root,
            capture_output=True,
            check=False,
        ).returncode == 0
        if tracked:
            worktree_dirty = subprocess.run(
                ["git", "diff", "--quiet", "--", relative_path],
                cwd=repository_root,
                capture_output=True,
                check=False,
            ).returncode != 0
            index_dirty = subprocess.run(
                ["git", "diff", "--cached", "--quiet", "--", relative_path],
                cwd=repository_root,
                capture_output=True,
                check=False,
            ).returncode != 0
            if worktree_dirty or index_dirty:
                raise RuntimeError("processor_worktree_not_clean")
        elif target.exists():
            raise RuntimeError("processor_worktree_not_clean")
    snapshot = snapshot_tracked_files(repository_root, paths)
    temporary = tempfile.TemporaryDirectory(prefix="ledger-replacement-")
    candidate_root = Path(temporary.name)
    try:
        for relative_path, content in candidate_files.items():
            candidate = candidate_root / relative_path
            candidate.parent.mkdir(parents=True, exist_ok=True)
            candidate.write_bytes(content)
            if failure_hook:
                failure_hook("candidate_file_write", relative_path)

        for index, relative_path in enumerate(paths):
            if failure_hook:
                failure_hook("before_replace", relative_path)
            source = candidate_root / relative_path
            target = repository_root / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, target)
            if failure_hook:
                failure_hook("after_replace", relative_path)
            if index < len(paths) - 1 and failure_hook:
                failure_hook("between_replacements", relative_path)

        if failure_hook:
            failure_hook("final_integrity_verification", "")
        for relative_path, expected in candidate_files.items():
            if (repository_root / relative_path).read_bytes() != expected:
                raise RuntimeError("processor_integrity_failure")
    except Exception:
        _restore_snapshot(repository_root, snapshot)
        raise
    finally:
        temporary.cleanup()
