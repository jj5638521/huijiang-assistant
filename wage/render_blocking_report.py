"""Render blocking report for wage settlement."""
from __future__ import annotations

from typing import Iterable

from .checks import CheckResult


def render_blocking_report(
    *,
    person_name: str | None,
    project_name: str | None,
    run_id: str,
    version_note: str,
    input_hash: str,
    hard_failures: Iterable[CheckResult],
    missing_fields: list[str],
    invalid_items: list[str],
    suggestions: list[str],
    include_hash: bool,
    include_audit: bool,
    output_hash_placeholder: str,
) -> str:
    lines = ["【阻断｜工资结算】"]
    title = f"对象: {person_name or '未知'}"
    if project_name:
        title += f"｜项目: {project_name}"
    lines.append(title)
    lines.append("阻断原因:")
    for check in hard_failures:
        lines.append(f"- [{check.code}] {check.name}: {check.detail}")
    if missing_fields:
        lines.append("缺失项:")
        for item in missing_fields:
            lines.append(f"- {item}")
    if invalid_items:
        lines.append("异常项:")
        for item in invalid_items:
            lines.append(f"- {item}")
    if suggestions:
        lines.append("修复建议:")
        for item in suggestions:
            lines.append(f"- {item}")
    if include_audit:
        lines.append("审计留痕:")
        lines.append(f"- run_id: {run_id}")
        lines.append(f"- 规则版本: {version_note}")
        if include_hash:
            lines.append(f"- input_hash: {input_hash}")
            lines.append(f"- output_hash: {output_hash_placeholder}")
    return "\n".join(lines)
