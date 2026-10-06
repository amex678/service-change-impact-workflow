#!/usr/bin/env python3
"""Fetch Azure Updates from the public Microsoft Release Communications API.

Read-only and unauthenticated. Two windows are merged:

* recent: notices modified within ``--lookback-days``
* active retirements: retirement notices whose retirement month is in the future
  or within ``--retirement-grace-months`` in the past, even if they were
  published long ago (a feature still in use after its retirement date is the
  most urgent case)

The API omits ``@odata.nextLink`` when ``$top`` is supplied, so pages are read
explicitly with ``$skip``. Items can shift between pages while paging, so the
result is de-duplicated by id and marked incomplete when fewer unique items than
the reported count were retrieved. Never treat an incomplete fetch as "no impact".
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from typing import Callable, Iterable

API_URL = "https://www.microsoft.com/releasecommunications/api/v2/azure"
UPDATE_URL = "https://azure.microsoft.com/updates?id={id}"
PAGE_SIZE = 100
DEFAULT_MAX_PAGES = 30
USER_AGENT = "service-change-impact-workflow/0.1"

JsonFetcher = Callable[[str], dict]


class _TextExtractor(HTMLParser):
    """Convert notice HTML to plain text and collect outbound links."""

    _BLOCK_TAGS = {"p", "br", "li", "div", "tr", "h1", "h2", "h3", "h4", "ul", "ol"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._BLOCK_TAGS:
            self.parts.append("\n")
        if tag == "li":
            self.parts.append("- ")
        if tag == "a":
            href = dict(attrs).get("href")
            if href and href.startswith("http") and href not in self.links:
                self.links.append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def html_to_text(html: str | None) -> tuple[str, list[str]]:
    """Return (plain text, links) for a notice description."""
    if not html:
        return "", []
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    lines = [" ".join(line.split()) for line in "".join(parser.parts).splitlines()]
    text = "\n".join(line for line in lines if line)
    return text, parser.links


def build_url(filter_expr: str, skip: int, top: int = PAGE_SIZE) -> str:
    params = {
        "$filter": filter_expr,
        "$orderby": "modified desc,id asc",
        "$count": "true",
        "$top": str(top),
        "$skip": str(skip),
    }
    return API_URL + "?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote, safe="$,'()/:")


def http_get_json(url: str, timeout: int = 60) -> dict:
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed https endpoint
        return json.load(response)


def fetch_all(filter_expr: str, fetcher: JsonFetcher = http_get_json, max_pages: int = DEFAULT_MAX_PAGES) -> dict:
    """Page through one filter and report whether every reported item was retrieved."""
    items: dict[str, dict] = {}
    total: int | None = None
    pages = 0
    duplicates = 0
    skip = 0
    while pages < max_pages:
        page = fetcher(build_url(filter_expr, skip))
        pages += 1
        if total is None and page.get("@odata.count") is not None:
            total = int(page["@odata.count"])
        values = page.get("value") or []
        for value in values:
            key = str(value.get("id"))
            if key in items:
                duplicates += 1
            items[key] = value
        skip += PAGE_SIZE
        if not values or (total is not None and skip >= total):
            break
    complete = total is not None and len(items) >= total
    return {
        "filter": filter_expr,
        "reported_total": total,
        "unique_items": len(items),
        "pages": pages,
        "duplicates_dropped": duplicates,
        "complete": complete,
        "items": list(items.values()),
    }


def normalize(item: dict) -> dict:
    text, links = html_to_text(item.get("description"))
    notice_id = str(item.get("id"))
    return {
        "id": notice_id,
        "title": (item.get("title") or "").strip(),
        "url": UPDATE_URL.format(id=urllib.parse.quote(notice_id)),
        "products": item.get("products") or [],
        "product_categories": item.get("productCategories") or [],
        "tags": item.get("tags") or [],
        "status": item.get("status"),
        "created": item.get("created"),
        "modified": item.get("modified"),
        "general_availability": item.get("generalAvailabilityDate"),
        "preview_availability": item.get("previewAvailabilityDate"),
        "availabilities": item.get("availabilities") or [],
        "description_text": text,
        "links": links,
    }


_MONTHS = {name: index for index, name in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], start=1)}


def _month_number(month: object) -> int | None:
    if isinstance(month, int):
        return month
    if isinstance(month, str):
        return _MONTHS.get(month.strip().lower())
    return None


def months_back(as_of: datetime, months: int) -> tuple[int, int]:
    """(year, month) that lies ``months`` calendar months before ``as_of``."""
    index = as_of.year * 12 + (as_of.month - 1) - months
    return index // 12, index % 12 + 1


def retirement_is_active(item: dict, as_of: datetime, grace_months: int = 0) -> bool:
    """True when a retirement month is not earlier than ``grace_months`` before ``as_of``."""
    earliest = months_back(as_of, grace_months)
    for availability in item.get("availabilities") or []:
        if (availability.get("ring") or "").lower() != "retirement":
            continue
        year = availability.get("year")
        month = _month_number(availability.get("month"))
        if isinstance(year, int) and (year, month or 12) >= earliest:
            return True
    return False


def collect(lookback_days: int, include_retirements: bool, as_of: datetime,
            fetcher: JsonFetcher = http_get_json, max_pages: int = DEFAULT_MAX_PAGES,
            grace_months: int = 3) -> dict:
    since = (as_of - timedelta(days=lookback_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    windows = [("recent", f"modified ge {since}")]
    if include_retirements:
        first_year = months_back(as_of, grace_months)[0]
        windows.append(("active-retirement",
                        f"availabilities/any(a: a/ring eq 'Retirement' and a/year ge {first_year})"))

    merged: dict[str, dict] = {}
    reports = []
    for name, filter_expr in windows:
        result = fetch_all(filter_expr, fetcher=fetcher, max_pages=max_pages)
        kept = 0
        for raw in result.pop("items"):
            if name == "active-retirement" and not retirement_is_active(raw, as_of, grace_months):
                continue
            notice = merged.setdefault(str(raw.get("id")), {**normalize(raw), "windows": []})
            notice["windows"].append(name)
            kept += 1
        reports.append({"window": name, **result, "kept": kept})

    return {
        "source": API_URL,
        "fetched_at": as_of.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lookback_days": lookback_days,
        "retirement_grace_months": grace_months if include_retirements else None,
        "since": since,
        "complete": all(report["complete"] for report in reports),
        "windows": reports,
        "count": len(merged),
        "items": sorted(merged.values(), key=lambda n: (n.get("modified") or ""), reverse=True),
    }


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lookback-days", default="14",
                        help="Days of recently modified notices to include (default 14; empty means 14)")
    parser.add_argument("--include-active-retirements", action="store_true",
                        help="Also include retirement notices whose retirement month has not passed")
    parser.add_argument("--retirement-grace-months", type=int, default=3,
                        help="Keep retirements that passed within this many months (default 3)")
    parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES)
    parser.add_argument("--output", required=True, help="Path of the JSON file to write")
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    args = parse_args(argv)
    lookback = int(args.lookback_days) if str(args.lookback_days).strip() else 14
    if not 1 <= lookback <= 365:
        print("--lookback-days must be between 1 and 365", file=sys.stderr)
        return 2
    try:
        result = collect(lookback, args.include_active_retirements, datetime.now(timezone.utc),
                         max_pages=args.max_pages, grace_months=max(0, args.retirement_grace_months))
    except Exception as error:  # noqa: BLE001 - record the failure for the agent instead of guessing
        result = {"source": API_URL, "complete": False, "error": f"{type(error).__name__}: {error}",
                  "count": 0, "items": [], "windows": []}
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    status = "complete" if result.get("complete") else "INCOMPLETE"
    print(f"Azure Updates: {result.get('count', 0)} notices ({status}) -> {args.output}")
    if result.get("error"):
        print(f"Fetch error: {result['error']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
