#!/usr/bin/env python3
"""Build bounded, place-specific media search jobs for East Lake."""

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


def build_keywords(unit: dict[str, str], terms: dict, limit: int) -> list[str]:
    aliases = [item.strip() for item in unit["aliases"].split("|") if item.strip()]
    primary = aliases[0]
    candidates: list[str] = []

    # Every POI alias gets several high-yield vegetation terms.
    def anchored(alias: str) -> str:
        return alias if "武汉" in alias else f"武汉 {alias}"

    for alias in aliases:
        for term in ("荷花", "荷叶", "残荷", "水草", "浮萍", "湿地"):
            candidates.append(f"{anchored(alias)} {term}")

    # The primary place name gets the richer phenology and disturbance matrix.
    for plant, phase in terms["preferred_pair_templates"]:
        candidates.append(f"{anchored(primary)} {plant} {phase}")
    for term in terms["core_plants"]:
        candidates.append(f"{anchored(primary)} {term}")
    for term in terms["observation_context"] + terms["management_events"]:
        candidates.append(f"{anchored(primary)} {term}")

    return unique(candidates)[:limit]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--units", type=Path, default=Path("config/east_lake_spatial_units.csv"))
    parser.add_argument("--terms", type=Path, default=Path("config/aquatic_media_terms.json"))
    parser.add_argument("--output", type=Path, default=Path("data/interim/media_collection_plan.json"))
    parser.add_argument("--max-keywords-per-unit", type=int, default=60)
    args = parser.parse_args()

    with args.units.open(encoding="utf-8-sig", newline="") as handle:
        units = list(csv.DictReader(handle))
    terms = json.loads(args.terms.read_text(encoding="utf-8"))

    jobs = []
    for unit in units:
        keywords = build_keywords(unit, terms, args.max_keywords_per_unit)
        jobs.append(
            {
                "unit_id": unit["unit_id"],
                "region": unit["region"],
                "place": unit["place"],
                "aliases": unit["aliases"].split("|"),
                "priority": int(unit["priority"]),
                "image_refs": [int(value) for value in unit["image_refs"].split("|") if value],
                "scope_note": unit["scope_note"],
                "keywords": keywords,
                "platforms": list(PLATFORMS),
            }
        )

    payload = {
        "schema_version": "1.0",
        "generated_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"),
        "research_period": {"start": "2018-01-01", "end": "2026-10-30"},
        "policy": {
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
