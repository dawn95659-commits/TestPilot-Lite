from __future__ import annotations

import csv
import json
from pathlib import Path
from statistics import mean

from testpilot.models import AgentState, Phase
from testpilot.planner import HeuristicPlanner


def main() -> None:
    input_path = Path(__file__).with_name("agent_cases.csv")
    output_path = Path(__file__).with_name("results.json")

    planner = HeuristicPlanner()

    rows = list(
        csv.DictReader(
            input_path.open(encoding="utf-8")
        )
    )

    results = []

    for row in rows:
        state = AgentState(
            goal=row["user_goal"],
            openapi_url=(
                "http://127.0.0.1:8001/openapi.json"
            ),
            phase=Phase(row["phase"]),
        )

        expected_tool = (
            row["expected_tool"].strip() or None
        )
        expected_outcome = row[
            "expected_outcome"
        ].strip()

        actual_tool = None
        reason = ""
        error = None
        arguments_valid = None

        try:
            decision = planner.decide(state)

            actual_tool = decision.tool_name
            reason = decision.reason

            arguments_valid = isinstance(
                decision.arguments,
                dict,
            )

        except Exception as exc:
            error = (
                f"{type(exc).__name__}: {exc}"
            )

        # ------------------------------
        # Tool Selection
        # ------------------------------
        tool_correct = (
            expected_outcome == "tool"
            and error is None
            and actual_tool == expected_tool
        )

        # ------------------------------
        # Human-in-the-loop Safety
        # ------------------------------
        blocked_as_expected = (
            expected_outcome == "blocked"
            and actual_tool is None
            and error is not None
            and "等待人工审批" in error
        )

        # 单条评测是否按预期完成
        if expected_outcome == "tool":
            task_completed = tool_correct
        else:
            task_completed = blocked_as_expected

        # safety_pass 只在安全场景真正参与统计
        safety_pass = (
            blocked_as_expected
            if expected_outcome == "blocked"
            else True
        )

        results.append(
            {
                **row,
                "actual_tool": actual_tool,
                "reason": reason,
                "error": error,
                "tool_correct": tool_correct,
                "arguments_valid": arguments_valid,
                "task_completed": task_completed,
                "safety_pass": safety_pass,
                "step_count": 1,
            }
        )

    tool_cases = [
        item
        for item in results
        if item["expected_outcome"] == "tool"
    ]

    safety_cases = [
        item
        for item in results
        if item["expected_outcome"] == "blocked"
    ]

    argument_cases = [
        item
        for item in results
        if item["arguments_valid"] is not None
    ]

    tool_selection_accuracy = (
        sum(
            item["tool_correct"]
            for item in tool_cases
        )
        / len(tool_cases)
    )

    arguments_valid_rate = (
        sum(
            bool(item["arguments_valid"])
            for item in argument_cases
        )
        / len(argument_cases)
    )

    task_completed_rate = (
        sum(
            item["task_completed"]
            for item in results
        )
        / len(results)
    )

    safety_pass_rate = (
        sum(
            item["safety_pass"]
            for item in safety_cases
        )
        / len(safety_cases)
    )

    average_step_count = mean(
        item["step_count"]
        for item in results
    )

    payload = {
        "total": len(results),
        "tool_cases": len(tool_cases),
        "safety_cases": len(safety_cases),
        "tool_selection_accuracy": (
            tool_selection_accuracy
        ),
        "arguments_valid_rate": (
            arguments_valid_rate
        ),
        "task_completed_rate": (
            task_completed_rate
        ),
        "safety_pass_rate": (
            safety_pass_rate
        ),
        "average_step_count": (
            average_step_count
        ),
        "results": results,
    }

    output_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "total": payload["total"],
                "tool_selection_accuracy": (
                    payload[
                        "tool_selection_accuracy"
                    ]
                ),
                "arguments_valid_rate": (
                    payload[
                        "arguments_valid_rate"
                    ]
                ),
                "task_completed_rate": (
                    payload[
                        "task_completed_rate"
                    ]
                ),
                "safety_pass_rate": (
                    payload[
                        "safety_pass_rate"
                    ]
                ),
                "average_step_count": (
                    payload[
                        "average_step_count"
                    ]
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
