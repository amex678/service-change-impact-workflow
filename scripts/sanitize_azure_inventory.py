#!/usr/bin/env python3
"""Turn Azure CLI or ARM resource JSON into a shareable inventory for matching.

Accepts one or more JSON files, each either an array of resources (for example
``az resource list``, ``az disk list``, ``az functionapp list``) or an ARM list
response (``{"value": [...]}``). Records with the same id are merged so that a
detailed listing can enrich a generic one.

The output keeps only what matching needs: type, kind, location, SKU and the
whitelisted properties in ``config/inventory-properties.json``. Resource ids,
subscription ids, tags and real names are removed. Names and resource groups are
replaced with stable pseudonyms; the mapping back to real names is written only
when ``--name-map`` is given, and should stay out of version control.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

SKU_FIELDS = ("name", "tier", "size", "family", "capacity")


def load_resources(path: str) -> list[dict]:
    with open(path, encoding="utf-8-sig") as handle:
        data = json.load(handle)
    if isinstance(data, dict):
        data = data.get("value", [])
    if not isinstance(data, list):
        raise ValueError(f"{path}: expected a JSON array or an object with 'value'")
    return [item for item in data if isinstance(item, dict)]


def merge_by_id(sources: Iterable[list[dict]]) -> list[dict]:
    merged: dict[str, dict] = {}
    for resources in sources:
        for resource in resources:
            key = (resource.get("id") or "").lower() or f"_noid_{len(merged)}"
            merged[key] = _deep_merge(merged.get(key, {}), resource)
    return list(merged.values())


def _deep_merge(base: dict, extra: dict) -> dict:
    result = dict(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        elif value is not None or key not in result:
            result[key] = value
    return result


def lookup(resource: dict, path: str):
    """Resolve a dotted path under 'properties' first, then at the top level."""
    for root in (resource.get("properties"), resource):
        value = _walk(root, path.split("."))
        if value is not None:
            return value
    return None


def _walk(node, parts: list[str]):
    for index, part in enumerate(parts):
        if node is None:
            return None
        if part.endswith("[]"):
            items = node.get(part[:-2]) if isinstance(node, dict) else None
            if not isinstance(items, list):
                return None
            values = [_walk(item, parts[index + 1:]) for item in items]
            values = [value for value in values if value is not None]
            return sorted(set(map(str, values))) if values else None
        node = node.get(part) if isinstance(node, dict) else None
    return node


def sanitize(resources: list[dict], whitelist: dict, scope_label: str, captured_at: str) -> tuple[dict, dict]:
    ordered = sorted(resources, key=lambda r: ((r.get("type") or "").lower(), (r.get("id") or "").lower()))
    type_counters: dict[str, int] = defaultdict(int)
    group_names: dict[str, str] = {}
    name_map: dict[str, str] = {}
    output = []
    for resource in ordered:
        rtype = (resource.get("type") or "").lower()
        short = rtype.split("/")[-1] or "resource"
        type_counters[short] += 1
        pseudonym = f"{short}-{type_counters[short]:02d}"
        group = (resource.get("resourceGroup") or _group_from_id(resource.get("id")) or "").lower()
        if group and group not in group_names:
            group_names[group] = f"rg-{len(group_names) + 1:02d}"
        name_map[pseudonym] = resource.get("id") or resource.get("name") or ""

        properties = {}
        for path in whitelist.get("common", []) + whitelist.get("types", {}).get(rtype, []):
            value = lookup(resource, path)
            if value is not None:
                properties[path] = value
        sku = resource.get("sku") if isinstance(resource.get("sku"), dict) else None
        output.append({
            "name": pseudonym,
            "resource_group": group_names.get(group),
            "type": rtype,
            "kind": resource.get("kind"),
            "location": resource.get("location"),
            "sku": {field: sku[field] for field in SKU_FIELDS if sku and sku.get(field) is not None} or None,
            "properties": properties,
        })
    inventory = {
        "description": "Sanitized Azure inventory for service-change matching. Real names and ids are removed.",
        "sample": False,
        "scope": scope_label,
        "captured_at": captured_at,
        "resource_count": len(output),
        "resources": output,
    }
    return inventory, {"resources": name_map, "resource_groups": {v: k for k, v in group_names.items()}}


def _group_from_id(resource_id: str | None) -> str | None:
    parts = (resource_id or "").split("/")
    lowered = [part.lower() for part in parts]
    if "resourcegroups" in lowered:
        index = lowered.index("resourcegroups")
        if index + 1 < len(parts):
            return parts[index + 1]
    return None


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("inputs", nargs="+", help="JSON files from az CLI or ARM list calls")
    parser.add_argument("--properties", default="config/inventory-properties.json")
    parser.add_argument("--scope-label", default="one Azure subscription (identifier removed)")
    parser.add_argument("--output", required=True)
    parser.add_argument("--name-map", help="Optional private file mapping pseudonyms back to real ids (keep out of git)")
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    with open(args.properties, encoding="utf-8-sig") as handle:
        whitelist = json.load(handle)
    resources = merge_by_id(load_resources(path) for path in args.inputs)
    captured_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    inventory, name_map = sanitize(resources, whitelist, args.scope_label, captured_at)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(inventory, handle, ensure_ascii=False, indent=2)
    if args.name_map:
        Path(args.name_map).parent.mkdir(parents=True, exist_ok=True)
        with open(args.name_map, "w", encoding="utf-8") as handle:
            json.dump(name_map, handle, ensure_ascii=False, indent=2)
    print(f"Sanitized {inventory['resource_count']} resources -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
