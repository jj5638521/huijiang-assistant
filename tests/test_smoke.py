from wage.settle_person import settle_person


def test_settle_person_runs() -> None:
    attendance_rows = [
        {"日期": "2025-11-01", "姓名": "王怀宇", "是否施工": "是", "车辆": "防撞"}
    ]
    payment_rows = [
        {
            "报销日期": "2025-11-02",
            "报销金额": "0",
            "报销状态": "已支付",
            "报销类型": "工资",
            "报销人员": "王怀宇",
            "项目": "测试项目",
            "上传凭证": "V000",
        }
    ]

    result = settle_person(
        attendance_rows,
        payment_rows,
        person_name="王怀宇",
        role="组长",
        project_ended=False,
        project_name="测试项目",
        runtime_overrides={},
    )

    assert "工资结算" in result
