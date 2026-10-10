import argparse
import copy
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import prepare_candidates as prep  # noqa: E402
import assessment  # noqa: E402

AS_OF = datetime(2026, 10, 1, tzinfo=timezone.utc)
PRODUCT_MAP = json.loads((ROOT / "config" / "product-map.json").read_text(encoding="utf-8"))
HINTS = json.loads((ROOT / "config" / "evidence-hints.json").read_text(encoding="utf-8"))


def azure_notice(notice_id, title, products, tags=("Retirements",), retire=(2026, "November"), text=""):
    availabilities = [{"ring": "Retirement", "year": retire[0], "month": retire[1]}] if retire else []
    return {"id": notice_id, "title": title, "products": list(products), "tags": list(tags),
            "availabilities": availabilities, "description_text": text, "modified": "2026-09-20T00:00:00Z"}


FUNCTION_APP = {"name": "sites-01", "type": "microsoft.web/sites", "kind": "functionapp",
                "properties": {"siteConfig.powerShellVersion": "7.4", "siteConfig.minTlsVersion": "1.2"}}
OS_DISK = {"name": "disks-01", "type": "microsoft.compute/disks", "sku": {"name": "Standard_LRS"},
           "properties": {"osType": "Windows"}}
STORAGE = {"name": "storageaccounts-01", "type": "microsoft.storage/storageaccounts", "kind": "StorageV2",
           "sku": {"name": "Standard_LRS"}, "properties": {}}


class Workspace:
    """Write inputs to a temporary folder and run prepare_candidates.main()."""

    def __init__(self, updates, resources, messages=None, profile=None, issues=None, complete=True, previous=None):
        self.dir = tempfile.TemporaryDirectory()
        base = Path(self.dir.name)
        self.paths = {name: base / f"{name}.json" for name in
                      ("updates", "inventory", "messages", "profile", "issues", "output", "previous")}
        self.include_m365 = messages is not None
        self.noop = base / "safeoutputs" / "outputs.jsonl"
        self._write("updates", {"items": updates, "count": len(updates), "complete": complete})
        self._write("inventory", {"resources": resources})
        if messages is not None:
            self._write("messages", {"messages": messages})
            self._write("profile", profile or {"services_in_use": []})
        if issues is not None:
            self._write("issues", issues)
        if previous is not None:
            self._write("previous", previous)

    def _write(self, name, data):
        self.paths[name].write_text(json.dumps(data), encoding="utf-8")

    def run(self, *extra):
        argv = ["--azure-updates", str(self.paths["updates"]), "--azure-inventory", str(self.paths["inventory"]),
                "--product-map", str(ROOT / "config" / "product-map.json"),
                "--evidence-hints", str(ROOT / "config" / "evidence-hints.json"),
                "--m365-notices", str(self.paths["messages"]), "--m365-profile", str(self.paths["profile"]),
                "--existing-issues", str(self.paths["issues"]), "--output", str(self.paths["output"]),
                "--include-m365", str(self.include_m365).lower(),
                "--noop-file", str(self.noop), *extra]
        if self.paths["previous"].exists():
            argv.extend(["--previous-report", str(self.paths["previous"])])
        self.exit_code = prep.main(argv, as_of=AS_OF)
        return json.loads(self.paths["output"].read_text(encoding="utf-8"))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.dir.cleanup()


class ProductMapTests(unittest.TestCase):
    def test_every_mapped_product_exists_in_observed_vocabulary(self):
        vocabulary = json.loads((ROOT / "config" / "azure-updates-products.json").read_text(encoding="utf-8"))
        known = {entry["name"] for entry in vocabulary["products"]}
        used = {p for rule in PRODUCT_MAP["rules"] for p in rule["products"]}
        used |= set(PRODUCT_MAP["subscription_wide_products"]["products"])
        self.assertEqual(sorted(used - known), [])

    def test_function_app_maps_to_functions_and_app_service(self):
        self.assertEqual(prep.resource_products(FUNCTION_APP, PRODUCT_MAP), ["Azure Functions", "App Service"])

    def test_coverage_reports_unmapped_and_ignored_types(self):
        inventory = {"resources": [FUNCTION_APP, {"name": "x", "type": "microsoft.purview/accounts"},
                                   {"name": "y", "type": "microsoft.managedidentity/userassignedidentities"}]}
        resources, coverage = prep.index_inventory(inventory, PRODUCT_MAP)
        self.assertEqual(len(resources), 1)
        self.assertEqual(coverage["unmapped_types"], {"microsoft.purview/accounts": 1})
        self.assertEqual(coverage["ignored_types"], {"microsoft.managedidentity/userassignedidentities": 1})


