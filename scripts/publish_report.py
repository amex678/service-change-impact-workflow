#!/usr/bin/env python3
"""Validate all verdicts, render the report and stage its required artifacts."""

from __future__ import annotations

import argparse
import copy
import html
import json
import re
import shutil
import sys
from collections import Counter
from pathlib import Path
from string import Template
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
VERDICTS = ("Impacted", "Not impacted", "Needs investigation", "Cannot evaluate")
FILES = {"impact-report.md", "index.html", "candidates.json"}
KEY = re.compile(r"\b(Azure|M365) ([A-Za-z0-9._-]+)(?=:|\]|$)")
HEADERS = ("Notice", "Change and effective date", "Matched resources or settings / checked scope",
           "Deciding evidence", "Verdict", "Next step")
SAMPLE_URL = ("https://github.com/amex678/service-change-impact-workflow/blob/main/"
              "data/samples/m365-message-center.sample.json")


def split_row(line: str) -> list[str]:
    return [cell.strip().replace(r"\|", "|") for cell in re.split(r"(?<!\\)\|", line.strip().strip("|"))]


def cell(value: str) -> str:
    return value.replace("|", r"\|").replace("\n", " ")


def sections(markdown: str) -> tuple[str, str]:
    parts = re.split(r"(?m)^## 2\. Verdicts\s*$", markdown)
    if len(parts) != 2:
        raise ValueError("Report must have exactly one '## 2. Verdicts' section.")
    parts = re.split(r"(?m)^## 3\. Details[^\n]*$", parts[1], maxsplit=1)
    if len(parts) != 2:
        raise ValueError("Report must have a '## 3. Details' section.")
    details = re.split(r"(?m)^## 4\.[^\n]*$", parts[1], maxsplit=1)[0].strip()
    return parts[0], details


def require_samples(candidates: dict) -> None:
    inputs = candidates["inputs"]
    if not inputs["azure_inventory"].get("sample"):
        raise ValueError("Public report requires a synthetic Azure inventory.")
    m365 = inputs["m365"]
    if m365["included"] and not (m365.get("notices_sample") and m365.get("profile_sample")):
        raise ValueError("Public report requires synthetic Microsoft 365 notices and profile.")


def validate_report(candidates: dict, markdown: str, public_output: bool = False) -> list[list[str]]:
    if public_output:
        require_samples(candidates)
    expected = [item["key"] for item in candidates["candidates"]]
    if len(set(expected)) != len(expected) or candidates["counts"]["candidates"] != len(expected):
        raise ValueError("Candidate snapshot has duplicate keys or an inconsistent candidate count.")
    if re.search(r"\\n(?:\\n)?(?=\*\*|##|- \[)", markdown):
        raise ValueError("Report contains literal newline escapes instead of Markdown line breaks.")
    table, details = sections(markdown)
    rows: list[list[str]] = []
    for line in table.splitlines():
        if not line.strip().startswith("|"):
            continue
        values = split_row(line)
        if values[0] == "Notice" or all(re.fullmatch(r":?-{3,}:?", value) for value in values):
            continue
        if len(values) != 6 or any(not value for value in values):
            raise ValueError("Each verdict row must have six nonempty columns.")
        match = KEY.search(values[0])
        if not match:
            raise ValueError(f"Verdict row is missing an exact candidate key: {values[0]}")
        key = f"{match[1]} {match[2]}"
        values[4] = values[4].strip("*_` ")
        if values[4] not in VERDICTS:
            raise ValueError(f"Invalid verdict for {key}: {values[4]}")
        values[0] = key
        rows.append(values)
    actual = [row[0] for row in rows]
    if len(set(actual)) != len(actual):
        raise ValueError("Report has duplicate candidate verdicts.")
    if set(actual) != set(expected):
        raise ValueError(f"Verdict coverage mismatch; missing={sorted(set(expected) - set(actual))}; "
                         f"unexpected={sorted(set(actual) - set(expected))}.")
    detail_keys = [f"{source} {notice_id}" for source, notice_id in
                   re.findall(r"(?m)^###\s+(Azure|M365)\s+([A-Za-z0-9._-]+)", details)]
    if len(set(detail_keys)) != len(detail_keys) or set(detail_keys) - set(expected):
        raise ValueError("Detail headings have duplicate or unexpected candidate keys.")
    for row in rows:
        if row[4] in {"Impacted", "Needs investigation"} and row[0] not in detail_keys:
            raise ValueError(f"Missing deciding evidence detail section for {row[0]}.")
        if row[0].startswith("Azure ") and not candidates["inputs"]["azure_updates"]["complete"]:
            if row[4] != "Cannot evaluate":
                raise ValueError(f"Incomplete Azure fetch cannot support the {row[4]} verdict for {row[0]}.")
    return rows


