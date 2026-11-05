#!/usr/bin/env python3
"""Normalize and download a reviewed Weibo search export for East Lake research."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


FIELDS = [
    "record_id", "platform", "query_keyword", "post_url", "content_text",
    "publish_time", "crawl_time", "media_type", "media_local_path",
    "media_sha256", "platform_poi_name", "platform_poi_address",
    "platform_lng", "platform_lat", "coordinate_system", "visual_location",
    "visual_location_confidence", "location_match_class", "vegetation_type",
    "growth_stage", "cover_grade", "phenology_confidence", "media_value", "review_status",
    "notes",
]

REGION_RE = re.compile(r"东湖|听涛|磨山|落雁|荷园|东湖南路|东湖植物园")
VEGETATION_RE = re.compile(r"荷花|荷叶|荷塘|荷池|莲花|莲叶|睡莲|芦苇|水草|浮萍|菱角|菖蒲|水生植")


def parse_time(raw: str, crawled_at: datetime) -> datetime | None:
    raw = raw.strip()
    match = re.search(r"(20\d{2})年(\d{2})月(\d{2})日\s+(\d{2}):(\d{2})", raw)
    if match:
        return datetime(*map(int, match.groups()), tzinfo=crawled_at.tzinfo)
    match = re.search(r"(\d{2})月(\d{2})日\s+(\d{2}):(\d{2})", raw)
    if match:
        month, day, hour, minute = map(int, match.groups())
        return datetime(crawled_at.year, month, day, hour, minute, tzinfo=crawled_at.tzinfo)
    match = re.search(r"今天\s*(\d{2}):(\d{2})", raw)
    if match:
        hour, minute = map(int, match.groups())
        return crawled_at.replace(hour=hour, minute=minute, second=0, microsecond=0)
    match = re.search(r"昨天\s*(\d{2}):(\d{2})", raw)
    if match:
        hour, minute = map(int, match.groups())
        return (crawled_at - timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    match = re.search(r"(\d+)分钟前", raw)
    if match:
        return crawled_at - timedelta(minutes=int(match.group(1)))
    match = re.search(r"(\d+)小时前", raw)
    if match:
        return crawled_at - timedelta(hours=int(match.group(1)))
    if "刚刚" in raw:
        return crawled_at
    return None


def clean_text(text: str) -> str:
    text = text.replace("\u200b", "").replace("收起d", "").strip()
    return re.sub(r"\n{3,}", "\n\n", text)


def classify(text: str, location: str) -> tuple[str, str]:
    blob = f"{text} {location}"
    if REGION_RE.search(blob) and VEGETATION_RE.search(text):
        if re.search(r"像.{0,12}(东湖.{0,6})?荷花", text) and not location:
            return "weak", "疑似比喻性提及，需人工确认画面与地点"
        return "strong", "正文同时包含东湖区域与水生植被证据"
    if REGION_RE.search(blob):
        return "weak", "具有东湖区域证据，但正文缺少明确水生植被词"
    return "reject", "缺少东湖区域证据"


def sha_record(post_url: str) -> str:
    return hashlib.sha256(f"weibo:{post_url}".encode()).hexdigest()[:24]


def download_one(url: str, target: Path) -> tuple[Path, str]:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.stat().st_size:
        body = target.read_bytes()
        return target, hashlib.sha256(body).hexdigest()
    request = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 EastLakePhenologyResearch/1.0",
        "Referer": "https://weibo.com/",
    })
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read(25 * 1024 * 1024 + 1)
        content_type = response.headers.get_content_type()
    if len(body) > 25 * 1024 * 1024:
        raise ValueError("media exceeds 25 MiB safety limit")
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


def merge(existing: list[dict[str, str]], incoming: list[dict[str, str]]) -> list[dict[str, str]]:
    by_url = {(row.get("platform"), row.get("post_url")): row for row in existing}
    for row in incoming:
        by_url[(row.get("platform"), row.get("post_url"))] = row
    return sorted(by_url.values(), key=lambda row: (row.get("platform", ""), row.get("publish_time", ""), row.get("record_id", "")))


def rebuild_all(processed: Path) -> int:
    rows: list[dict[str, str]] = []
    for path in sorted(processed.glob("*_posts.csv")):
        if path.name != "all_posts.csv":
            rows.extend(read_csv(path))
    rows = merge([], rows)
    write_csv(processed / "all_posts.csv", rows)
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--start", default="2018-01-01")
    parser.add_argument("--end", default="2026-10-30")
    parser.add_argument("--max-media-per-post", type=int, default=3)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    root = args.project_root.resolve()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    crawled_at = datetime.fromisoformat(manifest["crawl_time"])
    if crawled_at.tzinfo is None:
        crawled_at = crawled_at.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
    start = datetime.fromisoformat(args.start).date()
    end = datetime.fromisoformat(args.end).date()

    candidates: list[dict] = []
    stats = {"raw": 0, "reject_relevance": 0, "reject_time": 0, "strong": 0, "weak": 0}
    for item in manifest["records"]:
        stats["raw"] += 1
        text = clean_text(item.get("text", ""))
        location = item.get("locationText", "").strip()
        relevance, reason = classify(text, location)
        if relevance == "reject":
            stats["reject_relevance"] += 1
            continue
        published = parse_time(item.get("timeText", ""), crawled_at)
        if published is None or not (start <= published.date() <= end):
            stats["reject_time"] += 1
            continue
        stats[relevance] += 1
        item = dict(item)
        item.update({
            "text": text,
            "locationText": location,
            "relevance": relevance,
            "relevance_reason": reason,
            "published": published,
            "record_id": sha_record(item["postUrl"]),
        })
        candidates.append(item)

    jobs: dict = {}
    media_results: dict[str, list[tuple[Path, str]]] = {item["record_id"]: [] for item in candidates}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for item in candidates:
            for index, url in enumerate(item.get("media", [])[: args.max_media_per_post], start=1):
                target = root / "media" / "weibo" / item["record_id"] / f"{index:03d}.jpg"
                jobs[pool.submit(download_one, url, target)] = (item["record_id"], index)
        for future in as_completed(jobs):
            rid, index = jobs[future]
            try:
                path, digest = future.result()
                media_results[rid].append((path, digest))
            except Exception as error:
                media_results[rid].append((Path(f"ERROR:{type(error).__name__}:{error}"), ""))

    rows: list[dict[str, str]] = []
    for item in candidates:
        results = sorted(media_results[item["record_id"]], key=lambda value: value[0].as_posix())
        good = [(path, digest) for path, digest in results if not path.as_posix().startswith("ERROR:")]
        errors = [path.as_posix() for path, _ in results if path.as_posix().startswith("ERROR:")]
        primary = good[0][0].relative_to(root).as_posix() if good else ""
        primary_hash = good[0][1] if good else ""
        location = item["locationText"]
        has_video = "微博视频" in item["text"] or "视频号" in item["text"]
        notes = [
            f"raw_time={item.get('timeText', '')}",
            f"time_precision=minute",
            f"relevance={item['relevance']}",
            f"relevance_reason={item['relevance_reason']}",
            f"location_url={item.get('locationUrl', '')}",
            f"observed_media_urls={len(item.get('media', []))}",
            f"gallery_images_saved={len(good)}",
        ]
        if errors:
            notes.append(f"download_errors={len(errors)}")
        rows.append({
            "record_id": item["record_id"],
            "platform": "weibo",
            "query_keyword": manifest["query_keyword"],
            "post_url": item["postUrl"],
            "content_text": item["text"],
            "publish_time": item["published"].strftime("%Y-%m-%d %H:%M:%S"),
            "crawl_time": manifest["crawl_time"],
            "media_type": "image" if good else "video_link" if has_video else "none",
            "media_local_path": primary,
            "media_sha256": primary_hash,
            "platform_poi_name": location or "东湖（正文提及，未提供平台定位）",
            "platform_poi_address": "",
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
            "notes": "; ".join(notes),
        })

    output = root / "data" / "processed" / "weibo_posts.csv"
    merged = merge(read_csv(output), rows)
    write_csv(output, merged)
    total = rebuild_all(root / "data" / "processed")
    stats.update({
        "accepted": len(rows),
        "with_media": sum(bool(row["media_local_path"]) for row in rows),
        "media_files": sum(len([p for p in (root / "media" / "weibo" / row["record_id"]).glob("*") if p.is_file()]) for row in rows),
        "platform_total": len(merged),
        "all_total": total,
    })
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
