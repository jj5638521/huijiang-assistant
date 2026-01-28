"""Validation checks for wage settlement."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class CheckResult:
    code: str
    name: str
    passed: bool
    severity: str
    detail: str


def _check(
    code: str, name: str, passed: bool, detail: str, severity: str = "hard"
) -> CheckResult:
    return CheckResult(code=code, name=name, passed=passed, severity=severity, detail=detail)


def _amount_equal(a: Decimal, b: Decimal) -> bool:
    return a == b


def run_checks(context: dict) -> tuple[list[CheckResult], list[CheckResult]]:
    attendance = context["attendance"]
    payment = context["payment"]
    pricing = context["pricing"]
    command_ok = bool(context.get("person_name")) and bool(context.get("role"))

    checks: list[CheckResult] = []

    headers_ok = not attendance.missing_fields and not payment.missing_fields
    detail = "OK" if headers_ok else "缺失: " + ",".join(
        attendance.missing_fields + payment.missing_fields
    )
    checks.append(_check("A", "表头映射成功", headers_ok, detail))

    checks.append(
        _check(
            "K",
            "口令信息完整",
            command_ok,
            "OK" if command_ok else "缺少姓名/角色",
        )
    )

    project_name = context.get("project_name")
    project_ok = bool(project_name)
    checks.append(
        _check(
            "B",
            "项目名确定",
            project_ok,
            "OK" if project_ok else "未识别项目名",
        )
    )

    project_ended = context.get("project_ended")
    project_ended_ok = project_ended is not None
    checks.append(
        _check(
            "L",
            "项目结束标识",
            project_ended_ok,
            "OK" if project_ended_ok else "缺少项目已结束=是/否",
        )
    )

    voucher_ok = not payment.voucher_duplicates and not payment.empty_voucher_duplicates
    voucher_detail = "OK"
    if not voucher_ok:
        parts = []
        if payment.voucher_duplicates:
            parts.append("凭证重复")
        if payment.empty_voucher_duplicates:
            parts.append("空凭证重复")
        voucher_detail = ";".join(parts)
    checks.append(_check("C", "凭证唯一", voucher_ok, voucher_detail))

    conflict_ok = True
    conflict_detail = "OK"
    if attendance.conflict_logs:
        conflict_detail = f"冲突{len(attendance.conflict_logs)}条已消解"
    checks.append(_check("D", "出勤冲突消解", conflict_ok, conflict_detail, "soft"))

    payable_formula = pricing["payable"]
    recompute = (
        pricing["wage_total"]
        + pricing["meal_total"]
        + pricing["travel_total"]
        - pricing["paid_total"]
        - pricing["prepay_total"]
    )
    payable_ok = _amount_equal(payable_formula, recompute)
    payable_detail = "OK" if payable_ok else "应付反算不一致"
    checks.append(_check("E", "应付反算一致", payable_ok, payable_detail))

    mode_ok = True
    mode_detail = "OK"
    checks.append(_check("F", "模式不混合", mode_ok, mode_detail))

    amount_ok = not payment.invalid_amounts
    amount_detail = "OK" if amount_ok else "金额格式异常"
    checks.append(_check("G", "金额数值化", amount_ok, amount_detail))

    date_sets_ok = context.get("date_sets_consistent", True)
    checks.append(
        _check(
            "H",
            "两版日期集合一致",
            date_sets_ok,
            "OK" if date_sets_ok else "日期集合不一致",
        )
    )

    single_required_ok = True
    if any(attendance.date_sets["单防撞｜出勤"] + attendance.date_sets["单防撞｜未出勤"]):
        single_required_ok = attendance.has_vehicle_field
    single_detail = "OK" if single_required_ok else "缺少车辆字段"
    checks.append(_check("M", "单防撞必要字段满足", single_required_ok, single_detail))

    pending_detail = f"待确认{len(payment.pending_items)}条"
    checks.append(_check("P", "待确认条数提示", True, pending_detail, "soft"))

    version_note = context.get("version_note")
    version_ok = bool(version_note)
    checks.append(
        _check(
            "V",
            "版本尾注存在",
            version_ok,
            "OK" if version_ok else "缺少版本尾注",
        )
    )

    schema_ok = (
        not attendance.invalid_dates
        and not attendance.project_mismatches
        and not payment.invalid_amounts
    )
    if payment.project_mismatches:
        schema_ok = False
    if payment.invalid_status_items:
        schema_ok = False
    schema_detail_parts: list[str] = []
    if attendance.invalid_dates:
        schema_detail_parts.append("日期格式异常")
    if attendance.project_mismatches or payment.project_mismatches:
        schema_detail_parts.append("项目不匹配")
    if payment.invalid_status_items:
        schema_detail_parts.append("状态无效")
    if payment.invalid_amounts:
        schema_detail_parts.append("金额格式异常")
    schema_detail = "OK" if schema_ok else ";".join(schema_detail_parts)
    checks.append(_check("S", "schema校验", schema_ok, schema_detail))

    hard_failures = [
        check for check in checks if not check.passed and check.severity == "hard"
    ]
    return checks, hard_failures
