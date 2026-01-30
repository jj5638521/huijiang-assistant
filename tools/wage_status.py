"""工资出单状态盘点/自检报告工具."""
from __future__ import annotations

import csv
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from wage.ruleset import get_ruleset_version

ATTENDANCE_KEYWORDS = [
    "施工日期",
    "是否施工",
    "出勤模式",
    "组长",
    "驾驶员",
    "辅助",
    "实际出勤人数",
    "实际出勤人员",
]
PAYMENT_KEYWORDS = [
    "报销类型",
    "报销人员",
    "报销日期",
    "报销金额",
    "报销状态",
    "上传凭证",
    "报销说明",
    "凭证号",
    "金额",
    "状态",
]

ONLY_MODE_HINTS = ["ONLY", "极简", "00_出勤", "99_报销"]
PROJECT_POOL_HINTS = ["2026年-项目池_施工表", "2026年-项目池_报销表"]


@dataclass(frozen=True)
class CsvCandidate:
    path: Path
    attendance_score: int
    payment_score: int
    cleaned_headers: list[str]


def _run_git(args: list[str]) -> str:
    try:
        output = subprocess.check_output(["git", *args], text=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "(无法获取)"
    return output.strip()


def _resolve_repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _clean_header(text: str) -> str:
    cleaned = (
        text.replace("\ufeff", "")
        .replace("（", "(")
        .replace("）", ")")
        .replace("　", " ")
    )
    cleaned = re.sub(r"\s+", " ", cleaned.strip())
    return cleaned


def _read_headers(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        return next(reader, [])


def _score_headers(headers: list[str], keywords: list[str]) -> int:
    hits: set[str] = set()
    for header in headers:
        for keyword in keywords:
            if keyword in header:
                hits.add(keyword)
    return len(hits)


def _detect_table_role(path: Path) -> CsvCandidate:
    headers = [_clean_header(item) for item in _read_headers(path)]
    return CsvCandidate(
        path=path,
        attendance_score=_score_headers(headers, ATTENDANCE_KEYWORDS),
        payment_score=_score_headers(headers, PAYMENT_KEYWORDS),
        cleaned_headers=headers,
    )


def _summarize_headers(headers: list[str], limit: int = 30) -> str:
    if not headers:
        return "(空表头)"
    if len(headers) <= limit:
        return "｜".join(headers)
    return "｜".join(headers[:limit]) + f"...(共{len(headers)}列)"


def _scan_csv_candidates(data_dir: Path) -> list[CsvCandidate]:
    candidates: list[CsvCandidate] = []
    for path in sorted(data_dir.iterdir()):
        if path.is_file() and path.suffix.lower() == ".csv":
            candidates.append(_detect_table_role(path))
    return candidates


def _select_input_paths(
    candidates: list[CsvCandidate],
) -> tuple[CsvCandidate, CsvCandidate] | None:
    combined = [
        candidate
        for candidate in candidates
        if candidate.attendance_score >= 2 and candidate.payment_score >= 2
    ]
    if combined:
        if len(combined) == 1:
            candidate = combined[0]
            return candidate, candidate
        return None

    if not candidates:
        return None

    if len(candidates) == 2:
        attendance_sorted = sorted(
            candidates,
            key=lambda candidate: candidate.attendance_score - candidate.payment_score,
            reverse=True,
        )
        payment_sorted = sorted(
            candidates,
            key=lambda candidate: candidate.payment_score - candidate.attendance_score,
            reverse=True,
        )
        attendance_best = attendance_sorted[0]
        payment_best = payment_sorted[0]
        attendance_delta = attendance_best.attendance_score - attendance_best.payment_score
        payment_delta = payment_best.payment_score - payment_best.attendance_score
        if (
            attendance_delta > 0
            and payment_delta > 0
            and attendance_best.path != payment_best.path
        ):
            return attendance_best, payment_best
        return None

    attendance_sorted = sorted(
        candidates,
        key=lambda candidate: candidate.attendance_score,
        reverse=True,
    )
    payment_sorted = sorted(
        candidates,
        key=lambda candidate: candidate.payment_score,
        reverse=True,
    )

    attendance_best = attendance_sorted[0]
    payment_best = payment_sorted[0]

    if attendance_best.attendance_score < 2 or payment_best.payment_score < 2:
        return None

    if len(attendance_sorted) > 1:
        runner_up = attendance_sorted[1]
        if runner_up.attendance_score == attendance_best.attendance_score:
            return None

    if len(payment_sorted) > 1:
        runner_up = payment_sorted[1]
        if runner_up.payment_score == payment_best.payment_score:
            return None

    return attendance_best, payment_best


def _resolve_mode(candidates: list[CsvCandidate]) -> tuple[str, str]:
    names = [candidate.path.name for candidate in candidates]
    if len(candidates) == 2 and all(
        any(hint in name for hint in ONLY_MODE_HINTS) for name in names
    ):
        return "A) ONLY/极简双表模式", "文件名包含 ONLY/极简/00_出勤/99_报销 且仅2个CSV"

    if any(any(hint in name for hint in PROJECT_POOL_HINTS) for name in names):
        return "B) 项目池原表模式", "文件名包含 2026年-项目池_施工表/报销表"

    if len(candidates) == 1:
        candidate = candidates[0]
        if candidate.attendance_score >= 2 and candidate.payment_score >= 2:
            return "C) 合并表模式", "单CSV且出勤+报销锚点同时命中"

    return "未知/需确认", "未命中 ONLY/项目池/合并表判定规则"


def _print_csv_scan(candidates: list[CsvCandidate]) -> None:
    if not candidates:
        print("- CSV列表: 无")
        return
    print("- CSV列表:")
    for candidate in candidates:
        size = candidate.path.stat().st_size
        headers = _summarize_headers(candidate.cleaned_headers)
        print(f"  * 文件名: {candidate.path.name}")
        print(f"    大小: {size} bytes")
        print(f"    表头(前30列): {headers}")
        print(
            "    锚点命中: "
            f"出勤 {candidate.attendance_score}, "
            f"报销 {candidate.payment_score}"
        )


def _print_selection_audit(
    candidates: list[CsvCandidate],
    selected: tuple[CsvCandidate, CsvCandidate] | None,
) -> None:
    print("选表审计：")
    if not candidates:
        print("- 当前无CSV候选，无法选表")
        return
    for candidate in sorted(candidates, key=lambda item: item.path.name):
        attendance_delta = candidate.attendance_score - candidate.payment_score
        payment_delta = candidate.payment_score - candidate.attendance_score
        print(
            "- 候选: "
            f"{candidate.path.name} | "
            f"出勤命中 {candidate.attendance_score}, "
            f"报销命中 {candidate.payment_score}, "
            f"差值分 出勤-报销 {attendance_delta}, "
            f"报销-出勤 {payment_delta}"
        )
    if selected is None:
        print("- 选表结果: 阻断")
        print("- 阻断原因: 选表歧义或命中不足，请只保留 1 出勤 + 1 报销或 1 合并表")
        return
    attendance, payment = selected
    print(f"- 选表结果: 出勤表={attendance.path.name} ｜ 报销表={payment.path.name}")


def main() -> int:
    repo_root = _resolve_repo_root()
    data_dir = repo_root / "data"
    current_dir = data_dir / "当前"

    print("工资出单状态盘点/自检报告")

    branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"])
    latest_commit = _run_git(["log", "-1", "--oneline"])
    dirty = _run_git(["status", "--porcelain"]) != ""

    print("一、当前代码版本")
    print(f"- 最近1个commit: {latest_commit}")
    print(f"- 分支名: {branch}")
    print(f"- 是否dirty: {'是' if dirty else '否'}")

    print("二、规则版本号")
    try:
        rules_version = get_ruleset_version()
    except (FileNotFoundError, ValueError):
        rules_version = "未知"
    print(f"- 计算口径版本: {rules_version}")

    print("三、最近20条提交摘要")
    log_output = _run_git(["log", "-20", "--oneline"])
    if log_output == "(无法获取)":
        print("- (无法获取)")
    else:
        for line in log_output.splitlines():
            print(f"- {line}")

    print("四、数据目录扫描结果")
    if current_dir.exists():
        if current_dir.is_symlink():
            resolved = current_dir.resolve()
            print(f"- data/当前(软链接→真实路径): {resolved}")
        else:
            print(f"- data/当前: {current_dir}")
        scan_dir = current_dir
    else:
        print("- data/当前: (不存在)")
        scan_dir = current_dir

    command_file = scan_dir / "口令.txt"
    print(f"- 口令.txt: {'存在' if command_file.exists() else '不存在'}")

    candidates = _scan_csv_candidates(scan_dir) if scan_dir.exists() else []
    _print_csv_scan(candidates)

    print("五、运行模式判定")
    mode, reason = _resolve_mode(candidates)
    print(f"- 模式: {mode}")
    print(f"- 依据: {reason}")

    print("六、选表审计")
    selected = _select_input_paths(candidates)
    _print_selection_audit(candidates, selected)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
