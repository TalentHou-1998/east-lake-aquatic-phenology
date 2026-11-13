#!/usr/bin/env python3
"""Build broad-landmark media search jobs for East Lake."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


def unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        value = " ".join(value.split())
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def build_query_records(poi: dict[str, str], terms: dict, limit: int) -> list[dict[str, str]]:
    anchors = [item.strip() for item in poi["search_anchors"].split("|") if item.strip()]
    candidates: list[tuple[str, str]] = []

    candidates.extend((anchor, "place_name") for anchor in anchors)
    for term in terms["loose_search_terms"]:
        for anchor in anchors:
            candidates.append((f"{anchor} {term}", "place_plus_context"))

    primary = anchors[0]
    for plant, phase in terms["preferred_pair_templates"]:
        candidates.append((f"{primary} {plant} {phase}", "place_plus_phenology"))

    seen: set[str] = set()
    records: list[dict[str, str]] = []
    for query, strategy in candidates:
        query = " ".join(query.split())
        if query and query not in seen:
            seen.add(query)
            records.append({"query": query, "strategy": strategy})
    return records[:limit]


def regional_job(terms: dict, platforms: list[str], routes: dict[str, str]) -> dict:
    queries = unique(terms["regional_recall_terms"])
    return {
        "unit_id": "REGION01",
        "broad_poi_id": "",
        "region": "武汉东湖及周边",
        "place": "武汉东湖及周边（无定位召回）",
        "source_unit_ids": [],
        "search_anchors": ["武汉", "东湖"],
        "aliases": ["武汉东湖", "东湖风景区", "东湖绿道"],
        "priority": 0,
        "image_refs": [],
        "scope_note": "召回正文、字幕或画面文字指向研究区，但平台没有挂载定位的内容",
        "keywords": queries,
        "query_records": [{"query": query, "strategy": "regional_content_recall"} for query in queries],
        "platforms": platforms,
        "collector_routes": routes,
        "requires_platform_geotag": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--units", type=Path, default=Path("config/east_lake_spatial_units.csv"))
    parser.add_argument("--hierarchy", type=Path, default=Path("config/east_lake_poi_hierarchy.csv"))
    parser.add_argument("--terms", type=Path, default=Path("config/aquatic_media_terms.json"))
    parser.add_argument("--platforms", type=Path, default=Path("config/platform_sources.json"))
    parser.add_argument("--output", type=Path, default=Path("data/interim/media_collection_plan.json"))
    parser.add_argument("--max-keywords-per-unit", type=int, default=48)
    args = parser.parse_args()

    with args.units.open(encoding="utf-8-sig", newline="") as handle:
        units = list(csv.DictReader(handle))
    with args.hierarchy.open(encoding="utf-8-sig", newline="") as handle:
        broad_pois = list(csv.DictReader(handle))
    terms = json.loads(args.terms.read_text(encoding="utf-8"))
    platform_config = json.loads(args.platforms.read_text(encoding="utf-8"))
    platforms = [item["key"] for item in platform_config["platforms"] if item.get("media")]
    routes = {item["key"]: item["route"] for item in platform_config["platforms"] if item.get("media")}

    units_by_id = {unit["unit_id"]: unit for unit in units}

    jobs = [regional_job(terms, platforms, routes)]
    for poi in broad_pois:
        source_unit_ids = [item for item in poi["source_unit_ids"].split("|") if item]
        source_units = [units_by_id[unit_id] for unit_id in source_unit_ids]
        query_records = build_query_records(poi, terms, args.max_keywords_per_unit)
        keywords = [item["query"] for item in query_records]
        jobs.append(
            {
                "unit_id": poi["broad_poi_id"],
                "broad_poi_id": poi["broad_poi_id"],
                "region": source_units[0]["region"],
                "place": poi["broad_poi"],
                "source_unit_ids": source_unit_ids,
                "search_anchors": poi["search_anchors"].split("|"),
                "aliases": poi["match_aliases"].split("|"),
                "priority": min(int(unit["priority"]) for unit in source_units),
                "image_refs": sorted({int(value) for unit in source_units for value in unit["image_refs"].split("|") if value}),
                "scope_note": poi["scope_note"],
                "keywords": keywords,
                "query_records": query_records,
                "platforms": platforms,
                "collector_routes": routes,
                "requires_platform_geotag": False,
            }
        )

    payload = {
        "schema_version": "3.0",
        "generated_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"),
        "research_period": {"start": "2018-01-01", "end": "2026-10-30"},
        "policy": {
            "poi_level": "broad_landmark",
            "platform_geotag_required": False,
            "location_decision_sources": ["platform_location", "content_text", "ocr_text", "visual_landmark"],
            "query_keyword_is_location_proof": False,
            "media_only_final_archive": True,
            "comments": False,
            "max_concurrency": 1,
            "incremental_batches": True,
            "stop_on_verification_or_risk_control": True,
        },
        "jobs": sorted(jobs, key=lambda item: (item["priority"], item["unit_id"])),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"units={len(jobs)} keywords={sum(len(job['keywords']) for job in jobs)} output={args.output}")


if __name__ == "__main__":
    main()
