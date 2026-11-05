#!/usr/bin/env python3
"""Fail closed when a public-release tree contains secrets or restricted data."""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path


BLOCKED_PATHS = (
    "data/raw/",
    "data/interim/",
    "data/processed/",
    "data/annotations/",
    "data/edge-profile/",
    "media/",
    "output/",
    "vendor/",
    "sites/east-lake-map/.openai/",
    "sites/east-lake-map/dist/assets/media/",
    "sites/east-lake-map/dist/data/points.json",
    "sites/east-lake-map/dist/data/summary.json",
)

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".pytest_cache", ".ruff_cache"}

PATTERNS = {
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "openai_key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "github_token": re.compile(r"\b(?:ghp|github_pat)_[A-Za-z0-9_]{20,}\b"),
    "bearer_token": re.compile(r"\bBearer\s+[A-Za-z0-9._~-]{20,}\b", re.I),
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    "personal_home_path": re.compile(r"/(?:Users|home)/[A-Za-z0-9._-]+/"),
    "email": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
}

ALLOWED_LITERALS = {
    "<YOUR_AMAP_API_KEY>",
    "<YOUR_BAIDU_MAP_AK>",
    "<YOUR_GITHUB_TOKEN>",
    "<YOUR_HTTPS_PROXY_URL>",
    "<YOUR_GITHUB_USERNAME>",
    "example@example.com",
    "noreply@github.com",
}


def iter_files(root: Path):
    for current, dirs, files in os.walk(root):
        dirs[:] = [name for name in dirs if name not in SKIP_DIRS]
        current_path = Path(current)
        for name in files:
            yield current_path / name


def text_or_none(path: Path) -> str | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in data[:8192]:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = args.root.resolve()
    findings: list[str] = []

    for path in iter_files(root):
        relative = path.relative_to(root).as_posix()
        if any(relative == blocked.rstrip("/") or relative.startswith(blocked) for blocked in BLOCKED_PATHS):
            findings.append(f"blocked_path:{relative}")
            continue
        if path.name.startswith(".env") and path.name != ".env.example":
            findings.append(f"environment_file:{relative}")
            continue
        text = text_or_none(path)
        if text is None:
            continue
        sanitized = text
        for literal in ALLOWED_LITERALS:
            sanitized = sanitized.replace(literal, "<ALLOWED_PLACEHOLDER>")
        for label, pattern in PATTERNS.items():
            for match in pattern.finditer(sanitized):
                line = sanitized.count("\n", 0, match.start()) + 1
                findings.append(f"{label}:{relative}:{line}")

    if findings:
        print("Public release check FAILED. Values are intentionally not echoed.")
        for finding in sorted(set(findings)):
            print(f"- {finding}")
        return 1
    print("Public release check PASSED: no restricted paths or recognized secrets found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

