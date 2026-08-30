"""Channel-neutral session store backed by SharedState (#96 / #93)."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..storage.shared_state import get_shared_state

NS_SESSIONS = "yasin_sessions"
NS_SESSION_BY_THREAD = "yasin_session_by_thread"
NS_PENDING_CONTROL = "yasin_pending_control"


@dataclass
class Session:
    session_id: str
    channel: str
    source: str
    thread_id: Optional[str] = None
    channel_id: Optional[str] = None
    yasin_user_id: Optional[str] = None
    slack_user_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    recent_turns: List[Dict[str, str]] = field(default_factory=list)
    execution_ids: List[str] = field(default_factory=list)
    github_prs: List[int] = field(default_factory=list)
    github_issues: List[int] = field(default_factory=list)
    monday_item_ids: List[str] = field(default_factory=list)
    memory_refs: List[str] = field(default_factory=list)
    pending_confirmation: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "channel": self.channel,
            "source": self.source,
            "thread_id": self.thread_id,
            "channel_id": self.channel_id,
            "yasin_user_id": self.yasin_user_id,
            "slack_user_id": self.slack_user_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "recent_turns": list(self.recent_turns[-20:]),
            "execution_ids": list(self.execution_ids[-20:]),
            "github_prs": list(self.github_prs[-10:]),
            "github_issues": list(self.github_issues[-10:]),
            "monday_item_ids": list(self.monday_item_ids[-10:]),
            "memory_refs": list(self.memory_refs[-10:]),
            "pending_confirmation": self.pending_confirmation,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Session":
        return cls(
            session_id=str(data.get("session_id") or ""),
            channel=str(data.get("channel") or "unknown"),
            source=str(data.get("source") or "unknown"),
            thread_id=data.get("thread_id"),
            channel_id=data.get("channel_id"),
            yasin_user_id=data.get("yasin_user_id"),
            slack_user_id=data.get("slack_user_id"),
            created_at=float(data.get("created_at") or time.time()),
            updated_at=float(data.get("updated_at") or time.time()),
            recent_turns=list(data.get("recent_turns") or []),
            execution_ids=list(data.get("execution_ids") or []),
            github_prs=[int(x) for x in (data.get("github_prs") or [])],
            github_issues=[int(x) for x in (data.get("github_issues") or [])],
            monday_item_ids=list(data.get("monday_item_ids") or []),
            memory_refs=list(data.get("memory_refs") or []),
            pending_confirmation=data.get("pending_confirmation"),
            metadata=dict(data.get("metadata") or {}),
        )

    def add_turn(self, role: str, text: str) -> None:
        self.recent_turns.append({"role": role, "text": text[:2000]})
        self.recent_turns = self.recent_turns[-20:]
        self.updated_at = time.time()

    def remember_execution(self, execution_id: str) -> None:
        if execution_id and execution_id not in self.execution_ids:
            self.execution_ids.append(execution_id)
            self.execution_ids = self.execution_ids[-20:]
            self.updated_at = time.time()


class SessionStore:
    TTL = 7 * 24 * 3600

    def __init__(self, store=None) -> None:
        self._store = store

    @property
    def store(self):
        if self._store is None:
            self._store = get_shared_state()
        return self._store

    def create(
        self,
        *,
        channel: str,
        source: str,
        thread_id: Optional[str] = None,
        channel_id: Optional[str] = None,
        yasin_user_id: Optional[str] = None,
        slack_user_id: Optional[str] = None,
    ) -> Session:
        sid = f"sess-{uuid.uuid4().hex[:12]}"
        session = Session(
            session_id=sid,
            channel=channel,
            source=source,
            thread_id=thread_id,
            channel_id=channel_id,
            yasin_user_id=yasin_user_id,
            slack_user_id=slack_user_id,
        )
        self.save(session)
        if thread_id:
            self.store.set(
                NS_SESSION_BY_THREAD,
                f"{channel}:{thread_id}",
                sid,
                ttl_seconds=self.TTL,
            )
        return session

    def save(self, session: Session) -> None:
        session.updated_at = time.time()
        self.store.set(NS_SESSIONS, session.session_id, session.as_dict(), ttl_seconds=self.TTL)

    def get(self, session_id: str) -> Optional[Session]:
        data = self.store.get(NS_SESSIONS, session_id)
        if not isinstance(data, dict):
            return None
        return Session.from_dict(data)

    def get_by_thread(self, channel: str, thread_id: str) -> Optional[Session]:
        sid = self.store.get(NS_SESSION_BY_THREAD, f"{channel}:{thread_id}")
        if not sid:
            return None
        return self.get(str(sid))

    def get_or_create_for_thread(
        self,
        *,
        channel: str,
        source: str,
        thread_id: Optional[str],
        channel_id: Optional[str] = None,
        yasin_user_id: Optional[str] = None,
        slack_user_id: Optional[str] = None,
    ) -> Session:
        if thread_id:
            existing = self.get_by_thread(channel, thread_id)
            if existing:
                if yasin_user_id and not existing.yasin_user_id:
                    existing.yasin_user_id = yasin_user_id
                if slack_user_id and not existing.slack_user_id:
                    existing.slack_user_id = slack_user_id
                self.save(existing)
                return existing
        return self.create(
            channel=channel,
            source=source,
            thread_id=thread_id,
            channel_id=channel_id,
            yasin_user_id=yasin_user_id,
            slack_user_id=slack_user_id,
        )

    def save_pending_control(self, token: str, payload: Dict[str, Any]) -> None:
        self.store.set(NS_PENDING_CONTROL, token, payload, ttl_seconds=3600)

    def get_pending_control(self, token: str) -> Optional[Dict[str, Any]]:
        data = self.store.get(NS_PENDING_CONTROL, token)
        return data if isinstance(data, dict) else None

    def clear_pending_control(self, token: str) -> None:
        self.store.delete(NS_PENDING_CONTROL, token)


_session_store: Optional[SessionStore] = None


def get_session_store() -> SessionStore:
    global _session_store
    if _session_store is None:
        _session_store = SessionStore()
    return _session_store


def reset_session_store_for_tests(store=None) -> None:
    global _session_store
    _session_store = SessionStore(store=store) if store is not None else SessionStore()
