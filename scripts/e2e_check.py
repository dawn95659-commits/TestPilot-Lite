from __future__ import annotations

import subprocess
import sys
import time

import httpx


def wait_ready(url: str, timeout_seconds: float = 10) -> None:
    deadline = time.monotonic() + timeout_seconds
    with httpx.Client(timeout=1, trust_env=False) as client:
        while time.monotonic() < deadline:
            try:
                if client.get(url).is_success:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
    raise RuntimeError(f"服务未在规定时间内启动：{url}")


def main() -> None:
    commands = [
        [sys.executable, "-m", "uvicorn", "sample_api.main:app", "--host", "127.0.0.1", "--port", "8001"],
        [sys.executable, "-m", "uvicorn", "testpilot.api:app", "--host", "127.0.0.1", "--port", "8000"],
    ]
    processes = [subprocess.Popen(command) for command in commands]
    try:
        wait_ready("http://127.0.0.1:8001/docs")
        wait_ready("http://127.0.0.1:8000/health")
        with httpx.Client(timeout=30, trust_env=False) as client:
            created = client.post(
                "http://127.0.0.1:8000/sessions",
                json={
                    "openapi_url": "http://127.0.0.1:8001/openapi.json",
                    "goal": "端到端验证样例商城 API",
                    "max_cases": 12,
                },
            )
            created.raise_for_status()
            state = created.json()
            assert state["phase"] == "waiting_approval", state
            completed = client.post(
                f"http://127.0.0.1:8000/sessions/{state['session_id']}/approve",
                json={"approved": True},
            )
            completed.raise_for_status()
            state = completed.json()
            assert state["phase"] == "completed", state
            report = client.get(
                f"http://127.0.0.1:8000/sessions/{state['session_id']}/report"
            )
            report.raise_for_status()
            summary = report.json()["summary"]
            assert summary["failed_cases"] == 0, summary
            print("E2E PASS", summary)
    finally:
        for process in processes:
            process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    main()

