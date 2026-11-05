#!/usr/bin/env python3
"""Create labeled contact sheets for efficient visual screening."""

from __future__ import annotations

import argparse
import csv
import subprocess
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--per-sheet", type=int, default=20)
    args = parser.parse_args()

    with args.csv.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    args.output_dir.mkdir(parents=True, exist_ok=True)

    for start in range(0, len(rows), args.per_sheet):
        chunk = rows[start : start + args.per_sheet]
        command = [
            "magick",
            "montage",
            "-font",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
        ]
        for offset, row in enumerate(chunk, start=start + 1):
            image = args.project_root / row["media_local_path"]
            command.extend(["-label", f"{offset:03d} {row['publish_time'][:10]}", str(image)])
        sheet_number = start // args.per_sheet + 1
        output = args.output_dir / f"{args.prefix}_{sheet_number:02d}.jpg"
        command.extend(
            [
                "-auto-orient",
                "-thumbnail",
                "260x190^",
                "-gravity",
                "center",
                "-extent",
                "260x190",
                "-background",
                "#111111",
                "-fill",
                "white",
                "-pointsize",
                "18",
                "-tile",
                "5x4",
                "-geometry",
                "+6+24",
                str(output),
            ]
        )
        subprocess.run(command, check=True)
        print(output)


if __name__ == "__main__":
    main()
