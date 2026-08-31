"""Deterministic intent parser for natural-language @Yasin messages (#96).

External text is untrusted. Parsing never grants authority.
"""

from __future__ import annotations

import re
from typing import Optional

from .intents import CONTROL_OPS, Intent, IntentKind

MENTION_RE = re.compile(
    r"^\s*(?:<@[^>]+>|@yasin|@Yasin|@YASIN)\s*[:,-]?\s*",
    re.IGNORECASE,
)
EXEC_RE = re.compile(r"\b(?:execution\s+)?(exec[_-][a-zA-Z0-9._-]+)\b", re.I)
PR_RE = re.compile(r"\b(?:PR|pr|pull request)\s*#?\s*(\d+)\b")
ISSUE_RE = re.compile(r"\b(?:issue)\s*#?\s*(\d+)\b")
MONDAY_RE = re.compile(r"\b(?:monday|item)\s+(?:id\s+)?([a-zA-Z0-9_-]+)\b", re.I)
CONFIRM_RE = re.compile(r"^\s*(?:confirm|yes\s+confirm)\s+([a-zA-Z0-9_-]+)\s*$", re.I)
CANCEL_CTRL_RE = re.compile(r"^\s*(?:cancel\s+control|abort\s+control)\s*$", re.I)

CONTROL_PATTERNS = [
    (re.compile(r"\b(retry|re-?run)\b.*\b(exec|execution)\b", re.I), "retry"),
    (re.compile(r"\b(cancel)\b.*\b(exec|execution)\b", re.I), "cancel"),
    (re.compile(r"\b(pause)\b.*\b(exec|execution)\b", re.I), "pause"),
    (re.compile(r"\b(resume)\b.*\b(exec|execution)\b", re.I), "resume"),
    (re.compile(r"\b(start)\b.*\b(exec|execution)\b", re.I), "start"),
    (re.compile(r"\b(approve)\b", re.I), "approve"),
    (re.compile(r"\b(reject)\b", re.I), "reject"),
    (re.compile(r"\b(merge)\b.*\b(pr|pull)\b", re.I), "approve"),
]


def normalize_message(text: str) -> str:
    if not text:
        return ""
    t = MENTION_RE.sub("", text.strip())
    return t.strip()


def is_yasin_addressed(text: str, *, bot_user_id: Optional[str] = None) -> bool:
    if not text:
        return False
    low = text.lower()
    if "@yasin" in low:
        return True
    if bot_user_id and f"<@{bot_user_id.lower()}>" in low:
        return True
    return False


def _extract_execution_id(text: str) -> Optional[str]:
    m = EXEC_RE.search(text)
    if not m:
        return None
    return m.group(1)


def parse_intent(text: str) -> Intent:
    raw = text or ""
    cleaned = normalize_message(raw)
    if not cleaned:
        return Intent(kind=IntentKind.UNKNOWN, raw_text=raw, confidence=0.0)

    cm = CONFIRM_RE.match(cleaned)
    if cm:
        return Intent(
            kind=IntentKind.CONFIRM_CONTROL,
            raw_text=raw,
            confirmation_token=cm.group(1),
            confidence=0.95,
        )
    if CANCEL_CTRL_RE.match(cleaned):
        return Intent(kind=IntentKind.CANCEL_CONTROL, raw_text=raw, confidence=0.95)

    low = cleaned.lower()
    eid = _extract_execution_id(cleaned)
    pr_m = PR_RE.search(cleaned)
    issue_m = ISSUE_RE.search(cleaned)
    mon_m = MONDAY_RE.search(cleaned)
    pr = int(pr_m.group(1)) if pr_m else None
    issue = int(issue_m.group(1)) if issue_m else None
    monday_id = mon_m.group(1) if mon_m else None

    for pat, op in CONTROL_PATTERNS:
        if pat.search(cleaned) and op in CONTROL_OPS:
            return Intent(
                kind=IntentKind.CONTROL_REQUEST,
                raw_text=raw,
                execution_id=eid,
                github_pr=pr,
                control_operation=op,
                confidence=0.85,
                entities=[x for x in [eid, str(pr) if pr else None] if x],
            )

    failure_words = ("failed", "failure", "failing", "fail", "what went wrong", "root cause")
    failure_follow_up = "why" in low and any(word in low for word in failure_words)
    if any(w in low for w in ("why", "investigate", "root cause", "what went wrong", "failed", "failure", "ci failed")):
        if eid or "execution" in low or "ci" in low or failure_follow_up:
            return Intent(
                kind=IntentKind.INVESTIGATE_FAILURE,
                raw_text=raw,
                execution_id=eid,
                github_pr=pr,
                confidence=0.8,
            )

    if any(w in low for w in ("summarize", "summary", "tl;dr", "tldr")):
        return Intent(
            kind=IntentKind.SUMMARIZE,
            raw_text=raw,
            execution_id=eid,
            github_pr=pr,
            github_issue=issue,
            confidence=0.8,
        )

    if pr is not None or issue is not None or "github" in low or "pull request" in low:
        return Intent(
            kind=IntentKind.READ_GITHUB,
            raw_text=raw,
            github_pr=pr,
            github_issue=issue,
            execution_id=eid,
            confidence=0.75,
        )

    if monday_id or "monday" in low:
        return Intent(
            kind=IntentKind.READ_MONDAY,
            raw_text=raw,
            monday_item_id=monday_id,
            execution_id=eid,
            confidence=0.75,
        )

    if eid or "execution" in low:
        return Intent(
            kind=IntentKind.READ_EXECUTION,
            raw_text=raw,
            execution_id=eid,
            confidence=0.8,
        )

    if any(w in low for w in ("status", "health", "what is happening", "what's happening", "latest")):
        return Intent(
            kind=IntentKind.READ_STATUS,
            raw_text=raw,
            execution_id=eid,
            confidence=0.7,
        )

    return Intent(kind=IntentKind.UNKNOWN, raw_text=raw, confidence=0.2, metadata={"cleaned": cleaned})
