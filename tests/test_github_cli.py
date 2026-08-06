from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from scripts.processor.common import ProcessorError
from scripts.processor.github_cli import run_json_command


class TestStrictGitHubCommandBoundary(unittest.TestCase):
    def run_child(self, payload: list[int], *, returncode: int = 0):
        script = (
            "import sys;"
            f"sys.stdout.buffer.write(bytes({payload!r}));"
            "sys.stderr.buffer.write(bytes([114,97,119,45,115,116,100,101,114,114]));"
            f"raise SystemExit({returncode})"
        )
        with tempfile.TemporaryDirectory(prefix="strict-gh-bytes-") as raw:
            return run_json_command(
                [sys.executable, "-c", script],
                repository_root=Path(raw),
                failure_code="processor_source_unavailable",
            )

    def test_genuine_utf8_subprocess_bytes_decode_before_json(self):
        # {"body":"é"} encoded directly as bytes, never through a mojibaked string.
        payload = [
            123, 34, 98, 111, 100, 121, 34, 58, 34,
            195, 169,
            34, 125,
        ]
        self.assertEqual(self.run_child(payload), {"body": "\u00e9"})

    def test_malformed_utf8_fails_with_generic_code(self):
        with self.assertRaises(ProcessorError) as raised:
            self.run_child([123, 34, 120, 34, 58, 34, 255, 34, 125])
        self.assertEqual(raised.exception.code, "processor_source_unavailable")
        self.assertNotIn("raw-stderr", str(raised.exception))

    def test_nonzero_exit_never_decodes_or_echoes_stderr(self):
        with self.assertRaises(ProcessorError) as raised:
            self.run_child([123, 125], returncode=2)
        self.assertEqual(raised.exception.code, "processor_source_unavailable")
        self.assertNotIn("raw-stderr", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
