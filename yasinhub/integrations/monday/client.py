"""monday GraphQL client abstraction (used by sync in #67).

Credentials never leave this module into board items or normal responses.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from .config import MondayConfig, get_monday_config

logger = logging.getLogger(__name__)

MONDAY_API_URL = "https://api.monday.com/v2"


class MondayClientError(Exception):
    pass


class MondayClient:
    def __init__(self, config: Optional[MondayConfig] = None) -> None:
        self._config = config or get_monday_config()

    @property
    def available(self) -> bool:
        return bool(self._config.api_token)

    def execute(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self._config.api_token:
            raise MondayClientError("monday API token not configured")
        payload = {"query": query}
        if variables:
            payload["variables"] = variables
        data = json.dumps(payload).encode("utf-8")
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
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise MondayClientError(f"monday HTTP {e.code}") from e
        except Exception as e:
            raise MondayClientError(str(e)) from e
        if "errors" in body and body["errors"]:
            raise MondayClientError(str(body["errors"]))
        return body.get("data") or {}

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
