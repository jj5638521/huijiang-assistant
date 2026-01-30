from wage.settle_person import settle_person


def test_project_pool_blocks_without_command() -> None:
    attendance_rows = [
        {
            "施工日期": "2026-01-02",
            "姓名": "张三",
            "是否施工": "是",
            "项目": "项目A",
            "出勤模式": "全组",
        },
        {
            "施工日期": "2026-01-03",
            "姓名": "张三",
            "是否施工": "是",
            "项目": "项目B",
            "出勤模式": "全组",
        },
    ]
    payment_rows = [
        {
            "报销日期": "2026-01-04",
            "报销金额": "100",
            "报销状态": "已支付",
            "报销类型": "工资",
            "报销人员": "张三",
            "项目": "项目A",
            "上传凭证": "V001",
        },
        {
            "报销日期": "2026-01-05",
            "报销金额": "120",
            "报销状态": "已支付",
            "报销类型": "工资",
            "报销人员": "张三",
            "项目": "项目B",
            "上传凭证": "V002",
        },
    ]

    output = settle_person(
        attendance_rows,
        payment_rows,
        person_name="张三",
        role="组员",
        project_ended=True,
        project_name=None,
        runtime_overrides={},
    )

    assert output.startswith("【阻断｜工资结算】")
    assert "项目池包含多个项目" in output
    assert "出勤表项目Top10" in output
    assert "支付表项目Top10" in output


def test_project_pool_filters_with_command() -> None:
    attendance_rows = [
        {
            "施工日期": "2026-01-02",
            "姓名": "张三",
            "是否施工": "是",
            "项目": "项目A",
            "出勤模式": "全组",
        },
        {
            "施工日期": "2026-01-03",
            "姓名": "张三",
            "是否施工": "是",
            "项目": "项目B",
            "出勤模式": "全组",
        },
    ]
    payment_rows = [
        {
            "报销日期": "2026-01-04",
            "报销金额": "100",
            "报销状态": "已支付",
            "报销类型": "工资",
            "报销人员": "张三",
            "项目": "项目A",
            "上传凭证": "V001",
        },
        {
            "报销日期": "2026-01-05",
            "报销金额": "120",
            "报销状态": "已支付",
            "报销类型": "工资",
            "报销人员": "张三",
            "项目": "项目B",
            "上传凭证": "V002",
        },
    ]

    output = settle_person(
        attendance_rows,
        payment_rows,
        person_name="张三",
        role="组员",
        project_ended=True,
        project_name="项目A",
        runtime_overrides={},
    )

    assert not output.startswith("【阻断｜工资结算】")
