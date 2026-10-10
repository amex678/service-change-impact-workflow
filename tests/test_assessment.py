import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import assessment  # noqa: E402


def candidate(key):
    source, notice_id = key.split(" ", 1)
    field = "modified" if source == "Azure" else "lastModifiedDateTime"
    return {"key": key, "source": source.lower(), "notice": {"id": notice_id, field: assessment.REVIEWED_REVISIONS[key]},
            "matched_resources": [], "tenant_settings": {}, "assessment_context": {}}


class EvidenceGuardTests(unittest.TestCase):
    def test_five_historical_missing_facts_do_not_allow_impact_or_no_impact(self):
        for key in assessment.REVIEWED_REVISIONS:
            with self.subTest(key=key):
                data = candidate(key)
                self.assertEqual(assessment.evidence_guard(data)[0], {"Needs investigation", "Cannot evaluate"})
                for verdict in ("Impacted", "Not impacted"):
                    with self.assertRaisesRegex(ValueError, "Unsupported"):
                        assessment.check_verdict(data, verdict)

    def test_sms_enabled_without_primary_signin_flag_is_insufficient(self):
        data = candidate("M365 MC-SAMPLE-001")
        data["tenant_settings"]["entra.authenticationMethods.sms"] = {"value": "enabled for all users", "source": "sample"}
        with self.assertRaisesRegex(ValueError, "primary sign-in"):
            assessment.check_verdict(data, "Impacted")

    def test_explicit_sms_primary_signin_flag_supports_the_right_direction(self):
        for value, verdict in ((True, "Impacted"), (False, "Not impacted")):
            with self.subTest(value=value):
                data = candidate("M365 MC-SAMPLE-001")
                data["tenant_settings"]["entra.authenticationMethods.sms.isUsableForSignIn"] = {
                    "value": value, "source": "captured sample policy target"}
                assessment.check_verdict(data, verdict)
                opposite = "Not impacted" if value else "Impacted"
                with self.assertRaises(ValueError):
                    assessment.check_verdict(data, opposite)

    def test_region_is_not_subscription_cloud(self):
        data = candidate("Azure 498749")
        data["matched_resources"] = [{"name": "vm-01", "location": "japaneast"}]
        with self.assertRaisesRegex(ValueError, "cloud"):
            assessment.check_verdict(data, "Not impacted")
        data["assessment_context"]["cloud"] = "AzureCloud"
        assessment.check_verdict(data, "Not impacted")

    def test_vm_series_is_not_reservation_order_evidence(self):
        data = candidate("Azure 560948")
        data["matched_resources"] = [{"name": "vm-01", "properties": {"hardwareProfile.vmSize": "Standard_D2s_v5"}}]
        with self.assertRaisesRegex(ValueError, "reservation-order"):
            assessment.check_verdict(data, "Not impacted")

    def test_preview_uses_specific_configuration_not_monitor_presence(self):
        data = candidate("Azure 551523")
        data["matched_resources"] = [{"name": "components-01", "properties": {"IngestionMode": "LogAnalytics"}}]
        with self.assertRaisesRegex(ValueError, "preview export"):
            assessment.check_verdict(data, "Not impacted")
        data["assessment_context"]["observations"] = {
            "azureMonitor.vmClientPreviewExport.enabled": {"value": False, "source": "captured DCR setting"}}
        assessment.check_verdict(data, "Not impacted")

    def test_main_tls_does_not_prove_scm_or_client_compatibility(self):
        data = candidate("Azure 557852")
        data["matched_resources"] = [{"name": "sites-01", "type": "microsoft.web/sites",
                                      "properties": {"siteConfig.minTlsVersion": "1.2"}}]
        with self.assertRaisesRegex(ValueError, "SCM"):
            assessment.check_verdict(data, "Not impacted")
        data["matched_resources"][0]["properties"]["siteConfig.scmMinTlsVersion"] = "1.2"
        with self.assertRaisesRegex(ValueError, "Client"):
            assessment.check_verdict(data, "Not impacted")
        data["assessment_context"]["observations"] = {
            "functionApp.clients.supportTls12": {"value": True, "source": "captured client compatibility test"}}
        assessment.check_verdict(data, "Not impacted")

    def test_changed_notice_revision_does_not_reuse_old_conditions(self):
        data = candidate("Azure 498749")
        data["notice"]["modified"] = "2026-10-10T00:00:00Z"
        data["assessment_context"]["cloud"] = "AzureCloud"
        with self.assertRaisesRegex(ValueError, "revision"):
            assessment.check_verdict(data, "Not impacted")

    def test_unknown_disk_role_is_rendered_from_the_snapshot(self):
        data = {"matched_resources": [{"name": "disks-02", "type": "microsoft.compute/disks",
                                       "sku": {"name": "Standard_LRS"}, "properties": {}}]}
        scope = assessment.captured_scope(data)
        self.assertIn("OS/data role not captured", scope)
        self.assertNotIn("is a data disk", scope)


class FingerprintTests(unittest.TestCase):
    def test_capture_time_and_resource_order_do_not_trigger_false_deltas(self):
        first = {"captured_at": "2026-10-01", "resources": [{"name": "b"}, {"name": "a"}]}
        second = {"captured_at": "2026-10-10", "resources": [{"name": "a"}, {"name": "b"}]}
        self.assertEqual(assessment.configuration(first), assessment.configuration(second))

    def test_real_configuration_change_is_not_ignored(self):
        first = {"resources": [{"name": "sites-01", "properties": {"powerShellVersion": "7.4"}}]}
        second = copy.deepcopy(first)
        second["resources"][0]["properties"]["powerShellVersion"] = "7.6"
        self.assertNotEqual(assessment.digest(assessment.configuration(first)),
                            assessment.digest(assessment.configuration(second)))


if __name__ == "__main__":
    unittest.main()
