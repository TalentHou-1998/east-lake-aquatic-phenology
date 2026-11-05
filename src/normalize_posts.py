#!/usr/bin/env python3
"""Normalize a crawler CSV into the research schema without author identifiers."""

from __future__ import annotations

import argparse
import csv
import hashlib
import sqlite3
from collections import defaultdict
from math import ceil
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo


OUTPUT_COLUMNS = [
    "record_id",
    "platform",
    "query_keyword",
    "post_url",
    "content_text",
    "publish_time",
    "crawl_time",
    "media_type",
    "media_local_path",
    "media_sha256",
    "platform_poi_name",
    "platform_poi_address",
    "platform_lng",
    "platform_lat",
    "coordinate_system",
    "visual_location",
    "visual_location_confidence",
    "location_match_class",
    "vegetation_type",
    "growth_stage",
    "cover_grade",
    "phenology_confidence",
    "media_value",
    "review_status",
    "notes",
]


def canonical_url(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    parts = urlsplit(value)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), "", ""))


def record_id(platform: str, url: str, text: str, publish_time: str) -> str:
    identity = f"{platform}\n{url}\n{text}\n{publish_time}".encode("utf-8")
    return hashlib.sha256(identity).hexdigest()[:24]


def strict_east_lake(source: dict[str, str]) -> bool:
    text = source.get("content_text", "") or ""
    poi = source.get("poi_name", "") or ""
    address = source.get("poi_address", "") or ""
    combined = f"{text} {poi} {address}"
    if "东湖" not in combined:
        return False

    # “东湖高新区/东湖新技术开发区”是行政区名，不能单独证明内容位于东湖湖区。
    administrative_terms = ("东湖高新区", "东湖新技术开发区")
    scenic_terms = (
        "东湖风景",
        "东湖绿道",
        "东湖荷",
        "磨山",
        "听涛",
        "落雁",
        "白马",
        "凌波门",
        "东湖之眼",
    )
    if any(term in combined for term in administrative_terms) and not any(
        term in combined for term in scenic_terms
    ):
        return False

    if "武汉" in f"{text} {address}":
        return True
    try:
        longitude = float(source.get("location_lng", ""))
        latitude = float(source.get("location_lat", ""))
    except (TypeError, ValueError):
        return False
    return 114.32 <= longitude <= 114.48 and 30.48 <= latitude <= 30.62 and "东湖" in poi


def temporal_spread(rows: list[dict[str, str]], limit: int) -> list[dict[str, str]]:
    if limit <= 0 or len(rows) <= limit:
        return rows
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[row["publish_time"][:4]].append(row)
    for values in groups.values():
        values.sort(key=lambda row: row["publish_time"])

    years = sorted(groups)
    quota = ceil(limit / max(1, len(years)))
    selected: list[dict[str, str]] = []
    leftovers: dict[str, list[dict[str, str]]] = {}
    for year in years:
        selected.extend(groups[year][:quota])
        leftovers[year] = groups[year][quota:]
    while len(selected) < limit and any(leftovers.values()):
        for year in reversed(years):
            if leftovers[year] and len(selected) < limit:
                selected.append(leftovers[year].pop(0))
    return sorted(selected[:limit], key=lambda row: row["publish_time"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--platform", required=True, choices=["amap", "douyin", "kesong", "kuaishou"])
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--state-db", default="", help="Optional dykw state SQLite used to recover query_keyword")
    parser.add_argument("--require-term", default="", help="Keep only rows whose text/POI/address contains this term")
    parser.add_argument("--east-lake-strict", action="store_true", help="Require explicit Wuhan evidence or an East Lake POI coordinate")
    parser.add_argument("--temporal-spread", action="store_true", help="Retain scarce older years before filling from abundant years")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    crawl_time = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")
    seen: set[str] = set()
    rows: list[dict[str, str]] = []
    keyword_by_item: dict[str, str] = {}
    if args.state_db:
        connection = sqlite3.connect(args.state_db)
        keyword_by_item = {
            str(item_id): str(keyword or "")
            for item_id, keyword in connection.execute(
                "SELECT item_id, keyword FROM seen_item WHERE platform = ?", (args.platform,)
            )
        }
        connection.close()

    with input_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for source in csv.DictReader(handle):
            url = canonical_url(source.get("post_url", ""))
            text = (source.get("content_text", "") or "").strip()
            publish_time = (source.get("publish_time", "") or "").strip()
            region_text = " ".join(
                [text, source.get("poi_name", "") or "", source.get("poi_address", "") or ""]
            )
            if args.require_term and args.require_term not in region_text:
                continue
            if args.east_lake_strict and not strict_east_lake(source):
                continue
            rid = record_id(args.platform, url, text, publish_time)
            if rid in seen:
                continue
            seen.add(rid)
            rows.append(
                {
                    "record_id": rid,
                    "platform": args.platform,
                    "query_keyword": keyword_by_item.get(url.rsplit("/", 1)[-1], ""),
                    "post_url": url,
                    "content_text": text,
                    "publish_time": publish_time,
                    "crawl_time": crawl_time,
                    "media_type": source.get("media_type", "unknown") or "unknown",
                    "media_local_path": "",
                    "media_sha256": "",
                    "platform_poi_name": source.get("poi_name", "") or "",
                    "platform_poi_address": source.get("poi_address", "") or "",
                    "platform_lng": source.get("location_lng", "") or "",
                    "platform_lat": source.get("location_lat", "") or "",
                    "coordinate_system": "unknown",
                    "visual_location": "",
                    "visual_location_confidence": "unknown",
                    "location_match_class": "unknown",
                    "vegetation_type": "",
                    "growth_stage": "unknown",
                    "cover_grade": "unknown",
                    "phenology_confidence": "unknown",
                    "media_value": "unknown",
                    "review_status": "pending",
                    "notes": "",
                }
            )
    if args.temporal_spread:
        rows = temporal_spread(rows, args.limit)
    elif args.limit > 0:
        rows = rows[: args.limit]

    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"normalized_rows={len(rows)} output={output_path}")


if __name__ == "__main__":
    main()

