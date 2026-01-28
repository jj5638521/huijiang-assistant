from wage.command import parse_command


def test_parse_project_command_normalizes_and_reads_project_fields() -> None:
    command_text = (
        "项目结算：测试项目 项目已结束＝是 路补口令=无路补\n"
        "角色:\n"
        "张三=组员\n"
        "固定日薪:\n"
        "张三=200"
    )

    command = parse_command(command_text)

    assert command["mode"] == "project"
    assert command["project_name"] == "测试项目"
    assert command["project_ended"] is True
