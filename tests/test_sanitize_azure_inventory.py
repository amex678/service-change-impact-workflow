import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import sanitize_azure_inventory as sanitize  # noqa: E402

WHITELIST = json.loads((ROOT / "config" / "inventory-properties.json").read_text(encoding="utf-8"))
SUB = "00000000-1111-2222-3333-444444444444"
DISK_ID = f"/subscriptions/{SUB}/resourceGroups/Prod-RG/providers/Microsoft.Compute/disks/contoso-vm01_OsDisk"
APP_ID = f"/subscriptions/{SUB}/resourceGroups/Prod-RG/providers/Microsoft.Web/sites/contoso-payroll-func"

GENERIC = [
    {"id": DISK_ID, "name": "contoso-vm01_OsDisk", "type": "Microsoft.Compute/disks", "location": "japaneast",
     "resourceGroup": "Prod-RG", "sku": {"name": "Standard_LRS", "tier": "Standard"}, "tags": {"owner": "alice"}},
    {"id": APP_ID, "name": "contoso-payroll-func", "type": "Microsoft.Web/sites", "kind": "functionapp",
     "location": "japaneast", "resourceGroup": "Prod-RG", "tags": {"cost-center": "123"}},
]
DISK_DETAIL = [{"id": DISK_ID, "diskSizeGB": 127, "osType": "Windows", "diskState": "Attached"}]
APP_DETAIL = {"value": [{"id": APP_ID, "properties": {"siteConfig": {"powerShellVersion": "7.4"}, "httpsOnly": True}}]}


class LookupTests(unittest.TestCase):
    def test_properties_first_then_top_level(self):
        self.assertEqual(sanitize.lookup({"properties": {"a": {"b": 1}}, "a": {"b": 2}}, "a.b"), 1)
        self.assertEqual(sanitize.lookup({"diskSizeGB": 127}, "diskSizeGB"), 127)

    def test_array_path_collects_unique_values(self):
        resource = {"properties": {"agentPoolProfiles": [{"osSKU": "Ubuntu"}, {"osSKU": "AzureLinux"}, {"osSKU": "Ubuntu"}]}}
        self.assertEqual(sanitize.lookup(resource, "agentPoolProfiles[].osSKU"), ["AzureLinux", "Ubuntu"])


class SanitizeTests(unittest.TestCase):
    def run_sanitize(self):
        merged = sanitize.merge_by_id([GENERIC, DISK_DETAIL, APP_DETAIL["value"]])
        return sanitize.sanitize(merged, WHITELIST, "test scope", "2026-10-01T00:00:00Z")

    def test_merge_enriches_generic_listing(self):
        inventory, _ = self.run_sanitize()
        by_type = {r["type"]: r for r in inventory["resources"]}
        disk = by_type["microsoft.compute/disks"]
        self.assertEqual(disk["properties"], {"diskSizeGB": 127, "osType": "Windows", "diskState": "Attached"})
        self.assertEqual(disk["sku"], {"name": "Standard_LRS", "tier": "Standard"})
        self.assertEqual(by_type["microsoft.web/sites"]["properties"],
                         {"siteConfig.powerShellVersion": "7.4", "httpsOnly": True})

    def test_identifiers_names_and_tags_are_removed(self):
        inventory, name_map = self.run_sanitize()
        text = json.dumps(inventory)
        for secret in (SUB, "contoso", "Prod-RG", "alice", "cost-center"):
            self.assertNotIn(secret, text)
        self.assertEqual({r["name"] for r in inventory["resources"]}, {"disks-01", "sites-01"})
        self.assertEqual({r["resource_group"] for r in inventory["resources"]}, {"rg-01"})
        self.assertEqual(name_map["resources"]["disks-01"], DISK_ID)
        self.assertFalse(inventory["sample"])

    def test_main_writes_name_map_only_when_requested(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            source = base / "resources.json"
            source.write_text(json.dumps(GENERIC), encoding="utf-8")
            output = base / "inventory.json"
            sanitize.main([str(source), "--properties", str(ROOT / "config" / "inventory-properties.json"),
                           "--output", str(output)])
            self.assertTrue(output.exists())
            self.assertEqual(sorted(p.name for p in base.iterdir()), ["inventory.json", "resources.json"])
            name_map = base / "raw" / "name-map.json"
            sanitize.main([str(source), "--properties", str(ROOT / "config" / "inventory-properties.json"),
                           "--output", str(output), "--name-map", str(name_map)])
            self.assertIn("disks-01", json.loads(name_map.read_text(encoding="utf-8"))["resources"])


if __name__ == "__main__":
    unittest.main()
