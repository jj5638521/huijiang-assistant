"""Attendance pipeline for wage settlement."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Mapping

DATE_HEADERS = ["日期", "施工日期", "工作日期", "出勤日期"]
NAME_HEADERS = [
    "姓名",
    "施工人员",
    "实际施工人员",
    "出勤人员",
    "实际出勤人员",
    "实际人员",
]
WORK_HEADERS = ["是否施工", "出勤", "施工", "今天是否施工", "是否施工?", "是否施工？"]
VEHICLE_HEADERS = ["车辆", "车辆信息", "车牌"]
PROJECT_HEADERS = ["项目", "项目名称"]
ROLE_HEADERS = ["角色", "职务", "岗位"]
MODE_HEADERS = ["出勤模式", "出勤模式（填表用）", "配置出勤模式（引用）"]
ROSTER_HEADERS = [
    "组长(自动)",
    "设标车驾驶员(默认)",
    "防撞车驾驶员(默认)",
    "辅助1(固定)",
    "辅助2(固定)",
]
PAYMENT_ANCHOR_TOKENS = [
    "报销类型",
    "费用类型",
    "类别",
    "科目",
    "报销状态",
    "支付状态",
    "报销结果",
    "金额",
    "报销金额",
    "凭证",
    "票据",
    "流水",
    "订单",
]


@dataclass(frozen=True)
class AttendanceRowInfo:
    date: str
    name: str
    is_work: bool
    raw_vehicle: str
    raw_project: str


@dataclass(frozen=True)
class AttendanceResult:
    date_sets: dict[str, list[str]]
    mode_by_date: dict[str, str]
    missing_fields: list[str]
    invalid_dates: list[str]
    project_mismatches: list[str]
    conflict_logs: list[str]
    normalization_logs: list[str]
    has_vehicle_field: bool
    has_explicit_mode: bool
    fangzhuang_hits: list[str]
    auto_corrections: list[str]
    role_by_person: dict[str, str]


def _find_header(headers: set[str], candidates: list[str]) -> str | None:
    for candidate in candidates:
        if candidate in headers:
            return candidate
    return None


def _parse_date(value: str) -> tuple[str | None, str | None]:
    raw = value.strip()
    if not raw:
        return None, None
    normalized = raw
    normalized = normalized.replace("年", "-").replace("月", "-").replace("日", "")
    normalized = normalized.replace("/", "-").replace(".", "-")
    normalized = "-".join(part for part in normalized.split("-") if part)
    for fmt in ("%Y-%m-%d", "%Y-%m-%d", "%Y%m%d"):
        try:
            parsed = datetime.strptime(normalized, fmt)
        except ValueError:
            continue
        result = parsed.strftime("%Y-%m-%d")
        if result != raw:
            return result, raw
        return result, None
    return None, raw


def _find_payment_anchor_headers(headers: set[str]) -> list[str]:
    return [
        header
        for header in headers
        if any(token in header for token in PAYMENT_ANCHOR_TOKENS)
    ]


def _normalize_role(value: str) -> str | None:
    text = value.strip()
    if not text:
        return None
    if "组长" in text:
        return "组长"
    if "组员" in text:
        return "组员"
    return None


def _is_work(value: str) -> bool:
    text = value.strip()
    return text in {"是", "施工", "出勤", "1", "Y", "y", "有"}


def _split_names(raw: str) -> list[str]:
    cleaned = raw.strip()
    if not cleaned:
        return []
    parts = [part for part in re.split(r"[、，,;；\s]+", cleaned) if part]
    if not parts:
        return [cleaned]
    seen: set[str] = set()
    deduped: list[str] = []
    for part in parts:
        if part not in seen:
            seen.add(part)
            deduped.append(part)
    return deduped


def _collect_row_names(
    row: Mapping[str, str],
    name_key: str | None,
    roster_keys: list[str],
) -> tuple[list[str], str]:
    primary_value = row.get(name_key, "").strip() if name_key else ""
    if primary_value:
        names = _split_names(primary_value)
        return names, primary_value
    roster_values = [
        row.get(key, "").strip()
        for key in roster_keys
        if row.get(key, "").strip()
    ]
    names: list[str] = []
    seen: set[str] = set()
    for value in roster_values:
        for name in _split_names(value):
            if name not in seen:
                seen.add(name)
                names.append(name)
    return names, ""


def compute_attendance(
    attendance_rows: Iterable[Mapping[str, str]],
    project_name: str | None,
    target_person: str | None,
) -> AttendanceResult:
    rows = list(attendance_rows)
    headers = {key.strip() for row in rows for key in row.keys()}
    date_key = _find_header(headers, DATE_HEADERS)
    name_key = _find_header(headers, NAME_HEADERS)
    work_key = _find_header(headers, WORK_HEADERS)
    if work_key is None:
        for header in headers:
            if "是否施工" in header:
                work_key = header
                break
    vehicle_key = _find_header(headers, VEHICLE_HEADERS)
    project_key = _find_header(headers, PROJECT_HEADERS)
    role_key = _find_header(headers, ROLE_HEADERS)
    mode_key = _find_header(headers, MODE_HEADERS)
    roster_keys = [key for key in ROSTER_HEADERS if key in headers]
    payment_anchor_keys = _find_payment_anchor_headers(headers)

    missing_fields = []
    for key, label in (
        (date_key, "日期"),
        (name_key, "姓名"),
        (work_key, "是否施工"),
    ):
        if key is None:
            missing_fields.append(label)
    if name_key is None and roster_keys:
        missing_fields = [item for item in missing_fields if item != "姓名"]

    invalid_dates: list[str] = []
    project_mismatches: list[str] = []
    conflict_logs: list[str] = []
    normalization_logs: list[str] = []
    auto_corrections: list[str] = []
    fangzhuang_hits: list[str] = []
    role_by_person: dict[str, str] = {}

    person_day_status: dict[tuple[str, str], bool] = {}
    day_people_working: dict[str, set[str]] = {}
    day_people_any: dict[str, set[str]] = {}
    explicit_mode_by_date: dict[str, str] = {}

    for row in rows:
        if date_key is None or name_key is None or work_key is None:
            continue
        work_value = row.get(work_key, "")
        if not work_value.strip() and payment_anchor_keys:
            if any(row.get(key, "").strip() for key in payment_anchor_keys):
                continue
        date_value = row.get(date_key, "")
        parsed_date, raw_date = _parse_date(date_value)
        if parsed_date is None:
            if date_value.strip():
                invalid_dates.append(date_value)
            continue
        if raw_date:
            normalization_logs.append(
                f"日期格式标准化: '{raw_date}' -> '{parsed_date}'"
            )
        name_list, primary_name_value = _collect_row_names(
            row, name_key, roster_keys
        )
        if not name_list:
            continue
        if primary_name_value and len(name_list) > 1:
            normalization_logs.append(
                f"姓名拆分: '{primary_name_value}' -> '{'、'.join(name_list)}'"
            )
        is_work = _is_work(work_value)
        vehicle_value = row.get(vehicle_key, "").strip() if vehicle_key else ""
        role_value = row.get(role_key, "").strip() if role_key else ""
        normalized_role = _normalize_role(role_value)
        mode_value = row.get(mode_key, "").strip() if mode_key else ""
        if mode_value:
            mode_label = "单防撞" if "单防撞" in mode_value else "全组"
            existing_mode = explicit_mode_by_date.get(parsed_date)
            if existing_mode != "单防撞":
                explicit_mode_by_date[parsed_date] = mode_label
        if vehicle_value and "防撞" in vehicle_value:
            for name in name_list:
                fangzhuang_hits.append(f"{name}@{parsed_date}:{vehicle_value}")
        raw_project = row.get(project_key, "").strip() if project_key else ""
        for name in name_list:
            if normalized_role:
                existing_role = role_by_person.get(name)
                if existing_role and existing_role != normalized_role:
                    selected_role = (
                        "组长" if "组长" in {existing_role, normalized_role} else existing_role
                    )
                    role_by_person[name] = selected_role
                    auto_corrections.append(
                        f"角色冲突: {name} {existing_role}->{selected_role} (组长优先)"
                    )
                else:
                    role_by_person[name] = normalized_role
            if project_name and raw_project and raw_project != project_name:
                project_mismatches.append(f"{name}@{parsed_date}: {raw_project}")

            key = (name, parsed_date)
            if key in person_day_status:
                if person_day_status[key] is False and is_work is True:
                    person_day_status[key] = True
                    conflict_logs.append(
                        f"同日冲突: {name} {parsed_date} 未施工->施工 (施工优先)"
                    )
                    auto_corrections.append(
                        f"冲突消解: {name} {parsed_date} 按施工优先"
                    )
                elif person_day_status[key] is True and is_work is False:
                    conflict_logs.append(
                        f"同日冲突: {name} {parsed_date} 施工保持"
                    )
                continue
            person_day_status[key] = is_work

            day_people_any.setdefault(parsed_date, set()).add(name)
            if is_work:
                day_people_working.setdefault(parsed_date, set()).add(name)

    mode_by_date: dict[str, str] = {}
    for date in sorted(day_people_any.keys()):
        explicit_mode = explicit_mode_by_date.get(date)
        if explicit_mode:
            mode = explicit_mode
        else:
            working = day_people_working.get(date, set())
            count = len(working)
            if 1 <= count <= 2:
                mode = "单防撞"
            elif count >= 3:
                mode = "全组"
            else:
                mode = "全组"
        mode_by_date[date] = mode

    date_sets = {
        "单防撞｜出勤": [],
        "单防撞｜未出勤": [],
        "全组｜出勤": [],
        "全组｜未出勤": [],
    }

    if target_person:
        person_dates = sorted(
            {
                date
                for (name, date), _ in person_day_status.items()
                if name == target_person
            }
        )
        for date in person_dates:
            mode = mode_by_date.get(date, "全组")
            worked = person_day_status[(target_person, date)]
            if mode == "单防撞":
                if worked:
                    date_sets["单防撞｜出勤"].append(date)
                else:
                    date_sets["单防撞｜未出勤"].append(date)
            else:
                if worked:
                    date_sets["全组｜出勤"].append(date)
                else:
                    date_sets["全组｜未出勤"].append(date)

    for key in list(date_sets.keys()):
        date_sets[key] = sorted(set(date_sets[key]))

    return AttendanceResult(
        date_sets=date_sets,
        mode_by_date=mode_by_date,
        missing_fields=missing_fields,
        invalid_dates=invalid_dates,
        project_mismatches=project_mismatches,
        conflict_logs=conflict_logs,
        normalization_logs=normalization_logs,
        has_vehicle_field=vehicle_key is not None,
        has_explicit_mode=bool(explicit_mode_by_date),
        fangzhuang_hits=fangzhuang_hits,
        auto_corrections=auto_corrections,
        role_by_person=role_by_person,
    )


def collect_attendance_people(
    attendance_rows: Iterable[Mapping[str, str]],
    project_name: str | None,
) -> set[str]:
    rows = list(attendance_rows)
    headers = {key.strip() for row in rows for key in row.keys()}
    name_key = _find_header(headers, NAME_HEADERS)
    project_key = _find_header(headers, PROJECT_HEADERS)
    roster_keys = [key for key in ROSTER_HEADERS if key in headers]
    if name_key is None and not roster_keys:
        return set()
    people: set[str] = set()
    for row in rows:
        name_list, _ = _collect_row_names(row, name_key, roster_keys)
        if not name_list:
            continue
        raw_project = row.get(project_key, "").strip() if project_key else ""
        if project_name and raw_project and raw_project != project_name:
            continue
        for name in name_list:
            people.add(name)
    return people
