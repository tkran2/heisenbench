#!/usr/bin/env python3
"""Integration checks for parsing, errors, and deterministic replay."""

from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
BINARY = Path(sys.argv[1]).resolve()
sys.argv = [sys.argv[0]]


def run(*arguments, text=None):
    return subprocess.run([str(BINARY), *arguments], input=text, text=True, capture_output=True)


class CliTests(unittest.TestCase):
    def test_replay_matches_expected_and_both_implementations(self):
        expected = (ROOT / "examples/session.expected.txt").read_text()
        for implementation in ("tree", "flat"):
            result = run("--impl", implementation, "--check", "--file", str(ROOT / "examples/session.txt"))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, expected)

    def test_quiet_replay_has_same_summary(self):
        full = run("--file", str(ROOT / "examples/session.txt"))
        quiet = run("--quiet", "--file", str(ROOT / "examples/session.txt"))
        self.assertEqual(quiet.returncode, 0, quiet.stderr)
        self.assertEqual(quiet.stdout, full.stdout.splitlines()[-1] + "\n")

    def test_reject_does_not_stop_session(self):
        result = run(text="LIMIT 1 BUY 100 2\nLIMIT 1 SELL 100 2\nBOOK\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("REJECT 2 1 DUPLICATE_ID", result.stdout)
        self.assertIn("LEVEL BUY 100 2 1", result.stdout)

    def test_invalid_syntax_reports_line(self):
        result = run(text="# header\nLIMIT 1 BUY 100 2 extra\n")
        self.assertEqual(result.returncode, 2)
        self.assertIn("line 2", result.stderr)

    def test_invalid_number_and_unknown_options(self):
        self.assertEqual(run(text="CANCEL -1\n").returncode, 2)
        self.assertEqual(run("--impl", "unknown").returncode, 2)
        self.assertEqual(run("--file").returncode, 2)
        self.assertEqual(run("--file", "does-not-exist.txt").returncode, 2)

    def test_quit_stops_reading(self):
        result = run(text="QUIT\nINVALID\n")
        self.assertEqual(result.returncode, 0)
        self.assertIn("commands=0", result.stdout)

    def test_help(self):
        result = run("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("new_remaining_quantity", result.stdout)


if __name__ == "__main__":
    unittest.main()
