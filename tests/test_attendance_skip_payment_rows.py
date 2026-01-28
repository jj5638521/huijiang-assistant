from wage.attendance_pipe import compute_attendance
from wage.settle_person import settle_person


def test_attendance_skips_payment_rows_in_merged_csv() -> None:
    combined_rows = [
        {
            "日期": "2025-11-05",
            "姓名": "徐新亮",
            "是否施工": "",
            "报销类型": "工资",
            "金额": "2815",
            "报销状态": "已报销",
            "凭证": "V-2815",
            "项目": "测试项目",
        },
        {
            "日期": "2025-11-06",
            "姓名": "测试工人",
            "是否施工": "是",
            "车辆": "防撞车",
            "报销类型": "",
            "金额": "",
            "报销状态": "",
            "凭证": "",
            "项目": "测试项目",
        },
    ]

    attendance = compute_attendance(
        combined_rows,
        project_name="测试项目",
        target_person="徐新亮",
    )

    all_dates = {date for dates in attendance.date_sets.values() for date in dates}
    assert "2025-11-05" not in all_dates

    output = settle_person(
        combined_rows,
        combined_rows,
        person_name="徐新亮",
        role="组员",
        project_ended=True,
        project_name="测试项目",
        runtime_overrides={},
    )

    assert "[M]" not in output
