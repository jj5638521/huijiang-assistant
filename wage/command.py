"""Command parsing for wage settlement."""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping

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


def _is_ignored_line(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    if stripped.startswith("#"):
        return True
    if re.match(r"^【[^】]*】$", stripped):
        return True
    return False


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


PROJECT_HEADERS = ["项目", "项目名称", "项目名"]


@dataclass
class _PassphraseState:
    buffer_lines: list[str] = field(default_factory=list)
    project_ended: bool | None = None
    project_name: str | None = None
    leader_keys: set[str] = field(default_factory=set)
    leader_names: list[str] = field(default_factory=list)
    road_yes: list[tuple[str, str]] = field(default_factory=list)
    road_no: list[tuple[str, str]] = field(default_factory=list)
    road_yes_names: dict[str, list[str]] = field(default_factory=dict)
    road_no_names: dict[str, list[str]] = field(default_factory=dict)
    current_target: str | None = None
    seen_marker: bool = False


def _split_names(raw: str) -> list[str]:
    cleaned = raw.strip()
    if not cleaned:
        return []
    return [part for part in re.split(r"[、，,;；\s]+", cleaned) if part]


def _add_names(
    names: list[str],
    *,
    entries: list[tuple[str, str]],
    name_map: dict[str, list[str]],
) -> None:
    seen = {key for key, _ in entries}
    for display in names:
        key = name_key(display)
        name_map.setdefault(key, []).append(display)
        if key in seen:
            continue
        entries.append((key, display))
        seen.add(key)


def _match_passphrase_key(line: str) -> tuple[str, str] | None:
    normalized = _normalize_line(line)
    match = re.match(r"^(项目已结束|项目结束|项目是否结束)\s*[:=]\s*(\S+)$", normalized)
    if match:
        return "project_ended", match.group(2)
    match = re.match(r"^项目\s*[:=]\s*(.+)$", normalized)
    if match:
        return "project", match.group(1).strip()
    match = re.match(r"^组长\s*:\s*(.*)$", normalized)
    if match:
        return "leader", match.group(1).strip()
    match = re.match(r"^路补\s*=\s*(有|无)\s*:?\s*(.*)$", normalized)
    if match:
        return ("road_yes" if match.group(1) == "有" else "road_no", match.group(2).strip())
    return None


def _collect_project_counts(rows: Iterable[Mapping[str, str]]) -> Counter:
    rows_list = list(rows)
    headers = {key.strip() for row in rows_list for key in row.keys()}
    project_key = next((header for header in PROJECT_HEADERS if header in headers), None)
    counter: Counter[str] = Counter()
    if not project_key:
        return counter
    for row in rows_list:
        value = row.get(project_key, "").strip()
        if value:
            counter[value] += 1
    return counter


def _format_project_counts(counter: Counter[str]) -> str:
    return "、".join(
        f"{name}({count})"
        for name, count in counter.most_common()
    )


def _resolve_project_name(
    attendance_rows: Iterable[Mapping[str, str]] | None,
    payment_rows: Iterable[Mapping[str, str]] | None,
    errors: list[str],
) -> str | None:
    attendance_counter = (
        _collect_project_counts(attendance_rows) if attendance_rows is not None else Counter()
    )
    if len(attendance_counter) >= 2:
        errors.append(
            "出勤表包含多个项目，无法自动识别项目，请补充项目=xxx"
            f"（项目清单：{_format_project_counts(attendance_counter)}）"
        )
        return None
    attendance_project = (
        next(iter(attendance_counter.keys())) if len(attendance_counter) == 1 else None
    )

    payment_counter = (
        _collect_project_counts(payment_rows) if payment_rows is not None else Counter()
    )
    if attendance_project is None and len(payment_counter) >= 2:
        errors.append(
            "支付表包含多个项目，无法自动识别项目，请补充项目=xxx"
            f"（项目清单：{_format_project_counts(payment_counter)}）"
        )
        return None
    payment_project = (
        next(iter(payment_counter.keys())) if len(payment_counter) == 1 else None
    )

    if attendance_project and payment_project and attendance_project != payment_project:
        errors.append(
            "出勤表与支付表项目名不一致，无法自动识别项目："
            f"出勤表={attendance_project}，支付表={payment_project}"
        )
        return None
    resolved = attendance_project or payment_project
    if resolved:
        return resolved
    errors.append("未能自动识别项目，请补充项目=xxx")
    return None


def expand_wage_passphrase_commands(
    text: str,
    *,
    attendance_rows: Iterable[Mapping[str, str]] | None = None,
    payment_rows: Iterable[Mapping[str, str]] | None = None,
) -> tuple[list[str], list[str], list[str]]:
    expanded_lines: list[str] = []
    audit_lines: list[str] = []
    errors: list[str] = []
    state: _PassphraseState | None = None

    def finalize_state() -> None:
        nonlocal state
        if not state:
            return
        if not state.seen_marker:
            expanded_lines.extend(state.buffer_lines)
            state = None
            return
        if state.project_ended is None:
            errors.append("口令缺少字段：项目已结束=是/否")
            state = None
            return
        if not state.road_yes and not state.road_no:
            errors.append("路补=有/无 两组人员均为空，无法展开工资命令")
            state = None
            return
        conflict_keys = set(state.road_yes_names).intersection(state.road_no_names)
        if conflict_keys:
            conflict_display = []
            for key in conflict_keys:
                display_names = state.road_yes_names.get(key, []) + state.road_no_names.get(key, [])
                conflict_display.append("/".join(display_names))
            errors.append(f"路补名单冲突：{ '、'.join(conflict_display) }")
            state = None
            return
        project_name = state.project_name
        if not project_name:
            project_name = _resolve_project_name(attendance_rows, payment_rows, errors)
            if errors:
                state = None
                return
        leader_set = state.leader_keys
        road_no_counts = {"组长": 0, "组员": 0}
        road_yes_counts = {"组长": 0, "组员": 0}
        commands: list[str] = []
        for key, display in state.road_no:
            role = "组长" if key in leader_set else "组员"
            road_no_counts[role] += 1
            commands.append(
                f"工资：{display} {role} 项目已结束={'是' if state.project_ended else '否'} 路补=无"
                f"{f' 项目={project_name}' if project_name else ''}"
            )
        for key, display in state.road_yes:
            role = "组长" if key in leader_set else "组员"
            road_yes_counts[role] += 1
            commands.append(
                f"工资：{display} {role} 项目已结束={'是' if state.project_ended else '否'} 路补=有"
                f"{f' 项目={project_name}' if project_name else ''}"
            )
        expanded_lines.extend(commands)
        audit_lines.append("【口令展开审计】")
        audit_lines.append(
            "无路补：组长{0}人/组员{1}人；有路补：组长{2}人/组员{3}人".format(
                road_no_counts["组长"],
                road_no_counts["组员"],
                road_yes_counts["组长"],
                road_yes_counts["组员"],
            )
        )
        audit_lines.append(f"生成总条数 {len(commands)}")
        audit_lines.append("展开命令:")
        for command in commands:
            audit_lines.append(f"- {command}")
        state = None

    for raw_line in text.splitlines():
        if _is_ignored_line(raw_line):
            continue
        normalized = _normalize_line(raw_line)
        if not normalized:
            continue
        if _detect_mode(normalized) in {"single", "project"}:
            if state:
                finalize_state()
                if errors:
                    break
            expanded_lines.append(raw_line.strip())
            continue
        if normalized.startswith("角色") or normalized.startswith("固定日薪"):
            if state:
                finalize_state()
                if errors:
                    break
            expanded_lines.append(raw_line.strip())
            continue
        match = _match_passphrase_key(raw_line)
        if match:
            if state is None:
                state = _PassphraseState()
            state.buffer_lines.append(raw_line.strip())
            key, value = match
            if key == "project_ended":
                state.seen_marker = True
                parsed = _parse_bool(value)
                state.project_ended = parsed
            elif key == "project":
                state.project_name = value.strip()
            elif key == "leader":
                state.seen_marker = True
                state.current_target = "leader"
                leader_names = _split_names(value)
                for display in leader_names:
                    key_name = name_key(display)
                    if key_name not in state.leader_keys:
                        state.leader_keys.add(key_name)
                        state.leader_names.append(display)
            elif key == "road_yes":
                state.seen_marker = True
                state.current_target = "road_yes"
                _add_names(
                    _split_names(value),
                    entries=state.road_yes,
                    name_map=state.road_yes_names,
                )
            elif key == "road_no":
                state.seen_marker = True
                state.current_target = "road_no"
                _add_names(
                    _split_names(value),
                    entries=state.road_no,
                    name_map=state.road_no_names,
                )
            continue
        if state and state.current_target:
            names = _split_names(raw_line)
            if state.current_target == "leader":
                for display in names:
                    key_name = name_key(display)
                    if key_name not in state.leader_keys:
                        state.leader_keys.add(key_name)
                        state.leader_names.append(display)
            elif state.current_target == "road_yes":
                _add_names(names, entries=state.road_yes, name_map=state.road_yes_names)
            elif state.current_target == "road_no":
                _add_names(names, entries=state.road_no, name_map=state.road_no_names)
            state.buffer_lines.append(raw_line.strip())
            continue
        if state:
            finalize_state()
            if errors:
                break
        expanded_lines.append(raw_line.strip())

    if not errors:
        finalize_state()
    return expanded_lines, audit_lines, errors


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
    normalized_lines: list[tuple[int, str, str]] = []
    for line_no, raw_line in enumerate(raw_lines, start=1):
        normalized = _normalize_line(raw_line)
        if normalized:
            normalized_lines.append((line_no, raw_line, normalized))
    first_line = normalized_lines[0][2] if normalized_lines else ""
    mode = _detect_mode(first_line)
    role_overrides: dict[str, str] = {}
    fixed_daily_rates: dict[str, Decimal] = {}
    fixed_rate_names: dict[str, list[dict[str, object]]] = {}
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
                    source_line=normalized_lines[0][1],
                )
    if first_line:
        for key, value in _extract_kv_pairs(first_line):
            _apply_kv_mapping(
                result,
                key,
                value,
                source_line=normalized_lines[0][1],
            )

    block_mode: str | None = None
    for line_no, raw_line, line in normalized_lines[1:]:
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
                fixed_rate_names.setdefault(key, []).append(
                    {
                        "display_name": name.strip(),
                        "line_no": line_no,
                    }
                )
            continue
        for key, value in _extract_kv_pairs(line):
            _apply_kv_mapping(result, key, value, source_line=raw_line)

    result.pop("_road_cmd_source", None)
    for key, entries in fixed_rate_names.items():
        if len(entries) <= 1:
            continue
        display_names = sorted(
            {entry["display_name"] for entry in entries if entry.get("display_name")}
        )
        line_nos = sorted(
            {
                int(entry["line_no"])
                for entry in entries
                if isinstance(entry.get("line_no"), int)
            }
        )
        fixed_rate_conflicts.append(
            {
                "name_key": key,
                "display_names": display_names,
                "line_nos": line_nos,
            }
        )
        line_display = ",".join(str(item) for item in line_nos) if line_nos else "-"
        _append_command_error(
            result,
            "固定日薪姓名冲突: "
            f"name_key={key} "
            f"显示名={','.join(display_names)} "
            f"行号={line_display}",
        )
    if fixed_rate_conflicts:
        result["runtime_overrides"]["name_key_conflicts"] = fixed_rate_conflicts
    return result
