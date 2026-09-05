from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .models import BugAdvice


TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")


def _tokens(text: str) -> set[str]:
    return {token.lower() for token in TOKEN_RE.findall(text)}


class BugKnowledgeBase:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.entries: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))

    def search(self, query: str, top_k: int = 2) -> list[BugAdvice]:
        query_tokens = _tokens(query)
        scored: list[tuple[float, dict[str, Any]]] = []
        for entry in self.entries:
            haystack = " ".join(
                [entry["title"], entry["likely_cause"], *entry["keywords"], *entry["checks"]]
            )
            entry_tokens = _tokens(haystack)
            overlap = len(query_tokens & entry_tokens)
            score = overlap / max(len(query_tokens), 1)
            if score > 0:
                scored.append((score, entry))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            BugAdvice(
                bug_id=entry["bug_id"],
                title=entry["title"],
                score=round(score, 4),
                likely_cause=entry["likely_cause"],
                checks=entry["checks"],
            )
            for score, entry in scored[:top_k]
        ]

