from wage.settle_person import settle_person


def test_combined_csv_skips_non_payment_rows() -> None:
    combined_rows = [
        {
            "日期": "2025-11-01",
            "实际出勤人员": "王怀宇、张三",
            "今天是否施工": "是",
            "车辆": "防撞车",
            "报销日期": "",
            "报销金额": "",
            "报销状态": "",
            "报销类型": "",
            "报销人员": "",
            "项目": "",
            "上传凭证": "",
            "备注": "",
        },
        {
            "日期": "",
            "实际出勤人员": "",
            "今天是否施工": "",
            "车辆": "",
            "报销日期": "2025-11-02",
            "报销金额": "￥1,200 元",
            "报销状态": "已支付",
            "报销类型": "工资",
            "报销人员": "王怀宇",
            "项目": "测试项目",
            "上传凭证": "V-001",
            "备注": "工资支付",
        },
    ]

    output = settle_person(
        combined_rows,
        combined_rows,
        person_name="王怀宇",
        role="组长",
        project_ended=True,
        project_name="测试项目",
        runtime_overrides={},
    )

    assert "【阻断｜工资结算】" not in output
    assert "【详细版（给杰对账）】" in output
    assert "已付合计：1200" in output
