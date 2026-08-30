"""GitHub integration adapter for YasinHub."""

from .webhook import handle_github_webhook
from .adapter import get_github_adapter, GitHubAdapter

__all__ = ["handle_github_webhook", "get_github_adapter", "GitHubAdapter"]