class EvidenceTests(unittest.TestCase):
    def test_disk_sku_alias_applies_to_disks_only(self):
        self.assertIn("standard hdd", prep.resource_facts(OS_DISK, HINTS))
        self.assertIn("os disk", prep.resource_facts(OS_DISK, HINTS))
        self.assertNotIn("standard hdd", prep.resource_facts(STORAGE, HINTS))

    def test_runtime_version_phrase(self):
        facts = prep.resource_facts(FUNCTION_APP, HINTS)
        self.assertEqual(facts["powershell 7.4"], 2)
        score, found = prep.evidence("Support for PowerShell\u202f7.4 ends.", {"sites-01": facts})
        self.assertEqual({entry["phrase"] for entry in found}, {"powershell", "powershell 7.4"})
        self.assertEqual(score, 3)

    def test_plural_and_punctuation(self):
        self.assertTrue(prep.phrase_in("os disk", prep.normalize_text("OS Disks on Standard HDD.")))
        self.assertTrue(prep.phrase_in("standard hdd", prep.normalize_text("OS Disks on Standard HDD.")))
        self.assertFalse(prep.phrase_in("tls 1.2", prep.normalize_text("TLS 1.25")))

    def test_linux_fx_version_is_normalized(self):
        facts = prep.resource_facts({"type": "microsoft.web/sites", "properties": {"siteConfig.linuxFxVersion": "PYTHON|3.11"}}, HINTS)
        self.assertIn("python 3.11", facts)


