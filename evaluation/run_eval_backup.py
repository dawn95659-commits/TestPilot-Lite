from __future__ import annotations

import csv
import json
from pathlib import Path

from testpilot.models import AgentState, Phase
from testpilot.planner import HeuristicPlanner


def main() -> None:
    input_path = Path(__file__).with_name("agent_cases.csv")
    output_path = Path(__file__).with_name("results.json")
    planner = HeuristicPlanner()
    rows = list(csv.DictReader(input_path.open(encoding="utf-8")))
    results = []
    for row in rows:
        state = AgentState(
            goal="评测规划器",
            openapi_url="http://127.0.0.1:8001/openapi.json",
            phase=Phase(row["phase"]),
        )
        actual = planner.decide(state).tool_name
        results.append({**row, "actual_tool": actual, "correct": actual == row["expected_tool"]})
    accuracy = sum(item["correct"] for item in results) / len(results)
    payload = {"total": len(results), "tool_selection_accuracy": accuracy, "results": results}
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"total": len(results), "tool_selection_accuracy": accuracy}, indent=2))


if __name__ == "__main__":
    main()

