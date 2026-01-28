"""Command parsing for wage settlement."""
from __future__ import annotations

import re
from typing import Any


ROLE_KEYWORDS = ["组长", "组员"]


def _normalize_text(text: str) -> str:
    cleaned = text.replace("：", ":")
    cleaned = cleaned.replace("｜", " ")
    cleaned = cleaned.replace("|", " ")
    return " ".join(cleaned.split())


def _extract_project_ended(text: str) -> bool | None:
    match = re.search(r"项目已结束\s*=\s*([是否])", text)
    if not match:
        match = re.search(r"项目结束\s*=\s*([是否])", text)
    if not match:
        return None
    return match.group(1) == "是"


def _extract_project_name(text: str) -> str | None:
    match = re.search(r"项目\s*=\s*([^\s]+)", text)
    if not match:
        return None
    return match.group(1).strip()


def _extract_role(text: str) -> str | None:
    for role in ROLE_KEYWORDS:
        if role in text:
            return role
    return None


def _extract_person_name(text: str) -> str | None:
    match = re.search(r"工资\s*[:：]\s*([^\s]+)", text)
    if match:
        return match.group(1).strip()
    tokens = [token for token in re.split(r"\s+", text) if token]
    for token in tokens:
        if token in ("工资", "工资:", "工资："):
            continue
        if token in ROLE_KEYWORDS:
            continue
        if "=" in token:
            continue
        if token.startswith("项目"):
            continue
        return token
    return None


def parse_command(text: str) -> dict[str, Any]:
    """Parse wage settlement command text.

    Returns a dict with person_name, role, project_ended, project_name,
    runtime_overrides.
    """
    normalized = _normalize_text(text)
    return {
        "person_name": _extract_person_name(normalized),
        "role": _extract_role(normalized),
        "project_ended": _extract_project_ended(normalized),
        "project_name": _extract_project_name(normalized),
        "runtime_overrides": {},
    }
