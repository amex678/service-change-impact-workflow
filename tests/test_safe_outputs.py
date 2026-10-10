import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_safe_outputs as guard  # noqa: E402
from test_publish_report import DRAFT, candidates  # noqa: E402


class CreationGuardTests(unittest.TestCase):
    def test_duplicate_pr_for_tracked_finding_is_rejected_before_writes(self):
        data = candidates()
        data["candidates"][0]["tracking_issue"] = {"issue": 4, "state": "OPEN"}
        outputs = {"items": [{"type": "create_pull_request", "title": "Azure 572770: upgrade to 7.6"}]}
        with self.assertRaisesRegex(ValueError, "existing finding"):
            guard.validate(data, DRAFT, outputs)

    def test_open_remediation_pr_is_not_duplicated(self):
        data = candidates()
        data["candidates"][0]["tracking_pull_request"] = {"number": 9, "state": "OPEN"}
        outputs = {"items": [{"type": "create_pull_request", "title": "Azure 572770: upgrade to 7.6"}]}
        with self.assertRaisesRegex(ValueError, "open PR"):
            guard.validate(data, DRAFT, outputs)

    def test_duplicate_finding_issue_is_rejected(self):
        data = candidates()
        data["candidates"][0]["tracking_issue"] = {"issue": 4, "state": "OPEN"}
        outputs = {"items": [{"type": "create_issue", "title": "Azure 572770: PowerShell retirement"}]}
        with self.assertRaisesRegex(ValueError, "existing finding"):
            guard.validate(data, DRAFT, outputs)

    def test_new_impacted_azure_candidate_can_still_propose_one_pr(self):
        outputs = {"items": [{"type": "create_pull_request", "title": "Azure 572770: upgrade to 7.6"}]}
        self.assertEqual(guard.validate(candidates(), DRAFT, outputs), 1)

    def test_investigation_is_not_a_remediation_pr(self):
        outputs = {"items": [{"type": "create_pull_request", "title": "M365 MC-SAMPLE-001: change SMS"}]}
        with self.assertRaisesRegex(ValueError, "only an Impacted Azure"):
            guard.validate(candidates(), DRAFT, outputs)

    def test_comments_and_noop_remain_allowed(self):
        outputs = {"items": [{"type": "add_comment", "item_number": 4, "body": "Reassessment"},
                             {"type": "noop", "message": "No new work"}]}
        self.assertEqual(guard.validate(candidates(), DRAFT, outputs), 0)

    def test_unselected_notice_is_not_allowed_to_create_work(self):
        outputs = {"items": [{"type": "create_issue", "title": "Azure 999: unrelated"}]}
        with self.assertRaisesRegex(ValueError, "unselected"):
            guard.validate(candidates(), DRAFT, outputs)

    def test_compiled_gate_precedes_safe_output_processing(self):
        compiled = (ROOT / ".github" / "workflows" / "service-change-impact.lock.yml").read_text(encoding="utf-8")
        self.assertLess(compiled.index("name: Reject duplicate finding and PR creation before writes"),
                        compiled.index("name: Process Safe Outputs"))


if __name__ == "__main__":
    unittest.main()
