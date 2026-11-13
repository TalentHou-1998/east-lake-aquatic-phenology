#!/usr/bin/env python3
"""Promote evidence-backed MediaCrawler candidates into all_posts.csv."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--candidates", type=Path, default=Path("data/interim/media_run_posts.csv"))
    parser.add_argument("--evidence", type=Path, default=Path("data/interim/media_run_location_evidence.csv"))
    parser.add_argument("--existing", type=Path, default=Path("data/processed/all_posts.csv"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/all_posts.csv"))
    args = parser.parse_args()

    root = args.project_root.resolve()
    resolve = lambda path: path if path.is_absolute() else root / path
    candidates_path, evidence_path, existing_path, output_path = map(
        resolve, (args.candidates, args.evidence, args.existing, args.output)
    )
    candidates = read_csv(candidates_path)
    evidence = {row["record_id"]: row for row in read_csv(evidence_path)}
    existing = read_csv(existing_path)
    fields = list(existing[0]) if existing else list(candidates[0])

    accepted: list[dict[str, str]] = []
    rejected: list[dict[str, str]] = []
    for row in candidates:
        ev = evidence.get(row["record_id"], {})
        collected = "archive_scope=media_collected" in row.get("notes", "")
        sources = set(filter(None, ev.get("location_evidence_sources", "").split("|")))
        independently_located = (
            ev.get("location_decision") in {"located_candidate", "regional_candidate"}
            and bool(ev.get("matched_broad_poi"))
            and bool(sources & {"platform_location", "content_text", "ocr_text", "visual_landmark"})
        )
        if collected or independently_located:
            row["archive_poi"] = ev.get("matched_broad_poi", "") or row.get("archive_poi", "")
            row["notes"] = row.get("notes", "") + f";location_decision={ev.get('location_decision', '')}"
            accepted.append(row)
        else:
            rejected.append(row)

    by_id = {row.get("record_id", ""): row for row in existing}
    added = 0
    updated_media = 0
    for row in accepted:
        current = by_id.get(row["record_id"])
        if current:
            if not current.get("media_paths") and row.get("media_paths"):
                current["media_paths"] = row["media_paths"]
                current["media_local_path"] = row["media_local_path"]
                current["media_sha256"] = row["media_sha256"]
                updated_media += 1
            continue
        by_id[row["record_id"]] = row
        added += 1

    stamp = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%dT%H%M%S")
    backup = root / "data" / "interim" / "backups" / f"all_posts_before_media_runs_{stamp}.csv"
    write_csv(backup, existing, fields)
    merged = sorted(by_id.values(), key=lambda row: (row.get("platform", ""), row.get("publish_time", ""), row.get("record_id", "")))
    write_csv(output_path, merged, fields)
    rejected_path = root / "data" / "interim" / "media_run_rejected.csv"
    write_csv(rejected_path, rejected, list(candidates[0]))
    print(json.dumps({
        "accepted": len(accepted), "rejected": len(rejected), "added": added,
        "updated_media": updated_media, "total": len(merged), "backup": str(backup),
        "rejected_output": str(rejected_path),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
