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
    command_errors = context.get("command_errors") or []
    command_ok = (
        bool(context.get("person_name"))
        and bool(context.get("role"))
        and not command_errors
    )

    checks: list[CheckResult] = []

    headers_ok = not attendance.missing_fields and not payment.missing_fields
    detail = "OK" if headers_ok else "缺失: " + ",".join(
        attendance.missing_fields + payment.missing_fields
    )
    checks.append(_check("A", "表头映射成功", headers_ok, detail))

    command_detail_parts: list[str] = []
    if not context.get("person_name") or not context.get("role"):
        command_detail_parts.append("缺少姓名/角色")
    if command_errors:
        command_detail_parts.append("；".join(command_errors))
    command_detail = "OK" if command_ok else "；".join(command_detail_parts)
    checks.append(_check("K", "口令信息完整", command_ok, command_detail))

    name_key_conflicts = context.get("name_key_conflicts") or []
    name_key_ok = not name_key_conflicts
    name_key_detail = "OK"
    if not name_key_ok:
        name_key_detail = f"name_key 冲突 {len(name_key_conflicts)}条"
    checks.append(_check("N", "姓名归一冲突", name_key_ok, name_key_detail))

    project_name = context.get("project_name")
    project_pool_issue = context.get("project_pool_issue", False)
    project_name_source = context.get("project_name_source")
    project_requires_command = project_pool_issue and project_name_source != "command"
    if project_requires_command:
        project_ok = False
        project_detail = "项目池包含多个项目，需口令指定项目=XXX"
    else:
        project_ok = bool(project_name) or not project_pool_issue
        project_detail = "OK" if project_ok else "未识别项目名"
    checks.append(_check("B", "项目名确定", project_ok, project_detail))

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
    require_project_ended = context.get("require_project_ended")
    if require_project_ended:
        require_ok = project_ended is True
        checks.append(
            _check(
                "L2",
                "项目已结束=是",
                require_ok,
                "OK" if require_ok else "项目未结束",
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
    amount_detail = (
        "OK"
        if amount_ok
        else "金额格式异常: " + "; ".join(payment.invalid_amounts)
    )
    checks.append(_check("G", "金额数值化", amount_ok, amount_detail))

    type_required_ok = not payment.missing_type_candidates
    type_detail = (
        "OK"
        if type_required_ok
        else "支付行类型缺失（必填）：请补‘报销类型/费用类型/科目/类别’；"
        + "; ".join(payment.missing_type_candidates)
    )
    checks.append(_check("T", "支付行类型必填", type_required_ok, type_detail))

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
    single_detail = "OK"
    if any(attendance.date_sets["单防撞｜出勤"] + attendance.date_sets["单防撞｜未出勤"]):
        if attendance.has_vehicle_field:
            single_required_ok = True
            single_detail = "OK"
        elif attendance.has_explicit_mode:
            single_required_ok = True
            single_detail = "OK(出勤模式)"
        else:
            single_required_ok = False
            single_detail = "缺少车辆字段/出勤模式"
    checks.append(_check("M", "单防撞必要字段满足", single_required_ok, single_detail))

    pending_total = len(payment.pending_items) + len(payment.missing_amount_candidates)
    pending_detail = f"待确认{pending_total}条"
    if payment.missing_amount_candidates:
        pending_detail += f"(金额缺失{len(payment.missing_amount_candidates)}条)"
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

    project_mismatch_blocking = not (
        project_pool_issue and project_name_source == "command"
    )
    schema_ok = (
        not attendance.invalid_dates
        and not attendance.invalid_work_values
        and (not attendance.project_mismatches or not project_mismatch_blocking)
        and not payment.invalid_amounts
    )
    if payment.project_mismatches and project_mismatch_blocking:
        schema_ok = False
    schema_detail_parts: list[str] = []
    if attendance.invalid_dates:
        schema_detail_parts.append("日期格式异常")
    if attendance.invalid_work_values:
        schema_detail_parts.append("是否施工取值异常")
    if project_mismatch_blocking and (
        attendance.project_mismatches or payment.project_mismatches
    ):
        schema_detail_parts.append("项目不匹配")
    if payment.invalid_amounts:
        schema_detail_parts.append("金额格式异常")
    schema_detail = "OK" if schema_ok else ";".join(schema_detail_parts)
    checks.append(_check("S", "schema校验", schema_ok, schema_detail))

    hard_failures = [
        check for check in checks if not check.passed and check.severity == "hard"
    ]
    return checks, hard_failures
