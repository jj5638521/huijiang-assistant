"""Command parsing for wage settlement."""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any


ROLE_KEYWORDS = ["组长", "组员"]
FULLWIDTH_SPACE = "\u3000"


def _normalize_line(text: str) -> str:
    cleaned = (
        text.replace("\ufeff", "")
        .replace("：", ":")
        .replace("＝", "=")
        .replace(FULLWIDTH_SPACE, " ")
        .replace("｜", " ")
        .replace("|", " ")
    )
    return " ".join(cleaned.strip().split())


def _parse_bool(value: str) -> bool | None:
    normalized = value.strip().lower()
    if normalized in {"是", "true", "1"}:
        return True
    if normalized in {"否", "false", "0"}:
        return False
    return None


def _extract_project_header(line: str) -> tuple[str | None, str]:
    normalized = _normalize_line(line)
    if not normalized.startswith("项目结算"):
        return None, ""
    remainder = normalized[len("项目结算") :].lstrip(":").strip()
    if not remainder:
        return None, ""
    tokens = remainder.split()
    if tokens and all(sep not in tokens[0] for sep in (":", "=")):
        project_name = tokens[0]
        rest = " ".join(tokens[1:]).strip()
        return project_name, rest
    return None, remainder


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
    normalized = _normalize_line(text)
    match = re.search(r"[:=]", normalized)
    if not match:
        return None, None
    name, value = normalized.split(match.group(0), 1)
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
    normalized = _normalize_line(first_line)
    if normalized.startswith("工资:") or normalized.startswith("工资"):
        return "single"
    if normalized.startswith("项目结算:") or normalized.startswith("项目结算"):
        return "project"
    return None


def _extract_kv_pairs(line: str) -> list[tuple[str, str]]:
    normalized = _normalize_line(line)
    return re.findall(r"([^\s:=]+)\s*[:=]\s*([^\s]+)", normalized)


def _parse_blocks(lines: list[str]) -> tuple[dict[str, str], dict[str, Decimal]]:
    role_overrides: dict[str, str] = {}
    fixed_daily_rates: dict[str, Decimal] = {}
    mode: str | None = None
    for line in lines:
        stripped = _normalize_line(line)
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


def _apply_kv_mapping(
    result: dict[str, Any],
    key: str,
    value: str,
) -> None:
    if key in {"项目已结束", "项目结束", "项目是否结束"}:
        parsed = _parse_bool(value)
        if parsed is not None:
            result["project_ended"] = parsed
        return
    if key == "项目":
        result["project_name"] = value.strip()
        return
    if key == "路补口令":
        runtime_overrides = result.setdefault("runtime_overrides", {})
        runtime_overrides["road_passphrase"] = value.strip()


def parse_command(text: str) -> dict[str, Any]:
    """Parse wage settlement command text.

    Returns a dict with person_name, role, project_ended, project_name,
    runtime_overrides.
    """
    raw_lines = text.splitlines()
    lines = [_normalize_line(line) for line in raw_lines if _normalize_line(line)]
    first_line = lines[0] if lines else ""
    mode = _detect_mode(first_line)
    role_overrides: dict[str, str] = {}
    fixed_daily_rates: dict[str, Decimal] = {}
    result: dict[str, Any] = {
        "mode": mode,
        "person_name": _extract_person_name(first_line),
        "role": _extract_role(first_line),
        "project_ended": None,
        "project_name": None,
        "role_overrides": role_overrides,
        "fixed_daily_rates": fixed_daily_rates,
        "runtime_overrides": {},
    }
    if mode == "project" and first_line:
        project_name, remainder = _extract_project_header(first_line)
        if project_name:
            result["project_name"] = project_name
        if remainder:
            for key, value in _extract_kv_pairs(remainder):
                _apply_kv_mapping(result, key, value)
    if first_line:
        for key, value in _extract_kv_pairs(first_line):
            _apply_kv_mapping(result, key, value)

    block_mode: str | None = None
    for line in lines[1:]:
        if line.startswith("角色"):
            block_mode = "role"
            continue
        if line.startswith("固定日薪"):
            block_mode = "fixed"
            continue
        if block_mode == "role":
            name, value = _split_kv(line)
            if not name or not value:
                continue
            role = _normalize_role(value)
            if role:
                role_overrides[name] = role
            continue
        if block_mode == "fixed":
            name, value = _split_kv(line)
            if not name or not value:
                continue
            rate = _parse_fixed_daily_rate(value)
            if rate is not None:
                fixed_daily_rates[name] = rate
            continue
        for key, value in _extract_kv_pairs(line):
            _apply_kv_mapping(result, key, value)

    return result
