#!/usr/bin/env python3
"""Append the controller-reviewed final DeepSeek governance architecture correction."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "2026-07-26-deepseek-v4-pro-governance-tooling-a-architecture-reset-003"

RECORD = {
    "schema_version": 1,
    "record_type": "evaluation",
    "run_id": RUN_ID,
    "reviewed_at": "2026-07-26T12:12:00+08:00",
    "executor_reported_at": None,
    "provider": "DeepSeek",
    "model": "DeepSeek V4 Pro",
    "task_class": "research",
    "difficulty": "high",
    "subject_alias": "governance-tooling-a",
    "revision_binding": "exact-public-base-and-head-controller-verified; final no-mutation architecture correction",
    "prompt_sha256": None,
    "prompt_capture": "The complete final Design-gated Gate 1 prompt and architecture packet are preserved privately; no standalone prompt hash was computed.",
    "objective": [
        "close the five remaining Toolkit issue-governance architecture defects before a new controller lock",
        "hard-bind production detector dispatch and move mutation control into a test-only harness",
        "define policy-owned findings deterministic opaque subjects and mechanical Node-workflow dependency closure",
        "preserve the exact pull-request head and perform no repository or external-system mutation",
    ],
    "reported_operations": {
        "repository_mutations": 0,
        "issue_or_pull_request_mutations": 0,
        "provider_or_production_actions": 0,
        "architecture_sections_reported": 17,
        "adversarial_test_rows_reported": 27,
        "clean_worktree_reported": True,
    },
    "controller_verification": {
        "exact_base_and_head_verified": True,
        "draft_unmerged_state_verified": True,
        "zero_mutation_boundary_consistent_with_live_head": True,
        "current_runtime_policy_workflows_and_reviews_inspected": True,
        "mechanically_lockable_without_correction": False,
        "material_architecture_corrections_required": 6,
        "highest_finding_severity": "P1",
    },
    "outcome": "amend",
    "first_pass_accepted": False,
    "controller_intervention_required": True,
    "safe_final_state_reported": True,
    "safe_final_state_verified": True,
    "root_cause_identified": True,
    "follow_up_runs_required": 1,
    "scores": {
        "correctness": 2.9,
        "safety_and_scope_control": 5.0,
        "evidence_quality": 4.7,
        "operational_judgement": 2.8,
        "task_understanding": 4.6,
        "tracker_and_repository_hygiene": 5.0,
        "autonomy": 4.4,
        "efficiency": 4.0,
    },
    "weighted_score_5": 3.96,
    "weighted_score_10": 7.92,
    "integrity_and_control_flags": [
        "shared_detector_alias_breaks_code_specific_mutation",
        "production_internal_registry_builder_exposed",
        "diagnostic_context_not_type_bounded",
        "opaque_subject_representation_instability",
        "workflow_inventory_false_negative_paths",
        "prior_architecture_blast_radius_dropped",
    ],
    "verified_strengths": [
        "preserved the exact authorised pull-request head and strict no-mutation boundary",
        "provided a substantially clearer production module split and recognised that policy must own normative finding metadata",
        "moved toward an independent exact-tuple oracle controlled local side-effect proof and mechanically discovered workflow coverage",
        "documented a detailed path-level proposal and correctly retained version 2.0.0 as an unmerged pre-release contract",
    ],
    "verified_defects": [
        "multiple finding codes still map to the same broad detector function, so replacing one code entry does not suppress that finding and cannot prove code-specific reachability",
        "the sample GOV014 mutation uses a valid zero-finding fixture and therefore cannot make the unchanged exact oracle fail",
        "the test harness imports a mutable buildRegistry export from production-internal code instead of independently assembling code-specific detector units under the test tree",
        "emitFinding interpolates arbitrary schema-valid context values including branch or metadata strings and silently ignores undeclared context rather than enforcing a typed public-safe context contract",
        "opaque-subject ordering depends on the first raw numeric or string representation and the packet contradicts itself about whether duplicate-ID detection occurs before subject construction",
        "the workflow inventory excludes or relaxes real Node execution paths, misses step-level composite actions and does not bind npm ci to the relevant checkout working directory lockfile and execution order",
        "the proposed Gate 3 blast radius marks schema and templates unchanged and omits previously required body-authority replacement lifecycle side-effect and hostile-diagnostic repairs",
    ],
    "next_evaluation": "produce one consolidated Sol XHigh Gate 1 correction using one code-specific detector per policy code, an independently assembled test-only mutation engine, typed fail-closed diagnostic context, representation-independent per-run opaque subjects, complete workflow and wrapper traversal, and the full carried-forward body lifecycle side-effect and parity blast radius",
    "confidence": "provisional",
    "redaction_notice": "Public-safe controller evaluation; repository identity and operational evidence are represented by an opaque subject alias.",
}

DEEPSEEK_SECTION = """## DeepSeek V4 Pro

