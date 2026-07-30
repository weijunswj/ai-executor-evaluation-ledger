"""Exact frozen-source refetch without body or identity persistence."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

from scripts.processor.batch_processor import fetch_live_142_comments
from scripts.processor.common import (
    ProcessorError,
    canonical_json_bytes,
    safe_author_hash,
    safe_comment_body_hash,
    sha256_bytes,
    valid_author_login,
)

FROZEN_BATCH_ID = "batch-20260729-gate3-amendment-004"
FROZEN_COUNT = 101
FROZEN_WATERMARK = 5115014307


def refetch_frozen_source(
    repository_root: Path,
    receipt: Mapping[str, Any],
    *,
    queue_fetcher: Callable[[Path], list[dict[str, Any]]] = fetch_live_142_comments,
) -> dict[str, Any]:
    """Refetch the exact membership and return privacy-safe fingerprints."""

    source_ids = receipt.get("source_comment_ids")
    bindings = receipt.get("comment_bindings")
    if (
        receipt.get("batch_id") != FROZEN_BATCH_ID
        or receipt.get("source_comment_watermark") != FROZEN_WATERMARK
        or not isinstance(source_ids, list)
        or source_ids != sorted(source_ids)
        or len(source_ids) != FROZEN_COUNT
        or len(set(source_ids)) != FROZEN_COUNT
        or max(source_ids) != FROZEN_WATERMARK
        or not isinstance(bindings, list)
    ):
        raise ProcessorError("source_changed")
    expected_times = {
        binding.get("comment_id"): (
            binding.get("created_at"),
            binding.get("updated_at"),
        )
        for binding in bindings
        if isinstance(binding, dict)
    }
    if set(expected_times) != set(source_ids) or len(expected_times) != len(bindings):
        raise ProcessorError("source_changed")

    queue = queue_fetcher(repository_root)
    if not isinstance(queue, list):
        raise ProcessorError("processor_source_unavailable")
    by_id: dict[int, dict[str, Any]] = {}
    for comment in queue:
        comment_id = comment.get("id") if isinstance(comment, dict) else None
        if not isinstance(comment_id, int):
            raise ProcessorError("processor_source_unavailable")
        if comment_id in by_id:
            raise ProcessorError("source_changed")
        by_id[comment_id] = comment
    if not set(source_ids).issubset(by_id):
        raise ProcessorError("source_changed")

    fingerprints: list[dict[str, Any]] = []
    selected_comments: list[dict[str, Any]] = []
    for comment_id in source_ids:
        comment = by_id[comment_id]
        body = comment.get("body")
        user = comment.get("user")
        author = user.get("login") if isinstance(user, dict) else None
        created_at = comment.get("created_at")
        updated_at = comment.get("updated_at")
        if (
            not isinstance(body, str)
            or not valid_author_login(author)
            or (created_at, updated_at) != expected_times[comment_id]
        ):
            raise ProcessorError("source_changed")
        fingerprints.append(
            {
                "id": comment_id,
                "author_sha256": safe_author_hash(author),
                "created_at": created_at,
                "updated_at": updated_at,
                "body_sha256": safe_comment_body_hash(body),
            }
        )
        selected_comments.append(comment)

    return {
        "comments": selected_comments,
        "fingerprints": fingerprints,
        "source_body_sha256": {
            str(item["id"]): item["body_sha256"] for item in fingerprints
        },
        "queue_snapshot_sha256": sha256_bytes(canonical_json_bytes(fingerprints)),
        "later_comment_count": len(set(by_id) - set(source_ids)),
    }
