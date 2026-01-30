from pathlib import Path

from tools import demo_settle_project
from wage.command import parse_command
from wage.settle_person import settle_person


def _attendance_rows(project: str) -> list[dict[str, str]]:
    return [
        {
            "日期": "2025-11-01",
            "姓名": "王怀宇",
            "是否施工": "是",
            "车辆": "防撞车",
            "项目": project,
        },
        {
            "日期": "2025-11-01",
            "姓名": "余步云",
            "是否施工": "是",
            "车辆": "防撞车",
            "项目": project,
        },
        {
            "日期": "2025-11-01",
            "姓名": "张三",
            "是否施工": "是",
            "车辆": "防撞车",
            "项目": project,
        },
    ]


def _payment_rows(project: str) -> list[dict[str, str]]:
    return [
        {
            "报销日期": "2025-11-02",
            "报销金额": "100",
            "报销状态": "已支付",
            "报销类型": "工资",
            "报销人员": "王怀宇",
            "项目": project,
            "上传凭证": "V001",
        }
    ]


def test_fixed_daily_rate_priority(tmp_path: Path) -> None:
    project = "测试项目"
    command_text = "\n".join(
        [
            f"项目结算：项目={project} 项目已结束=是",
            "固定日薪:",
            "  王怀宇=280",
        ]
    )
    command = parse_command(command_text)
    output_dir = tmp_path / "输出"
    output_dir.mkdir()

    summary_path = demo_settle_project.settle_project(
        _attendance_rows(project),
        _payment_rows(project),
        command=command,
        project_name=project,
        output_dir=output_dir,
        runtime_overrides={"attendance_source": "a.csv", "payment_source": "b.csv"},
    )

    summary = summary_path.read_text(encoding="utf-8")
    assert "固定日薪命中：" in summary
    assert "王怀宇=280（来源：口令）" in summary
    assert "余步云=260（来源：系统）" in summary

    wage_text = (output_dir / "工资单_王怀宇.txt").read_text(encoding="utf-8")
    assert "工资：280×1=280" in wage_text


def test_fixed_daily_rate_name_key_match() -> None:
    attendance_rows = [
        {"日期": "2025-11-01", "姓名": "袁玉兵(P007)", "是否施工": "是", "车辆": "防撞车"},
        {"日期": "2025-11-01", "姓名": "张三", "是否施工": "是", "车辆": "防撞车"},
        {"日期": "2025-11-01", "姓名": "李四", "是否施工": "是", "车辆": "防撞车"},
        {"日期": "2025-11-02", "姓名": "袁玉兵(P007)", "是否施工": "是", "车辆": "防撞车"},
        {"日期": "2025-11-02", "姓名": "张三", "是否施工": "是", "车辆": "防撞车"},
        {"日期": "2025-11-02", "姓名": "李四", "是否施工": "是", "车辆": "防撞车"},
    ]
    payment_rows = [
        {
            "报销日期": "2025-11-03",
            "报销金额": "0",
            "报销状态": "已支付",
            "报销类型": "工资",
            "报销人员": "袁玉兵(P007)",
            "上传凭证": "V200",
        }
    ]

    output = settle_person(
        attendance_rows,
        payment_rows,
        person_name="袁玉兵(P007)",
        role="组员",
        project_ended=True,
        project_name="测试项目",
        runtime_overrides={},
    )

    assert "工资：300×2=600（全组2天）" in output
