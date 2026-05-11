"""Ranking logic for hybrid GraphRAG retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import sqrt


def _safe_parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        if ts.endswith("Z"):
            ts = ts.replace("Z", "+00:00")
        return datetime.fromisoformat(ts)
    except Exception:
        return None


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sqrt(sum(x * x for x in a))
    nb = sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


@dataclass
class RankWeights:
    recency: float = 0.3
    dependency_strength: float = 0.2
    semantic_similarity: float = 0.35
    bug_frequency: float = 0.1
    commit_importance: float = 0.05


def recency_score(timestamp: str | None) -> float:
    dt = _safe_parse_iso(timestamp)
    if not dt:
        return 0.0
    age_days = (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).days
    if age_days <= 1:
        return 1.0
    if age_days <= 7:
        return 0.8
    if age_days <= 30:
        return 0.5
    return 0.2


def compute_rank(item: dict, query_embedding: list[float], weights: RankWeights | None = None) -> float:
    w = weights or RankWeights()
    semantic = cosine_similarity(query_embedding, item.get("embedding") or [])
    recency = recency_score(item.get("timestamp"))
    dep_strength = min(float(item.get("hop_distance", 2) or 2), 2.0)
    dep_strength = 1.0 - (dep_strength / 2.0)
    bug_freq = min(float(item.get("bug_frequency", 0) or 0), 5.0) / 5.0
    importance = min(float(item.get("importance", 1.0) or 1.0), 5.0) / 5.0
    return (
        w.recency * recency
        + w.dependency_strength * dep_strength
        + w.semantic_similarity * semantic
        + w.bug_frequency * bug_freq
        + w.commit_importance * importance
    )

