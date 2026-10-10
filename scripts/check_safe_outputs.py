#!/usr/bin/env python3
"""Reject duplicate or unsupported finding/PR requests before writes happen."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import publish_report

NOTICE_KEY = re.compile(r"\b(Azure|M365) ([A-Za-z0-9._-]+):")


def validate(candidates: dict, markdown: str, outputs: dict) -> int:
    rows = publish_report.validate_report(candidates, markdown)
    verdicts = {row[0]: row[4] for row in rows}
    by_key = {candidate["key"]: candidate for candidate in candidates["candidates"]}
    items = outputs.get("items")
    if not isinstance(items, list):
        raise ValueError("Safe outputs must contain a typed items list.")
    checked = 0
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Safe-output items must be objects.")
        operation = item.get("type")
        if operation not in {"create_issue", "create_pull_request"}:
            continue
        match = NOTICE_KEY.search(item.get("title") or "")
        if not match:
            raise ValueError(f"{operation} does not name a selected candidate key.")
        key = f"{match[1]} {match[2]}"
        candidate = by_key.get(key)
        if candidate is None:
            raise ValueError(f"{operation} names an unselected candidate: {key}.")
        if candidate.get("tracking_issue"):
            raise ValueError(f"Duplicate {operation} for {key}: the existing finding must receive a comment.")
        if operation == "create_pull_request":
            if candidate.get("tracking_pull_request"):
                raise ValueError(f"Duplicate remediation PR for {key}: an open PR already exists.")
            if candidate["source"] != "azure" or verdicts[key] != "Impacted":
                raise ValueError(f"Unsupported remediation PR for {key}: only an Impacted Azure candidate qualifies.")
        elif verdicts[key] not in {"Impacted", "Needs investigation"}:
            raise ValueError(f"Unsupported finding Issue for {key}: {verdicts[key]}.")
        checked += 1
    return checked


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--outputs", required=True)
    args = parser.parse_args()
    try:
        candidates = json.loads(Path(args.candidates).read_text(encoding="utf-8"))
        outputs = json.loads(Path(args.outputs).read_text(encoding="utf-8"))
        count = validate(candidates, Path(args.report).read_text(encoding="utf-8"), outputs)
        print(f"Safe-output creation requests verified: {count}; no duplicate finding or remediation PR allowed.")
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Safe-output validation failed before writes: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
