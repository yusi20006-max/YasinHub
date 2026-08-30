"""
Slack slash command parser and handlers.

Commands enter through the Slack Adapter, are authorized, then invoke
YasinHub Control API / observer surfaces — never Yasin-Agent directly.
"""

from __future__ import annotations

import logging
import shlex
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ...adapters.agent_runtime import get_runtime_adapter
from ...execution.control_api import ControlRequest, get_control_api
from ...observer import get_default_store
from ...report import build_report
from .events import SlackInboundEvent
from .permissions import (
    AuthorizationError,
    IdentityStore,
    YasinIdentity,
    authorize_command,
)

logger = logging.getLogger(__name__)

KNOWN_COMMANDS = (
    "status",
    "health",
    "executions",
    "execution",
    "help",
    "run",
    "cancel",
    "retry",
)


@dataclass
class ParsedCommand:
    name: str
    args: List[str]
    raw_text: str


@dataclass
class CommandResult:
    ok: bool
    text: str
    status: int = 200
    data: Optional[Dict[str, Any]] = None


def parse_command(command: Optional[str], text: Optional[str]) -> Optional[ParsedCommand]:
    name = (command or "").lstrip("/").lower().strip()
    raw = (text or "").strip()
    args: List[str] = []
    if not name and raw:
        try:
            tokens = shlex.split(raw)
        except ValueError:
            tokens = raw.split()
        if not tokens:
            return None
        name = tokens[0].lstrip("/").lower()
        args = tokens[1:]
    elif raw:
        try:
            args = shlex.split(raw)
        except ValueError:
            args = raw.split()
    if not name:
        return None
    return ParsedCommand(name=name, args=args, raw_text=raw)


def _help_text() -> str:
    return (
        "*Yasin Slack commands*\n"
        "• `/status` — ecosystem status\n"
        "• `/health` — hub health\n"
        "• `/executions` — list recent executions\n"
        "• `/execution <id>` — execution details\n"
        "• `/run <task>` — start execution (operator+)\n"
        "• `/cancel <id>` — cancel execution (operator+)\n"
        "• `/retry <id>` — retry failed execution (operator+)\n"
        "• `/help` — this message"
    )


def _format_execution(data: Dict[str, Any]) -> str:
    eid = data.get("execution_id") or "?"
    status = data.get("status") or "?"
    task = data.get("task_id") or ""
    err = data.get("error")
    line = f"`{eid}` — *{status}*"
    if task:
        line += f" task=`{task}`"
    if err:
        line += f"\nerror: {err}"
    return line


