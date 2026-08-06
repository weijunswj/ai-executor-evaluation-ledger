from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from scripts import check_public_safety as safety


class CompanionUrlPolicyTests(unittest.TestCase):
    def test_single_canonical_readme_link_is_allowed(self) -> None:
        text = safety.COMPANION_README_LINE + "\n"
        prepared, failures = safety.prepare_tracked_text("README.md", text)

        self.assertEqual([], failures)
        self.assertEqual([], safety.scan_text("README.md", prepared))

    def test_duplicate_readme_link_is_rejected(self) -> None:
        text = f"{safety.COMPANION_README_LINE}\n{safety.COMPANION_README_LINE}\n"
        prepared, failures = safety.prepare_tracked_text("README.md", text)

        self.assertTrue(failures)
        self.assertTrue(safety.scan_text("README.md", prepared))

    def test_link_in_another_file_is_rejected(self) -> None:
        failures = safety.scan_text(
            "scripts/example.py",
            f'url = "{safety.COMPANION_URL}"',
        )

        self.assertTrue(any("GitHub repository URL" in item for item in failures))

    def test_suffix_after_markdown_close_is_rejected(self) -> None:
        text = safety.COMPANION_README_LINE.replace(").", ")/issues/123.")
        prepared, policy_failures = safety.prepare_tracked_text("README.md", text)

        self.assertTrue(policy_failures)
        self.assertTrue(safety.scan_text("README.md", prepared))

    def test_apostrophe_suffix_is_rejected(self) -> None:
        text = (
            "Used in conjunction with "
            f"[{safety.COMPANION_LINK_LABEL}]({safety.COMPANION_URL}'/issues/123)."
        )
        prepared, policy_failures = safety.prepare_tracked_text("README.md", text)

        self.assertTrue(policy_failures)
        self.assertTrue(safety.scan_text("README.md", prepared))

    def test_exact_historical_readme_line_is_allowed_only_at_bound_commit(self) -> None:
        text = safety.LEGACY_REVERSED_README_LINE + "\n"
        prepared = safety.prepare_historical_text(
            "fc0c69d71d2e8ca28c8bcae0cf06f0010031377b",
            "README.md",
            text,
        )

        self.assertEqual([], safety.scan_text("history", prepared))

        unbound = safety.prepare_historical_text(
            "0" * 40,
            "README.md",
            text,
        )
        self.assertTrue(safety.scan_text("history", unbound))

    def test_historical_script_exception_is_file_bound(self) -> None:
        text = safety.LEGACY_SCRIPT_URL_LINE + "\n"
        prepared = safety.prepare_historical_text(
            "1b6bef8bb0ae32934a31bad5ac388c9f525205ff",
            "scripts/check_public_safety.py",
            text,
        )

        self.assertEqual([], safety.scan_text("history", prepared))

        wrong_file = safety.prepare_historical_text(
            "1b6bef8bb0ae32934a31bad5ac388c9f525205ff",
            "evaluations.jsonl",
            text,
        )
        self.assertTrue(safety.scan_text("history", wrong_file))

    def test_current_readme_history_line_is_exact(self) -> None:
        text = safety.COMPANION_README_LINE + "\n"
        prepared = safety.prepare_historical_text(
            "4b7da9295ccfbe4cb27867601db0a70f9f3a405b",
            "README.md",
            text,
        )

        self.assertEqual([], safety.scan_text("history", prepared))

        suffixed = text.replace(").", ")/issues/123.")
        prepared_suffix = safety.prepare_historical_text(
            "4b7da9295ccfbe4cb27867601db0a70f9f3a405b",
            "README.md",
            suffixed,
        )
        self.assertTrue(safety.scan_text("history", prepared_suffix))


