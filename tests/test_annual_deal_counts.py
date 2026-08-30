"""Tests for the count-only Artemis dashboard smoke test."""

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from validate_annual_deal_counts import (  # noqa: E402
    compare_counts,
    count_directory_deals,
    parse_dashboard_reference,
)


class AnnualDealCountValidationTests(unittest.TestCase):
    def test_parses_dashboard_arrays_and_modified_date(self):
        html = """
        <script type="application/ld+json">{"dateModified":"2026-08-27T10:33:39+00:00"}</script>
        <script>
        xAxis: [{categories: ['2024', '2025', '2026']}],
        series: [{name: 'No. of Transactions', data: [93, 122, 91]}]
        </script>
        """
        parsed = parse_dashboard_reference(html)
        self.assertEqual(parsed.modified_at, "2026-08-27T10:33:39+00:00")
        self.assertEqual(parsed.counts["year"].tolist(), [2024, 2025, 2026])
        self.assertEqual(parsed.counts["artemis_dashboard_count"].tolist(), [93, 122, 91])

    def test_counts_unique_urls_and_strict_dates(self):
        index = pd.DataFrame(
            {
                "deal_url": ["https://example/a", "https://example/b", "https://example/c"],
                "date_text": ["Jan 2024", "Dec 2024", "Jan 2025"],
            }
        )
        counted = count_directory_deals(index)
        self.assertEqual(counted.to_dict("records"), [
            {"year": 2024, "directory_count": 2},
            {"year": 2025, "directory_count": 1},
        ])

    def test_duplicate_url_fails_loudly(self):
        index = pd.DataFrame(
            {
                "deal_url": ["https://example/a", "https://example/a"],
                "date_text": ["Jan 2024", "Jan 2024"],
            }
        )
        with self.assertRaisesRegex(ValueError, "duplicate deal URL"):
            count_directory_deals(index)

    def test_comparison_distinguishes_scope_gap_from_missing(self):
        directory = pd.DataFrame(
            {"year": [2023, 2024, 2025], "directory_count": [11, 10, 8]}
        )
        dashboard = pd.DataFrame(
            {"year": [2023, 2024, 2025], "artemis_dashboard_count": [10, 10, 9]}
        )
        result = compare_counts(directory, dashboard)
        self.assertEqual(result["result"].tolist(), ["SCOPE_GAP", "MATCH", "FAIL_MISSING"])


if __name__ == "__main__":
    unittest.main()
