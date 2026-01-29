from wage.settle_person import settle_person


def _attendance_rows() -> list[dict[str, str]]:
    return [
        {"日期": "2025-11-01", "姓名": "王怀宇", "是否施工": "是", "车辆": "防撞车"},
        {"日期": "2025-11-01", "姓名": "张三", "是否施工": "是", "车辆": "防撞车"},
        {"日期": "2025-11-02", "姓名": "王怀宇", "是否施工": "否", "车辆": "防撞车"},
        {"日期": "2025-11-02", "姓名": "张三", "是否施工": "是", "车辆": "防撞车"},
        {"日期": "2025-11-02", "姓名": "李四", "是否施工": "是", "车辆": "防撞车"},
    ]


def _payment_rows() -> list[dict[str, str]]:
    return [
        {
            "报销日期": "",
            "报销金额": "",
            "报销状态": "",
            "报销类型": "",
            "报销人员": "",
            "项目": "",
            "上传凭证": "",
        }
    ]


def _settle(project_ended: bool, road_cmd: str) -> str:
    return settle_person(
        _attendance_rows(),
        _payment_rows(),
        person_name="王怀宇",
        role="组长",
        project_ended=project_ended,
        project_name="测试项目",
        runtime_overrides={"road_passphrase": road_cmd},
    )


def test_road_allowance_fixed_200_when_enabled() -> None:
    output = _settle(project_ended=True, road_cmd="计算路补")

    assert "路补：200" in output
    detailed, compressed = output.split("\n\n")
    assert "路补200" in compressed
    assert "固定200元/人/项目" in detailed


def test_road_allowance_zero_when_disabled() -> None:
    output = _settle(project_ended=True, road_cmd="无路补")

    assert "路补：0" in output


def test_road_allowance_zero_when_not_ended() -> None:
    output = _settle(project_ended=False, road_cmd="计算路补")

    assert "路补：0" in output
