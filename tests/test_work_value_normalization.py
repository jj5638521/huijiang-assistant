from wage.settle_person import settle_person


def test_invalid_work_value_blocks() -> None:
    attendance_rows = [
        {"施工日期": "2026-01-02", "姓名": "张三", "是否施工": "未知", "项目": "项目A"},
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
        }
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

    assert output.startswith("【阻断｜工资结算】")
    assert "是否施工取值异常" in output
    assert "第1行" in output
