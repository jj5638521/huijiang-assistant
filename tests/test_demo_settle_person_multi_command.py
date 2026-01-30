from pathlib import Path

from tools import demo_settle_person


def _write_csv(path: Path, headers: list[str], rows: list[list[str]]) -> None:
    lines = [",".join(headers)]
    for row in rows:
        lines.append(",".join(row))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_demo_settle_person_multi_command(
    tmp_path: Path, monkeypatch: object, capsys: object
) -> None:
    repo_root = tmp_path
    tools_dir = repo_root / "tools"
    tools_dir.mkdir()
    fake_script = tools_dir / "demo_settle_person.py"
    fake_script.write_text("", encoding="utf-8")
    monkeypatch.setattr(demo_settle_person, "__file__", str(fake_script))

    current_dir = repo_root / "data" / "当前"
    current_dir.mkdir(parents=True)

    attendance_path = current_dir / "attendance.csv"
    payment_path = current_dir / "payment.csv"
    _write_csv(
        attendance_path,
        ["施工日期", "施工人员", "是否施工", "车辆"],
        [
            ["2025-11-01", "王怀宇", "是", "防撞车"],
            ["2025-11-01", "李四", "是", "防撞车"],
        ],
    )
    _write_csv(
        payment_path,
        ["报销日期", "报销金额", "报销状态", "报销类型", "报销人员", "项目", "上传凭证"],
        [
            ["2025-11-02", "100", "已支付", "工资", "王怀宇", "测试项目", "V001"],
            ["2025-11-02", "200", "已支付", "工资", "李四", "测试项目", "V002"],
        ],
    )

    command_path = current_dir / "口令.txt"
    command_path.write_text(
        "\n".join(
            [
                "工资：王怀宇 组长 项目已结束=是 项目=测试项目",
                "工资：李四 组员 项目已结束=是 项目=测试项目",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = demo_settle_person.main()

    assert result == 0
    output = capsys.readouterr().out
    assert output.count("【压缩版】") == 2
    assert output.count("测试项目｜工资结算（王怀宇｜组长）") == 2
    assert output.count("测试项目｜工资结算（李四｜组员）") == 2
