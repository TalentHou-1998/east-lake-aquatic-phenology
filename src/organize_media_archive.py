#!/usr/bin/env python3
"""Place MediaCrawler downloads under region/place and emit text-free metadata."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


PLATFORM_SPEC = {
    "xhs": {"id": "note_id", "time": "time", "url": "note_url", "store_dir": "xhs", "media_dir": "xhs"},
    "dy": {"id": "aweme_id", "time": "create_time", "url": "aweme_url", "store_dir": "douyin", "media_dir": "dy"},
    "ks": {"id": "video_id", "time": "create_time", "url": "video_url", "store_dir": "kuaishou", "media_dir": "ks"},
    "wb": {"id": "note_id", "time": "create_time", "url": "note_url", "store_dir": "weibo", "media_dir": "wb"},
    "bili": {"id": "video_id", "time": "create_time", "url": "video_url", "store_dir": "bilibili", "media_dir": "bili"},
}
MEDIA_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4", ".mov", ".m4v", ".webm"}
FIELDS = [
    "archive_path", "sha256", "platform", "region", "place", "unit_id", "content_id",
    "media_index", "gallery_size", "media_type", "quality_flag", "crawl_time", "publish_time",
    "source_keyword", "source_url",
]


def safe_component(value: str) -> str:
    value = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "_", value).strip(" .")
    return value[:100] or "unknown"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_time(value) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, str) and not value.isdigit():
        return value
    number = int(value)
    if number > 10_000_000_000:
        number //= 1000
    return datetime.fromtimestamp(number, ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")


def read_records(run_root: Path, platform: str) -> list[dict]:
    records: list[dict] = []
    store_dir = PLATFORM_SPEC[platform]["store_dir"]
    for path in sorted((run_root / store_dir / "jsonl").glob("*contents*.jsonl")):
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    records.append(json.loads(line))
    return records


def location_match_state(record: dict, unit: dict, all_units: list[dict]) -> str:
    """Return match/ambiguous/none using the strongest explicit POI alias."""
    text = " ".join(
        str(record.get(field, ""))
        for field in ("title", "desc", "content", "note_title", "note_desc")
    )
    scores: dict[str, int] = {}
    for candidate in all_units:
        aliases = [alias for alias in candidate.get("aliases", []) if len(alias) >= 4]
        scores[candidate["unit_id"]] = max(
            (len(alias) for alias in aliases if alias in text),
            default=0,
        )
    current = scores.get(unit["unit_id"], 0)
    if current == 0:
        return "none"
    if any(score >= current for unit_id, score in scores.items() if unit_id != unit["unit_id"]):
        return "ambiguous"
    return "match"


def aquatic_relevant(record: dict) -> bool:
    text = " ".join(
        str(record.get(field, ""))
        for field in ("title", "desc", "content", "note_title", "note_desc")
    )
    terms = (
        "荷花", "荷叶", "荷塘", "荷园", "残荷", "莲花", "并蒂莲", "睡莲",
        "水草", "浮萍", "水葫芦", "芦苇", "菖蒲", "香蒲", "菱角", "水生植物",
        "湿地", "水道", "池塘", "湖湾", "浅滩", "返青", "盛花", "枯黄", "打捞",
    )
    return any(term in text for term in terms)


def place_file(source: Path, target: Path, mode: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        return
    if mode == "copy":
        shutil.copy2(source, target)
    else:
        try:
            os.link(source, target)
        except OSError:
            shutil.copy2(source, target)


def collision_safe_target(target: Path, digest: str) -> Path:
    """Keep names deterministic while avoiding silent collisions across repeat runs."""
    if not target.exists() or sha256(target) == digest:
        return target
    return target.with_name(f"{target.stem}_{digest[:8]}{target.suffix}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--platform", required=True, choices=tuple(PLATFORM_SPEC))
    parser.add_argument("--unit-id", required=True)
    parser.add_argument("--plan", type=Path, default=Path("data/interim/media_collection_plan.json"))
    parser.add_argument("--archive-root", type=Path, default=Path("media_collected"))
    parser.add_argument("--crawl-time", default="")
    parser.add_argument("--mode", choices=("hardlink", "copy"), default="hardlink")
    parser.add_argument("--start", default="2018-01-01")
    parser.add_argument("--end", default="2026-10-30")
    parser.add_argument(
        "--allow-unanchored",
        action="store_true",
        help="Archive records without a Wuhan/POI anchor; disabled by default.",
    )
    parser.add_argument(
        "--allow-nonaquatic",
        action="store_true",
        help="Archive records without aquatic vegetation semantics; disabled by default.",
    )
    args = parser.parse_args()

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    unit = next((job for job in plan["jobs"] if job["unit_id"] == args.unit_id), None)
    if unit is None:
        raise SystemExit(f"unknown unit_id: {args.unit_id}")

    crawl_dt = (
        datetime.fromisoformat(args.crawl_time)
        if args.crawl_time
        else datetime.now(ZoneInfo("Asia/Shanghai"))
    )
    stamp = crawl_dt.strftime("%Y%m%dT%H%M%S")
    spec = PLATFORM_SPEC[args.platform]
    records = read_records(args.run_root, args.platform)
    destination = args.archive_root / safe_component(unit["region"]) / safe_component(unit["place"]) / args.platform
    manifest_path = destination.parent / "media_manifest.csv"

    existing: list[dict[str, str]] = []
    known_hashes: set[str] = set()
    if manifest_path.exists():
        with manifest_path.open(encoding="utf-8-sig", newline="") as handle:
            existing = list(csv.DictReader(handle))
        known_hashes = {row["sha256"] for row in existing if row.get("sha256")}

    added: list[dict[str, str]] = []
    skipped_text_only = 0
    skipped_out_of_period = 0
    skipped_geography = 0
    skipped_ambiguous_geography = 0
    skipped_nonaquatic = 0
    for record in records:
        content_id = str(record.get(spec["id"], ""))
        publish_time = parse_time(record.get(spec["time"]))
        if publish_time and not (args.start <= publish_time[:10] <= args.end):
            skipped_out_of_period += 1
            continue
        if not args.allow_unanchored:
            location_state = location_match_state(record, unit, plan["jobs"])
            if location_state == "none":
                skipped_geography += 1
                continue
            if location_state == "ambiguous":
                skipped_ambiguous_geography += 1
                continue
        if not args.allow_nonaquatic and not aquatic_relevant(record):
            skipped_nonaquatic += 1
            continue
        media_dir = args.run_root / spec["media_dir"] / "media" / safe_component(content_id)
        files = sorted(
            path for path in media_dir.glob("*")
            if path.is_file() and path.suffix.lower() in MEDIA_SUFFIXES and not path.name.endswith(".part")
        )
        if not files:
            skipped_text_only += 1
            continue
        for index, source in enumerate(files, start=1):
            digest = sha256(source)
            if digest in known_hashes:
                continue
            name = (
                f"{stamp}_{safe_component(unit['place'])}_{args.platform}_"
                f"{safe_component(content_id)}_{index:02d}{source.suffix.lower()}"
            )
            target = collision_safe_target(destination / name, digest)
            place_file(source, target, args.mode)
            row = {
                "archive_path": target.as_posix(),
                "sha256": digest,
                "platform": args.platform,
                "region": unit["region"],
                "place": unit["place"],
                "unit_id": args.unit_id,
                "content_id": content_id,
                "media_index": str(index),
                "gallery_size": str(len(files)),
                "media_type": "video" if source.suffix.lower() in {".mp4", ".mov", ".m4v", ".webm"} else "image",
                "quality_flag": "large_gallery_review" if len(files) > 50 else "",
                "crawl_time": crawl_dt.isoformat(timespec="seconds"),
                "publish_time": publish_time,
                "source_keyword": record.get("source_keyword", ""),
                "source_url": record.get(spec["url"], ""),
            }
            added.append(row)
            known_hashes.add(digest)

    destination.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(existing + added)
    print(
        f"records={len(records)} media_added={len(added)} text_only_skipped={skipped_text_only} "
        f"out_of_period_skipped={skipped_out_of_period} "
        f"geography_skipped={skipped_geography} "
        f"ambiguous_geography_skipped={skipped_ambiguous_geography} "
        f"nonaquatic_skipped={skipped_nonaquatic} "
        f"manifest={manifest_path}"
    )


if __name__ == "__main__":
    main()
