"""Demo entrypoint for wage settlement."""
from __future__ import annotations

import csv
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from wage.command import parse_command
from wage.settle_person import settle_person

ATTENDANCE_FIELDS = {
    "施工日期",
    "是否施工",
    "今天是否施工",
    "是否施工?",
    "是否施工？",
    "出勤",
    "施工人员",
    "实际施工人员",
    "实际出勤人员",
    "实际人员",
    "工作日期",
    "日期",
}
PAYMENT_FIELDS = {
    "报销日期",
    "报销金额",
    "报销状态",
    "报销类型",
    "费用类型",
    "上传凭证",
    "凭证号",
    "项目",
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
    payment_score: int
    mtime: float


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return list(reader)


def _read_headers(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        return next(reader, [])


def _score_headers(headers: list[str], fields: set[str]) -> int:
    return len(set(headers) & fields)


def _scan_csv_candidates(data_dir: Path) -> list[CsvCandidate]:
    candidates: list[CsvCandidate] = []
    for path in data_dir.iterdir():
        if not path.is_file() or path.suffix.lower() != ".csv":
            continue
        headers = _read_headers(path)
        candidates.append(
            CsvCandidate(
                path=path,
                attendance_score=_score_headers(headers, ATTENDANCE_FIELDS),
                payment_score=_score_headers(headers, PAYMENT_FIELDS),
                mtime=path.stat().st_mtime,
            )
        )
    return candidates


def _report_current_dir_overflow(candidates: list[CsvCandidate]) -> None:
    print("当前目录发现多个CSV：")
    for candidate in sorted(candidates, key=lambda item: item.path.name):
        print(f"- {candidate.path.name}")
    print("当前目录只保留 1(合并) 或 2(分开) 个CSV")


def _resolve_input_paths(data_dir: Path) -> tuple[Path, Path] | None:
    current_dir = data_dir / "当前"
    if current_dir.exists():
        candidates = _scan_csv_candidates(current_dir)
        if not candidates:
            print("请把本次CSV拖到 数据/当前/（文件名随意）")
            return None
        if len(candidates) > 2:
            _report_current_dir_overflow(candidates)
            return None
        selected = _select_input_paths(candidates)
        if selected is None:
            if len(candidates) == 1:
                print("当前目录只有 1 个 CSV，无法判定为合并表，请再放一份")
            else:
                _print_candidate_report(candidates)
            return None
        return selected

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
            _print_candidate_report(candidates)
        return None
    return selected


def _select_input_paths(candidates: list[CsvCandidate]) -> tuple[Path, Path] | None:
    combined = [
        candidate
        for candidate in candidates
        if candidate.attendance_score > 0 and candidate.payment_score > 0
    ]
    if combined:
        if len(combined) == 1:
            path = combined[0].path
            return path, path
        return None

    if not candidates:
        return None

    attendance_sorted = sorted(
        candidates,
        key=lambda candidate: (candidate.attendance_score, candidate.mtime),
        reverse=True,
    )
    payment_sorted = sorted(
        candidates,
        key=lambda candidate: (candidate.payment_score, candidate.mtime),
        reverse=True,
    )

    attendance_best = attendance_sorted[0]
    payment_best = payment_sorted[0]

    if attendance_best.attendance_score == 0 or payment_best.payment_score == 0:
        return None

    if len(attendance_sorted) > 1:
        runner_up = attendance_sorted[1]
        if (
            runner_up.attendance_score == attendance_best.attendance_score
            and runner_up.mtime == attendance_best.mtime
        ):
            return None

    if len(payment_sorted) > 1:
        runner_up = payment_sorted[1]
        if (
            runner_up.payment_score == payment_best.payment_score
            and runner_up.mtime == payment_best.mtime
        ):
            return None

    return attendance_best.path, payment_best.path


def _print_candidate_report(candidates: list[CsvCandidate]) -> None:
    print("无法唯一确定出勤/报销表，请只保留 1 出勤 + 1 报销或 1 合并表。")
    for candidate in sorted(candidates, key=lambda item: item.path.name):
        print(
            f"- {candidate.path.name}: "
            f"出勤命中 {candidate.attendance_score}, "
            f"报销命中 {candidate.payment_score}"
        )


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

    command_path = data_dir / "当前" / "口令.txt"
    command_text = _read_command_file(command_path)
    if not command_text:
        return 0

    selected = _resolve_input_paths(data_dir)
    if selected is None:
        return 0

    attendance_rows = _read_csv(selected[0])
    payment_rows = _read_csv(selected[1])

    lines = [line.strip() for line in command_text.splitlines() if line.strip()]
    wage_lines = [line for line in lines if line.startswith("工资：")]
    global_lines = [line for line in lines if not line.startswith("工资：")]

    def _run_single(command_source: str) -> int:
        command = parse_command(command_source)
        if command.get("mode") == "project":
            from . import demo_settle_project

            return demo_settle_project.main()
        if not command.get("project_name"):
            command["project_name"] = _derive_project_name(selected[0])

        runtime_overrides = dict(command.get("runtime_overrides") or {})
        config_path = data_dir / "当前" / "配置.txt"
        runtime_overrides.update(_read_runtime_overrides(config_path))
        runtime_overrides["attendance_source"] = selected[0].name
        runtime_overrides["payment_source"] = selected[1].name

        output = settle_person(
            attendance_rows,
            payment_rows,
            person_name=command.get("person_name"),
            role=command.get("role"),
            project_ended=command.get("project_ended"),
            project_name=command.get("project_name"),
            runtime_overrides=runtime_overrides,
        )
        print(output)
        return 0

    if len(wage_lines) <= 1:
        return _run_single(command_text)

    temp_path = data_dir / "当前" / "._口令_单人临时.txt"
    try:
        for index, wage_line in enumerate(wage_lines):
            temp_content = "\n".join(global_lines + [wage_line])
            temp_path.write_text(temp_content, encoding="utf-8")
            temp_command_text = _read_command_file(temp_path)
            if temp_command_text:
                _run_single(temp_command_text)
            if index != len(wage_lines) - 1:
                print()
    finally:
        if temp_path.exists():
            temp_path.unlink()
    return 0


if __name__ == "__main__":
    sys.exit(main())
