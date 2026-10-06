#!/usr/bin/env python3
"""Pre-match service-change notices against the inventory before the agent runs.

Deterministic and read-only. Produces ``candidates.json`` for the agent and a
Markdown summary for humans. The agent only evaluates the listed candidates;
everything else stays visible with the reason it was not evaluated, so "not
evaluated" is never presented as "no impact".

Ranking (not a verdict): action signal (retirement > pricing/security >
informational), then evidence hints (configuration facts from the inventory that
appear in the notice text), then the nearest deadline.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

SIGNAL_ORDER = {"high": 0, "medium": 1, "low": 2}
TRACKED_TITLE = re.compile(r"\b(Azure|M365) ([A-Za-z0-9._-]+):")
MONTHS = ["january", "february", "march", "april", "may", "june", "july",
          "august", "september", "october", "november", "december"]


def load_json(path: str | None, default=None):
    if not path:
        return default
    file = Path(path)
    if not file.exists():
        return default
    with file.open(encoding="utf-8-sig") as handle:
        return json.load(handle)


# ---------------------------------------------------------------- inventory

def resource_products(resource: dict, product_map: dict) -> list[str]:
    rtype = (resource.get("type") or "").lower()
    kind = (resource.get("kind") or "").lower()
    products: list[str] = []
    for rule in product_map.get("rules", []):
        if rule["type"] != rtype:
            continue
        needle = rule.get("kind_contains")
        if needle and needle.lower() not in kind:
            continue
        for product in rule["products"]:
            if product not in products:
                products.append(product)
    return products


def index_inventory(inventory: dict, product_map: dict) -> tuple[list[dict], dict]:
    ignored = set(product_map.get("ignored_types", {}).get("types", []))
    resources, unmapped, ignored_seen = [], Counter(), Counter()
    for resource in inventory.get("resources", []):
        rtype = (resource.get("type") or "").lower()
        if rtype in ignored:
            ignored_seen[rtype] += 1
            continue
        products = resource_products(resource, product_map)
        if not products:
            unmapped[rtype] += 1
            continue
        resources.append({**resource, "products": products})
    coverage = {
        "resources_total": len(inventory.get("resources", [])),
        "resources_mapped": len(resources),
        "ignored_types": dict(sorted(ignored_seen.items())),
        "unmapped_types": dict(sorted(unmapped.items())),
    }
    return resources, coverage


# ---------------------------------------------------------------- evidence hints

def normalize_text(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"[\u2010-\u2015]", "-", text)
    text = re.sub(r"[^a-z0-9.+#\- ]+", " ", text)
    text = re.sub(r"\.(?=\s|$)", " ", text)
    return " " + re.sub(r"\s+", " ", text).strip() + " "


def normalize_value(value: str) -> str:
    value = value.strip().replace("|", " ").replace("~", "")
    value = re.sub(r"^v(?=\d)", "", value, flags=re.IGNORECASE)
    value = re.sub(r"(?<=\d)\.0$", "", value)
    return normalize_text(value).strip()


def split_camel(segment: str) -> str:
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", segment).lower()


def phrase_in(phrase: str, text: str) -> bool:
    return re.search(r"(?<![a-z0-9])" + re.escape(phrase) + r"s?(?![a-z0-9])", text) is not None


def resource_facts(resource: dict, hints: dict) -> dict[str, int]:
    """Phrases describing the resource configuration, weighted 2 when a value is included."""
    rtype = (resource.get("type") or "").lower()
    aliases = hints.get("property_aliases", {})
    value_aliases = hints.get("value_aliases", {}).get(rtype, {})
    facts: dict[str, int] = {}

    def add(phrase: str, weight: int) -> None:
        phrase = phrase.strip()
        if len(phrase) >= 2:
            facts[phrase] = max(facts.get(phrase, 0), weight)

    for path, raw in (resource.get("properties") or {}).items():
        key = path.split(".")[-1]
        names = aliases.get(path, aliases.get(key, []))
        for value in raw if isinstance(raw, list) else [raw]:
            if value is None or isinstance(value, bool):
                continue
            text = normalize_value(str(value))
            for name in names:
                add(name, 1)
                if text:
                    add(f"{name} {text}", 2)
            if "|" in str(value) and text:
                add(text, 2)
                add(text.split(" ")[0], 1)
            for alias in value_aliases.get(path, {}).get(str(value), []):
                add(alias, 2)
    sku_name = (resource.get("sku") or {}).get("name")
    for alias in value_aliases.get("sku.name", {}).get(str(sku_name), []):
        add(alias, 2)
    for alias in value_aliases.get("kind", {}).get(str(resource.get("kind")), []):
        add(alias, 2)
    return facts


def setting_facts(settings: dict) -> dict[str, int]:
    facts: dict[str, int] = {}
    for key in settings or {}:
        for segment in key.split("."):
            phrase = split_camel(segment).strip()
            if len(phrase) >= 3:
                facts[phrase] = 1
    return facts


def evidence(notice_text: str, facts_by_source: dict[str, dict[str, int]]) -> tuple[int, list[dict]]:
    text = normalize_text(notice_text)
    found: dict[str, dict] = {}
    for source, facts in facts_by_source.items():
        for phrase, weight in facts.items():
            if phrase_in(phrase, text):
                entry = found.setdefault(phrase, {"phrase": phrase, "weight": weight, "from": []})
                entry["from"].append(source)
    score = sum(entry["weight"] for entry in found.values())
    return score, sorted(found.values(), key=lambda entry: (-entry["weight"], entry["phrase"]))


# ---------------------------------------------------------------- signals

def _month_index(value) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lower() in MONTHS:
        return MONTHS.index(value.strip().lower()) + 1
    return None


def retirement_deadline(notice: dict) -> str | None:
    months = []
    for availability in notice.get("availabilities") or []:
        if (availability.get("ring") or "").lower() == "retirement" and isinstance(availability.get("year"), int):
            months.append((availability["year"], _month_index(availability.get("month")) or 12))
    if not months:
        return None
    year, month = min(months)
    return f"{year:04d}-{month:02d}"


def months_until(deadline: str | None, as_of: datetime) -> int | None:
    if not deadline:
        return None
    year, month = (int(part) for part in deadline.split("-")[:2])
    return (year - as_of.year) * 12 + (month - as_of.month)


def azure_signal(notice: dict, as_of: datetime) -> dict:
    tags = {tag.lower() for tag in notice.get("tags") or []}
    deadline = retirement_deadline(notice)
    months = months_until(deadline, as_of)
    if deadline or "retirements" in tags:
        level = "high"
        reason = "retirement date has passed; confirm nothing still depends on it" if (months or 0) < 0 else "retirement"
    elif "pricing & offerings" in tags:
        level, reason = "medium", "pricing or offering change"
    elif tags & {"security", "compliance"}:
        level, reason = "medium", "security or compliance change"
    else:
        level, reason = "low", "informational (feature, preview, region or service update)"
    return {"level": level, "reason": reason, "deadline_hint": deadline, "months_until_deadline": months}


def m365_signal(message: dict, as_of: datetime) -> dict:
    category = (message.get("category") or "").lower()
    deadline = (message.get("actionRequiredByDateTime") or "")[:10] or None
    if deadline or message.get("isMajorChange"):
        level, reason = "high", "action required or major change"
    elif category in {"planforchange", "preventorfixissue"}:
        level, reason = "medium", f"category {message.get('category')}"
    else:
        level, reason = "low", "informational (stay informed)"
    return {"level": level, "reason": reason, "deadline_hint": deadline,
            "months_until_deadline": months_until(deadline[:7], as_of) if deadline else None}


def sort_key(candidate: dict):
    signal = candidate["signal"]
    months = signal.get("months_until_deadline")
    return (SIGNAL_ORDER[signal["level"]], -candidate["evidence_score"],
            months if months is not None else 10_000, candidate["notice"].get("title") or "")


# ---------------------------------------------------------------- tracking

def tracked_keys(existing_issues: list[dict] | None) -> dict[str, dict]:
    tracked: dict[str, dict] = {}
    for issue in existing_issues or []:
        match = TRACKED_TITLE.search(issue.get("title") or "")
        if match:
            key = f"{match.group(1)} {match.group(2)}"
            tracked.setdefault(key, {"issue": issue.get("number"), "state": issue.get("state")})
    return tracked


# ---------------------------------------------------------------- matching

def match_azure(updates: dict, resources: list[dict], product_map: dict, hints: dict, as_of: datetime):
    wide = set(product_map.get("subscription_wide_products", {}).get("products", []))
    facts = {resource["name"]: resource_facts(resource, hints) for resource in resources}
    matched, out_of_scope = [], 0
    for notice in updates.get("items", []):
        products = set(notice.get("products") or [])
        hits = [resource for resource in resources if products & set(resource["products"])]
        signal = azure_signal(notice, as_of)
        if hits:
            scope = "resource"
        elif products & wide and signal["level"] == "high":
            scope = "subscription"
        else:
            out_of_scope += 1
            continue
        score, hints_found = evidence(f"{notice.get('title', '')}\n{notice.get('description_text', '')}",
                                      {r["name"]: facts[r["name"]] for r in hits})
        matched.append({
            "key": f"Azure {notice['id']}",
            "source": "azure",
            "scope": scope,
            "signal": signal,
            "evidence_score": score,
            "evidence_hints": hints_found,
            "matched_products": sorted(products & ({p for r in hits for p in r["products"]} | wide)),
            "matched_resources": [{k: v for k, v in r.items() if k != "products"} for r in hits],
            "notice": notice,
        })
    return matched, out_of_scope


def match_m365(messages: dict | None, profile: dict | None, as_of: datetime):
    if not messages or not profile:
        return [], 0
    in_use = {service.lower() for service in profile.get("services_in_use", [])}
    facts = {"tenant settings": setting_facts(profile.get("settings", {}))}
    matched, out_of_scope = [], 0
    for message in messages.get("messages", []):
        services = [service for service in message.get("services") or [] if service.lower() in in_use]
        if not services:
            out_of_scope += 1
            continue
        score, hints_found = evidence(f"{message.get('title', '')}\n{message.get('body', '')}", facts)
        matched.append({
            "key": f"M365 {message['id']}",
            "source": "m365",
            "scope": "tenant",
            "signal": m365_signal(message, as_of),
            "evidence_score": score,
            "evidence_hints": hints_found,
            "matched_services": services,
            "tenant_settings": profile.get("settings", {}),
            "notice": message,
        })
    return matched, out_of_scope


def build(args: argparse.Namespace, as_of: datetime) -> dict:
    product_map = load_json(args.product_map, {})
    hints = load_json(args.evidence_hints, {})
    updates = load_json(args.azure_updates, {"items": [], "complete": False, "error": "file not found"})
    inventory = load_json(args.azure_inventory, {"resources": []})
    messages = load_json(args.m365_notices) if args.include_m365 else None
    profile = load_json(args.m365_profile) if args.include_m365 else None
    tracked = tracked_keys(load_json(args.existing_issues, []))

    resources, coverage = index_inventory(inventory, product_map)
    azure, azure_out = match_azure(updates, resources, product_map, hints, as_of)
    m365, m365_out = match_m365(messages, profile, as_of)

    candidates, deferred, already = [], [], []
    limits = {"azure": args.max_azure, "m365": args.max_m365}
    taken: Counter = Counter()
    for item in sorted(azure + m365, key=sort_key):
        brief = {"key": item["key"], "title": item["notice"].get("title"), "signal": item["signal"]["level"],
                 "evidence_score": item["evidence_score"]}
        source = item["source"]
        if item["key"] in tracked:
            already.append({**brief, **tracked[item["key"]]})
        elif item["signal"]["level"] == "low":
            deferred.append({**brief, "reason": item["signal"]["reason"]})
        elif taken[source] >= limits[source]:
            deferred.append({**brief, "reason": f"over the per-run limit of {limits[source]} {source} candidates"})
        else:
            candidates.append(item)
            taken[source] += 1

    warnings = []
    if updates.get("error"):
        warnings.append(f"Azure Updates fetch failed: {updates['error']}")
    elif not updates.get("complete"):
        warnings.append("Azure Updates fetch is incomplete; missing notices cannot be treated as no impact.")
    if coverage["unmapped_types"]:
        warnings.append("Some inventory resource types are not mapped to Azure Updates products and were not evaluated.")
    if any(entry["reason"].startswith("over the per-run limit") for entry in deferred):
        warnings.append("Some candidates exceeded the per-run limit and were not evaluated in this run.")
    if inventory.get("sample"):
        warnings.append("The Azure inventory is a synthetic sample, not a real environment.")
    if profile and profile.get("sample"):
        warnings.append("The Microsoft 365 notices and tenant profile are synthetic samples.")

    return {
        "generated_at": as_of.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "inputs": {
            "azure_updates": {"path": args.azure_updates, "count": updates.get("count", len(updates.get("items", []))),
                              "complete": bool(updates.get("complete")), "error": updates.get("error"),
                              "since": updates.get("since"), "windows": updates.get("windows", [])},
            "azure_inventory": {"path": args.azure_inventory, "sample": bool(inventory.get("sample")),
                                "captured_at": inventory.get("captured_at"), "scope": inventory.get("scope")},
            "m365": {"included": bool(messages and profile),
                     "notices_path": args.m365_notices if args.include_m365 else None,
                     "profile_path": args.m365_profile if args.include_m365 else None,
                     "sample": bool(profile and profile.get("sample")),
                     "count": len((messages or {}).get("messages", []))},
            "existing_issues": {"path": args.existing_issues, "tracked": len(tracked)},
        },
        "coverage": coverage,
        "limits": {"max_azure": args.max_azure, "max_m365": args.max_m365},
        "counts": {"candidates": len(candidates), "deferred": len(deferred), "already_tracked": len(already),
                   "out_of_scope": {"azure": azure_out, "m365": m365_out}},
        "warnings": warnings,
        "candidates": candidates,
        "deferred": deferred,
        "already_tracked": already,
    }


def describe_out_of_scope(counts: dict) -> str:
    out = counts["out_of_scope"]
    return f"{out['azure']} Azure, {out['m365']} Microsoft 365"


def summary_markdown(result: dict) -> str:
    counts, inputs = result["counts"], result["inputs"]
    azure = inputs["azure_updates"]
    m365 = inputs["m365"]
    lines = [
        "## Service-change pre-match",
        "",
        f"- Azure Updates: {azure['count']} notices (recent since {azure.get('since')} plus active retirements, "
        f"{'complete' if azure['complete'] else 'INCOMPLETE'})",
        f"- Inventory: {result['coverage']['resources_mapped']} of {result['coverage']['resources_total']} resources "
        f"mapped{' (synthetic sample)' if inputs['azure_inventory']['sample'] else ''}",
        (f"- Microsoft 365: {m365['count']} notices{' (synthetic sample)' if m365['sample'] else ''}"
         if m365["included"] else "- Microsoft 365: not included"),
        f"- For the agent: {counts['candidates']} | deferred: {counts['deferred']} | "
        f"already tracked: {counts['already_tracked']} | out of scope: {describe_out_of_scope(counts)}",
        "",
    ]
    if result["candidates"]:
        lines += ["| Notice | Signal | Evidence hints | Deadline hint | Matched |", "|---|---|---|---|---|"]
        for item in result["candidates"]:
            matched = ", ".join(r.get("name", "?") for r in item.get("matched_resources", [])) or \
                ", ".join(item.get("matched_services", [])) or item["scope"]
            hints = ", ".join(h["phrase"] for h in item["evidence_hints"]) or "-"
            title = (item["notice"].get("title") or "").replace("|", "/")
            lines.append(f"| {item['key']}: {title} | {item['signal']['level']} ({item['signal']['reason']}) | "
                         f"{hints} | {item['signal'].get('deadline_hint') or '-'} | {matched} |")
        lines.append("")
    for warning in result["warnings"]:
        lines.append(f"> [!WARNING]\n> {warning}\n")
    return "\n".join(lines) + "\n"


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--azure-updates", required=True)
    parser.add_argument("--azure-inventory", required=True)
    parser.add_argument("--product-map", default="config/product-map.json")
    parser.add_argument("--evidence-hints", default="config/evidence-hints.json")
    parser.add_argument("--m365-notices")
    parser.add_argument("--m365-profile")
    parser.add_argument("--include-m365", default="true",
                        type=lambda value: str(value).strip().lower() not in {"false", "0", "no"})
    parser.add_argument("--existing-issues")
    parser.add_argument("--max-azure", type=int, default=10, help="Azure candidates evaluated per run")
    parser.add_argument("--max-m365", type=int, default=5, help="Microsoft 365 candidates evaluated per run")
    parser.add_argument("--output", required=True)
    parser.add_argument("--summary", help="Append a Markdown summary to this file (e.g. $GITHUB_STEP_SUMMARY)")
    parser.add_argument("--noop-file", help="Append a noop safe output here when there is nothing to evaluate")
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None, as_of: datetime | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    args = parse_args(argv)
    result = build(args, as_of or datetime.now(timezone.utc))
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    summary = summary_markdown(result)
    if args.summary:
        with open(args.summary, "a", encoding="utf-8") as handle:
            handle.write(summary)
    print(summary)

    healthy = result["inputs"]["azure_updates"]["complete"] and not result["inputs"]["azure_updates"]["error"]
    if args.noop_file and not result["candidates"] and healthy:
        message = (f"No new notices need evaluation: {result['counts']['already_tracked']} already tracked, "
                   f"{result['counts']['deferred']} deferred, out of scope {describe_out_of_scope(result['counts'])}.")
        Path(args.noop_file).parent.mkdir(parents=True, exist_ok=True)
        with open(args.noop_file, "a", encoding="utf-8") as handle:
            handle.write(json.dumps({"type": "noop", "message": message}) + "\n")
        print("noop written: the agent will be skipped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
