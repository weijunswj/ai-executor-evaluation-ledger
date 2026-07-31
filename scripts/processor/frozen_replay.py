"""Deterministic replay authority for the one frozen Ledger intake batch."""

from __future__ import annotations

import copy
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import jsonschema

from scripts.processor.common import (
    FROZEN_BATCH_ID,
    FROZEN_CANONICAL_BASE_SHA,
    FROZEN_COUNT,
    FROZEN_SNAPSHOT_SHA256,
    FROZEN_WATERMARK,
    REASONING_KEYS,
    WITHDRAWN_PAIRS,
    ProcessorError,
    canonical_json_bytes,
    canonical_json_line_bytes,
    safe_author_hash,
    safe_comment_body_hash,
    sha256_bytes,
    valid_author_login,
)
from scripts.processor.intake_parser import (
    HistoricalReviewTimestampAuthority,
    canonical_record_from_payload,
    parse_intake_comment,
)
from scripts.rebuild_views import (
    CANONICAL_MODEL_MAP,
    expected_files_for_records,
    resolved_evaluations,
)
from scripts.scrub_identity_variants import _scrub_value, legacy_identity_renames
from scripts.validate_manifests import (
    MANIFEST_PATHS,
    expected_manifests_for_bytes,
)

ROOT = Path(__file__).resolve().parents[2]
EVALUATION_SCHEMA = json.loads(
    (ROOT / "schema" / "evaluation.schema.json").read_text(encoding="utf-8")
)
DISPOSITION_SCHEMA = json.loads(
    (ROOT / "schema" / "disposition.schema.json").read_text(encoding="utf-8")
)
FORMAT_CHECKER = jsonschema.FormatChecker()
EVALUATION_VALIDATOR = jsonschema.Draft202012Validator(
    EVALUATION_SCHEMA,
    format_checker=FORMAT_CHECKER,
)
DISPOSITION_VALIDATOR = jsonschema.Draft202012Validator(
    DISPOSITION_SCHEMA,
    format_checker=FORMAT_CHECKER,
)

CANONICAL_CANDIDATE_PATHS = {
    "evaluations_jsonl": "evaluations.jsonl",
    "dispositions_jsonl": "ledger/dispositions.jsonl",
    "readme_md": "README.md",
    "scorecard_md": "scorecard.md",
    "model_recommendation_json": "analysis/model-recommendation.json",
}
MIGRATION_CANDIDATE_PATHS = {
    name: f"migrations/{name}" for name in MANIFEST_PATHS
}


def _reject_nonfinite_constant(_value: str) -> None:
    raise ValueError("nonfinite_json_number")


def _jsonl_records(raw: bytes) -> list[dict[str, Any]]:
    try:
        text = raw.decode("utf-8", errors="strict")
        values = [
            json.loads(line, parse_constant=_reject_nonfinite_constant)
            for line in text.splitlines()
            if line.strip()
        ]
    except (UnicodeDecodeError, TypeError, ValueError):
        raise ProcessorError("processor_schema_failure")
    if not all(isinstance(value, dict) for value in values):
        raise ProcessorError("processor_schema_failure")
    run_ids = [value.get("run_id") for value in values]
    if (
        any(not isinstance(run_id, str) for run_id in run_ids)
        or len(run_ids) != len(set(run_ids))
    ):
        raise ProcessorError("processor_schema_failure")
    return values


def _append_jsonl(existing: bytes, lines: Sequence[bytes]) -> bytes:
    output = existing
    if output and not output.endswith(b"\n"):
        output += b"\n"
    return output + b"".join(lines)


def _git_object_bytes(
    root: Path,
    revision: str,
    relative_path: str,
    *,
    missing_is_empty: bool = False,
) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{revision}:{relative_path}"],
        cwd=root,
        capture_output=True,
        text=False,
        check=False,
    )
    if result.returncode != 0:
        if missing_is_empty:
            return b""
        raise ProcessorError("authority_missing")
    return result.stdout


