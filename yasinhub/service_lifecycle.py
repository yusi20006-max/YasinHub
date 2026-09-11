"""
yasinhub/service_lifecycle.py — Generic self-healing startup/ownership contract.

Issue #182: extend the Issue #180 self-healing startup contract from YasinHub
itself to every service lifecycle-managed by YasinHub.

Final architecture (preserved)::

    PWA -> YasinHub -> Runit -> Service

YasinHub remains the single Control Plane and lifecycle authority. This module
orchestrates the existing primitives (registry / config / ports / pid_store /
service_manager identity / runit ``sv`` adapter); it introduces no second
process manager and never bypasses Runit for Runit-managed services.

Contract::

    Port free
        -> Start through Runit (sv up) or service spawn -> Verify PID/identity/port

    Port occupied -> Identify owner -> Same service?
        |-- YES -> graceful stop via Runit/service lifecycle -> wait death
        |         -> wait port release -> start -> verify new PID/identity/port
        |-- NO  -> FAIL CLOSED -> report -> do not kill

Safety:
  - Ownership is proven by real process identity, never by port number alone.
  - Foreign / unknown / stale / dead / incomplete ownership -> FAIL CLOSED.
  - Normal path never uses blind ``kill -9`` (graceful SIGTERM via the
    existing lifecycle only, then fail closed when the process refuses).
  - Diagnostics carry only service/port/PID numbers and boolean facts.
  - Termux/Android ARM64: stdlib socket + /proc only on the required path;
    ``sv``/lsof/ss are best-effort and never hard requirements.
  - Non-interactive: never prompts, never reads stdin.
"""

from __future__ import annotations

