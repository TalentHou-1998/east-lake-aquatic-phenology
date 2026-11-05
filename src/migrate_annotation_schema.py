#!/usr/bin/env python3
"""Migrate processed research CSVs to the four-stage phenology and media-value schema."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


STAGE_MAP = {
    "dormant": "declined",
    "emergence": "growth_start",
    "leaf": "fully_grown",
    "flower_bud": "fully_grown",
    "flowering": "fully_grown",
    "fruiting": "decline_start",
    "senescent": "decline_start",
    "unknown": "unknown",
    "": "unknown",
}


def migrate(path: Path) -> tuple[int, int]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fields = list(reader.fieldnames or [])
    if "media_value" not in fields:
        fields.insert(fields.index("review_status"), "media_value")
    changed = 0
    for row in rows:
        old = row.get("growth_stage", "unknown")
        new = STAGE_MAP.get(old, "unknown")
        if new != old:
            changed += 1
            if old not in {"", "unknown"}:
                note = row.get("notes", "").strip()
                row["notes"] = "; ".join(filter(None, [note, f"legacy_growth_stage={old}", "stage_migration=v2_four_stage"]))
        row["growth_stage"] = new
        row["media_value"] = row.get("media_value") or "unknown"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows), changed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--processed", type=Path, required=True)
    args = parser.parse_args()
    total = changed = 0
    for path in sorted(args.processed.glob("*_posts.csv")):
        if path.name == "all_posts.csv":
            continue
        rows, updates = migrate(path)
        total += rows
        changed += updates
        print(f"{path.name}: rows={rows} stage_updates={updates}")

    source_rows = []
    fields = None
    for path in sorted(args.processed.glob("*_posts.csv")):
        if path.name == "all_posts.csv":
            continue
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = fields or list(reader.fieldnames or [])
            source_rows.extend(reader)
    by_key = {(row.get("platform"), row.get("post_url")): row for row in source_rows}
    merged = sorted(by_key.values(), key=lambda row: (row.get("platform", ""), row.get("publish_time", ""), row.get("record_id", "")))
    with (args.processed / "all_posts.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields or [], extrasaction="ignore")
        writer.writeheader()
        writer.writerows(merged)
    print(f"total_platform_rows={total} stage_updates={changed} all_rows={len(merged)}")


if __name__ == "__main__":
    main()
