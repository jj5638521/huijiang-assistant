from wage.command import parse_command


def test_parse_wage_line_road_and_project() -> None:
    command = parse_command("工资：王怀宇 组长 项目已结束=是 路补=有 项目=测试项目")

    assert command["road_cmd"] == "计算路补"
    assert command["runtime_overrides"]["road_passphrase"] == "计算路补"
    assert command["project_name"] == "测试项目"


def test_parse_wage_line_road_no() -> None:
    command = parse_command("工资：王怀宇 组长 项目已结束=否 路补=无")

    assert command["road_cmd"] == "无路补"
    assert command["runtime_overrides"]["road_passphrase"] == "无路补"


def test_parse_wage_line_road_conflict_prefers_wage_line() -> None:
    command_text = "工资：王怀宇 组长 项目已结束=是 路补=有\n路补口令=无路补"
    command = parse_command(command_text)

    assert command["road_cmd"] == "计算路补"
    assert command["runtime_overrides"]["road_passphrase"] == "计算路补"
    assert "口令冲突：已采用工资行内路补设置" in command["runtime_overrides"][
        "audit_notes"
    ]


def test_parse_wage_line_separators_and_whitespace() -> None:
    command_text = "\ufeff工资：王怀宇　组长 项目已结束：0 路补：无 项目:测试项目"
    command = parse_command(command_text)

    assert command["project_ended"] is False
    assert command["road_cmd"] == "无路补"
    assert command["project_name"] == "测试项目"
