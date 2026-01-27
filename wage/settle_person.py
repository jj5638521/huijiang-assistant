"""Wage settlement logic (skeleton)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping


@dataclass(frozen=True)
class SettlementResult:
    """Lightweight placeholder result."""

    attendance_rows: int
    payment_rows: int


def settle_person(
    attendance_rows: Iterable[Mapping[str, str]],
    payment_rows: Iterable[Mapping[str, str]],
) -> SettlementResult:
    """Return a minimal deterministic summary for now.

    Args:
        attendance_rows: Iterable of attendance CSV rows.
        payment_rows: Iterable of payment CSV rows.

    Returns:
        SettlementResult placeholder summary.
    """
    attendance_count = sum(1 for _ in attendance_rows)
    payment_count = sum(1 for _ in payment_rows)
    return SettlementResult(
        attendance_rows=attendance_count,
        payment_rows=payment_count,
    )
