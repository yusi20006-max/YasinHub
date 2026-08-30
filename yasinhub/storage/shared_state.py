"""Shared state abstraction for Control Plane production hardening (#93).

Backends:
  - memory: process-local (default for unit tests)
  - file: directory of JSON key files with atomic write + fcntl lock

Configure via:
  YASIN_SHARED_STATE_BACKEND=memory|file
  YASIN_SHARED_STATE_DIR=/path/to/dir
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional, Protocol

logger = logging.getLogger(__name__)


class SharedStateStore(Protocol):
    def get(self, namespace: str, key: str) -> Optional[Any]:
        ...

    def set(self, namespace: str, key: str, value: Any, *, ttl_seconds: Optional[float] = None) -> None:
        ...

    def delete(self, namespace: str, key: str) -> None:
        ...

    def compare_and_set(
        self,
        namespace: str,
        key: str,
        expected: Optional[Any],
        new_value: Any,
        *,
        ttl_seconds: Optional[float] = None,
    ) -> bool:
        ...

    def try_acquire(
        self, namespace: str, key: str, owner: str, *, ttl_seconds: float = 60.0
    ) -> bool:
        ...

    def release(self, namespace: str, key: str, owner: str) -> None:
        ...

    def clear_namespace(self, namespace: str) -> None:
        ...


class MemorySharedState:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._data: Dict[str, Dict[str, Any]] = {}
        self._expiry: Dict[str, Dict[str, float]] = {}

    def _ns(self, namespace: str) -> Dict[str, Any]:
        if namespace not in self._data:
            self._data[namespace] = {}
            self._expiry[namespace] = {}
        return self._data[namespace]

    def _purge(self, namespace: str, key: str) -> None:
        exp = self._expiry.get(namespace, {})
        if key in exp and exp[key] <= time.time():
            self._data.get(namespace, {}).pop(key, None)
            exp.pop(key, None)

    def get(self, namespace: str, key: str) -> Optional[Any]:
        with self._lock:
            self._purge(namespace, key)
            return self._ns(namespace).get(key)

    def set(self, namespace: str, key: str, value: Any, *, ttl_seconds: Optional[float] = None) -> None:
        with self._lock:
            self._ns(namespace)[key] = value
            if ttl_seconds is not None:
                self._expiry.setdefault(namespace, {})[key] = time.time() + float(ttl_seconds)
            else:
                self._expiry.get(namespace, {}).pop(key, None)

    def delete(self, namespace: str, key: str) -> None:
        with self._lock:
            self._ns(namespace).pop(key, None)
            self._expiry.get(namespace, {}).pop(key, None)

    def compare_and_set(
        self,
        namespace: str,
        key: str,
        expected: Optional[Any],
        new_value: Any,
        *,
        ttl_seconds: Optional[float] = None,
    ) -> bool:
        with self._lock:
            self._purge(namespace, key)
            current = self._ns(namespace).get(key)
            if current != expected:
                return False
            self._ns(namespace)[key] = new_value
            if ttl_seconds is not None:
                self._expiry.setdefault(namespace, {})[key] = time.time() + float(ttl_seconds)
            else:
                self._expiry.get(namespace, {}).pop(key, None)
            return True

    def try_acquire(
        self, namespace: str, key: str, owner: str, *, ttl_seconds: float = 60.0
    ) -> bool:
        with self._lock:
            self._purge(namespace, key)
            current = self._ns(namespace).get(key)
            if current is not None and current != owner:
                return False
            self._ns(namespace)[key] = owner
            self._expiry.setdefault(namespace, {})[key] = time.time() + float(ttl_seconds)
            return True

    def release(self, namespace: str, key: str, owner: str) -> None:
        with self._lock:
            if self._ns(namespace).get(key) == owner:
                self._ns(namespace).pop(key, None)
                self._expiry.get(namespace, {}).pop(key, None)

    def clear_namespace(self, namespace: str) -> None:
        with self._lock:
            self._data.pop(namespace, None)
            self._expiry.pop(namespace, None)


class FileSharedState:
    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path(self, namespace: str, key: str) -> Path:
        safe_ns = "".join(c if c.isalnum() or c in "-_" else "_" for c in namespace)[:64]
        safe_key = "".join(c if c.isalnum() or c in "-_." else "_" for c in key)[:200]
        d = self._root / safe_ns
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{safe_key}.json"

    def _read(self, path: Path) -> Optional[Dict[str, Any]]:
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return None
            exp = data.get("expires_at")
            if exp is not None and float(exp) <= time.time():
                try:
                    path.unlink()
                except Exception:
                    pass
                return None
            return data
        except Exception:
            logger.warning("shared_state_read_failed path=%s", path)
            return None

    def _write(self, path: Path, value: Any, ttl_seconds: Optional[float]) -> None:
        payload: Dict[str, Any] = {"value": value, "updated_at": time.time()}
        if ttl_seconds is not None:
            payload["expires_at"] = time.time() + float(ttl_seconds)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, default=str), encoding="utf-8")
        os.replace(tmp, path)

    def _with_file_lock(self, path: Path, fn):
        import fcntl

        path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = path.with_suffix(".lock")
        with open(lock_path, "a+", encoding="utf-8") as lf:
            fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
            try:
                return fn()
            finally:
                fcntl.flock(lf.fileno(), fcntl.LOCK_UN)

    def get(self, namespace: str, key: str) -> Optional[Any]:
        path = self._path(namespace, key)

        def _do():
            data = self._read(path)
            return None if data is None else data.get("value")

        with self._lock:
            return self._with_file_lock(path, _do)

    def set(self, namespace: str, key: str, value: Any, *, ttl_seconds: Optional[float] = None) -> None:
        path = self._path(namespace, key)

        def _do():
            self._write(path, value, ttl_seconds)

        with self._lock:
            self._with_file_lock(path, _do)

    def delete(self, namespace: str, key: str) -> None:
        path = self._path(namespace, key)

        def _do():
            if path.exists():
                path.unlink()

        with self._lock:
            self._with_file_lock(path, _do)

    def compare_and_set(
        self,
        namespace: str,
        key: str,
        expected: Optional[Any],
        new_value: Any,
        *,
        ttl_seconds: Optional[float] = None,
    ) -> bool:
        path = self._path(namespace, key)

        def _do() -> bool:
            data = self._read(path)
            current = None if data is None else data.get("value")
            if current != expected:
                return False
            self._write(path, new_value, ttl_seconds)
            return True

        with self._lock:
            return self._with_file_lock(path, _do)

    def try_acquire(
        self, namespace: str, key: str, owner: str, *, ttl_seconds: float = 60.0
    ) -> bool:
        path = self._path(namespace, key)

        def _do() -> bool:
            data = self._read(path)
            current = None if data is None else data.get("value")
            if current is not None and current != owner:
                return False
            self._write(path, owner, ttl_seconds)
            return True

        with self._lock:
            return self._with_file_lock(path, _do)

    def release(self, namespace: str, key: str, owner: str) -> None:
        path = self._path(namespace, key)

        def _do():
            data = self._read(path)
            if data is not None and data.get("value") == owner and path.exists():
                path.unlink()

        with self._lock:
            self._with_file_lock(path, _do)

    def clear_namespace(self, namespace: str) -> None:
        safe_ns = "".join(c if c.isalnum() or c in "-_" else "_" for c in namespace)[:64]
        d = self._root / safe_ns
        if not d.exists():
            return
        for p in d.glob("*"):
            try:
                p.unlink()
            except Exception:
                pass


_store: Optional[Any] = None
_store_lock = threading.Lock()


def create_shared_state_from_env() -> Any:
    backend = (os.environ.get("YASIN_SHARED_STATE_BACKEND") or "memory").strip().lower()
    if backend == "file":
        root = os.environ.get("YASIN_SHARED_STATE_DIR") or os.environ.get("YASIN_STATE_DIR")
        if not root:
            root = str(Path.cwd() / ".yasin_shared_state")
        return FileSharedState(root)
    return MemorySharedState()


def get_shared_state() -> Any:
    global _store
    with _store_lock:
        if _store is None:
            _store = create_shared_state_from_env()
        return _store


def reset_shared_state_for_tests(store: Optional[Any] = None) -> None:
    global _store
    with _store_lock:
        _store = store if store is not None else MemorySharedState()


NS_CONTROL_EVENTS = "control_events"
NS_SLACK_THREADS = "slack_threads"
NS_RECONCILE_LOCKS = "reconcile_locks"
NS_AUDIT_CURSOR = "audit_cursor"
