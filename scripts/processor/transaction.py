"""Isolated candidate-tree construction and rollback-safe replacement."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Mapping, Optional

from scripts.processor.common import ProcessorError

FailureHook = Optional[Callable[[str, str], None]]

GENERATED_OUTPUTS = (
    "evaluations.jsonl",
    "ledger/dispositions.jsonl",
    "README.md",
    "scorecard.md",
    "analysis/model-recommendation.json",
)
JOURNAL_NAME = "ledger-processor-recovery"
MANIFEST_NAME = "manifest.json"
MANIFEST_KEYS = frozenset(
    {"schema_version", "state", "replaced_count", "restored_count", "targets"}
)
TARGET_KEYS = frozenset(
    {"path", "original_present", "original_sha256", "candidate_sha256", "snapshot"}
)
RECOVERY_RETRIES = 3


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


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _validate_relative_path(value: Any) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ProcessorError("processor_invalid_contract")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        raise ProcessorError("processor_invalid_contract")
    return value


def _git_metadata_dir(repository_root: Path) -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--absolute-git-dir"],
        cwd=repository_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ProcessorError("processor_recovery_required")
    path = Path(result.stdout.strip()).resolve()
    if not path.is_dir():
        raise ProcessorError("processor_recovery_required")
    return path


def recovery_journal_path(repository_root: Path) -> Path:
    return _git_metadata_dir(repository_root) / JOURNAL_NAME


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw_temporary = tempfile.mkstemp(prefix=".ledger-atomic-", dir=path.parent)
    temporary = Path(raw_temporary)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


def _canonical_manifest_bytes(manifest: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            manifest,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _validate_manifest(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != MANIFEST_KEYS:
        raise ProcessorError("processor_recovery_required")
    if value.get("schema_version") != 1:
        raise ProcessorError("processor_recovery_required")
    if value.get("state") not in {"prepared", "replacing", "restoring"}:
        raise ProcessorError("processor_recovery_required")
    targets = value.get("targets")
    if not isinstance(targets, list) or not targets:
        raise ProcessorError("processor_recovery_required")
    paths: list[str] = []
    for target in targets:
        if not isinstance(target, dict) or set(target) != TARGET_KEYS:
            raise ProcessorError("processor_recovery_required")
        paths.append(_validate_relative_path(target.get("path")))
        if not isinstance(target.get("original_present"), bool):
            raise ProcessorError("processor_recovery_required")
        for field in ("candidate_sha256",):
            digest = target.get(field)
            if not isinstance(digest, str) or len(digest) != 64:
                raise ProcessorError("processor_recovery_required")
        original_digest = target.get("original_sha256")
        snapshot = target.get("snapshot")
        if target["original_present"]:
            if (
                not isinstance(original_digest, str)
                or len(original_digest) != 64
                or not isinstance(snapshot, str)
                or Path(snapshot).name != snapshot
            ):
                raise ProcessorError("processor_recovery_required")
        elif original_digest is not None or snapshot is not None:
            raise ProcessorError("processor_recovery_required")
    if len(paths) != len(set(paths)):
        raise ProcessorError("processor_recovery_required")
    for field in ("replaced_count", "restored_count"):
        count = value.get(field)
        if not isinstance(count, int) or isinstance(count, bool) or not 0 <= count <= len(targets):
            raise ProcessorError("processor_recovery_required")
    return value


def _read_manifest(journal: Path) -> dict[str, Any]:
    try:
        raw = (journal / MANIFEST_NAME).read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        raise ProcessorError("processor_recovery_required")
    manifest = _validate_manifest(value)
    if raw != _canonical_manifest_bytes(manifest):
        raise ProcessorError("processor_recovery_required")
    return manifest


def _write_manifest(journal: Path, manifest: Mapping[str, Any]) -> None:
    _validate_manifest(dict(manifest))
    _atomic_write(journal / MANIFEST_NAME, _canonical_manifest_bytes(manifest))


def _bounded_filesystem_action(action: Callable[[], None]) -> None:
    last_error: Optional[OSError] = None
    for attempt in range(RECOVERY_RETRIES):
        try:
            action()
            return
        except OSError as error:
            last_error = error
            if attempt + 1 < RECOVERY_RETRIES:
                time.sleep(0.01 * (attempt + 1))
    if last_error is not None:
        raise last_error


def _replace_bytes(target: Path, content: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(target, content)
    if target.read_bytes() != content:
        raise OSError("replacement_verification_failed")


def _remove_exact_path(target: Path) -> None:
    if target.exists():
        target.unlink()
        _fsync_directory(target.parent)
    if target.exists():
        raise OSError("absence_verification_failed")


def _create_recovery_journal(
    repository_root: Path,
    candidate_files: Mapping[str, bytes],
    snapshot: Mapping[str, Optional[bytes]],
) -> Path:
    git_dir = _git_metadata_dir(repository_root)
    journal = git_dir / JOURNAL_NAME
    if journal.exists():
        raise ProcessorError("processor_recovery_required")
    staging = Path(tempfile.mkdtemp(prefix=f".{JOURNAL_NAME}-", dir=git_dir))
    targets: list[dict[str, Any]] = []
    try:
        for index, (relative_path, candidate) in enumerate(candidate_files.items()):
            original = snapshot[relative_path]
            snapshot_name = f"{index:04d}.snapshot" if original is not None else None
            if snapshot_name is not None:
                _atomic_write(staging / snapshot_name, original)
            targets.append(
                {
                    "path": relative_path,
                    "original_present": original is not None,
                    "original_sha256": _sha256(original) if original is not None else None,
                    "candidate_sha256": _sha256(candidate),
                    "snapshot": snapshot_name,
                }
            )
        manifest = {
            "schema_version": 1,
            "state": "prepared",
            "replaced_count": 0,
            "restored_count": 0,
            "targets": targets,
        }
        _write_manifest(staging, manifest)
        _fsync_directory(staging)
        os.replace(staging, journal)
        _fsync_directory(git_dir)
        return journal
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def _verified_snapshot_bytes(journal: Path, target: Mapping[str, Any]) -> Optional[bytes]:
    if not target["original_present"]:
        return None
    snapshot_path = journal / target["snapshot"]
    try:
        content = snapshot_path.read_bytes()
    except OSError:
        raise ProcessorError("processor_recovery_required")
    if _sha256(content) != target["original_sha256"]:
        raise ProcessorError("processor_recovery_required")
    return content


def _remove_journal(journal: Path) -> None:
    completed = journal.with_name(f"{JOURNAL_NAME}.complete")
    if completed.exists():
        shutil.rmtree(completed)
    os.replace(journal, completed)
    _fsync_directory(journal.parent)
    try:
        shutil.rmtree(completed)
    except OSError:
        pass


def _restore_from_journal(
    repository_root: Path,
    journal: Path,
    *,
    failure_hook: FailureHook = None,
) -> None:
    manifest = _read_manifest(journal)
    manifest["state"] = "restoring"
    manifest["restored_count"] = 0
    _write_manifest(journal, manifest)
    targets = manifest["targets"]
    try:
        for index, entry in enumerate(targets):
            relative_path = entry["path"]
            original = _verified_snapshot_bytes(journal, entry)
            if failure_hook:
                failure_hook("before_restore", relative_path)
            target = repository_root / relative_path
            if original is None:
                _bounded_filesystem_action(lambda target=target: _remove_exact_path(target))
            else:
                _bounded_filesystem_action(
                    lambda target=target, original=original: _replace_bytes(target, original)
                )
            manifest["restored_count"] = index + 1
            _write_manifest(journal, manifest)
            if failure_hook:
                failure_hook("after_restore", relative_path)
            if index + 1 < len(targets) and failure_hook:
                failure_hook("between_restorations", relative_path)
        if failure_hook:
            failure_hook("restoration_verification", "")
        for entry in targets:
            target = repository_root / entry["path"]
            original = _verified_snapshot_bytes(journal, entry)
            if original is None:
                if target.exists():
                    raise OSError("absence_verification_failed")
            elif not target.is_file() or target.read_bytes() != original:
                raise OSError("restoration_verification_failed")
    except Exception as error:
        raise ProcessorError("processor_recovery_required") from error
    _remove_journal(journal)


def recover_incomplete_transaction(
    repository_root: Path,
    *,
    failure_hook: FailureHook = None,
) -> bool:
    """Restore and verify any durable incomplete transaction before new work."""

    journal = recovery_journal_path(repository_root)
    if not journal.exists():
        return False
    if not journal.is_dir():
        raise ProcessorError("processor_recovery_required")
    _restore_from_journal(repository_root, journal, failure_hook=failure_hook)
    return True


def replace_tracked_files(
    repository_root: Path,
    candidate_files: Mapping[str, bytes],
    *,
    failure_hook: FailureHook = None,
) -> None:
    """Durably replace all outputs or restore every starting byte on failure."""

    recover_incomplete_transaction(repository_root, failure_hook=failure_hook)
    paths = tuple(_validate_relative_path(path) for path in candidate_files)
    if not paths or len(paths) != len(set(paths)):
        raise ProcessorError("processor_invalid_contract")
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
    journal = _create_recovery_journal(repository_root, candidate_files, snapshot)
    manifest = _read_manifest(journal)
    manifest["state"] = "replacing"
    _write_manifest(journal, manifest)
    try:
        for relative_path, content in candidate_files.items():
            if failure_hook:
                failure_hook("candidate_file_write", relative_path)

        for index, relative_path in enumerate(paths):
            if failure_hook:
                failure_hook("before_candidate_replace", relative_path)
                failure_hook("before_replace", relative_path)
            target = repository_root / relative_path
            _replace_bytes(target, candidate_files[relative_path])
            manifest["replaced_count"] = index + 1
            _write_manifest(journal, manifest)
            if failure_hook:
                failure_hook("after_candidate_replace", relative_path)
                failure_hook("after_replace", relative_path)
            if index < len(paths) - 1 and failure_hook:
                failure_hook("between_candidate_replacements", relative_path)
                failure_hook("between_replacements", relative_path)

        if failure_hook:
            failure_hook("candidate_verification", "")
            failure_hook("final_integrity_verification", "")
        for relative_path, expected in candidate_files.items():
            if (repository_root / relative_path).read_bytes() != expected:
                raise RuntimeError("processor_integrity_failure")
    except Exception as replacement_error:
        try:
            _restore_from_journal(
                repository_root,
                journal,
                failure_hook=failure_hook,
            )
        except ProcessorError as recovery_error:
            raise ProcessorError("processor_recovery_required") from recovery_error
        raise replacement_error
    _remove_journal(journal)
