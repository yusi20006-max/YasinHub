"""YasinHub integration adapters."""

from .agent_runtime import (
    AgentRuntimeAdapter,
    InProcessAgentRuntimeAdapter,
    IntegrationContext,
    bind_agent_runtime,
    get_runtime_adapter,
    project_event_dict,
    project_execution_dict,
    project_fleet_dict,
    resolve_integration_context,
    set_runtime_adapter,
)
from .http_adapter import HttpAgentRuntimeAdapter, build_adapter_from_env
from .http_transport import (
    AuthenticationError,
    ConnectionHealth,
    HttpTransportClient,
    HttpTransportConfig,
    TransportError,
    TransportUnavailable,
)

__all__ = [
    "AgentRuntimeAdapter",
    "InProcessAgentRuntimeAdapter",
    "HttpAgentRuntimeAdapter",
    "IntegrationContext",
    "bind_agent_runtime",
    "get_runtime_adapter",
    "set_runtime_adapter",
    "resolve_integration_context",
    "project_execution_dict",
    "project_event_dict",
    "project_fleet_dict",
    "build_adapter_from_env",
    "HttpTransportClient",
    "HttpTransportConfig",
    "ConnectionHealth",
    "TransportError",
    "AuthenticationError",
    "TransportUnavailable",
]
