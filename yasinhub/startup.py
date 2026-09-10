"""
yasinhub/startup.py — Official single-command self-healing YasinHub startup.

Issue #180: make YasinHub startup a single-command, non-interactive operation
on the dedicated Control Plane port 7000:

    preflight -> identify -> safely restart if YasinHub -> start -> verify

Contract:
  - YasinHub owns dedicated HTTP port 7000 (canonical allocation).
  - Preflight runs automatically before bind.
  - Port free -> start normally.
  - Port occupied by verified YasinHub -> graceful SIGTERM stop (never blind
    kill -9 on the normal path), wait for death, verify port release, start
    new Hub, verify new PID + identity + listening + health.
  - Port occupied by another/unknown process, or ownership indeterminable
    without a verified Hub anchor -> FAIL CLOSED. Never kill it.
  - Stale/dead PIDs, missing /proc metadata, refusal to stop, or lingering
    port occupancy all fail safely rather than guessing.

Authority: YasinHub remains the sole Control Plane and lifecycle/PID
authority. This module orchestrates the existing primitives in
yasinhub.ports / yasinhub.pid_store / yasinhub.service_manager; it does not
introduce a second control plane, a second lifecycle manager, or direct PWA
lifecycle control.

Termux/Android ARM64: stdlib socket + /proc only on the required path.
lsof/fuser/ss are optional best-effort supplements, never hard requirements.

Secrets: diagnostics carry only port/PID numbers and boolean facts. Health
probes never log headers/tokens/bodies. Command lines are truncated and
redacted before display.

Official launcher::

    python -m yasinhub.startup
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set

from .pid_store import is_pid_alive, read_pid, remove_pid, save_pid
from .ports import (
    check_http_health,
    is_port_occupied,
    port_for,
    port_owner_pids,
)

try:
    from .service_manager import verify_process_identity as _verify_identity
except Exception:  # pragma: no cover - import-time safety

    def _verify_identity(pid: int, pattern: Optional[str], start_command: Optional[str] = None):  # type: ignore[misc]
        return None


HUB_SERVICE_NAME = "yasinhub"
HUB_PID_NAME = "yasinhub"
HUB_CHECK_HOST = "127.0.0.1"
HUB_HEALTH_ENDPOINT = "/api/health"

# Canonical Hub server identity. The launcher itself runs as
# `yasinhub.startup` and must NOT match these markers.
HUB_SERVER_MARKERS = (
    "yasinhub.api.server",
    "yasinhub/api/server",
)

# Discovery pattern used for pgrep fallback (read-only, never a kill basis).
HUB_PGREP_PATTERN = "yasinhub.api.server"

STOP_GRACE_SECONDS = 10.0
STOP_POLL_INTERVAL = 0.2
PORT_RELEASE_TIMEOUT = 10.0
PORT_RELEASE_POLL = 0.2
VERIFY_TIMEOUT = 20.0
VERIFY_POLL = 0.5

_SECRET_REDACT = re.compile(
    r"(?i)(token|secret|password|passwd|api[_-]?key|bearer|authorization)(\s*[:=]\s*)\S+"
)


def resolve_hub_port() -> int:
    """Canonical Hub port: allocation table wins, YASINHUB_PORT may override."""
    try:
        raw = (os.environ.get("YASINHUB_PORT", "") or "").strip()
        if raw:
            port = int(raw)
            if 1 <= port <= 65535:
                return port
    except (TypeError, ValueError):
        pass
    try:
        allocated = port_for(HUB_SERVICE_NAME)
        if allocated:
            return int(allocated)
    except (TypeError, ValueError):
        pass
    return 7000


def sanitize_cmdline(cmdline: Optional[str], limit: int = 300) -> str:
    """Truncate + redact a cmdline for safe diagnostics (never secrets)."""
    if not cmdline:
        return ""
    cleaned = _SECRET_REDACT.sub(r"\1\2***", cmdline)
    cleaned = " ".join(cleaned.split())
    if len(cleaned) > limit:
        cleaned = cleaned[:limit] + "…"
    return cleaned


def read_process_cmdline(pid: int) -> Optional[str]:
    """Read /proc/<pid>/cmdline. None when unavailable (Termux-safe)."""
    try:
        data = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return None
    except Exception:
        return None
    try:
        return data.replace(b"\0", b" ").decode("utf-8", errors="replace").strip()
    except Exception:
        return None


def is_yasinhub_process(pid: int) -> Optional[bool]:
    """True when PID is verifiably the Hub server, False when foreign.

    Returns None when unverifiable (dead PID, no /proc, no hints). Never
    raises. Identity is marker-based, never "it occupies 7000".
    """
    try:
        pid_i = int(pid)
    except (TypeError, ValueError):
        return None
    if pid_i <= 0:
        return None
    try:
        alive = is_pid_alive(pid_i)
    except Exception:
        return None
    if not alive:
        return None
    cmdline = read_process_cmdline(pid_i)
    if cmdline is None:
        # Fall back to the shared verifier (same /proc source, same answer),
        # kept for consistency with the service lifecycle authority.
        try:
            verdict = _verify_identity(pid_i, HUB_PGREP_PATTERN, None)
        except Exception:
            return None
        return verdict
    for marker in HUB_SERVER_MARKERS:
        if marker in cmdline:
            return True
    return False


def hub_pid_candidates() -> List[int]:
    """PIDs that might be the Hub: PID file + pgrep (read-only hints)."""
    candidates: List[int] = []
    try:
        saved = read_pid(HUB_PID_NAME)
    except Exception:
        saved = None
    if saved:
        try:
            candidates.append(int(saved))
        except (TypeError, ValueError):
            pass
    try:
        proc = subprocess.run(
            ["pgrep", "-f", HUB_PGREP_PATTERN],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return candidates
    except Exception:
        return candidates
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if not line.isdigit():
            continue
        try:
            pid = int(line)
        except ValueError:
            continue
        if pid == os.getpid():
            continue
        if pid not in candidates:
            candidates.append(pid)
    return candidates


def optional_external_owners(port: int) -> Set[int]:
    """Best-effort PID hints via lsof/ss/fuser when present. Never required.

    Returns an (possibly empty) set. Never raises. These are hints only; a
    kill decision always requires verified process identity first.
    """
    found: Set[int] = set()
    try:
        port_i = int(port)
    except (TypeError, ValueError):
        return found
    # lsof -ti :PORT prints owning PIDs, one per line.
    if shutil.which("lsof"):
        try:
            proc = subprocess.run(
                ["lsof", "-ti", f":{port_i}"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            for line in (proc.stdout or "").splitlines():
                line = line.strip()
                if line.isdigit() and int(line) != os.getpid():
                    found.add(int(line))
        except Exception:
            pass
    # ss -ltnp exposes pid=... for listeners (when permitted).
    if shutil.which("ss"):
        try:
            proc = subprocess.run(
                ["ss", "-ltnp"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            for match in re.finditer(r"pid=(\d+)", proc.stdout or ""):
                try:
                    pid = int(match.group(1))
                except ValueError:
                    continue
                if pid != os.getpid():
                    found.add(pid)
        except Exception:
            pass
    # fuser PORT/tcp prints PIDs on stdout/stderr.
    if shutil.which("fuser"):
        try:
            proc = subprocess.run(
                ["fuser", f"{port_i}/tcp"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            for chunk in ((proc.stdout or "") + " " + (proc.stderr or "")).split():
                chunk = chunk.strip().strip(",")
                if chunk.isdigit() and int(chunk) != os.getpid():
                    found.add(int(chunk))
        except Exception:
            pass
    return found


@dataclass
class PreflightResult:
    """Automatic preflight verdict for port 7000. No secrets."""

    port: int
    occupied: bool = False
    proc_owner_pids: List[int] = field(default_factory=list)
    owner_discovery: Optional[bool] = None  # True/False, None=indeterminable
    hub_pids: List[int] = field(default_factory=list)
    foreign_pids: List[int] = field(default_factory=list)
    unknown_pids: List[int] = field(default_factory=list)
    decision: str = "free"  # free | yasinhub | foreign | indeterminate
    detail: str = ""


def preflight_hub_port(
    host: Optional[str] = None,
    port: Optional[int] = None,
    health_check: Optional[Callable[[str, int, str], bool]] = None,
) -> PreflightResult:
    """Decide what owns the Hub port without touching any process.

    - free: nothing listens -> start normally.
    - yasinhub: every provable owner verifies as the Hub server (or, where
      owner discovery is unavailable on hardened Termux, a live verified Hub
      PID plus a succeeding Hub health anchor correlates the occupant).
    - foreign/indeterminate: fail closed, never kill.
    """
    check_host = host or HUB_CHECK_HOST
    check_port = int(port) if port is not None else resolve_hub_port()
    result = PreflightResult(port=check_port)
    try:
        owners = port_owner_pids(check_port)
    except Exception:
        owners = None
    if owners is None:
        result.owner_discovery = None
        result.proc_owner_pids = []
    else:
        result.owner_discovery = True
        result.proc_owner_pids = sorted(owners)
    try:
        occupied = is_port_occupied(check_host, check_port)
    except Exception:
        occupied = bool(result.proc_owner_pids)
    if owners is not None and owners:
        occupied = True
    result.occupied = bool(occupied)
    if not result.occupied:
        result.decision = "free"
        result.detail = f"port {check_port} free"
        return result

    # Port is occupied: classify every provable owner by real identity.
    to_classify: Set[int] = set(result.proc_owner_pids)
    if owners is None:
        # Supplement with PID-file/pgrep hints + optional tool hints, but
        # these alone never prove port ownership (see health anchor below).
        for pid in hub_pid_candidates():
            to_classify.add(pid)
        for pid in optional_external_owners(check_port):
            to_classify.add(pid)
    for pid in sorted(to_classify):
        if pid == os.getpid():
            continue
        try:
            verdict = is_yasinhub_process(pid)
        except Exception:
            verdict = None
        if verdict is True:
            result.hub_pids.append(pid)
        elif verdict is False:
            result.foreign_pids.append(pid)
        else:
            result.unknown_pids.append(pid)

    if owners is not None:
        if result.proc_owner_pids and not result.foreign_pids and not result.unknown_pids and result.hub_pids:
            result.decision = "yasinhub"
            result.detail = (
                f"port {check_port} occupied by verified YasinHub "
                f"pid(s)={result.hub_pids}"
            )
            return result
        if result.foreign_pids:
            result.decision = "foreign"
            result.detail = (
                f"port {check_port} occupied; owner pid(s)={result.proc_owner_pids} "
                f"include non-Hub process(es)={result.foreign_pids}; fail closed"
            )
            return result
        result.decision = "indeterminate"
        result.detail = (
            f"port {check_port} occupied; ownership cannot be reliably "
            f"established (owners={result.proc_owner_pids}, "
            f"hub={result.hub_pids}, unknown={result.unknown_pids}); fail closed"
        )
        return result

    # Hardened platform: owner discovery unavailable. Correlate via a live
    # verified Hub PID plus the Hub health anchor (same ladder as the
    # service lifecycle authority). Without both, fail closed.
    if result.hub_pids and not result.foreign_pids:
        probe = health_check or (lambda h, p, e: check_http_health(h, p, e))
        try:
            healthy = bool(probe(check_host, check_port, HUB_HEALTH_ENDPOINT))
        except Exception:
            healthy = False
        if healthy:
            result.decision = "yasinhub"
            result.detail = (
                f"port {check_port} occupied; owner discovery unavailable, "
                f"correlated to verified YasinHub pid(s)={result.hub_pids} "
                "via live identity + Hub health anchor"
            )
            return result
    if result.foreign_pids:
        result.decision = "foreign"
    else:
        result.decision = "indeterminate"
    result.detail = (
        f"port {check_port} occupied; owner indeterminable on this platform "
        f"(hub={result.hub_pids}, foreign={result.foreign_pids}, "
        f"unknown={result.unknown_pids}); fail closed"
    )
    return result


def stop_hub_gracefully(pid: int, timeout: float = STOP_GRACE_SECONDS) -> bool:
    """SIGTERM the old Hub and wait for death. No SIGKILL on this path.

    Returns True only when the PID is actually gone. A refusal stays a safe
    failure for the caller (never escalate to blind kill -9 here).
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
        alive = is_pid_alive(pid_i)
    except Exception:
        return False
    if not alive:
        return True
    # Re-verify identity right before signaling: only a verified Hub PID may
    # be signaled by the startup launcher.
    try:
        if is_yasinhub_process(pid_i) is not True:
            return False
    except Exception:
        return False
    try:
        os.kill(pid_i, signal.SIGTERM)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    except OSError:
        return False
    deadline = max(0.1, float(timeout))
    interval = STOP_POLL_INTERVAL
    attempts = max(1, int(deadline / interval))
    for _ in range(attempts):
        try:
            if not is_pid_alive(pid_i):
                return True
        except Exception:
            return False
        time.sleep(interval)
    try:
        return not is_pid_alive(pid_i)
    except Exception:
        return False


