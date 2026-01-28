"""Wage settlement logic for per-person settlement."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Mapping

from .attendance_pipe import AttendanceResult, compute_attendance
from .checks import CheckResult, run_checks
from .payment_pipe import PaymentResult, compute_payments
from .render_blocking_report import render_blocking_report
from .ruleset import get_ruleset_version

RULE_VERSION = get_ruleset_version()
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
    road_raw_total = sum(
        (item.amount for item in payment.road_allowance_items), Decimal("0")
    )

    wage_group = daily_group * Decimal(group_yes_days)
    wage_single_yes = single_yes * Decimal(single_yes_days)
    wage_single_no = single_no * Decimal(single_no_days)
    wage_total = wage_group + wage_single_yes + wage_single_no

    meal_total = Decimal("25") * Decimal(group_yes_days) + Decimal("40") * Decimal(
        group_no_days
    )
    travel_total = (
        min(Decimal("200"), road_raw_total) if project_ended else Decimal("0")
    )

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


def _render_check_summary(checks: list[CheckResult]) -> str:
    parts = []
    for check in checks:
        symbol = "✓" if check.passed else "×"
        parts.append(f"{check.code}{symbol}")
    return " ".join(parts)


def _serialize_payment_items(items: list[object]) -> list[dict[str, str]]:
    serialized = []
    for item in items:
        serialized.append(
            {
                "date": item.date,
                "name": item.name,
                "project": item.project,
                "amount": _format_decimal(item.amount),
                "category": item.category,
                "status": item.status,
                "voucher": item.voucher,
                "raw_type": item.raw_type,
            }
        )
    return serialized


def _write_log(run_id: str, payload: dict) -> None:
    log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{run_id}.json"
    log_path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )


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

    verbose = int(runtime_overrides.get("verbose", 0))
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
        log_payload = {
            "run_id": run_id,
            "ruleset_version": RULE_VERSION,
            "version_note": VERSION_NOTE,
            "input_hash": input_hash,
            "hard_failures": [
                {
                    "code": check.code,
                    "name": check.name,
                    "detail": check.detail,
                }
                for check in hard_failures
            ],
            "missing_items": missing_items,
            "invalid_items": invalid_items,
            "suggestions": suggestions,
        }
        _write_log(run_id, log_payload)
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
    road_raw_total = sum(
        (item.amount for item in payment.road_allowance_items), Decimal("0")
    )

    pending_total = len(payment.pending_items) + len(payment.missing_amount_candidates)
    pending_reasons: dict[str, int] = {}
    if payment.invalid_status_items:
        pending_reasons["状态无效"] = len(payment.invalid_status_items)
    pending_other = len(payment.pending_items) - len(payment.invalid_status_items)
    if pending_other:
        pending_reasons["类别待确认"] = pending_other
    if payment.missing_amount_candidates:
        pending_reasons["金额缺失"] = len(payment.missing_amount_candidates)

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
        (
            f"- 餐补：25×{group_yes_days} + 40×{group_no_days}="
            f"{_format_decimal(pricing.meal_total)}"
        ),
        (
            f"- 路补：min(200, 路补有效金额合计{_format_decimal(road_raw_total)})="
            f"{_format_decimal(pricing.travel_total)}"
            if project_ended
            else f"- 路补：{_format_decimal(pricing.travel_total)}（项目已结束=否）"
        ),
        "3）已付/预支明细：",
    ]

    detail_lines.append(
        f"- 已付合计：{_format_decimal(pricing.paid_total)}｜预支合计：{_format_decimal(pricing.prepay_total)}"
    )
    if verbose:
        detail_lines.extend(_render_payment_items("- 已付明细", payment.paid_items))
        detail_lines.extend(_render_payment_items("- 预支明细", payment.prepay_items))
    else:
        detail_lines.append(f"- 明细详见 logs/{run_id}.json")
    if pending_total:
        pending_summary = "，".join(
            f"{reason}{count}条" for reason, count in pending_reasons.items()
        )
        detail_lines.append(f"待确认汇总：{pending_summary}")
    detail_lines.append(
        "4）应付：工资 + 餐补 + 路补 - 已付 - 预支"
        f" = {_format_decimal(pricing.payable)}"
    )
    if pricing.payable < 0:
        detail_lines.append(
            f"【当期应付为负：员工需返还或下期冲减｜负值金额：¥{_format_decimal(-pricing.payable)}】"
        )
    detail_lines.append("5）差异清单：")
    if differences == ["无"]:
        detail_lines.append("- 无")
    else:
        detail_lines.append(f"- 共{len(differences)}条，详见 logs/{run_id}.json")
        if verbose:
            for item in differences:
                detail_lines.append(f"- {item}")
    detail_lines.append("6）备注与校核摘要：")
    detail_lines.append("餐补口径：25×施工天 + 40×未施工天")
    detail_lines.append("二管道隔离：工资结算与支付流水分账核算")
    detail_lines.append(f"单防撞命中：{len(attendance.fangzhuang_hits)}条")
    detail_lines.append("7）校核摘要：")
    detail_lines.append(_render_check_summary(checks))
    detail_lines.append("8）审计留痕：")
    detail_lines.append(f"- run_id: {run_id}")
    detail_lines.append(f"- 规则版本: {VERSION_NOTE}")
    detail_lines.append(f"- input_hash: {input_hash}")
    detail_lines.append("- output_hash: __OUTPUT_HASH__ (不含hash行)")
    detail_lines.append(VERSION_NOTE)

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
    log_payload = {
        "run_id": run_id,
        "ruleset_version": RULE_VERSION,
        "version_note": VERSION_NOTE,
        "input_hash": input_hash,
        "output_hash": output_hash,
        "attendance": {
            "date_sets": attendance.date_sets,
            "mode_by_date": attendance.mode_by_date,
            "missing_fields": attendance.missing_fields,
            "invalid_dates": attendance.invalid_dates,
            "project_mismatches": attendance.project_mismatches,
            "conflict_logs": attendance.conflict_logs,
            "normalization_logs": attendance.normalization_logs,
            "auto_corrections": attendance.auto_corrections,
            "fangzhuang_hits": attendance.fangzhuang_hits,
        },
        "payment": {
            "paid_items": _serialize_payment_items(payment.paid_items),
            "prepay_items": _serialize_payment_items(payment.prepay_items),
            "project_expense_items": _serialize_payment_items(payment.project_expense_items),
            "road_allowance_items": _serialize_payment_items(
                payment.road_allowance_items
            ),
            "pending_items": _serialize_payment_items(payment.pending_items),
            "missing_amount_candidates": payment.missing_amount_candidates,
            "invalid_status_items": _serialize_payment_items(payment.invalid_status_items),
            "missing_fields": payment.missing_fields,
            "invalid_amounts": payment.invalid_amounts,
            "project_mismatches": payment.project_mismatches,
            "voucher_duplicates": payment.voucher_duplicates,
            "empty_voucher_duplicates": payment.empty_voucher_duplicates,
        },
        "pricing": {
            "wage_group": _format_decimal(pricing.wage_group),
            "wage_single_yes": _format_decimal(pricing.wage_single_yes),
            "wage_single_no": _format_decimal(pricing.wage_single_no),
            "wage_total": _format_decimal(pricing.wage_total),
            "meal_total": _format_decimal(pricing.meal_total),
            "travel_total": _format_decimal(pricing.travel_total),
            "paid_total": _format_decimal(pricing.paid_total),
            "prepay_total": _format_decimal(pricing.prepay_total),
            "payable": _format_decimal(pricing.payable),
        },
        "differences": differences if differences != ["无"] else [],
        "pending_summary": pending_reasons,
        "checks": [
            {
                "code": check.code,
                "name": check.name,
                "passed": check.passed,
                "severity": check.severity,
                "detail": check.detail,
            }
            for check in checks
        ],
    }
    _write_log(run_id, log_payload)

    return "\n\n".join([detailed, compressed])
