from wage.settle_person import settle_person


def _attendance_rows() -> list[dict[str, str]]:
    return [
        {"日期": "2025-11-01", "姓名": "王怀宇", "是否施工": "是", "车辆": "防撞车"},
        {"日期": "2025-11-01", "姓名": "张三", "是否施工": "是", "车辆": "防撞车"},
        {"日期": "2025-11-02", "姓名": "王怀宇", "是否施工": "否", "车辆": "防撞车"},
        {"日期": "2025-11-02", "姓名": "张三", "是否施工": "是", "车辆": "防撞车"},
        {"日期": "2025-11-02", "姓名": "李四", "是否施工": "是", "车辆": "防撞车"},
        {"日期": "2025-11-02", "姓名": "赵五", "是否施工": "是", "车辆": "防撞车"},
        {"日期": "2025-11-03", "姓名": "王怀宇", "是否施工": "是", "车辆": "防撞车"},
        {"日期": "2025-11-03", "姓名": "张三", "是否施工": "是", "车辆": "防撞车"},
        {"日期": "2025-11-03", "姓名": "李四", "是否施工": "是", "车辆": "防撞车"},
    ]


def _payment_rows() -> list[dict[str, str]]:
    return [
        {
            "报销日期": "2025-11-04",
            "报销金额": "300",
            "报销状态": "已支付",
            "报销类型": "工资",
            "报销人员": "王怀宇",
            "项目": "测试项目",
            "上传凭证": "V001",
        }
    ]


def test_settle_person_outputs_two_segments() -> None:
    output = settle_person(
        _attendance_rows(),
        _payment_rows(),
        person_name="王怀宇",
        role="组长",
        project_ended=True,
        project_name="测试项目",
        runtime_overrides={},
    )

    assert "【详细版（给杰对账）】" in output
    assert "【压缩版（发员工）】" in output
    assert "计算口径版本 v2025-11-25R52｜阻断模式：Hard" in output


def test_settle_person_blocking_report() -> None:
    output = settle_person(
        [],
        [],
        person_name="王怀宇",
        role="组长",
        project_ended=True,
        project_name="测试项目",
        runtime_overrides={},
    )

    assert output.startswith("【阻断｜工资结算】")
    assert "【详细版（给杰对账）】" not in output
