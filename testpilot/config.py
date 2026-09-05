from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


def _csv_ints(value: str) -> frozenset[int]:
    return frozenset(int(item.strip()) for item in value.split(",") if item.strip())


@dataclass(frozen=True, slots=True)
class Settings:
    project_root: Path = PROJECT_ROOT
    allowed_ports: frozenset[int] = _csv_ints(
        os.getenv("TESTPILOT_ALLOWED_PORTS", "8001")
    )
    max_cases: int = int(os.getenv("TESTPILOT_MAX_CASES", "12"))
    max_steps: int = int(os.getenv("TESTPILOT_MAX_STEPS", "10"))
    timeout_seconds: float = float(os.getenv("TESTPILOT_TIMEOUT_SECONDS", "3"))
    planner: str = os.getenv("TESTPILOT_PLANNER", "heuristic").lower()
    llm_base_url: str | None = os.getenv("LLM_BASE_URL")
    llm_api_key: str | None = os.getenv("LLM_API_KEY")
    llm_model: str | None = os.getenv("LLM_MODEL")

    @property
    def sessions_dir(self) -> Path:
        return self.project_root / "data" / "sessions"

    @property
    def reports_dir(self) -> Path:
        return self.project_root / "data" / "reports"

    @property
    def bug_knowledge_path(self) -> Path:
        return self.project_root / "data" / "bug_knowledge.json"


settings = Settings()

