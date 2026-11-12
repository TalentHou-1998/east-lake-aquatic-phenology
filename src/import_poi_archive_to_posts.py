#!/usr/bin/env python3
"""Create map-ready post rows for archive records absent from all_posts.csv."""

from __future__ import annotations

import argparse
import csv
import hashlib
from pathlib import Path


STANDARD_FIELDS = [
    "record_id", "platform", "query_keyword", "post_url", "content_text",
    "publish_time", "crawl_time", "media_type", "media_local_path", "media_sha256",
    "platform_poi_name", "platform_poi_address", "platform_lng", "platform_lat",
    "coordinate_system", "visual_location", "visual_location_confidence",
    "location_match_class", "vegetation_type", "growth_stage", "cover_grade",
    "phenology_confidence", "media_value", "review_status", "notes", "media_paths",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--archive-index", type=Path, default=Path("media_by_poi/_归档索引.csv"))
    parser.add_argument("--existing", type=Path, default=Path("data/processed/all_posts.csv"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/archive_posts.csv"))
    args = parser.parse_args()
    root = args.project_root.resolve()
    index_path = args.archive_index if args.archive_index.is_absolute() else root / args.archive_index
    existing_path = args.existing if args.existing.is_absolute() else root / args.existing
    output_path = args.output if args.output.is_absolute() else root / args.output

    existing = read_csv(existing_path)
    existing_by_id = {row.get("record_id", ""): row for row in existing if row.get("record_id")}
    existing_by_url = {row.get("post_url", ""): row for row in existing if row.get("post_url")}

    grouped: dict[tuple[str, str, str], list[dict[str, str]]] = {}
    for row in read_csv(index_path):
        key = (row["platform"], row["content_id"], row["poi"])
        grouped.setdefault(key, []).append(row)

    output: list[dict[str, str]] = []
    for (platform, content_id, poi), media_rows in sorted(grouped.items()):
        first = media_rows[0]
        source_url = first.get("source_url", "")
        matched = existing_by_id.get(content_id) or existing_by_url.get(source_url)
        record_id = (
            matched.get("record_id", "")
            if matched
            else hashlib.sha256(f"{platform}|{content_id}|{poi}".encode()).hexdigest()[:24]
        )
        paths = [row["new_archive_path"] for row in sorted(media_rows, key=lambda x: int(x.get("media_index") or 0))]
        types = {row.get("media_type", "") for row in media_rows}
        row = {field: (matched or {}).get(field, "") for field in STANDARD_FIELDS}
        row.update(
            {
                "record_id": record_id,
                "platform": platform,
                "query_keyword": first.get("source_keyword", ""),
                "post_url": source_url,
                "content_text": (matched or {}).get("content_text", ""),
                "publish_time": first.get("publish_time", "") or (matched or {}).get("publish_time", ""),
                "crawl_time": first.get("crawl_time", "") or (matched or {}).get("crawl_time", ""),
                "media_type": "mixed" if len(types) > 1 else (next(iter(types)) if types else "media"),
                "media_local_path": paths[0],
                "media_sha256": first.get("sha256", ""),
                "platform_poi_name": (matched or {}).get("platform_poi_name", "") or poi,
                "coordinate_system": (matched or {}).get("coordinate_system", "") or "unknown",
                "visual_location_confidence": (matched or {}).get("visual_location_confidence", "") or "unknown",
                "location_match_class": (matched or {}).get("location_match_class", "") or "unknown",
                "growth_stage": (matched or {}).get("growth_stage", "") or "unknown",
                "cover_grade": (matched or {}).get("cover_grade", "") or "unknown",
                "phenology_confidence": (matched or {}).get("phenology_confidence", "") or "unknown",
                "media_value": (matched or {}).get("media_value", "") or "unknown",
                "review_status": (matched or {}).get("review_status", "") or "candidate_unverified",
                "notes": (matched or {}).get("notes", "") or "archive_media_only; text_not_collected; location_requires_manual_verification",
                "media_paths": "|".join(paths),
            }
        )
        output.append(row)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=STANDARD_FIELDS)
        writer.writeheader()
        writer.writerows(output)
    print(f"archive_posts={len(output)} matched_existing={sum(row['record_id'] in existing_by_id for row in output)} output={output_path}")


if __name__ == "__main__":
    main()
