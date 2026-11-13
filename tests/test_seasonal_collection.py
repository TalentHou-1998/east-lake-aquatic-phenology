import unittest

from src.build_media_collection_plan import build_query_records
from src.organize_media_archive import parse_months


class SeasonalCollectionTests(unittest.TestCase):
    def setUp(self):
        self.poi = {"search_anchors": "东湖听涛景区|听涛景区"}
        self.terms = {
            "spring_backfill_terms": ["春天", "清明"],
            "seasonal_recall_terms": [],
            "calendar_event_terms": [{"term": "五一", "target_months": "4-5"}],
            "neutral_activity_terms": ["周末", "散步"],
            "loose_search_terms": ["荷花"],
            "preferred_pair_templates": [["荷花", "盛花"]],
        }

    def test_spring_queries_precede_aquatic_queries(self):
        rows = build_query_records(self.poi, self.terms, 50)
        strategies = [row["strategy"] for row in rows]
        self.assertLess(strategies.index("spring_backfill"), strategies.index("place_plus_context"))

    def test_spring_queries_have_target_months(self):
        rows = build_query_records(self.poi, self.terms, 50)
        spring = [row for row in rows if row["strategy"] == "spring_backfill"]
        self.assertTrue(spring)
        self.assertTrue(all(row["target_months"] == "1-5" for row in spring))

    def test_month_range_parser(self):
        self.assertEqual(parse_months("1-3,5,12"), {1, 2, 3, 5, 12})

    def test_month_range_parser_rejects_invalid_month(self):
        with self.assertRaises(ValueError):
            parse_months("0,13")


if __name__ == "__main__":
    unittest.main()
