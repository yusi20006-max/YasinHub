"""
ports.py — Single Source of Truth for the dedicated Yasin HTTP service port contract.

Issue #179: reserved range 7000-7099 with central allocation. This module is the
authoritative source for lifecycle port configuration; no other module may
hardcode a canonical Yasin service port.

Only services with a verified HTTP runtime receive a canonical HTTP port.
Worker/CLI services remain portless and are verified by PID/process identity
and liveness instead of a synthetic HTTP requirement.
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
    try:
        return YASIN_RESERVED_PORT_RANGE_START <= int(port) <= YASIN_RESERVED_PORT_RANGE_END
    except (TypeError, ValueError):
        return False


def port_for(service_name: str) -> Optional[int]:
    return YASIN_SERVICE_PORT_ALLOCATION.get(service_name)


def host_for(service_name: str) -> Optional[str]:
    if service_name not in YASIN_SERVICE_PORT_ALLOCATION:
        return None
    return YASIN_SERVICE_HOSTS.get(service_name, "127.0.0.1")


def health_endpoint_for(service_name: str) -> Optional[str]:
    return YASIN_SERVICE_HEALTH_ENDPOINTS.get(service_name)


def allocation_snapshot() -> Dict[str, int]:
    return dict(YASIN_SERVICE_PORT_ALLOCATION)


def is_port_occupied(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except (OSError, ValueError, OverflowError):
        return False
    except Exception:
        return False


def _listening_inodes_for_port(want_port: int) -> Set[str]:
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
    pass


def _pids_holding_inodes(inodes: Set[str]) -> Set[int]:
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
            fds = list((entry / "fd").iterdir())
        except (OSError, ValueError):
            continue
        for fd in fds:
            try:
                target = os.readlink(fd)
            except OSError:
                continue
            if target.startswith("socket:[") and target.endswith("]") and target[8:-1] in inodes:
                pids.add(pid)
                break
    return pids


def port_owner_pids(port: int) -> Optional[Set[int]]:
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
    try:
        _listening_inodes_for_port(1)
        return True
    except _ProcUnavailable:
        return False
