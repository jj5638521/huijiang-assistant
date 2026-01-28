from wage.payment_pipe import compute_payments


def test_payment_pipe_skips_attendance_rows_in_merged_table() -> None:
    attendance_rows = [
        {
            "施工日期": f"2025-11-{day:02d}",
            "施工人员": f"工人{index}",
            "是否施工": "是",
            "报销日期": "",
            "报销金额": "",
            "报销状态": "",
            "报销类型": "",
            "报销人员": "",
            "项目": "",
            "上传凭证": "",
        }
        for index, day in enumerate(range(1, 51), start=1)
    ]
    payment_rows = [
        {
            "施工日期": "",
            "施工人员": "",
            "是否施工": "",
            "报销日期": "2025-11-20",
            "报销金额": "2000",
            "报销状态": "已支付",
            "报销类型": "工资",
            "报销人员": "王怀宇",
            "项目": "测试项目",
            "上传凭证": "V200",
        },
        {
            "施工日期": "",
            "施工人员": "",
            "是否施工": "",
            "报销日期": "2025-11-21",
            "报销金额": "500",
            "报销状态": "已支付",
            "报销类型": "预支",
            "报销人员": "王怀宇",
            "项目": "测试项目",
            "上传凭证": "V201",
        },
    ]

    result = compute_payments(
        attendance_rows + payment_rows,
        project_name="测试项目",
        target_person="王怀宇",
    )

    assert result.missing_amount_candidates == []
    assert len(result.paid_items) == 1
    assert len(result.prepay_items) == 1
