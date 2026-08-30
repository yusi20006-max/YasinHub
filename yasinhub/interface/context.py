"""Controlled context gathering for Yasin Interface (#96)."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from ..execution.correlation import get_correlation_store
from ..execution.reconciliation import reconcile
from ..observer.execution_store import get_default_store, redact_secrets
from .intents import Intent, IntentKind
from .session import Session

logger = logging.getLogger(__name__)


def gather_context(
    intent: Intent,
    session: Optional[Session] = None,
    *,
    memory_adapter=None,
) -> Dict[str, Any]:
    ctx: Dict[str, Any] = {"sources": []}
    store = get_default_store()
    corr_store = get_correlation_store()

    eid = intent.execution_id
    if not eid and session and session.execution_ids:
        eid = session.execution_ids[-1]

    if intent.kind in (
        IntentKind.READ_EXECUTION,
        IntentKind.INVESTIGATE_FAILURE,
        IntentKind.READ_STATUS,
        IntentKind.SUMMARIZE,
        IntentKind.CONTROL_REQUEST,
        IntentKind.READ_GITHUB,
        IntentKind.READ_MONDAY,
    ):
        if eid:
            snap = store.get_execution(eid)
            if snap:
                data = redact_secrets(snap.as_dict())
                data.pop("result", None)
                ctx["execution"] = data
                ctx["sources"].append("execution_store")
                ctx["execution_id"] = eid
            corr = corr_store.get_by_execution(eid)
            if corr:
                ctx["correlation"] = redact_secrets(corr.as_dict())
                ctx["sources"].append("correlation")

        if intent.kind == IntentKind.READ_STATUS and not eid:
            items = store.list_executions()
            recent = []
            for s in items[-5:]:
                d = redact_secrets(s.as_dict())
                recent.append(
                    {
                        "execution_id": d.get("execution_id"),
                        "status": d.get("status"),
                        "task_id": d.get("task_id"),
                        "error": d.get("error"),
                    }
                )
            ctx["recent_executions"] = recent
            ctx["sources"].append("execution_list")

    if intent.kind in (IntentKind.INVESTIGATE_FAILURE, IntentKind.READ_STATUS):
        try:
            report = reconcile(dry_run=True, skip_lock=True)
            findings = []
            for f in report.findings:
                if eid and f.execution_id and f.execution_id != eid:
                    continue
                findings.append(f.as_dict())
            ctx["reconciliation"] = findings[:10]
            ctx["sources"].append("reconciliation")
        except Exception:
            logger.debug("context_reconcile_failed", exc_info=True)

    if intent.kind in (IntentKind.READ_GITHUB, IntentKind.SUMMARIZE, IntentKind.INVESTIGATE_FAILURE):
        pr = intent.github_pr
        if pr and eid and "correlation" in ctx:
            ctx["github"] = {
                "pr": pr,
                "repo": (ctx.get("correlation") or {}).get("github_repo"),
                "ci_status": (ctx.get("correlation") or {}).get("ci_status"),
            }
            ctx["sources"].append("github_correlation")
        elif pr:
            ctx["github"] = {"pr": pr, "note": "limited correlation data available"}
            ctx["sources"].append("github_request")

    if intent.kind == IntentKind.READ_MONDAY:
        mid = intent.monday_item_id
        if mid:
            ctx["monday"] = {"item_id": mid}
            ctx["sources"].append("monday_request")
        if "correlation" in ctx:
            c = ctx["correlation"]
            ctx["monday"] = {
                "item_id": c.get("monday_item_id") or mid,
                "board_id": c.get("monday_board_id"),
            }
            ctx["sources"].append("monday_correlation")

    if memory_adapter is not None:
        try:
            mem = memory_adapter.recall(intent=intent, session=session)
            if mem:
                ctx["memory"] = mem
                ctx["sources"].append("yasin_core_memory")
        except Exception:
            logger.debug("memory_recall_failed", exp_info=True)

    return ctx
