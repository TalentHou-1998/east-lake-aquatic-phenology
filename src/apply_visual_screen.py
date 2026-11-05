#!/usr/bin/env python3
"""Apply auditable row-numbered primary-image annotations to platform CSV files."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--annotations", required=True, type=Path)
    parser.add_argument("--data-dir", required=True, type=Path)
    args = parser.parse_args()

    by_platform: dict[str, dict[int, dict[str, str]]] = defaultdict(dict)
    with args.annotations.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            by_platform[row["platform"]][int(row["row_number"])] = row

    for platform, annotations in by_platform.items():
        path = args.data_dir / f"{platform}_posts.csv"
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = list(reader.fieldnames or [])
            rows = list(reader)
        for number, row in enumerate(rows, start=1):
            row["review_status"] = "primary_screened"
            annotation = annotations.get(number)
            if not annotation:
                extra = "primary_image_screened=no_clear_aquatic_vegetation_or_insufficient_detail"
                row["notes"] = "; ".join(filter(None, [row.get("notes", ""), extra]))
                continue
            for field in (
                "vegetation_type",
                "growth_stage",
                "cover_grade",
                "phenology_confidence",
                "visual_location",
                "visual_location_confidence",
                "location_match_class",
            ):
                row[field] = annotation[field]
            row["review_status"] = "preannotated_primary"
            row["notes"] = "; ".join(
                filter(
                    None,
                    [
                        row.get("notes", ""),
                        "visual_basis=primary_image_only",
                        annotation["annotation_notes"],
                    ],
                )
            )
        temporary = path.with_suffix(path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        temporary.replace(path)
        print(f"platform={platform} rows={len(rows)} preannotated={len(annotations)}")


if __name__ == "__main__":
    main()
