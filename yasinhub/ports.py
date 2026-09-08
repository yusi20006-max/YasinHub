"""
ports.py — Single Source of Truth for the dedicated Yasin HTTP service port contract.

Issue #179: reserved range 7000-7099 with central allocation. This module is the
authoritative source for lifecycle port configuration; no other module may
hardcode a canonical Yasin service port.

Contents:
  - reserved range constants (YASIN_RESERVED_SERVICE_PORT_RANGE)
  - central allocation table (service name -> port)
  - canonical bind hosts and health endpoints
  - low-level verification primitives used by the lifecycle authority
    (YasinHub service_manager): port occupancy, /proc-based port-owner
    discovery, and HTTP health probing.

Security rules (fail closed, never kill unknown owners, never log secrets):
  - every helper here is read-only: nothing here signals, kills, or spawns.
  - diagnostics contain only port numbers, PID numbers and boolean facts.
  - health probing never logs headers, tokens, or bodies.

Only verified HTTP runtimes receive canonical HTTP ports. Worker/CLI services
remain portless and are verified by PID/process identity and liveness.
"""

from __future__ import annotations

import os
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

YASIN_RESERVED_PORT_RANGE_START = 7000
YASIN_RESERVED_PORT_RANGE_END = 7099
YASIN_RESERVED_SERVICE_PORT_RANGE = (
    YASIN_RESERVED_PORT_RANGE_START,
    YASIN_RESERVED_PORT_RANGE_END,
)

# Only verified HTTP runtimes are allocated canonical HTTP ports.
# YasinHub is the PWA/control-plane HTTP service. Yasin-Agent and YasinFeed
# have verified HTTP runtimes. YasinRelay, Yasin-AI, YasinPress and Yasin-Coder
# are portless until an actual HTTP runtime is verified and registered.
YASIN_SERVICE_PORT_ALLOCATION: Dict[str, int] = {
    "yasinhub": 7000,
    "yasin-agent": 7002,
    "yasinfeed": 7004,
}

# Preferred local bind host. Hub itself is the documented 0.0.0.0 exception.
YASIN_SERVICE_HOSTS: Dict[str, str] = {
    name: "127.0.0.1" for name in YASIN_SERVICE_PORT_ALLOCATION
}
YASIN_SERVICE_HOSTS["yasinhub"] = "0.0.0.0"

YASIN_SERVICE_HEALTH_ENDPOINTS: Dict[str, str] = {
    "yasinhub": "/api/health",
    "yasin-agent": "/v1/health",
    "yasinfeed": "/api/health",
}


def is_port_in_reserved_range(port: int) -> bool:
    """True when port lies in the reserved 7000-7099 range."""
    try:
        return YASIN_RESERVED_PORT_RANGE_START <= int(port) <= YASIN_RESERVED_PORT_RANGE_END
    except (TypeError, ValueError):
        return False


def port_for(service_name: str) -> Optional[int]:
    """Canonical allocated port for a service, or None when portless."""
    return YASIN_SERVICE_PORT_ALLOCATION.get(service_name)


def host_for(service_name: str) -> Optional[str]:
    """Canonical bind/check host for an allocated service, else None."""
    if service_name not in YASIN_SERVICE_PORT_ALLOCATION:
        return None
    return YASIN_SERVICE_HOSTS.get(service_name, "127.0.0.1")


def health_endpoint_for(service_name: str) -> Optional[str]:
    """Canonical health endpoint path for an allocated service, else None."""
    return YASIN_SERVICE_HEALTH_ENDPOINTS.get(service_name)


def allocation_snapshot() -> Dict[str, int]:
    """Copy of the central allocation table (prevents caller mutation)."""
    return dict(YASIN_SERVICE_PORT_ALLOCATION)


def is_port_occupied(host: str, port: int, timeout: float = 0.5) -> bool:
    """True when something accepts TCP connections on host:port."""
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except (OSError, ValueError, OverflowError):
        return False
    except Exception:
        return False