def notice_url(candidate: dict, sample_m365: bool = False) -> str | None:
    if candidate["source"] == "m365":
        url = candidate["notice"].get("url") or candidate["notice"].get("webLink")
        return url or (SAMPLE_URL if sample_m365 else None)
    url = candidate["notice"]["url"]
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "azure.microsoft.com":
        raise ValueError(f"Invalid Azure source URL for {candidate['key']}.")
    if parse_qs(parsed.query).get("id") != [candidate["notice"]["id"]]:
        raise ValueError(f"Azure source URL does not identify {candidate['key']}.")
    return url


def canonical_report(candidates: dict, draft: str, run_url: str | None = None,
                     public_output: bool = False) -> str:
    rows = validate_report(candidates, draft, public_output)
    _, details = sections(draft)
    inputs, counts = candidates["inputs"], candidates["counts"]
    azure, inventory, m365 = inputs["azure_updates"], inputs["azure_inventory"], inputs["m365"]
    sample = inventory.get("sample") or m365.get("sample")
    lines = [
        "# Service-change impact report", "",
        "> SYNTHETIC SAMPLE inputs are explicitly marked below; do not treat them as real-environment evidence."
        if sample else "> Sanitized configuration snapshot; verdicts remain proposals for human review.",
        "> AI-assisted evidence review is not human approval. Nothing was merged or deployed.", "",
        "## 1. Scope and completeness", "",
        "| Item | Value |", "|---|---|",
        f"| Input snapshot | {cell(candidates['generated_at'])} |",
        f"| Run | {cell(run_url or 'Reviewed local replay; not a workflow or live-environment test')} |",
        f"| Azure Updates | {azure['count']} notices; {'complete' if azure['complete'] else 'INCOMPLETE'}; "
        f"recent since {cell(str(azure.get('since')))} plus active retirements |",
        f"| Azure inventory | {cell(str(inventory.get('scope')))}; captured {cell(str(inventory.get('captured_at')))}; "
        f"{candidates['coverage']['resources_mapped']}/{candidates['coverage']['resources_total']} resources mapped; "
        f"{'SYNTHETIC SAMPLE' if inventory.get('sample') else 'sanitized export'} |",
        f"| Microsoft 365 | {'included' if m365['included'] else 'not included'}; {m365['count']} notices; "
        f"notices={'sample' if m365.get('notices_sample') else 'not sample'}; "
        f"profile={'sample' if m365.get('profile_sample') else 'not sample'}; "
        f"profile captured {cell(str(m365.get('captured_at') or 'not captured'))} |",
        f"| Evaluated | {len(rows)}/{counts['candidates']} candidates |",
        f"| Deferred / already tracked | {counts['deferred']} / {counts['already_tracked']} |",
        f"| Out of matching scope | {counts['out_of_scope']['azure']} Azure; "
        f"{counts['out_of_scope']['m365']} Microsoft 365 (not evaluated, not 'not impacted') |", "",
    ]
    for warning in candidates["warnings"]:
        lines += [f"> Warning: {cell(warning)}", ""]
    lines += ["## 2. Verdicts", "", "| " + " | ".join(HEADERS) + " |", "|---|---|---|---|---|---|"]
    by_key = {candidate["key"]: candidate for candidate in candidates["candidates"]}
    for values in rows:
        candidate = by_key[values[0]]
        title = f"{candidate['key']}: {candidate['notice']['title']}"
        url = notice_url(candidate, m365.get("notices_sample", False))
        values[0] = f"[{title}]({url})" if url else title
        lines.append("| " + " | ".join(cell(value) for value in values) + " |")
    lines += ["", "## 3. Details for Impacted and Needs investigation", "", details, "",
              "## 4. Not evaluated in this run", "", "| Notice | Reason |", "|---|---|"]
    not_evaluated = candidates["deferred"] + candidates["already_tracked"]
    for item in not_evaluated:
        reason = item.get("reason") or f"Already tracked in Issue {item['issue']} ({item.get('state', 'unknown state')})"
        lines.append(f"| {cell(item['key'] + ': ' + item['title'])} | {cell(reason)} |")
    if not not_evaluated:
        lines.append("| None | Every selected candidate was evaluated |")
    lines += ["", "## 5. Coverage gaps", ""]
    for label, key in (("Unmapped resource types", "unmapped_types"), ("Ignored resource types", "ignored_types")):
        entries = candidates["coverage"][key]
        lines.append(f"- {label}: " + (", ".join(f"{name} ({count})" for name, count in entries.items()) or "none"))
    lines += ["", "## 6. Reviewer checklist", "",
              "- [x] Every selected candidate has exactly one valid verdict and deciding evidence (automated validation).",
              "- [ ] A human owner accepts or corrects the evidence and the stated scope.",
              "- [ ] Missing usage, cloud, client or policy settings have been obtained where needed.",
              "- [ ] Owners and dates are assigned to findings before action.",
              "- [ ] Any draft pull request passes checks and receives human approval before deployment.", ""]
    return "\n".join(lines)


