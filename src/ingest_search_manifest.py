#!/usr/bin/env python3
"""Normalize a reviewed public-search manifest into the project dataset schema."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import mimetypes
import os
import shutil
import urllib.request
from pathlib import Path


FIELDS = [
    "record_id", "platform", "query_keyword", "post_url", "content_text",
    "publish_time", "crawl_time", "media_type", "media_local_path",
    "media_sha256", "platform_poi_name", "platform_poi_address",
    "platform_lng", "platform_lat", "coordinate_system", "visual_location",
    "visual_location_confidence", "location_match_class", "vegetation_type",
    "growth_stage", "cover_grade", "phenology_confidence", "media_value", "review_status",
    "notes", "media_paths",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def download(url: str, destination: Path) -> tuple[Path, str]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 EastLakePhenologyResearch/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        content_type = response.headers.get_content_type()
        body = response.read(25 * 1024 * 1024 + 1)
    if len(body) > 25 * 1024 * 1024:
        raise ValueError("media exceeds 25 MiB safety limit")
    suffix = mimetypes.guess_extension(content_type) or destination.suffix or ".jpg"
    destination = destination.with_suffix(suffix)
    destination.write_bytes(body)
    return destination, hashlib.sha256(body).hexdigest()


def local_media(source: Path, destination: Path) -> tuple[Path, str]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination = destination.with_suffix(source.suffix.lower() or ".media")
    if not destination.exists():
        try:
            os.link(source, destination)
        except OSError:
            shutil.copy2(source, destination)
    return destination, hashlib.sha256(destination.read_bytes()).hexdigest()


def record_id(platform: str, source_id: str) -> str:
    return hashlib.sha256(f"{platform}:{source_id}".encode()).hexdigest()[:24]


def normalize(manifest_path: Path, project_root: Path, download_media: bool) -> tuple[str, list[dict[str, str]]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    platform = manifest["platform"]
    rows: list[dict[str, str]] = []
    for item in manifest["records"]:
        if item.get("relevance_level") == "reject":
            continue
        source_id = item.get("photo_id") or item.get("post_id") or item["post_url"]
        rid = record_id(platform, source_id)
        saved_media: list[Path] = []
        digests: list[str] = []
        media_urls = item.get("media_urls") or []
        if item.get("cover_url") and item["cover_url"] not in media_urls:
            media_urls = [item["cover_url"], *media_urls]
        local_paths = item.get("local_media_paths") or []
        if download_media:
            for index, url in enumerate(media_urls, start=1):
                try:
                    saved, digest = download(
                        url,
                        project_root / "media" / platform / rid / f"{index:03d}.media",
                    )
                    saved_media.append(saved)
                    digests.append(digest)
                except Exception as error:  # retain metadata even if a CDN expires
                    item.setdefault("download_errors", []).append(
                        f"{type(error).__name__}: {error}"
                    )
            offset = len(saved_media)
            for index, value in enumerate(local_paths, start=1):
                source = Path(value).expanduser()
                if not source.is_absolute():
                    source = manifest_path.parent / source
                try:
                    saved, digest = local_media(
                        source.resolve(),
                        project_root / "media" / platform / rid / f"{offset + index:03d}{source.suffix}",
                    )
                    saved_media.append(saved)
                    digests.append(digest)
                except Exception as error:
                    item.setdefault("download_errors", []).append(
                        f"{type(error).__name__}: {error}"
                    )
        relative_media = [path.relative_to(project_root).as_posix() for path in saved_media]
        notes = [
            f"like_count={item.get('like_count', '')}",
            f"relevance={item.get('relevance_level', 'unknown')}",
            f"relevance_reason={item.get('relevance_reason', '')}",
            f"time_source={manifest.get('time_source', 'platform')}",
            f"time_precision={item.get('time_precision', manifest.get('time_precision', 'unknown'))}",
        ]
        if not any(item.get(field) for field in ("platform_poi_name", "platform_poi_address", "platform_lng", "platform_lat")):
            notes.append("platform_location_absent")
        if item.get("download_errors"):
            notes.append(f"download_errors={len(item['download_errors'])}")
        rows.append({
            "record_id": rid,
            "platform": platform,
            "query_keyword": manifest.get("query_keyword", ""),
            "post_url": item.get("post_url", ""),
            "content_text": item.get("content_text", ""),
            "publish_time": item.get("publish_time", ""),
            "crawl_time": manifest.get("crawl_time", ""),
            "media_type": item.get("media_type", "unknown"),
            "media_local_path": relative_media[0] if relative_media else "",
            "media_paths": "|".join(relative_media),
            "media_sha256": "|".join(digests),
            "platform_poi_name": item.get("platform_poi_name", ""),
            "platform_poi_address": item.get("platform_poi_address", ""),
            "platform_lng": item.get("platform_lng", ""),
            "platform_lat": item.get("platform_lat", ""),
            "coordinate_system": item.get("coordinate_system", "unknown"),
            "visual_location": "",
            "visual_location_confidence": "unknown",
            "location_match_class": "unknown",
            "vegetation_type": "",
            "growth_stage": "unknown",
            "cover_grade": "unknown",
            "phenology_confidence": "unknown",
            "media_value": "unknown",
            "review_status": "candidate_unverified",
            "notes": "; ".join(notes),
        })
    return platform, rows


def merge_rows(existing: list[dict[str, str]], incoming: list[dict[str, str]]) -> list[dict[str, str]]:
    by_key = {(row.get("platform"), row.get("post_url")): row for row in existing}
    for row in incoming:
        by_key[(row.get("platform"), row.get("post_url"))] = row
    return sorted(by_key.values(), key=lambda row: (row.get("platform", ""), row.get("publish_time", ""), row.get("record_id", "")))


def rebuild_all(processed_dir: Path) -> int:
    rows: list[dict[str, str]] = []
    for path in sorted(processed_dir.glob("*_posts.csv")):
        if path.name != "all_posts.csv":
            rows.extend(read_csv(path))
    rows = merge_rows([], rows)
    write_csv(processed_dir / "all_posts.csv", rows)
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--download-media", action="store_true")
    args = parser.parse_args()

    root = args.project_root.resolve()
    platform, incoming = normalize(args.manifest.resolve(), root, args.download_media)
    output = root / "data" / "processed" / f"{platform}_posts.csv"
    merged = merge_rows(read_csv(output), incoming)
    write_csv(output, merged)
    total = rebuild_all(root / "data" / "processed")
    print(json.dumps({"platform": platform, "accepted": len(incoming), "platform_total": len(merged), "all_total": total}, ensure_ascii=False))


if __name__ == "__main__":
    main()
