import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import assessment  # noqa: E402
import restore_assessment as restore  # noqa: E402


class RestoreTests(unittest.TestCase):
    def test_no_previous_report_is_visible_and_does_not_create_fake_state(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(restore, "gh_json", return_value=[]):
            output = Path(temporary) / "previous.json"
            self.assertFalse(restore.restore("amex678/service-change-impact-workflow", "10", output))
            self.assertFalse(output.exists())

    def test_expired_report_is_not_used(self):
        responses = [[{"databaseId": 1, "headBranch": "main"}],
                     {"artifacts": [{"name": "report", "expired": True}]}]
        with tempfile.TemporaryDirectory() as temporary, patch.object(restore, "gh_json", side_effect=responses), \
                patch.object(restore.subprocess, "run") as download:
            self.assertFalse(restore.restore("amex678/service-change-impact-workflow", "10",
                                             Path(temporary) / "previous.json"))
            download.assert_not_called()

    def test_verified_state_is_restored_without_current_or_other_branch_runs(self):
        state = {"assessment_state_version": assessment.STATE_VERSION, "assessments": {
            "Azure 1": {"fingerprint": "a" * 64, "verdict": "Needs investigation",
                        "assessed_at": "2026-10-10T00:00:00Z"}}}
        responses = [[{"databaseId": 10, "headBranch": "main"}, {"databaseId": 9, "headBranch": "untrusted"},
                      {"databaseId": 8, "headBranch": "main"}],
                     {"artifacts": [{"name": "report", "expired": False}]}]
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "previous.json"
            metadata = output.parent / "previous-report-8" / "run" / "report" / "candidates.json"
            metadata.parent.mkdir(parents=True)
            metadata.write_text(json.dumps(state), encoding="utf-8")
            with patch.object(restore, "gh_json", side_effect=responses), patch.object(restore.subprocess, "run") as download:
                self.assertTrue(restore.restore("amex678/service-change-impact-workflow", "10", output))
                download.assert_called_once()
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), state)

    def test_github_retrieval_failure_is_not_a_successful_empty_state(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(restore, "gh_json", side_effect=OSError("denied")):
            with self.assertRaisesRegex(OSError, "denied"):
                restore.restore("amex678/service-change-impact-workflow", "10", Path(temporary) / "previous.json")


if __name__ == "__main__":
    unittest.main()
