#!/usr/bin/env python3
"""Restore revision state from the last successfully verified report artifact."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import assessment


def gh_json(*args: str) -> object:
    result = subprocess.run(["gh", *args], check=True, capture_output=True, text=True, encoding="utf-8")
    return json.loads(result.stdout)


def restore(repository: str, current_run: str, output: Path) -> bool:
    runs = gh_json("run", "list", "--repo", repository, "--workflow", "service-change-impact.lock.yml",
                   "--status", "success", "--limit", "10", "--json", "databaseId,conclusion,status,headBranch")
    for run in runs:
        if str(run["databaseId"]) == current_run or run["headBranch"] != "main":
            continue
        run_id = str(run["databaseId"])
        artifacts = gh_json("api", f"repos/{repository}/actions/runs/{run_id}/artifacts")["artifacts"]
        report = next((artifact for artifact in artifacts if artifact["name"] == "report"), None)
        if not report or report["expired"]:
            print(f"Previous run {run_id} has no retained report; checking earlier successful runs.", file=sys.stderr)
            continue
        directory = output.parent / f"previous-report-{run_id}"
        subprocess.run(["gh", "run", "download", run_id, "--repo", repository, "--name", "report",
                        "--dir", str(directory)], check=True)
        metadata = directory / "run" / "report" / "candidates.json"
        snapshot = json.loads(metadata.read_text(encoding="utf-8"))
        state = assessment.load_state(snapshot)
        if not state:
            print(f"Previous run {run_id} predates revision state; tracked notices will be re-evaluated.", file=sys.stderr)
            return False
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Restored {len(state)} assessment revisions from verified run {run_id}.")
        return True
    print("No retained verified assessment state; candidates will be re-evaluated.", file=sys.stderr)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--current-run", default=os.environ.get("GITHUB_RUN_ID", ""))
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if not args.repo:
        parser.error("--repo or GITHUB_REPOSITORY is required")
    try:
        restore(args.repo, args.current_run, Path(args.output))
    except (subprocess.CalledProcessError, OSError, ValueError, KeyError, TypeError) as error:
        print(f"Assessment state retrieval failed: {error}", file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
