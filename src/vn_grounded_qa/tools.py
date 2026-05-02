"""Bounded semantic tool layer."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, Iterable, List, Optional

from .store import GroundedStore


class ToolSession:
    def __init__(self, store: GroundedStore, max_calls: int = 6, max_searches: int = 2, trace_id: Optional[str] = None):
        self.store = store
        self.max_calls = max_calls
        self.max_searches = max_searches
        self.trace_id = trace_id
        self.calls: List[Dict[str, Any]] = []
        self._searches = 0

    def _record(self, name: str, args: Dict[str, Any], result_count: int) -> None:
        if len(self.calls) >= self.max_calls:
            raise RuntimeError("Tool call ceiling exceeded")
        if name == "search_units":
            self._searches += 1
            if self._searches > self.max_searches:
                raise RuntimeError("Search call ceiling exceeded")
        call = {"tool": name, "args": args, "result_count": result_count}
        self.calls.append(call)
        if self.trace_id:
            self.store.record_tool_call(self.trace_id, len(self.calls), name, args, result_count)

    def search_units(self, query: str, top_k: int = 10, doc_type: Optional[str] = None, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        active_filters = dict(filters or {})
        if doc_type and "doc_type" not in active_filters:
            active_filters["doc_type"] = doc_type
        hits = self.store.search_units(query, min(top_k, 20), filters=active_filters)
        self._record("search_units", {"query": query, "top_k": top_k, "filters": active_filters}, len(hits))
        return [asdict(hit) for hit in hits]

    def read_units(self, unit_ids: Iterable[str]) -> List[Dict[str, Any]]:
        ids = list(unit_ids)
        hits = self.store.read_units(ids)
        self._record("read_units", {"unit_ids": ids}, len(hits))
        return [asdict(hit) for hit in hits]

    def expand_context(self, unit_id: str, depth: int = 1) -> List[Dict[str, Any]]:
        hits = self.store.expand_context(unit_id, depth=min(depth, 1))
        self._record("expand_context", {"unit_id": unit_id, "depth": depth}, len(hits))
        return [asdict(hit) for hit in hits]

    def resolve_terms(self, query: str) -> List[str]:
        terms = self.store.resolve_terms(query)
        self._record("resolve_terms", {"query": query}, len(terms))
        return terms

    def get_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        row = self.store.get_document(doc_id)
        self._record("get_document", {"doc_id": doc_id}, 1 if row else 0)
        if not row:
            return None
        document = dict(row)
        document["outline"] = self.store.get_document_outline(doc_id)
        return document

    def get_applicable_version(self, doc_family_id: str, as_of: str = "") -> Optional[Dict[str, Any]]:
        row = self.store.get_applicable_version(doc_family_id, as_of=as_of)
        self._record("get_applicable_version", {"doc_family_id": doc_family_id, "as_of": as_of}, 1 if row else 0)
        return dict(row) if row else None
