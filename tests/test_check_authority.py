from __future__ import annotations

import copy
import unittest

from scripts.processor.cleanup_workflow import _required_check_attempts


HEAD = "a" * 40


def run(
    run_id: int,
    *,
    path: str,
    event: str,
    number: int,
    attempt: int = 1,
    status: str = "completed",
    conclusion: str | None = "success",
    head_sha: str = HEAD,
) -> dict:
    return {
        "id": run_id,
        "workflow_id": 1000 + run_id,
        "path": path,
        "event": event,
        "run_number": number,
        "run_attempt": attempt,
        "check_suite_id": 2000 + run_id,
        "head_sha": head_sha,
        "status": status,
        "conclusion": conclusion,
    }


def jobs(run_value: dict, names: tuple[str, ...], conclusion: str | None = "success") -> list[dict]:
    return [
        {
            "id": run_value["id"] * 10 + index,
            "run_id": run_value["id"],
            "name": name,
            "head_sha": run_value["head_sha"],
            "status": "completed",
            "conclusion": conclusion,
        }
        for index, name in enumerate(names, start=1)
    ]


def successful_fixture():
    runs = [
        run(1, path=".github/workflows/ci.yml", event="push", number=10),
        run(2, path=".github/workflows/ci.yml", event="pull_request", number=11),
        run(3, path=".github/workflows/public-safety.yml", event="pull_request", number=12),
        run(4, path="dynamic/github-code-scanning/codeql", event="dynamic", number=13),
    ]
    by_attempt = {
        (runs[0]["id"], 1): jobs(runs[0], ("validate",)),
        (runs[1]["id"], 1): jobs(runs[1], ("validate",)),
        (runs[2]["id"], 1): jobs(runs[2], ("Scan public ledger",)),
        (runs[3]["id"], 1): jobs(runs[3], ("Analyze (python)", "Analyze (actions)")),
    }
    return runs, by_attempt


class TestAuthoritativeRequiredCheckAttempts(unittest.TestCase):
    def test_older_success_followed_by_newer_failure(self):
        runs, by_attempt = successful_fixture()
        newer = run(
            5,
            path=".github/workflows/ci.yml",
            event="push",
            number=20,
            conclusion="failure",
        )
        runs.append(newer)
        by_attempt[(5, 1)] = jobs(newer, ("validate",), conclusion="failure")
        self.assertEqual(_required_check_attempts(HEAD, runs, by_attempt)[0], "incomplete")

    def test_older_failure_followed_by_newer_success(self):
        runs, by_attempt = successful_fixture()
        older = run(
            5,
            path=".github/workflows/ci.yml",
            event="push",
            number=1,
            conclusion="failure",
        )
        runs.append(older)
        by_attempt[(5, 1)] = jobs(older, ("validate",), conclusion="failure")
        self.assertEqual(_required_check_attempts(HEAD, runs, by_attempt)[0], "passed")

    def test_rerun_attempt_supersedes_prior_attempt(self):
        runs, by_attempt = successful_fixture()
        first = runs[0]
        first["conclusion"] = "failure"
        by_attempt[(first["id"], 1)] = jobs(first, ("validate",), conclusion="failure")
        rerun = copy.deepcopy(first)
        rerun["run_attempt"] = 2
        rerun["conclusion"] = "success"
        runs.append(rerun)
        by_attempt[(rerun["id"], 2)] = jobs(rerun, ("validate",))
        status, evidence = _required_check_attempts(HEAD, runs, by_attempt)
        self.assertEqual(status, "passed")
        self.assertEqual(evidence["ci_push"]["run_attempt"], 2)

    def test_same_name_job_from_different_workflow_cannot_satisfy(self):
        runs, by_attempt = successful_fixture()
        runs = [item for item in runs if not (item["path"] == ".github/workflows/ci.yml" and item["event"] == "push")]
        foreign = run(9, path=".github/workflows/other.yml", event="push", number=99)
        runs.append(foreign)
        by_attempt[(9, 1)] = jobs(foreign, ("validate",))
        self.assertEqual(_required_check_attempts(HEAD, runs, by_attempt)[0], "incomplete")

    def test_duplicate_conflicting_latest_candidates_fail_closed(self):
        runs, by_attempt = successful_fixture()
        duplicate = run(9, path=".github/workflows/ci.yml", event="push", number=10)
        runs.append(duplicate)
        by_attempt[(9, 1)] = jobs(duplicate, ("validate",))
        self.assertEqual(_required_check_attempts(HEAD, runs, by_attempt)[0], "incomplete")

    def test_skipped_and_neutral_latest_jobs_fail_closed(self):
        for conclusion in ("skipped", "neutral"):
            runs, by_attempt = successful_fixture()
            by_attempt[(1, 1)] = jobs(runs[0], ("validate",), conclusion=conclusion)
            self.assertEqual(
                _required_check_attempts(HEAD, runs, by_attempt)[0],
                "incomplete",
            )

    def test_wrong_head_never_counts(self):
        runs, by_attempt = successful_fixture()
        runs[0]["head_sha"] = "b" * 40
        by_attempt[(1, 1)] = jobs(runs[0], ("validate",))
        self.assertEqual(_required_check_attempts(HEAD, runs, by_attempt)[0], "incomplete")

    def test_missing_producer_or_run_metadata_fails_closed(self):
        runs, by_attempt = successful_fixture()
        del runs[0]["workflow_id"]
        self.assertEqual(_required_check_attempts(HEAD, runs, by_attempt)[0], "incomplete")
        runs, by_attempt = successful_fixture()
        del by_attempt[(1, 1)]
        self.assertEqual(_required_check_attempts(HEAD, runs, by_attempt)[0], "incomplete")


if __name__ == "__main__":
    unittest.main()
