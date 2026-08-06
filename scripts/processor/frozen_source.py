"""Exact frozen-source refetch without body or identity persistence."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from scripts.processor.batch_processor import fetch_live_142_comments
from scripts.processor.common import (
    FROZEN_BATCH_ID,
    FROZEN_COUNT,
    FROZEN_WATERMARK,
    ProcessorError,
    canonical_json_bytes,
    safe_author_hash,
    safe_comment_body_hash,
    sha256_bytes,
    valid_author_login,
    valid_timestamp,
)
from scripts.processor.frozen_replay import FrozenBatchPolicy


def refetch_frozen_source(
    repository_root: Path,
    receipt: Mapping[str, Any],
    *,
    queue_fetcher: Callable[[Path], list[dict[str, Any]]] = fetch_live_142_comments,
) -> dict[str, Any]:
    """Refetch the exact membership and return privacy-safe fingerprints."""

    policy = FrozenBatchPolicy.from_receipt(receipt)
    queue = queue_fetcher(repository_root)
    if not isinstance(queue, list):
        raise ProcessorError("processor_source_unavailable")
    verified = policy.verify_source(queue)
    fingerprints = [dict(item) for item in verified.fingerprints]

    return {
        "comments": [dict(item) for item in verified.comments],
        "fingerprints": fingerprints,
        "source_body_sha256": {
            str(item["id"]): item["body_sha256"] for item in fingerprints
        },
        "queue_snapshot_sha256": verified.snapshot_sha256,
        "later_comment_count": verified.later_comment_count,
    }


def refetch_frozen_source_for_refreeze(
    repository_root: Path,
    receipt: Mapping[str, Any],
    *,
    queue_fetcher: Callable[[Path], list[dict[str, Any]]] = fetch_live_142_comments,
) -> dict[str, Any]:
    """Compare exact live membership before enforcing old body hashes."""

    policy = FrozenBatchPolicy.from_receipt(receipt)
    queue = queue_fetcher(repository_root)
    if not isinstance(queue, list):
        raise ProcessorError("processor_source_unavailable")
    by_id: dict[int, Mapping[str, Any]] = {}
    for comment in queue:
        if not isinstance(comment, Mapping):
            raise ProcessorError("processor_source_unavailable")
        comment_id = comment.get("id")
        if (
            not isinstance(comment_id, int)
            or isinstance(comment_id, bool)
            or comment_id <= 0
            or comment_id in by_id
        ):
            raise ProcessorError("source_changed")
        by_id[comment_id] = comment
    bounded_ids = {
        comment_id
        for comment_id in by_id
        if comment_id <= policy.source_comment_watermark
    }
    if bounded_ids != set(policy.source_comment_ids):
        raise ProcessorError("source_changed")

    baseline_fingerprints: list[dict[str, Any]] = []
    live_fingerprints: list[dict[str, Any]] = []
    selected: list[dict[str, Any]] = []
    changed_ids: list[int] = []
    for comment_id in policy.source_comment_ids:
        comment = by_id[comment_id]
        expected = policy.bindings[comment_id]
        body = comment.get("body")
        user = comment.get("user")
        author = user.get("login") if isinstance(user, Mapping) else None
        created_at = comment.get("created_at")
        updated_at = comment.get("updated_at")
        if (
            not isinstance(body, str)
            or not valid_author_login(author)
            or created_at != expected.created_at
        ):
            raise ProcessorError("source_changed")
        author_hash = safe_author_hash(author)
        baseline_fingerprints.append(
            {
                "id": comment_id,
                "author_sha256": author_hash,
                "created_at": expected.created_at,
                "updated_at": expected.updated_at,
                "body_sha256": expected.body_sha256,
            }
        )
        body_hash = safe_comment_body_hash(body)
        if body_hash == expected.body_sha256:
            if updated_at != expected.updated_at:
                raise ProcessorError("source_changed")
        else:
            if (
                not valid_timestamp(updated_at)
                or not valid_timestamp(expected.updated_at)
                or datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                < datetime.fromisoformat(expected.updated_at.replace("Z", "+00:00"))
            ):
                raise ProcessorError("source_changed")
            changed_ids.append(comment_id)
        live_fingerprints.append(
            {
                "id": comment_id,
                "author_sha256": author_hash,
                "created_at": created_at,
                "updated_at": updated_at,
                "body_sha256": body_hash,
            }
        )
        selected.append(dict(comment))

    if (
        sha256_bytes(canonical_json_bytes(baseline_fingerprints))
        != policy.queue_snapshot_sha256
        or len(changed_ids) != 1
    ):
        raise ProcessorError("source_changed")
    return {
        "comments": selected,
        "fingerprints": live_fingerprints,
        "source_body_sha256": {
            str(item["id"]): item["body_sha256"] for item in live_fingerprints
        },
        "queue_snapshot_sha256": sha256_bytes(canonical_json_bytes(live_fingerprints)),
        "changed_comment_ids": changed_ids,
        "later_comment_count": len(set(by_id) - bounded_ids),
    }
