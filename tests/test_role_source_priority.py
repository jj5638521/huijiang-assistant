from pathlib import Path

from tools import demo_settle_project
from wage.command import parse_command


def _attendance_rows(project: str) -> list[dict[str, str]]:
    return [
        {
            "日期": "2025-11-01",
            "姓名": "李四",
            "是否施工": "是",
            "车辆": "防撞车",
            "角色": "组长",
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
            "报销人员": "李四",
            "项目": project,
            "上传凭证": "V001",
        }
    ]


def test_role_source_priority(tmp_path: Path) -> None:
    project = "测试项目"
    command_text = "\n".join(
        [
            f"项目结算：项目={project} 项目已结束=是",
            "角色:",
            "  李四=组员",
            "  张三=组长",
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
    assert "角色来源：" in summary
    assert "李四=组长（来源：表）" in summary
    assert "张三=组长（来源：口令）" in summary
