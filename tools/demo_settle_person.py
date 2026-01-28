"""Demo entrypoint for wage settlement."""
from __future__ import annotations

import csv
import sys
from pathlib import Path

from wage.settle_person import settle_person


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader)


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    attendance_path = repo_root / "data" / "attendance.csv"
    payment_path = repo_root / "data" / "payment.csv"

    missing = [path for path in (attendance_path, payment_path) if not path.exists()]
    if missing:
        print("把文件放到 data/attendance.csv 与 data/payment.csv")
        return 0

    attendance_rows = _read_csv(attendance_path)
    payment_rows = _read_csv(payment_path)

    result = settle_person(attendance_rows, payment_rows)
    print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
