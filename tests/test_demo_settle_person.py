from pathlib import Path

from tools import demo_settle_person


def _write_csv(path: Path, headers: list[str]) -> None:
    content = ",".join(headers)
    path.write_text(f"{content}\n", encoding="utf-8")


def test_selects_combined_csv(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    combined = data_dir / "combined.csv"
    _write_csv(
        combined,
        ["施工日期", "报销日期", "报销金额"],
    )

    candidates = demo_settle_person._scan_csv_candidates(data_dir)
    selected = demo_settle_person._select_input_paths(candidates)

    assert selected == (combined, combined)


def test_selects_separate_csvs(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    attendance = data_dir / "attendance_any.csv"
    payment = data_dir / "payment_any.csv"
    _write_csv(attendance, ["施工日期", "是否施工", "施工人员"])
    _write_csv(payment, ["报销日期", "报销金额", "报销状态"])

    candidates = demo_settle_person._scan_csv_candidates(data_dir)
    selected = demo_settle_person._select_input_paths(candidates)

    assert selected == (attendance, payment)
