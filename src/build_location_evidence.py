#!/usr/bin/env python3
"""Build auditable location evidence from POI, text, OCR and visual notes."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform as runtime_platform
from pathlib import Path
import shutil
import subprocess
import tempfile


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".tif", ".tiff", ".bmp"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv"}
TARGET_CONTEXT = {
    "荷花", "荷叶", "残荷", "莲花", "睡莲", "水草", "浮萍", "湿地", "池塘",
    "湖边", "岸边", "钓鱼", "划船", "航拍", "栈道", "水葫芦", "打捞",
    "返青", "盛花", "枯黄", "芦苇", "菖蒲", "香蒲", "水生植物",
}
FIELDS = [
    "record_id",
    "platform",
    "platform_location_text",
    "content_evidence_text",
    "ocr_text",
    "visual_evidence_text",
    "matched_broad_poi",
    "matched_aliases",
    "location_evidence_sources",
    "location_evidence_score",
    "location_evidence_level",
    "location_decision",
    "location_decision_reason",
    "platform_geotag_present",
    "ocr_engine",
    "ocr_media_count",
    "ocr_error",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def hierarchy(path: Path) -> list[tuple[str, str]]:
    aliases: set[tuple[str, str]] = set()
    for row in read_csv(path):
        broad = row["broad_poi"]
        values = [broad, *row["search_anchors"].split("|"), *row["match_aliases"].split("|")]
        aliases.update((value.strip(), broad) for value in values if value.strip())
    return sorted(aliases, key=lambda item: len(item[0]), reverse=True)


def canonical_platform(value: str) -> str:
    return {
        "dy": "douyin",
        "ks": "kuaishou",
        "wb": "weibo",
        "bili": "bilibili",
    }.get(value, value)


def record_media(project_root: Path, row: dict[str, str]) -> list[Path]:
    candidates: list[Path] = []
    for value in row.get("media_paths", "").split("|"):
        if value.strip():
            candidates.append(project_root / value.strip())
    if row.get("media_local_path", "").strip():
        candidates.append(project_root / row["media_local_path"].strip())
    media_dir = project_root / "media" / canonical_platform(row.get("platform", "")) / row["record_id"]
    if media_dir.is_dir():
        candidates.extend(path for path in media_dir.iterdir() if path.is_file())
    unique: dict[str, Path] = {}
    for path in candidates:
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES | VIDEO_SUFFIXES:
            unique[str(path.resolve())] = path.resolve()
    return sorted(unique.values())


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_vision_binary(project_root: Path) -> Path:
    if runtime_platform.system() != "Darwin":
        raise RuntimeError("Apple Vision OCR is only available on macOS")
    source = project_root / "scripts" / "vision_ocr.swift"
    binary = project_root / "data" / "interim" / "bin" / "vision_ocr"
    if not binary.exists() or binary.stat().st_mtime < source.stat().st_mtime:
        binary.parent.mkdir(parents=True, exist_ok=True)
        swiftc = shutil.which("swiftc") or "/Library/Developer/CommandLineTools/usr/bin/swiftc"
        subprocess.run([swiftc, "-O", str(source), "-o", str(binary)], check=True)
    return binary


def video_frames(path: Path, target_dir: Path, limit: int) -> list[Path]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required for video OCR")
    pattern = target_dir / "frame-%03d.jpg"
    subprocess.run(
        [
            ffmpeg, "-v", "error", "-i", str(path),
            "-vf", "fps=1/12,scale='min(1600,iw)':-2",
            "-frames:v", str(limit), str(pattern),
        ],
        check=True,
        timeout=180,
    )
    return sorted(target_dir.glob("frame-*.jpg"))


def ocr_image(binary: Path, cache_dir: Path, path: Path) -> dict:
    digest = file_sha256(path)
    cache_path = cache_dir / f"{digest}.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))
    completed = subprocess.run(
        [str(binary), str(path)],
        check=True,
        capture_output=True,
        text=True,
        timeout=90,
    )
    result = json.loads(completed.stdout)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(result, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


def extract_ocr(
    project_root: Path,
    paths: list[Path],
    binary: Path,
    max_media: int,
    max_video_frames: int,
) -> tuple[str, int, str]:
    texts: list[str] = []
    processed = 0
    errors: list[str] = []
    cache_dir = project_root / "data" / "interim" / "ocr_cache"
    for path in paths[:max_media]:
        try:
            if path.suffix.lower() in IMAGE_SUFFIXES:
                result = ocr_image(binary, cache_dir, path)
                if result.get("text"):
                    texts.append(result["text"])
                processed += 1
            else:
                with tempfile.TemporaryDirectory(prefix="east-lake-frames-") as temporary:
                    frames = video_frames(path, Path(temporary), max_video_frames)
                    for frame in frames:
                        result = ocr_image(binary, cache_dir, frame)
                        if result.get("text"):
                            texts.append(result["text"])
                    processed += 1
        except Exception as error:
            errors.append(f"{path.name}:{type(error).__name__}")
    return "\n".join(texts)[:12000], processed, "|".join(errors[:10])


def source_matches(text: str, aliases: list[tuple[str, str]]) -> list[tuple[str, str]]:
    return [(alias, broad) for alias, broad in aliases if alias in text]


def evaluate(row: dict[str, str], ocr_text: str, aliases: list[tuple[str, str]]) -> dict[str, str]:
    raw_poi = row.get("platform_poi_name", "").strip()
    if "正文提及" in raw_poi or "未提供平台定位" in raw_poi:
        raw_poi = ""
    platform_text = " ".join(
        value.strip()
        for value in (
            raw_poi,
            row.get("platform_poi_address", ""),
        )
        if value.strip()
    )
    content_text = row.get("content_text", "").strip()
    visual_text = row.get("visual_location", "").strip()
    sources = {
        "platform_location": (platform_text, 1.00),
        "content_text": (content_text, 0.82),
        "ocr_text": (ocr_text, 0.72),
        "visual_landmark": (visual_text, 0.90),
    }
    scores: dict[str, float] = {}
    source_by_poi: dict[str, set[str]] = {}
    aliases_by_poi: dict[str, set[str]] = {}
    for source, (text, weight) in sources.items():
        if not text:
            continue
        best_for_source: dict[str, tuple[str, float]] = {}
        for alias, broad in source_matches(text, aliases):
            specificity = 1.0 if len(alias) >= 4 else 0.72
            candidate = weight * specificity
            if candidate > best_for_source.get(broad, ("", 0.0))[1]:
                best_for_source[broad] = (alias, candidate)
        for broad, (alias, candidate) in best_for_source.items():
            scores[broad] = min(1.0, scores.get(broad, 0.0) + candidate)
            source_by_poi.setdefault(broad, set()).add(source)
            aliases_by_poi.setdefault(broad, set()).add(alias)

    generic_sources = {
        source for source, (text, _) in sources.items()
        if "东湖" in text and source != "platform_location"
    }
    combined_text = " ".join(value[0] for value in sources.values())
    context_hits = sorted(term for term in TARGET_CONTEXT if term in combined_text)
    if scores:
        best_score = max(scores.values())
        winners = [name for name, score in scores.items() if score == best_score]
        matched = winners[0] if len(winners) == 1 else ""
    else:
        best_score = 0.0
        matched = ""

    if matched:
        evidence_sources = source_by_poi[matched]
        matched_aliases = aliases_by_poi[matched]
        if "platform_location" in evidence_sources or len(evidence_sources) >= 2:
            level = "high"
        elif best_score >= 0.70:
            level = "medium"
        else:
            level = "low"
        decision = "located_candidate"
        reason = f"{'+'.join(sorted(evidence_sources))} 命中 {matched}"
    elif generic_sources and context_hits:
        matched = "东湖风景区（综合）"
        matched_aliases = {"东湖"}
        evidence_sources = generic_sources
        best_score = min(0.69, 0.45 + 0.08 * len(generic_sources))
        level = "medium" if len(generic_sources) >= 2 else "low"
        decision = "regional_candidate"
        reason = f"非定位证据提及东湖，并命中场景词：{'、'.join(context_hits[:6])}"
    else:
        matched_aliases = set()
        evidence_sources = set()
        level = "none"
        decision = "needs_review"
        reason = "未获得足以定位的正文、OCR、画面或平台位置证据"

    return {
        "platform_location_text": platform_text,
        "content_evidence_text": content_text[:4000],
        "ocr_text": ocr_text[:12000],
        "visual_evidence_text": visual_text,
        "matched_broad_poi": matched,
        "matched_aliases": "|".join(sorted(matched_aliases, key=len, reverse=True)),
        "location_evidence_sources": "|".join(sorted(evidence_sources)),
        "location_evidence_score": f"{best_score:.2f}",
        "location_evidence_level": level,
        "location_decision": decision,
        "location_decision_reason": reason,
        "platform_geotag_present": "true" if platform_text or row.get("platform_lng") else "false",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--input", type=Path, default=Path("data/processed/all_posts.csv"))
    parser.add_argument("--hierarchy", type=Path, default=Path("config/east_lake_poi_hierarchy.csv"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/location_evidence.csv"))
    parser.add_argument("--ocr", choices=("none", "vision"), default="none")
    parser.add_argument(
        "--ocr-unresolved-only",
        action="store_true",
        help="Run OCR only when POI/content/visual evidence does not already locate the record.",
    )
    parser.add_argument("--max-records", type=int, default=0)
    parser.add_argument("--max-media-per-record", type=int, default=8)
    parser.add_argument("--max-video-frames", type=int, default=6)
    args = parser.parse_args()

    root = args.project_root.resolve()
    input_path = args.input if args.input.is_absolute() else root / args.input
    hierarchy_path = args.hierarchy if args.hierarchy.is_absolute() else root / args.hierarchy
    output_path = args.output if args.output.is_absolute() else root / args.output
    rows = read_csv(input_path)
    if args.max_records:
        rows = rows[: args.max_records]
    aliases = hierarchy(hierarchy_path)
    binary = ensure_vision_binary(root) if args.ocr == "vision" else None

    results: list[dict[str, str]] = []
    for row in rows:
        ocr_text = ""
        media_count = 0
        ocr_error = ""
        preliminary = evaluate(row, "", aliases)
        should_ocr = binary and not (
            args.ocr_unresolved_only and preliminary["location_decision"] == "located_candidate"
        )
        if should_ocr:
            ocr_text, media_count, ocr_error = extract_ocr(
                root,
                record_media(root, row),
                binary,
                args.max_media_per_record,
                args.max_video_frames,
            )
        evidence = evaluate(row, ocr_text, aliases) if ocr_text else preliminary
        results.append({
            "record_id": row["record_id"],
            "platform": row.get("platform", ""),
            **evidence,
            "ocr_engine": "apple_vision" if binary else "not_run",
            "ocr_media_count": str(media_count),
            "ocr_error": ocr_error,
        })
    write_csv(output_path, results)
    counts: dict[str, int] = {}
    for row in results:
        counts[row["location_decision"]] = counts.get(row["location_decision"], 0) + 1
    print(json.dumps({"records": len(results), "decisions": counts, "output": str(output_path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
