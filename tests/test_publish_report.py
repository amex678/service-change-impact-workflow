import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import publish_report as report  # noqa: E402
import assessment  # noqa: E402


def candidates():
    return {
        "generated_at": "2026-10-10T00:00:00Z",
        "inputs": {
            "azure_updates": {"count": 20, "complete": True, "since": "2026-09-26", "path": "run/private-path.json"},
            "azure_inventory": {"sample": True, "scope": "sample", "captured_at": "2026-10-01"},
            "m365": {"included": True, "sample": True, "notices_sample": True, "profile_sample": True, "count": 4},
        },
        "counts": {"candidates": 2, "deferred": 1, "already_tracked": 0, "out_of_scope": {"azure": 17, "m365": 1}},
        "coverage": {"resources_mapped": 10, "resources_total": 12, "unmapped_types": {"microsoft.purview/accounts": 1},
                     "ignored_types": {"microsoft.managedidentity/userassignedidentities": 1}},
        "warnings": ["Synthetic sample."],
        "candidates": [
            {"key": "Azure 572770", "source": "azure",
             "notice": {"id": "572770", "title": "PowerShell retirement", "url": "https://azure.microsoft.com/updates?id=572770",
                        "description_text": "A complete notice body that should not be republished."}},
            {"key": "M365 MC-SAMPLE-001", "source": "m365",
             "notice": {"id": "MC-SAMPLE-001", "title": "SMS sign-in", "body": "Fictional full notice body."}},
        ],
        "deferred": [{"key": "Azure 1", "title": "Informational", "reason": "informational"}],
        "already_tracked": [],
    }


DRAFT = """# Service-change impact report

## 2. Verdicts

| Notice | Change and effective date | Matched resources | Deciding evidence | Verdict | Next step |
|---|---|---|---|---|---|
| Azure 572770: PowerShell | 2026-11-10 | sites-01 | PowerShell 7.4 matches the retiring version. | Impacted | Review PR 9. |
| M365 MC-SAMPLE-001: SMS | 2026-12-01 | SMS policy | SMS enabled does not capture isUsableForSignIn. | Needs investigation | Read the target sign-in flag. |

## 3. Details for Impacted and Needs investigation

### Azure 572770: PowerShell

- **Source:** https://azure.microsoft.com/updates?id=572770
- **Checked:** PowerShell 7.4.

### M365 MC-SAMPLE-001: SMS

- **Checked:** SMS enabled; the primary sign-in flag is missing.
"""


class ValidationTests(unittest.TestCase):
    def test_every_candidate_is_validated(self):
        self.assertEqual(len(report.validate_report(candidates(), DRAFT, True)), 2)

    def test_missing_candidate_fails(self):
        draft = "\n".join(line for line in DRAFT.splitlines() if not line.startswith("| M365"))
        with self.assertRaisesRegex(ValueError, "coverage mismatch"):
            report.validate_report(candidates(), draft)

    def test_duplicate_candidate_fails(self):
        draft = DRAFT.replace("| M365 MC-SAMPLE-001: SMS", "| Azure 572770: duplicate")
        with self.assertRaisesRegex(ValueError, "duplicate candidate"):
            report.validate_report(candidates(), draft)

    def test_unlisted_candidate_fails(self):
        with self.assertRaisesRegex(ValueError, "coverage mismatch"):
            report.validate_report(candidates(), DRAFT.replace("Azure 572770:", "Azure 999:"))

    def test_invalid_verdict_fails(self):
        with self.assertRaisesRegex(ValueError, "Invalid verdict"):
            report.validate_report(candidates(), DRAFT.replace("| Impacted |", "| Probably impacted |"))

    def test_missing_detail_fails(self):
        with self.assertRaisesRegex(ValueError, "detail section"):
            report.validate_report(candidates(), DRAFT.replace("### Azure 572770:", "### Other:"))

    def test_literal_newline_formatting_fails(self):
        with self.assertRaisesRegex(ValueError, "literal newline"):
            report.validate_report(candidates(), DRAFT + r"\n\n**Deadline**")

    def test_incomplete_fetch_does_not_support_impact_verdict(self):
        data = candidates()
        data["inputs"]["azure_updates"]["complete"] = False
        with self.assertRaisesRegex(ValueError, "Incomplete Azure fetch"):
            report.validate_report(data, DRAFT)

    def test_public_output_rejects_real_inventory(self):
        data = candidates()
        data["inputs"]["azure_inventory"]["sample"] = False
        with self.assertRaisesRegex(ValueError, "synthetic Azure"):
            report.validate_report(data, DRAFT, True)

    def test_public_output_rejects_real_message_bodies(self):
        data = candidates()
        data["inputs"]["m365"]["notices_sample"] = False
        with self.assertRaisesRegex(ValueError, "synthetic Microsoft 365"):
            report.validate_report(data, DRAFT, True)


