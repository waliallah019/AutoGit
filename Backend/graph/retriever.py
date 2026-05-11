"""Hybrid retrieval: graph traversal + vector similarity + diff context."""

from __future__ import annotations

from typing import Any

from .context_formatter import ContextFormatter
from .embedding_service import EmbeddingService
from .neo4j_client import Neo4jClient
from .ranking import compute_rank


class GraphRetriever:
    def __init__(
        self,
        neo4j_client: Neo4jClient,
        embedding_service: EmbeddingService,
        formatter: ContextFormatter | None = None,
    ) -> None:
        self.client = neo4j_client
        self.embedding_service = embedding_service
        self.formatter = formatter or ContextFormatter()

    def retrieve(
        self,
        changed_files: list[str],
        current_change_summary: str,
        top_k: int = 12,
    ) -> dict[str, Any]:
        if not self.client.enabled or not changed_files:
            return self.formatter.format_context(current_change_summary, [])

        candidates = self._graph_candidates(changed_files)
        query_embedding = self.embedding_service.embed_text(current_change_summary)

        for item in candidates:
            item["score"] = compute_rank(item, query_embedding)

        ranked = sorted(candidates, key=lambda x: x.get("score", 0.0), reverse=True)[:top_k]
        return self.formatter.format_context(current_change_summary, ranked)

    def _graph_candidates(self, changed_files: list[str]) -> list[dict[str, Any]]:
        query = """
        UNWIND $files AS path
        MATCH (f:File {file_id: path})
        MATCH p=(f)-[*1..2]-(n)
        WITH n, min(length(p)) AS hop_distance
        WITH DISTINCT n, hop_distance
        OPTIONAL MATCH (n)<-[:FIXED_BY]-(b:Bug)
        OPTIONAL MATCH (n)<-[:MODIFIED_IN]-(ff:File)<-[:AFFECTS]-(v:Version)
        RETURN
          labels(n)[0] AS node_type,
          coalesce(n.summary_id, n.version_id, n.commit_hash, n.file_id, n.function_id, n.class_id, n.feature_id, n.bug_id, n.name) AS id,
          coalesce(n.text, n.message, n.path, n.name, n.file_id, n.commit_hash) AS text,
          coalesce(n.embedding, []) AS embedding,
          coalesce(n.timestamp, v.timestamp, '') AS timestamp,
          hop_distance,
          count(DISTINCT b) AS bug_frequency,
          coalesce(n.importance, 1.0) AS importance
        LIMIT 300
        """
        rows = self.client.run(query, {"files": changed_files})
        return rows or []