class LiteralPathspecTests(unittest.TestCase):
    """Prove that literal pathspec handling remains correct for all filenames."""

    def test_normal_filename_patch_is_retrieved(self) -> None:
        additions = safety.added_lines_for_path(
            "4b7da9295ccfbe4cb27867601db0a70f9f3a405b",
            "README.md",
        )

        self.assertIn(safety.COMPANION_README_LINE, additions)

    def test_changed_files_in_known_commit(self) -> None:
        files = safety.changed_files_in_commit(
            "4b7da9295ccfbe4cb27867601db0a70f9f3a405b"
        )

        self.assertIn("README.md", files)

    def test_leading_colon_filename_would_receive_literal_prefix(self) -> None:
        fake = ":(exclude)**"
        cmd = [
            "git",
            "show",
            "--format=",
            "--unified=0",
            "--no-renames",
            "HEAD",
            "--",
            ":(literal)" + fake,
        ]

        self.assertEqual(":(literal)" + fake, cmd[-1])
        self.assertTrue(cmd[-1].startswith(":(literal)"))

    def test_exclude_shaped_filename_cannot_suppress_own_patch(self) -> None:
        fake_label = ":(exclude)**"
        result = safety.added_lines_for_path("HEAD", fake_label)

        self.assertEqual("", result)

    def test_top_pathspec_magic_prefix_handled_literally(self) -> None:
        fake_label = ":(top)README.md"
        result = safety.added_lines_for_path("HEAD", fake_label)

        self.assertEqual("", result)

    def test_second_pathspec_magic_prefix_handled_literally(self) -> None:
        fake_label = ":README.md"
        result = safety.added_lines_for_path("HEAD", fake_label)

        self.assertEqual("", result)

    def test_deleted_file_with_prohibited_content_still_scanned_in_history(
        self,
    ) -> None:
        additions = safety.added_lines_for_path(
            "1b6bef8bb0ae32934a31bad5ac388c9f525205ff",
            "scripts/check_public_safety.py",
        )

        self.assertIn(safety.LEGACY_SCRIPT_URL_LINE, additions)

    def test_unknown_commit_file_returns_empty_additions(self) -> None:
        import subprocess

        try:
            safety.added_lines_for_path("0" * 40, "NONEXISTENT_FILE")
        except subprocess.CalledProcessError:
            pass  # expected: unknown commit
        # The key property: the function called git with :(literal) prefix,
        # not a bare filename that could trigger pathspec magic.


class BroadExceptionTests(unittest.TestCase):
    """Prove host-wide, repository-wide or generic URL exceptions are rejected."""

    def test_no_url_prefix_exception_remains(self) -> None:
        from scripts.check_public_safety import COMPANION_URL, URL_MASK

        self.assertNotIn("github.com", URL_MASK)

    def test_no_host_wide_exception_exists(self) -> None:
        from scripts.check_public_safety import HISTORICAL_ALLOWED_LINES

        for (commit, label), lines in HISTORICAL_ALLOWED_LINES.items():
            self.assertIsInstance(commit, str)
            self.assertEqual(40, len(commit))
            self.assertIsInstance(label, str)
            for line in lines:
                self.assertIn(safety.COMPANION_URL, line)

    def test_no_generic_url_exception_in_rules(self) -> None:
        import re
        from scripts.check_public_safety import RULES

        found = False
        for rule_name, pattern in RULES:
            if rule_name == "GitHub repository URL":
                text = safety.COMPANION_URL
                self.assertIsNotNone(pattern.search(text))
                found = True
                break
        self.assertTrue(found)


