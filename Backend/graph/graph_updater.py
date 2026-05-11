"""Incremental ingestion pipeline for GraphRAG memory."""

from __future__ import annotations

import json
import os
import subprocess
import hashlib
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv
from langchain_groq import ChatGroq

from .ast_parser import ASTChangeParser
from .embedding_service import EmbeddingService
from .graph_builder import GraphBuilder
from .neo4j_client import Neo4jClient
from .retriever import GraphRetriever

load_dotenv()


@dataclass
class IngestionResult:
    status: str
    event_type: str
    changed_files: list[str]
    versions_created: int
    commit_hash: str
    details: dict[str, Any]


class GraphUpdater:
    """Owns schema bootstrap, incremental ingestion, and memory retrieval."""

    def __init__(self) -> None:
        self.client = Neo4jClient()
        self.embedding = EmbeddingService()
        self.parser = ASTChangeParser()
        self.builder = GraphBuilder(self.client, self.embedding)
        self.retriever = GraphRetriever(self.client, self.embedding)
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="autogit-graph")
        self._init_schema_if_available()

    @property
    def enabled(self) -> bool:
        return self.client.enabled

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=False)
        self.client.close()

    def _init_schema_if_available(self) -> None:
        if self.client.enabled:
            self.client.ensure_schema()

    @staticmethod
    def _run_git(args: list[str]) -> str:
        result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="ignore")
        if result.returncode != 0:
            return ""
        return result.stdout.strip()

    def _current_commit_hash(self) -> str:
        return self._run_git(["git", "rev-parse", "HEAD"])

    def _current_branch(self) -> str:
        return self._run_git(["git", "rev-parse", "--abbrev-ref", "HEAD"]) or "main"

    def _parent_commit_hash(self, commit_hash: str) -> str | None:
        if not commit_hash:
            return None
        parent = self._run_git(["git", "rev-parse", f"{commit_hash}^"])
        return parent or None

    def _git_diff(self, commit_hash: str | None, staged: bool = True) -> str:
        if commit_hash:
            return self._run_git(["git", "show", "--format=", "--unified=0", commit_hash])
        if staged:
            return self._run_git(["git", "diff", "--cached", "--unified=0"])
        return self._run_git(["git", "diff", "--unified=0"])

    def _diff_changed_files(self, diff_text: str) -> list[str]:
        file_chunks = self.parser.split_diff_by_file(diff_text)
        return list(file_chunks.keys())

    @staticmethod
    def _repo_root() -> str:
        result = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
        if result.returncode != 0:
            return os.getcwd()
        return result.stdout.strip()

    def _llm_summary(self, event_type: str, file_path: str, parsed_info: dict[str, Any]) -> str:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            return self._fallback_summary(event_type, file_path, parsed_info)

        prompt = (
            "Summarize this change in one concise sentence focused on evolution and intent.\n"
            f"Event: {event_type}\n"
            f"File: {file_path}\n"
            f"Parsed details: {json.dumps(parsed_info, ensure_ascii=True)[:1800]}\n"
            "Return only the sentence."
        )
        try:
            llm = ChatGroq(
                model="llama-3.1-8b-instant",
                api_key=api_key,
                temperature=0.1,
                max_tokens=80,
            )
            resp = llm.invoke(prompt)
            out = (resp.content or "").strip()
            return out or self._fallback_summary(event_type, file_path, parsed_info)
        except Exception:
            return self._fallback_summary(event_type, file_path, parsed_info)

    @staticmethod
    def _fallback_summary(event_type: str, file_path: str, parsed_info: dict[str, Any]) -> str:
        fn = ", ".join(parsed_info.get("functions", [])[:3]) or "core logic"
        cls = ", ".join(parsed_info.get("classes", [])[:2])
        cls_part = f"; classes: {cls}" if cls else ""
        return f"{event_type}: evolved {file_path} around {fn}{cls_part}."

    def ingest(
        self,
        event_type: str,
        commit_hash: str | None = None,
        diff_text: str | None = None,
        run_async: bool = False,
    ) -> IngestionResult | Future[IngestionResult]:
        if run_async:
            return self._executor.submit(self._ingest_sync, event_type, commit_hash, diff_text)
        return self._ingest_sync(event_type, commit_hash, diff_text)

    def maybe_ingest(
        self,
        event_type: str,
        commit_hash: str | None = None,
        diff_text: str | None = None,
    ) -> IngestionResult | Future[IngestionResult]:
        resolved_diff = diff_text or self._git_diff(commit_hash=commit_hash, staged=False)
        should_async = len(resolved_diff) > 6000 or len(self._diff_changed_files(resolved_diff)) > 3
        return self.ingest(event_type=event_type, commit_hash=commit_hash, diff_text=resolved_diff, run_async=should_async)

    def on_file_save(self, file_path: str) -> IngestionResult | Future[IngestionResult]:
        diff = self._run_git(["git", "diff", "--unified=0", "--", file_path])
        return self.maybe_ingest(event_type="file_save", diff_text=diff)

    def on_branch_merge(self, commit_hash: str | None = None) -> IngestionResult | Future[IngestionResult]:
        return self.maybe_ingest(event_type="branch_merge", commit_hash=commit_hash)

    def _ingest_sync(
        self,
        event_type: str,
        commit_hash: str | None = None,
        diff_text: str | None = None,
    ) -> IngestionResult:
        if not self.client.enabled:
            return IngestionResult(
                status="disabled",
                event_type=event_type,
                changed_files=[],
                versions_created=0,
                commit_hash="",
                details={"reason": "neo4j_not_configured"},
            )

        commit = commit_hash or self._current_commit_hash()

        raw_diff = diff_text or self._git_diff(commit_hash=commit, staged=False)
        if not commit:
            seed = hashlib.sha1(raw_diff.encode("utf-8", errors="ignore")).hexdigest()[:16]
            commit = f"workspace:{seed}"

        branch = self._current_branch()
        parent = self._parent_commit_hash(commit) if not commit.startswith("workspace:") else None
        message = (
            self._run_git(["git", "show", "-s", "--format=%s", commit])
            if not commit.startswith("workspace:")
            else ""
        )
        self.builder.upsert_commit(
            commit_hash=commit,
            message=message or f"{event_type} update",
            branch=branch,
            parent_hash=parent,
        )

        file_patches = self.parser.split_diff_by_file(raw_diff)
        changed_files = list(file_patches.keys())
        if not changed_files:
            return IngestionResult(
                status="success",
                event_type=event_type,
                changed_files=[],
                versions_created=0,
                commit_hash=commit,
                details={"reason": "no_changed_files"},
            )

        repo_root = self._repo_root()
        versions_created = 0
        summaries: dict[str, str] = {}

        for file_path, patch in file_patches.items():
            parsed = self.parser.parse(repo_root=repo_root, file_path=file_path, file_patch=patch)
            parsed_info = {
                "functions": parsed.functions,
                "classes": parsed.classes,
                "imports": parsed.imports,
                "dependencies": parsed.dependencies,
                "modified_lines_count": len(parsed.modified_lines),
            }
            summary = self._llm_summary(event_type, file_path, parsed_info)
            summaries[file_path] = summary
            self.builder.write_change(parsed=parsed, commit_hash=commit, semantic_summary=summary, event_type=event_type)
            versions_created += 1

            # Lightweight bug lineage hook from commit semantics.
            if "fix" in summary.lower() or "bug" in summary.lower():
                bug_id = f"{file_path}:{commit[:8]}"
                self.builder.write_bug_fix_link(bug_id=bug_id, commit_hash=commit, note=summary)

        return IngestionResult(
            status="success",
            event_type=event_type,
            changed_files=changed_files,
            versions_created=versions_created,
            commit_hash=commit,
            details={"summaries": summaries},
        )

    def build_context(self, current_change_text: str, diff_text: str | None = None, top_k: int = 12) -> dict[str, Any]:
        if not self.client.enabled:
            return {
                "current_change": current_change_text,
                "related_history": [],
                "architectural_dependencies": [],
                "related_bugs": [],
                "important_commits": [],
                "potential_impact": [],
            }
        resolved_diff = diff_text or self._git_diff(commit_hash=None, staged=True) or self._git_diff(commit_hash=None, staged=False)
        changed_files = self._diff_changed_files(resolved_diff)
        return self.retriever.retrieve(changed_files=changed_files, current_change_summary=current_change_text, top_k=top_k)

