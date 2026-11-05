#!/bin/zsh
set -eu

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROFILE_DIR="$PROJECT_ROOT/data/edge-profile"
mkdir -p "$PROFILE_DIR"

open -na "Microsoft Edge" --args \
  --remote-debugging-port=9222 \
  --user-data-dir="$PROFILE_DIR" \
  "https://www.douyin.com/"

echo "Edge 已启动。请在窗口中完成抖音登录；该 profile 仅用于本项目。"

