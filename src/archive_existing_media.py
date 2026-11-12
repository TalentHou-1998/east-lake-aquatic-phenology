#!/usr/bin/env python3
"""Re-index existing local media into the region/place archive without text fields."""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import re
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


MEDIA_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4", ".mov", ".m4v", ".webm"}
FIELDS = [
    "archive_path", "sha256", "platform", "region", "place", "unit_id", "content_id",
    "media_index", "gallery_size", "media_type", "quality_flag", "crawl_time", "publish_time",
    "source_keyword", "source_url",
]


def safe(value: str) -> str:
    return (re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "_", value).strip(" .")[:100] or "unknown")


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def stamp(value: str) -> str:
    if value:
        normalized = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized).strftime("%Y%m%dT%H%M%S")
        except ValueError:
            digits = re.sub(r"\D", "", value)
            if len(digits) >= 8:
                return f"{digits[:8]}T{(digits[8:14] + '000000')[:6]}"
    return datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%dT%H%M%S")


def load_units(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def choose_unit(row: dict[str, str], units: list[dict[str, str]]) -> dict[str, str]:
    haystack = " ".join(
        row.get(field, "")
        for field in ("platform_poi_name", "platform_poi_address", "query_keyword", "visual_location", "content_text")
    )
    matches: list[tuple[int, dict[str, str]]] = []
    for unit in units:
        for alias in unit["aliases"].split("|"):
            if alias and alias in haystack:
                matches.append((len(alias), unit))
    if matches:
        return max(matches, key=lambda item: item[0])[1]
    return {
        "unit_id": "EL00",
        "region": "武汉东湖及周边",
        "place": "东湖—待核验地点",
        "aliases": "",
    }


def media_files(root: Path, row: dict[str, str]) -> list[Path]:
    relative = row.get("media_local_path", "").strip()
    if not relative:
        return []
    primary = root / relative
    if not primary.is_file():
        return []
    siblings = [
        path for path in primary.parent.iterdir()
        if path.is_file() and path.suffix.lower() in MEDIA_SUFFIXES and not path.name.endswith(".part")
    ]
    return sorted(siblings) or [primary]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument("--input", type=Path, default=Path("data/processed/all_posts.csv"))
    parser.add_argument("--units", type=Path, default=Path("config/east_lake_spatial_units.csv"))
    parser.add_argument("--archive-root", type=Path, default=Path("media_collected"))
    parser.add_argument("--mode", choices=("hardlink", "copy"), default="hardlink")
    args = parser.parse_args()

    root = args.project_root.resolve()
    input_path = root / args.input
    units = load_units(root / args.units)
    with input_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    archive_base = root / args.archive_root
    preexisting: dict[Path, list[dict[str, str]]] = {}
    seen: set[tuple[str, str]] = set()
    for manifest in archive_base.rglob("media_manifest.csv") if archive_base.exists() else []:
        with manifest.open(encoding="utf-8-sig", newline="") as handle:
            preexisting[manifest] = list(csv.DictReader(handle))
        seen.update((str(manifest), row.get("sha256", "")) for row in preexisting[manifest])

    output_rows: dict[Path, list[dict[str, str]]] = defaultdict(list)
    copied = 0
    missing_media = 0
    for row in rows:
        files = media_files(root, row)
        if not files:
            missing_media += 1
            continue
        unit = choose_unit(row, units)
        platform = safe(row.get("platform", "unknown"))
        place_dir = root / args.archive_root / safe(unit["region"]) / safe(unit["place"])
        destination = place_dir / platform
        manifest = place_dir / "media_manifest.csv"
        content_id = row.get("record_id", "") or hashlib.sha256(row.get("post_url", "").encode()).hexdigest()[:16]
        collection_stamp = stamp(row.get("crawl_time", ""))
        for index, source in enumerate(files, start=1):
            file_digest = digest(source)
            dedupe_key = (str(manifest), file_digest)
            if dedupe_key in seen:
                continue
            filename = (
                f"{collection_stamp}_{safe(unit['place'])}_{platform}_"
                f"{safe(content_id)}_{index:02d}{source.suffix.lower()}"
            )
            target = destination / filename
            if target.exists() and digest(target) != file_digest:
                target = target.with_name(f"{target.stem}_{file_digest[:8]}{target.suffix}")
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                if args.mode == "copy":
                    shutil.copy2(source, target)
                else:
                    try:
                        os.link(source, target)
                    except OSError:
                        shutil.copy2(source, target)
                copied += 1
            output_rows[manifest].append(
                {
                    "archive_path": target.relative_to(root).as_posix(),
                    "sha256": file_digest,
                    "platform": platform,
                    "region": unit["region"],
                    "place": unit["place"],
                    "unit_id": unit["unit_id"],
                    "content_id": content_id,
                    "media_index": str(index),
                    "gallery_size": str(len(files)),
                    "media_type": "video" if source.suffix.lower() in {".mp4", ".mov", ".m4v", ".webm"} else "image",
                    "quality_flag": "large_gallery_review" if len(files) > 50 else "",
                    "crawl_time": row.get("crawl_time", ""),
                    "publish_time": row.get("publish_time", ""),
                    "source_keyword": row.get("query_keyword", ""),
                    "source_url": row.get("post_url", ""),
                }
            )
            seen.add(dedupe_key)

    for manifest in set(preexisting) | set(output_rows):
        combined = preexisting.get(manifest, []) + output_rows.get(manifest, [])
        manifest_rows = list({row.get("sha256", ""): row for row in combined}.values())
        manifest.parent.mkdir(parents=True, exist_ok=True)
        with manifest.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(manifest_rows)

    print(
        f"records={len(rows)} archived_files={len(seen)} newly_linked_or_copied={copied} "
        f"records_without_local_media={missing_media} places={len(output_rows)}"
    )


if __name__ == "__main__":
    main()
