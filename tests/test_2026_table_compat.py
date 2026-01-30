import csv
from pathlib import Path

from wage.attendance_pipe import collect_attendance_people, compute_attendance
from wage.payment_pipe import compute_payments
from wage.settle_person import settle_person


def _write_csv(path: Path, headers: list[str], rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_attendance_expands_multiple_people(tmp_path: Path) -> None:
    attendance_path = tmp_path / "attendance.csv"
    _write_csv(
        attendance_path,
        ["施工日期", "项目", "是否施工", "实际出勤人员", "出勤模式（填表用）"],
        [["2026-01-02", "测试项目", "是", "张三、李四", "全组"]],
    )

    attendance_rows = _read_csv(attendance_path)
    people = collect_attendance_people(attendance_rows, "测试项目")
    assert people == {"张三", "李四"}

    for person in ["张三", "李四"]:
        result = compute_attendance(attendance_rows, "测试项目", person)
        assert "2026-01-02" in result.date_sets["全组｜出勤"]


def test_attendance_mode_without_vehicle_field(tmp_path: Path) -> None:
    attendance_path = tmp_path / "attendance.csv"
    payment_path = tmp_path / "payment.csv"
    _write_csv(
        attendance_path,
        ["施工日期", "项目", "是否施工", "实际出勤人员", "出勤模式（填表用）"],
        [["2026-01-03", "测试项目", "是", "张三", "单防撞"]],
    )
    _write_csv(
        payment_path,
        ["项目", "报销人员", "报销日期", "报销类型", "报销金额", "上传凭证", "报销状态"],
        [["测试项目", "张三", "2026-01-04", "工资", "100", "V101", "已支付"]],
    )

    output = settle_person(
        _read_csv(attendance_path),
        _read_csv(payment_path),
        person_name="张三",
        role="组员",
        project_ended=False,
        project_name="测试项目",
        runtime_overrides={},
    )

    assert not output.startswith("【阻断｜工资结算】")
    assert "缺少车辆字段" not in output


def test_payment_wage_only_new_headers(tmp_path: Path) -> None:
    payment_path = tmp_path / "payment.csv"
    _write_csv(
        payment_path,
        ["项目", "报销人员", "报销日期", "报销类型", "报销金额", "上传凭证", "报销说明", "报销状态"],
        [
            ["测试项目", "张三", "2026-01-05", "工资预支", "100", "V201", "", "已支付"],
            ["测试项目", "张三", "2026-01-06", "油费", "50", "V202", "", "已支付"],
            ["测试项目", "张三", "2026-01-07", "餐补", "30", "V203", "", "已支付"],
        ],
    )

    payment_rows = _read_csv(payment_path)
    result = compute_payments(payment_rows, "测试项目", "张三")

    assert len(result.prepay_items) == 1
    assert result.prepay_total == result.prepay_items[0].amount
    assert not result.paid_items
    assert not result.pending_items
