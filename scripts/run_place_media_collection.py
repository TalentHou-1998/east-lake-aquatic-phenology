#!/usr/bin/env python3
"""Run one conservative MediaCrawler place/platform batch and archive its media."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


SUPPORTED = ("xhs", "dy", "ks", "wb", "bili")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--unit-id", required=True)
    parser.add_argument("--platform", required=True, choices=SUPPORTED)
    parser.add_argument("--plan", type=Path, default=Path("data/interim/media_collection_plan.json"))
    parser.add_argument("--keyword-start", type=int, default=0)
    parser.add_argument("--keyword-count", type=int, default=1)
    parser.add_argument("--strategy", default="", help="Select query_records by strategy before slicing.")
    parser.add_argument("--target-months", default="", help="Only archive posts in these publish months, e.g. 1-5 or 1,3,4.")
    parser.add_argument("--allow-nonaquatic", action="store_true", help="Keep place-anchored media even when the caption has no aquatic term.")
    parser.add_argument("--max-notes", type=int, default=10)
    parser.add_argument("--login-type", choices=("qrcode", "phone", "cookie"), default="qrcode")
    parser.add_argument("--execute", action="store_true", help="Without this flag, only print the job.")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    crawler_root = project_root / "vendor" / "MediaCrawler"
    payload = json.loads((project_root / args.plan).read_text(encoding="utf-8"))
    unit = next((job for job in payload["jobs"] if job["unit_id"] == args.unit_id), None)
    if unit is None:
        raise SystemExit(f"unknown unit_id: {args.unit_id}")
    query_records = unit.get("query_records") or [{"query": value, "strategy": ""} for value in unit["keywords"]]
    if args.strategy:
        query_records = [item for item in query_records if item.get("strategy") == args.strategy]
    selected_records = query_records[args.keyword_start : args.keyword_start + args.keyword_count]
    keywords = [item["query"] for item in selected_records]
    if not keywords:
        raise SystemExit("selected keyword slice is empty")

    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    run_root = project_root / "data" / "raw" / "media_runs" / now.strftime("%Y%m%dT%H%M%S") / args.unit_id
    command = [
        "uv", "run", "main.py", "--platform", args.platform, "--lt", args.login_type,
        "--type", "search", "--keywords", ",".join(keywords), "--get_media", "true",
        "--get_comment", "false", "--get_sub_comment", "false", "--headless", "false",
        "--save_data_option", "jsonl", "--save_data_path", str(run_root),
        "--crawler_max_notes_count", str(args.max_notes), "--max_concurrency_num", "1",
        "--enable_ip_proxy", "false",
    ]
    print(json.dumps({
        "unit_id": args.unit_id,
        "place": unit["place"],
        "platform": args.platform,
        "strategy": args.strategy or "all",
        "target_months": args.target_months,
        "keywords": keywords,
        "run_root": str(run_root),
        "execute": args.execute,
    }, ensure_ascii=False, indent=2))
    if not args.execute:
        return

    returncode = 0
    try:
        returncode = subprocess.run(command, cwd=crawler_root, check=False).returncode
    except KeyboardInterrupt:
        returncode = 130
    finally:
        archive_root = project_root / ("media_candidates" if args.unit_id == "REGION01" else "media_collected")
        organize_command = [
                "python3", str(project_root / "src" / "organize_media_archive.py"),
                "--run-root", str(run_root), "--platform", args.platform,
                "--unit-id", args.unit_id, "--plan", str(project_root / args.plan),
                "--archive-root", str(archive_root),
                "--crawl-time", now.isoformat(timespec="seconds"),
            ]
        if args.unit_id == "REGION01":
            organize_command.append("--allow-unanchored")
        broad_recall = args.strategy in {"spring_backfill", "calendar_event", "neutral_activity", "seasonal_balance"}
        if args.allow_nonaquatic or broad_recall:
            organize_command.append("--allow-nonaquatic")
        if args.target_months:
            organize_command.extend(["--months", args.target_months])
        subprocess.run(
            organize_command,
            cwd=project_root,
            check=True,
        )
    if returncode:
        raise SystemExit(returncode)


if __name__ == "__main__":
    main()
