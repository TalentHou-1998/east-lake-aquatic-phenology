#!/usr/bin/env python3
"""Build a publication-time-named, POI-centric media archive.

The source archive is left untouched. Files in the rebuilt archive are hard
linked when possible (and copied as a fallback), so the operation is
recoverable and does not duplicate file contents on the same filesystem.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
import hashlib
import os
from pathlib import Path
import re
import shutil


PLATFORM_NAMES = {
    "amap": "高德地图",
    "baidu": "百度地图",
    "bili": "哔哩哔哩",
    "bilibili": "哔哩哔哩",
    "dianping": "大众点评",
    "douyin": "抖音",
    "dy": "抖音",
    "kuaishou": "快手",
    "meituan": "美团",
    "2bulu": "两步路",
    "kesong": "可颂",
    "ks": "快手",
    "weibo": "微博",
    "wb": "微博",
    "xhs": "小红书",
}

PLATFORM_KEYS = {
    "amap": "amap",
    "baidu": "baidu",
    "bili": "bilibili",
    "bilibili": "bilibili",
    "dianping": "dianping",
    "douyin": "douyin",
    "dy": "douyin",
    "kuaishou": "kuaishou",
    "meituan": "meituan",
    "2bulu": "2bulu",
    "kesong": "kesong",
    "ks": "kuaishou",
    "weibo": "weibo",
    "wb": "weibo",
    "xhs": "xhs",
}

INDEX_FIELDS = [
    "new_archive_path",
    "original_archive_path",
    "sha256",
    "platform",
    "platform_name",
    "region",
    "poi",
    "year_folder",
    "source_place",
    "unit_id",
    "content_id",
    "media_index",
    "media_type",
    "publish_time",
    "crawl_time",
    "source_keyword",
    "source_url",
]


def safe_name(value: str, fallback: str = "地点待核验") -> str:
    value = (value or "").strip()
    value = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "_", value)
    value = re.sub(r"\s+", " ", value).strip(" .-")
    return value[:100] or fallback


def publish_stamp(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return "发布时间未知"
    normalized = value.replace("Z", "+00:00")
    for parser in (
        lambda text: datetime.fromisoformat(text),
        lambda text: datetime.strptime(text, "%Y-%m-%d %H:%M:%S"),
        lambda text: datetime.strptime(text, "%Y-%m-%d"),
    ):
        try:
            parsed = parser(normalized)
            if len(value) <= 10:
                return parsed.strftime("%Y%m%d")
            return parsed.strftime("%Y%m%d-%H%M%S")
        except ValueError:
            continue
    compact = re.sub(r"[^0-9]", "", value)
    return compact[:14] or "发布时间未知"


def normalized_extension(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".bin":
        try:
            if path.read_bytes()[:3] == b"\xff\xd8\xff":
                return ".jpg"
        except OSError:
            pass
    return suffix or ".media"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def processed_lookups(path: Path) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    by_id: dict[str, dict[str, str]] = {}
    by_url: dict[str, dict[str, str]] = {}
    if not path.exists():
        return by_id, by_url
    for row in read_csv(path):
        if row.get("record_id"):
            by_id[row["record_id"]] = row
        if row.get("post_url"):
            by_url[row["post_url"]] = row
    return by_id, by_url


def load_hierarchy(path: Path) -> tuple[dict[str, str], list[tuple[str, str]]]:
    mapping: dict[str, str] = {}
    aliases: list[tuple[str, str]] = []
    for row in read_csv(path):
        mapping[row["broad_poi_id"]] = row["broad_poi"]
        for unit_id in row["source_unit_ids"].split("|"):
            if unit_id:
                mapping[unit_id] = row["broad_poi"]
        for alias in [row["broad_poi"], *row["search_anchors"].split("|"), *row["match_aliases"].split("|")]:
            if alias:
                aliases.append((alias, row["broad_poi"]))
    return mapping, sorted(set(aliases), key=lambda item: len(item[0]), reverse=True)


def choose_poi(
    row: dict[str, str],
    processed: dict[str, str] | None,
    location_evidence: dict[str, str] | None,
    hierarchy: dict[str, str],
    aliases: list[tuple[str, str]],
) -> str:
    evidence_poi = (location_evidence or {}).get("matched_broad_poi", "").strip()
    if evidence_poi:
        return evidence_poi
    mapped = hierarchy.get(row.get("unit_id", ""))
    if mapped:
        return mapped
    evidence = " ".join(
        [
            row.get("place", ""),
            row.get("source_keyword", ""),
            (processed or {}).get("platform_poi_name", ""),
            (processed or {}).get("platform_poi_address", ""),
            (processed or {}).get("query_keyword", ""),
        ]
    )
    scores: dict[str, int] = {}
    for alias, broad_poi in aliases:
        if alias in evidence:
            scores[broad_poi] = max(scores.get(broad_poi, 0), len(alias))
    if scores:
        best = max(scores.values())
        winners = [poi for poi, score in scores.items() if score == best]
        if len(winners) == 1:
            return winners[0]
    return "东湖风景区（综合）"


def year_folder(value: str) -> str:
    match = re.match(r"^(20\d{2})", (value or "").strip())
    return match.group(1) if match else "年份未知"


def hardlink_or_copy(source: Path, target: Path) -> str:
    if target.exists():
        if target.stat().st_size == source.stat().st_size:
            return "existing"
        raise FileExistsError(f"target exists with different size: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, target)
        return "hardlink"
    except OSError:
        shutil.copy2(source, target)
        return "copy"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--source-root", type=Path, default=Path("media_collected"))
    parser.add_argument("--output-root", type=Path, default=Path("media_by_landmark_year"))
    parser.add_argument("--processed", type=Path, default=Path("data/processed/all_posts.csv"))
    parser.add_argument("--evidence", type=Path, default=Path("data/processed/location_evidence.csv"))
    parser.add_argument("--hierarchy", type=Path, default=Path("config/east_lake_poi_hierarchy.csv"))
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    source_root = args.source_root if args.source_root.is_absolute() else project_root / args.source_root
    output_root = args.output_root if args.output_root.is_absolute() else project_root / args.output_root
    processed_path = args.processed if args.processed.is_absolute() else project_root / args.processed
    evidence_path = args.evidence if args.evidence.is_absolute() else project_root / args.evidence
    hierarchy_path = args.hierarchy if args.hierarchy.is_absolute() else project_root / args.hierarchy
    output_root.mkdir(parents=True, exist_ok=True)

    by_id, by_url = processed_lookups(processed_path)
    evidence_by_id = {
        row["record_id"]: row for row in read_csv(evidence_path)
    } if evidence_path.exists() else {}
    hierarchy, hierarchy_aliases = load_hierarchy(hierarchy_path)
    source_rows: list[dict[str, str]] = []
    for manifest in sorted(source_root.rglob("media_manifest.csv")):
        source_rows.extend(read_csv(manifest))

    prepared: list[dict[str, str]] = []
    for row in source_rows:
        source = project_root / row["archive_path"]
        if not source.is_file():
            raise FileNotFoundError(source)
        processed = by_id.get(row.get("content_id", "")) or by_url.get(row.get("source_url", ""))
        location_evidence = evidence_by_id.get((processed or {}).get("record_id", ""))
        poi = safe_name(choose_poi(row, processed, location_evidence, hierarchy, hierarchy_aliases))
        prepared.append(
            {
                **row,
                "_source": str(source),
                "poi": poi,
                "platform": PLATFORM_KEYS.get(row.get("platform", ""), row.get("platform", "unknown")),
                "platform_name": PLATFORM_NAMES.get(row.get("platform", ""), row.get("platform", "未知平台")),
                "_stamp": publish_stamp(row.get("publish_time", "")),
                "year_folder": year_folder(row.get("publish_time", "")),
                "source_place": row.get("place", ""),
            }
        )

    prepared.sort(
        key=lambda row: (
            row["poi"],
            row["year_folder"],
            row["publish_time"] or "9999",
            row["platform_name"],
            row.get("content_id", ""),
            int(row.get("media_index") or 0),
            row.get("sha256", ""),
        )
    )

    counters: dict[tuple[str, str], int] = {}
    index_rows: list[dict[str, str]] = []
    methods: dict[str, int] = {"hardlink": 0, "copy": 0, "existing": 0}
    for row in prepared:
        poi = row["poi"]
        year = row["year_folder"]
        counter_key = (poi, year)
        counters[counter_key] = counters.get(counter_key, 0) + 1
        sequence = counters[counter_key]
        if sequence > 999:
            raise RuntimeError(f"POI {poi!r} exceeds the requested 001-999 sequence range")
        source = Path(row["_source"])
        filename = f"{poi}-{row['_stamp']}-{row['platform_name']}-{sequence:03d}{normalized_extension(source)}"
        target = output_root / poi / year / filename
        methods[hardlink_or_copy(source, target)] += 1
        new_path = target.relative_to(project_root).as_posix()
        indexed = {field: row.get(field, "") for field in INDEX_FIELDS}
        indexed["new_archive_path"] = new_path
        indexed["original_archive_path"] = row.get("archive_path", "")
        indexed["poi"] = poi
        indexed["year_folder"] = year
        indexed["source_place"] = row.get("place", "")
        indexed["platform"] = row["platform"]
        indexed["platform_name"] = row["platform_name"]
        index_rows.append(indexed)

    write_csv(output_root / "_归档索引.csv", index_rows, INDEX_FIELDS)
    for poi, year in sorted(counters):
        write_csv(
            output_root / poi / year / "媒体索引.csv",
            [row for row in index_rows if row["poi"] == poi and row["year_folder"] == year],
            INDEX_FIELDS,
        )

    digest = hashlib.sha256((output_root / "_归档索引.csv").read_bytes()).hexdigest()
    print(
        f"media={len(index_rows)} broad_pois={len({poi for poi, _ in counters})} year_folders={len(counters)} hardlinks={methods['hardlink']} "
        f"copies={methods['copy']} existing={methods['existing']} index_sha256={digest}"
    )


if __name__ == "__main__":
    main()
