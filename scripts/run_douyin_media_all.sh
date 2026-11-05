#!/bin/zsh
set -eu

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MEDIACRAWLER_DIR="$PROJECT_ROOT/vendor/MediaCrawler"

SPECIFIED_IDS="$(python3 - "$PROJECT_ROOT/data/processed/douyin_posts.csv" <<'PY'
import csv
import sys

with open(sys.argv[1], encoding="utf-8-sig", newline="") as handle:
    print(",".join(row["post_url"] for row in csv.DictReader(handle)))
PY
)"

cd "$MEDIACRAWLER_DIR"
uv run main.py \
  --platform dy \
  --lt qrcode \
  --type detail \
  --specified_id "$SPECIFIED_IDS" \
  --get_media true \
  --get_comment false \
  --max_concurrency_num 1 \
  --save_data_option jsonl \
  --save_data_path "$PROJECT_ROOT/media"

