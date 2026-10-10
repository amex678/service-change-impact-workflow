import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import demo_replay  # noqa: E402


class ReplayTests(unittest.TestCase):
    def test_frozen_demo_and_unchanged_second_run_are_reproducible_offline(self):
        with tempfile.TemporaryDirectory() as temporary:
            first, second = Path(temporary) / "first", Path(temporary) / "second"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(demo_replay.replay(first), 12)
                self.assertEqual(demo_replay.replay(second, first / "report" / "candidates.json"), 0)
            data = json.loads((first / "report" / "candidates.json").read_text(encoding="utf-8"))
            self.assertEqual(len(data["assessments"]), 12)
            self.assertTrue(data["inputs"]["azure_updates"]["sample"])
            markdown = (second / "report" / "impact-report.md").read_text(encoding="utf-8")
            self.assertIn("the AI agent was not started", markdown)
            self.assertTrue((second / "noop.jsonl").is_file())


if __name__ == "__main__":
    unittest.main()