class LedgerIdentityPolicyTests(unittest.TestCase):
    def test_current_tree_scan_rejects_every_forbidden_token(self) -> None:
        tokens = set(safety.FORBIDDEN_LEDGER_IDENTITY_TOKENS)
        self.assertEqual(14, len(tokens))
        self.assertEqual(tokens, set(safety.FORBIDDEN_LEDGER_IDENTITY_TOKENS))
        for token in tokens:
            self.assertTrue(
                safety.scan_ledger_identity("tracked/current.txt", "prefix " + token),
                token,
            )

    def test_migration_audit_is_count_only_not_a_token_exception(self) -> None:
        forbidden_attribute = next(
            token
            for token in safety.FORBIDDEN_LEDGER_IDENTITY_TOKENS
            if token.startswith("requested")
        )
        self.assertTrue(
            safety.scan_ledger_identity(
                "migrations/reasoning-scrub-receipt.json",
                forbidden_attribute,
            )
        )
        count_only = '{"removed_attribute_key_count":6}'
        self.assertEqual(
            [],
            safety.scan_ledger_identity(
                "migrations/reasoning-scrub-receipt.json",
                count_only,
            ),
        )
        self.assertTrue(
            safety.scan_ledger_identity("tests/fixture.json", forbidden_attribute)
        )

    def test_normalized_variants_are_rejected_without_blocking_canonical_model(self) -> None:
        words = (*safety.GPT_MODEL_WORDS, safety.HIGH_SETTING_WORD)
        separators = (
            (" ", " ", " ", " "),
            ("-", "-", "-", "-"),
            ("_", "_", "_", "_"),
            (".", ".", ".", "."),
            (":", ":", ":", ":"),
            ("/", "/", "/", "/"),
            ("\\", "\\", "\\", "\\"),
            ("---", "___", "..", "  "),
            (",", ",", ",", ","),
            ("+", "+", "+", "+"),
            ("|", "|", "|", "|"),
            ("[", "][", "][", "]"),
            (",+|", "[]", "::", "\\/"),
            (chr(0x2014), chr(0xFF0C), chr(0x2022), chr(0x3001)),
        )
        for values in separators:
            variant = "".join(
                word + (values[index] if index < len(values) else "")
                for index, word in enumerate(words)
            )
            self.assertTrue(
                safety.scan_ledger_identity("tracked/current.txt", variant),
                variant,
            )
            self.assertTrue(
                safety.scan_ledger_identity(
                    "tracked/current.txt",
                    variant.swapcase(),
                ),
                variant,
            )
        compatibility_variant = "".join(
            chr(ord(character) + 0xFEE0)
            if "!" <= character <= "~"
            else character
            for character in ",".join(words)
        )
        self.assertTrue(
            safety.scan_ledger_identity(
                "tracked/current.txt",
                compatibility_variant,
            )
        )

        canonical = safety.GPT_MODEL_NAME
        self.assertEqual(
            [],
            safety.scan_ledger_identity("tracked/current.txt", canonical),
        )
        ordinary = "-".join(words)
        self.assertEqual(
            [],
            safety.scan_ledger_identity("tracked/current.txt", "x" + ordinary),
        )
        self.assertEqual(
            [],
            safety.scan_ledger_identity("tracked/current.txt", ordinary + "x"),
        )

    def test_normalized_attribute_variants_are_rejected_in_all_directories(self) -> None:
        words = safety.NATIVE_CLASSIFICATION_WORDS
        for separator in ("-", "_", " ", "...", ",+|", chr(0x2014)):
            variant = separator.join(words)
            for label in (
                "tests/fixture.json",
                "migrations/fixture.json",
                "scripts/fixture.py",
            ):
                self.assertTrue(safety.scan_ledger_identity(label, variant))

    def test_complete_token_boundaries_do_not_match_longer_alphanumeric_runs(self) -> None:
        words = (*safety.GPT_MODEL_WORDS, safety.MAX_SETTING_WORD)
        separated = ".".join(words)
        self.assertTrue(safety.scan_ledger_identity("tracked/current.txt", separated))
        self.assertEqual(
            [],
            safety.scan_ledger_identity("tracked/current.txt", "prefix" + separated),
        )
        self.assertEqual(
            [],
            safety.scan_ledger_identity("tracked/current.txt", separated + "suffix"),
        )


