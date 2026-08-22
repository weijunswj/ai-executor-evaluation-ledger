import copy
import hashlib
import json
import unittest

from scripts.processor import router
from scripts.processor.source_watch import SourceWatchPlanner, stale_route_report, validate_metadata


def _legacy_router() -> dict:
    return {
        "schema_version": 1,
        "record_type": "ledger_router",
        "router_revision": 1,
        "cutover_state": "LEGACY_ACTIVE",
        "active_generation": 0,
        "active_issue_number": 142,
        "legacy_generation": 0,
        "legacy_issue_number": 142,
        "legacy_segment_state": "active",
        "final_watermark": None,
        "predecessor_generation": None,
        "predecessor_issue_number": None,
        "successor_generation": None,
        "successor_issue_number": None,
        "rotation_threshold": 500,
        "cutover_anchor_sha256": None,
    }


def _prepared_router() -> dict:
    value = _legacy_router()
    value.update(
        {
            "router_revision": 2,
            "cutover_state": "PREPARED",
            "active_generation": None,
            "active_issue_number": None,
            "legacy_segment_state": "paused",
        }
    )
    return value


def _anchor(revision: int = 3, watermark: int = 874) -> dict:
    return {
        "schema_version": 1,
        "manifest_type": "ledger_router_cutover_anchor",
        "authority_scope": "cutover_authority_only_no_admission_no_receipt_no_cleanup_no_rewrite",
        "canonical_main_sha": "d38852a98b630bf1bd39ce62bf8e5d1e2921f39d",
        "router_revision": revision,
        "legacy_generation": 0,
        "legacy_issue_number": 142,
        "final_watermark": watermark,
        "frozen_legacy_source_count": watermark,
        "frozen_legacy_source_snapshot_sha256": hashlib.sha256(b"frozen-source").hexdigest(),
        "successor_generation": 1,
        "successor_issue_number": 1780,
    }


def _committed_router() -> dict:
    anchor = _anchor()
    value = _legacy_router()
    value.update(
        {
            "router_revision": anchor["router_revision"],
            "cutover_state": "CUTOVER_COMMITTED",
            "active_generation": None,
            "active_issue_number": None,
            "legacy_segment_state": "frozen",
            "final_watermark": anchor["final_watermark"],
            "predecessor_generation": 0,
            "predecessor_issue_number": 142,
            "successor_generation": 1,
            "successor_issue_number": 1780,
            "cutover_anchor_sha256": router.cutover_anchor_sha256(anchor),
        }
    )
    return value


def _successor_router() -> dict:
    value = _committed_router()
    value.update(
        {
            "router_revision": 4,
            "cutover_state": "SUCCESSOR_ACTIVE",
            "active_generation": 1,
            "active_issue_number": 1780,
            "legacy_segment_state": "retired",
        }
    )
    return value