def migrate_canonical_base(
    canonical_base_bytes: bytes,
) -> tuple[list[dict[str, Any]], bytes]:
    """Apply the already-closed v1-to-v2 migration without candidate evidence."""

    source_records = _jsonl_records(canonical_base_bytes)
    renames = legacy_identity_renames()
    replacements = [0]
    migrated_records: list[dict[str, Any]] = []
    withdrawn_count = 0
    folded_count = 0
    for source in source_records:
        migrated = _scrub_value(
            copy.deepcopy(source),
            renames=renames,
            replacements=replacements,
        )
        for key in REASONING_KEYS:
            migrated.pop(key, None)
        if migrated.get("record_type") == "correction":
            corrected = migrated.get("corrected_fields")
            if not isinstance(corrected, dict):
                raise ProcessorError("processor_schema_failure")
            for key in REASONING_KEYS:
                corrected.pop(key, None)
            if not corrected:
                folded_count += 1
                continue

        raw_model = migrated.get("model")
        canonical_model = CANONICAL_MODEL_MAP.get(raw_model)
        if canonical_model is None and isinstance(raw_model, str):
            canonical_model = next(
                (
                    base_model
                    for base_model in CANONICAL_MODEL_MAP
                    if raw_model.startswith(base_model + " ")
                ),
                None,
            )
        if canonical_model is None:
            raise ProcessorError("processor_schema_failure")
        migrated["model"] = canonical_model
        migrated["schema_version"] = 2
        migrated["evaluation_protocol"] = migrated.get(
            "evaluation_protocol",
            "protocol_unknown",
        )
        if (migrated.get("provider"), canonical_model) in WITHDRAWN_PAIRS:
            withdrawn_count += 1
            continue
        migrated_records.append(migrated)

    if (
        len(source_records) != 66
        or len(migrated_records) != 59
        or withdrawn_count != 6
        or folded_count != 1
    ):
        raise ProcessorError("processor_authority_mismatch")
    migrated_bytes = b"".join(
        (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8")
        for record in migrated_records
    )
    return migrated_records, migrated_bytes


@dataclass(frozen=True)
class FrozenCommentBinding:
    comment_id: int
    created_at: Any
    updated_at: Any
    body_sha256: str


@dataclass(frozen=True)
class FrozenBatchPolicy:
    batch_id: str
    canonical_base_sha: str
    source_comment_ids: tuple[int, ...]
    source_comment_watermark: int
    queue_snapshot_sha256: str
    bindings: Mapping[int, FrozenCommentBinding]

    @classmethod
    def from_receipt(cls, receipt: Mapping[str, Any]) -> "FrozenBatchPolicy":
        source_ids = receipt.get("source_comment_ids")
        source_hashes = receipt.get("source_body_sha256")
        raw_bindings = receipt.get("comment_bindings")
        if (
            receipt.get("batch_id") != FROZEN_BATCH_ID
            or receipt.get("base_sha") != FROZEN_CANONICAL_BASE_SHA
            or receipt.get("canonical_main_sha") != FROZEN_CANONICAL_BASE_SHA
            or receipt.get("source_comment_watermark") != FROZEN_WATERMARK
            or receipt.get("queue_snapshot_sha256") != FROZEN_SNAPSHOT_SHA256
            or receipt.get("full_queue_count") != FROZEN_COUNT
            or not isinstance(source_ids, list)
            or source_ids != sorted(source_ids)
            or len(source_ids) != FROZEN_COUNT
            or len(set(source_ids)) != FROZEN_COUNT
            or max(source_ids, default=0) != FROZEN_WATERMARK
            or not isinstance(source_hashes, dict)
            or set(source_hashes) != {str(value) for value in source_ids}
            or not isinstance(raw_bindings, list)
        ):
            raise ProcessorError("source_changed")
        bindings: dict[int, FrozenCommentBinding] = {}
        for raw_binding in raw_bindings:
            if not isinstance(raw_binding, dict):
                raise ProcessorError("source_changed")
            comment_id = raw_binding.get("comment_id")
            body_hash = raw_binding.get("body_sha256")
            if (
                not isinstance(comment_id, int)
                or comment_id in bindings
                or body_hash != source_hashes.get(str(comment_id))
            ):
                raise ProcessorError("source_changed")
            bindings[comment_id] = FrozenCommentBinding(
                comment_id=comment_id,
                created_at=raw_binding.get("created_at"),
                updated_at=raw_binding.get("updated_at"),
                body_sha256=body_hash,
            )
        if set(bindings) != set(source_ids):
            raise ProcessorError("source_changed")
        return cls(
            batch_id=FROZEN_BATCH_ID,
            canonical_base_sha=FROZEN_CANONICAL_BASE_SHA,
            source_comment_ids=tuple(source_ids),
            source_comment_watermark=FROZEN_WATERMARK,
            queue_snapshot_sha256=FROZEN_SNAPSHOT_SHA256,
            bindings=bindings,
        )

    def verify_source(
        self,
        comments: Sequence[Mapping[str, Any]],
    ) -> "VerifiedFrozenSource":
        by_id: dict[int, Mapping[str, Any]] = {}
        for comment in comments:
            if not isinstance(comment, Mapping):
                raise ProcessorError("processor_source_unavailable")
            comment_id = comment.get("id")
            if not isinstance(comment_id, int) or comment_id in by_id:
                raise ProcessorError("source_changed")
            by_id[comment_id] = comment
        if not set(self.source_comment_ids).issubset(by_id):
            raise ProcessorError("source_changed")

        selected: list[Mapping[str, Any]] = []
        fingerprints: list[dict[str, Any]] = []
        for comment_id in self.source_comment_ids:
            comment = by_id[comment_id]
            body = comment.get("body")
            user = comment.get("user")
            author = user.get("login") if isinstance(user, Mapping) else None
            created_at = comment.get("created_at")
            updated_at = comment.get("updated_at")
            expected = self.bindings[comment_id]
            if (
                not isinstance(body, str)
                or not valid_author_login(author)
                or safe_comment_body_hash(body) != expected.body_sha256
                or created_at != expected.created_at
                or updated_at != expected.updated_at
            ):
                raise ProcessorError("source_changed")
            selected.append(comment)
            fingerprints.append(
                {
                    "id": comment_id,
                    "author_sha256": safe_author_hash(author),
                    "created_at": created_at,
                    "updated_at": updated_at,
                    "body_sha256": expected.body_sha256,
                }
            )
        snapshot_hash = sha256_bytes(canonical_json_bytes(fingerprints))
        if snapshot_hash != self.queue_snapshot_sha256:
            raise ProcessorError("source_changed")
        return VerifiedFrozenSource(
            comments=tuple(selected),
            fingerprints=tuple(fingerprints),
            snapshot_sha256=snapshot_hash,
            later_comment_count=len(set(by_id) - set(self.source_comment_ids)),
        )


@dataclass(frozen=True)
class VerifiedFrozenSource:
    comments: tuple[Mapping[str, Any], ...]
    fingerprints: tuple[Mapping[str, Any], ...]
    snapshot_sha256: str
    later_comment_count: int


@dataclass(frozen=True)
class FrozenReplayResult:
    candidate_files: Mapping[str, bytes]
    artifact_hashes: Mapping[str, str]
    canonical_hashes: Mapping[str, str]
    terminal_outcomes: Mapping[str, Mapping[str, Any]]
    admitted_run_ids: tuple[str, ...]
    accepted_record_proofs: Mapping[str, Mapping[str, Any]]
    canonical_record_hashes: Mapping[str, str]
    comment_bindings: tuple[Mapping[str, Any], ...]
    source_comment_ids: tuple[int, ...]
    source_body_sha256: Mapping[str, str]
    source_snapshot_sha256: str
    later_comment_count: int


def replay_frozen_batch(
    repository_root: Path,
    *,
    canonical_base_sha: str,
    batch_id: str,
    policy: FrozenBatchPolicy,
    verified_source: VerifiedFrozenSource,
    existing_canonical_base_records: Sequence[Mapping[str, Any]],
    existing_canonical_base_bytes: bytes,
    canonical_source_base_bytes: bytes,
    existing_dispositions_bytes: bytes,
    canonical_base_readme_bytes: bytes,
    canonical_base_scorecard_bytes: bytes,
) -> FrozenReplayResult:
    """Replay every frozen classification and derive every candidate byte."""

    if (
        canonical_base_sha != FROZEN_CANONICAL_BASE_SHA
        or batch_id != FROZEN_BATCH_ID
        or policy.canonical_base_sha != canonical_base_sha
        or verified_source.snapshot_sha256 != FROZEN_SNAPSHOT_SHA256
        or tuple(
            int(fingerprint["id"])
            for fingerprint in verified_source.fingerprints
        )
        != policy.source_comment_ids
    ):
        raise ProcessorError("processor_authority_mismatch")
    base_records = [dict(record) for record in existing_canonical_base_records]
    if _jsonl_records(existing_canonical_base_bytes) != base_records:
        raise ProcessorError("processor_authority_mismatch")
    if any(
        any(EVALUATION_VALIDATOR.iter_errors(record))
        for record in base_records
    ):
        raise ProcessorError("processor_schema_failure")

    existing_dispositions: list[dict[str, Any]] = []
    if existing_dispositions_bytes:
        try:
            existing_dispositions = [
                json.loads(line, parse_constant=_reject_nonfinite_constant)
                for line in existing_dispositions_bytes.decode(
                    "utf-8",
                    errors="strict",
                ).splitlines()
                if line.strip()
            ]
        except (UnicodeDecodeError, TypeError, ValueError):
            raise ProcessorError("processor_schema_failure")
        if any(
            not isinstance(value, dict)
            or any(DISPOSITION_VALIDATOR.iter_errors(value))
            for value in existing_dispositions
        ):
            raise ProcessorError("processor_schema_failure")

    recorded_run_ids = {
        str(record["run_id"]) for record in base_records
    }
    seen_candidate_ids: set[str] = set()
    admitted_records: list[dict[str, Any]] = []
    admitted_lines: list[bytes] = []
    disposition_lines: list[bytes] = []
    terminal_outcomes: dict[str, dict[str, Any]] = {}
    admitted_run_ids: list[str] = []
    record_hashes: dict[str, str] = {}
    record_proofs: dict[str, dict[str, Any]] = {}
    bindings: list[dict[str, Any]] = []
    frozen_ids = frozenset(policy.source_comment_ids)

    for comment, fingerprint in zip(
        verified_source.comments,
        verified_source.fingerprints,
    ):
        comment_id = int(fingerprint["id"])
        body = comment["body"]
        expected = policy.bindings[comment_id]
        historical_authority = HistoricalReviewTimestampAuthority(
            batch_id=batch_id,
            comment_id=comment_id,
            frozen_comment_ids=frozen_ids,
            verified_snapshot_sha256=verified_source.snapshot_sha256,
            source_body_sha256=fingerprint["body_sha256"],
            expected_body_sha256=expected.body_sha256,
            source_created_at=fingerprint["created_at"],
            expected_created_at=expected.created_at,
            source_updated_at=fingerprint["updated_at"],
            expected_updated_at=expected.updated_at,
        )
        code, payload, _reason_code = parse_intake_comment(
            comment_id,
            body,
            recorded_run_ids,
            seen_candidate_ids,
            historical_review_authority=historical_authority,
        )
        run_id = None
        record_hash = None
        if code == "admitted":
            try:
                record = canonical_record_from_payload(payload)
            except (KeyError, TypeError):
                raise ProcessorError("authority_missing")
            if any(EVALUATION_VALIDATOR.iter_errors(record)):
                raise ProcessorError("processor_schema_failure")
            line = canonical_json_line_bytes(record)
            run_id = record["run_id"]
            record_hash = sha256_bytes(line)
            admitted_records.append(record)
            admitted_lines.append(line)
            admitted_run_ids.append(run_id)
            record_hashes[run_id] = record_hash
            record_proofs[run_id] = {
                "provider": record["provider"],
                "model": record["model"],
                "outcome": record["outcome"],
                "weighted_score_5": record["weighted_score_5"],
            }
            recorded_run_ids.add(run_id)
        else:
            processed_at = fingerprint["updated_at"] or fingerprint["created_at"]
            disposition = {
                "schema_version": 2,
                "comment_id": comment_id,
                "comment_body_sha256": fingerprint["body_sha256"],
                "disposition_code": code,
                "processed_at": processed_at,
                "evaluation_run_id": None,
            }
            if any(DISPOSITION_VALIDATOR.iter_errors(disposition)):
                raise ProcessorError("processor_schema_failure")
            disposition_lines.append(canonical_json_line_bytes(disposition))

        outcome = {
            "outcome_code": code,
            "evaluation_run_id": run_id,
            "canonical_record_sha256": record_hash,
            "cleanup_eligible": False,
        }
        terminal_outcomes[str(comment_id)] = outcome
        bindings.append(
            {
                "comment_id": comment_id,
                "created_at": fingerprint["created_at"],
                "updated_at": fingerprint["updated_at"],
                "body_sha256": fingerprint["body_sha256"],
                **outcome,
            }
        )

    final_evaluations = _append_jsonl(
        existing_canonical_base_bytes,
        admitted_lines,
    )
    final_dispositions = _append_jsonl(
        existing_dispositions_bytes,
        disposition_lines,
    )
    final_records = base_records + admitted_records
    if _jsonl_records(final_evaluations) != final_records:
        raise ProcessorError("processor_integrity_failure")

    readme_text = canonical_base_readme_bytes.decode("utf-8", errors="strict")
    scorecard_text = canonical_base_scorecard_bytes.decode(
        "utf-8",
        errors="strict",
    )
    expected_readme, expected_scorecard, recommendation = (
        expected_files_for_records(
            resolved_evaluations(final_records),
            readme_text,
            scorecard_text,
            queued_evaluations=[],
        )
    )
    candidate_files: dict[str, bytes] = {
        "evaluations.jsonl": final_evaluations,
        "ledger/dispositions.jsonl": final_dispositions,
        "README.md": expected_readme.encode("utf-8"),
        "scorecard.md": expected_scorecard.encode("utf-8"),
        "analysis/model-recommendation.json": (
            json.dumps(
                recommendation,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
            + "\n"
        ).encode("utf-8"),
    }
    manifests = expected_manifests_for_bytes(
        repository_root,
        final_evaluations,
        base_raw=canonical_source_base_bytes,
    )
    for name, manifest in manifests.items():
        candidate_files[MIGRATION_CANDIDATE_PATHS[name]] = (
            json.dumps(
                manifest,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
            + "\n"
        ).encode("utf-8")

    artifact_hashes = {
        path: sha256_bytes(content)
        for path, content in sorted(candidate_files.items())
    }
    canonical_hashes = {
        name: artifact_hashes[path]
        for name, path in CANONICAL_CANDIDATE_PATHS.items()
    }
    return FrozenReplayResult(
        candidate_files=candidate_files,
        artifact_hashes=artifact_hashes,
        canonical_hashes=canonical_hashes,
        terminal_outcomes=terminal_outcomes,
        admitted_run_ids=tuple(admitted_run_ids),
        accepted_record_proofs=record_proofs,
        canonical_record_hashes=record_hashes,
        comment_bindings=tuple(bindings),
        source_comment_ids=policy.source_comment_ids,
        source_body_sha256={
            str(comment_id): policy.bindings[comment_id].body_sha256
            for comment_id in policy.source_comment_ids
        },
        source_snapshot_sha256=verified_source.snapshot_sha256,
        later_comment_count=verified_source.later_comment_count,
    )

def replay_frozen_from_receipt(
    repository_root: Path,
    receipt: Mapping[str, Any],
    comments: Sequence[Mapping[str, Any]],
) -> FrozenReplayResult:
    """Resolve exact canonical Git authority and invoke the shared replay."""

    policy = FrozenBatchPolicy.from_receipt(receipt)
    source = policy.verify_source(comments)
    canonical_source_bytes = _git_object_bytes(
        repository_root,
        policy.canonical_base_sha,
        "evaluations.jsonl",
    )
    canonical_records, canonical_bytes = migrate_canonical_base(
        canonical_source_bytes
    )
    return replay_frozen_batch(
        repository_root,
        canonical_base_sha=policy.canonical_base_sha,
        batch_id=policy.batch_id,
        policy=policy,
        verified_source=source,
        existing_canonical_base_records=canonical_records,
        existing_canonical_base_bytes=canonical_bytes,
        canonical_source_base_bytes=canonical_source_bytes,
        existing_dispositions_bytes=_git_object_bytes(
            repository_root,
            policy.canonical_base_sha,
            "ledger/dispositions.jsonl",
            missing_is_empty=True,
        ),
        canonical_base_readme_bytes=_git_object_bytes(
            repository_root,
            policy.canonical_base_sha,
            "README.md",
        ),
        canonical_base_scorecard_bytes=_git_object_bytes(
            repository_root,
            policy.canonical_base_sha,
            "scorecard.md",
        ),
    )
