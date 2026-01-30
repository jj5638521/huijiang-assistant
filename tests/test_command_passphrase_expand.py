from wage.command import expand_wage_passphrase_commands, parse_command


def _parse_people(lines: list[str]) -> dict[str, dict[str, object]]:
    results: dict[str, dict[str, object]] = {}
    for line in lines:
        if not line.startswith("工资："):
            continue
        command = parse_command(line)
        results[command["person_name"]] = command
    return results


def test_passphrase_basic_expand() -> None:
    command_text = "\n".join(
        [
            "项目已结束=是",
            "项目=测试项目",
            "组长：王怀宇 袁玉兵",
            "路补=无：王怀宇 余步云",
            "路补=有：邹志同",
        ]
    )
    lines, _, errors = expand_wage_passphrase_commands(command_text)

    assert not errors
    people = _parse_people(lines)
    assert set(people.keys()) == {"王怀宇", "余步云", "邹志同"}
    assert people["王怀宇"]["role"] == "组长"
    assert people["余步云"]["role"] == "组员"
    assert people["邹志同"]["role"] == "组员"
    assert people["王怀宇"]["road_cmd"] == "无路补"
    assert people["邹志同"]["road_cmd"] == "计算路补"
    assert people["王怀宇"]["project_name"] == "测试项目"
    assert people["王怀宇"]["project_ended"] is True


def test_passphrase_allow_empty_road_yes() -> None:
    command_text = "\n".join(
        [
            "项目已结束=是",
            "项目=测试项目",
            "路补=无：王怀宇",
            "路补=有：",
        ]
    )
    lines, _, errors = expand_wage_passphrase_commands(command_text)

    assert not errors
    people = _parse_people(lines)
    assert list(people.keys()) == ["王怀宇"]
    assert people["王怀宇"]["road_cmd"] == "无路补"


def test_passphrase_empty_groups_block() -> None:
    command_text = "\n".join(
        [
            "项目已结束=是",
            "路补=无：",
            "路补=有：",
        ]
    )
    _, _, errors = expand_wage_passphrase_commands(command_text)

    assert errors
    assert "两组人员均为空" in errors[0]


def test_passphrase_road_conflict_block() -> None:
    command_text = "\n".join(
        [
            "项目已结束=是",
            "路补=无：王怀宇",
            "路补=有：王怀宇",
        ]
    )
    _, _, errors = expand_wage_passphrase_commands(command_text)

    assert errors
    assert "路补名单冲突" in errors[0]
    assert "王怀宇" in errors[0]


def test_passphrase_leader_name_key() -> None:
    command_text = "\n".join(
        [
            "项目已结束=是",
            "项目=测试项目",
            "组长：王怀宇 袁玉兵",
            "路补=无：王怀宇(P001) 袁玉兵(P007)",
        ]
    )
    lines, _, errors = expand_wage_passphrase_commands(command_text)

    assert not errors
    people = _parse_people(lines)
    assert people["王怀宇(P001)"]["role"] == "组长"
    assert people["袁玉兵(P007)"]["role"] == "组长"


def test_passphrase_project_auto_single() -> None:
    attendance_rows = [{"项目": "测试项目"}, {"项目": "测试项目"}]
    command_text = "\n".join(
        [
            "项目已结束=是",
            "路补=无：王怀宇",
        ]
    )
    lines, _, errors = expand_wage_passphrase_commands(
        command_text,
        attendance_rows=attendance_rows,
        payment_rows=[],
    )

    assert not errors
    people = _parse_people(lines)
    assert people["王怀宇"]["project_name"] == "测试项目"


def test_passphrase_project_auto_multiple_block() -> None:
    attendance_rows = [{"项目": "项目A"}, {"项目": "项目B"}]
    command_text = "\n".join(
        [
            "项目已结束=是",
            "路补=无：王怀宇",
        ]
    )
    _, _, errors = expand_wage_passphrase_commands(
        command_text,
        attendance_rows=attendance_rows,
        payment_rows=[],
    )

    assert errors
    assert "项目清单" in errors[0]
