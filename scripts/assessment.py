"""Shared evidence guards and revision-aware assessment state."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

VERDICTS = ("Impacted", "Not impacted", "Needs investigation", "Cannot evaluate")
STATE_VERSION = 1
MAX_STATE_AGE = timedelta(days=30)
REVIEWED_REVISIONS = {
    "Azure 557852": "2026-05-21T21:45:32.2389902Z",
    "Azure 551523": "2026-01-30T18:30:02.6205929Z",
    "Azure 560948": "2026-05-05T20:00:13.4947532Z",
    "Azure 498749": "2025-08-20T16:30:32.3883784Z",
    "M365 MC-SAMPLE-001": "2026-09-25T00:00:00Z",
}


def digest(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def configuration(value: object) -> object:
    if isinstance(value, dict):
        return {key: configuration(child) for key, child in value.items()
                if key not in {"captured_at", "description"}}
    if isinstance(value, list):
        return sorted((configuration(child) for child in value), key=lambda child: json.dumps(child, sort_keys=True))
    return value


def policy_digest() -> str:
    root = Path(__file__).resolve().parents[1]
    return digest({
        "workflow": (root / ".github" / "workflows" / "service-change-impact.md").read_text(encoding="utf-8"),
        "guards": Path(__file__).read_text(encoding="utf-8"),
    })


def fingerprint(candidate: dict, inventory: dict, profile: dict | None, product_map: dict,
                hints: dict, policy: str) -> str:
    notice = {key: value for key, value in candidate["notice"].items() if key != "windows"}
    return digest({"notice": notice, "inventory": configuration(inventory),
                   "profile": configuration(profile) if candidate["source"] == "m365" else None,
                   "product_map": product_map, "hints": hints, "policy": policy})


def parse_time(value: str) -> datetime:
    instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if instant.tzinfo is None:
        raise ValueError("Assessment times must include a timezone.")
    return instant.astimezone(timezone.utc)


def load_state(snapshot: dict | None) -> dict:
    if not snapshot or "assessments" not in snapshot:
        return {}
    if snapshot.get("assessment_state_version") != STATE_VERSION:
        raise ValueError("Unsupported assessment state version; do not silently skip notices.")
    state = snapshot["assessments"]
    if not isinstance(state, dict):
        raise ValueError("Assessment state must be an object.")
    for key, record in state.items():
        if not isinstance(record, dict) or record.get("verdict") not in VERDICTS:
            raise ValueError(f"Invalid assessment state for {key}.")
        signature = record.get("fingerprint")
        if not isinstance(signature, str) or len(signature) != 64 or any(c not in "0123456789abcdef" for c in signature):
            raise ValueError(f"Invalid assessment fingerprint for {key}.")
        parse_time(record["assessed_at"])
    return state


def unchanged(candidate: dict, record: dict | None, tracked: bool, as_of: datetime) -> bool:
    if not record or record["fingerprint"] != candidate["assessment_fingerprint"]:
        return False
    age = as_of - parse_time(record["assessed_at"])
    if not timedelta(0) <= age < MAX_STATE_AGE or record["verdict"] == "Cannot evaluate":
        return False
    # An uncreated finding must not disappear just because it was evaluated.
    return record["verdict"] == "Not impacted" or tracked


def observation(context: dict, key: str) -> object:
    record = context.get("observations", {}).get(key)
    if isinstance(record, dict) and record.get("source"):
        return record.get("value")
    return None


def evidence_guard(candidate: dict) -> tuple[set[str], str] | None:
    key = candidate["key"]
    if key not in REVIEWED_REVISIONS:
        return None
    notice = candidate["notice"]
    revision = notice.get("modified") if candidate["source"] == "azure" else notice.get("lastModifiedDateTime")
    uncertain = {"Needs investigation", "Cannot evaluate"}
    if revision != REVIEWED_REVISIONS[key]:
        return uncertain, "This notice revision is not covered by the reviewed evidence guard."
    context = candidate.get("assessment_context", {})
    if key == "M365 MC-SAMPLE-001":
        record = candidate.get("tenant_settings", {}).get("entra.authenticationMethods.sms.isUsableForSignIn")
        value = record.get("value") if isinstance(record, dict) and record.get("source") else None
        if not isinstance(value, bool):
            return uncertain, "SMS authentication enablement does not capture primary sign-in usability."
        return uncertain | {"Impacted" if value else "Not impacted"}, "Captured SMS primary sign-in flag."
    if key == "Azure 498749":
        cloud = context.get("cloud")
        if cloud not in {"AzureCloud", "AzureChinaCloud", "AzureUSGovernment"}:
            return uncertain, "The subscription cloud was not explicitly captured."
        if cloud != "AzureChinaCloud":
            return uncertain | {"Not impacted"}, "The captured cloud excludes this 21Vianet-only notice."
        return uncertain, "China cloud matches the scope, but Defender feature usage still requires evidence."
    if key == "Azure 560948":
        reservations = context.get("reservations")
        if not isinstance(reservations, dict) or reservations.get("complete") is not True:
            return uncertain, "Current VM size is not complete reservation-order evidence."
        return set(VERDICTS), "Reservation orders were captured; the reviewer must compare their series and terms."
    if key == "Azure 551523":
        value = observation(context, "azureMonitor.vmClientPreviewExport.enabled")
        if not isinstance(value, bool):
            return uncertain, "The specific VM-client preview export configuration was not captured."
        return uncertain | {"Impacted" if value else "Not impacted"}, "Captured preview export usage."
    sites = [r for r in candidate.get("matched_resources", []) if r.get("type", "").lower() == "microsoft.web/sites"]
    if not sites or any(r.get("properties", {}).get("siteConfig.minTlsVersion") not in {"1.2", "1.3"}
                        or r.get("properties", {}).get("siteConfig.scmMinTlsVersion") not in {"1.2", "1.3"}
                        for r in sites):
        return uncertain, "Main-site and independent SCM TLS configuration are not both verified as TLS 1.2+."
    if observation(context, "functionApp.clients.supportTls12") is not True:
        return uncertain, "Client TLS 1.2+ compatibility was not captured."
    return uncertain | {"Not impacted"}, "Both endpoint minima and captured clients exclude legacy TLS."


def check_verdict(candidate: dict, verdict: str) -> None:
    guard = evidence_guard(candidate)
    if guard and verdict not in guard[0]:
        raise ValueError(f"Unsupported {verdict} verdict for {candidate['key']}: {guard[1]}")


def captured_scope(candidate: dict) -> str | None:
    resources = candidate.get("matched_resources", [])
    if not resources:
        return None
    values = []
    for resource in resources:
        name = resource["name"]
        if resource.get("type", "").lower() == "microsoft.compute/disks":
            properties = resource.get("properties", {})
            os_type = properties.get("osType")
            role = f"OS type captured: {os_type}" if os_type else "OS/data role not captured"
            sku = (resource.get("sku") or {}).get("name", "not captured")
            values.append(f"`{name}` (SKU {sku}; {role})")
        else:
            values.append(f"`{name}`")
    return "; ".join(values) + " (pre-matched inventory, not all confirmed affected)"