class CandidateTests(unittest.TestCase):
    def test_matching_runtime_is_ranked_before_other_runtimes(self):
        updates = [azure_notice("1", "Support for Python 3.10 ends", ["Azure Functions"]),
                   azure_notice("2", "Support for PowerShell 7.4 ends", ["Azure Functions"])]
        with Workspace(updates, [FUNCTION_APP]) as ws:
            result = ws.run()
        self.assertEqual([c["key"] for c in result["candidates"]], ["Azure 2", "Azure 1"])
        self.assertEqual(result["candidates"][0]["matched_resources"][0]["name"], "sites-01")

    def test_notice_without_matching_product_is_out_of_scope(self):
        updates = [azure_notice("1", "AKS change", ["Azure Kubernetes Service (AKS)"])]
        with Workspace(updates, [FUNCTION_APP]) as ws:
            result = ws.run()
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["counts"]["out_of_scope"]["azure"], 1)

    def test_legacy_tracked_notice_is_re_evaluated_without_duplicate_finding(self):
        updates = [azure_notice("572770", "Support for PowerShell 7.4 ends", ["Azure Functions"])]
        issues = [{"number": 7, "title": "[service-change] Azure 572770: Support for PowerShell 7.4 ends", "state": "OPEN"}]
        with Workspace(updates, [FUNCTION_APP], issues=issues) as ws:
            result = ws.run()
        self.assertEqual(result["candidates"][0]["tracking_issue"]["issue"], 7)
        self.assertEqual(result["already_tracked"], [])
        self.assertTrue(any("re-evaluated" in warning for warning in result["warnings"]))

    def test_informational_notice_is_deferred_not_evaluated(self):
        updates = [azure_notice("1", "New feature", ["Azure Functions"], tags=("Features",), retire=None)]
        with Workspace(updates, [FUNCTION_APP]) as ws:
            result = ws.run()
        self.assertEqual(result["candidates"], [])
        self.assertIn("informational", result["deferred"][0]["reason"])

    def test_review_tracked_keeps_issue_link_and_does_not_write_noop(self):
        updates = [azure_notice("572770", "Support for PowerShell 7.4 ends", ["Azure Functions"])]
        issues = [{"number": 4, "title": "[service-change] Azure 572770: Support for PowerShell 7.4 ends", "state": "OPEN"}]
        with Workspace(updates, [FUNCTION_APP], issues=issues) as ws:
            result = ws.run("--review-tracked", "true")
            self.assertFalse(ws.noop.exists())
        self.assertEqual(result["candidates"][0]["tracking_issue"], {"issue": 4, "state": "OPEN"})
        self.assertEqual(result["already_tracked"], [])
        self.assertTrue(result["inputs"]["existing_issues"]["review_tracked"])

    def test_review_tracked_still_respects_candidate_limit(self):
        updates = [azure_notice(str(i), f"Retirement {i}", ["Azure Functions"]) for i in range(3)]
        issues = [{"number": i + 1, "title": f"[service-change] Azure {i}: Retirement {i}"} for i in range(3)]
        with Workspace(updates, [FUNCTION_APP], issues=issues) as ws:
            result = ws.run("--review-tracked", "true", "--max-azure", "1")
        self.assertEqual(len(result["candidates"]), 1)
        self.assertEqual(len(result["deferred"]), 2)
        self.assertEqual(result["already_tracked"], [])

    def test_overdue_retirement_is_flagged(self):
        updates = [azure_notice("1", "Old runtime retired", ["Azure Functions"], retire=(2026, "August"))]
        with Workspace(updates, [FUNCTION_APP]) as ws:
            result = ws.run()
        signal = result["candidates"][0]["signal"]
        self.assertEqual(signal["months_until_deadline"], -2)
        self.assertIn("passed", signal["reason"])

    def test_subscription_wide_retirement_becomes_candidate(self):
        updates = [azure_notice("1", "ARM API retirement", ["Azure Resource Manager"])]
        with Workspace(updates, [FUNCTION_APP]) as ws:
            result = ws.run()
        self.assertEqual(result["candidates"][0]["scope"], "subscription")

    def test_per_source_limit_defers_overflow(self):
        updates = [azure_notice(str(i), f"Retirement {i}", ["Azure Functions"]) for i in range(4)]
        with Workspace(updates, [FUNCTION_APP]) as ws:
            result = ws.run("--max-azure", "2")
        self.assertEqual(len(result["candidates"]), 2)
        self.assertEqual(sum("per-run limit" in d["reason"] for d in result["deferred"]), 2)
        self.assertTrue(any("per-run limit" in warning for warning in result["warnings"]))

    def test_m365_matches_services_in_use_and_setting_hints(self):
        messages = [{"id": "MC1", "title": "SMS sign-in change", "services": ["Microsoft Entra"],
                     "category": "planForChange", "isMajorChange": True, "body": "SMS"},
                    {"id": "MC2", "title": "Viva update", "services": ["Microsoft Viva"], "category": "stayInformed"}]
        profile = {"services_in_use": ["Microsoft Entra"], "settings": {"entra.authenticationMethods.sms": {}}}
        with Workspace([], [], messages=messages, profile=profile) as ws:
            result = ws.run()
        self.assertEqual([c["key"] for c in result["candidates"]], ["M365 MC1"])
        self.assertIn("sms", {h["phrase"] for h in result["candidates"][0]["evidence_hints"]})
        self.assertEqual(result["counts"]["out_of_scope"]["m365"], 1)


