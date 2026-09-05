from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import AgentState


def build_report_data(state: AgentState) -> dict[str, Any]:
    executed = [result for result in state.results if not result.blocked]
    passed = sum(result.passed for result in executed)
    blocked = sum(result.blocked for result in state.results)
    return {
        "session_id": state.session_id,
        "goal": state.goal,
        "target": state.base_url,
        "summary": {
            "operations": len(state.operations),
            "generated_cases": len(state.test_cases),
            "executed_cases": len(executed),
            "passed_cases": passed,
            "failed_cases": len(executed) - passed,
            "blocked_cases": blocked,
            "pass_rate": round(passed / len(executed), 4) if executed else 0.0,
            "average_latency_ms": round(
                sum(item.latency_ms for item in executed) / len(executed), 2
            ) if executed else 0.0,
        },
        "results": [item.model_dump(mode="json") for item in state.results],
        "bug_advice": [item.model_dump(mode="json") for item in state.bug_advice],
        "trace": [item.model_dump(mode="json") for item in state.trace],
    }


def _markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# TestPilot 测试报告",
        "",
        f"- 会话：`{report['session_id']}`",
        f"- 目标：`{report['target']}`",
        f"- 测试目标：{report['goal']}",
        f"- 通过率：{summary['pass_rate']:.2%}",
        f"- 已执行 / 通过 / 失败 / 拦截：{summary['executed_cases']} / {summary['passed_cases']} / {summary['failed_cases']} / {summary['blocked_cases']}",
        f"- 平均响应时间：{summary['average_latency_ms']} ms",
        "",
        "## 用例结果",
        "",
        "| case_id | 状态 | HTTP | 耗时(ms) | 错误 |",
        "|---|---:|---:|---:|---|",
    ]
    for result in report["results"]:
        status = "BLOCKED" if result["blocked"] else ("PASS" if result["passed"] else "FAIL")
        error = "；".join(result["errors"]) or "-"
        lines.append(
            f"| {result['case_id']} | {status} | {result['actual_status'] or '-'} | {result['latency_ms']:.2f} | {error} |"
        )
    if report["bug_advice"]:
        lines.extend(["", "## 历史 Bug 建议", ""])
        for advice in report["bug_advice"]:
            lines.append(f"### {advice['title']}")
            lines.append("")
            lines.append(f"可能原因：{advice['likely_cause']}")
            lines.append("")
            lines.extend(f"- {item}" for item in advice["checks"])
            lines.append("")
    return "\n".join(lines) + "\n"


def save_report(state: AgentState, reports_dir: Path) -> tuple[Path, Path]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    report = build_report_data(state)
    json_path = reports_dir / f"{state.session_id}.json"
    markdown_path = reports_dir / f"{state.session_id}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(_markdown(report), encoding="utf-8")
    return json_path, markdown_path

