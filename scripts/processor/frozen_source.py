"""Exact frozen-source refetch without body or identity persistence."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

from scripts.processor.batch_processor import fetch_live_142_comments
from scripts.processor.common import (
    FROZEN_BATCH_ID,
    FROZEN_COUNT,
    FROZEN_WATERMARK,
    ProcessorError,
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
