"""Command parsing for wage settlement."""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
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


def _split_kv(text: str) -> tuple[str | None, str | None]:
    normalized = text.replace("：", ":").replace("=", ":")
    if ":" not in normalized:
        return None, None
    name, value = normalized.split(":", 1)
    name = name.strip()
    value = value.strip()
    if not name or not value:
        return None, None
    return name, value


def _normalize_role(value: str) -> str | None:
    text = value.strip()
    if "组长" in text:
        return "组长"
    if "组员" in text:
        return "组员"
    return None


def _parse_fixed_daily_rate(value: str) -> Decimal | None:
    cleaned = value.replace("元", "").replace("￥", "").replace("¥", "").strip()
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _detect_mode(first_line: str) -> str | None:
    normalized = _normalize_text(first_line)
    if normalized.startswith("工资:") or normalized.startswith("工资"):
        return "single"
    if normalized.startswith("项目结算:") or normalized.startswith("项目结算"):
        return "project"
    return None


def _parse_blocks(lines: list[str]) -> tuple[dict[str, str], dict[str, Decimal]]:
    role_overrides: dict[str, str] = {}
    fixed_daily_rates: dict[str, Decimal] = {}
    mode: str | None = None
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("角色"):
            mode = "role"
            continue
        if stripped.startswith("固定日薪"):
            mode = "fixed"
            continue
        if mode == "role":
            name, value = _split_kv(stripped)
            if not name or not value:
                continue
            role = _normalize_role(value)
            if role:
                role_overrides[name] = role
        elif mode == "fixed":
            name, value = _split_kv(stripped)
            if not name or not value:
                continue
            rate = _parse_fixed_daily_rate(value)
            if rate is not None:
                fixed_daily_rates[name] = rate
    return role_overrides, fixed_daily_rates


def parse_command(text: str) -> dict[str, Any]:
    """Parse wage settlement command text.

    Returns a dict with person_name, role, project_ended, project_name,
    runtime_overrides.
    """
    lines = [line for line in text.splitlines() if line.strip()]
    first_line = lines[0] if lines else ""
    normalized = _normalize_text(first_line)
    role_overrides, fixed_daily_rates = _parse_blocks(lines[1:])
    mode = _detect_mode(first_line)
    return {
        "mode": mode,
        "person_name": _extract_person_name(normalized),
        "role": _extract_role(normalized),
        "project_ended": _extract_project_ended(normalized),
        "project_name": _extract_project_name(normalized),
        "role_overrides": role_overrides,
        "fixed_daily_rates": fixed_daily_rates,
        "runtime_overrides": {},
    }
