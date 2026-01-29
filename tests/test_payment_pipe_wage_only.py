from wage.payment_pipe import compute_payments


def test_payment_pipe_wage_only_filters_non_wage() -> None:
    payment_rows = [
        {
            "报销日期": "2025-11-04",
            "报销金额": "300",
            "报销状态": "已支付",
            "报销类型": "工资",
            "报销人员": "王怀宇",
            "项目": "测试项目",
            "上传凭证": "V001",
        },
        {
            "报销日期": "2025-11-04",
            "报销金额": "120",
            "报销状态": "已支付",
            "报销类型": "工资预支",
            "报销人员": "王怀宇",
            "项目": "测试项目",
            "上传凭证": "V002",
        },
        {
            "报销日期": "2025-11-05",
            "报销金额": "80",
            "报销状态": "已支付",
            "报销类型": "餐补",
            "报销人员": "王怀宇",
            "项目": "测试项目",
            "上传凭证": "M001",
        },
        {
            "报销日期": "2025-11-06",
            "报销金额": "60",
            "报销状态": "状态无效",
            "报销类型": "路费",
            "报销人员": "王怀宇",
            "项目": "测试项目",
            "上传凭证": "R001",
        },
        {
            "报销日期": "2025-11-07",
            "报销金额": "ABC",
            "报销状态": "已支付",
            "报销类型": "油费",
            "报销人员": "王怀宇",
            "项目": "测试项目",
            "上传凭证": "O001",
        },
    ]

    result = compute_payments(payment_rows, "测试项目", "王怀宇")

    assert [item.category for item in result.paid_items] == ["工资"]
    assert [item.category for item in result.prepay_items] == ["预支"]
    assert result.pending_items == []
    assert result.missing_amount_candidates == []
    assert result.invalid_amounts == []
    assert result.invalid_status_items == []
