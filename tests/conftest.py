from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import json


from testpilot.bug_search import BugKnowledgeBase
from testpilot.config import Settings
from testpilot.controller import AgentController
from testpilot.http_client import LocalHttpClient
from testpilot.planner import HeuristicPlanner
from testpilot.store import SessionStore


@pytest.fixture
def openapi_document() -> dict:
    return {
        "openapi": "3.1.0",
        "info": {"title": "Fixture API", "version": "1"},
        "paths": {
            "/items": {
                "get": {
                    "summary": "List items",
                    "operationId": "list_items",
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/json": {
                                    "schema": {"type": "array", "items": {"$ref": "#/components/schemas/Item"}}
                                }
                            },
                        }
                    },
                }
            },
            "/items/{item_id}": {
                "get": {
                    "summary": "Get item",
                    "operationId": "get_item",
                    "parameters": [
                        {
                            "name": "item_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "integer"},
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Item"}}},
                        },
                        "404": {
                            "description": "Missing",
                            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}},
                        },
                        "422": {"description": "Validation"},
                    },
                }
            },
            "/orders": {
                "post": {
                    "summary": "Create order",
                    "operationId": "create_order",
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/OrderCreate"}}},
                    },
                    "responses": {
                        "201": {
                            "description": "Created",
                            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Order"}}},
                        },
                        "422": {"description": "Validation"},
                    },
                }
            },
        },
        "components": {
            "schemas": {
                "Item": {
                    "type": "object",
                    "properties": {"id": {"type": "integer"}, "name": {"type": "string"}},
                    "required": ["id", "name"],
                },
                "Error": {
                    "type": "object",
                    "properties": {"detail": {"type": "string"}},
                    "required": ["detail"],
                },
                "OrderCreate": {
                    "type": "object",
                    "properties": {
                        "product_id": {"type": "integer", "minimum": 1},
                        "quantity": {"type": "integer", "minimum": 1},
                    },
                    "required": ["product_id", "quantity"],
                },
                "Order": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "product_id": {"type": "integer"},
                        "quantity": {"type": "integer"},
                    },
                    "required": ["id", "product_id", "quantity"],
                },
            }
        },
    }


@pytest.fixture
def mock_transport(openapi_document: dict) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/openapi.json":
            return httpx.Response(200, json=openapi_document)
        if request.method == "GET" and path == "/items":
            return httpx.Response(200, json=[{"id": 1, "name": "demo"}])
        if request.method == "GET" and path == "/items/1":
            return httpx.Response(200, json={"id": 1, "name": "demo"})
        if request.method == "GET" and path == "/items/999999":
            return httpx.Response(404, json={"detail": "not found"})
        if request.method == "GET" and path == "/items/not-a-number":
            return httpx.Response(422, json={"detail": []})
        if request.method == "POST" and path == "/orders":
            if request.content in {b"", b"null"}:
                return httpx.Response(422, json={"detail": []})
            body = json.loads(request.content.decode("utf-8"))
            if (body.get("product_id", 0) < 1 or body.get("quantity", 0) < 1):
                return httpx.Response(422,json={"detail": []},)
            return httpx.Response(201, json={"id": 1, "product_id": 1, "quantity": 1})
        return httpx.Response(404, json={"detail": "unknown fixture path"})

    return httpx.MockTransport(handler)


@pytest.fixture
def app_settings(tmp_path: Path) -> Settings:
    return Settings(
        project_root=tmp_path,
        allowed_ports=frozenset({8001}),
        max_cases=12,
        max_steps=10,
        timeout_seconds=1,
        planner="heuristic",
    )


@pytest.fixture
def controller(
    app_settings: Settings,
    mock_transport: httpx.MockTransport,
) -> AgentController:
    data = app_settings.project_root / "data"
    data.mkdir(parents=True)
    source = Path(__file__).resolve().parents[1] / "data" / "bug_knowledge.json"
    bug_path = data / "bug_knowledge.json"
    bug_path.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return AgentController(
        settings=app_settings,
        store=SessionStore(app_settings.sessions_dir),
        planner=HeuristicPlanner(),
        http_client=LocalHttpClient(
            allowed_ports=app_settings.allowed_ports,
            timeout_seconds=1,
            transport=mock_transport,
        ),
        bug_knowledge=BugKnowledgeBase(bug_path),
    )

