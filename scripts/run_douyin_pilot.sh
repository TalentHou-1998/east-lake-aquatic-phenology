#!/bin/zsh
set -eu

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CRAWLER_DIR="$PROJECT_ROOT/vendor/Douyin_keyword_crawler"
VENV_DIR="$PROJECT_ROOT/.venv-dykw"

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  uv venv --python 3.11 "$VENV_DIR"
  uv pip install --python "$VENV_DIR/bin/python" -r "$CRAWLER_DIR/requirements.txt"
fi

cd "$CRAWLER_DIR"
"$VENV_DIR/bin/python" main.py \
  --platform douyin \
  --browser-channel msedge \
  --cdp-url "http://127.0.0.1:9222" \
  --keywords-file "$PROJECT_ROOT/config/keywords_pilot.txt" \
  --locations "武汉东湖" \
  --location-sep " " \
  --start-date 2018-01-01 \
  --end-date 2026-10-30 \
  --out-format both \
  --out "$PROJECT_ROOT/data/raw/douyin_pilot.csv" \
  --state-db "$PROJECT_ROOT/data/interim/douyin_state.sqlite3" \
  --max-pages 2 \
  --max-items 25 \
  --max-responses 40 \
  --min-sleep 5 \
  --max-sleep 10

