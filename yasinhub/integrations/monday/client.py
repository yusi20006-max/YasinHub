"""monday GraphQL client abstraction.

Credentials never leave this module into board items or normal responses.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from .config import MondayConfig, get_monday_config

logger = logging.getLogger(__name__)

MONDAY_API_URL = "https://api.monday.com/v2"


class MondayClientError(Exception):
    """Safe error — never includes token or full request body."""

    def __init__(self, message: str, *, status_code: Optional[int] = None, retriable: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.retriable = retriable


def _safe_error_message(exc: BaseException) -> str:
    msg = str(exc)
    for needle in ("Bearer ", "token", "Authorization"):
        if needle.lower() in msg.lower():
            return "monday request failed (details redacted)"
    return msg[:200]


class MondayClient:
    def __init__(self, config: Optional[MondayConfig] = None) -> None:
        self._config = config or get_monday_config()

    @property
    def available(self) -> bool:
        return bool(self._config.api_token)

    @property
    def live_ready(self) -> bool:
        return self._config.is_live_ready()

    def execute(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self._config.api_token:
            raise MondayClientError("monday API token not configured", retriable=False)

        payload = {"query": query}
        if variables:
            payload["variables"] = variables
        data = json.dumps(payload).encode("utf-8")

        attempts = max(1, self._config.max_retries + 1)
        last_err: Optional[MondayClientError] = None

        for attempt in range(attempts):
            try:
                req = urllib.request.Request(
                    MONDAY_API_URL,
                    data=data,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": self._config.api_token,
                        "API-Version": "2024-10",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=self._config.request_timeout_seconds) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                retriable = e.code in (429, 500, 502, 503, 504)
                last_err = MondayClientError(
                    f"monday HTTP {e.code}",
                    status_code=e.code,
                    retriable=retriable,
                )
                if retriable and attempt < attempts - 1:
                    time.sleep(self._config.retry_backoff_seconds * (attempt + 1))
                    continue
                raise last_err from e
            except Exception as e:
                last_err = MondayClientError(_safe_error_message(e), retriable=True)
                if attempt < attempts - 1:
                    time.sleep(self._config.retry_backoff_seconds * (attempt + 1))
                    continue
                raise last_err from e

            if "errors" in body and body["errors"]:
                # GraphQL errors are usually not retriable (validation etc.)
                raise MondayClientError("monday GraphQL error", retriable=False)
            return body.get("data") or {}

        raise last_err or MondayClientError("monday request failed")

    def get_item(self, item_id: str) -> Optional[Dict[str, Any]]:
        q = """
        query ($ids: [ID!]) {
          items (ids: $ids) {
            id
            name
            board { id }
            column_values { id text value }
          }
        }
        """
        data = self.execute(q, {"ids": [str(item_id)]})
        items = data.get("items") or []
        return items[0] if items else None

    def change_column_value(
        self,
        board_id: str,
        item_id: str,
        column_id: str,
        value: Any,
    ) -> Dict[str, Any]:
        q = """
        mutation ($boardId: ID!, $itemId: ID!, $columnId: String!, $value: JSON!) {
          change_column_value(
            board_id: $boardId,
            item_id: $itemId,
            column_id: $columnId,
            value: $value
          ) { id }
        }
        """
        val = value if isinstance(value, str) else json.dumps(value)
        return self.execute(
            q,
            {
                "boardId": str(board_id),
                "itemId": str(item_id),
                "columnId": column_id,
                "value": val,
            },
        )

    def health_check(self) -> Dict[str, Any]:
        """Lightweight connectivity probe. Never returns secrets."""
        if not self.available:
            return {"ok": False, "mode": "dry-run", "reason": "no credentials"}
        try:
            # minimal query
            self.execute("{ me { id } }")
            return {"ok": True, "mode": "live" if self.live_ready else "read-only"}
        except MondayClientError as e:
            return {
                "ok": False,
                "mode": "error",
                "reason": str(e),
                "retriable": e.retriable,
            }