class CommandDispatcher:
    def __init__(self, identity_store: Optional[IdentityStore] = None) -> None:
        self._identities = identity_store or IdentityStore()

    def dispatch(self, event: SlackInboundEvent) -> CommandResult:
        parsed = parse_command(event.command, event.text)
        if parsed is None:
            return CommandResult(ok=False, text="Unable to parse command. Try `/help`.")
        if parsed.name not in KNOWN_COMMANDS:
            return CommandResult(ok=False, text=f"Unknown command `/{parsed.name}`. Try `/help`.")
        identity = self._identities.resolve(event.slack_user_id)
        try:
            identity = authorize_command(identity, parsed.name)
        except AuthorizationError as exc:
            if exc.reason == "unmapped_slack_user":
                return CommandResult(ok=False, text="Your Slack user is not mapped to a Yasin identity.")
            if exc.reason == "forbidden":
                return CommandResult(ok=False, text=f"Not authorized for `/{parsed.name}` (role required).")
            return CommandResult(ok=False, text=f"Authorization failed: {exc.reason}")
        handler = getattr(self, f"_cmd_{parsed.name}", None)
        if handler is None:
            return CommandResult(ok=False, text="Command not implemented.")
        try:
            return handler(parsed, identity, event)
        except Exception as exc:
            logger.warning("slack_command_failed cmd=%s error=%s", parsed.name, type(exc).__name__)
            return CommandResult(ok=False, text=f"Command failed: {type(exc).__name__}")

    def _cmd_help(self, parsed: ParsedCommand, identity: YasinIdentity, event: SlackInboundEvent) -> CommandResult:
        return CommandResult(ok=True, text=_help_text())

    def _cmd_status(self, parsed: ParsedCommand, identity: YasinIdentity, event: SlackInboundEvent) -> CommandResult:
        reports = build_report()
        if not reports:
            return CommandResult(ok=True, text="No projects registered.")
        lines = ["*Yasin status*"]
        for r in reports[:20]:
            lines.append(f"• `{r.name}` — {r.health_state}")
        return CommandResult(ok=True, text="\n".join(lines))

    def _cmd_health(self, parsed: ParsedCommand, identity: YasinIdentity, event: SlackInboundEvent) -> CommandResult:
        return CommandResult(ok=True, text="YasinHub health: *ok*")

    def _cmd_executions(self, parsed: ParsedCommand, identity: YasinIdentity, event: SlackInboundEvent) -> CommandResult:
        store = get_default_store()
        items = store.list_executions()
        if not items:
            return CommandResult(ok=True, text="No executions.")
        lines = [f"*Executions* ({len(items)})"]
        for snap in items[:15]:
            d = snap.as_dict() if hasattr(snap, "as_dict") else dict(snap)
            lines.append("• " + _format_execution(d))
        return CommandResult(ok=True, text="\n".join(lines))

    def _cmd_execution(self, parsed: ParsedCommand, identity: YasinIdentity, event: SlackInboundEvent) -> CommandResult:
        if not parsed.args:
            return CommandResult(ok=False, text="Usage: `/execution <id>`")
        eid = parsed.args[0]
        adapter = get_runtime_adapter()
        data = None
        try:
            data = adapter.get_execution(eid)
        except Exception:
            data = None
        if data is None:
            rec = get_default_store().get_execution(eid)
            if rec is None:
                return CommandResult(ok=False, text=f"Unknown execution `{eid}`")
            data = rec.as_dict()
        if not isinstance(data, dict):
            data = {"execution_id": eid, "status": str(data)}
        return CommandResult(ok=True, text=_format_execution(data), data=data)

    def _cmd_run(self, parsed: ParsedCommand, identity: YasinIdentity, event: SlackInboundEvent) -> CommandResult:
        if not parsed.args:
            return CommandResult(ok=False, text="Usage: `/run <task>`")
        task = " ".join(parsed.args)
        store = get_default_store()
        eid = f"exec-{uuid.uuid4().hex[:12]}"
        snap = store.create_execution(
            execution_id=eid,
            task_id=task,
            session_id=f"slack-{event.request_id}",
            metadata={"source": "slack", "actor": identity.yasin_user_id, "slack_user_id": identity.slack_user_id},
        )
        ctrl = get_control_api().handle(
            ControlRequest(
                action="start",
                actor=identity.yasin_user_id,
                source="slack",
                execution_id=eid,
                control_event_id=event.request_id or f"slack-run-{uuid.uuid4().hex[:10]}",
                metadata={"slack_user_id": identity.slack_user_id, "task": task},
            )
        )
        status = "started" if ctrl.success else "queued"
        note = "" if ctrl.success else f" (start deferred: {ctrl.error or 'policy'})"
        return CommandResult(
            ok=True,
            text=f"Execution `{snap.execution_id}` {status} for task `{task}`{note}",
            data=snap.as_dict() if hasattr(snap, "as_dict") else {"execution_id": eid},
        )

    def _cmd_cancel(self, parsed: ParsedCommand, identity: YasinIdentity, event: SlackInboundEvent) -> CommandResult:
        if not parsed.args:
            return CommandResult(ok=False, text="Usage: `/cancel <execution_id>`")
        eid = parsed.args[0]
        resp = get_control_api().handle(
            ControlRequest(
                action="cancel",
                actor=identity.yasin_user_id,
                source="slack",
                execution_id=eid,
                control_event_id=event.request_id or f"slack-cancel-{uuid.uuid4().hex[:10]}",
                metadata={"slack_user_id": identity.slack_user_id},
            )
        )
        if not resp.success:
            return CommandResult(ok=False, text=f"Cancel failed for `{eid}`: {resp.error or 'denied'}")
        return CommandResult(ok=True, text=f"Cancel requested for `{eid}`", data=resp.execution)

    def _cmd_retry(self, parsed: ParsedCommand, identity: YasinIdentity, event: SlackInboundEvent) -> CommandResult:
        if not parsed.args:
            return CommandResult(ok=False, text="Usage: `/retry <execution_id>`")
        eid = parsed.args[0]
        resp = get_control_api().handle(
            ControlRequest(
                action="retry",
                actor=identity.yasin_user_id,
                source="slack",
                execution_id=eid,
                control_event_id=event.request_id or f"slack-retry-{uuid.uuid4().hex[:10]}",
                metadata={"slack_user_id": identity.slack_user_id},
            )
        )
        if not resp.success:
            return CommandResult(ok=False, text=f"Retry failed for `{eid}`: {resp.error or 'denied'}")
        new_id = (resp.execution or {}).get("execution_id") if isinstance(resp.execution, dict) else None
        label = f"`{new_id}`" if new_id else "new execution"
        return CommandResult(ok=True, text=f"Retry queued as {label} (from `{eid}`)", data=resp.execution)
