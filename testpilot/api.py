from __future__ import annotations

import json

from fastapi import FastAPI, HTTPException

from .bug_search import BugKnowledgeBase
from .config import Settings, settings
from .controller import AgentController
from .http_client import LocalHttpClient
from .models import (
    AgentState,
    ApprovalRequest,
    CreateSessionRequest,
    Phase,
    TraceEvent,
)
from .planner import build_planner
from .reporting import build_report_data
from .store import SessionNotFound, SessionStore


def build_controller(app_settings: Settings) -> AgentController:
    return AgentController(
        settings=app_settings,
        store=SessionStore(app_settings.sessions_dir),
        planner=build_planner(app_settings),
        http_client=LocalHttpClient(
            allowed_ports=app_settings.allowed_ports,
            timeout_seconds=app_settings.timeout_seconds,
        ),
        bug_knowledge=BugKnowledgeBase(app_settings.bug_knowledge_path),
    )


def create_app(
    controller: AgentController | None = None,
    app_settings: Settings = settings,
) -> FastAPI:
    app = FastAPI(
        title="TestPilot Lite",
        version="0.1.0",
        description="仅测试本地自建 API 的学习型智能测试 Agent。",
    )
    app.state.controller = controller or build_controller(app_settings)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/sessions", response_model=AgentState, status_code=201)
    def create_session(request: CreateSessionRequest) -> AgentState:
        state = app.state.controller.create(
            goal=request.goal,
            openapi_url=str(request.openapi_url),
            max_cases=request.max_cases,
        )
        return state

    def load_state(session_id: str) -> AgentState:
        try:
            return app.state.controller.store.load(session_id)
        except SessionNotFound as exc:
            raise HTTPException(status_code=404, detail="会话不存在") from exc

    @app.get("/sessions/{session_id}", response_model=AgentState)
    def get_session(session_id: str) -> AgentState:
        return load_state(session_id)
    
    @app.get("/sessions/{session_id}/trace",response_model=list[TraceEvent],)
    def get_trace(session_id: str) -> list[TraceEvent]:
        state = load_state(session_id)
        return state.trace

    @app.post("/sessions/{session_id}/approve", response_model=AgentState)
    def approve_session(session_id: str, request: ApprovalRequest) -> AgentState:
        state = load_state(session_id)
        try:
            return app.state.controller.approve(state, request.approved)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/sessions/{session_id}/continue", response_model=AgentState)
    def continue_session(session_id: str) -> AgentState:
        state = load_state(session_id)
        if state.phase == Phase.WAITING_APPROVAL:
            raise HTTPException(status_code=409, detail="需要先进行人工审批")
        return app.state.controller.run(state)

    @app.get("/sessions/{session_id}/report")
    def get_report(session_id: str) -> dict:
        state = load_state(session_id)
        if state.phase != Phase.COMPLETED:
            raise HTTPException(status_code=409, detail="报告尚未生成")
        if state.report_json_path:
            with open(state.report_json_path, "r", encoding="utf-8") as file:
                return json.load(file)
        return build_report_data(state)

    return app


app = create_app()

