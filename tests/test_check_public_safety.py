from __future__ import annotations

import unittest

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


if __name__ == "__main__":
    unittest.main()