def wait_port_released(
    host: Optional[str] = None,
    port: Optional[int] = None,
    old_pid: Optional[int] = None,
    timeout: float = PORT_RELEASE_TIMEOUT,
) -> bool:
    """True only when the port no longer listens / old PID no longer owns it."""
    check_host = host or HUB_CHECK_HOST
    check_port = int(port) if port is not None else resolve_hub_port()
    deadline = max(0.1, float(timeout))
    attempts = max(1, int(deadline / PORT_RELEASE_POLL))
    for _ in range(attempts):
        try:
            occupied = is_port_occupied(check_host, check_port)
        except Exception:
            occupied = True
        if not occupied:
            return True
        if old_pid is not None:
            try:
                owners = port_owner_pids(check_port)
            except Exception:
                owners = None
            if owners is not None and int(old_pid) not in set(owners):
                if not occupied:
                    return True
            elif owners is not None and not owners:
                return True
        time.sleep(PORT_RELEASE_POLL)
    try:
        if not is_port_occupied(check_host, check_port):
            return True
    except Exception:
        pass
    return False


def _hub_repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _hub_logs_dir() -> Path:
    try:
        from .config_manager import get_logs_dir

        return get_logs_dir()
    except Exception:
        return Path.home() / ".yasinhub" / "logs"


