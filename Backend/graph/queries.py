"""Reusable Cypher query snippets for GraphRAG operations."""

SCHEMA_QUERIES = [
    "CREATE CONSTRAINT file_id IF NOT EXISTS FOR (f:File) REQUIRE f.file_id IS UNIQUE",
    "CREATE CONSTRAINT function_id IF NOT EXISTS FOR (f:Function) REQUIRE f.function_id IS UNIQUE",
    "CREATE CONSTRAINT class_id IF NOT EXISTS FOR (c:Class) REQUIRE c.class_id IS UNIQUE",
    "CREATE CONSTRAINT commit_hash IF NOT EXISTS FOR (c:Commit) REQUIRE c.commit_hash IS UNIQUE",
    "CREATE CONSTRAINT bug_id IF NOT EXISTS FOR (b:Bug) REQUIRE b.bug_id IS UNIQUE",
    "CREATE CONSTRAINT feature_id IF NOT EXISTS FOR (f:Feature) REQUIRE f.feature_id IS UNIQUE",
    "CREATE CONSTRAINT branch_name IF NOT EXISTS FOR (b:Branch) REQUIRE b.name IS UNIQUE",
    "CREATE CONSTRAINT version_id IF NOT EXISTS FOR (v:Version) REQUIRE v.version_id IS UNIQUE",
    "CREATE CONSTRAINT summary_id IF NOT EXISTS FOR (s:SemanticSummary) REQUIRE s.summary_id IS UNIQUE",
    "CREATE INDEX file_path_idx IF NOT EXISTS FOR (f:File) ON (f.path)",
    "CREATE INDEX commit_time_idx IF NOT EXISTS FOR (c:Commit) ON (c.timestamp)",
    "CREATE INDEX version_time_idx IF NOT EXISTS FOR (v:Version) ON (v.timestamp)",
]

EXAMPLE_RETRIEVAL = """
UNWIND $files AS path
MATCH (f:File {file_id: path})
MATCH (f)-[*1..2]-(n)
RETURN labels(n)[0] AS node_type, n
LIMIT 100
"""

EXAMPLE_BUG_LINEAGE = """
MATCH (b:Bug)-[:FIXED_BY]->(c:Commit)<-[:INTRODUCED_IN]-(v:Version)<-[:AFFECTS]-(f:File)
RETURN b.bug_id AS bug, c.commit_hash AS fixed_by, f.path AS impacted_file
ORDER BY c.timestamp DESC
LIMIT 50
"""

