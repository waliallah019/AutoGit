"""Neo4j client and schema management for GraphRAG memory."""

from __future__ import annotations

import os
from typing import Any, Iterable

try:
    from neo4j import GraphDatabase
except Exception:  # pragma: no cover - optional dependency fallback
    GraphDatabase = None


class Neo4jClient:
    """Thin Neo4j wrapper with schema bootstrap helpers."""

    def __init__(
        self,
        uri: str | None = None,
        username: str | None = None,
        password: str | None = None,
        database: str | None = None,
    ) -> None:
        self.uri = uri or os.getenv("NEO4J_URI")
        self.username = username or os.getenv("NEO4J_USER")
        self.password = password or os.getenv("NEO4J_PASSWORD")
        self.database = database or os.getenv("NEO4J_DATABASE", "neo4j")

        self._driver = None
        if GraphDatabase and self.uri and self.username and self.password:
            self._driver = GraphDatabase.driver(self.uri, auth=(self.username, self.password))

    @property
    def enabled(self) -> bool:
        return self._driver is not None

    def close(self) -> None:
        if self._driver:
            self._driver.close()

    def run(self, query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Run a query and return records as dictionaries."""
        if not self._driver:
            return []
        with self._driver.session(database=self.database) as session:
            result = session.run(query, params or {})
            return [record.data() for record in result]

    def run_many(self, statements: Iterable[tuple[str, dict[str, Any] | None]]) -> None:
        """Run multiple write statements in a single session."""
        if not self._driver:
            return
        with self._driver.session(database=self.database) as session:
            for query, params in statements:
                session.run(query, params or {})

    def ensure_schema(self) -> None:
        """Create constraints/indexes used by the GraphRAG memory layer."""
        if not self._driver:
            return

        statements: list[tuple[str, dict[str, Any] | None]] = [
            ("CREATE CONSTRAINT file_id IF NOT EXISTS FOR (f:File) REQUIRE f.file_id IS UNIQUE", None),
            ("CREATE CONSTRAINT function_id IF NOT EXISTS FOR (f:Function) REQUIRE f.function_id IS UNIQUE", None),
            ("CREATE CONSTRAINT class_id IF NOT EXISTS FOR (c:Class) REQUIRE c.class_id IS UNIQUE", None),
            ("CREATE CONSTRAINT commit_hash IF NOT EXISTS FOR (c:Commit) REQUIRE c.commit_hash IS UNIQUE", None),
            ("CREATE CONSTRAINT bug_id IF NOT EXISTS FOR (b:Bug) REQUIRE b.bug_id IS UNIQUE", None),
            ("CREATE CONSTRAINT feature_id IF NOT EXISTS FOR (f:Feature) REQUIRE f.feature_id IS UNIQUE", None),
            ("CREATE CONSTRAINT branch_name IF NOT EXISTS FOR (b:Branch) REQUIRE b.name IS UNIQUE", None),
            ("CREATE CONSTRAINT version_id IF NOT EXISTS FOR (v:Version) REQUIRE v.version_id IS UNIQUE", None),
            (
                "CREATE CONSTRAINT summary_id IF NOT EXISTS FOR (s:SemanticSummary) REQUIRE s.summary_id IS UNIQUE",
                None,
            ),
            ("CREATE INDEX file_path_idx IF NOT EXISTS FOR (f:File) ON (f.path)", None),
            ("CREATE INDEX commit_time_idx IF NOT EXISTS FOR (c:Commit) ON (c.timestamp)", None),
            ("CREATE INDEX version_time_idx IF NOT EXISTS FOR (v:Version) ON (v.timestamp)", None),
            ("CREATE INDEX summary_time_idx IF NOT EXISTS FOR (s:SemanticSummary) ON (s.timestamp)", None),
        ]
        self.run_many(statements)

