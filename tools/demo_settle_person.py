"""Demo entrypoint for wage settlement."""
from __future__ import annotations

import csv
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from wage.command import expand_wage_passphrase_commands, parse_command
from wage.settle_person import settle_person

ATTENDANCE_KEYWORDS = [
    "日期",
    "施工日期",
    "工作日期",
    "姓名",
    "施工人员",
    "实际出勤人员",
    "项目名",
    "项目",
    "项目名称",
    "是否施工",
    "出勤模式",
    "车辆",
    "车牌",
]
ATTENDANCE_STRONG_KEYWORDS = [
    "是否施工",
    "出勤模式",
    "车辆",
    "车牌",
    "施工人员",
    "实际出勤人员",
]
PAYMENT_KEYWORDS = [
    "报销类型",
    "费用类型",
    "报销人员",
    "姓名",
    "报销日期",
    "日期",
    "报销金额",
    "金额",
    "报销状态",
    "状态",
    "上传凭证",
    "凭证号",
    "报销说明",
    "备注",
    "项目",
    "项目名",
]
PAYMENT_STRONG_KEYWORDS = [
    "报销类型",
    "费用类型",
    "报销金额",
    "报销状态",
    "上传凭证",
    "凭证号",
    "报销说明",
]

ATTENDANCE_FIELD_CANDIDATES = {
    "日期": ["施工日期", "日期", "工作日期", "出勤日期"],
    "姓名": ["实际出勤人员", "施工人员", "出勤人员", "实际施工人员", "实际人员", "姓名"],
    "项目": ["项目", "项目名称"],
    "是否施工": ["是否施工", "今天是否施工", "是否施工?", "是否施工？"],
    "出勤模式": ["出勤模式", "出勤模式（填表用）", "配置出勤模式（引用）"],
}
PAYMENT_FIELD_CANDIDATES = {
    "日期": ["报销日期", "支付日期", "打款日期", "日期"],
    "姓名": ["报销人员", "姓名", "收款人", "人员"],
    "项目": ["项目", "项目名称"],
    "类型": ["报销类型", "类型", "费用类型", "科目", "类别", "费用类别"],
    "金额": ["报销金额", "金额", "支付金额", "实付金额"],
    "状态": ["报销状态", "状态", "付款状态"],
    "凭证": ["上传凭证", "凭证号", "凭证", "票据号", "流水号", "订单号"],
}

COMMON_SUFFIXES = [
    "出勤表",
    "施工表",
    "考勤表",
    "报销表",
    "支付表",
    "付款表",
    "支付记录",
    "_数据表_数据",
    "_表格",
    "_问卷",
    "_收集结果",
]


@dataclass(frozen=True)
class CsvCandidate:
    path: Path
    attendance_score: int
    attendance_strong_hits: int
    payment_score: int
    payment_strong_hits: int
    cleaned_headers: list[str]
    header_map: dict[str, str]
    mtime: float


ATTENDANCE_SCORE_THRESHOLD = 2
PAYMENT_SCORE_THRESHOLD = 2


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return list(reader)