import os
import signal
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Tunables (bounded waits; Termux-safe polling, no wall-clock arithmetic that
# breaks under mocked time — attempt counting like the existing lifecycle).
# ---------------------------------------------------------------------------

STOP_GRACE_SECONDS = 10.0
STOP_POLL_INTERVAL = 0.2
PORT_RELEASE_TIMEOUT = 10.0
PORT_RELEASE_POLL = 0.2


# ---------------------------------------------------------------------------
# Data contracts (no secrets).
# ---------------------------------------------------------------------------

@dataclass
class ServicePreflight:
    """Generic preflight verdict for one managed service. No secrets."""

    service: str = ""
    host: Optional[str] = None
    port: Optional[int] = None
    occupied: bool = False
    owner_pids: List[int] = field(default_factory=list)
    same_pids: List[int] = field(default_factory=list)
    foreign_pids: List[int] = field(default_factory=list)
    unknown_pids: List[int] = field(default_factory=list)
    # free | same | foreign | indeterminate | portless
    decision: str = "indeterminate"
    detail: str = ""


@dataclass
class ServiceStartupResult:
    """Outcome of one generic heal/start orchestration. No secrets."""

    success: bool = False
    # started | restarted | refused
    action: str = "refused"
    pid: Optional[int] = None
    port: Optional[int] = None
    owner_pid: Optional[int] = None
    owner_identity: Optional[bool] = None
    classification: str = "indeterminate"
    detail: str = ""


# ---------------------------------------------------------------------------
# Port / PID / identity discovery (derived from registry + ports + /proc).
# ---------------------------------------------------------------------------

def service_host_port(project) -> Tuple[Optional[str], Optional[int]]:
    """(host, port) for a registry entry. None port means portless worker."""
    host = getattr(project, "host", None)
    port = getattr(project, "port", None)
    if port is None:
        try:
            from .ports import port_for, host_for

            name = getattr(project, "name", "")
            port = port_for(name)
            if host is None:
                host = host_for(name)
        except Exception:
            pass
    if port is None:
        return (host, None)
    try:
        port_i = int(port)
    except (TypeError, ValueError):
        return (host, None)
    if not 1 <= port_i <= 65535:
        return (host, None)
    if not host:
        host = "127.0.0.1"
    return (host, port_i)


def discover_port_owners(port: int) -> Optional[Set[int]]:
    """PIDs owning a LISTEN socket, or None when indeterminable. Never raises."""
    try:
        from .ports import port_owner_pids

        return port_owner_pids(int(port))
    except Exception:
        return None


def is_port_listening(host: str, port: int) -> bool:
    """True when something accepts TCP on host:port. Never raises."""
    try:
        from .ports import is_port_occupied

        return bool(is_port_occupied(host, int(port)))
    except Exception:
        return False


def check_pid_alive(pid: int) -> bool:
    """True when the PID is alive. Never raises (unverifiable -> False).

    Delegates to the lifecycle authority's liveness probe first so test
    doubles installed on ``yasinhub.service_manager`` are honoured; falls
    back to the PID store on real devices.
    """
    try:
        from . import service_manager as _sm

        probe = getattr(_sm, "_is_pid_alive", None)
        if callable(probe):
            return bool(probe(int(pid)))
    except Exception:
        pass
    try:
        from .pid_store import is_pid_alive

        return bool(is_pid_alive(int(pid)))
    except Exception:
        return False


def identify_service_process(pid: int, project) -> Optional[bool]:
    """True=same service, False=foreign, None=unverifiable. Never raises.

    Identity is proven from the real command line via the shared lifecycle
    verifier (pattern and/or start-command argv[0]); never from the port
    number alone. Stale/dead PIDs and missing /proc metadata yield None.
    """
    try:
        pid_i = int(pid)
    except (TypeError, ValueError):
        return None
    if pid_i <= 0:
        return None
    try:
        alive = check_pid_alive(pid_i)
    except Exception:
        return None
    if not alive:
        return None
    try:
        from .service_manager import verify_process_identity

        return verify_process_identity(
            pid_i,
            getattr(project, "process_pattern", None),
            getattr(project, "start_command", None),
        )
    except Exception:
        return None


def _read_cmdline(pid: int) -> Optional[str]:
    """Read /proc/<pid>/cmdline. None when unavailable (Termux-safe)."""
    try:
        data = Path(f"/proc/{int(pid)}/cmdline").read_bytes()
    except OSError:
        return None
    except Exception:
        return None
    try:
        return data.replace(b"\0", b" ").decode("utf-8", errors="replace").strip()
    except Exception:
        return None


def strict_service_identity(pid: int, project) -> Optional[bool]:
    """Classification-grade identity: the discovery pattern must match.

    When the registry entry configures ``process_pattern``, that pattern must
    textually appear in the live command line; a bare interpreter match
    (e.g. any ``python3`` process) is NOT sufficient and reads as foreign.
    Without a configured pattern, falls back to the shared lifecycle
    verifier. Stale/dead PIDs and missing /proc metadata yield None
    (unverifiable -> unsafe). Never raises, never port-based.
    """
    try:
        pid_i = int(pid)
    except (TypeError, ValueError):
        return None
    if pid_i <= 0:
        return None
    try:
        if pid_i == os.getpid():
            return None  # never classify our own process as an owner
    except Exception:
        pass
    try:
        alive = check_pid_alive(pid_i)
    except Exception:
        return None
    if not alive:
        return None
    cmdline = _read_cmdline(pid_i)
    if cmdline is None:
        return None
    pattern = getattr(project, "process_pattern", None)
    if pattern:
        return True if pattern in cmdline else False
    try:
        from .service_manager import verify_process_identity

        return verify_process_identity(
            pid_i, None, getattr(project, "start_command", None)
        )
    except Exception:
        return None


def classify_owner_pid(
    pid: int,
    project,
    identity_fn: Optional[Callable[[int], Optional[bool]]] = None,
) -> str:
    """Classify one port owner: 'same' | 'foreign' | 'unknown'. Never raises.

    Default identity is classification-grade (discovery pattern must match
    when configured); never port-based. Stale/dead/incomplete metadata reads
    as unknown (unsafe, never kill).
    """
    try:
        pid_i = int(pid)
    except (TypeError, ValueError):
        return "unknown"
    if pid_i <= 0:
        return "unknown"
    try:
        if not check_pid_alive(pid_i):
            return "unknown"  # stale/dead -> unsafe, never kill
    except Exception:
        return "unknown"
    try:
        if identity_fn is not None:
            verdict = identity_fn(pid_i)
        else:
            verdict = strict_service_identity(pid_i, project)
    except Exception:
        return "unknown"
    if verdict is True:
        return "same"
    if verdict is False:
        return "foreign"
    return "unknown"  # missing/incomplete/ambiguous metadata -> unsafe


# ---------------------------------------------------------------------------
# Generic preflight: free | same | foreign | indeterminate | portless.
# ---------------------------------------------------------------------------

def discovery_candidates(project) -> List[int]:
    """Read-only PID hints for a service: PID file + pgrep pattern matches.

    Hints only — a kill/start decision always requires verified identity and
    (on hardened platforms) the health anchor first. Never raises.
    """
    name = getattr(project, "name", "") or ""
    found: List[int] = []
    try:
        from .pid_store import read_pid

        saved = read_pid(name)
        if saved is not None and int(saved) not in found:
            found.append(int(saved))
    except Exception:
        pass
    pattern = getattr(project, "process_pattern", None)
    if pattern:
        try:
            from .process_checker import check_process

            status = check_process(pattern)
            if status.running:
                for pid_str in status.pids:
                    try:
                        pid = int(str(pid_str).strip())
                    except ValueError:
                        continue
                    if pid not in found:
                        found.append(pid)
        except Exception:
            pass
    try:
        me = os.getpid()
        found = [p for p in found if p != me and p > 0]
    except Exception:
        pass
    return found


def external_owner_hints(port: int) -> List[int]:
    """Best-effort listener-PID hints via optional OS tools (never required).

    Uses the Hub launcher's optional supplement (lsof/fuser/ss when present).
    Hints only; every kill/start decision still requires verified process
    identity first. Never raises, never prompts.
    """
    try:
        from .startup import optional_external_owners

        hints = optional_external_owners(int(port))
        me = os.getpid()
        return sorted(p for p in set(hints) if p != me and p > 0)
    except Exception:
        return []


def probe_contract_health(project, host: str, port: int) -> bool:
    """True only when the service's contract health endpoint answers HTTP 200.

    Uses the lifecycle authority's auth headers (e.g. Yasin-Agent token) so
    the anchor works for protected services. Never logs secrets, never raises.
    """
    endpoint = getattr(project, "health_endpoint", None)
    if not endpoint:
        try:
            from .ports import health_endpoint_for

            endpoint = health_endpoint_for(getattr(project, "name", "") or "")
        except Exception:
            endpoint = None
    if not endpoint:
        return False
    headers = None
    try:
        from .service_manager import _health_headers_for

        headers = _health_headers_for(project)
    except Exception:
        headers = None
    try:
        from .ports import check_http_health

        return bool(check_http_health(host, int(port), endpoint, headers=headers))
    except Exception:
        return False


def _preflight_correlate_without_owners(
    pre: ServicePreflight, project, host: str, port: int
) -> ServicePreflight:
    """Owner discovery unavailable + port occupied: correlate or fail closed.

    Accepts ``same`` only with a live strict-verified same-service candidate
    AND the succeeding contract health anchor. A foreign candidate, a missing
    health anchor, or no candidates at all -> foreign/indeterminate (never kill).
    """
    name = pre.service
    try:
        candidates = discovery_candidates(project)
    except Exception:
        candidates = []
    # Supplement with optional OS-tool listener hints (lsof/fuser/ss when
    # present; never required). Widens foreign-owner detection on hardened
    # kernels while remaining a hint: identity still decides.
    try:
        for hint in external_owner_hints(port):
            if hint not in candidates:
                candidates.append(hint)
    except Exception:
        pass
    for pid in candidates:
        try:
            kind = classify_owner_pid(pid, project)
        except Exception:
            kind = "unknown"
        if kind == "same" and pid not in pre.same_pids:
            pre.same_pids.append(pid)
        elif kind == "foreign" and pid not in pre.foreign_pids:
            pre.foreign_pids.append(pid)
        elif pid not in pre.unknown_pids and pid not in pre.same_pids:
            pre.unknown_pids.append(pid)
    if pre.foreign_pids:
        pre.decision = "foreign"
        pre.detail = (
            f"port {port} for {name} occupied; owner discovery unavailable, "
            f"candidate(s)={candidates} include foreign process(es)="
            f"{pre.foreign_pids}; fail closed"
        )
        return pre
    if pre.same_pids and not pre.unknown_pids:
        try:
            healthy = probe_contract_health(project, host, port)
        except Exception:
            healthy = False
        if healthy:
            pre.decision = "same"
            pre.detail = (
                f"port {port} for {name} occupied; owner discovery unavailable, "
                f"correlated to verified same-service pid(s)={pre.same_pids} "
                "via live identity + contract health anchor"
            )
            return pre
    pre.decision = "indeterminate"
    pre.detail = (
        f"port {port} for {name} occupied; ownership cannot be reliably "
        f"established on this platform (candidates={candidates}, "
        f"same={pre.same_pids}, unknown={pre.unknown_pids}); fail closed"
    )
    return pre


def preflight_service(
    project,
    owner_fn: Optional[Callable[[int], Optional[Set[int]]]] = None,
    occupied_fn: Optional[Callable[[str, int], bool]] = None,
    identity_fn: Optional[Callable[[int], Optional[bool]]] = None,
) -> ServicePreflight:
    """Decide what owns the service port without touching any process.

    - portless: no port gating (legacy PID+identity lifecycle).
    - free: nothing listens -> start normally.
    - same: every provable owner verifies as the expected service (at least
      one) with no foreign/unknown owners -> graceful stop + restart path.
    - foreign/indeterminate: fail closed, never kill.
    """
    name = getattr(project, "name", "") or ""
    pre = ServicePreflight(service=name)
    host, port = service_host_port(project)
    pre.host, pre.port = host, port
    if port is None:
        pre.decision = "portless"
        pre.detail = f"{name or 'service'} is portless; no port pre-flight"
        return pre
    assert host is not None

    do_owners = owner_fn or discover_port_owners
    try:
        owners = do_owners(int(port))
    except Exception:
        owners = None
    if owners is None:
        owner_list: List[int] = []
    else:
        try:
            owner_list = sorted(set(int(p) for p in owners))
        except Exception:
            owner_list = []
    pre.owner_pids = owner_list

    do_occupied = occupied_fn or is_port_listening
    try:
        occupied = bool(do_occupied(host, int(port)))
    except Exception:
        occupied = bool(owner_list)
    if owner_list:
        occupied = True
    pre.occupied = occupied
    if not occupied:
        pre.decision = "free"
        pre.detail = f"port {port} free"
        return pre

    # Port occupied: classify every provable owner by real identity.
    for pid in owner_list:
        try:
            kind = classify_owner_pid(pid, project, identity_fn=identity_fn)
        except Exception:
            kind = "unknown"
        if kind == "same":
            pre.same_pids.append(pid)
        elif kind == "foreign":
            pre.foreign_pids.append(pid)
        else:
            pre.unknown_pids.append(pid)

    if owners is None and not owner_list:
        # Hardened platform (e.g. Termux kernels without /proc/net/tcp):
        # PID-level owner discovery is unavailable. Correlate via live
        # verified-same candidates (PID file + pgrep hints, read-only) plus
        # the contract health anchor — the same ladder the runtime verifier
        # uses. Without both, fail closed.
        return _preflight_correlate_without_owners(pre, project, host, port)

    if pre.foreign_pids:
        pre.decision = "foreign"
        pre.detail = (
            f"port {port} for {name} occupied; owner pid(s)={pre.owner_pids} "
            f"include foreign process(es)={pre.foreign_pids}; fail closed"
        )
        return pre
    if pre.unknown_pids or not pre.same_pids:
        # Covers: owners present but none verifiably same, stale/dead PIDs,
        # missing /proc metadata, and occupied-port with empty owner set.
        pre.decision = "indeterminate"
        pre.detail = (
            f"port {port} for {name} occupied; ownership cannot be reliably "
            f"established (owners={pre.owner_pids}, same={pre.same_pids}, "
            f"unknown={pre.unknown_pids}); fail closed"
        )
        return pre
    pre.decision = "same"
    pre.detail = (
        f"port {port} for {name} occupied by verified same-service "
        f"pid(s)={pre.same_pids}"
    )
    return pre


# ---------------------------------------------------------------------------
# Safe graceful stop + waits (never blind kill -9 on this path).
# ---------------------------------------------------------------------------

def stop_owned_pid_gracefully(pid: int, timeout: float = STOP_GRACE_SECONDS) -> bool:
    """SIGTERM one verified-owned PID and wait for death. No SIGKILL here.

    Returns True only when the PID is actually gone. A refusal stays a safe
    failure for the caller (never escalate to blind kill -9 on this path).
    """
    try:
        pid_i = int(pid)
    except (TypeError, ValueError):
        return False
    try:
        if pid_i == os.getpid() or pid_i <= 0:
            return False
    except Exception:
        return False
    try:
        alive = check_pid_alive(pid_i)
    except Exception:
        return False
    if not alive:
        return True
    try:
        os.kill(pid_i, signal.SIGTERM)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    except OSError:
        return False
    deadline = max(0.1, float(timeout))
    attempts = max(1, int(deadline / STOP_POLL_INTERVAL))
    for _ in range(attempts):
        try:
            if not check_pid_alive(pid_i):
                return True
        except Exception:
            return False
        time.sleep(STOP_POLL_INTERVAL)
    try:
        return not check_pid_alive(pid_i)
    except Exception:
        return False


def wait_pid_gone(pid: int, timeout: float = STOP_GRACE_SECONDS) -> bool:
    """True only when the PID is actually gone within timeout. Never signals."""
    try:
        pid_i = int(pid)
    except (TypeError, ValueError):
        return False
    deadline = max(0.1, float(timeout))
    attempts = max(1, int(deadline / STOP_POLL_INTERVAL))
    for _ in range(attempts):
        try:
            if not check_pid_alive(pid_i):
                return True
        except Exception:
            return False
        time.sleep(STOP_POLL_INTERVAL)
    try:
        return not check_pid_alive(pid_i)
    except Exception:
        return False


def wait_port_free(
    host: str,
    port: int,
    old_pid: Optional[int] = None,
    timeout: float = PORT_RELEASE_TIMEOUT,
    owner_fn: Optional[Callable[[int], Optional[Set[int]]]] = None,
    occupied_fn: Optional[Callable[[str, int], bool]] = None,
) -> bool:
    """True only when the port no longer listens / old PID no longer owns it."""
    do_owners = owner_fn or discover_port_owners
    do_occupied = occupied_fn or is_port_listening
    deadline = max(0.1, float(timeout))
    attempts = max(1, int(deadline / PORT_RELEASE_POLL))
    for _ in range(attempts):
        try:
            occupied = bool(do_occupied(host, int(port)))
        except Exception:
            occupied = True
        if not occupied:
            return True
        if old_pid is not None:
            try:
                owners = do_owners(int(port))
            except Exception:
                owners = None
            if owners is not None and int(old_pid) not in set(owners):
                if not occupied:
                    return True
            elif owners is not None and not owners:
                return True
        time.sleep(PORT_RELEASE_POLL)
    try:
        if not bool(do_occupied(host, int(port))):
            return True
    except Exception:
        pass
    return False


def stop_service_gracefully(
    project,
    pids: List[int],
    timeout: float = STOP_GRACE_SECONDS,
    sv_down_fn: Optional[Callable[[str], bool]] = None,
    signal_fn: Optional[Callable[[int, float], bool]] = None,
) -> bool:
    """Stop verified-same-service PIDs through Runit/service lifecycle.

    Order: Runit ``sv down`` first when the service is Runit-managed (so the
    supervisor does not resurrect the PID), then graceful SIGTERM of each
    still-live verified-same PID. Returns True only when every PID is gone.
    Never SIGKILLs on this path; a refusal returns False (fail closed).
    """
    name = getattr(project, "name", "") or ""
    targets: List[int] = []
    for pid in pids:
        try:
            targets.append(int(pid))
        except (TypeError, ValueError):
            return False
    if not targets:
        return False

    # Re-verify identity right before signaling: only verified-same PIDs may
    # be signaled by the self-healing lifecycle (classification-grade:
    # discovery pattern must match when configured).
    for pid in list(targets):
        try:
            if strict_service_identity(pid, project) is not True:
                return False
        except Exception:
            return False

    # Runit path first (preserves YasinHub -> Runit -> service).
    try:
        from . import runit as _runit

        managed = _runit.is_runit_managed(name)
    except Exception:
        managed = False
    if managed:
        try:
            if sv_down_fn is not None:
                down_ok = bool(sv_down_fn(name))
            else:
                from .runit import sv_down as _sv_down

                down_ok = bool(_sv_down(name).ok)
        except Exception:
            down_ok = False
        # sv down failing is not fatal by itself: fall through to graceful
        # SIGTERM of the verified PIDs, then require actual death below.
        _ = down_ok

    do_signal = signal_fn or stop_owned_pid_gracefully
    for pid in targets:
        try:
            if not check_pid_alive(pid):
                continue
            if not bool(do_signal(int(pid), float(timeout))):
                return False
        except Exception:
            return False
    for pid in targets:
        try:
            if check_pid_alive(int(pid)):
                return False
        except Exception:
            return False
    return True


# ---------------------------------------------------------------------------
# Post-start verification (real PID + identity + port).
# ---------------------------------------------------------------------------

def verify_service_started(project, pid: int) -> ServiceStartupResult:
    """Accept RUNNING only with PID alive + identity + listening/port + health.

    Reuses the lifecycle authority verdict (service_manager
    ``verify_runtime_running``) for HTTP-contract services so Hub, API, PWA
    and CLI observe the same truth. Portless services require alive plus
    non-foreign identity. Anything else fails closed.
    """
    name = getattr(project, "name", "") or ""
    out = ServiceStartupResult(action="refused", classification="indeterminate")
    out.port = getattr(project, "port", None)
    try:
        _host, port = service_host_port(project)
        if port is not None:
            out.port = port
    except Exception:
        pass
    try:
        pid_i = int(pid)
    except (TypeError, ValueError):
        out.detail = f"invalid pid for {name}; fail closed"
        return out
    out.pid = pid_i
    try:
        alive = check_pid_alive(pid_i)
    except Exception:
        alive = False
    if not alive:
        out.detail = f"pid {pid_i} for {name} not alive; fail closed"
        return out
    # Classification-grade identity: the discovery pattern must match when
    # configured, so a foreign process on the same box can never inherit a
    # passing verdict through a bare interpreter-name match.
    try:
        identity = strict_service_identity(pid_i, project)
    except Exception:
        identity = None
    out.owner_identity = identity
    if identity is not True:
        out.detail = (
            f"pid {pid_i} for {name} identity unverified ({identity}); fail closed"
        )
        return out
    try:
        from .service_manager import verify_runtime_running

        verdict = verify_runtime_running(project, pid_i)
    except Exception:
        verdict = None
    if verdict is None:
        out.detail = f"runtime verification unavailable for {name}; fail closed"
        return out
    if bool(getattr(verdict, "running", False)):
        out.success = True
        out.action = "started"
        out.classification = "same"
        reasons = "; ".join(getattr(verdict, "reasons", []) or ["verified"])
        out.detail = f"{name} running: pid={pid_i} port={out.port}; {reasons}"
        return out
    reasons = "; ".join(getattr(verdict, "reasons", []) or ["verification failed"])
    out.detail = f"pid {pid_i} for {name} failed verification: {reasons}"
    return out


# ---------------------------------------------------------------------------
# Failure reporting through the Hub status/report contract (PWA-visible).
# ---------------------------------------------------------------------------

def report_startup_refusal(
    project,
    preflight: Optional[ServicePreflight],
    reason: str,
    status_dir=None,
) -> str:
    """Persist a START-refused status so API/PWA show the real failure.

    Returns the persisted detail string (service + port + PID + identity +
    classification + reason; never secrets).
    """
    name = getattr(project, "name", "") or "service"
    port = getattr(project, "port", None)
    if preflight is not None and preflight.port is not None:
        port = preflight.port
    owners = list(preflight.owner_pids) if preflight else []
    classification = (preflight.decision if preflight else "indeterminate") or "indeterminate"
    detail = (
        f"start refused for {name}: port={port} owners={owners} "
        f"same={getattr(preflight, 'same_pids', [])} "
        f"foreign={getattr(preflight, 'foreign_pids', [])} "
        f"unknown={getattr(preflight, 'unknown_pids', [])} "
        f"classification={classification}; {reason}"
    )
    try:
        from .status_store import write_status

        if status_dir is None:
            try:
                from .config_manager import get_status_dir

                status_dir = get_status_dir()
            except Exception:
                status_dir = None
        if status_dir is not None:
            write_status(name, success=False, message=f"خطا: {detail}", status_dir=status_dir)
        else:
            from .status_store import write_status as _ws

            _ws(name, success=False, message=f"خطا: {detail}")
    except Exception:
        pass
    return detail


def refusal_result(
    project,
    preflight: Optional[ServicePreflight],
    reason: str,
    status_dir=None,
) -> ServiceStartupResult:
    """Build + persist a fail-closed refusal result. Never kills anything."""
    detail = report_startup_refusal(project, preflight, reason, status_dir=status_dir)
    out = ServiceStartupResult(success=False, action="refused")
    try:
        _host, port = service_host_port(project)
        out.port = port
    except Exception:
        out.port = None
    if preflight is not None:
        out.owner_pid = preflight.owner_pids[0] if len(preflight.owner_pids) == 1 else None
        out.classification = preflight.decision
    out.detail = detail
    return out
