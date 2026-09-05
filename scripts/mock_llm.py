from __future__ import annotations

import json

from fastapi import FastAPI


app = FastAPI()


TOOL_BY_PHASE = {
    "inspecting": "inspect_openapi",
    "generating": "generate_test_cases",
    "executing": "execute_tests",
    "searching_bugs": "search_bug_knowledge",
    "reporting": "save_report",
    "completed": "finish",
}


@app.post("/chat/completions")
def chat_completions(payload: dict) -> dict:
    user_message = payload["messages"][-1]["content"]

    prompt = json.loads(user_message)

    phase = prompt["phase"]

    tool_name = TOOL_BY_PHASE.get(
        phase,
        "finish",
    )

    decision = {
        "tool_name": tool_name,
        "arguments": {},
        "reason": (
            f"Mock LLM 根据 phase={phase} "
            f"选择工具 {tool_name}"
        ),
    }

    return {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        decision,
                        ensure_ascii=False,
                    )
                }
            }
        ]
    }
