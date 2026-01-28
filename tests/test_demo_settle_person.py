from pathlib import Path

from tools import demo_settle_person


def _write_csv(path: Path, headers: list[str]) -> None:
    content = ",".join(headers)
    path.write_text(f"{content}\n", encoding="utf-8")


def test_current_dir_empty(tmp_path: Path, capsys: object) -> None:
    data_dir = tmp_path / "data"
    current_dir = data_dir / "当前"
    current_dir.mkdir(parents=True)

    selected = demo_settle_person._resolve_input_paths(data_dir)

    assert selected is None
    captured = capsys.readouterr()
    assert "请把本次CSV拖到 数据/当前/（文件名随意）" in captured.out


def test_current_dir_single_combined(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    current_dir = data_dir / "当前"
    current_dir.mkdir(parents=True)
    combined = current_dir / "combined.csv"
    _write_csv(combined, ["施工日期", "报销日期", "报销金额"])

    selected = demo_settle_person._resolve_input_paths(data_dir)

    assert selected == (combined, combined)


def test_current_dir_single_non_combined(tmp_path: Path, capsys: object) -> None:
    data_dir = tmp_path / "data"
    current_dir = data_dir / "当前"
    current_dir.mkdir(parents=True)
    attendance = current_dir / "attendance.csv"
    _write_csv(attendance, ["施工日期", "是否施工", "施工人员"])

    selected = demo_settle_person._resolve_input_paths(data_dir)

    assert selected is None
    captured = capsys.readouterr()
    assert "当前目录只有 1 个 CSV，无法判定为合并表，请再放一份" in captured.out


def test_current_dir_two_csvs(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    current_dir = data_dir / "当前"
    current_dir.mkdir(parents=True)
    attendance = current_dir / "attendance_any.csv"
    payment = current_dir / "payment_any.csv"
    _write_csv(attendance, ["施工日期", "是否施工", "施工人员"])
    _write_csv(payment, ["报销日期", "报销金额", "报销状态"])

    selected = demo_settle_person._resolve_input_paths(data_dir)

    assert selected == (attendance, payment)


def test_current_dir_overflow(tmp_path: Path, capsys: object) -> None:
    data_dir = tmp_path / "data"
    current_dir = data_dir / "当前"
    current_dir.mkdir(parents=True)
    for index in range(3):
        _write_csv(current_dir / f"file_{index}.csv", ["施工日期"])

    selected = demo_settle_person._resolve_input_paths(data_dir)

    assert selected is None
    captured = capsys.readouterr()
    assert "当前目录只保留 1(合并) 或 2(分开) 个CSV" in captured.out


def test_archive_ignored_when_fallback(tmp_path: Path, capsys: object) -> None:
    data_dir = tmp_path / "data"
    archive_dir = data_dir / "归档"
    archive_dir.mkdir(parents=True)
    _write_csv(archive_dir / "archived.csv", ["施工日期", "报销日期"])

    selected = demo_settle_person._resolve_input_paths(data_dir)

    assert selected is None
    captured = capsys.readouterr()
    assert "把 CSV 放到 data/ 目录下（文件名随意）" in captured.out


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


def test_current_dir_empty_prompts_upload(tmp_path: Path, capsys: object) -> None:
    data_dir = tmp_path / "data"
    current_dir = data_dir / "当前"
    current_dir.mkdir(parents=True)

    selected = demo_settle_person._select_inputs(tmp_path)

    assert selected is None
    captured = capsys.readouterr().out
    assert "请把本次CSV拖到 数据/当前/（文件名随意）" in captured


def test_current_dir_single_combined_csv(tmp_path: Path, capsys: object) -> None:
    data_dir = tmp_path / "data"
    current_dir = data_dir / "当前"
    current_dir.mkdir(parents=True)
    combined = current_dir / "combined.csv"
    _write_csv(combined, ["施工日期", "报销日期", "报销金额"])

    selected = demo_settle_person._select_inputs(tmp_path)

    assert selected == (combined, combined)
    captured = capsys.readouterr().out
    assert f"出勤表: {combined}" in captured
    assert f"报销表: {combined}" in captured


def test_current_dir_single_non_combined_csv(tmp_path: Path, capsys: object) -> None:
    data_dir = tmp_path / "data"
    current_dir = data_dir / "当前"
    current_dir.mkdir(parents=True)
    attendance = current_dir / "attendance_only.csv"
    _write_csv(attendance, ["施工日期", "是否施工", "施工人员"])

    selected = demo_settle_person._select_inputs(tmp_path)

    assert selected is None
    captured = capsys.readouterr().out
    assert "未识别为合并表" in captured


def test_current_dir_two_csvs_selects_pair(tmp_path: Path, capsys: object) -> None:
    data_dir = tmp_path / "data"
    current_dir = data_dir / "当前"
    current_dir.mkdir(parents=True)
    attendance = current_dir / "attendance.csv"
    payment = current_dir / "payment.csv"
    _write_csv(attendance, ["施工日期", "是否施工", "施工人员"])
    _write_csv(payment, ["报销日期", "报销金额", "报销状态"])

    selected = demo_settle_person._select_inputs(tmp_path)

    assert selected == (attendance, payment)
    captured = capsys.readouterr().out
    assert f"出勤表: {attendance}" in captured
    assert f"报销表: {payment}" in captured


def test_current_dir_many_csvs_lists_and_exits(tmp_path: Path, capsys: object) -> None:
    data_dir = tmp_path / "data"
    current_dir = data_dir / "当前"
    current_dir.mkdir(parents=True)
    for name in ("a.csv", "b.csv", "c.csv"):
        _write_csv(current_dir / name, ["施工日期"])

    selected = demo_settle_person._select_inputs(tmp_path)

    assert selected is None
    captured = capsys.readouterr().out
    assert "当前目录只保留 1(合并) 或 2(分开) 个CSV" in captured
    assert "- a.csv" in captured
    assert "- b.csv" in captured
    assert "- c.csv" in captured


def test_archive_csvs_do_not_affect_current_selection(
    tmp_path: Path, capsys: object
) -> None:
    data_dir = tmp_path / "data"
    current_dir = data_dir / "当前"
    archive_dir = data_dir / "归档"
    current_dir.mkdir(parents=True)
    archive_dir.mkdir(parents=True)
    attendance = current_dir / "attendance.csv"
    payment = current_dir / "payment.csv"
    _write_csv(attendance, ["施工日期", "是否施工", "施工人员"])
    _write_csv(payment, ["报销日期", "报销金额", "报销状态"])
    for idx in range(3):
        _write_csv(archive_dir / f"old_{idx}.csv", ["施工日期", "报销日期"])

    selected = demo_settle_person._select_inputs(tmp_path)

    assert selected == (attendance, payment)
    captured = capsys.readouterr().out
    assert f"出勤表: {attendance}" in captured
    assert f"报销表: {payment}" in captured