class NoopTests(unittest.TestCase):
    def test_noop_written_when_nothing_to_evaluate(self):
        with Workspace([], [FUNCTION_APP]) as ws:
            ws.run()
            lines = ws.noop.read_text(encoding="utf-8").splitlines()
        self.assertEqual(json.loads(lines[0])["type"], "noop")

    def test_no_noop_when_fetch_incomplete(self):
        with Workspace([], [FUNCTION_APP], complete=False) as ws:
            result = ws.run()
            self.assertFalse(ws.noop.exists())
            self.assertEqual(ws.exit_code, 2)
        self.assertTrue(any("incomplete" in warning for warning in result["warnings"]))

    def test_no_noop_when_candidates_exist(self):
        updates = [azure_notice("1", "Support for PowerShell 7.4 ends", ["Azure Functions"])]
        with Workspace(updates, [FUNCTION_APP]) as ws:
            ws.run()
            self.assertFalse(ws.noop.exists())

    def test_missing_requested_m365_does_not_become_a_healthy_noop(self):
        with Workspace([], [FUNCTION_APP]) as ws:
            result = ws.run("--include-m365", "true")
            self.assertEqual(ws.exit_code, 2)
            self.assertFalse(ws.noop.exists())
        self.assertFalse(result["inputs_complete"])
        self.assertTrue(any("Microsoft 365" in warning and "missing" in warning for warning in result["warnings"]))

    def test_missing_inventory_does_not_become_a_healthy_noop(self):
        with Workspace([], []) as ws:
            ws.paths["inventory"].unlink()
            result = ws.run()
            self.assertEqual(ws.exit_code, 2)
            self.assertFalse(ws.noop.exists())
        self.assertFalse(result["inputs_complete"])


class RevisionTests(unittest.TestCase):
    def setUp(self):
        self.notice = azure_notice("572770", "Support for PowerShell 7.4 ends", ["Azure Functions"])
        self.issues = [{"number": 4, "title": "[service-change] Azure 572770: Original notice", "state": "OPEN"}]
        with Workspace([self.notice], [FUNCTION_APP]) as ws:
            first = ws.run()
        self.previous = {"assessment_state_version": assessment.STATE_VERSION, "assessments": {
            "Azure 572770": {"fingerprint": first["candidates"][0]["assessment_fingerprint"],
                             "verdict": "Impacted", "assessed_at": "2026-09-30T00:00:00Z",
                             "run_url": "https://github.com/amex678/service-change-impact-workflow/actions/runs/1"}}}

    def test_unchanged_notice_and_configuration_skip_ai(self):
        with Workspace([self.notice], [FUNCTION_APP], issues=self.issues, previous=self.previous) as ws:
            result = ws.run()
            self.assertTrue(ws.noop.exists())
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["already_tracked"][0]["issue"], 4)

    def test_changed_notice_is_re_evaluated_and_linked_to_existing_issue(self):
        changed = {**self.notice, "modified": "2026-10-01T00:00:00Z", "description_text": "Revised conditions"}
        with Workspace([changed], [FUNCTION_APP], issues=self.issues, previous=self.previous) as ws:
            result = ws.run()
        self.assertEqual(result["candidates"][0]["tracking_issue"]["issue"], 4)
        self.assertNotEqual(result["candidates"][0]["assessment_fingerprint"],
                            self.previous["assessments"]["Azure 572770"]["fingerprint"])

    def test_changed_inventory_is_re_evaluated(self):
        resource = copy.deepcopy(FUNCTION_APP)
        resource["properties"]["siteConfig.powerShellVersion"] = "7.6"
        with Workspace([self.notice], [resource], issues=self.issues, previous=self.previous) as ws:
            result = ws.run()
        self.assertEqual(len(result["candidates"]), 1)

    def test_expired_assessment_is_re_evaluated(self):
        self.previous["assessments"]["Azure 572770"]["assessed_at"] = "2026-09-01T00:00:00Z"
        with Workspace([self.notice], [FUNCTION_APP], issues=self.issues, previous=self.previous) as ws:
            result = ws.run()
        self.assertEqual(len(result["candidates"]), 1)

    def test_cannot_evaluate_is_not_cached_as_complete(self):
        self.previous["assessments"]["Azure 572770"]["verdict"] = "Cannot evaluate"
        with Workspace([self.notice], [FUNCTION_APP], issues=self.issues, previous=self.previous) as ws:
            result = ws.run()
        self.assertEqual(len(result["candidates"]), 1)

    def test_unpublished_finding_is_not_lost(self):
        with Workspace([self.notice], [FUNCTION_APP], previous=self.previous) as ws:
            result = ws.run()
        self.assertEqual(len(result["candidates"]), 1)

    def test_not_impacted_assessment_does_not_need_an_issue(self):
        self.previous["assessments"]["Azure 572770"]["verdict"] = "Not impacted"
        with Workspace([self.notice], [FUNCTION_APP], previous=self.previous) as ws:
            result = ws.run()
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["already_tracked"][0]["verdict"], "Not impacted")

    def test_manual_review_still_forces_re_evaluation(self):
        with Workspace([self.notice], [FUNCTION_APP], issues=self.issues, previous=self.previous) as ws:
            result = ws.run("--review-tracked", "true")
        self.assertEqual(len(result["candidates"]), 1)

    def test_invalid_state_does_not_silently_skip_candidates(self):
        self.previous["assessments"]["Azure 572770"]["fingerprint"] = "invalid"
        with Workspace([self.notice], [FUNCTION_APP], issues=self.issues, previous=self.previous) as ws:
            with self.assertRaisesRegex(ValueError, "fingerprint"):
                ws.run()

    def test_future_assessment_time_is_not_treated_as_current(self):
        self.previous["assessments"]["Azure 572770"]["assessed_at"] = "2026-10-02T00:00:00Z"
        with Workspace([self.notice], [FUNCTION_APP], issues=self.issues, previous=self.previous) as ws:
            result = ws.run()
        self.assertEqual(len(result["candidates"]), 1)

    def test_known_missing_evidence_guard_is_visible_to_the_agent(self):
        notice = azure_notice("557852", "TLS 1.0 and 1.1", ["Azure Functions"])
        notice["modified"] = assessment.REVIEWED_REVISIONS["Azure 557852"]
        with Workspace([notice], [FUNCTION_APP]) as ws:
            result = ws.run()
        requirements = result["candidates"][0]["evidence_requirements"]
        self.assertEqual(requirements["allowed_verdicts"], ["Cannot evaluate", "Needs investigation"])
        self.assertIn("SCM", requirements["reason"])


