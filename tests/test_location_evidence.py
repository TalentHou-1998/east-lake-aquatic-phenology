import unittest

from src.build_location_evidence import evaluate


ALIASES = [
    ("东湖听涛景区", "东湖听涛景区"),
    ("听涛景区", "东湖听涛景区"),
    ("东湖磨山景区", "东湖磨山景区"),
    ("磨山景区", "东湖磨山景区"),
]


def row(**overrides):
    value = {
        "platform_poi_name": "",
        "platform_poi_address": "",
        "platform_lng": "",
        "content_text": "",
        "visual_location": "",
        "query_keyword": "东湖磨山景区 荷花",
    }
    value.update(overrides)
    return value


class LocationEvidenceTests(unittest.TestCase):
    def test_content_can_locate_without_platform_geotag(self):
        result = evaluate(
            row(content_text="今天在听涛景区荷塘边看到荷花"),
            "",
            ALIASES,
        )
        self.assertEqual(result["matched_broad_poi"], "东湖听涛景区")
        self.assertEqual(result["location_decision"], "located_candidate")
        self.assertEqual(result["platform_geotag_present"], "false")
        self.assertIn("content_text", result["location_evidence_sources"])

    def test_ocr_can_locate_without_caption(self):
        result = evaluate(row(), "东湖磨山景区 游客中心", ALIASES)
        self.assertEqual(result["matched_broad_poi"], "东湖磨山景区")
        self.assertIn("ocr_text", result["location_evidence_sources"])

    def test_generic_east_lake_plus_aquatic_context_is_regional(self):
        result = evaluate(row(content_text="武汉东湖湖边的残荷已经枯黄"), "", ALIASES)
        self.assertEqual(result["matched_broad_poi"], "东湖风景区（综合）")
        self.assertEqual(result["location_decision"], "regional_candidate")

    def test_query_keyword_is_not_location_proof(self):
        result = evaluate(row(), "", ALIASES)
        self.assertEqual(result["matched_broad_poi"], "")
        self.assertEqual(result["location_decision"], "needs_review")

    def test_synthetic_text_poi_is_not_platform_geotag(self):
        result = evaluate(
            row(
                platform_poi_name="东湖（正文提及，未提供平台定位）",
                content_text="东湖荷花",
            ),
            "",
            ALIASES,
        )
        self.assertEqual(result["platform_geotag_present"], "false")


if __name__ == "__main__":
    unittest.main()
