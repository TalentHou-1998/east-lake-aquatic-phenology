#!/usr/bin/env python3
"""Normalize browser-harvested Amap reviews and save their observed photos."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import mimetypes
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen


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


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def record_id(source: dict) -> str:
    identity = "\n".join(
        [source.get("platform_poi_name", ""), source.get("time", ""), source.get("text", "")]
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]


def canonical_poi_url(source_url: str, rid: str) -> str:
    query = parse_qs(urlsplit(source_url).query)
    params = {key: query[key][0] for key in ("id", "name") if query.get(key)}
    return f"https://www.amap.com/ssr/search/poi_detail?{urlencode(params)}#review-{rid}"


def download(url: str, retries: int = 2) -> tuple[bytes, str]:
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Referer": "https://www.amap.com/",
        },
    )
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            with urlopen(request, timeout=30) as response:
                return response.read(), response.headers.get_content_type()
        except (HTTPError, URLError, TimeoutError) as error:
            last_error = error
            if attempt < retries:
                time.sleep(1.0 + attempt)
    raise RuntimeError(f"download failed: {url}: {last_error}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--media-root", required=True, type=Path)
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--delay", type=float, default=0.08)
    args = parser.parse_args()

    sources = json.loads(args.input.read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.media_root.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, str]] = []
    downloaded = 0
    failed = 0
    for source in sources:
        rid = record_id(source)
        item_dir = args.media_root / rid
        item_dir.mkdir(parents=True, exist_ok=True)
        saved: list[Path] = []
        for index, image_url in enumerate(source.get("image_urls") or [], start=1):
            existing = next(item_dir.glob(f"{index:03d}.*"), None)
            if existing:
                saved.append(existing)
                continue
            try:
                data, content_type = download(image_url)
                suffix = mimetypes.guess_extension(content_type) or ".jpg"
                if suffix == ".jpe":
                    suffix = ".jpg"
                target = item_dir / f"{index:03d}{suffix}"
                target.write_bytes(data)
                saved.append(target)
                downloaded += 1
            except RuntimeError as error:
                print(error)
                failed += 1
            time.sleep(args.delay)

        primary = saved[0] if saved else None
        notes = [
            "time_precision=date",
            f"observed_image_urls={len(source.get('image_urls') or [])}",
            f"platform_image_count={source.get('image_count', len(source.get('image_urls') or []))}",
        ]
        if len(saved) > 1:
            notes.append(f"gallery_images_saved={len(saved)}")
        rows.append(
            {
                "record_id": rid,
                "platform": "amap",
                "query_keyword": source.get("query_keyword", ""),
                "post_url": canonical_poi_url(source.get("source_url", ""), rid),
                "content_text": source.get("text", ""),
                "publish_time": source.get("time", ""),
                "crawl_time": source.get("observed_at", ""),
                "media_type": "image",
                "media_local_path": primary.relative_to(args.project_root).as_posix() if primary else "",
                "media_sha256": digest_bytes(primary.read_bytes()) if primary else "",
                "platform_poi_name": source.get("platform_poi_name", ""),
                "platform_poi_address": source.get("platform_poi_address", ""),
                "platform_lng": "",
                "platform_lat": "",
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
                "notes": "; ".join(notes),
            }
        )

    with args.output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"rows={len(rows)} downloaded={downloaded} failed={failed} output={args.output}")


if __name__ == "__main__":
    main()
