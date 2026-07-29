import json
import hashlib
import os

MODEL_MAP = {
    "MiMo 2.5 Pro": "MiMo 2.5 Pro",
    "Claude Opus 4.8": "Claude Opus 4.8",
    "Claude Opus 4.8 High": "Claude Opus 4.8",
    "Claude Opus 4.8 Ultra High": "Claude Opus 4.8",
    "Claude Opus 5": "Claude Opus 5",
    "Claude Opus 5 Max": "Claude Opus 5",
    "DeepSeek V4 Pro": "DeepSeek V4 Pro",
    "GPT-5.6 Sol": "GPT-5.6 Sol",
    "GPT-5.6 Sol Medium": "GPT-5.6 Sol",
    "GPT-5.6 Sol High": "GPT-5.6 Sol",
    "GPT-5.6 Sol Max": "GPT-5.6 Sol",
    "Qwen3.7 Plus": "Qwen3.7 Plus"
}

WITHDRAWN_RUN_IDS = {
    "2026-07-24-claude-opus-4-8-business-automation-a-implementation-001",
    "2026-07-24-claude-opus-4-8-business-automation-a-amendment-001",
    "2026-07-24-claude-opus-4-8-high-business-automation-a-amendment-002",
    "2026-07-24-claude-opus-4-8-ultra-high-business-automation-a-amendment-003",
    "2026-07-24-correction-claude-opus-4-8-high-implementation-001",
    "2026-07-24-correction-claude-opus-4-8-high-amendment-001"
}

REASONING_KEYS = {
    "requested_reasoning_level",
    "observed_reasoning_mode",
    "thinking_setting",
    "native_reasoning_classification",
    "reasoning_exposure_status",
    "reasoning_grouping"
}

def migrate():
    jsonl_path = "evaluations.jsonl"
    with open(jsonl_path, "rb") as f:
        raw_before = f.read()
    before_sha256 = hashlib.sha256(raw_before).hexdigest()

    with open(jsonl_path, "r", encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]

    starting_record_count = len(records)
    withdrawn_records = []
    reasoning_only_corrections_removed = []
    substantive_corrections_preserved = []
    scrubbed_fields_count = 0

    migrated_records = []

    for r in records:
        run_id = r.get("run_id")
        rec_type = r.get("record_type", "evaluation")

        if run_id in WITHDRAWN_RUN_IDS:
            withdrawn_records.append(run_id)
            continue

        # Scrub reasoning keys
        for rk in list(r.keys()):
            if rk in REASONING_KEYS:
                del r[rk]
                scrubbed_fields_count += 1

        # Map model
        if "model" in r:
            model = r["model"]
            if model in MODEL_MAP:
                r["model"] = MODEL_MAP[model]
            else:
                raise ValueError(f"Unmapped model: {model} in run {run_id}")

        if rec_type == "correction":
            cfields = r.get("corrected_fields", {})
            for rk in list(cfields.keys()):
                if rk in REASONING_KEYS:
                    del cfields[rk]
                    scrubbed_fields_count += 1
            if "model" in cfields and cfields["model"] in MODEL_MAP:
                cfields["model"] = MODEL_MAP[cfields["model"]]

            if not cfields:
                reasoning_only_corrections_removed.append(run_id)
                continue
            else:
                substantive_corrections_preserved.append(run_id)

        # Set v2 schema fields
        r["schema_version"] = 2
        r["evaluation_protocol"] = r.get("evaluation_protocol", "protocol_unknown")

        migrated_records.append(r)

    # Write migrated evaluations.jsonl
    os.makedirs("migrations", exist_ok=True)
    lines = [json.dumps(r, ensure_ascii=False) for r in migrated_records]
    content = "\n".join(lines) + "\n"

    with open(jsonl_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)

    with open(jsonl_path, "rb") as f:
        raw_after = f.read()
    after_sha256 = hashlib.sha256(raw_after).hexdigest()

    eval_count = sum(1 for r in migrated_records if r.get("record_type") == "evaluation")
    corr_count = sum(1 for r in migrated_records if r.get("record_type") == "correction")
    total_count = len(migrated_records)

    base_manifest = {
        "schema_version": 1,
        "manifest_type": "base_model_v2_migration",
        "generated_at": "2026-07-29T09:50:00Z",
        "source_base_sha": "27748b1fa4b70eb69f18047c31ec97c3505beb88",
        "starting_record_count": starting_record_count,
        "withdrawn_records": withdrawn_records,
        "reasoning_only_corrections_removed": reasoning_only_corrections_removed,
        "substantive_corrections_preserved": substantive_corrections_preserved,
        "final_evaluation_count": eval_count,
        "final_correction_count": corr_count,
        "final_total_count": total_count,
        "before_sha256": before_sha256,
        "after_sha256": after_sha256
    }
    with open("migrations/base-model-v2.json", "w", encoding="utf-8") as f:
        json.dump(base_manifest, f, indent=2)

    protocol_manifest = {
        "schema_version": 1,
        "manifest_type": "evaluation_protocol_v1",
        "generated_at": "2026-07-29T09:50:00Z",
        "total_evaluations": eval_count,
        "protocol_counts": {
            "gated_v1": 0,
            "legacy_pre_gate": 0,
            "protocol_unknown": eval_count
        },
        "records": {r["run_id"]: r["evaluation_protocol"] for r in migrated_records if r.get("record_type") == "evaluation"}
    }
    with open("migrations/evaluation-protocol-v1.json", "w", encoding="utf-8") as f:
        json.dump(protocol_manifest, f, indent=2)

    scrub_receipt = {
        "schema_version": 1,
        "manifest_type": "reasoning_scrub_receipt",
        "generated_at": "2026-07-29T09:50:00Z",
        "scrubbed_fields_count": scrubbed_fields_count,
        "reasoning_keys_removed": list(REASONING_KEYS),
        "removed_reasoning_only_correction_ids": reasoning_only_corrections_removed
    }
    with open("migrations/reasoning-scrub-receipt.json", "w", encoding="utf-8") as f:
        json.dump(scrub_receipt, f, indent=2)

    correction_manifest = {
        "schema_version": 1,
        "manifest_type": "correction_migration_manifest",
        "generated_at": "2026-07-29T09:50:00Z",
        "starting_corrections": 4,
        "withdrawn_corrections": [r for r in withdrawn_records if "correction" in r],
        "reasoning_only_corrections_removed": reasoning_only_corrections_removed,
        "substantive_corrections_preserved": substantive_corrections_preserved,
        "final_correction_count": corr_count
    }
    with open("migrations/correction-migration-manifest.json", "w", encoding="utf-8") as f:
        json.dump(correction_manifest, f, indent=2)

    print(f"Migration completed successfully!")
    print(f"Starting records: {starting_record_count}")
    print(f"Withdrawn: {len(withdrawn_records)}")
    print(f"Reasoning-only removed: {len(reasoning_only_corrections_removed)}")
    print(f"Final evaluations: {eval_count}")
    print(f"Final corrections: {corr_count}")
    print(f"Final total: {total_count}")
    print(f"Before SHA256: {before_sha256}")
    print(f"After SHA256: {after_sha256}")

if __name__ == "__main__":
    migrate()
