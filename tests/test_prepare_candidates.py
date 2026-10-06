import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import prepare_candidates as prep  # noqa: E402

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

    def __init__(self, updates, resources, messages=None, profile=None, issues=None, complete=True):
        self.dir = tempfile.TemporaryDirectory()
        base = Path(self.dir.name)
        self.paths = {name: base / f"{name}.json" for name in
                      ("updates", "inventory", "messages", "profile", "issues", "output")}
        self.noop = base / "safeoutputs" / "outputs.jsonl"
        self._write("updates", {"items": updates, "count": len(updates), "complete": complete})
        self._write("inventory", {"resources": resources})
        if messages is not None:
            self._write("messages", {"messages": messages})
            self._write("profile", profile or {"services_in_use": []})
        if issues is not None:
            self._write("issues", issues)

    def _write(self, name, data):
        self.paths[name].write_text(json.dumps(data), encoding="utf-8")

    def run(self, *extra):
        argv = ["--azure-updates", str(self.paths["updates"]), "--azure-inventory", str(self.paths["inventory"]),
                "--product-map", str(ROOT / "config" / "product-map.json"),
                "--evidence-hints", str(ROOT / "config" / "evidence-hints.json"),
                "--m365-notices", str(self.paths["messages"]), "--m365-profile", str(self.paths["profile"]),
                "--existing-issues", str(self.paths["issues"]), "--output", str(self.paths["output"]),
                "--noop-file", str(self.noop), *extra]
        prep.main(argv, as_of=AS_OF)
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

    def test_already_tracked_notice_is_skipped(self):
        updates = [azure_notice("572770", "Support for PowerShell 7.4 ends", ["Azure Functions"])]
        issues = [{"number": 7, "title": "[service-change] Azure 572770: Support for PowerShell 7.4 ends", "state": "OPEN"}]
        with Workspace(updates, [FUNCTION_APP], issues=issues) as ws:
            result = ws.run()
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["already_tracked"][0]["issue"], 7)

    def test_informational_notice_is_deferred_not_evaluated(self):
        updates = [azure_notice("1", "New feature", ["Azure Functions"], tags=("Features",), retire=None)]
        with Workspace(updates, [FUNCTION_APP]) as ws:
            result = ws.run()
        self.assertEqual(result["candidates"], [])
        self.assertIn("informational", result["deferred"][0]["reason"])

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
        self.assertTrue(any("incomplete" in warning for warning in result["warnings"]))

    def test_no_noop_when_candidates_exist(self):
        updates = [azure_notice("1", "Support for PowerShell 7.4 ends", ["Azure Functions"])]
        with Workspace(updates, [FUNCTION_APP]) as ws:
            ws.run()
            self.assertFalse(ws.noop.exists())


class SampleDataTests(unittest.TestCase):
    def test_samples_are_marked_synthetic(self):
        for name in ("azure-inventory.sample.json", "m365-message-center.sample.json", "m365-tenant-profile.sample.json"):
            data = json.loads((ROOT / "data" / "samples" / name).read_text(encoding="utf-8"))
            self.assertIs(data.get("sample"), True, name)


if __name__ == "__main__":
    unittest.main()
