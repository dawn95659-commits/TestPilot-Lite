from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from .models import AgentState, utc_now


class SessionNotFound(KeyError):
    pass


class SessionStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, session_id: str) -> Path:
        try:
            normalized = str(UUID(session_id))
        except ValueError as exc:
            raise SessionNotFound(session_id) from exc
        return self.directory / f"{normalized}.json"

    def save(self, state: AgentState) -> AgentState:
        state.updated_at = utc_now()
        path = self._path(state.session_id)
        temp = path.with_suffix(".tmp")
        temp.write_text(state.model_dump_json(indent=2), encoding="utf-8")
        temp.replace(path)
        return state

    def load(self, session_id: str) -> AgentState:
        path = self._path(session_id)
        if not path.exists():
            raise SessionNotFound(session_id)
        return AgentState.model_validate(json.loads(path.read_text(encoding="utf-8")))

