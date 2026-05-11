"""Usage examples for GraphUpdater ingestion and retrieval."""

from __future__ import annotations

from .graph_updater import GraphUpdater


def example_post_commit_ingestion() -> None:
    memory = GraphUpdater()
    # Use async for larger commits automatically.
    memory.maybe_ingest(event_type="git_commit")


def example_file_save_ingestion(file_path: str) -> None:
    memory = GraphUpdater()
    memory.on_file_save(file_path)


def example_retrieval(user_request: str) -> dict:
    memory = GraphUpdater()
    return memory.build_context(current_change_text=user_request, top_k=10)

