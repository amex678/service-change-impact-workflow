import sys
import unittest
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import fetch_azure_updates as fetch  # noqa: E402

AS_OF = datetime(2026, 10, 1, tzinfo=timezone.utc)


def page_fetcher(pages_by_filter):
    """Fake API: returns slices of the configured items according to $filter and $skip."""
    calls = []

    def fetcher(url):
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        filter_expr = query["$filter"][0]
        skip = int(query["$skip"][0])
        calls.append((filter_expr, skip))
        spec = pages_by_filter[filter_expr]
        if callable(spec):
            return spec(skip)
        items, total = spec
        return {"@odata.count": total, "value": items[skip:skip + fetch.PAGE_SIZE]}

    fetcher.calls = calls
    return fetcher


def notice(notice_id, **extra):
    return {"id": notice_id, "title": f"Notice {notice_id}", "products": ["Azure Functions"], "tags": [],
            "modified": "2026-09-20T00:00:00Z", "description": "<p>Body</p>", **extra}


class BuildUrlTests(unittest.TestCase):
    def test_query_round_trips(self):
        url = fetch.build_url("modified ge 2026-09-17T00:00:00Z", skip=200)
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        self.assertEqual(query["$filter"], ["modified ge 2026-09-17T00:00:00Z"])
        self.assertEqual(query["$skip"], ["200"])
        self.assertEqual(query["$top"], [str(fetch.PAGE_SIZE)])
        self.assertEqual(query["$orderby"], ["modified desc,id asc"])
        self.assertNotIn(" ", url)


class FetchAllTests(unittest.TestCase):
    def test_pages_with_skip_until_reported_total(self):
        items = [notice(str(i)) for i in range(250)]
        fetcher = page_fetcher({"f": (items, 250)})
        result = fetch.fetch_all("f", fetcher=fetcher)
        self.assertTrue(result["complete"])
        self.assertEqual(result["unique_items"], 250)
        self.assertEqual([skip for _, skip in fetcher.calls], [0, 100, 200])

    def test_shifted_pages_are_deduplicated_and_marked_incomplete(self):
        first = [notice(str(i)) for i in range(100)]
        second = [notice(str(i)) for i in range(99, 150)]  # one item repeated, one item lost

        def pages(skip):
            return {"@odata.count": 151, "value": first if skip == 0 else second if skip == 100 else []}

        result = fetch.fetch_all("f", fetcher=page_fetcher({"f": pages}))
        self.assertEqual(result["duplicates_dropped"], 1)
        self.assertEqual(result["unique_items"], 150)
        self.assertFalse(result["complete"])

    def test_page_limit_marks_incomplete(self):
        items = [notice(str(i)) for i in range(500)]
        result = fetch.fetch_all("f", fetcher=page_fetcher({"f": (items, 500)}), max_pages=2)
        self.assertEqual(result["unique_items"], 200)
        self.assertFalse(result["complete"])


class NormalizeTests(unittest.TestCase):
    def test_html_to_text_keeps_structure_and_links(self):
        text, links = fetch.html_to_text(
            '<p>Support&nbsp;ends.</p><ul><li>Upgrade to <a href="https://learn.microsoft.com/x">7.6</a></li></ul>')
        self.assertIn("Support ends.", text)
        self.assertIn("- Upgrade to 7.6", text)
        self.assertEqual(links, ["https://learn.microsoft.com/x"])

    def test_normalize_builds_public_url(self):
        normalized = fetch.normalize(notice("572770"))
        self.assertEqual(normalized["url"], "https://azure.microsoft.com/updates?id=572770")
        self.assertEqual(normalized["description_text"], "Body")


class RetirementWindowTests(unittest.TestCase):
    def retirement(self, year, month):
        return {"availabilities": [{"ring": "Retirement", "year": year, "month": month}]}

    def test_future_and_grace_period(self):
        self.assertTrue(fetch.retirement_is_active(self.retirement(2026, "November"), AS_OF))
        self.assertFalse(fetch.retirement_is_active(self.retirement(2026, "August"), AS_OF, grace_months=0))
        self.assertTrue(fetch.retirement_is_active(self.retirement(2026, "August"), AS_OF, grace_months=3))
        self.assertFalse(fetch.retirement_is_active(self.retirement(2026, "June"), AS_OF, grace_months=3))

    def test_grace_crosses_year_boundary(self):
        january = datetime(2027, 1, 15, tzinfo=timezone.utc)
        self.assertEqual(fetch.months_back(january, 3), (2026, 10))
        self.assertTrue(fetch.retirement_is_active(self.retirement(2026, "November"), january, grace_months=3))

    def test_collect_merges_windows(self):
        shared = notice("572770", availabilities=[{"ring": "Retirement", "year": 2026, "month": "November"}])
        old = notice("500157", availabilities=[{"ring": "Retirement", "year": 2028, "month": "September"}])
        expired = notice("1", availabilities=[{"ring": "Retirement", "year": 2026, "month": "January"}])
        recent_filter = "modified ge 2026-09-17T00:00:00Z"
        retirement_filter = "availabilities/any(a: a/ring eq 'Retirement' and a/year ge 2026)"
        fetcher = page_fetcher({recent_filter: ([shared], 1), retirement_filter: ([shared, old, expired], 3)})
        result = fetch.collect(14, True, AS_OF, fetcher=fetcher, grace_months=3)
        by_id = {item["id"]: item for item in result["items"]}
        self.assertEqual(set(by_id), {"572770", "500157"})
        self.assertEqual(by_id["572770"]["windows"], ["recent", "active-retirement"])
        self.assertTrue(result["complete"])


if __name__ == "__main__":
    unittest.main()