def inline_markdown(text: str) -> str:
    tokens = re.compile(r"`([^`]+)`|\[((?:[^\[\]\n]|\[[^\[\]\n]*\])+)\]\(([^)\s]+)\)|\*\*([^*]+)\*\*")
    pieces: list[str] = []
    end = 0
    for match in tokens.finditer(text):
        pieces.append(html.escape(text[end:match.start()]))
        if match[1] is not None:
            pieces.append(f"<code>{html.escape(match[1])}</code>")
        elif match[2] is not None:
            parsed = urlparse(match[3])
            if parsed.scheme != "https" or parsed.hostname not in {
                "azure.microsoft.com", "learn.microsoft.com", "www.microsoft.com",
                "github.com", "github.github.com", "amex678.github.io", "admin.microsoft.com",
            } or parsed.username or parsed.password:
                raise ValueError(f"Unsafe or unsupported report link: {match[3]}")
            pieces.append(f'<a href="{html.escape(match[3], quote=True)}">{html.escape(match[2])}</a>')
        else:
            pieces.append(f"<strong>{html.escape(match[4])}</strong>")
        end = match.end()
    pieces.append(html.escape(text[end:]))
    return "".join(pieces)


def markdown_html(markdown: str) -> str:
    lines, output = markdown.splitlines(), []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip() or line == "# Service-change impact report":
            index += 1
            continue
        if line.startswith("|"):
            table: list[list[str]] = []
            while index < len(lines) and lines[index].startswith("|"):
                values = split_row(lines[index])
                if not all(re.fullmatch(r":?-{3,}:?", value) for value in values):
                    table.append(values)
                index += 1
            output.append('<div class="table-wrap" tabindex="0"><table>')
            for row_index, values in enumerate(table):
                verdict = values[4] if len(values) == 6 and values[4] in VERDICTS else None
                attr = f' data-verdict="{verdict}"' if verdict else ""
                output.append(f"<tr{attr}>")
                tag = "th" if row_index == 0 else "td"
                for col_index, value in enumerate(values):
                    content = inline_markdown(value)
                    if verdict and col_index == 4:
                        content = f'<span class="badge {verdict.lower().replace(" ", "-")}">{content}</span>'
                    output.append(f"<{tag}>{content}</{tag}>")
                output.append("</tr>")
            output.append("</table></div>")
            continue
        heading = re.match(r"^(#{2,3}) (.+)$", line)
        if heading:
            level = len(heading[1])
            output.append(f"<h{level}>{inline_markdown(heading[2])}</h{level}>")
        elif line.startswith("> "):
            output.append(f'<p class="notice">{inline_markdown(line[2:])}</p>')
        elif line.startswith("- "):
            items = []
            while index < len(lines) and lines[index].startswith("- "):
                items.append(f"<li>{inline_markdown(lines[index][2:])}</li>")
                index += 1
            output.append("<ul>" + "".join(items) + "</ul>")
            continue
        else:
            output.append(f"<p>{inline_markdown(line)}</p>")
        index += 1
    return "\n".join(output)