def _read_headers(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        return next(reader, [])


def _clean_header(text: str) -> str:
    cleaned = (
        text.replace("\ufeff", "")
        .replace("（", "(")
        .replace("）", ")")
        .replace("　", " ")
    )
    cleaned = re.sub(r"\s+", " ", cleaned.strip())
    return cleaned


def _build_header_map(headers: list[str]) -> tuple[list[str], dict[str, str]]:
    cleaned_headers: list[str] = []
    header_map: dict[str, str] = {}
    for header in headers:
        cleaned = _clean_header(header)
        cleaned_headers.append(cleaned)
        header_map.setdefault(cleaned, header)
    return cleaned_headers, header_map


def _score_headers(headers: list[str], keywords: list[str]) -> int:
    hits: set[str] = set()
    for header in headers:
        for keyword in keywords:
            if keyword in header:
                hits.add(keyword)
    return len(hits)


def detect_table_role(path: Path) -> CsvCandidate:
    headers = _read_headers(path)
    cleaned_headers, header_map = _build_header_map(headers)
    return CsvCandidate(
        path=path,
        attendance_score=_score_headers(cleaned_headers, ATTENDANCE_KEYWORDS),
        attendance_strong_hits=_score_headers(cleaned_headers, ATTENDANCE_STRONG_KEYWORDS),
        payment_score=_score_headers(cleaned_headers, PAYMENT_KEYWORDS),
        payment_strong_hits=_score_headers(cleaned_headers, PAYMENT_STRONG_KEYWORDS),
        cleaned_headers=cleaned_headers,
        header_map=header_map,
        mtime=path.stat().st_mtime,
    )


def _scan_csv_candidates(data_dir: Path) -> list[CsvCandidate]:
    if not data_dir.exists():
        return []
    candidates: list[CsvCandidate] = []
    for path in data_dir.rglob("*.csv"):
        if not path.is_file():
            continue
        candidates.append(detect_table_role(path))
    return candidates


def _format_relative_path(path: Path, base_dir: Path) -> str:
    try:
        return str(path.relative_to(base_dir))
    except ValueError:
        return str(path)


def _format_mtime(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def _find_command_file(current_dir: Path, base_dir: Path) -> Path | None:
    if not current_dir.exists():
        print("请把口令.txt 放到 data/当前/（可放子目录）")
        print("示例口令：工资：王怀宇 组长 项目已结束=是 项目=溧马一溧芜设标-凌云")
        return None
    matches = sorted(current_dir.rglob("口令.txt"))
    if not matches:
        print("未找到口令文件，请创建 data/当前/口令.txt（UTF-8，可放子目录）")
        print("示例口令：工资：王怀宇 组长 项目已结束=是 项目=溧马一溧芜设标-凌云")
        return None
    if len(matches) > 1:
        print("【阻断｜口令】发现多个口令.txt，请只保留 1 份后重试：")
        for path in matches:
            rel_path = _format_relative_path(path, base_dir)
            print(f"- {rel_path}（mtime={_format_mtime(path.stat().st_mtime)}）")
        return None
    return matches[0]


def _resolve_input_paths(data_dir: Path) -> tuple[Path, Path] | None:
    current_dir = data_dir / "当前"
    if current_dir.exists():
        candidates = _scan_csv_candidates(current_dir)
        if not candidates:
            print("请把本次CSV拖到 数据/当前/（文件名随意，可放子目录）")
            return None
        selected = _select_input_paths(candidates)
        if selected is None:
            _print_blocking_reason(candidates, data_dir.parent)
            return None
        _print_selection_audit(selected[0], selected[1], data_dir.parent)
        return selected[0].path, selected[1].path

    attendance_path = data_dir / "attendance.csv"
    payment_path = data_dir / "payment.csv"
    if attendance_path.exists() and payment_path.exists():
        return attendance_path, payment_path

    candidates = _scan_csv_candidates(data_dir)
    selected = _select_input_paths(candidates)
    if selected is None:
        if not candidates:
            print("把 CSV 放到 data/ 目录下（文件名随意）")
        else:
            _print_blocking_reason(candidates, data_dir.parent)
        return None
    _print_selection_audit(selected[0], selected[1], data_dir.parent)
    return selected[0].path, selected[1].path


def _select_input_paths(
    candidates: list[CsvCandidate],
) -> tuple[CsvCandidate, CsvCandidate] | None:
    if not candidates:
        return None

    combined = [
        candidate
        for candidate in candidates
        if candidate.attendance_score >= ATTENDANCE_SCORE_THRESHOLD
        and candidate.attendance_strong_hits >= 1
        and candidate.payment_score >= PAYMENT_SCORE_THRESHOLD
        and candidate.payment_strong_hits >= 1
    ]
    if len(candidates) == 1 and len(combined) == 1:
        candidate = combined[0]
        return candidate, candidate
    if combined:
        return None

    attendance_candidates = [
        candidate
        for candidate in candidates
        if candidate.attendance_score >= ATTENDANCE_SCORE_THRESHOLD
        and candidate.attendance_strong_hits >= 1
    ]
    payment_candidates = [
        candidate
        for candidate in candidates
        if candidate.payment_score >= PAYMENT_SCORE_THRESHOLD
        and candidate.payment_strong_hits >= 1
    ]

    if len(attendance_candidates) == 1 and len(payment_candidates) == 1:
        attendance = attendance_candidates[0]
        payment = payment_candidates[0]
        if attendance.path != payment.path:
            return attendance, payment
    return None


def _summarize_headers(headers: list[str], limit: int = 30) -> str:
    if not headers:
        return "(空表头)"
    if len(headers) <= limit:
        return "｜".join(headers)
    return "｜".join(headers[:limit]) + f"...(共{len(headers)}列)"


def _match_header(
    cleaned_headers: list[str],
    header_map: dict[str, str],
    candidates: list[str],
) -> str | None:
    normalized_candidates = [_clean_header(item) for item in candidates]
    for candidate in normalized_candidates:
        for header in cleaned_headers:
            if header == candidate or candidate in header:
                return header_map.get(header, header)
    return None


def _build_field_mapping(candidate: CsvCandidate, mapping: dict[str, list[str]]) -> dict[str, str]:
    resolved: dict[str, str] = {}
    for field, candidates in mapping.items():
        matched = _match_header(candidate.cleaned_headers, candidate.header_map, candidates)
        resolved[field] = matched or "未命中"
    return resolved


def _print_selection_audit(
    attendance: CsvCandidate,
    payment: CsvCandidate,
    base_dir: Path,
) -> None:
    print("选表审计：")
    print(f"- 出勤表: {_format_relative_path(attendance.path, base_dir)}")
    print(f"- 报销表: {_format_relative_path(payment.path, base_dir)}")
    print(
        "- 出勤表命中: "
        f"出勤命中 {attendance.attendance_score}, "
        f"报销命中 {attendance.payment_score}, "
        f"差值 {attendance.attendance_score - attendance.payment_score}"
    )
    print(
        "- 报销表命中: "
        f"出勤命中 {payment.attendance_score}, "
        f"报销命中 {payment.payment_score}, "
        f"差值 {payment.payment_score - payment.attendance_score}"
    )
    attendance_headers = _summarize_headers(attendance.cleaned_headers)
    payment_headers = _summarize_headers(payment.cleaned_headers)
    print(f"- 出勤表表头(清洗): {attendance_headers}")
    print(f"- 报销表表头(清洗): {payment_headers}")
    attendance_mapping = _build_field_mapping(attendance, ATTENDANCE_FIELD_CANDIDATES)
    payment_mapping = _build_field_mapping(payment, PAYMENT_FIELD_CANDIDATES)
    print(
        "- 出勤表字段映射: "
        + "，".join(f"{key}={value}" for key, value in attendance_mapping.items())
    )
    print(
        "- 报销表字段映射: "
        + "，".join(f"{key}={value}" for key, value in payment_mapping.items())
    )


def _print_candidate_report(candidates: list[CsvCandidate], base_dir: Path) -> None:
    print("候选清单：")
    for candidate in sorted(candidates, key=lambda item: item.path.name):
        rel_path = _format_relative_path(candidate.path, base_dir)
        print(
            f"- {rel_path}: "
            f"mtime={_format_mtime(candidate.mtime)}, "
            f"出勤命中 {candidate.attendance_score}, "
            f"报销命中 {candidate.payment_score}, "
            f"表头: {_summarize_headers(candidate.cleaned_headers)}"
        )


def _print_blocking_reason(candidates: list[CsvCandidate], base_dir: Path) -> None:
    attendance_candidates = [
        candidate
        for candidate in candidates
        if candidate.attendance_score >= ATTENDANCE_SCORE_THRESHOLD
        and candidate.attendance_strong_hits >= 1
    ]
    payment_candidates = [
        candidate
        for candidate in candidates
        if candidate.payment_score >= PAYMENT_SCORE_THRESHOLD
        and candidate.payment_strong_hits >= 1
    ]
    combined_candidates = [
        candidate
        for candidate in candidates
        if candidate.attendance_score >= ATTENDANCE_SCORE_THRESHOLD
        and candidate.attendance_strong_hits >= 1
        and candidate.payment_score >= PAYMENT_SCORE_THRESHOLD
        and candidate.payment_strong_hits >= 1
    ]
    print("【阻断｜选表】无法唯一确定出勤/报销表。")
    if combined_candidates and len(candidates) > 1:
        print("检测到合并表候选，但同时存在其他CSV。")
    if not attendance_candidates:
        print("缺少可识别的施工/出勤表。")
    if not payment_candidates:
        print("缺少可识别的报销/支付表。")
    if len(attendance_candidates) > 1:
        print("发现多份施工/出勤候选表。")
    if len(payment_candidates) > 1:
        print("发现多份报销/支付候选表。")
    _print_candidate_report(candidates, base_dir)
    print("请把不需要的 CSV 移出 data/当前 后重试（不要求改名）。")


def _read_command_file(command_path: Path) -> str | None:
    if not command_path.exists():
        print("未找到口令文件，请创建 data/当前/口令.txt（UTF-8）")
        print("示例口令：工资：王怀宇 组长 项目已结束=是 项目=溧马一溧芜设标-凌云")
        return None
    return command_path.read_text(encoding="utf-8").strip()


def _read_runtime_overrides(config_path: Path) -> dict[str, int]:
    if not config_path.exists():
        return {}
    overrides: dict[str, int] = {}
    for line in config_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = re.search(
            r"\b("
            r"verbose|show_notes|show_checks|show_audit|"
            r"show_logs_in_compact|show_logs_in_detail"
            r")\s*[:=]\s*(\d+)\b",
            stripped,
        )
        if match:
            overrides[match.group(1)] = int(match.group(2))
    return overrides


def _append_audit_note(runtime_overrides: dict[str, object], note: str) -> None:
    notes = runtime_overrides.setdefault("audit_notes", [])
    if isinstance(notes, list) and note not in notes:
        notes.append(note)


def _derive_project_name(path: Path) -> str:
    name = path.stem
    name = re.sub(r"(\s*\(\d+\)|\s*（\d+）)$", "", name)
    for suffix in COMMON_SUFFIXES:
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return name.strip("-_")


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    data_dir = repo_root / "data"
    data_dir.mkdir(exist_ok=True)

    current_dir = data_dir / "当前"
    command_path = _find_command_file(current_dir, repo_root)
    if not command_path:
        return 0
    command_text = _read_command_file(command_path)
    if not command_text:
        return 0

    selected = _resolve_input_paths(data_dir)
    if selected is None:
        return 0

    attendance_rows = _read_csv(selected[0])
    payment_rows = _read_csv(selected[1])

    expanded_lines, audit_lines, errors = expand_wage_passphrase_commands(
        command_text,
        attendance_rows=attendance_rows,
        payment_rows=payment_rows,
    )
    if errors:
        print("【阻断｜口令解析】")
        print("阻断原因:")
        for error in errors:
            print(f"- {error}")
        return 0
    if audit_lines:
        print("\n".join(audit_lines))
        print()
    if not expanded_lines:
        return 0

    lines = [line.strip() for line in expanded_lines if line.strip()]
    wage_lines = [line for line in lines if line.startswith("工资：")]
    global_lines = [line for line in lines if not line.startswith("工资：")]

    def _run_single(command_source: str, *, print_output: bool = True) -> str:
        command = parse_command(command_source)
        if command.get("mode") == "project":
            from . import demo_settle_project

            demo_settle_project.main()
            return ""
        runtime_overrides = dict(command.get("runtime_overrides") or {})
        if command.get("project_name"):
            runtime_overrides["project_name_source"] = "command"
        if not command.get("project_name"):
            derived_project = _derive_project_name(selected[0])
            command["project_name"] = derived_project
            if derived_project:
                runtime_overrides["project_name_source"] = "derived"
                _append_audit_note(
                    runtime_overrides,
                    f"项目名未显式指定，已使用兜底：{derived_project}",
                )
        config_path = data_dir / "当前" / "配置.txt"
        runtime_overrides.update(_read_runtime_overrides(config_path))
        runtime_overrides["attendance_source"] = _format_relative_path(
            selected[0], repo_root
        )
        runtime_overrides["payment_source"] = _format_relative_path(
            selected[1], repo_root
        )

        output = settle_person(
            attendance_rows,
            payment_rows,
            person_name=command.get("person_name"),
            role=command.get("role"),
            project_ended=command.get("project_ended"),
            project_name=command.get("project_name"),
            runtime_overrides=runtime_overrides,
        )
        if print_output:
            print(output)
        return output

    if len(wage_lines) <= 1:
        _run_single("\n".join(lines))
        return 0

    temp_path = data_dir / "当前" / "._口令_单人临时.txt"
    try:
        outputs: list[str] = []
        for index, wage_line in enumerate(wage_lines):
            temp_content = "\n".join(global_lines + [wage_line])
            temp_path.write_text(temp_content, encoding="utf-8")
            temp_command_text = _read_command_file(temp_path)
            if temp_command_text:
                outputs.append(_run_single(temp_command_text, print_output=False))
        marker = "【压缩版】"
        detailed_parts: list[str] = []
        compact_parts: list[str] = []
        for text in outputs:
            if marker in text:
                detailed_part, compact_tail = text.split(marker, 1)
                detailed_parts.append(detailed_part.rstrip())
                compact_parts.append(marker + compact_tail)
            else:
                detailed_parts.append(text.rstrip())
                compact_parts.append("")
        for index, detailed_part in enumerate(detailed_parts):
            print(detailed_part)
            if index != len(detailed_parts) - 1:
                print()
        print("【压缩版合集】")
        for index, compact_part in enumerate(compact_parts):
            print(compact_part)
            if index != len(compact_parts) - 1:
                print()
    finally:
        if temp_path.exists():
            temp_path.unlink()
    return 0


if __name__ == "__main__":
    sys.exit(main())
