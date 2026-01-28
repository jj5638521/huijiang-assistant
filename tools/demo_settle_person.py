"""Demo entrypoint for wage settlement."""
from __future__ import annotations

import csv
import sys
from dataclasses import dataclass
from pathlib import Path

from wage.settle_person import settle_person

ATTENDANCE_FIELDS = {
    "施工日期",
    "是否施工",
    "出勤",
    "施工人员",
    "实际施工人员",
    "工作日期",
}
PAYMENT_FIELDS = {
    "报销日期",
    "报销金额",
    "报销状态",
    "报销类型",
    "费用类型",
    "上传凭证",
    "凭证号",
}


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return list(reader)


@dataclass(frozen=True)
class CsvCandidate:
    path: Path
    attendance_score: int
    payment_score: int
    mtime: float


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


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    data_dir = repo_root / "data"
    data_dir.mkdir(exist_ok=True)
    attendance_path = data_dir / "attendance.csv"
    payment_path = data_dir / "payment.csv"

    if attendance_path.exists() and payment_path.exists():
        selected = (attendance_path, payment_path)
    else:
        candidates = _scan_csv_candidates(data_dir)
        selected = _select_input_paths(candidates)
        if selected is None:
            if not candidates:
                print("把 CSV 放到 data/ 目录下（文件名随意）")
            else:
                _print_candidate_report(candidates)
            return 0

    attendance_rows = _read_csv(selected[0])
    payment_rows = _read_csv(selected[1])

    result = settle_person(attendance_rows, payment_rows)
    print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
