"""Ruleset helpers for wage settlement."""
from __future__ import annotations

from pathlib import Path
import re


def get_ruleset_version() -> str:
    repo_root = Path(__file__).resolve().parents[1]
    latest_txt = repo_root / "rules" / "latest.txt"
    if latest_txt.exists():
        version = latest_txt.read_text(encoding="utf-8").strip()
        if version:
            return version

    latest_md = repo_root / "rules" / "01_工资模块_latest.md"
    if not latest_md.exists():
        raise FileNotFoundError("ruleset version file not found")
    for line in latest_md.read_text(encoding="utf-8").splitlines():
        match = re.search(r"版本\s+(v[^\s]+)", line)
        if match:
            return match.group(1)
    raise ValueError("ruleset version not found in latest ruleset file")
