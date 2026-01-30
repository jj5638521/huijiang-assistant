from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def _write_csv(path: Path, headers: list[str]) -> None:
    content = ",".join(headers) + "\n"
    path.write_text(content, encoding="utf-8")


def test_wage_status_only_mode(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    data_current = repo_root / "data" / "当前"
    backup_dir = None
    if data_current.exists():
        backup_dir = tmp_path / "当前_backup"
        if backup_dir.exists():
            shutil.rmtree(backup_dir)
        data_current.rename(backup_dir)

    data_current.mkdir(parents=True, exist_ok=True)
    try:
        attendance_csv = data_current / "00_出勤_ONLY.csv"
        payment_csv = data_current / "99_报销_ONLY.csv"
        _write_csv(attendance_csv, ["施工日期", "是否施工", "实际出勤人员"])
        _write_csv(payment_csv, ["报销日期", "报销人员", "报销金额", "报销类型", "报销状态"])

        result = subprocess.run(
            [sys.executable, "-m", "tools.wage_status"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0
        assert "ONLY/极简双表模式" in result.stdout
        assert "选表审计" in result.stdout
        assert "出勤命中" in result.stdout
    finally:
        if data_current.exists():
            shutil.rmtree(data_current)
        if backup_dir is not None:
            backup_dir.rename(data_current)
