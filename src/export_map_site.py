#!/usr/bin/env python3
"""Export the research CSVs and media into a privacy-preserving static map bundle."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
import json
import math
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import quote


POI_COORDS_GCJ02 = {
    "东湖生态旅游风景区": (114.408432, 30.551802),
    "东湖听涛景区": (114.369919, 30.570279),
    "东湖听涛风景区": (114.369919, 30.570279),
    "东湖磨山景区": (114.407612, 30.550732),
    "磨山景区": (114.407612, 30.550732),
    "落雁景区": (114.470750, 30.561878),
    "东湖荷园": (114.407612, 30.551031),
    "东湖绿道": (114.405107, 30.576904),
    "东湖风景区（综合）": (114.408432, 30.551802),
    "东湖华侨城—欢乐谷片区": (114.395000, 30.615000),
    "东湖白马景区": (114.419581, 30.600659),
    "东湖落雁景区": (114.430750, 30.561878),
    "东湖南岸—武汉水生所": (114.431000, 30.514000),
    "马鞍山森林公园": (114.472000, 30.515000),
    "武汉植物园": (114.421000, 30.536000),
    "东湖绿道湖中道": (114.390500, 30.558000),
    "楚风园—梨园": (114.373166, 30.579660),
    "筲箕湖—华侨城岸段": (114.388900, 30.607200),
    "汤菱湖—欢乐谷岸段": (114.401000, 30.624000),
    "白马—桃花岛": (114.419581, 30.600659),
    "团湖—团子山岸段": (114.449000, 30.585000),
    "落雁景区—晨雁岛": (114.430750, 30.561878),
    "后湖—青王路岸段": (114.462000, 30.578000),
    "磨山梅园—荷园": (114.402514, 30.544318),
    "水生所—官桥湖岸段": (114.431000, 30.514000),
    "听涛南段—荷花塘": (114.369919, 30.570279),
    "马鞍山森林公园—吹笛景区": (114.472000, 30.515000),
    "武汉植物园—鲁磨路岸段": (114.421000, 30.536000),
    "渔光景区—湖中道": (114.390500, 30.558000),
    "喻家山—喻家湖": (114.443000, 30.513000),
    "东湖—待核验地点": (114.408432, 30.551802),
}


def transform_lat(x: float, y: float) -> float:
    value = -100 + 2 * x + 3 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    value += (20 * math.sin(6 * x * math.pi) + 20 * math.sin(2 * x * math.pi)) * 2 / 3
    value += (20 * math.sin(y * math.pi) + 40 * math.sin(y / 3 * math.pi)) * 2 / 3
    value += (160 * math.sin(y / 12 * math.pi) + 320 * math.sin(y * math.pi / 30)) * 2 / 3
    return value


def transform_lng(x: float, y: float) -> float:
    value = 300 + x + 2 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    value += (20 * math.sin(6 * x * math.pi) + 20 * math.sin(2 * x * math.pi)) * 2 / 3
    value += (20 * math.sin(x * math.pi) + 40 * math.sin(x / 3 * math.pi)) * 2 / 3
    value += (150 * math.sin(x / 12 * math.pi) + 300 * math.sin(x / 30 * math.pi)) * 2 / 3
    return value


def gcj02_to_wgs84(lng: float, lat: float) -> tuple[float, float]:
    a = 6378245.0
    ee = 0.006693421622965943
    dlat = transform_lat(lng - 105.0, lat - 35.0)
    dlng = transform_lng(lng - 105.0, lat - 35.0)
    radlat = lat / 180.0 * math.pi
    magic = math.sin(radlat)
    magic = 1 - ee * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((a * (1 - ee)) / (magic * sqrtmagic) * math.pi)
    dlng = (dlng * 180.0) / (a / sqrtmagic * math.cos(radlat) * math.pi)
    return lng * 2 - (lng + dlng), lat * 2 - (lat + dlat)


def fallback_coordinate(row: dict[str, str]) -> tuple[float, float, str]:
    poi = row.get("platform_poi_name", "")
    if poi in POI_COORDS_GCJ02:
        lng, lat = POI_COORDS_GCJ02[poi]
        return lng, lat, "poi_estimated"
    blob = " ".join(
        [
            poi,
            row.get("platform_poi_address", ""),
            row.get("query_keyword", ""),
            row.get("visual_location", ""),
        ]
    )
    for term, key in (
        ("听涛", "东湖听涛景区"),
        ("落雁", "落雁景区"),
        ("白马", "东湖绿道"),
        ("荷园", "东湖荷园"),
        ("荷塘", "东湖荷园"),
        ("磨山", "东湖磨山景区"),
        ("绿道", "东湖绿道"),
    ):
        if term in blob:
            lng, lat = POI_COORDS_GCJ02[key]
            return lng, lat, "poi_estimated"
    lng, lat = POI_COORDS_GCJ02["东湖生态旅游风景区"]
    return lng, lat, "regional_centroid"


def media_sources(project_root: Path, row: dict[str, str]) -> list[Path]:
    explicit_paths = [item.strip() for item in row.get("media_paths", "").split("|") if item.strip()]
    if explicit_paths:
        return [project_root / item for item in explicit_paths if (project_root / item).is_file()]
    local_path = row.get("media_local_path", "")
    if not local_path:
        return []
    primary = project_root / local_path
    if not primary.exists():
        return []
    siblings = sorted(path for path in primary.parent.iterdir() if path.is_file())
    return siblings if row["platform"] in {"amap", "weibo", "baidu"} else [primary]


def hierarchy_aliases(path: Path) -> tuple[set[str], list[tuple[str, str]]]:
    broad_names: set[str] = set()
    aliases: set[tuple[str, str]] = set()
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        broad = row["broad_poi"]
        broad_names.add(broad)
        values = [broad, *row["search_anchors"].split("|"), *row["match_aliases"].split("|")]
        aliases.update((value, broad) for value in values if value)
    return broad_names, sorted(aliases, key=lambda item: len(item[0]), reverse=True)


def broad_poi(row: dict[str, str], broad_names: set[str], aliases: list[tuple[str, str]]) -> str:
    archived = row.get("archive_poi", "").strip()
    if archived:
        return archived
    original = row.get("platform_poi_name", "").strip()
    if original in broad_names:
        return original
    evidence = " ".join(
        [original, row.get("platform_poi_address", ""), row.get("query_keyword", ""), row.get("visual_location", "")]
    )
    scores: dict[str, int] = {}
    for alias, broad in aliases:
        if alias in evidence:
            scores[broad] = max(scores.get(broad, 0), len(alias))
    if scores:
        best = max(scores.values())
        winners = [poi for poi, score in scores.items() if score == best]
        if len(winners) == 1:
            return winners[0]
    return "东湖风景区（综合）"


def compress_image(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.stat().st_mtime >= source.stat().st_mtime:
        return
    subprocess.run(
        [
            "magick",
            str(source),
            "-auto-orient",
            "-resize",
            "1400x1400>",
            "-strip",
            "-quality",
            "70",
            str(target),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def video_poster(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.stat().st_mtime >= source.stat().st_mtime:
        return
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temporary:
        poster = Path(temporary.name)
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-ss", "00:00:01", "-i", str(source),
                "-frames:v", "1", "-vf", "scale='min(1600,iw)':-2", str(poster),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        compress_image(poster, target)
    finally:
        poster.unlink(missing_ok=True)


def export_media(source: Path, target: Path) -> None:
    if source.suffix.lower() in {".mp4", ".mov", ".m4v", ".webm"}:
        video_poster(source, target)
    else:
        compress_image(source, target)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--site-dist", required=True, type=Path)
    args = parser.parse_args()

    data_dir = args.project_root / "data" / "processed"
    broad_names, broad_aliases = hierarchy_aliases(args.project_root / "config" / "east_lake_poi_hierarchy.csv")
    output_data = args.site_dist / "data"
    output_media = args.site_dist / "assets" / "media"
    output_data.mkdir(parents=True, exist_ok=True)
    output_media.mkdir(parents=True, exist_ok=True)

    platform_files = [data_dir / "all_posts.csv"]
    archive_posts = data_dir / "archive_posts.csv"
    if archive_posts.exists():
        platform_files.append(archive_posts)
    combined_rows: dict[str, dict[str, str]] = {}
    for platform_path in platform_files:
        with platform_path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        for row in rows:
            combined_rows[row["record_id"]] = row

    points: list[dict] = []
    for row in combined_rows.values():
        platform = row.get("platform", "unknown") or "unknown"
        broad_name = broad_poi(row, broad_names, broad_aliases)
        if row.get("platform_lng") and row.get("platform_lat"):
            gcj_lng = float(row["platform_lng"])
            gcj_lat = float(row["platform_lat"])
            coordinate_precision = "platform_observed_unknown_crs"
        else:
            coordinate_row = {**row, "platform_poi_name": broad_name}
            gcj_lng, gcj_lat, coordinate_precision = fallback_coordinate(coordinate_row)
        wgs_lng, wgs_lat = gcj02_to_wgs84(gcj_lng, gcj_lat)

        media: list[str] = []
        for index, source in enumerate(media_sources(args.project_root, row), start=1):
            target = output_media / platform / row["record_id"] / f"{index:02d}.webp"
            export_media(source, target)
            media.append(target.relative_to(args.site_dist).as_posix())

        publish_time = row.get("publish_time", "").strip()
        point = {
            "id": row["record_id"],
            "platform": platform,
            "queryKeyword": row["query_keyword"],
            "postUrl": row["post_url"],
            "text": row["content_text"],
            "publishTime": publish_time or "平台未提供",
            "year": int(publish_time[:4]) if re.match(r"^20\d{2}", publish_time) else None,
            "timeKnown": bool(publish_time),
            "media": media or ["assets/no-media.svg"],
            "mediaType": row["media_type"],
            "broadPoi": broad_name,
            "poiName": row["platform_poi_name"] or "未提供",
            "poiAddress": row["platform_poi_address"] or "未提供",
            "originalLng": row["platform_lng"] or None,
            "originalLat": row["platform_lat"] or None,
            "coordinatePrecision": coordinate_precision,
            "coordinateAssumption": "GCJ-02 assumed; converted to WGS84 for Baidu CRS rendering",
            "lng": round(wgs_lng, 7),
            "lat": round(wgs_lat, 7),
            "visualLocation": row["visual_location"] or "尚未判断",
            "visualLocationConfidence": row["visual_location_confidence"],
            "locationMatchClass": row["location_match_class"],
            "vegetationType": row["vegetation_type"] or "未识别",
            "growthStage": row["growth_stage"],
            "coverGrade": row["cover_grade"],
            "phenologyConfidence": row["phenology_confidence"],
            "mediaValue": row.get("media_value", "unknown") or "unknown",
            "reviewStatus": row["review_status"],
            "notes": row["notes"],
        }
        points.append(point)

    (output_data / "points.json").write_text(
        json.dumps(points, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    platforms = sorted({point["platform"] for point in points})
    summary = {
        "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "total": len(points),
        "platforms": {platform: sum(point["platform"] == platform for point in points) for platform in platforms},
        "platformObservedCoordinates": sum(point["coordinatePrecision"] == "platform_observed_unknown_crs" for point in points),
        "estimatedCoordinates": sum(point["coordinatePrecision"] != "platform_observed_unknown_crs" for point in points),
        "unknownPublishTime": sum(not point["timeKnown"] for point in points),
        "preannotated": sum(point["reviewStatus"] == "preannotated_primary" for point in points),
    }
    (output_data / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
