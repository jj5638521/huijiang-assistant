"""Payment pipeline for wage settlement."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Iterable, Mapping

DATE_HEADERS = ["报销日期", "支付日期", "打款日期", "日期"]
AMOUNT_HEADERS = ["报销金额", "金额", "支付金额", "实付金额"]
STATUS_HEADERS = ["报销状态", "状态", "付款状态"]
TYPE_HEADERS = ["报销类型", "费用类型", "类别", "类型", "科目"]
NAME_HEADERS = ["报销人员", "姓名", "收款人", "人员"]
PROJECT_HEADERS = ["项目", "项目名称"]
VOUCHER_HEADERS = ["上传凭证", "凭证号", "凭证", "票据号", "流水号", "订单号"]
REMARK_HEADERS = ["备注", "说明", "报销备注", "用途"]

CANDIDATE_AMOUNT_HEADERS = ["金额", "报销金额", "支付金额", "实付金额"]
CANDIDATE_CATEGORY_HEADERS = ["报销类型", "费用类型", "类型", "类别", "科目"]
CANDIDATE_STATUS_HEADERS = ["报销状态", "状态", "付款状态"]
CANDIDATE_VOUCHER_HEADERS = ["凭证号", "上传凭证", "票据号", "流水号", "订单号"]
CANDIDATE_REMARK_HEADERS = ["备注", "用途", "说明"]

STATUS_WHITELIST = {
    "已支付",
    "已转账",
    "已报销",
    "完成",
    "通过",
    "成功",
    "已结清",
    "OK",
    "已打款",
    "审核通过",
}


@dataclass(frozen=True)
class PaymentItem:
    date: str
    name: str
    project: str
    amount: Decimal
    category: str
    status: str
    voucher: str
    raw_type: str


@dataclass(frozen=True)
class PaymentResult:
    paid_items: list[PaymentItem]
    prepay_items: list[PaymentItem]
    project_expense_items: list[PaymentItem]
    road_allowance_items: list[PaymentItem]
    pending_items: list[PaymentItem]
    invalid_status_items: list[PaymentItem]
    missing_fields: list[str]
    invalid_amounts: list[str]
    missing_amount_candidates: list[str]
    project_mismatches: list[str]
    voucher_duplicates: list[str]
    empty_voucher_duplicates: list[str]

    @property
    def paid_total(self) -> Decimal:
        return sum((item.amount for item in self.paid_items), Decimal("0"))

    @property
    def prepay_total(self) -> Decimal:
        return sum((item.amount for item in self.prepay_items), Decimal("0"))


def _find_header(headers: set[str], candidates: list[str]) -> str | None:
    for candidate in candidates:
        if candidate in headers:
            return candidate
    return None


def _clean_amount_text(value: str) -> str:
    cleaned = (
        (value or "")
        .replace(",", "")
        .replace("¥", "")
        .replace("￥", "")
        .replace("元", "")
        .replace(" ", "")
        .replace("\u00a0", "")
        .strip()
    )
    return cleaned


def _parse_amount(value: str) -> tuple[Decimal | None, bool]:
    cleaned = _clean_amount_text(value)
    if not cleaned:
        return None, False
    try:
        return Decimal(cleaned), False
    except InvalidOperation:
        return None, True


def is_payment_candidate(row: Mapping[str, str]) -> bool:
    for header in CANDIDATE_AMOUNT_HEADERS:
        if _clean_amount_text(row.get(header, "")):
            return True
    for header_group in (
        CANDIDATE_CATEGORY_HEADERS,
        CANDIDATE_STATUS_HEADERS,
        CANDIDATE_VOUCHER_HEADERS,
        CANDIDATE_REMARK_HEADERS,
    ):
        for header in header_group:
            if row.get(header, "").strip():
                return True
    return False


def _normalize_date(value: str) -> str:
    return value.strip()


def _categorize(raw_type: str) -> str:
    text = raw_type.strip()
    if any(keyword in text for keyword in ("工资",)):
        return "工资"
    if any(keyword in text for keyword in ("预支", "借支", "预发")):
        return "预支"
    if any(keyword in text for keyword in ("餐补", "伙食", "盒饭", "工作餐")):
        return "餐补"
    if any(keyword in text for keyword in ("油费", "ETC")):
        return "路费"
    if any(keyword in text for keyword in ("路补", "顺风车", "拼车", "打车", "滴滴", "路费")):
        return "路补"
    return "其他"


def compute_payments(
    payment_rows: Iterable[Mapping[str, str]],
    project_name: str | None,
    target_person: str | None,
) -> PaymentResult:
    rows = list(payment_rows)
    headers = {key.strip() for row in rows for key in row.keys()}
    date_key = _find_header(headers, DATE_HEADERS)
    amount_key = _find_header(headers, AMOUNT_HEADERS)
    status_key = _find_header(headers, STATUS_HEADERS)
    type_key = _find_header(headers, TYPE_HEADERS)
    name_key = _find_header(headers, NAME_HEADERS)
    project_key = _find_header(headers, PROJECT_HEADERS)
    voucher_key = _find_header(headers, VOUCHER_HEADERS)
    remark_key = _find_header(headers, REMARK_HEADERS)

    missing_fields = []
    for key, label in (
        (date_key, "日期"),
        (amount_key, "金额"),
        (status_key, "状态"),
        (type_key, "类型"),
        (name_key, "姓名"),
    ):
        if key is None:
            missing_fields.append(label)

    invalid_amounts: list[str] = []
    missing_amount_candidates: list[str] = []
    project_mismatches: list[str] = []
    voucher_seen: set[tuple[str, str, Decimal]] = set()
    voucher_duplicates: list[str] = []
    empty_voucher_seen: set[tuple[str, str, str, Decimal, str]] = set()
    empty_voucher_duplicates: list[str] = []

    paid_items: list[PaymentItem] = []
    prepay_items: list[PaymentItem] = []
    project_expense_items: list[PaymentItem] = []
    road_allowance_items: list[PaymentItem] = []
    pending_items: list[PaymentItem] = []
    invalid_status_items: list[PaymentItem] = []

    for index, row in enumerate(rows, start=1):
        if not is_payment_candidate(row):
            continue
        if None in (date_key, amount_key, status_key, type_key, name_key):
            continue
        date_value = _normalize_date(row.get(date_key, ""))
        amount_raw = row.get(amount_key, "")
        status_value = row.get(status_key, "").strip()
        type_value = row.get(type_key, "").strip()
        name_value = row.get(name_key, "").strip()
        project_value = row.get(project_key, "").strip() if project_key else ""
        voucher_value = row.get(voucher_key, "").strip() if voucher_key else ""
        remark_value = row.get(remark_key, "").strip() if remark_key else ""

        amount, invalid_amount = _parse_amount(amount_raw)
        if amount is None:
            if invalid_amount:
                invalid_amounts.append(f"第{index}行 金额='{amount_raw}'")
            else:
                missing_amount_candidates.append(
                    f"第{index}行 疑似支付行但金额缺失: {amount_key}='{amount_raw}'"
                )
            continue

        if target_person and name_value and name_value != target_person:
            continue
        if project_name and project_value and project_value != project_name:
            project_mismatches.append(f"{name_value}@{date_value}: {project_value}")

        category = _categorize(type_value)
        item = PaymentItem(
            date=date_value,
            name=name_value,
            project=project_value,
            amount=amount,
            category=category,
            status=status_value,
            voucher=voucher_value,
            raw_type=type_value,
        )

        voucher_key_value = voucher_value or "TEMP"
        voucher_identity = (voucher_key_value, date_value, amount)
        if voucher_identity in voucher_seen:
            voucher_duplicates.append(f"{voucher_key_value}@{date_value}:{amount}")
        else:
            voucher_seen.add(voucher_identity)

        if not voucher_value:
            empty_key = (name_value, project_value, date_value, amount, type_value)
            if empty_key in empty_voucher_seen:
                empty_voucher_duplicates.append(
                    f"{name_value}@{project_value}@{date_value}:{amount}"
                )
            else:
                empty_voucher_seen.add(empty_key)

        if status_value not in STATUS_WHITELIST:
            pending_items.append(item)
            invalid_status_items.append(item)
            continue

        if category == "工资" or category == "餐补":
            paid_items.append(item)
        elif category == "预支":
            prepay_items.append(item)
        elif category == "路补":
            road_allowance_items.append(item)
        elif category == "路费":
            project_expense_items.append(item)
        else:
            pending_items.append(item)

    paid_items.sort(key=lambda item: (item.date, item.amount))
    prepay_items.sort(key=lambda item: (item.date, item.amount))
    project_expense_items.sort(key=lambda item: (item.date, item.amount))
    road_allowance_items.sort(key=lambda item: (item.date, item.amount))
    pending_items.sort(key=lambda item: (item.date, item.amount))
    invalid_status_items.sort(key=lambda item: (item.date, item.amount))

    return PaymentResult(
        paid_items=paid_items,
        prepay_items=prepay_items,
        project_expense_items=project_expense_items,
        road_allowance_items=road_allowance_items,
        pending_items=pending_items,
        invalid_status_items=invalid_status_items,
        missing_fields=missing_fields,
        invalid_amounts=invalid_amounts,
        missing_amount_candidates=missing_amount_candidates,
        project_mismatches=project_mismatches,
        voucher_duplicates=voucher_duplicates,
        empty_voucher_duplicates=empty_voucher_duplicates,
    )


def collect_payment_people(
    payment_rows: Iterable[Mapping[str, str]],
    project_name: str | None,
) -> set[str]:
    rows = list(payment_rows)
    headers = {key.strip() for row in rows for key in row.keys()}
    name_key = _find_header(headers, NAME_HEADERS)
    project_key = _find_header(headers, PROJECT_HEADERS)
    if name_key is None:
        return set()
    people: set[str] = set()
    for row in rows:
        if not is_payment_candidate(row):
            continue
        name_value = row.get(name_key, "").strip()
        if not name_value:
            continue
        raw_project = row.get(project_key, "").strip() if project_key else ""
        if project_name and raw_project and raw_project != project_name:
            continue
        people.add(name_value)
    return people
