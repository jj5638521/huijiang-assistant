import re

from wage.ruleset import get_ruleset_version
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


def _attendance_rows_for_allowances() -> list[dict[str, str]]:
    return [
        {"日期": "2025-11-05", "姓名": "王怀宇", "是否施工": "是", "车辆": "防撞车"},
        {"日期": "2025-11-05", "姓名": "张三", "是否施工": "是", "车辆": "防撞车"},
        {"日期": "2025-11-05", "姓名": "李四", "是否施工": "是", "车辆": "防撞车"},
        {"日期": "2025-11-06", "姓名": "王怀宇", "是否施工": "否", "车辆": "防撞车"},
        {"日期": "2025-11-06", "姓名": "张三", "是否施工": "是", "车辆": "防撞车"},
        {"日期": "2025-11-06", "姓名": "李四", "是否施工": "是", "车辆": "防撞车"},
        {"日期": "2025-11-06", "姓名": "赵五", "是否施工": "是", "车辆": "防撞车"},
    ]


def _payment_rows_for_allowances() -> list[dict[str, str]]:
    return [
        {
            "报销日期": "2025-11-07",
            "报销金额": "350",
            "报销状态": "已支付",
            "报销类型": "路补",
            "报销人员": "王怀宇",
            "项目": "测试项目",
            "上传凭证": "V100",
        }
    ]


def test_settle_person_outputs_two_segments() -> None:
    version = get_ruleset_version()
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
    assert f"计算口径版本 {version}｜阻断模式：Hard" in output
    assert f"- 规则版本: 计算口径版本 {version}｜阻断模式：Hard" in output
    assert "input_hash" not in output
    assert "待确认明细" not in output
    detailed, compressed = output.split("\n\n")
    assert "日期（模式→出勤）" in compressed
    assert "2025-11：" in compressed
    assert re.search(r"日志：logs/[0-9a-f]{12}_[0-9a-f]{8}\.json", output)


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


def test_settle_person_allowances_enabled() -> None:
    output = settle_person(
        _attendance_rows_for_allowances(),
        _payment_rows_for_allowances(),
        person_name="王怀宇",
        role="组长",
        project_ended=True,
        project_name="测试项目",
        runtime_overrides={},
    )

    assert "餐补：25×1 + 40×1=65" in output
    assert "路补：200" in output


def test_settle_person_no_road_allowance_when_missing() -> None:
    payment_rows = [
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
    output = settle_person(
        _attendance_rows_for_allowances(),
        payment_rows,
        person_name="王怀宇",
        role="组长",
        project_ended=True,
        project_name="测试项目",
        runtime_overrides={},
    )

    assert "路补：0" in output


def test_settle_person_default_suppresses_cleaning_logs() -> None:
    attendance_rows = [
        {"日期": "2025/11/01", "姓名": "王怀宇、张三", "是否施工": "是", "车辆": "防撞车"},
        {"日期": "2025/11/02", "姓名": "王怀宇", "是否施工": "否", "车辆": "防撞车"},
    ]
    output = settle_person(
        attendance_rows,
        _payment_rows(),
        person_name="王怀宇",
        role="组长",
        project_ended=True,
        project_name="测试项目",
        runtime_overrides={},
    )

    assert "姓名拆分" not in output
    assert "日期格式标准化" not in output
    assert "input_hash" not in output


def test_settle_person_verbose_includes_audit_and_cleaning_logs() -> None:
    attendance_rows = [
        {"日期": "2025/11/01", "姓名": "王怀宇、张三", "是否施工": "是", "车辆": "防撞车"},
        {"日期": "2025/11/02", "姓名": "王怀宇", "是否施工": "否", "车辆": "防撞车"},
    ]
    output = settle_person(
        attendance_rows,
        _payment_rows(),
        person_name="王怀宇",
        role="组长",
        project_ended=True,
        project_name="测试项目",
        runtime_overrides={"verbose": 1},
    )

    assert "姓名拆分" in output
    assert "日期格式标准化" in output
    assert "input_hash" in output
    assert "output_hash" in output


def test_settle_person_run_id_is_unique() -> None:
    first = settle_person(
        _attendance_rows(),
        _payment_rows(),
        person_name="王怀宇",
        role="组长",
        project_ended=True,
        project_name="测试项目",
        runtime_overrides={},
    )
    second = settle_person(
        _attendance_rows(),
        _payment_rows(),
        person_name="王怀宇",
        role="组长",
        project_ended=True,
        project_name="测试项目",
        runtime_overrides={},
    )
    first_match = re.search(r"- run_id: ([0-9a-f]{12})", first)
    second_match = re.search(r"- run_id: ([0-9a-f]{12})", second)
    assert first_match and second_match
    assert first_match.group(1) != second_match.group(1)


def test_settle_person_can_hide_audit_sections() -> None:
    output = settle_person(
        _attendance_rows(),
        _payment_rows(),
        person_name="王怀宇",
        role="组长",
        project_ended=True,
        project_name="测试项目",
        runtime_overrides={"show_notes": 0, "show_checks": 0, "show_audit": 0},
    )

    assert "6）备注与校核摘要" not in output
    assert "7）校核摘要" not in output
    assert "8）审计留痕" not in output
    assert "日志：logs/" not in output
