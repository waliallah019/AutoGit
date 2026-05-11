"""Compress retrieved memory into bounded structured context."""

from __future__ import annotations

from typing import Any


class ContextFormatter:
    def __init__(self, top_k: int = 12, max_items_per_section: int = 4) -> None:
        self.top_k = top_k
        self.max_items_per_section = max_items_per_section

    def format_context(
        self,
        current_change: str,
        ranked_items: list[dict[str, Any]],
    ) -> dict[str, Any]:
        top = ranked_items[: self.top_k]

        related_history: list[str] = []
        architectural_dependencies: list[str] = []
        related_bugs: list[str] = []
        important_commits: list[str] = []
        potential_impact: list[str] = []

        for item in top:
            typ = item.get("node_type", "Unknown")
            text = item.get("text") or item.get("name") or item.get("id") or ""
            if not text:
                continue
            if typ == "Commit":
                important_commits.append(text)
            elif typ in {"Feature", "Function", "Class", "File", "Version"}:
                architectural_dependencies.append(text)
            elif typ == "Bug":
                related_bugs.append(text)
            elif typ == "SemanticSummary":
                related_history.append(text)
            else:
                potential_impact.append(text)

        def clip(values: list[str]) -> list[str]:
            return values[: self.max_items_per_section]

        return {
            "current_change": current_change,
            "related_history": clip(related_history),
            "architectural_dependencies": clip(architectural_dependencies),
            "related_bugs": clip(related_bugs),
            "important_commits": clip(important_commits),
            "potential_impact": clip(potential_impact),
        }

