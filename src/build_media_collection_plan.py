#!/usr/bin/env python3
"""Build broad-landmark media search jobs for East Lake."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


PLATFORMS = ("xhs", "dy", "ks", "wb", "baidu", "amap")


def unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        value = " ".join(value.split())
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def build_keywords(poi: dict[str, str], terms: dict, limit: int) -> list[str]:
    anchors = [item.strip() for item in poi["search_anchors"].split("|") if item.strip()]
    candidates: list[str] = []

    # Keep the geographic anchor recognizable, but loosen the thematic side.
    candidates.extend(anchors)
    for term in terms["loose_search_terms"]:
        for anchor in anchors:
            candidates.append(f"{anchor} {term}")

    # Retain a small phenology-focused tail for seasonal evidence.
    primary = anchors[0]
    for plant, phase in terms["preferred_pair_templates"]:
        candidates.append(f"{primary} {plant} {phase}")

    return unique(candidates)[:limit]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--units", type=Path, default=Path("config/east_lake_spatial_units.csv"))
    parser.add_argument("--hierarchy", type=Path, default=Path("config/east_lake_poi_hierarchy.csv"))
    parser.add_argument("--terms", type=Path, default=Path("config/aquatic_media_terms.json"))
    parser.add_argument("--output", type=Path, default=Path("data/interim/media_collection_plan.json"))
    parser.add_argument("--max-keywords-per-unit", type=int, default=48)
    args = parser.parse_args()

    with args.units.open(encoding="utf-8-sig", newline="") as handle:
        units = list(csv.DictReader(handle))
    with args.hierarchy.open(encoding="utf-8-sig", newline="") as handle:
        broad_pois = list(csv.DictReader(handle))
    terms = json.loads(args.terms.read_text(encoding="utf-8"))

    units_by_id = {unit["unit_id"]: unit for unit in units}

    jobs = []
    for poi in broad_pois:
        source_unit_ids = [item for item in poi["source_unit_ids"].split("|") if item]
        source_units = [units_by_id[unit_id] for unit_id in source_unit_ids]
        keywords = build_keywords(poi, terms, args.max_keywords_per_unit)
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
                "platforms": list(PLATFORMS),
            }
        )

    payload = {
        "schema_version": "2.0",
        "generated_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"),
        "research_period": {"start": "2018-01-01", "end": "2026-10-30"},
        "policy": {
            "poi_level": "broad_landmark",
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
