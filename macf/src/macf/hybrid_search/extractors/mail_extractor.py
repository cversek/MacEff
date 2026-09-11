"""
Extractor for cached Gmail thread records.

A thread record is the dict ``macf.gmail.fetch_thread`` stores in the private
cache: ``thread_id``, ``fetched_at`` and a ``messages`` list of headers + body
text. Records never rest on disk in plaintext, so the primary entry point is
``extract_record`` on an in-memory dict; ``extract_document`` exists only to
satisfy the AbstractExtractor contract and reads a JSON file when a test hands
it one.
"""

import json
from pathlib import Path
from typing import Any

from .base import AbstractExtractor


class MailExtractor(AbstractExtractor):
    """Fields and embedding text for one cached mail thread."""

    #: Body text kept per message for embedding; MiniLM truncates far below this anyway.
    body_chars = 2000

    @property
    def name(self) -> str:
        return "mail"

    def get_fts_columns(self) -> list[tuple[str, str]]:
        return [("thread_id", "TEXT"), ("subject", "TEXT"), ("from", "TEXT"),
                ("date", "TEXT"), ("text", "TEXT")]

    def extract_record(self, rec: dict[str, Any]) -> dict[str, Any]:
        """Flatten a thread record into the FTS columns."""
        msgs = rec.get("messages") or []
        last = msgs[-1] if msgs else {}
        parts = []
        for m in msgs:
            parts.append(m.get("subject", ""))
            parts.append(m.get("from", ""))
            parts.append((m.get("body") or "")[: self.body_chars])
        return {
            "thread_id": rec.get("thread_id", ""),
            "subject": last.get("subject", ""),
            "from": last.get("from", ""),
            "date": last.get("date", ""),
            "messages": len(msgs),
            "text": "\n".join(p for p in parts if p),
        }

    def extract_document(self, doc_path: Path) -> dict[str, Any]:
        return self.extract_record(json.loads(Path(doc_path).read_text()))

    def generate_embedding_text(self, doc_data: dict) -> str:
        return f"{doc_data.get('subject', '')}\n{doc_data.get('text', '')}"

    def should_index(self, doc_path: Path) -> bool:
        return doc_path.suffix == ".json"
