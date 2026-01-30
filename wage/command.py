"""Command parsing for wage settlement."""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from .name_utils import name_key

ROLE_KEYWORDS = ["组长", "组员"]
FULLWIDTH_SPACE = "\u3000"
ROAD_VALUE_MAP = {
    "有": "计算路补",
    "无": "无路补",
}


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
    fixed_rate_names: dict[str, set[str]] = {}
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
                key = name_key(name)
                fixed_daily_rates[key] = rate
                fixed_rate_names.setdefault(key, set()).add(name.strip())
    return role_overrides, fixed_daily_rates


def _append_audit_note(result: dict[str, Any], note: str) -> None:
    runtime_overrides = result.setdefault("runtime_overrides", {})
    notes = runtime_overrides.setdefault("audit_notes", [])
    if note not in notes:
        notes.append(note)


def _append_command_error(result: dict[str, Any], message: str) -> None:
    runtime_overrides = result.setdefault("runtime_overrides", {})
    errors = runtime_overrides.setdefault("command_errors", [])
    errors.append(message)


def _normalize_road_value(value: str) -> str | None:
    normalized = _normalize_line(value)
    if not normalized:
        return None
    return normalized.split()[0]


def _set_road_cmd(
    result: dict[str, Any],
    road_cmd: str,
    source: str,
) -> None:
    runtime_overrides = result.setdefault("runtime_overrides", {})
    runtime_overrides["road_passphrase"] = road_cmd
    result["road_cmd"] = road_cmd
    result["_road_cmd_source"] = source


def _apply_kv_mapping(
    result: dict[str, Any],
    key: str,
    value: str,
    *,
    source_line: str | None = None,
) -> None:
    if key in {"项目已结束", "项目结束", "项目是否结束"}:
        parsed = _parse_bool(value)
        if parsed is not None:
            result["project_ended"] = parsed
        return
    if key == "项目":
        result["project_name"] = value.strip()
        return
    if key == "路补":
        normalized = _normalize_road_value(value)
        road_cmd = ROAD_VALUE_MAP.get(normalized or "")
        if not road_cmd:
            message = (
                f"路补仅支持有/无，收到'{value.strip() or value}'"
            )
            if source_line:
                message = f"{message}，原行：{source_line.strip()}"
            _append_command_error(result, message)
            return
        existing_source = result.get("_road_cmd_source")
        if existing_source and existing_source != "wage_line":
            _append_audit_note(result, "口令冲突：已采用工资行内路补设置")
        _set_road_cmd(result, road_cmd, "wage_line")
        return
    if key == "路补口令":
        existing_source = result.get("_road_cmd_source")
        if existing_source == "wage_line":
            _append_audit_note(result, "口令冲突：已采用工资行内路补设置")
            return
        _set_road_cmd(result, value.strip(), "standalone")
        return


def parse_command(text: str) -> dict[str, Any]:
    """Parse wage settlement command text.

    Returns a dict with person_name, role, project_ended, project_name,
    runtime_overrides.
    """
    raw_lines = text.splitlines()
    normalized_lines: list[tuple[str, str]] = []
    for raw_line in raw_lines:
        normalized = _normalize_line(raw_line)
        if normalized:
            normalized_lines.append((raw_line, normalized))
    first_line = normalized_lines[0][1] if normalized_lines else ""
    mode = _detect_mode(first_line)
    role_overrides: dict[str, str] = {}
    fixed_daily_rates: dict[str, Decimal] = {}
    fixed_rate_names: dict[str, set[str]] = {}
    fixed_rate_conflicts: list[dict[str, object]] = []
    result: dict[str, Any] = {
        "mode": mode,
        "person_name": _extract_person_name(first_line),
        "role": _extract_role(first_line),
        "project_ended": None,
        "project_name": None,
        "road_cmd": None,
        "role_overrides": role_overrides,
        "fixed_daily_rates": fixed_daily_rates,
        "runtime_overrides": {
            "audit_notes": [],
            "command_errors": [],
            "name_key_conflicts": [],
        },
    }
    if mode == "project" and first_line:
        project_name, remainder = _extract_project_header(first_line)
        if project_name:
            result["project_name"] = project_name
        if remainder:
            for key, value in _extract_kv_pairs(remainder):
                _apply_kv_mapping(
                    result,
                    key,
                    value,
                    source_line=normalized_lines[0][0],
                )
    if first_line:
        for key, value in _extract_kv_pairs(first_line):
            _apply_kv_mapping(
                result,
                key,
                value,
                source_line=normalized_lines[0][0],
            )

    block_mode: str | None = None
    for raw_line, line in normalized_lines[1:]:
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
                key = name_key(name)
                fixed_daily_rates[key] = rate
                fixed_rate_names.setdefault(key, set()).add(name.strip())
            continue
        for key, value in _extract_kv_pairs(line):
            _apply_kv_mapping(result, key, value, source_line=raw_line)

    result.pop("_road_cmd_source", None)
    for key, names in fixed_rate_names.items():
        if len(names) <= 1:
            continue
        display_names = sorted(names)
        fixed_rate_conflicts.append(
            {
                "name_key": key,
                "display_names": display_names,
            }
        )
        _append_command_error(
            result,
            f"固定日薪姓名冲突: name_key={key} 显示名={','.join(display_names)}",
        )
    if fixed_rate_conflicts:
        result["runtime_overrides"]["name_key_conflicts"] = fixed_rate_conflicts
    return result