def render_html(candidates: dict, markdown: str) -> str:
    rows = validate_report(candidates, markdown)
    counts = Counter(row[4] for row in rows)
    badges = "".join(f'<div class="stat"><strong>{counts[verdict]}</strong>'
                     f'<span>{verdict}</span></div>' for verdict in VERDICTS)
    template = Template((ROOT / "templates" / "impact-report.html").read_text(encoding="utf-8"))
    m365 = candidates["inputs"]["m365"]
    samples = candidates["inputs"]["azure_inventory"].get("sample") and (
        not m365["included"] or (m365.get("notices_sample") and m365.get("profile_sample")))
    boundary = ("Synthetic Azure inventory and, when included, fictional Microsoft 365 inputs only. "
                "Public Azure notices link to their original sources." if samples else
                "Sanitized inputs: keep this report private unless sharing is explicitly approved. "
                "Any synthetic inputs are marked in the scope table.")
    return template.substitute(content=markdown_html(markdown), counts=badges,
                               evaluated=len(rows), captured=html.escape(candidates["generated_at"]),
                               data_boundary=html.escape(boundary))


def snapshot(candidates: dict, run_url: str | None) -> dict:
    result = copy.deepcopy(candidates)
    result["report_run_url"] = run_url
    for values in result["inputs"].values():
        if isinstance(values, dict):
            for key in ("path", "notices_path", "profile_path"):
                values.pop(key, None)
    for candidate in result["candidates"]:
        for key in ("description_text", "body", "links"):
            candidate["notice"].pop(key, None)
    return result


def safe_directory(directory: Path) -> None:
    if any(path.is_symlink() for path in (directory, *directory.parents)):
        raise ValueError(f"Report directories must not be symlinks: {directory}")
    directory.mkdir(parents=True, exist_ok=True)
    if any(path.name not in FILES or not path.is_file() or path.is_symlink() for path in directory.iterdir()):
        raise ValueError(f"Unexpected files in report directory: {directory}")


def publish(candidates: dict, draft: str, output: Path, stage: Path | None = None,
            run_url: str | None = None, public_output: bool = False) -> int:
    run_url = run_url or candidates.get("report_run_url")
    data = snapshot(candidates, run_url)
    markdown = canonical_report(data, draft, run_url, public_output)
    rendered = render_html(data, markdown)
    payloads = {"impact-report.md": markdown, "index.html": rendered,
                "candidates.json": json.dumps(data, ensure_ascii=False, indent=2) + "\n"}
    safe_directory(output)
    if stage:
        safe_directory(stage)
    for name, value in payloads.items():
        (output / name).write_text(value, encoding="utf-8")
        if stage:
            shutil.copyfile(output / name, stage / name)
    return len(validate_report(data, markdown, public_output))


def verify(directory: Path, public_output: bool = False) -> int:
    if not directory.is_dir() or {path.name for path in directory.iterdir()} != FILES:
        raise ValueError("Delivered artifact must contain exactly Markdown, HTML and candidate metadata.")
    if any(path.is_symlink() or not path.is_file() for path in directory.iterdir()):
        raise ValueError("Delivered report files must be regular files.")
    candidates = json.loads((directory / "candidates.json").read_text(encoding="utf-8"))
    markdown = (directory / "impact-report.md").read_text(encoding="utf-8")
    expected = canonical_report(candidates, markdown, candidates.get("report_run_url"), public_output)
    if markdown != expected or (directory / "index.html").read_text(encoding="utf-8") != render_html(candidates, expected):
        raise ValueError("Delivered Markdown or HTML does not match the validated candidate report.")
    return len(validate_report(candidates, markdown, public_output))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates")
    parser.add_argument("--report")
    parser.add_argument("--output-dir")
    parser.add_argument("--stage-dir")
    parser.add_argument("--run-url")
    parser.add_argument("--public-output", action="store_true")
    parser.add_argument("--verify-directory")
    args = parser.parse_args()
    try:
        if args.verify_directory:
            count = verify(Path(args.verify_directory), args.public_output)
            print(f"Delivered report verified: {count}/{count} candidate verdicts.")
        else:
            if not (args.candidates and args.report and args.output_dir):
                parser.error("--candidates, --report and --output-dir are required for publication")
            if Path(args.report).is_symlink() or Path(args.candidates).is_symlink():
                raise ValueError("Report inputs must not be symlinks.")
            candidates = json.loads(Path(args.candidates).read_text(encoding="utf-8"))
            count = publish(candidates, Path(args.report).read_text(encoding="utf-8"), Path(args.output_dir),
                            Path(args.stage_dir) if args.stage_dir else None, args.run_url, args.public_output)
            print(f"Report published: {count}/{count} candidate verdicts; Markdown, HTML and metadata.")
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Report publication failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
