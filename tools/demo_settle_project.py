"""Demo entrypoint for project batch settlement."""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Iterable

from wage.attendance_pipe import collect_attendance_people, compute_attendance
from wage.command import parse_command
from wage.payment_pipe import collect_payment_people
from wage.settle_person import DAILY_WAGE_MAP, ROLE_WAGE_MAP, settle_person

from . import demo_settle_person


@dataclass(frozen=True)
class PersonSummary:
    name: str
    output_text: str
    blocked: bool
    pending: bool
    blocking_codes: list[str]
    log_path: Path | None


def _resolve_input_paths(data_dir: Path) -> tuple[Path, Path] | None:
    current_dir = data_dir / "当前"
    if not current_dir.exists():
        print("请把本次CSV拖到 数据/当前/（文件名随意）")
        return None
    candidates = demo_settle_person._scan_csv_candidates(current_dir)
    if not candidates:
        print("请把本次CSV拖到 数据/当前/（文件名随意）")
        return None
    if len(candidates) > 2:
        demo_settle_person._report_current_dir_overflow(candidates)
        return None
    selected = demo_settle_person._select_input_paths(candidates)
    if selected is None:
        if len(candidates) == 1:
            print("当前目录只有 1 个 CSV，无法判定为合并表，请再放一份")
        else:
            demo_settle_person._print_candidate_report(candidates)
        return None
    return selected


def _parse_blocking_codes(output: str) -> list[str]:
    codes: list[str] = []
    for line in output.splitlines():
        match = re.match(r"- \[([A-Z0-9]+)\]", line)
        if match:
            codes.append(match.group(1))
    return codes


def _extract_log_path(output: str) -> Path | None:
    match = re.search(r"日志：logs/([^\s]+\.json)", output)
    if not match:
        return None
    return Path("logs") / match.group(1)


def _load_pending_flag(log_path: Path | None) -> bool:
    if not log_path or not log_path.exists():
        return False
    payload = json.loads(log_path.read_text(encoding="utf-8"))
    pending_summary = payload.get("pending_summary")
    if isinstance(pending_summary, dict):
        return sum(pending_summary.values()) > 0
    return False


def _resolve_role(
    name: str,
    table_roles: dict[str, str],
    role_overrides: dict[str, str],
) -> tuple[str, str]:
    if name in table_roles:
        return table_roles[name], "表"
    if name in role_overrides:
        return role_overrides[name], "口令"
    return "组员", "默认"


def _resolve_daily_wage(
    name: str,
    *,
    fixed_daily_rates: dict[str, Decimal],
    role: str,
    table_roles: dict[str, str],
) -> tuple[Decimal, str]:
    if name in fixed_daily_rates:
        return fixed_daily_rates[name], "口令"
    if name in DAILY_WAGE_MAP:
        return DAILY_WAGE_MAP[name], "系统"
    if name in table_roles:
        return ROLE_WAGE_MAP.get(table_roles[name], Decimal("0")), "表"
    if role in ROLE_WAGE_MAP:
        return ROLE_WAGE_MAP[role], "默认"
    return Decimal("0"), "兜底"


def _render_summary(
    project_name: str,
    people: list[PersonSummary],
    fixed_rate_hits: dict[str, tuple[Decimal, str]],
    role_sources: dict[str, tuple[str, str]],
) -> str:
    total = len(people)
    blocked = sum(1 for person in people if person.blocked)
    success = total - blocked
    pending = sum(1 for person in people if person.pending)
    if total != success + blocked:
        raise ValueError("汇总人数不一致")

    lines = [
        "【汇总索引】",
        f"项目：{project_name}",
        f"总人数：{total}",
        f"成功：{success}",
        f"阻断：{blocked}",
        f"待确认：{pending}",
    ]

    if blocked:
        lines.append("阻断原因列表：")
        for person in people:
            if not person.blocked:
                continue
            codes = person.blocking_codes or ["UNKNOWN"]
            lines.append(f"- {person.name}: {','.join(codes)}")

    if fixed_rate_hits:
        lines.append("固定日薪命中：")
        for name, (rate, source) in fixed_rate_hits.items():
            lines.append(f"- {name}={rate}（来源：{source}）")

    if role_sources:
        lines.append("角色来源：")
        for name, (role, source) in role_sources.items():
            lines.append(f"- {name}={role}（来源：{source}）")

    return "\n".join(lines)


