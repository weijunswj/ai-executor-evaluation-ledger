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


if __name__ == "__main__":
    unittest.main()
