"""Attendance pipeline for wage settlement."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Mapping

DATE_HEADERS = ["日期", "施工日期", "工作日期", "出勤日期"]
NAME_HEADERS = ["姓名", "施工人员", "实际施工人员", "出勤人员"]
WORK_HEADERS = ["是否施工", "出勤", "施工"]
VEHICLE_HEADERS = ["车辆", "车辆信息", "车牌"]
PROJECT_HEADERS = ["项目", "项目名称"]


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
    fangzhuang_hits: list[str]
    auto_corrections: list[str]


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


def _is_work(value: str) -> bool:
    text = value.strip()
    return text in {"是", "施工", "出勤", "1", "Y", "y", "有"}


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
    vehicle_key = _find_header(headers, VEHICLE_HEADERS)
    project_key = _find_header(headers, PROJECT_HEADERS)

    missing_fields = []
    for key, label in (
        (date_key, "日期"),
        (name_key, "姓名"),
        (work_key, "是否施工"),
    ):
        if key is None:
            missing_fields.append(label)

    invalid_dates: list[str] = []
    project_mismatches: list[str] = []
    conflict_logs: list[str] = []
    normalization_logs: list[str] = []
    auto_corrections: list[str] = []
    fangzhuang_hits: list[str] = []

    person_day_status: dict[tuple[str, str], bool] = {}
    day_people_working: dict[str, set[str]] = {}
    day_people_any: dict[str, set[str]] = {}

    for row in rows:
        if date_key is None or name_key is None or work_key is None:
            continue
        date_value = row.get(date_key, "")
        parsed_date, raw_date = _parse_date(date_value)
        if parsed_date is None:
            invalid_dates.append(date_value)
            continue
        if raw_date:
            normalization_logs.append(
                f"日期格式标准化: '{raw_date}' -> '{parsed_date}'"
            )
        name_value = row.get(name_key, "").strip()
        if not name_value:
            continue
        work_value = row.get(work_key, "")
        is_work = _is_work(work_value)
        vehicle_value = row.get(vehicle_key, "").strip() if vehicle_key else ""
        if vehicle_value and "防撞" in vehicle_value:
            fangzhuang_hits.append(f"{name_value}@{parsed_date}:{vehicle_value}")
        raw_project = row.get(project_key, "").strip() if project_key else ""
        if project_name and raw_project and raw_project != project_name:
            project_mismatches.append(f"{name_value}@{parsed_date}: {raw_project}")

        key = (name_value, parsed_date)
        if key in person_day_status:
            if person_day_status[key] is False and is_work is True:
                person_day_status[key] = True
                conflict_logs.append(
                    f"同日冲突: {name_value} {parsed_date} 未施工->施工 (施工优先)"
                )
                auto_corrections.append(
                    f"冲突消解: {name_value} {parsed_date} 按施工优先"
                )
            elif person_day_status[key] is True and is_work is False:
                conflict_logs.append(
                    f"同日冲突: {name_value} {parsed_date} 施工保持"
                )
            continue
        person_day_status[key] = is_work

        day_people_any.setdefault(parsed_date, set()).add(name_value)
        if is_work:
            day_people_working.setdefault(parsed_date, set()).add(name_value)

    mode_by_date: dict[str, str] = {}
    for date in sorted(day_people_any.keys()):
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
        for date, mode in mode_by_date.items():
            worked = person_day_status.get((target_person, date), False)
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
        fangzhuang_hits=fangzhuang_hits,
        auto_corrections=auto_corrections,
    )