def settle_project(
    attendance_rows: Iterable[dict[str, str]],
    payment_rows: Iterable[dict[str, str]],
    *,
    command: dict[str, object],
    project_name: str,
    output_dir: Path,
    runtime_overrides: dict[str, object],
) -> Path:
    attendance_list = list(attendance_rows)
    payment_list = list(payment_rows)
    attendance_result = compute_attendance(attendance_list, project_name, None)
    table_roles = attendance_result.role_by_person
    people = sorted(
        collect_attendance_people(attendance_list, project_name)
        | collect_payment_people(payment_list, project_name)
    )

    role_overrides = command.get("role_overrides") or {}
    fixed_daily_rates = command.get("fixed_daily_rates") or {}

    fixed_rate_hits: dict[str, tuple[Decimal, str]] = {}
    role_sources: dict[str, tuple[str, str]] = {}
    person_summaries: list[PersonSummary] = []

    for name in people:
        role, role_source = _resolve_role(name, table_roles, role_overrides)
        daily_rate, rate_source = _resolve_daily_wage(
            name,
            fixed_daily_rates=fixed_daily_rates,
            role=role,
            table_roles=table_roles,
        )
        role_sources[name] = (role, role_source)
        if rate_source in {"口令", "系统"}:
            fixed_rate_hits[name] = (daily_rate, rate_source)

        per_runtime = dict(runtime_overrides)
        per_runtime["daily_group"] = str(daily_rate)
        per_runtime["require_project_ended"] = 1

        output_text = settle_person(
            attendance_list,
            payment_list,
            person_name=name,
            role=role,
            project_ended=command.get("project_ended"),
            project_name=project_name,
            runtime_overrides=per_runtime,
        )
        file_path = output_dir / f"工资单_{name}.txt"
        file_path.write_text(output_text, encoding="utf-8")

        blocked = output_text.startswith("【阻断｜工资结算】")
        log_path = _extract_log_path(output_text)
        pending = _load_pending_flag(log_path)
        person_summaries.append(
            PersonSummary(
                name=name,
                output_text=output_text,
                blocked=blocked,
                pending=pending,
                blocking_codes=_parse_blocking_codes(output_text) if blocked else [],
                log_path=log_path,
            )
        )

    summary_text = _render_summary(
        project_name,
        person_summaries,
        fixed_rate_hits,
        role_sources,
    )
    summary_path = output_dir / "汇总索引.txt"
    summary_path.write_text(summary_text, encoding="utf-8")
    return summary_path


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    data_dir = repo_root / "data"
    data_dir.mkdir(exist_ok=True)

    command_path = data_dir / "当前" / "口令.txt"
    command_text = demo_settle_person._read_command_file(command_path)
    if not command_text:
        return 0

    command = parse_command(command_text)
    if command.get("mode") != "project":
        print("口令非项目结算模式，请使用工资：开头或切换到项目结算：")
        return 0

    selected = _resolve_input_paths(data_dir)
    if selected is None:
        return 0

    attendance_rows = demo_settle_person._read_csv(selected[0])
    payment_rows = demo_settle_person._read_csv(selected[1])

    project_name = command.get("project_name")
    if not project_name:
        project_name = demo_settle_person._derive_project_name(selected[0])
        command["project_name"] = project_name

    runtime_overrides = dict(command.get("runtime_overrides") or {})
    config_path = data_dir / "当前" / "配置.txt"
    runtime_overrides.update(demo_settle_person._read_runtime_overrides(config_path))
    runtime_overrides["attendance_source"] = selected[0].name
    runtime_overrides["payment_source"] = selected[1].name

    output_dir = repo_root / "输出" / "当前" / str(project_name)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = settle_project(
        attendance_rows,
        payment_rows,
        command=command,
        project_name=str(project_name),
        output_dir=output_dir,
        runtime_overrides=runtime_overrides,
    )
    print(summary_path.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