def start_hub_process(
    host: Optional[str] = None,  # kept for API symmetry; server binds itself
    port: Optional[int] = None,
    logs_dir: Optional[Path] = None,
    popen_factory: Optional[Callable[..., subprocess.Popen]] = None,
) -> subprocess.Popen:
    """Spawn the Hub server (`python -m yasinhub.api.server`). Non-interactive."""
    check_port = int(port) if port is not None else resolve_hub_port()
    _ = host  # bind address is owned by yasinhub.api.server.run()
    _ = check_port
    target_dir = logs_dir or _hub_logs_dir()
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    log_path = target_dir / "yasinhub.log"
    try:
        log_file = open(log_path, "a", encoding="utf-8")
    except OSError:
        log_file = open(os.devnull, "a", encoding="utf-8")
    argv = [sys.executable, "-m", "yasinhub.api.server"]
    factory = popen_factory or subprocess.Popen
    proc = factory(
        argv,
        cwd=str(_hub_repo_root()),
        stdin=subprocess.DEVNULL,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    try:
        log_file.close()
    except Exception:
        pass
    try:
        save_pid(HUB_PID_NAME, int(proc.pid))
    except Exception:
        pass
    return proc


@dataclass
class HubVerifyResult:
    """Post-start runtime proof. No secrets."""

    running: bool = False
    pid: Optional[int] = None
    identity: Optional[bool] = None
    port_owned: Optional[bool] = None
    listening: bool = False
    health_ok: Optional[bool] = None
    reasons: List[str] = field(default_factory=list)


def verify_hub_running(
    pid: int,
    host: Optional[str] = None,
    port: Optional[int] = None,
    health_check: Optional[Callable[[str, int, str], bool]] = None,
) -> HubVerifyResult:
    """Accept RUNNING only with PID alive + Hub identity + listening + health.

    Port-ownership proof ladder mirrors the service lifecycle authority:
    strict PID-level proof where available, otherwise occupied-port plus the
    succeeding Hub health anchor. Anything else fails closed.
    """
    check_host = host or HUB_CHECK_HOST
    check_port = int(port) if port is not None else resolve_hub_port()
    verdict = HubVerifyResult(pid=None)
    try:
        pid_i = int(pid)
    except (TypeError, ValueError):
        verdict.reasons.append("invalid pid")
        return verdict
    verdict.pid = pid_i
    try:
        alive = is_pid_alive(pid_i)
    except Exception:
        alive = False
    if not alive:
        verdict.reasons.append(f"pid {pid_i} not alive")
        return verdict
    try:
        identity = is_yasinhub_process(pid_i)
    except Exception:
        identity = None
    verdict.identity = identity
    if identity is not True:
        verdict.reasons.append(
            f"pid {pid_i} identity unverified ({identity}); fail closed"
        )
        return verdict
    try:
        owners = port_owner_pids(check_port)
    except Exception:
        owners = None
    try:
        listening = bool(is_port_occupied(check_host, check_port))
    except Exception:
        listening = bool(owners)
    verdict.listening = listening
    if owners is None:
        verdict.port_owned = None
    else:
        verdict.port_owned = pid_i in set(owners)
        verdict.port_owned = bool(verdict.port_owned)
    if verdict.port_owned is False:
        verdict.reasons.append(
            f"pid {pid_i} does not own port {check_port} "
            f"(owners={sorted(set(owners or []))}); not RUNNING"
        )
        return verdict
    if verdict.port_owned is None and not listening:
        verdict.reasons.append(f"port {check_port} not listening; not RUNNING")
        return verdict
    probe = health_check or (lambda h, p, e: check_http_health(h, p, e))
    try:
        healthy = bool(probe(check_host, check_port, HUB_HEALTH_ENDPOINT))
    except Exception:
        healthy = False
    verdict.health_ok = healthy
    if not healthy:
        verdict.reasons.append(
            f"health {HUB_HEALTH_ENDPOINT} on port {check_port} did not "
            "succeed; not RUNNING"
        )
        return verdict
    verdict.running = True
    if verdict.port_owned is True:
        verdict.reasons.append(
            f"pid {pid_i} owns port {check_port}; identity and health verified"
        )
    else:
        verdict.reasons.append(
            f"pid {pid_i} verified by bind-correlation on port {check_port}; "
            "identity and health verified"
        )
    return verdict


@dataclass
class StartupResult:
    """Outcome of one launcher run. Diagnostics only; never secrets."""

    success: bool = False
    action: str = ""  # started | restarted | refused
    pid: Optional[int] = None
    port: int = 7000
    detail: str = ""
    preflight: Optional[PreflightResult] = None
    verify: Optional[HubVerifyResult] = None


def run_startup(
    host: Optional[str] = None,
    port: Optional[int] = None,
    stop_timeout: float = STOP_GRACE_SECONDS,
    release_timeout: float = PORT_RELEASE_TIMEOUT,
    verify_timeout: float = VERIFY_TIMEOUT,
    preflight_fn: Optional[Callable[..., PreflightResult]] = None,
    stop_fn: Optional[Callable[[int, float], bool]] = None,
    wait_release_fn: Optional[Callable[..., bool]] = None,
    start_fn: Optional[Callable[..., subprocess.Popen]] = None,
    verify_fn: Optional[Callable[..., HubVerifyResult]] = None,
) -> StartupResult:
    """Single-command orchestration: preflight -> restart-if-Hub -> start -> verify."""
    check_host = host or HUB_CHECK_HOST
    check_port = int(port) if port is not None else resolve_hub_port()
    outcome = StartupResult(success=False, port=check_port)
    do_preflight = preflight_fn or (lambda: preflight_hub_port(check_host, check_port))
    try:
        pre = do_preflight()
    except Exception as exc:
        outcome.detail = f"preflight failed safely: {type(exc).__name__}"
        return outcome
    outcome.preflight = pre
    if pre.decision == "foreign" or pre.decision == "indeterminate":
        outcome.action = "refused"
        outcome.detail = pre.detail or "port occupied by unknown owner; fail closed"
        return outcome
    if pre.decision not in ("free", "yasinhub"):
        outcome.action = "refused"
        outcome.detail = pre.detail or "preflight did not prove the port free; fail closed"
        return outcome

    old_pids: List[int] = list(pre.hub_pids) if pre.decision == "yasinhub" else []
    if pre.decision == "yasinhub":
        if not old_pids:
            outcome.action = "refused"
            outcome.detail = (
                f"port {check_port} occupied but no verified YasinHub PID; "
                "fail closed, nothing killed"
            )
            return outcome
        do_stop = stop_fn or (lambda pid, timeout: stop_hub_gracefully(pid, timeout))
        for old_pid in old_pids:
            try:
                stopped = bool(do_stop(int(old_pid), float(stop_timeout)))
            except Exception:
                stopped = False
            if not stopped:
                outcome.action = "refused"
                outcome.detail = (
                    f"existing YasinHub pid {old_pid} did not stop within "
                    f"{stop_timeout}s; fail closed, no new Hub started"
                )
                return outcome
        # Old process gone: require the port to actually be released.
        do_wait = wait_release_fn or (
            lambda: wait_port_released(check_host, check_port, old_pids[0], release_timeout)
        )
        try:
            released = bool(do_wait())
        except Exception:
            released = False
        if not released:
            outcome.action = "refused"
            outcome.detail = (
                f"port {check_port} still occupied after stopping "
                f"YasinHub pid(s)={old_pids}; fail closed, no new Hub started"
            )
            return outcome
        try:
            for old_pid in old_pids:
                try:
                    if not is_pid_alive(int(old_pid)):
                        remove_pid(HUB_PID_NAME)
                except Exception:
                    pass
        except Exception:
            pass

    do_start = start_fn or (lambda: start_hub_process(check_host, check_port))
    try:
        proc = do_start()
        new_pid = int(getattr(proc, "pid"))
    except Exception as exc:
        outcome.action = "refused"
        outcome.detail = f"failed to start YasinHub: {type(exc).__name__}"
        return outcome
    if old_pids and new_pid in old_pids:
        outcome.action = "refused"
        outcome.pid = new_pid
        outcome.detail = f"new PID {new_pid} reuses old PID; fail closed"
        return outcome

    do_verify = verify_fn or (
        lambda pid: verify_hub_running(pid, check_host, check_port)
    )
    deadline = max(0.5, float(verify_timeout))
    attempts = max(1, int(deadline / VERIFY_POLL))
    last: Optional[HubVerifyResult] = None
    for _ in range(attempts):
        try:
            last = do_verify(new_pid)
        except Exception:
            last = HubVerifyResult(pid=new_pid, reasons=["verify raised safely"])
        if last is not None and last.running:
            break
        # Fail fast when identity is definitively foreign: waiting cannot fix
        # our own child being the wrong process.
        if last is not None and last.identity is False:
            break
        try:
            child_gone = getattr(proc, "poll", lambda: None)() is not None
        except Exception:
            child_gone = False
        if child_gone:
            break
        time.sleep(VERIFY_POLL)
    outcome.verify = last
    outcome.pid = new_pid
    if last is not None and last.running:
        outcome.success = True
        outcome.action = "restarted" if old_pids else "started"
        outcome.detail = (
            f"YasinHub running: pid={new_pid} port={check_port} listening "
            f"health={HUB_HEALTH_ENDPOINT}; " + "; ".join(last.reasons)
        )
        return outcome
    reasons = "; ".join((last.reasons if last else []) or ["verification failed"])
    # Our own fresh child failed verification: stop only that child, never
    # any unrelated PID, then fail closed.
    try:
        if is_yasinhub_process(new_pid) is True or (
            last is not None and last.identity is not False
        ):
            try:
                stop_hub_gracefully(new_pid, timeout=min(5.0, float(stop_timeout)))
            except Exception:
                pass
    except Exception:
        pass
    try:
        remove_pid(HUB_PID_NAME)
    except Exception:
        pass
    outcome.action = "refused"
    outcome.detail = f"new YasinHub pid={new_pid} failed verification: {reasons}"
    return outcome


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yasinhub-startup",
        description=(
            "Official single-command YasinHub startup: preflight port 7000, "
            "safely restart an existing Hub, start, then verify. "
            "Non-interactive, Termux-compatible."
        ),
    )
    parser.add_argument("--port", type=int, default=None, help="Hub port (default 7000)")
    parser.add_argument("--host", default=HUB_CHECK_HOST, help="check host (default 127.0.0.1)")
    parser.add_argument("--stop-timeout", type=float, default=STOP_GRACE_SECONDS)
    parser.add_argument("--release-timeout", type=float, default=PORT_RELEASE_TIMEOUT)
    parser.add_argument("--verify-timeout", type=float, default=VERIFY_TIMEOUT)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Non-interactive entrypoint. Never prompts, never reads stdin."""
    args = build_parser().parse_args(argv)
    try:
        port = int(args.port) if args.port is not None else resolve_hub_port()
    except (TypeError, ValueError):
        print("startup refused: invalid port", flush=True)
        return 2
    result = run_startup(
        host=args.host,
        port=port,
        stop_timeout=float(args.stop_timeout),
        release_timeout=float(args.release_timeout),
        verify_timeout=float(args.verify_timeout),
    )
    if result.success:
        print(
            f"YasinHub startup ok: action={result.action} "
            f"pid={result.pid} port={result.port}",
            flush=True,
        )
        return 0
    print(f"YasinHub startup refused: {result.detail}", flush=True)
    if result.preflight is not None:
        pre = result.preflight
        safe_owners = list(pre.proc_owner_pids)
        print(
            f"preflight: occupied={pre.occupied} "
            f"decision={pre.decision} owners={safe_owners} "
            f"hub={list(pre.hub_pids)}",
            flush=True,
        )
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