class PublicationTests(unittest.TestCase):
    def test_complete_zero_candidate_report_is_visible_and_verifiable(self):
        data = candidates()
        data["inputs_complete"] = True
        data["candidates"] = []
        data["counts"]["candidates"] = 0
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            self.assertEqual(report.publish(data, report.noop_report(data), output, public_output=True), 0)
            self.assertEqual(report.verify(output, True), 0)
            markdown = (output / "impact-report.md").read_text(encoding="utf-8")
            self.assertIn("the AI agent was not started", markdown)
            self.assertIn("not an environment-wide no-impact finding", markdown)

    def test_incomplete_zero_candidate_input_cannot_be_published_as_noop(self):
        data = candidates()
        data["candidates"] = []
        data["counts"]["candidates"] = 0
        data["inputs_complete"] = False
        with self.assertRaisesRegex(ValueError, "complete inputs"):
            report.noop_report(data)

    def test_publication_records_the_assessed_revision_fingerprint(self):
        data = candidates()
        for candidate in data["candidates"]:
            candidate["assessment_fingerprint"] = assessment.digest(candidate)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            report.publish(data, DRAFT, output, public_output=True)
            metadata = json.loads((output / "candidates.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["assessments"]["Azure 572770"]["verdict"], "Impacted")
            self.assertEqual(metadata["assessments"]["Azure 572770"]["fingerprint"],
                              data["candidates"][0]["assessment_fingerprint"])
            self.assertEqual(report.verify(output, True), 2)

    def test_invented_disk_role_is_not_preserved_in_the_trusted_resource_column(self):
        data = candidates()
        data["candidates"][0]["matched_resources"] = [
            {"name": "disks-02", "type": "microsoft.compute/disks", "sku": {"name": "Standard_LRS"}, "properties": {}}]
        draft = DRAFT.replace("| sites-01 |", "| disks-02 is a data disk |")
        markdown = report.canonical_report(data, draft)
        self.assertNotIn("disks-02 is a data disk", markdown)
        self.assertIn("OS/data role not captured", markdown)

    def test_compiled_workflow_delivers_validated_report_after_publication(self):
        compiled = (ROOT / ".github" / "workflows" / "service-change-impact.lock.yml").read_text(encoding="utf-8")
        self.assertLess(compiled.index("name: Validate every verdict and stage the complete report"),
                        compiled.index("name: Deliver the validated report (including zero-candidate runs)"))
        self.assertIn("overwrite: true", compiled)
        self.assertNotIn('"upload_artifact":', compiled)

    def test_committed_review_covers_all_twelve_candidates_and_the_sms_correction(self):
        data = json.loads((ROOT / "docs" / "reports" / "review-candidates.json").read_text(encoding="utf-8"))
        markdown = (ROOT / "docs" / "reports" / "impact-report.md").read_text(encoding="utf-8")
        rows = report.validate_report(data, markdown, True)
        self.assertEqual(len(rows), 12)
        by_key = {row[0]: row[4] for row in rows}
        self.assertEqual(by_key["M365 MC-SAMPLE-001"], "Needs investigation")
        self.assertEqual(by_key["Azure 557852"], "Needs investigation")
        self.assertEqual(sum(value == "Impacted" for value in by_key.values()), 2)
        self.assertEqual(by_key["Azure 560948"], "Needs investigation")
        self.assertEqual(sum(value == "Not impacted" for value in by_key.values()), 2)
        self.assertEqual(sum(value == "Needs investigation" for value in by_key.values()), 8)

    def test_real_message_without_url_does_not_link_to_a_fictional_notice(self):
        candidate = candidates()["candidates"][1]
        self.assertIsNone(report.notice_url(candidate))
        self.assertEqual(report.notice_url(candidate, True), report.SAMPLE_URL)

    def test_reviewed_publication_retains_the_original_workflow_run(self):
        data = candidates()
        data["report_run_url"] = "https://github.com/amex678/service-change-impact-workflow/actions/runs/38012531004"
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            report.publish(data, DRAFT, output)
            self.assertIn(data["report_run_url"], (output / "impact-report.md").read_text(encoding="utf-8"))
            self.assertEqual(report.verify(output), 2)

    def test_mixed_samples_are_not_mislabelled_as_an_all_sample_environment(self):
        data = candidates()
        data["inputs"]["azure_inventory"]["sample"] = False
        data["inputs"]["m365"]["profile_sample"] = False
        markdown = report.canonical_report(data, DRAFT)
        self.assertIn("notices=sample; profile=not sample", markdown)
        html = report.render_html(data, markdown)
        self.assertIn("keep this report private", html)

    def test_files_are_staged_and_verified_without_republishing_notice_bodies(self):
        data, original = candidates(), copy.deepcopy(candidates())
        with tempfile.TemporaryDirectory() as temporary:
            output, stage = Path(temporary) / "output", Path(temporary) / "staging" / "run" / "report"
            self.assertEqual(report.publish(data, DRAFT, output, stage, public_output=True), 2)
            self.assertEqual({path.name for path in stage.iterdir()}, report.FILES)
            self.assertEqual(report.verify(stage, True), 2)
            html = (stage / "index.html").read_text(encoding="utf-8")
            self.assertEqual(html.count('data-verdict="'), 2)
            self.assertIn("SYNTHETIC SAMPLE", html)
            snapshot = json.loads((stage / "candidates.json").read_text(encoding="utf-8"))
            self.assertNotIn("description_text", snapshot["candidates"][0]["notice"])
            self.assertNotIn("body", snapshot["candidates"][1]["notice"])
            self.assertNotIn("path", snapshot["inputs"]["azure_updates"])
        self.assertEqual(data, original)

    def test_missing_html_is_not_a_successful_artifact(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            report.publish(candidates(), DRAFT, output)
            (output / "index.html").unlink()
            with self.assertRaisesRegex(ValueError, "exactly Markdown, HTML"):
                report.verify(output)

    def test_modified_html_is_not_a_successful_artifact(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            report.publish(candidates(), DRAFT, output)
            (output / "index.html").write_text("<p>Incomplete</p>", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "does not match"):
                report.verify(output)

    def test_html_escapes_untrusted_text(self):
        data = candidates()
        data["candidates"][0]["notice"]["title"] = "<script>alert(1)</script>"
        markdown = report.canonical_report(data, DRAFT)
        html = report.render_html(data, markdown)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertNotIn("<script>alert(1)</script>", html)

    def test_unsafe_links_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            report.inline_markdown("[source](javascript:alert)")

    def test_sample_title_brackets_preserve_the_clickable_source(self):
        value = report.inline_markdown("[M365 MC-SAMPLE-001: [SAMPLE] SMS](https://github.com/amex678/example)")
        self.assertEqual(value, '<a href="https://github.com/amex678/example">M365 MC-SAMPLE-001: [SAMPLE] SMS</a>')

    def test_wrong_notice_source_is_rejected(self):
        data = candidates()
        data["candidates"][0]["notice"]["url"] = "https://azure.microsoft.com/updates?id=999"
        with self.assertRaisesRegex(ValueError, "does not identify"):
            report.canonical_report(data, DRAFT)


if __name__ == "__main__":
    unittest.main()
