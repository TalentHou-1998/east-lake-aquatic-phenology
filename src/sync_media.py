#!/usr/bin/env python3
"""Attach locally downloaded Douyin media evidence to the normalized table."""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
from pathlib import Path


AWEME_RE = re.compile(r"/(?:video|note)/(\d+)")
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--media-root", required=True, type=Path)
    parser.add_argument("--project-root", required=True, type=Path)
    args = parser.parse_args()

    with args.csv.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    static_count = 0
    video_count = 0
    for row in rows:
        match = AWEME_RE.search(row.get("post_url", ""))
        if not match:
            continue
        media_dir = args.media_root / match.group(1)
        if not media_dir.is_dir():
            continue

        files = [path for path in media_dir.iterdir() if path.is_file() and not path.name.endswith(".part")]
        images = sorted((path for path in files if path.suffix.lower() in IMAGE_SUFFIXES), key=lambda p: (p.name != "cover.jpeg", p.name))
        videos = sorted(path for path in files if path.suffix.lower() in VIDEO_SUFFIXES)

        if images:
            primary = images[0]
            row["media_local_path"] = primary.relative_to(args.project_root).as_posix()
            row["media_sha256"] = sha256(primary)
            static_count += 1

        note_parts = [part.strip() for part in (row.get("notes") or "").split(";") if part.strip()]
        note_parts = [part for part in note_parts if not part.startswith(("gallery_images=", "full_video="))]
        if len(images) > 1:
            note_parts.append(f"gallery_images={len(images)}")
        if videos:
            note_parts.append(f"full_video={videos[0].relative_to(args.project_root).as_posix()}")
            video_count += 1
        row["notes"] = "; ".join(note_parts)

    temporary = args.csv.with_suffix(args.csv.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(args.csv)
    print(f"rows={len(rows)} static_media={static_count} full_video={video_count}")


if __name__ == "__main__":
    main()
