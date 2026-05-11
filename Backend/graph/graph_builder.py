"""Graph write-layer: immutable versioned nodes + relationships."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from .ast_parser import ParsedChange
from .embedding_service import EmbeddingService
from .neo4j_client import Neo4jClient


class GraphBuilder:
    def __init__(self, client: Neo4jClient, embedding_service: EmbeddingService) -> None:
        self.client = client
        self.embedding_service = embedding_service

    @staticmethod
    def _ts() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _version_id(file_path: str, commit_hash: str, summary_seed: str) -> str:
        return hashlib.sha1(f"{file_path}|{commit_hash}|{summary_seed}".encode("utf-8")).hexdigest()

    @staticmethod
    def _summary_id(owner_id: str, kind: str, text: str) -> str:
        digest = hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()[:16]
        return f"{owner_id}:{kind}:{digest}"

    def upsert_commit(
        self,
        commit_hash: str,
        message: str,
        branch: str,
        parent_hash: str | None,
        timestamp: str | None = None,
        importance: float = 1.0,
    ) -> None:
        ts = timestamp or self._ts()
        commit_embedding = self.embedding_service.embed_text(message or f"commit {commit_hash}")
        self.client.run_many(
            [
                (
                    """
                    MERGE (c:Commit {commit_hash: $commit_hash})
                    ON CREATE SET c.message = $message, c.timestamp = $timestamp, c.importance = $importance, c.embedding = $embedding
                    """,
                    {
                        "commit_hash": commit_hash,
                        "message": message,
                        "timestamp": ts,
                        "importance": importance,
                        "embedding": commit_embedding,
                    },
                ),
                ("MERGE (b:Branch {name: $branch})", {"branch": branch}),
                (
                    """
                    MATCH (c:Commit {commit_hash: $commit_hash}), (b:Branch {name: $branch})
                    MERGE (c)-[:BELONGS_TO_BRANCH]->(b)
                    """,
                    {"commit_hash": commit_hash, "branch": branch},
                ),
            ]
        )
        if parent_hash:
            self.client.run(
                """
                MERGE (p:Commit {commit_hash: $parent_hash})
                MATCH (c:Commit {commit_hash: $commit_hash})
                MERGE (c)-[:RELATED_TO {type: 'PARENT'}]->(p)
                """,
                {"commit_hash": commit_hash, "parent_hash": parent_hash},
            )

    def write_change(
        self,
        parsed: ParsedChange,
        commit_hash: str,
        semantic_summary: str,
        event_type: str,
    ) -> str:
        ts = self._ts()
        version_id = self._version_id(parsed.file_path, commit_hash, parsed.summary_seed)
        file_id = parsed.file_path

        file_embedding = self.embedding_service.embed_text(
            f"{parsed.file_path} functions={parsed.functions} classes={parsed.classes} imports={parsed.imports}"
        )
        summary_embedding = self.embedding_service.embed_text(semantic_summary)

        self.client.run_many(
            [
                (
                    """
                    MERGE (f:File {file_id: $file_id})
                    ON CREATE SET f.path = $path, f.created_at = $timestamp
                    """,
                    {"file_id": file_id, "path": parsed.file_path, "timestamp": ts},
                ),
                (
                    """
                    CREATE (v:Version {
                        version_id: $version_id,
                        file_id: $file_id,
                        commit_hash: $commit_hash,
                        timestamp: $timestamp,
                        modified_lines: $modified_lines,
                        language: $language,
                        event_type: $event_type,
                        embedding: $embedding
                    })
                    """,
                    {
                        "version_id": version_id,
                        "file_id": file_id,
                        "commit_hash": commit_hash,
                        "timestamp": ts,
                        "modified_lines": parsed.modified_lines,
                        "language": parsed.language,
                        "event_type": event_type,
                        "embedding": file_embedding,
                    },
                ),
                (
                    """
                    MATCH (f:File {file_id: $file_id}), (v:Version {version_id: $version_id})
                    MERGE (f)-[:AFFECTS]->(v)
                    """,
                    {"file_id": file_id, "version_id": version_id},
                ),
                (
                    """
                    MATCH (c:Commit {commit_hash: $commit_hash}), (v:Version {version_id: $version_id})
                    MERGE (f:File {file_id: $file_id})
                    MERGE (f)-[:MODIFIED_IN]->(c)
                    MERGE (v)-[:INTRODUCED_IN]->(c)
                    """,
                    {"file_id": file_id, "commit_hash": commit_hash, "version_id": version_id},
                ),
            ]
        )

        prev = self.client.run(
            """
            MATCH (prev:Version {file_id: $file_id})
            WHERE prev.version_id <> $version_id
            RETURN prev.version_id AS version_id, prev.timestamp AS ts
            ORDER BY ts DESC
            LIMIT 1
            """,
            {"file_id": file_id, "version_id": version_id},
        )
        if prev:
            self.client.run(
                """
                MATCH (p:Version {version_id: $prev_id}), (v:Version {version_id: $version_id})
                MERGE (p)-[:REFACTORED_TO]->(v)
                """,
                {"prev_id": prev[0]["version_id"], "version_id": version_id},
            )

        self._write_symbols(parsed, version_id)
        self._write_semantic_summary(owner_id=version_id, text=semantic_summary, kind="file", embedding=summary_embedding)
        return version_id

    def _write_symbols(self, parsed: ParsedChange, version_id: str) -> None:
        file_id = parsed.file_path
        statements: list[tuple[str, dict[str, Any] | None]] = []

        for cls in parsed.classes:
            class_id = f"{file_id}::{cls}"
            statements.extend(
                [
                    ("MERGE (c:Class {class_id: $class_id}) SET c.name = $name, c.file_id = $file_id", {"class_id": class_id, "name": cls, "file_id": file_id}),
                    (
                        """
                        MATCH (v:Version {version_id: $version_id}), (c:Class {class_id: $class_id})
                        MERGE (v)-[:AFFECTS]->(c)
                        """,
                        {"version_id": version_id, "class_id": class_id},
                    ),
                ]
            )

        for fn in parsed.functions:
            fn_id = f"{file_id}::{fn}"
            fn_summary = f"{fn} evolved in {file_id} at version {version_id}"
            fn_embedding = self.embedding_service.embed_text(fn_summary)
            statements.extend(
                [
                    (
                        """
                        MERGE (f:Function {function_id: $fn_id})
                        SET f.name = $name, f.file_id = $file_id, f.embedding = $embedding
                        """,
                        {"fn_id": fn_id, "name": fn, "file_id": file_id, "embedding": fn_embedding},
                    ),
                    (
                        """
                        MATCH (v:Version {version_id: $version_id}), (f:Function {function_id: $fn_id})
                        MERGE (v)-[:AFFECTS]->(f)
                        """,
                        {"version_id": version_id, "fn_id": fn_id},
                    ),
                ]
            )
            self._write_function_summary(function_id=fn_id, text=fn_summary, embedding=fn_embedding)

        for dep in parsed.dependencies:
            statements.extend(
                [
                    ("MERGE (d:Feature {feature_id: $feature_id}) SET d.name = $name", {"feature_id": dep, "name": dep}),
                    (
                        """
                        MATCH (file:File {file_id: $file_id}), (d:Feature {feature_id: $feature_id})
                        MERGE (file)-[:IMPORTS]->(d)
                        MERGE (file)-[:DEPENDS_ON]->(d)
                        """,
                        {"file_id": file_id, "feature_id": dep},
                    ),
                ]
            )

        for call in parsed.calls:
            callee_id = f"{file_id}::{call}"
            statements.extend(
                [
                    (
                        "MERGE (callee:Function {function_id: $callee_id}) SET callee.name = $name",
                        {"callee_id": callee_id, "name": call},
                    ),
                ]
            )
            for fn in parsed.functions:
                caller_id = f"{file_id}::{fn}"
                statements.append(
                    (
                        """
                        MATCH (caller:Function {function_id: $caller_id}), (callee:Function {function_id: $callee_id})
                        MERGE (caller)-[:CALLS]->(callee)
                        """,
                        {"caller_id": caller_id, "callee_id": callee_id},
                    )
                )

        if statements:
            self.client.run_many(statements)

    def _write_semantic_summary(self, owner_id: str, text: str, kind: str, embedding: list[float]) -> None:
        if not text.strip():
            return
        summary_id = self._summary_id(owner_id, kind, text)
        self.client.run(
            """
            MERGE (s:SemanticSummary {summary_id: $summary_id})
            ON CREATE SET s.text = $text, s.kind = $kind, s.timestamp = $timestamp, s.embedding = $embedding
            WITH s
            MATCH (v:Version {version_id: $owner_id})
            MERGE (s)-[:RELATED_TO]->(v)
            """,
            {
                "summary_id": summary_id,
                "text": text,
                "kind": kind,
                "timestamp": self._ts(),
                "embedding": embedding,
                "owner_id": owner_id,
            },
        )

    def _write_function_summary(self, function_id: str, text: str, embedding: list[float]) -> None:
        summary_id = self._summary_id(function_id, "function", text)
        self.client.run(
            """
            MERGE (s:SemanticSummary {summary_id: $summary_id})
            ON CREATE SET s.text = $text, s.kind = 'function', s.timestamp = $timestamp, s.embedding = $embedding
            WITH s
            MATCH (f:Function {function_id: $function_id})
            MERGE (s)-[:RELATED_TO]->(f)
            """,
            {
                "summary_id": summary_id,
                "text": text,
                "timestamp": self._ts(),
                "embedding": embedding,
                "function_id": function_id,
            },
        )

    def write_bug_fix_link(self, bug_id: str, commit_hash: str, note: str = "") -> None:
        self.client.run(
            """
            MERGE (b:Bug {bug_id: $bug_id})
            ON CREATE SET b.created_at = $timestamp
            SET b.note = CASE WHEN $note = '' THEN b.note ELSE $note END
            MERGE (c:Commit {commit_hash: $commit_hash})
            MERGE (b)-[:FIXED_BY]->(c)
            """,
            {"bug_id": bug_id, "commit_hash": commit_hash, "timestamp": self._ts(), "note": note},
        )

