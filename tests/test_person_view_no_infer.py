from wage.attendance_pipe import compute_attendance


def test_person_view_does_not_infer_missing_dates() -> None:
    attendance_rows = [
        {"日期": "2025-11-01", "姓名": "王怀宇", "是否施工": "是"},
        {"日期": "2025-11-01", "姓名": "张三", "是否施工": "是"},
        {"日期": "2025-11-02", "姓名": "张三", "是否施工": "是"},
        {"日期": "2025-11-03", "姓名": "王怀宇", "是否施工": "否"},
    ]

    result = compute_attendance(attendance_rows, project_name=None, target_person="王怀宇")

    assert "2025-11-02" not in result.date_sets["单防撞｜未出勤"]
    assert "2025-11-02" not in result.date_sets["全组｜未出勤"]
