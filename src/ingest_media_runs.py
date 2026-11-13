#!/usr/bin/env python3
"""Normalize MediaCrawler JSONL plus archived media into candidate post rows."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


FIELDS = [
    "record_id", "platform", "query_keyword", "post_url", "content_text",
    "publish_time", "crawl_time", "media_type", "media_local_path", "media_sha256",
    "platform_poi_name", "platform_poi_address", "platform_lng", "platform_lat",
    "coordinate_system", "visual_location", "visual_location_confidence",
    "location_match_class", "vegetation_type", "growth_stage", "cover_grade",
    "phenology_confidence", "media_value", "review_status", "notes", "media_paths",
    "archive_poi",
]

PLATFORMS = {
    "xhs": {"canonical": "xhs", "store": "xhs", "id": "note_id", "url": "note_url", "time": "time"},
    "dy": {"canonical": "douyin", "store": "douyin", "id": "aweme_id", "url": "aweme_url", "time": "create_time"},
    "ks": {"canonical": "kuaishou", "store": "kuaishou", "id": "video_id", "url": "video_url", "time": "create_time"},
    "wb": {"canonical": "weibo", "store": "weibo", "id": "note_id", "url": "note_url", "time": "create_time"},
    "bili": {"canonical": "bilibili", "store": "bilibili", "id": "video_id", "url": "video_url", "time": "create_time"},
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def publish_time(value: object) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, str) and not value.isdigit():
        return value
    number = int(value)
    if number > 10_000_000_000:
        number //= 1000
    return datetime.fromtimestamp(number, ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")


def relative_path(root: Path, value: str) -> str:
    path = Path(value)
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def load_raw(raw_root: Path) -> dict[tuple[str, str], dict]:
    records: dict[tuple[str, str], dict] = {}
    for short, spec in PLATFORMS.items():
        for path in sorted(raw_root.rglob(f"{spec['store']}/jsonl/*contents*.jsonl")):
            with path.open(encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    item = json.loads(line)
                    content_id = str(item.get(spec["id"], ""))
                    if content_id:
                        records[(short, content_id)] = item
    return records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw/media_runs"))
    parser.add_argument("--manifest-root", action="append", type=Path)
    parser.add_argument("--output", type=Path, default=Path("data/interim/media_run_posts.csv"))
    args = parser.parse_args()

    root = args.project_root.resolve()
    raw_root = args.raw_root if args.raw_root.is_absolute() else root / args.raw_root
    manifest_roots = args.manifest_root or [Path("media_collected"), Path("media_candidates")]
    manifest_roots = [path if path.is_absolute() else root / path for path in manifest_roots]
    output = args.output if args.output.is_absolute() else root / args.output
    raw = load_raw(raw_root)

    grouped: dict[tuple[str, str], list[dict[str, str]]] = {}
    scopes: dict[tuple[str, str], set[str]] = {}
    for manifest_root in manifest_roots:
        scope = manifest_root.name
        for manifest in sorted(manifest_root.rglob("media_manifest.csv")):
            for row in read_csv(manifest):
                key = (row.get("platform", ""), row.get("content_id", ""))
                if all(key):
                    grouped.setdefault(key, []).append(row)
                    scopes.setdefault(key, set()).add(scope)

    rows: list[dict[str, str]] = []
    missing_raw = 0
    for (short, content_id), media_rows in sorted(grouped.items()):
        spec = PLATFORMS.get(short)
        item = raw.get((short, content_id))
        if not spec or not item:
            missing_raw += 1
            continue
        media_rows.sort(key=lambda row: (row.get("archive_path", ""), int(row.get("media_index") or 0)))
        paths = [relative_path(root, row["archive_path"]) for row in media_rows]
        kinds = {row.get("media_type", "") for row in media_rows}
        text = "\n".join(
            value.strip()
            for value in (str(item.get("title", "")), str(item.get("desc", "")), str(item.get("content", "")))
            if value.strip()
        )
        platform = spec["canonical"]
        rid = hashlib.sha256(f"{platform}|{content_id}".encode()).hexdigest()[:24]
        first = media_rows[0]
        row = {field: "" for field in FIELDS}
        row.update(
            {
                "record_id": rid,
                "platform": platform,
                "query_keyword": str(item.get("source_keyword", "")),
                "post_url": str(item.get(spec["url"], "")),
                "content_text": text,
                "publish_time": first.get("publish_time", "") or publish_time(item.get(spec["time"])),
                "crawl_time": first.get("crawl_time", ""),
                "media_type": "mixed" if len(kinds) > 1 else (next(iter(kinds)) if kinds else "media"),
                "media_local_path": paths[0],
                "media_sha256": first.get("sha256", ""),
                "coordinate_system": "unknown",
                "visual_location_confidence": "unknown",
                "location_match_class": "unknown",
                "growth_stage": "unknown",
                "cover_grade": "unknown",
                "phenology_confidence": "unknown",
                "media_value": "unknown",
                "review_status": "candidate_unverified",
                "notes": ";".join(
                    [
                        "source=mediacrawler",
                        "platform_location_absent",
                        f"archive_scope={'+'.join(sorted(scopes[(short, content_id)]))}",
                        f"unit_id={first.get('unit_id', '')}",
                    ]
                ),
                "media_paths": "|".join(paths),
                "archive_poi": first.get("place", "") if first.get("unit_id") != "REGION01" else "",
            }
        )
        rows.append(row)

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({"posts": len(rows), "missing_raw": missing_raw, "output": str(output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