class HistoricalPipelineTests(unittest.TestCase):
    def git(self, root: Path, *args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    @contextmanager
    def activated_repo(
        self,
        root: Path,
        *,
        pre_activation: tuple[tuple[str, str], ...] = (),
    ):
        self.git(root, "init", "-q")
        self.git(root, "config", "core.autocrlf", "false")
        self.git(
            root,
            "config",
            "user.email",
            "fixture" + "@" + "example.invalid",
        )
        self.git(root, "config", "user.name", "fixture")
        (root / "seed.txt").write_text("seed\n", encoding="utf-8")
        self.git(root, "add", ".")
        self.git(root, "commit", "-qm", "seed")
        baseline = self.git(root, "rev-parse", "HEAD")
        (root / ".public-safety-baseline").write_bytes(
            (baseline + "\n").encode("ascii")
        )
        self.git(root, "add", ".public-safety-baseline")
        self.git(root, "commit", "-qm", "baseline")
        canonical = self.git(root, "rev-parse", "HEAD")
        for label, text in pre_activation:
            self.commit_text(root, text, label=label)
        (root / "activation.txt").write_text(
            "activation\n",
            encoding="utf-8",
        )
        self.git(root, "add", "activation.txt")
        self.git(root, "commit", "-qm", "activation boundary")
        activation = self.git(root, "rev-parse", "HEAD")
        with mock.patch.multiple(
            safety,
            GENERIC_HISTORY_BASELINE=baseline,
            CANONICAL_MAIN_BASE=canonical,
            PR_ACTIVATION_HEAD=activation,
            PRE_ACTIVATION_OCCURRENCE_COUNT=sum(
                len(safety.iter_ledger_identity_matches(text))
                for _label, text in pre_activation
            ),
        ):
            manifest = safety.expected_activation_manifest(root)
            path = root / safety.ACTIVATION_MANIFEST_RELATIVE_PATH
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(manifest, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
            self.git(root, "add", path.relative_to(root).as_posix())
            self.git(root, "commit", "-qm", "activation manifest")
            yield {
                "activation": activation,
                "baseline": baseline,
                "canonical": canonical,
                "manifest": manifest,
            }

    def commit_text(
        self,
        root: Path,
        text: str,
        *,
        label: str = "history.txt",
    ) -> None:
        (root / label).write_text(text + "\n", encoding="utf-8")
        self.git(root, "add", label)
        self.git(root, "commit", "-qm", "history fixture")

    def test_hosted_history_path_scans_normalized_add_then_delete_variants(self):
        words = (*safety.GPT_MODEL_WORDS, safety.HIGH_SETTING_WORD)
        punctuation = "...".join(words).swapcase()
        unicode_separators = chr(0x2014).join(words)
        compatibility = "".join(
            chr(ord(character) + 0xFEE0)
            if "!" <= character <= "~"
            else character
            for character in ",".join(words)
        )
        repeated = (chr(0x2022) * 3).join(words)
        with tempfile.TemporaryDirectory(
            prefix="public-safety-history-"
        ) as raw:
            root = Path(raw)
            with self.activated_repo(root):
                variants = (
                    punctuation,
                    unicode_separators,
                    compatibility,
                    repeated,
                )
                for index, variant in enumerate(variants):
                    self.commit_text(
                        root,
                        variant,
                        label=f"history-{index}.txt",
                    )
                for index in range(len(variants)):
                    (root / f"history-{index}.txt").unlink()
                self.git(root, "add", ".")
                self.git(root, "commit", "-qm", "delete history fixture")

                failures = safety.history_failures(root)
                identity_failures = [
                    item
                    for item in failures
                    if "forbidden ledger identity token" in item
                ]
                self.assertGreaterEqual(len(identity_failures), 4)
                diagnostics = "\n".join(failures)
                for variant in variants:
                    self.assertNotIn(variant, diagnostics)

    def test_historical_scan_fails_closed_on_invalid_utf8(self):
        with tempfile.TemporaryDirectory(
            prefix="public-safety-invalid-utf8-"
        ) as raw:
            root = Path(raw)
            with self.activated_repo(root):
                label = "invalid-utf8-fixture.txt"
                (root / label).write_bytes(
                    b"fixture-invalid-utf8-byte-\xff\n"
                )
                self.git(root, "add", label)
                self.git(root, "commit", "-qm", "invalid UTF-8 fixture")

                with self.assertRaises(RuntimeError) as caught:
                    safety.history_failures(root)

                diagnostic = str(caught.exception)
                self.assertEqual(
                    diagnostic,
                    "history patch is not strict UTF-8",
                )
                self.assertTrue(diagnostic.isascii())
                self.assertNotIn(chr(0xFFFD), diagnostic)
                self.assertNotIn("invalid-utf8-fixture", diagnostic)
                self.assertNotIn("fixture-invalid-utf8-byte", diagnostic)
                self.assertNotIn("gh" + "p_", diagnostic)

    def test_history_pipeline_preserves_generic_rules_after_deletion(self):
        secret = "gh" + "p_" + "A" * 24
        with tempfile.TemporaryDirectory(
            prefix="public-safety-generic-"
        ) as raw:
            root = Path(raw)
            with self.activated_repo(root):
                self.commit_text(root, secret, label="generic.txt")
                (root / "generic.txt").unlink()
                self.git(root, "add", "generic.txt")
                self.git(root, "commit", "-qm", "delete generic fixture")
                failures = safety.history_failures(root)
                self.assertTrue(
                    any("GitHub token" in item for item in failures)
                )
                self.assertNotIn(secret, "\n".join(failures))

    def test_history_pipeline_allows_canonical_and_longer_boundaries(self):
        words = (*safety.GPT_MODEL_WORDS, safety.HIGH_SETTING_WORD)
        longer = "prefix" + ".".join(words) + "suffix"
        with tempfile.TemporaryDirectory(
            prefix="public-safety-boundary-"
        ) as raw:
            root = Path(raw)
            with self.activated_repo(root):
                self.commit_text(
                    root,
                    safety.GPT_MODEL_NAME + "\n" + longer,
                )
                self.assertEqual([], safety.history_failures(root))

    def test_inventory_recomputes_and_manifest_is_closed(self):
        words = (*safety.GPT_MODEL_WORDS, safety.HIGH_SETTING_WORD)
        variant = "...".join(words)
        with tempfile.TemporaryDirectory(
            prefix="public-safety-inventory-"
        ) as raw:
            root = Path(raw)
            with self.activated_repo(
                root,
                pre_activation=(("legacy.txt", variant),),
            ) as authority:
                self.assertEqual(
                    authority["manifest"],
                    safety.validate_activation_manifest(root),
                )
                self.assertEqual(
                    (1, authority["manifest"]["pre_activation_inventory_sha256"]),
                    safety.pre_activation_inventory(root),
                )
                self.assertEqual(
                    safety.ACTIVATION_MANIFEST_FIELDS,
                    frozenset(authority["manifest"]),
                )

    def test_duplicate_and_malformed_inventory_descriptors_fail(self):
        descriptor = {
            "commit_sha": "a" * 40,
            "path": "safe.txt",
            "added_line_ordinal": 1,
            "match_ordinal": 1,
            "rule_id": "unicode_identity_001",
            "added_line_sha256": "b" * 64,
        }
        with self.assertRaisesRegex(RuntimeError, "duplicate"):
            safety.canonical_inventory_bytes([descriptor, descriptor])
        malformed = dict(descriptor)
        malformed["matched_text"] = "not persisted"
        with self.assertRaisesRegex(RuntimeError, "malformed"):
            safety.canonical_inventory_bytes([malformed])

    def test_rule_set_change_invalidates_manifest(self):
        with tempfile.TemporaryDirectory(
            prefix="public-safety-rule-set-"
        ) as raw:
            root = Path(raw)
            with self.activated_repo(root):
                changed_rules = safety.FORBIDDEN_LEDGER_IDENTITY_RULES + (
                    ("unicode_identity_999", ("nonmatching",)),
                )
                with mock.patch.object(
                    safety,
                    "FORBIDDEN_LEDGER_IDENTITY_RULES",
                    changed_rules,
                ):
                    with self.assertRaisesRegex(RuntimeError, "authority mismatch"):
                        safety.history_failures(root)

    def test_generic_baseline_and_pre_activation_range_remain_active(self):
        secret = "gh" + "p_" + "B" * 24
        with tempfile.TemporaryDirectory(
            prefix="public-safety-old-generic-"
        ) as raw:
            root = Path(raw)
            with self.activated_repo(
                root,
                pre_activation=(("legacy-secret.txt", secret),),
            ) as authority:
                failures = safety.history_failures(root)
                self.assertTrue(any("GitHub token" in item for item in failures))
                activation_blob = self.git(
                    root,
                    "show",
                    f"{authority['activation']}:.public-safety-baseline",
                )
                head_blob = self.git(
                    root,
                    "show",
                    "HEAD:.public-safety-baseline",
                )
                self.assertEqual(authority["baseline"], activation_blob)
                self.assertEqual(activation_blob, head_blob)

    def test_pre_activation_identity_is_inventory_not_failure(self):
        words = (*safety.GPT_MODEL_WORDS, safety.HIGH_SETTING_WORD)
        variant = chr(0x2014).join(words)
        with tempfile.TemporaryDirectory(
            prefix="public-safety-pre-activation-"
        ) as raw:
            root = Path(raw)
            with self.activated_repo(
                root,
                pre_activation=(("legacy-identity.txt", variant),),
            ):
                failures = safety.history_failures(root)
                self.assertFalse(
                    any("forbidden ledger identity token" in item for item in failures)
                )

    def test_pr_descendant_uses_activation_head(self):
        with tempfile.TemporaryDirectory(
            prefix="public-safety-pr-mode-"
        ) as raw:
            root = Path(raw)
            with self.activated_repo(root) as authority:
                start, mode = safety.unicode_history_start(
                    root,
                    authority["manifest"],
                )
                self.assertEqual(authority["activation"], start)
                self.assertEqual("pr-descendant", mode)

    def test_squash_descendant_uses_canonical_base_and_scans(self):
        words = (*safety.GPT_MODEL_WORDS, safety.HIGH_SETTING_WORD)
        variant = "...".join(words)
        with tempfile.TemporaryDirectory(
            prefix="public-safety-squash-mode-"
        ) as raw:
            root = Path(raw)
            with self.activated_repo(root) as authority:
                manifest_text = (
                    root / safety.ACTIVATION_MANIFEST_RELATIVE_PATH
                ).read_text(encoding="utf-8")
                self.git(
                    root,
                    "checkout",
                    "-qb",
                    "squash-fixture",
                    authority["canonical"],
                )
                manifest_path = root / safety.ACTIVATION_MANIFEST_RELATIVE_PATH
                manifest_path.parent.mkdir(parents=True, exist_ok=True)
                manifest_path.write_text(manifest_text, encoding="utf-8")
                self.commit_text(root, variant, label="squash-history.txt")
                self.git(root, "add", manifest_path.relative_to(root).as_posix())
                self.git(root, "commit", "--amend", "-qm", "synthetic squash")
                start, mode = safety.unicode_history_start(
                    root,
                    authority["manifest"],
                )
                self.assertEqual(authority["canonical"], start)
                self.assertEqual("canonical-main-squash", mode)
                self.assertTrue(
                    any(
                        "forbidden ledger identity token" in item
                        for item in safety.history_failures(root)
                    )
                )

    def test_missing_and_malformed_manifest_fail_closed(self):
        with tempfile.TemporaryDirectory(
            prefix="public-safety-manifest-failure-"
        ) as raw:
            root = Path(raw)
            with self.activated_repo(root):
                path = root / safety.ACTIVATION_MANIFEST_RELATIVE_PATH
                original = path.read_bytes()
                path.unlink()
                with self.assertRaisesRegex(RuntimeError, "unavailable"):
                    safety.history_failures(root)
                path.write_bytes(b"{")
                with self.assertRaisesRegex(RuntimeError, "malformed"):
                    safety.history_failures(root)

    def test_neither_authority_ancestor_fails_closed(self):
        with tempfile.TemporaryDirectory(
            prefix="public-safety-no-authority-"
        ) as raw:
            root = Path(raw)
            with self.activated_repo(root) as authority:
                self.git(root, "checkout", "-q", authority["baseline"])
                with self.assertRaisesRegex(RuntimeError, "ancestry"):
                    safety.unicode_history_start(root, authority["manifest"])

    def test_shallow_history_fails_closed(self):
        with tempfile.TemporaryDirectory(
            prefix="public-safety-complete-source-"
        ) as source_raw, tempfile.TemporaryDirectory(
            prefix="public-safety-shallow-parent-"
        ) as clone_parent:
            source = Path(source_raw)
            with self.activated_repo(source):
                shallow = Path(clone_parent) / "shallow"
                subprocess.run(
                    [
                        "git",
                        "clone",
                        "-q",
                        "--depth",
                        "1",
                        source.resolve().as_uri(),
                        str(shallow),
                    ],
                    check=True,
                    capture_output=True,
                )
                with self.assertRaisesRegex(RuntimeError, "incomplete"):
                    safety.history_failures(shallow)


if __name__ == "__main__":
    unittest.main()
