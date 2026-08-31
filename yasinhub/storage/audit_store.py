"""Durable audit / event store (#111).

Preserves PolicyEngine audit semantics while surviving process restart.
SharedState remains coordination/idempotency only — not a full audit DB.

Backends:
  memory — process-local (tests / default)
  file   — append-only JSONL under YASIN_AUDIT_DIR

Config:
  YASIN_AUDIT_BACKEND=memory|file
  YASIN_AUDIT_DIR=/path/to/dir
  YASIN_AUDIT_RETENTION_MAX=10000
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

from ..observer.execution_store import redact_secrets

logger = logging.getLogger(__name__)

DEFAULT_RETENTION_MAX = 10_000


class AuditEventStore(Protocol):
    def append(self, record: Dict[str, Any]) -> None:
        ...

    def list(
        self,
        *,
        limit: int = 100,
        actor: Optional[str] = None,
        execution_id: Optional[str] = None,
        action: Optional[str] = None,
        since: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        ...

    def clear(self) -> None:
        ...


def _normalize(record: Dict[str, Any]) -> Dict[str, Any]:
    return redact_secrets(dict(record))


class MemoryAuditStore:
    def __init__(self, *, retention_max: int = DEFAULT_RETENTION_MAX) -> None:
        self._lock = threading.RLock()
        self._items: List[Dict[str, Any]] = []
        self._retention_max = max(1, retention_max)

    def append(self, record: Dict[str, Any]) -> None:
        row = _normalize(record)
        with self._lock:
            self._items.append(row)
            if len(self._items) > self._retention_max:
                self._items = self._items[-self._retention_max :]

    def list(
        self,
        *,
        limit: int = 100,
        actor: Optional[str] = None,
        execution_id: Optional[str] = None,
        action: Optional[str] = None,
        since: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        with self._lock:
            items = list(self._items)
        if actor is not None:
            items = [i for i in items if i.get("actor") == actor]
        if execution_id is not None:
            items = [i for i in items if i.get("execution_id") == execution_id]
        if action is not None:
            items = [i for i in items if i.get("action") == action]
        if since is not None:
            items = [i for i in items if float(i.get("timestamp") or 0) >= since]
        return items[-max(1, limit) :]

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


class FileAuditStore:
    """Append-only JSONL audit log with bounded retention on read/append."""

    def __init__(self, directory: str, *, retention_max: int = DEFAULT_RETENTION_MAX) -> None:
        self._dir = Path(directory)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / "audit_events.jsonl"
        self._lock = threading.RLock()
        self._retention_max = max(1, retention_max)
        self._cache: Optional[List[Dict[str, Any]]] = None

    def _load(self) -> List[Dict[str, Any]]:
        if self._cache is not None:
            return self._cache
        items: List[Dict[str, Any]] = []
        if self._path.exists():
            try:
                with self._path.open("r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            items.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
            except OSError as exc:
                logger.warning("audit_store_read_failed err=%s", type(exc).__name__)
        if len(items) > self._retention_max:
            items = items[-self._retention_max :]
        self._cache = items
        return items

    def _rewrite(self, items: List[Dict[str, Any]]) -> None:
        tmp = self._path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for row in items:
                fh.write(json.dumps(row, default=str) + "\n")
        tmp.replace(self._path)

    def append(self, record: Dict[str, Any]) -> None:
        row = _normalize(record)
        with self._lock:
            items = self._load()
            items.append(row)
            if len(items) > self._retention_max:
                items = items[-self._retention_max :]
                self._rewrite(items)
            else:
                try:
                    with self._path.open("a", encoding="utf-8") as fh:
                        fh.write(json.dumps(row, default=str) + "\n")
                except OSError as exc:
                    logger.warning("audit_store_append_failed err=%s", type(exc).__name__)
            self._cache = items

    def list(
        self,
        *,
        limit: int = 100,
        actor: Optional[str] = None,
        execution_id: Optional[str] = None,
        action: Optional[str] = None,
        since: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        with self._lock:
            items = list(self._load())
        if actor is not None:
            items = [i for i in items if i.get("actor") == actor]
        if execution_id is not None:
            items = [i for i in items if i.get("execution_id") == execution_id]
        if action is not None:
            items = [i for i in items if i.get("action") == action]
        if since is not None:
            items = [i for i in items if float(i.get("timestamp") or 0) >= since]
        return items[-max(1, limit) :]

    def clear(self) -> None:
        with self._lock:
            self._cache = []
            try:
                if self._path.exists():
                    self._path.unlink()
            except OSError:
                pass


_store: Optional[AuditEventStore] = None
_store_lock = threading.Lock()


def _retention_max() -> int:
    raw = (os.environ.get("YASIN_AUDIT_RETENTION_MAX") or "").strip()
    if not raw:
        return DEFAULT_RETENTION_MAX
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_RETENTION_MAX


def create_audit_store_from_env() -> AuditEventStore:
    backend = (os.environ.get("YASIN_AUDIT_BACKEND") or "memory").strip().lower()
    retention = _retention_max()
    if backend == "file":
        directory = (os.environ.get("YASIN_AUDIT_DIR") or "").strip() or "/tmp/yasin-audit"
        return FileAuditStore(directory, retention_max=retention)
    return MemoryAuditStore(retention_max=retention)


def get_audit_store() -> AuditEventStore:
    global _store
    with _store_lock:
        if _store is None:
            _store = create_audit_store_from_env()
        return _store


def set_audit_store(store: Optional[AuditEventStore]) -> None:
    global _store
    with _store_lock:
        _store = store


def reset_audit_store_for_tests(store: Optional[AuditEventStore] = None) -> None:
    global _store
    with _store_lock:
        _store = store if store is not None else MemoryAuditStore()