class RouterCutoverTests(unittest.TestCase):
    def test_marker_is_byte_zero_and_payload_is_single_closed_object(self):
        value = _legacy_router()
        body = router.MARKER + "\n" + json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
        self.assertEqual(value, router.parse_router_body(body))
        for invalid in (
            "prefix" + body,
            body + body,
            router.MARKER + "\n{}\n",
            router.MARKER + "\n" + json.dumps({**value, "unknown": True}) + "\n",
            router.MARKER + "\n" + json.dumps(value)[:-1],
        ):
            with self.subTest(invalid=invalid[:30]):
                with self.assertRaises(router.RouterValidationError):
                    router.parse_router_body(invalid)

    def test_state_machine_has_only_required_recovery_states(self):
        self.assertEqual(
            router.ROUTER_STATES,
            {"LEGACY_ACTIVE", "PREPARED", "CUTOVER_COMMITTED", "SUCCESSOR_ACTIVE", "MIGRATION_VERIFIED"},
        )
        self.assertEqual(router.resolve_active_segment(_legacy_router()), (0, 142, 500))
        with self.assertRaises(router.RouterValidationError):
            router.resolve_active_segment(_prepared_router())
        with self.assertRaises(router.RouterValidationError):
            router.resolve_active_segment(_committed_router())
        self.assertEqual(router.resolve_active_segment(_successor_router()), (1, 1780, 500))

    def test_transitions_are_monotonic_and_w0_cannot_advance(self):
        router.validate_router_transition(_legacy_router(), _prepared_router())
        router.validate_router_transition(_prepared_router(), _committed_router())
        router.validate_router_transition(_committed_router(), _successor_router())
        advanced = _successor_router()
        advanced["final_watermark"] += 1
        with self.assertRaises(router.RouterValidationError):
            router.validate_router_transition(_successor_router(), advanced)
        rolled_back = _committed_router()
        rolled_back["router_revision"] = 5
        rolled_back["cutover_state"] = "LEGACY_ACTIVE"
        rolled_back["active_generation"] = 0
        rolled_back["active_issue_number"] = 142
        rolled_back["legacy_segment_state"] = "active"
        rolled_back["final_watermark"] = None
        rolled_back["predecessor_generation"] = None
        rolled_back["predecessor_issue_number"] = None
        rolled_back["successor_generation"] = None
        rolled_back["successor_issue_number"] = None
        rolled_back["cutover_anchor_sha256"] = None
        with self.assertRaises(router.RouterValidationError):
            router.validate_router_transition(_committed_router(), rolled_back)

    def test_cutover_anchor_is_immutable_and_bound(self):
        committed = _committed_router()
        anchor = _anchor()
        router.validate_cutover_anchor_binding(committed, anchor)
        changed = copy.deepcopy(anchor)
        changed["final_watermark"] += 1
        with self.assertRaises(router.RouterValidationError):
            router.validate_cutover_anchor_binding(committed, changed)

    def test_all_cutover_race_windows_are_classified_by_authority(self):
        before = _legacy_router()
        same = router.post_protocol_decision(
            posted=True,
            readback_verified=True,
            router_reread_available=True,
            before_router=before,
            after_router=before,
            target_generation=0,
            target_issue_number=142,
            posted_body="payload",
            readback={"issue_number": 142, "id": 873, "body": "payload"},
        )
        self.assertEqual(same["status"], "queued")
        committed = _committed_router()
        stale = router.post_protocol_decision(
            posted=True,
            readback_verified=True,
            router_reread_available=True,
            before_router=before,
            after_router=committed,
            target_generation=0,
            target_issue_number=142,
            posted_body="payload",
            readback={"issue_number": 142, "id": 875, "body": "payload"},
            cutover_anchor=_anchor(),
        )
        self.assertEqual(stale["status"], "stale_route")
        self.assertTrue(stale["retry_allowed"])
        self.assertTrue(stale["first_post_permanently_ineligible"])
        successor_stale = router.post_protocol_decision(
            posted=True,
            readback_verified=True,
            router_reread_available=True,
            before_router=before,
            after_router=_successor_router(),
            target_generation=0,
            target_issue_number=142,
            posted_body="payload",
            readback={"issue_number": 142, "id": 875, "body": "payload"},
            cutover_anchor=_anchor(),
        )
        self.assertEqual(successor_stale["status"], "stale_route")
        for kwargs, expected in (
            ({"posted": False, "readback_verified": False, "router_reread_available": True}, "post_failed"),
            ({"posted": True, "readback_verified": False, "router_reread_available": True}, "readback_unverified"),
        ):
            with self.subTest(expected=expected):
                result = router.post_protocol_decision(
                    **kwargs,
                    before_router=before,
                    after_router=None,
                    target_generation=0,
                    target_issue_number=142,
                )
                self.assertEqual(result["status"], expected)
                self.assertFalse(result["canonical"])
        result = router.post_protocol_decision(
            posted=True,
            readback_verified=True,
            router_reread_available=False,
            before_router=before,
            after_router=None,
            target_generation=0,
            target_issue_number=142,
            posted_body="payload",
            readback={"issue_number": 142, "id": 875, "body": "payload"},
        )
        self.assertEqual(result["status"], "router_reread_unavailable")

    def test_stale_retry_requires_readback_identity_and_exact_boundary(self):
        before = _legacy_router()
        after = _committed_router()

        def decide(comment_id, *, readback="__default__", anchor=_anchor(), body="payload", after_router=after, reread=True):
            return router.post_protocol_decision(
                posted=True,
                readback_verified=True,
                router_reread_available=reread,
                before_router=before,
                after_router=after_router if reread else None,
                target_generation=0,
                target_issue_number=142,
                posted_body=body,
                readback=None if readback == "__missing__" else (readback if readback != "__default__" else {"issue_number": 142, "id": comment_id, "body": body}),
                cutover_anchor=anchor,
            )

        for comment_id in (873, 874):
            with self.subTest(comment_id=comment_id):
                result = decide(comment_id)
                self.assertFalse(result["retry_allowed"])
                self.assertEqual(result["status"], "legacy_authority_input")
        result = decide(875)
        self.assertEqual(result["status"], "stale_route")
        self.assertTrue(result["retry_allowed"])
        wrong_anchor = _anchor()
        wrong_anchor["final_watermark"] += 1
        self.assertFalse(decide(875, anchor=wrong_anchor)["retry_allowed"])
        self.assertFalse(decide(875, anchor=None)["retry_allowed"])
        self.assertFalse(decide(875, readback="__missing__")["retry_allowed"])
        self.assertFalse(decide(875, reread=False)["retry_allowed"])
        bad_after = _successor_router()
        bad_after["router_revision"] = 1
        self.assertFalse(decide(875, after_router=bad_after)["retry_allowed"])
        self.assertFalse(
            decide(875, readback={"issue_number": 142, "id": 875, "body": "different"})["retry_allowed"]
        )
        self.assertFalse(
            decide(875, readback={"issue_number": 1780, "id": 875, "body": "payload"})["retry_allowed"]
        )

    def test_router_marker_rejects_schema_valid_cutover_anchor(self):
        body = router.MARKER + "\n" + json.dumps(_anchor(), sort_keys=True, separators=(",", ":")) + "\n"
        with self.assertRaises(router.RouterValidationError):
            router.parse_router_body(body)
    def test_stale_route_is_terminal_auditable_input_not_pending(self):
        classification = router.classify_legacy_comment(
            issue_number=142,
            comment_id=875,
            legacy_issue_number=142,
            final_watermark=874,
        )
        self.assertEqual(classification, "stale_route")
        status = router.stale_route_status(classification=classification, comment_id=875, final_watermark=874)
        self.assertFalse(status["queued"])
        self.assertFalse(status["pending"])
        self.assertFalse(status["recorded"])
        self.assertTrue(status["retained"])
        self.assertTrue(status["auditable"])
        self.assertFalse(status["disposition_required"])
        self.assertEqual(
            router.classify_legacy_comment(
                issue_number=142,
                comment_id=874,
                legacy_issue_number=142,
                final_watermark=874,
                frozen_comment_body_sha256="a" * 64,
                observed_comment_body_sha256="b" * 64,
            ),
            "source_changed",
        )

    def test_lock_state_is_advisory_not_the_post_integrity_boundary(self):
        self.assertEqual(
            router.classify_legacy_comment(
                issue_number=142,
                comment_id=875,
                legacy_issue_number=142,
                final_watermark=874,
            ),
            "stale_route",
        )
        report = stale_route_report(
            router_authority=_committed_router(),
            cutover_anchor=_anchor(),
            comment={"issue_number": 142, "id": 875},
        )
        self.assertEqual(report["classification"], "stale_route")
        self.assertFalse(report["queued"])
        self.assertFalse(report["pending"])

    def test_source_binding_and_cross_generation_identity_fail_closed(self):
        successor = _successor_router()
        router.validate_source_segment_binding(
            successor,
            router_revision=4,
            source_generation=1,
            source_issue_number=1780,
            source_watermark=100,
            source_snapshot_sha256="c" * 64,
        )
        with self.assertRaises(router.RouterValidationError):
            router.validate_source_segment_binding(
                successor,
                router_revision=3,
                source_generation=1,
                source_issue_number=1780,
                source_watermark=100,
                source_snapshot_sha256="c" * 64,
            )
        self.assertEqual(router.cross_generation_identity_outcome(same_identity=False, same_content=False), "new_identity")
        self.assertEqual(router.cross_generation_identity_outcome(same_identity=True, same_content=True), "already_recorded")
        self.assertEqual(router.cross_generation_identity_outcome(same_identity=True, same_content=False), "conflicting_identity")

    def test_source_binding_rejects_wrong_active_issue_and_generation(self):
        successor = _successor_router()
        with self.assertRaises(router.RouterValidationError):
            router.validate_source_segment_binding(
                successor,
                router_revision=4,
                source_generation=1,
                source_issue_number=142,
                source_watermark=100,
                source_snapshot_sha256="c" * 64,
            )
        with self.assertRaises(router.RouterValidationError):
            router.validate_source_segment_binding(
                successor,
                router_revision=4,
                source_generation=0,
                source_issue_number=1780,
                source_watermark=100,
                source_snapshot_sha256="c" * 64,
            )

    def test_cutover_boundary_is_independent_of_lock_order(self):
        before = _legacy_router()
        prepared = _prepared_router()
        committed = _committed_router()
        for after, expected, retry in (
            (prepared, "authority_changed", False),
            (committed, "stale_route", True),
            (_successor_router(), "stale_route", True),
        ):
            with self.subTest(expected=expected):
                result = router.post_protocol_decision(
                    posted=True,
                    readback_verified=True,
                    router_reread_available=True,
                    before_router=before,
                    after_router=after,
                    target_generation=0,
                    target_issue_number=142,
                    posted_body="payload",
                    readback={"issue_number": 142, "id": 875, "body": "payload"},
                    cutover_anchor=_anchor() if after is not prepared else None,
                )
                self.assertEqual(result["status"], expected)
                self.assertEqual(result["retry_allowed"], retry)
        self.assertEqual(
            router.classify_legacy_comment(
                issue_number=142,
                comment_id=875,
                legacy_issue_number=142,
                final_watermark=874,
            ),
            "stale_route",
        )

    def test_source_watch_production_surfaces_terminal_stale_route(self):
        body = router.MARKER + "\n" + json.dumps(_successor_router(), sort_keys=True, separators=(",", ":")) + "\n"
        result = SourceWatchPlanner().plan_source_watch(
            router_body=body,
            source_comments=[{"issue_number": 142, "id": 875}],
            router_revision=4,
            source_generation=1,
            source_issue_number=1780,
            source_watermark=100,
            source_snapshot_sha256="c" * 64,
            cutover_anchor=_anchor(),
        )
        self.assertEqual(result["status"], "STALE_ROUTE_TERMINAL")
        self.assertFalse(result["queued"])
        self.assertFalse(result["pending"])
        self.assertFalse(result["recorded"])
        self.assertTrue(result["auditable"])
        eligible = SourceWatchPlanner().plan_source_watch(
            router_body=body,
            source_comments=[{"issue_number": 142, "id": 874}],
            router_revision=4,
            source_generation=1,
            source_issue_number=1780,
            source_watermark=100,
            source_snapshot_sha256="c" * 64,
            cutover_anchor=_anchor(),
        )
        self.assertEqual(eligible["status"], "SOURCE_WATCH_VALIDATED")
        self.assertEqual(eligible["legacy_authority_inputs"], [874])
        with self.assertRaises(ValueError):
            SourceWatchPlanner().plan_source_watch(
                router_body=body,
                source_comments=[{"issue_number": 999, "id": 875}],
                router_revision=4,
                source_generation=1,
                source_issue_number=1780,
                source_watermark=100,
                source_snapshot_sha256="c" * 64,
                cutover_anchor=_anchor(),
            )
    def test_source_watch_router_metadata_binds_generation_and_target(self):
        metadata = {
            "schema_version": 1,
            "record_type": "source_watch_pr_metadata",
            "mode": "incremental",
            "base_sha": "a" * 40,
            "canonical_main_sha": "b" * 40,
            "batch_id": "batch-router-001",
            "controller_run_id": "controller-router-001",
            "pr_number": 151,
            "expected_head_sha": "c" * 40,
            "activation_mode": "dry-run",
            "source_issue_number": 1780,
            "receipt_issue_number": 143,
            "dry_run": True,
            "source_authority_mode": "router_v1",
            "router_issue_number": 142,
            "router_revision": 4,
            "source_generation": 1,
            "source_watermark": 100,
            "source_snapshot_sha256": "d" * 64,
        }
        validate_metadata(metadata)
        metadata["source_issue_number"] = 142
        with self.assertRaises(ValueError):
            validate_metadata(metadata)

if __name__ == "__main__":
    unittest.main()
