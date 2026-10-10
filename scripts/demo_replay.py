#!/usr/bin/env python3
"""Replay the frozen sample inputs and reviewed verdicts offline, without AI."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import prepare_candidates
import publish_report

ROOT = Path(__file__).resolve().parents[1]
AS_OF = datetime(2026, 10, 10, tzinfo=timezone.utc)


def replay(output: Path, previous: Path | None = None) -> int:
    output.mkdir(parents=True, exist_ok=True)
    samples = ROOT / "data" / "samples"
    reference = json.loads((ROOT / "docs" / "reports" / "review-candidates.json").read_text(encoding="utf-8"))
    published_findings = {"Azure 551523": 10, "Azure 560948": 11, "Azure 498749": 12, "Azure 557852": 13}
    issues = []
    for item in reference["candidates"]:
        tracking = item.get("tracking_issue")
        number = tracking["issue"] if tracking else published_findings.get(item["key"])
        if number:
            issues.append({"number": number, "title": f"[service-change] {item['key']}: frozen reference",
                           "state": tracking["state"] if tracking else "OPEN"})
    issues_path = output / "reference-issues.json"
    issues_path.write_text(json.dumps(issues), encoding="utf-8")
    arguments = [
        "--azure-updates", str(samples / "azure-updates.reference.json"),
        "--azure-inventory", str(samples / "azure-inventory.sample.json"),
        "--m365-notices", str(samples / "m365-message-center.sample.json"),
        "--m365-profile", str(samples / "m365-tenant-profile.sample.json"),
        "--product-map", str(ROOT / "config" / "product-map.json"),
        "--evidence-hints", str(ROOT / "config" / "evidence-hints.json"),
        "--existing-issues", str(issues_path), "--output", str(output / "candidates.json"),
        "--noop-file", str(output / "noop.jsonl"), "--public-output",
    ]
    if previous:
        arguments += ["--previous-report", str(previous)]
    if prepare_candidates.main(arguments, as_of=AS_OF) != 0:
        raise ValueError("Frozen reference preparation failed; no successful replay was produced.")
    candidates = json.loads((output / "candidates.json").read_text(encoding="utf-8"))
    draft = (ROOT / "docs" / "reports" / "impact-report.md").read_text(encoding="utf-8") if candidates["candidates"] else \
        publish_report.noop_report(candidates)
    count = publish_report.publish(candidates, draft, output / "report", public_output=True)
    publish_report.verify(output / "report", public_output=True)
    print(f"FROZEN OFFLINE REPLAY: {count} verdicts; no API fetch, AI inference or GitHub/Azure/M365 write.")
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--previous-report")
    args = parser.parse_args()
    try:
        replay(Path(args.output_dir), Path(args.previous_report) if args.previous_report else None)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Frozen demo replay failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
