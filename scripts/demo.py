from __future__ import annotations

import argparse
import json

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a TestPilot demo through its REST API")
    parser.add_argument("--backend", default="http://127.0.0.1:8000")
    parser.add_argument("--openapi", default="http://127.0.0.1:8001/openapi.json")
    parser.add_argument("--approve", action="store_true", help="Approve write operations")
    args = parser.parse_args()

    with httpx.Client(timeout=30, trust_env=False) as client:
        response = client.post(
            f"{args.backend}/sessions",
            json={
                "openapi_url": args.openapi,
                "goal": "为样例商城 API 生成并执行测试，输出报告",
                "max_cases": 12,
            },
        )
        response.raise_for_status()
        state = response.json()
        print(f"phase={state['phase']} session={state['session_id']}")
        if state["phase"] == "waiting_approval":
            response = client.post(
                f"{args.backend}/sessions/{state['session_id']}/approve",
                json={"approved": args.approve},
            )
            response.raise_for_status()
            state = response.json()
        report = client.get(f"{args.backend}/sessions/{state['session_id']}/report")
        report.raise_for_status()
        print(json.dumps(report.json()["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