class SampleDataTests(unittest.TestCase):
    def test_boolean_options_preserve_supported_values(self):
        for value in ("true", "1", "YES"):
            self.assertTrue(prep.parse_boolean(value))
        for value in ("false", "0", "NO"):
            self.assertFalse(prep.parse_boolean(value))

    def test_invalid_boolean_is_rejected_instead_of_enabling_review(self):
        with self.assertRaisesRegex(argparse.ArgumentTypeError, "Expected true or false"):
            prep.parse_boolean("uncertain")

    def test_samples_are_marked_synthetic(self):
        for name in ("azure-inventory.sample.json", "m365-message-center.sample.json", "m365-tenant-profile.sample.json"):
            data = json.loads((ROOT / "data" / "samples" / name).read_text(encoding="utf-8"))
            self.assertIs(data.get("sample"), True, name)

    def test_public_output_rejects_real_inventory(self):
        with Workspace([], [FUNCTION_APP]) as ws:
            with self.assertRaisesRegex(ValueError, "synthetic Azure inventory"):
                ws.run("--public-output", "--include-m365", "false")

    def test_public_output_rejects_real_notices_even_with_sample_profile(self):
        with Workspace([], [], messages=[], profile={"sample": True, "services_in_use": []}) as ws:
            ws._write("inventory", {"sample": True, "resources": []})
            with self.assertRaisesRegex(ValueError, "synthetic Microsoft 365 notices"):
                ws.run("--public-output")

    def test_public_output_accepts_only_all_sample_inputs(self):
        with Workspace([], [], messages=[], profile={"sample": True, "services_in_use": []}) as ws:
            ws._write("inventory", {"sample": True, "resources": []})
            ws._write("messages", {"sample": True, "messages": []})
            ws._write("profile", {"sample": True, "services_in_use": []})
            result = ws.run("--public-output")
        self.assertTrue(result["inputs"]["m365"]["notices_sample"])
        self.assertTrue(result["inputs"]["m365"]["profile_sample"])


if __name__ == "__main__":
    unittest.main()
