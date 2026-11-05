#!/usr/bin/env python3
"""Download public Baidu Map POI albums and normalize them into the research schema."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


FIELDS = [
    "record_id", "platform", "query_keyword", "post_url", "content_text",
    "publish_time", "crawl_time", "media_type", "media_local_path",
    "media_sha256", "platform_poi_name", "platform_poi_address",
    "platform_lng", "platform_lat", "coordinate_system", "visual_location",
    "visual_location_confidence", "location_match_class", "vegetation_type",
    "growth_stage", "cover_grade", "phenology_confidence", "media_value", "review_status",
    "notes",
]


def stable_id(url: str) -> str:
    return hashlib.sha256(f"baidu:{url}".encode()).hexdigest()[:24]


def download(url: str, target: Path) -> tuple[Path, str]:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.stat().st_size:
        body = target.read_bytes()
        return target, hashlib.sha256(body).hexdigest()
    request = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 EastLakePhenologyResearch/1.0",
        "Referer": "https://ditu.baidu.com/",
    })
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read(25 * 1024 * 1024 + 1)
        content_type = response.headers.get_content_type()
    if len(body) > 25 * 1024 * 1024:
        raise ValueError("media exceeds 25 MiB safety limit")
    if not content_type.startswith("image/"):
        raise ValueError(f"unexpected content type: {content_type}")
    suffix = ".png" if content_type == "image/png" else ".webp" if content_type == "image/webp" else ".jpg"
    target = target.with_suffix(suffix)
    target.write_bytes(body)
    return target, hashlib.sha256(body).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def rebuild_all(processed: Path) -> int:
    rows: list[dict[str, str]] = []
    for path in sorted(processed.glob("*_posts.csv")):
        if path.name != "all_posts.csv":
            rows.extend(read_csv(path))
    by_key = {(row.get("platform"), row.get("post_url")): row for row in rows}
    merged = sorted(by_key.values(), key=lambda row: (row.get("platform", ""), row.get("publish_time", ""), row.get("record_id", "")))
    write_csv(processed / "all_posts.csv", merged)
    return len(merged)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    root = args.project_root.resolve()
    payload = json.loads(args.manifest.read_text(encoding="utf-8"))
    albums = payload["albums"]
    results: dict[str, list[tuple[int, Path, str]]] = {stable_id(a["post_url"]): [] for a in albums}
    errors: dict[str, int] = {stable_id(a["post_url"]): 0 for a in albums}
    jobs = {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for album in albums:
            rid = stable_id(album["post_url"])
            for index, url in enumerate(dict.fromkeys(album.get("media", [])), start=1):
                target = root / "media" / "baidu" / rid / f"{index:03d}.jpg"
                jobs[pool.submit(download, url, target)] = (rid, index)
        for future in as_completed(jobs):
            rid, index = jobs[future]
            try:
                path, digest = future.result()
                results[rid].append((index, path, digest))
            except Exception:
                errors[rid] += 1

    rows = []
    for album in albums:
        rid = stable_id(album["post_url"])
        saved = sorted(results[rid])
        primary = saved[0][1].relative_to(root).as_posix() if saved else ""
        digest = saved[0][2] if saved else ""
        rows.append({
            "record_id": rid,
            "platform": "baidu",
            "query_keyword": album["query_keyword"],
            "post_url": album["post_url"],
            "content_text": "百度地图公开地点相册。平台网页未显示单张照片的上传或拍摄时间，仅用于空间和植被画面核验。",
            "publish_time": "",
            "crawl_time": payload["crawl_time"],
            "media_type": "image_gallery" if saved else "none",
            "media_local_path": primary,
            "media_sha256": digest,
            "platform_poi_name": album["poi_name"],
            "platform_poi_address": album["poi_address"],
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
            "review_status": "candidate_unverified",
            "notes": f"time_precision=unknown; album_images_saved={len(saved)}; download_errors={errors[rid]}; public_album=true",
        })

    output = root / "data" / "processed" / "baidu_posts.csv"
    write_csv(output, rows)
    total = rebuild_all(root / "data" / "processed")
    print(json.dumps({
        "albums": len(rows),
        "images_saved": sum(len(value) for value in results.values()),
        "download_errors": sum(errors.values()),
        "all_total": total,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
