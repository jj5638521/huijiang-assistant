from wage.command import parse_command


def test_parse_command_minimal() -> None:
    command = parse_command("工资：王怀宇 组长 项目已结束=是 项目=测试项目")

    assert command["person_name"] == "王怀宇"
    assert command["role"] == "组长"
    assert command["project_ended"] is True
    assert command["project_name"] == "测试项目"
