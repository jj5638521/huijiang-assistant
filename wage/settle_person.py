"""Wage settlement logic for per-person settlement."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Mapping

from .attendance_pipe import AttendanceResult, compute_attendance
from .checks import CheckResult, run_checks
from .payment_pipe import PaymentResult, compute_payments
from .render_blocking_report import render_blocking_report

RULE_VERSION = "v2025-11-25R54"
VERSION_NOTE = f"计算口径版本 {RULE_VERSION}｜阻断模式：Hard"

DAILY_WAGE_MAP = {
    "王怀宇": Decimal("300"),
    "余步云": Decimal("260"),
    "董峰": Decimal("300"),
    "董祥": Decimal("300"),
    "王怀良": Decimal("230"),
    "袁玉兵": Decimal("300"),
}
ROLE_WAGE_MAP = {
    "组长": Decimal("300"),
    "组员": Decimal("200"),
}
DEFAULT_SINGLE_YES = Decimal("270")
DEFAULT_SINGLE_NO = Decimal("135")


@dataclass(frozen=True)
class SettlementOutput:
    detailed: str
    compressed: str


@dataclass(frozen=True)
class PricingResult:
    wage_group: Decimal
    wage_single_yes: Decimal
    wage_single_no: Decimal
    wage_total: Decimal
    meal_total: Decimal
    travel_total: Decimal
    paid_total: Decimal
    prepay_total: Decimal
    payable: Decimal


def _hash_payload(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _format_decimal(value: Decimal) -> str:
    return f"{value:.0f}"


def _build_date_list(dates: list[str]) -> str:
    return "、".join(dates) if dates else "无"


def _compute_pricing(
    attendance: AttendanceResult,
    payment: PaymentResult,
    daily_group: Decimal,
    single_yes: Decimal,
    single_no: Decimal,
    project_ended: bool | None,
) -> PricingResult:
    group_yes_days = len(attendance.date_sets["全组｜出勤"])
    group_no_days = len(attendance.date_sets["全组｜未出勤"])
    single_yes_days = len(attendance.date_sets["单防撞｜出勤"])
    single_no_days = len(attendance.date_sets["单防撞｜未出勤"])

    wage_group = daily_group * Decimal(group_yes_days)
    wage_single_yes = single_yes * Decimal(single_yes_days)
    wage_single_no = single_no * Decimal(single_no_days)
    wage_total = wage_group + wage_single_yes + wage_single_no

    meal_total = Decimal("0")
    travel_total = Decimal("0")

    paid_total = payment.paid_total
    prepay_total = payment.prepay_total
    payable = wage_total + meal_total + travel_total - paid_total - prepay_total

    return PricingResult(
        wage_group=wage_group,
        wage_single_yes=wage_single_yes,
        wage_single_no=wage_single_no,
        wage_total=wage_total,
        meal_total=meal_total,
        travel_total=travel_total,
        paid_total=paid_total,
        prepay_total=prepay_total,
        payable=payable,
    )


def _render_payment_items(title: str, items: list[object]) -> list[str]:
    lines = [title]
    if not items:
        lines.append("- 无")
        return lines
    for item in items:
        lines.append(
            "- "
            f"{item.date}｜{item.raw_type or item.category}｜{item.amount}｜"
            f"状态:{item.status}｜凭证:{item.voucher or 'TEMP'}"
        )
    return lines


def _render_checks(checks: list[CheckResult]) -> list[str]:
    lines = []
    for check in checks:
        status = "通过" if check.passed else "失败"
        lines.append(f"- [{check.code}] {check.name}: {status}｜{check.detail}")
    return lines


def _collect_missing_items(attendance: AttendanceResult, payment: PaymentResult) -> list[str]:
    items = []
    for field in attendance.missing_fields:
        items.append(f"出勤表缺少字段: {field}")
    for field in payment.missing_fields:
        items.append(f"支付表缺少字段: {field}")
    return items


def _collect_invalid_items(attendance: AttendanceResult, payment: PaymentResult) -> list[str]:
    items: list[str] = []
    if attendance.invalid_dates:
        items.append("出勤表日期格式异常")
    if attendance.project_mismatches or payment.project_mismatches:
        items.append("项目字段不匹配")
    if payment.invalid_amounts:
        items.append(f"支付表金额格式异常: {'; '.join(payment.invalid_amounts)}")
    if payment.invalid_status_items:
        items.append("支付表存在无效状态")
    if payment.voucher_duplicates:
        items.append("凭证唯一性冲突")
    if payment.empty_voucher_duplicates:
        items.append("空凭证五元组重复")
    return items


def _collect_suggestions(attendance: AttendanceResult, payment: PaymentResult) -> list[str]:
    suggestions = []
    if attendance.missing_fields:
        suggestions.append("补齐出勤表字段：日期/姓名/是否施工/车辆(如有)")
    if payment.missing_fields:
        suggestions.append("补齐支付表字段：日期/金额/状态/类型/姓名/项目/凭证")
    if attendance.invalid_dates:
        suggestions.append("统一日期格式为 YYYY-MM-DD")
    if payment.invalid_amounts:
        suggestions.append("金额请填写数字金额，可包含￥/元/逗号但勿含文字")
    if payment.invalid_status_items:
        suggestions.append("报销状态需在白名单内（如已支付/已报销/审核通过）")
    if payment.voucher_duplicates or payment.empty_voucher_duplicates:
        suggestions.append("确保凭证号唯一或补充凭证")
    if attendance.project_mismatches or payment.project_mismatches:
        suggestions.append("确认CSV内项目字段与口令项目一致")
    return suggestions


def settle_person(
    attendance_rows: Iterable[Mapping[str, str]],
    payment_rows: Iterable[Mapping[str, str]],
    *,
    person_name: str | None,
    role: str | None,
    project_ended: bool | None,
    project_name: str | None,
    runtime_overrides: dict | None = None,
) -> str:
    """Return the settlement report (two segments) or blocking report."""
    runtime_overrides = runtime_overrides or {}
    attendance_list = list(attendance_rows)
    payment_list = list(payment_rows)

    attendance = compute_attendance(attendance_list, project_name, person_name)
    payment = compute_payments(payment_list, project_name, person_name)

    daily_group = DAILY_WAGE_MAP.get(
        person_name or "",
        ROLE_WAGE_MAP.get(role or "", Decimal("0")),
    )
    single_yes = Decimal(str(runtime_overrides.get("single_yes", DEFAULT_SINGLE_YES)))
    single_no = Decimal(str(runtime_overrides.get("single_no", DEFAULT_SINGLE_NO)))

    pricing = _compute_pricing(
        attendance, payment, daily_group, single_yes, single_no, project_ended
    )

    input_hash = _hash_payload(
        {
            "command": {
                "person_name": person_name,
                "role": role,
                "project_ended": project_ended,
                "project_name": project_name,
            },
            "attendance_rows": attendance_list,
            "payment_rows": payment_list,
        }
    )
    run_id = input_hash[:12]

    context = {
        "attendance": attendance,
        "payment": payment,
        "pricing": pricing.__dict__,
        "person_name": person_name,
        "role": role,
        "project_name": project_name,
        "project_ended": project_ended,
        "version_note": VERSION_NOTE,
        "date_sets_consistent": True,
    }

    checks, hard_failures = run_checks(context)

    missing_items = _collect_missing_items(attendance, payment)
    invalid_items = _collect_invalid_items(attendance, payment)
    suggestions = _collect_suggestions(attendance, payment)

    if hard_failures:
        return render_blocking_report(
            person_name=person_name,
            project_name=project_name,
            run_id=run_id,
            version_note=VERSION_NOTE,
            input_hash=input_hash,
            hard_failures=hard_failures,
            missing_fields=missing_items,
            invalid_items=invalid_items,
            suggestions=suggestions,
        )

    auto_logs = attendance.auto_corrections + attendance.normalization_logs
    differences = auto_logs if auto_logs else ["无"]

    group_yes_days = len(attendance.date_sets["全组｜出勤"])
    group_no_days = len(attendance.date_sets["全组｜未出勤"])
    single_yes_days = len(attendance.date_sets["单防撞｜出勤"])
    single_no_days = len(attendance.date_sets["单防撞｜未出勤"])

    detail_lines = [
        "【详细版（给杰对账）】",
        f"{project_name or '项目未识别'}｜工资结算（{person_name or '未知'}｜{role or '未标注'}）",
        "1）出勤与模式：",
        f"- 单防撞出勤 {single_yes_days} 天：{_build_date_list(attendance.date_sets['单防撞｜出勤'])}",
        f"- 单防撞未出勤 {single_no_days} 天：{_build_date_list(attendance.date_sets['单防撞｜未出勤'])}",
        f"- 全组出勤 {group_yes_days} 天：{_build_date_list(attendance.date_sets['全组｜出勤'])}",
        f"- 全组未出勤 {group_no_days} 天：{_build_date_list(attendance.date_sets['全组｜未出勤'])}",
        "2）金额与公式：",
        (
            f"- 全组工资：{_format_decimal(daily_group)}×{group_yes_days}="
            f"{_format_decimal(pricing.wage_group)}"
        ),
        (
            f"- 单防撞工资：{_format_decimal(single_yes)}×{single_yes_days} + "
            f"{_format_decimal(single_no)}×{single_no_days}="
            f"{_format_decimal(pricing.wage_single_yes + pricing.wage_single_no)}"
        ),
        f"- 工资合计：{_format_decimal(pricing.wage_total)}",
        f"- 餐补：{_format_decimal(pricing.meal_total)}（当前口径=0）",
        f"- 路补：{_format_decimal(pricing.travel_total)}（当前口径=0，项目已结束={'是' if project_ended else '否'}）",
        "3）已付/预支明细：",
    ]

    detail_lines.extend(_render_payment_items("- 已付", payment.paid_items))
    detail_lines.extend(_render_payment_items("- 预支", payment.prepay_items))
    detail_lines.append(
        f"已付合计：{_format_decimal(pricing.paid_total)}｜预支合计：{_format_decimal(pricing.prepay_total)}"
    )
    detail_lines.append(f"待确认条数：{len(payment.pending_items)}")
    detail_lines.append(
        "4）应付：工资 + 餐补 + 路补 - 已付 - 预支"
        f" = {_format_decimal(pricing.payable)}"
    )
    if pricing.payable < 0:
        detail_lines.append(
            f"【当期应付为负：员工需返还或下期冲减｜负值金额：¥{_format_decimal(-pricing.payable)}】"
        )
    detail_lines.append("5）差异清单：")
    for item in differences:
        detail_lines.append(f"- {item}")
    detail_lines.append("6）校核摘要：")
    detail_lines.extend(_render_checks(checks))
    detail_lines.append("7）审计留痕：")
    detail_lines.append(f"- run_id: {run_id}")
    detail_lines.append(f"- 规则版本: {VERSION_NOTE}")
    detail_lines.append(f"- input_hash: {input_hash}")
    detail_lines.append("- output_hash: __OUTPUT_HASH__ (不含hash行)")
    if attendance.fangzhuang_hits:
        detail_lines.append(f"- 防撞标记: {len(attendance.fangzhuang_hits)}条")
    detail_lines.append(VERSION_NOTE)
    detail_lines.append("日期（模式→出勤）")
    for label, dates in attendance.date_sets.items():
        if dates:
            detail_lines.append(f"{label}: {_build_date_list(dates)}")

    compressed_lines = ["【压缩版（发员工）】"]
    if pricing.wage_total != 0:
        compressed_lines.append(
            f"工资：{_format_decimal(pricing.wage_total)}"
            f"（全组{group_yes_days}天 + 单防撞{single_yes_days}天）"
        )
    if pricing.meal_total != 0:
        compressed_lines.append(
            f"餐补：{_format_decimal(pricing.meal_total)}（仅全组参与）"
        )
    if pricing.travel_total != 0:
        compressed_lines.append(
            f"路补：{_format_decimal(pricing.travel_total)}（项目已结束={'是' if project_ended else '否'}）"
        )
    compressed_lines.append(
        f"应付：{_format_decimal(pricing.payable)}"
    )

    detailed = "\n".join(detail_lines)
    compressed = "\n".join(compressed_lines)
    output_hash_source = "\n\n".join(
        [detailed.replace("__OUTPUT_HASH__ (不含hash行)", ""), compressed]
    )
    output_hash = _hash_payload(output_hash_source)
    detailed = detailed.replace("__OUTPUT_HASH__", output_hash)

    return "\n\n".join([detailed, compressed])