def _listening_inodes_for_port(want_port: int) -> Set[str]:
    """Socket inodes in LISTEN state via /proc/net/tcp*."""
    inodes: Set[str] = set()
    found_table = False
    for table in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            text = Path(table).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        found_table = True
        for line in text.splitlines()[1:]:
            parts = line.split()
            if len(parts) < 10 or parts[3] != "0A":
                continue
            local = parts[1]
            if ":" not in local:
                continue
            try:
                if int(local.rsplit(":", 1)[1], 16) != int(want_port):
                    continue
            except (ValueError, OverflowError):
                continue
            inodes.add(parts[9])
    if not found_table:
        raise _ProcUnavailable("/proc/net/tcp unavailable")
    return inodes


class _ProcUnavailable(Exception):
    """Raised when /proc-based owner discovery is not supported here."""


def _pids_holding_inodes(inodes: Set[str]) -> Set[int]:
    """PIDs holding one of the given socket inodes open."""
    pids: Set[int] = set()
    if not inodes:
        return pids
    try:
        entries = list(Path("/proc").iterdir())
    except OSError:
        raise _ProcUnavailable("/proc unavailable")
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            pid = int(entry.name)
        except ValueError:
            continue
        try:
            fds = list((entry / "fd").iterdir())
        except OSError:
            continue
        for fd in fds:
            try:
                target = os.readlink(fd)
            except OSError:
                continue
            if target.startswith("socket:[") and target.endswith("]"):
                if target[8:-1] in inodes:
                    pids.add(pid)
                    break
    return pids


def port_owner_pids(port: int) -> Optional[Set[int]]:
    """PIDs owning a LISTEN socket, or None when indeterminable."""
    try:
        inodes = _listening_inodes_for_port(port)
    except _ProcUnavailable:
        return None
    if not inodes:
        return set()
    try:
        return _pids_holding_inodes(inodes)
    except _ProcUnavailable:
        return None


def owner_discovery_available() -> bool:
    """True when PID-level port-owner discovery works on this platform."""
    try:
        Path("/proc/net/tcp").read_text(encoding="utf-8", errors="replace")
        return True
    except OSError:
        try:
            Path("/proc/net/tcp6").read_text(encoding="utf-8", errors="replace")
            return True
        except OSError:
            return False


@dataclass
class PortOwnership:
    """Read-only verdict about who owns a port. Never contains secrets."""

    port: int
    occupied: bool = False
    owner_pids: List[int] = field(default_factory=list)
    owned_by_pid: Optional[bool] = None
    detail: str = ""


def verify_port_ownership(host: str, port: int, pid: Optional[int]) -> PortOwnership:
    """Check whether pid owns the LISTEN socket on port (fail-closed data)."""
    try:
        port_i = int(port)
    except (TypeError, ValueError):
        return PortOwnership(port=0, detail="invalid port")
    owners = port_owner_pids(port_i)
    if owners is None:
        occupied = is_port_occupied(host, port_i)
        return PortOwnership(
            port=port_i,
            occupied=occupied,
            owner_pids=[],
            owned_by_pid=None,
            detail=f"owner indeterminable; occupied={occupied}",
        )
    occupied = bool(owners) or is_port_occupied(host, port_i)
    if pid is None:
        return PortOwnership(
            port=port_i,
            occupied=occupied,
            owner_pids=sorted(owners),
            owned_by_pid=False,
            detail=f"no pid to match; owners={sorted(owners)}",
        )
    try:
        pid_i = int(pid)
    except (TypeError, ValueError):
        return PortOwnership(port=port_i, occupied=occupied, detail="invalid pid")
    owned = pid_i in owners
    if not owned:
        return PortOwnership(
            port=port_i,
            occupied=occupied,
            owner_pids=sorted(owners),
            owned_by_pid=False,
            detail=f"pid {pid_i} does not own port; owners={sorted(owners)}",
        )
    return PortOwnership(
        port=port_i,
        occupied=True,
        owner_pids=sorted(owners),
        owned_by_pid=True,
        detail=f"pid {pid_i} owns port",
    )


def check_http_health(
    host: str,
    port: int,
    endpoint: str,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 2.0,
) -> bool:
    """Probe http://host:port<endpoint>; True only on HTTP 200."""
    try:
        port_i = int(port)
    except (TypeError, ValueError):
        return False
    if not endpoint or not endpoint.startswith("/"):
        return False
    url = f"http://{host}:{port_i}{endpoint}"
    try:
        request = urllib.request.Request(url, headers=dict(headers or {}))
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return getattr(response, "status", None) == 200
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError):
        return False
    except Exception:
        return False