Evidence level: **Provisional — 4 formal high-difficulty architecture and research runs**

Observed scores:

- scheduled batch-review architecture proposal: **4.14/5**;
- governance architecture reset: **3.94/5**;
- revised governance architecture reset: **4.18/5**;
- final governance architecture correction: **3.96/5**;
- four-run average: **4.06/5**;
- first-pass acceptance: **25%**;
- verified safe final state: **4/4**.

### Approved

- Exact-revision, no-mutation repository architecture packets.
- Authority mapping, root-cause analysis, option comparison, threat modelling and adversarial test planning for controller adjudication.
- Narrow architecture resets that preserve the existing branch, pull request and mutation boundary.

### Conditional

- Architecture recommendations remain advisory and require an independent controller lock before implementation.
- Executable parity requires one code-specific detector function or wrapper per canonical finding code; broad shared helpers may not be the mutation authority.
- Test mutation engines must be assembled under the test tree without production override parameters or mutable registry builders in the supported production surface.
- Mutation-sensitive proof must run the unchanged exact oracle on the isolated invalid fixture and prove the assertion fails after the exact detector is replaced.
- Canonical policy alone owns severity, grouping and message identity; message context must be typed, bounded and public-safe.
- Opaque subjects must use one representation-independent canonical key and reset deterministically per audit invocation.
- Workflow dependency closure must traverse workflows, reusable workflows, step-level composite actions, shell wrappers, package scripts and module imports, then bind locked installation to the correct checkout and working directory.
- The final implementation lock must retain all earlier body-authority, replacement lifecycle, side-effect, diagnostic and parity repairs.

### Not currently approved

- Mapping several finding codes to one broad detector while claiming per-code reachability or mutation proof.
- Using a valid zero-finding fixture to demonstrate that removal of a violation detector makes an oracle fail.
- Exporting a mutable registry builder from production-internal code for the test harness.
- Interpolating arbitrary validated branch, body, PR, property or path values into public diagnostics.
- Assigning opaque subjects according to encounter order or the first raw numeric/string representation.
- Hand-waving Node test, composite-action, shell-wrapper or installation-order paths as dependency-free exceptions.
- Implementing the current governance reset until the controller replaces these remaining architecture choices.

### Current evidence

The first run produced a useful scheduled-review architecture proposal but required controller replacement of private-source resolution, batch discovery, durable publication, trusted validation and recovery choices. The second run accurately diagnosed the surviving Toolkit governance defects but proposed self-certified reachability, an invalid lexical monkeypatch and incomplete lifecycle, diagnostic and dependency controls. The third run materially improved the design but still exposed detector overrides, inverted mutation proof, duplicated policy metadata, mixed subject identities and left workflow coverage non-mechanical. The fourth run produced a clearer module architecture and stronger policy direction, but its shared detector aliases make code-specific mutation impossible, its diagnostic context remains caller-controlled, its subject ordering is representation-dependent, its workflow traversal has material false-negative paths and its Gate 3 blast radius drops earlier required repairs.

### Current disposition

DeepSeek V4 Pro remains useful for bounded no-mutation architecture investigation and revision, but has not converged on this policy/schema trust boundary after three corrective architecture passes. The next attempt must use the owner-approved XHigh task classification and produce one consolidated packet with code-specific detector authority, an independently assembled test harness, typed public-safe diagnostic context, stable subject canonicalisation, complete workflow traversal and the full carried-forward implementation scope. Provider-native reasoning is not part of future public model identity; earlier legacy metadata remains pending the dedicated base-model migration.

"""


def append_record() -> None:
    path = ROOT / "evaluations.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    for line in lines:
        if line.strip() and json.loads(line).get("run_id") == RUN_ID:
            raise SystemExit(f"Run already present: {RUN_ID}")
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(RECORD, ensure_ascii=False, separators=(",", ":")) + "\n")


def replace_policy_section() -> None:
    path = ROOT / "model-policy.md"
    text = path.read_text(encoding="utf-8")
    start = text.index("## DeepSeek V4 Pro\n")
    end = text.index("## GPT-5.6 Sol Medium\n", start)
    updated = text[:start] + DEEPSEEK_SECTION + text[end:]
    updated = re.sub(
        r"^Updated: .+$",
        "Updated: 26 July 2026, 12:12 SGT",
        updated,
        count=1,
        flags=re.MULTILINE,
    )
    path.write_text(updated, encoding="utf-8", newline="\n")


def main() -> int:
    append_record()
    replace_policy_section()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
