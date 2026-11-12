#!/usr/bin/env python3
"""Move a mistaken archive batch to a recoverable quarantine and remove its manifest rows."""

from __future__ import annotations

import argparse
import csv
import shutil
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument("--crawl-time-prefix", required=True)
    parser.add_argument("--platform", required=True)
    parser.add_argument(
        "--content-ids",
        default="",
        help="Optional comma-separated content IDs; empty selects the entire batch.",
    )
    parser.add_argument("--reason", default="geography_mismatch")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    root = args.project_root.resolve()
    manifest = (root / args.manifest).resolve()
    with manifest.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        rows = list(reader)

    content_ids = {value.strip() for value in args.content_ids.split(",") if value.strip()}
    selected = [
        row for row in rows
        if row.get("platform") == args.platform
        and row.get("crawl_time", "").startswith(args.crawl_time_prefix)
        and (not content_ids or row.get("content_id") in content_ids)
    ]
    print(f"selected_rows={len(selected)} execute={args.execute}")
    if not args.execute or not selected:
        return

    for row in selected:
        source = (root / row["archive_path"]).resolve()
        if not source.is_relative_to(root) or not source.is_file():
            continue
        target = root / "media_quarantine" / args.reason / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            target = target.with_name(f"{target.stem}_{row['sha256'][:8]}{target.suffix}")
        shutil.move(source, target)

    remaining = [row for row in rows if row not in selected]
    temporary = manifest.with_suffix(manifest.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(remaining)
    temporary.replace(manifest)
    print(f"quarantined={len(selected)} remaining={len(remaining)}")


if __name__ == "__main__":
    main()
