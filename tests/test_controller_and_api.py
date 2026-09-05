from __future__ import annotations

from fastapi.testclient import TestClient

from testpilot.api import create_app
from testpilot.models import Phase


def test_controller_pauses_for_approval(controller) -> None:
    state = controller.create(
        goal="test fixture api",
        openapi_url="http://127.0.0.1:8001/openapi.json",
        max_cases=12,
    )
    assert state.phase == Phase.WAITING_APPROVAL
    assert state.requires_approval
    assert [event.tool_name for event in state.trace] == ["inspect_openapi", "generate_test_cases"]


def test_controller_completes_after_approval(controller) -> None:
    state = controller.create(
        goal="test fixture api",
        openapi_url="http://127.0.0.1:8001/openapi.json",
        max_cases=12,
    )
    completed = controller.approve(state, approved=True)
    assert completed.phase == Phase.COMPLETED
    assert completed.results
    assert all(result.passed for result in completed.results)
    assert completed.report_json_path


def test_controller_rejects_write_cases_but_runs_gets(controller) -> None:
    state = controller.create(
        goal="test fixture api",
        openapi_url="http://127.0.0.1:8001/openapi.json",
        max_cases=12,
    )
    completed = controller.approve(state, approved=False)
    assert completed.phase == Phase.COMPLETED
    assert any(result.blocked for result in completed.results)
    assert any(result.passed for result in completed.results)


def test_api_full_flow(controller) -> None:
    client = TestClient(create_app(controller=controller))
    response = client.post(
        "/sessions",
        json={
            "goal": "test fixture api",
            "openapi_url": "http://127.0.0.1:8001/openapi.json",
            "max_cases": 12,
        },
    )
    assert response.status_code == 201
    state = response.json()
    assert state["phase"] == "waiting_approval"

    approved = client.post(
        f"/sessions/{state['session_id']}/approve",
        json={"approved": True},
    )
    assert approved.status_code == 200
    assert approved.json()["phase"] == "completed"

    report = client.get(f"/sessions/{state['session_id']}/report")
    assert report.status_code == 200
    assert report.json()["summary"]["failed_cases"] == 0


def test_api_rejects_nonlocal_target(controller) -> None:
    client = TestClient(create_app(controller=controller))
    response = client.post(
        "/sessions",
        json={
            "goal": "test external api",
            "openapi_url": "http://example.com:8001/openapi.json",
            "max_cases": 2,
        },
    )
    assert response.status_code == 201
    assert response.json()["phase"] == "failed"
    assert "只允许" in response.json()["error"]


def test_api_returns_404_for_unknown_session(controller) -> None:
    client = TestClient(create_app(controller=controller))
    response = client.get("/sessions/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404

def test_api_returns_404_when_approving_unknown_session(controller) -> None:
    client = TestClient(create_app(controller=controller))

    response = client.post(
        "/sessions/00000000-0000-0000-0000-000000000000/approve",
        json={"approved": True},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "会话不存在"


def test_api_continue_requires_approval_first(controller) -> None:
    client = TestClient(create_app(controller=controller))

    created = client.post(
        "/sessions",
        json={
            "goal": "test fixture api",
            "openapi_url": "http://127.0.0.1:8001/openapi.json",
            "max_cases": 12,
        },
    )

    assert created.status_code == 201
    state = created.json()
    assert state["phase"] == "waiting_approval"

    response = client.post(
        f"/sessions/{state['session_id']}/continue"
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "需要先进行人工审批"
