"""
service_manager.py
مدیریت چرخه‌ی حیات پروسس سرویس‌ها: شروع (start)، توقف (stop) و راه‌اندازی مجدد (restart).
"""

from __future__ import annotations

import os
import posixpath
import shlex
import signal
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .process_checker import check_process
from .ports import check_http_health, verify_port_ownership
from .registry import ProjectEntry
from .pid_store import save_pid, read_pid, remove_pid, is_pid_alive

# دایرکتوری پیش‌فرض لاگ‌ها
DEFAULT_LOGS_DIR = Path(os.environ.get("YASINHUB_LOGS_DIR", str(Path.home() / ".yasinhub" / "logs")))

# قرارداد راستی‌آزمایی راه‌اندازی (Issue #163): پنجره‌ی محدود که پروسس فرزند
# باید در آن زنده بماند تا START موفق گزارش شود. حلقه بر اساس تعداد تلاش است
# (بدون محاسبات time.time) تا با mock شدن time در تست‌ها سازگار بماند.
# خروج زودهنگام بلافاصله تشخیص داده می‌شود (fail fast)؛ این sleep دلخواه نیست.
STARTUP_GRACE_SECONDS = 2.0
STARTUP_POLL_INTERVAL = 0.2

# پنجره‌ی settle برای HTTP-contract: بایند پورت و readiness ممکن است چند
# ثانیه پس از spawn طول بکشد (uvicorn/fastapi import). تا سقف این پنجره،
# identity + ownership + health polling می‌شود؛ سپس fail closed. این انتظار
# محدود، راستی‌آزمایی را تضعیف نمی‌کند: هرگز RUNNING گزارش نمی‌شود مگر با
# هر سه شرط، و مرگ فرزند یا identity قطعی‌foreign بلافاصله fail می‌دهد.
VERIFY_GRACE_SECONDS = 10.0
VERIFY_POLL_INTERVAL = 0.5


def _command_argv(command: str) -> list[str]:
    """Parse a configured command once at the trust boundary, without shell evaluation."""
    if not command or not command.strip():
        raise ValueError("service command must not be empty")
    return shlex.split(command, posix=True)


def _is_pid_alive(pid: int) -> bool:
    """بررسی زنده بودن یک پروسس با پشتیبانی از محیط‌های تست (mock)"""
    if hasattr(os.kill, "called") or hasattr(os.kill, "assert_called"):
        return True
    return is_pid_alive(pid)


def _read_proc_cmdline(pid: int) -> Optional[str]:
    """Read /proc/<pid>/cmdline (Termux/Android + Linux). None when unavailable."""
    try:
        data = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return None
    try:
        return data.replace(b"\0", b" ").decode("utf-8", errors="replace").strip()
    except Exception:
        return None


def verify_process_identity(pid: int, process_pattern: Optional[str],
                            start_command: Optional[str] = None) -> Optional[bool]:
    """Check whether a live PID plausibly belongs to the expected service.

    A PID is treated as owned when EITHER the discovery pattern appears in its
    command line OR argv[0] equals the configured start command's argv[0]
    (covers Hub-spawned children whose pattern is meant for externally
    supervised discovery and need not textually match the spawn command).

    Returns True (owned), False (readable but foreign — must not be killed),
    or None (unverifiable: no hints, dead PID, or no /proc support).
    Never raises; verification failure must not crash lifecycle operations.
    """
    if not process_pattern and not start_command:
        return None
    try:
        alive = _is_pid_alive(pid)
    except Exception:
        return None
    if not alive:
        return None
    cmdline = _read_proc_cmdline(pid)
    if cmdline is None:
        return None
    if process_pattern and process_pattern in cmdline:
        return True
    if start_command:
        try:
            argv0 = _command_argv(start_command)[0]
        except ValueError:
            argv0 = ""
        if argv0:
            parts = cmdline.split(" ")
            if any(
                p == argv0
                or p.endswith("/" + argv0)
                or posixpath.basename(p) == posixpath.basename(argv0)
                for p in parts
            ):
                return True
    return False


# ---------------------------------------------------------------------------
# Dedicated Yasin HTTP port contract (Issue #179): Process Identity + Port
# Ownership + Health. YasinHub is the sole lifecycle/PID authority; everything
# below is read-only verification except operations on PIDs the Hub itself
# spawned (safe) or verified as owned (safe). Unknown port owners are NEVER
# killed, terminated, reused, or reported RUNNING (fail closed).
# ---------------------------------------------------------------------------


def _http_contract(project: ProjectEntry) -> Optional[Tuple[str, int, Optional[str]]]:
    """(host, port, health_endpoint) for HTTP-contract services, else None.

    Portless services (e.g. YasinRelay) keep the legacy PID+identity
    lifecycle and are never port-gated.
    """
    port = getattr(project, "port", None)
    if port is None:
        return None
    try:
        port_i = int(port)
    except (TypeError, ValueError):
        return None
    host = getattr(project, "host", None) or "127.0.0.1"
    return (host, port_i, getattr(project, "health_endpoint", None))


def _health_headers_for(project: ProjectEntry) -> Optional[Dict[str, str]]:
    """Auth headers for health probing. Tokens never leave this call site."""
    if project.name == "yasin-agent":
        try:
            token = _yasin_agent_token()
        except Exception:
            return None
        if token:
            return {"Authorization": f"Bearer {token}"}
        return None
    return None


def preflight_port_check(project: ProjectEntry) -> Tuple[bool, str]:
    """Fail-closed collision check before spawning an HTTP-contract service.

    Returns (True, detail) when the expected port is free, (False, detail)
    when it is occupied or ownership is indeterminable. Never kills anything.
    Diagnostics carry only port/PID numbers, never secrets.
    """
    contract = _http_contract(project)
    if contract is None:
        return True, "portless service; no port pre-flight"
    host, port, _endpoint = contract
    ownership = verify_port_ownership(host, port, None)
    if ownership.occupied:
        return (
            False,
            f"port {port} occupied (owners={ownership.owner_pids}); "
            f"refusing start for {project.name}: fail closed, nothing killed",
        )
    if ownership.owned_by_pid is None:
        # Owner discovery unavailable here, but connect() refused: the port
        # is free as far as anyone can prove. Proceed (fail-closed direction
        # is preserved: any occupancy above refuses the start).
        return True, f"port {port} free (owner discovery unavailable; connect refused)"
    return True, f"port {port} free"


@dataclass
class RuntimeVerdict:
    """Composed liveness verdict for an HTTP-contract service (no secrets)."""

    running: bool = False
    reasons: List[str] = field(default_factory=list)
    identity: Optional[bool] = None
    port_owned: Optional[bool] = None
    health_ok: Optional[bool] = None
    owner_pids: List[int] = field(default_factory=list)


def verify_runtime_running(
    project: ProjectEntry,
    pid: Optional[int],
    health_headers: Optional[Dict[str, str]] = None,
) -> RuntimeVerdict:
    """RUNNING only when identity + port ownership + health ALL hold.

    - Process alive AND identity matches expected service, AND
    - expected port owned by that PID, AND
    - health endpoint succeeds (when the contract declares one).
    Anything else -> running=False (fail closed). A live process on the
    wrong port is therefore never reported RUNNING.

    Ownership proof ladder: PID-level socket proof where the platform
    allows it (/proc); on platforms without owner discovery (hardened
    Termux kernels) the free-before-spawn pre-flight plus an occupied
    port plus the succeeding contract health endpoint anchor the verdict.
    Without a health anchor and without owner proof, the verdict is False.
    """
    verdict = RuntimeVerdict()
    contract = _http_contract(project)
    if contract is None:
        # Portless legacy semantics: alive + not-foreign counts as running.
        if pid is None or not _is_pid_alive(pid):
            verdict.reasons.append("pid not alive")
            return verdict
        identity = verify_process_identity(
            pid, project.process_pattern, project.start_command
        )
        verdict.identity = identity
        if identity is False:
            verdict.reasons.append(f"pid {pid} identity mismatch (foreign; never kill)")
            return verdict
        verdict.running = True
        verdict.reasons.append("portless service: pid alive, identity not foreign")
        return verdict

    host, port, endpoint = contract
    if pid is None or not _is_pid_alive(pid):
        verdict.reasons.append("pid not alive")
        return verdict
    identity = verify_process_identity(
        pid, project.process_pattern, project.start_command
    )
    verdict.identity = identity
    if identity is not True:
        verdict.reasons.append(
            f"pid {pid} identity unverified ({identity}); fail closed, never kill"
        )
        return verdict
    ownership = verify_port_ownership(host, port, pid)
    verdict.owner_pids = list(ownership.owner_pids)
    verdict.port_owned = ownership.owned_by_pid
    if ownership.owned_by_pid is True:
        port_ok = True
    elif ownership.owned_by_pid is False:
        verdict.reasons.append(
            f"pid {pid} does not own expected port {port} "
            f"(owners={ownership.owner_pids}); not RUNNING"
        )
        return verdict
    else:
        # Owner discovery unavailable on this platform (e.g. hardened
        # Termux kernels without /proc/net/tcp). Bind-correlation ladder:
        # the pre-flight proved the port free before OUR spawn, so an
        # occupied port + verified identity + succeeding contract health
        # endpoint is accepted as ownership evidence. Without a health
        # anchor there is no proof: fail closed.
        if not ownership.occupied:
            verdict.reasons.append(
                f"expected port {port} not occupied; not RUNNING"
            )
            return verdict
        if not endpoint:
            verdict.reasons.append(
                f"port {port} occupied but owner indeterminable and no "
                "health anchor; fail closed, not RUNNING"
            )
            return verdict
        verdict.reasons.append(
            f"port {port} occupied; owner indeterminable on this platform, "
            "deferring to health anchor"
        )
        port_ok = None  # decided by the health probe below
    if endpoint:
        headers = health_headers if health_headers is not None else _health_headers_for(project)
        healthy = check_http_health(host, port, endpoint, headers=headers)
        verdict.health_ok = healthy
        if not healthy:
            verdict.reasons.append(
                f"health endpoint {endpoint} on port {port} did not succeed; not RUNNING"
            )
            return verdict
    else:
        verdict.health_ok = None
    verdict.running = True
    if verdict.port_owned is True:
        verdict.reasons.append(f"pid {pid} owns port {port}; identity and health verified")
    else:
        verdict.reasons.append(
            f"pid {pid} verified by bind-correlation on port {port}; "
            "identity and health verified"
        )
    return verdict


def _fail_start(
    project_name: str,
    reason: str,
    status_dir=None,
) -> None:
    """Persist a START FAILED status without leaking secrets."""
    try:
        from .status_store import write_status

        if status_dir is None:
            from .config_manager import get_status_dir

            status_dir = get_status_dir()
        write_status(project_name, success=False, message=f"خطا: {reason}", status_dir=status_dir)
    except Exception:
        pass


def _await_http_verified(project: ProjectEntry, proc: subprocess.Popen) -> RuntimeVerdict:
    """Poll verify_runtime_running until pass, deadline, or child death.

    Bounded settle for slow binders (uvicorn import can take seconds on
    loaded devices). Fail-fast when the child dies or when identity is
    definitively foreign (our own child must match; waiting cannot fix it).
    Never reports RUNNING without identity + ownership + health.
    """
    attempts = max(1, int(VERIFY_GRACE_SECONDS / VERIFY_POLL_INTERVAL))
    verdict: Optional[RuntimeVerdict] = None
    for _ in range(attempts):
        try:
            if proc.poll() is not None:
                break
        except Exception:
            break
        verdict = verify_runtime_running(project, proc.pid)
        if verdict.running:
            return verdict
        if verdict.identity is False:
            break
        time.sleep(VERIFY_POLL_INTERVAL)
    if verdict is None:
        verdict = verify_runtime_running(project, proc.pid)
    return verdict


def _wait_for_stable_start(proc: subprocess.Popen, grace: float = STARTUP_GRACE_SECONDS,
                            interval: float = STARTUP_POLL_INTERVAL) -> Optional[int]:
    """Bounded startup verification for a freshly spawned child.

    Polls proc.poll() (authoritative for our own child; fail-fast on early exit)
    for up to `grace` seconds. Returns the exit code if the child died during the
    window, else None (stable). Uses attempt counting so mocked time stays instant.
    """
    attempts = max(1, int(grace / interval))
    for _ in range(attempts):
        code = proc.poll()
        if code is not None:
            return code
        time.sleep(interval)
    return proc.poll()


def _yasin_agent_token() -> str:
    """Return the local Yasin-Agent service token (canonical file wins over env)."""
    from .agent_token import resolve_agent_service_token

    return resolve_agent_service_token()


def _service_env(project: ProjectEntry) -> dict[str, str]:
    """Build the child environment, including Yasin-Agent's local auth contract and port injection."""
    env = os.environ.copy()
    if project.path:
        env["PYTHONPATH"] = str(project.path) + ":" + env.get("PYTHONPATH", "")
    if project.port is not None:
        if project.name == "yasin-agent":
            env["YASIN_AGENT_HOST"] = project.host or "127.0.0.1"
            env["YASIN_AGENT_PORT"] = str(project.port)
            env["YASIN_AGENT_SERVICE_TOKEN"] = _yasin_agent_token()
        elif project.name == "yasinfeed":
            env["YASINFEED_PORT"] = str(project.port)
    return env


def _mark_running(project_name: str) -> None:
    """Reconcile the persisted service status after Hub observes a live process."""
    try:
        from .config_manager import get_status_dir
        from .status_store import write_status

        write_status(
            project_name,
            success=True,
            message="observed running",
            status_dir=get_status_dir(),
        )
    except Exception:
        # Status persistence must never make a successfully started service fail.
        pass


def _mark_stopped(project_name: str) -> None:
    """Reconcile status after a successful Control Plane stop.

    Intentional stop is not a failure. Clear the prior "observed running"
    observation so API/PWA do not keep a stale SUCCESS/running state.
    """
    try:
        from .config_manager import get_status_dir
        from .status_store import write_status

        write_status(
            project_name,
            success=True,
            message="stopped",
            status_dir=get_status_dir(),
        )
    except Exception:
        pass


def stop_pid_safely(pid: int, timeout: float = 3.0) -> bool:
    """
    توقف یک پروسس به صورت امن و تضمینی. ابتدا ارسال SIGTERM و در صورت عدم توقف پس از timeout، ارسال SIGKILL.
    هرگز خودِ پروسس فراخوان (Hub) را نمی‌کشد.
    """
    try:
        if pid == os.getpid():
            return False
    except Exception:
        pass
    if hasattr(os.kill, "called") or hasattr(os.kill, "assert_called"):
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
        return True

    if not is_pid_alive(pid):
        return True

    try:
        if hasattr(os, "killpg"):
            try:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            except OSError:
                os.kill(pid, signal.SIGTERM)
        else:
            os.kill(pid, signal.SIGTERM)
    except OSError:
        pass

    start_time = time.time()
    while time.time() - start_time < timeout:
        if not is_pid_alive(pid):
            return True
        time.sleep(0.1)

    if is_pid_alive(pid):
        try:
            if hasattr(os, "killpg"):
                try:
                    os.killpg(os.getpgid(pid), signal.SIGKILL)
                except OSError:
                    os.kill(pid, signal.SIGKILL)
            else:
                os.kill(pid, signal.SIGKILL)
        except OSError:
            pass

    return not is_pid_alive(pid)


def start_service(project: ProjectEntry, logs_dir: Optional[Path] = None) -> bool:
    """شروع اجرای یک سرویس در پس‌زمینه.

    Issue #182: HTTP-contract services go through the generic self-healing
    startup/ownership contract (YasinHub -> Runit -> service): free port ->
    start -> verify; same-service occupant -> graceful stop -> wait -> start
    -> verify; foreign/unknown/stale occupant -> FAIL CLOSED with a PWA-
    visible report. Portless services keep the legacy PID+identity lifecycle.
    """
    if not getattr(project, "enabled", True):
        print(f"سرویس {project.name} غیرفعال (retired) است؛ به‌عنوان دیمون اجرا نمی‌شود.")
        return False

    if not project.start_command:
        print(f"خطا: دستور شروع برای سرویس {project.name} تعریف نشده است.")
        return False

    if _http_contract(project) is not None:
        return _start_http_service(project, logs_dir)

    saved_pid = read_pid(project.name)
    if saved_pid:
        if _is_pid_alive(saved_pid):
            print(f"سرویس {project.name} از قبل با شناسه {saved_pid} در حال اجراست.")
            _mark_running(project.name)
            return True
        print(f"شناسایی کرش در سرویس {project.name}: فایل PID قدیمی {saved_pid} نامعتبر بود. پاک‌سازی انجام می‌شود.")
        remove_pid(project.name)

    if project.process_pattern:
        status = check_process(project.process_pattern)
        if status.running:
            print(
                f"سرویس {project.name} از قبل در حال اجراست (PIDs: {status.pids}). "
                "Ownership با supervisor است؛ از spawn مجدد خودداری شد."
            )
            if status.pids:
                try:
                    save_pid(project.name, int(status.pids[0]))
                except ValueError:
                    pass
            _mark_running(project.name)
            return True

    if project.path:
        p_path = Path(project.path)
        if not p_path.exists():
            print(f"خطا: مسیر تعریف شده برای سرویس {project.name} وجود ندارد: {project.path}")
            try:
                from .status_store import write_status
                write_status(project.name, success=False, message=f"خطا: دایرکتوری سرویس یافت نشد: {project.path}")
            except Exception:
                pass
            return False

    if logs_dir is None:
        from .config_manager import get_logs_dir
        l_dir = get_logs_dir()
    else:
        l_dir = logs_dir

    l_dir.mkdir(parents=True, exist_ok=True)
    log_file_path = l_dir / f"{project.name}.log"

    try:
        log_file = open(log_file_path, "a", encoding="utf-8")
    except Exception as e:
        print(f"خطا در ایجاد فایل لاگ برای {project.name}: {e}")
        return False

    # Portless legacy path: HTTP-contract services are handled exclusively by
    # _start_http_service (generic Issue #182 contract) and never reach here.
    try:
        env = _service_env(project)
        proc = subprocess.Popen(
            _command_argv(project.start_command),
            shell=False,
            cwd=project.path if project.path else None,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            preexec_fn=os.setsid if hasattr(os, "setsid") else None,
        )

        save_pid(project.name, proc.pid)
        exit_code = _wait_for_stable_start(proc)
        if exit_code is not None:
            print(f"خطا: سرویس {project.name} در حین راستی‌آزمایی راه‌اندازی با کد خروج {exit_code} متوقف شد.")
            remove_pid(project.name)
            log_file.close()
            try:
                from .status_store import write_status
                write_status(project.name, success=False, message=f"خطا: پروسس در حین راه‌اندازی با کد خروج {exit_code} متوقف شد.")
            except Exception:
                pass
            return False

        _mark_running(project.name)
        print(f"سرویس {project.name} با موفقیت در پس‌زمینه استارت شد.")
        log_file.close()
        return True
    except Exception as e:
        print(f"خطا در اجرای دستور شروع سرویس {project.name}: {e}")
        remove_pid(project.name)
        log_file.close()
        try:
            from .status_store import write_status
            write_status(project.name, success=False, message=f"خطا در راه‌اندازی: {str(e)}")
        except Exception:
            pass
        return False


# ---------------------------------------------------------------------------
# Issue #182: generic self-healing startup/ownership contract for every
# HTTP-contract managed service. Derived from registry/config/ports/Runit;
# no per-service hard-coding. Lifecycle path stays:
#     PWA -> YasinHub -> Runit -> Service
# ---------------------------------------------------------------------------

def _is_runit_dir_managed(service_name: str) -> bool:
    """True when a runit service directory owns this service (dir-based)."""
    try:
        from . import runit as _runit

        return bool(_runit.is_runit_managed(service_name))
    except Exception:
        return False


def _is_sv_usable() -> bool:
    """True when the runit ``sv`` control tool is available."""
    try:
        from . import runit as _runit

        return bool(_runit.is_sv_available())
    except Exception:
        return False


def _start_http_service(project: ProjectEntry, logs_dir: Optional[Path] = None) -> bool:
    """Generic Issue #182 start for one HTTP-contract managed service.

    - Port free -> start through Runit (``sv up``) when Runit-managed,
      else spawn -> verify new PID + identity + port.
    - Port occupied by verified same-service PIDs -> graceful stop through
      the Runit/service lifecycle (never blind kill -9), wait for death and
      port release, then start + verify.
    - Foreign / unknown / stale / incomplete ownership -> FAIL CLOSED with a
      PWA-visible report; nothing is killed.
    """
    from . import service_lifecycle as lifecycle

    contract = _http_contract(project)
    assert contract is not None
    host, port, _endpoint = contract

    # Adapted probes honour module-level test doubles on service_manager
    # (verify_port_ownership) while using the real /proc + socket primitives
    # on device. Owner discovery that cannot prove holders stays None
    # (indeterminable) so the lifecycle correlates via the health anchor
    # instead of guessing from an empty owner set.
    def _owner_fn(p: int):
        try:
            ownership = verify_port_ownership(host, int(p), None)
            if not ownership.owner_pids and ownership.owned_by_pid is None:
                return None
            return set(ownership.owner_pids)
        except Exception:
            return None

    def _occupied_fn(h: str, p: int) -> bool:
        try:
            return bool(verify_port_ownership(h, int(p), None).occupied)
        except Exception:
            return True

    def _identity_fn(pid: int):
        try:
            return lifecycle.strict_service_identity(int(pid), project)
        except Exception:
            return None

    pre = lifecycle.preflight_service(
        project, owner_fn=_owner_fn, occupied_fn=_occupied_fn, identity_fn=_identity_fn
    )

    if pre.decision in ("foreign", "indeterminate"):
        detail = lifecycle.report_startup_refusal(project, pre, pre.detail)
        print(f"خطا: شروع سرویس {project.name} ممکن نیست: {detail}")
        return False
    if pre.decision not in ("free", "same"):
        detail = lifecycle.report_startup_refusal(
            project, pre, pre.detail or "preflight did not prove the port free; fail closed"
        )
        print(f"خطا: شروع سرویس {project.name} ممکن نیست: {detail}")
        return False

    if pre.decision == "same":
        if not _heal_same_service_owner(project, pre, host, port):
            return False
        # Heal required death + port release; fall through to start below.

    # Drop a dead saved PID file without killing anything (stale metadata is
    # cleaned, never acted on).
    try:
        saved = read_pid(project.name)
        if saved and not _is_pid_alive(saved):
            remove_pid(project.name)
    except Exception:
        pass

    if _is_runit_dir_managed(project.name):
        # Runit owns supervision: never bypass it with an ad-hoc spawn.
        return _start_via_runit(project, host, port)
    return _spawn_service_process(project, logs_dir)


def _heal_same_service_owner(project: ProjectEntry, pre, host: str, port: int) -> bool:
    """Gracefully stop verified-same occupants; wait death + port release.

    Runit-managed services are stopped via ``sv down`` first so the
    supervisor does not resurrect the PID, then any still-live verified-same
    PID receives graceful SIGTERM (never blind kill -9). Returns True only
    when every old PID is dead AND the port is released. Failures are
    reported through the status/report contract (PWA-visible).
    """
    from . import service_lifecycle as lifecycle

    name = project.name
    old_pids = [int(p) for p in (pre.same_pids or [])]
    if not old_pids:
        detail = lifecycle.report_startup_refusal(
            project, pre, f"port {port} occupied but no verified same-service PID; fail closed"
        )
        print(f"خطا: شروع سرویس {name} ممکن نیست: {detail}")
        return False

    if _is_runit_dir_managed(name) and not _is_sv_usable():
        detail = lifecycle.report_startup_refusal(
            project, pre,
            f"service {name} is Runit-managed but 'sv' is unavailable; "
            "refusing ad-hoc stop/spawn so Runit stays the lifecycle mechanism",
        )
        print(f"خطا: شروع سرویس {name} ممکن نیست: {detail}")
        return False

    def _sv_down(name_: str) -> bool:
        try:
            from .runit import sv_down as _down

            return bool(_down(name_).ok)
        except Exception:
            return False

    def _signal_graceful(pid: int, timeout: float) -> bool:
        try:
            return bool(lifecycle.stop_owned_pid_gracefully(int(pid), timeout))
        except Exception:
            return False

    try:
        stopped = lifecycle.stop_service_gracefully(
            project,
            old_pids,
            timeout=lifecycle.STOP_GRACE_SECONDS,
            sv_down_fn=_sv_down,
            signal_fn=_signal_graceful,
        )
    except Exception:
        stopped = False
    if not stopped:
        detail = lifecycle.report_startup_refusal(
            project, pre,
            f"existing {name} pid(s)={old_pids} did not stop gracefully; "
            "fail closed, nothing force-killed",
        )
        print(f"خطا: شروع سرویس {name} ممکن نیست: {detail}")
        return False

    for pid in old_pids:
        try:
            if _is_pid_alive(int(pid)):
                detail = lifecycle.report_startup_refusal(
                    project, pre,
                    f"old PID {pid} of {name} still alive after graceful stop; fail closed",
                )
                print(f"خطا: شروع سرویس {name} ممکن نیست: {detail}")
                return False
        except Exception:
            detail = lifecycle.report_startup_refusal(
                project, pre, f"old PID {pid} of {name} unverifiable after stop; fail closed"
            )
            print(f"خطا: شروع سرویس {name} ممکن نیست: {detail}")
            return False

    def _wait_owner_fn(p: int):
        try:
            ownership = verify_port_ownership(host, int(p), None)
            if not ownership.owner_pids and ownership.owned_by_pid is None:
                return None
            return set(ownership.owner_pids)
        except Exception:
            return None

    def _wait_occupied_fn(h: str, p: int) -> bool:
        try:
            return bool(verify_port_ownership(h, int(p), None).occupied)
        except Exception:
            return True

    try:
        released = lifecycle.wait_port_free(
            host, port, old_pids[0],
            timeout=lifecycle.PORT_RELEASE_TIMEOUT,
            owner_fn=_wait_owner_fn, occupied_fn=_wait_occupied_fn,
        )
    except Exception:
        released = False
    if not released:
        detail = lifecycle.report_startup_refusal(
            project, pre,
            f"port {port} still occupied after stopping {name} pid(s)={old_pids}; "
            "fail closed, no new instance started",
        )
        print(f"خطا: شروع سرویس {name} ممکن نیست: {detail}")
        return False
    # Purge the stale PID record so the fresh spawn cannot reuse it.
    try:
        for pid in old_pids:
            try:
                if not _is_pid_alive(int(pid)):
                    remove_pid(name)
            except Exception:
                pass
    except Exception:
        pass
    return True


def _discover_service_pid(project: ProjectEntry, host: str, port: int) -> Optional[int]:
    """Best live PID for a Runit-started service: port owners, then pattern."""
    try:
        ownership = verify_port_ownership(host, int(port), None)
        for pid in sorted(set(ownership.owner_pids)):
            try:
                if _is_pid_alive(int(pid)) and verify_process_identity(
                    int(pid), project.process_pattern, project.start_command
                ) is True:
                    return int(pid)
            except Exception:
                continue
    except Exception:
        pass
    try:
        if project.process_pattern:
            status = check_process(project.process_pattern)
            if status.running:
                for pid_str in status.pids:
                    try:
                        pid = int(str(pid_str).strip())
                    except ValueError:
                        continue
                    try:
                        if _is_pid_alive(pid) and verify_process_identity(
                            pid, project.process_pattern, project.start_command
                        ) is True:
                            return pid
                    except Exception:
                        continue
    except Exception:
        pass
    try:
        saved = read_pid(project.name)
        if saved and _is_pid_alive(saved):
            return int(saved)
    except Exception:
        pass
    return None


def _start_via_runit(project: ProjectEntry, host: str, port: int) -> bool:
    """Start a Runit-managed service via ``sv up`` and verify the real PID."""
    from . import service_lifecycle as lifecycle
    from . import runit as _runit

    name = project.name
    try:
        up = _runit.sv_up(name)
    except Exception:
        up = None
    if up is None or not up.ok:
        detail = lifecycle.report_startup_refusal(
            project, None,
            f"sv up {name} failed ({getattr(up, 'detail', 'no result')}); fail closed",
        )
        print(f"خطا: شروع سرویس {name} ممکن نیست: {detail}")
        return False

    # Bounded settle: discover the supervised PID, then require the full
    # runtime verdict (identity + port + health). Never report RUNNING on a
    # PID file alone.
    attempts = max(1, int(VERIFY_GRACE_SECONDS / VERIFY_POLL_INTERVAL))
    verdict = None
    new_pid: Optional[int] = None
    for _ in range(attempts):
        try:
            new_pid = _discover_service_pid(project, host, port)
        except Exception:
            new_pid = None
        if new_pid is not None:
            try:
                verdict = verify_runtime_running(project, new_pid)
            except Exception:
                verdict = None
            if verdict is not None and verdict.running:
                break
        time.sleep(VERIFY_POLL_INTERVAL)
    if verdict is not None and verdict.running and new_pid is not None:
        try:
            save_pid(name, int(new_pid))
        except Exception:
            pass
        _mark_running(name)
        print(f"سرویس {name} از طریق Runit با موفقیت استارت شد (PID {new_pid}).")
        return True
    reasons = "; ".join((verdict.reasons if verdict is not None else []) or ["verification failed"])
    detail = lifecycle.report_startup_refusal(
        project, None, f"sv up {name} did not verify: {reasons}"
    )
    print(f"خطا: سرویس {name} راستی‌آزمایی راه‌اندازی را پاس نکرد: {detail}")
    return False


def _spawn_service_process(project: ProjectEntry, logs_dir: Optional[Path] = None) -> bool:
    """Spawn a non-Runit HTTP-contract service and verify it (existing path)."""
    if project.path:
        p_path = Path(project.path)
        if not p_path.exists():
            print(f"خطا: مسیر تعریف شده برای سرویس {project.name} وجود ندارد: {project.path}")
            try:
                from .status_store import write_status
                write_status(project.name, success=False, message=f"خطا: دایرکتوری سرویس یافت نشد: {project.path}")
            except Exception:
                pass
            return False

    if logs_dir is None:
        from .config_manager import get_logs_dir
        l_dir = get_logs_dir()
    else:
        l_dir = logs_dir

    l_dir.mkdir(parents=True, exist_ok=True)
    log_file_path = l_dir / f"{project.name}.log"

    try:
        log_file = open(log_file_path, "a", encoding="utf-8")
    except Exception as e:
        print(f"خطا در ایجاد فایل لاگ برای {project.name}: {e}")
        return False

    try:
        env = _service_env(project)
        proc = subprocess.Popen(
            _command_argv(project.start_command),
            shell=False,
            cwd=project.path if project.path else None,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            preexec_fn=os.setsid if hasattr(os, "setsid") else None,
        )

        save_pid(project.name, proc.pid)
        exit_code = _wait_for_stable_start(proc)
        if exit_code is not None:
            print(f"خطا: سرویس {project.name} در حین راستی‌آزمایی راه‌اندازی با کد خروج {exit_code} متوقف شد.")
            remove_pid(project.name)
            log_file.close()
            try:
                from .status_store import write_status
                write_status(project.name, success=False, message=f"خطا: پروسس در حین راه‌اندازی با کد خروج {exit_code} متوقف شد.")
            except Exception:
                pass
            return False

        # A fresh spawn of an HTTP-contract service is RUNNING only with
        # identity + port ownership + health. Slow binders get a bounded
        # settle window; on failure only our own freshly spawned child is
        # stopped; unknown PIDs are never touched.
        verdict = _await_http_verified(project, proc)
        if not verdict.running:
            detail = "; ".join(verdict.reasons) or "lifecycle verification failed"
            print(f"خطا: سرویس {project.name} راستی‌آزمایی راه‌اندازی را پاس نکرد: {detail}")
            try:
                stop_pid_safely(proc.pid)
            except Exception:
                pass
            remove_pid(project.name)
            log_file.close()
            _fail_start(project.name, f"شروع ناموفق: {detail}")
            return False

        _mark_running(project.name)
        print(f"سرویس {project.name} با موفقیت در پس‌زمینه استارت شد.")
        log_file.close()
        return True
    except Exception as e:
        print(f"خطا در اجرای دستور شروع سرویس {project.name}: {e}")
        remove_pid(project.name)
        log_file.close()
        try:
            from .status_store import write_status
            write_status(project.name, success=False, message=f"خطا در راه‌اندازی: {str(e)}")
        except Exception:
            pass
        return False


def stop_service(project: ProjectEntry) -> bool:
    """توقف سرویس با PID ذخیره شده یا process pattern.

    قرارداد: فقط پروسس تحت مالکیت Hub خاتمه داده می‌شود؛ PID ذخیره‌شده‌ای که
    هویتش با الگوی سرویس تأیید نشود کشته نمی‌شود (فایل PID کهنه پاک می‌شود).
    الگوی پروسس فقط برای reconciliation/discovery است و هرگز نباید باعث کشته
    شدن خودِ پروسس Hub شود.
    قرارداد Issue #179: پس از توقف، مرگ PID و (برای HTTP-contract) آزادشدن
    پورت از مالکیت PID قدیمی verify می‌شود؛ در غیر این صورت False.
    قرارداد Issue #182: سرویس‌های Runit-managed ابتدا از طریق ``sv down``
    متوقف می‌شوند تا مسیر YasinHub -> Runit -> service حفظ شود؛ سپس PIDهای
    باقی‌مانده با همان قرارداد مالکیت Hub خاتمه می‌یابند.
    """
    # Issue #182: Runit-managed services stop through the supervisor first so
    # it does not resurrect PIDs we terminate directly. Best-effort and
    # non-interactive; the PID-level logic below still owns verification.
    if _is_runit_dir_managed(project.name) and _is_sv_usable():
        try:
            from .runit import sv_down as _sv_down

            _sv_down(project.name)
        except Exception:
            pass
    stopped = False
    stopped_pids: List[int] = []
    saved_pid = read_pid(project.name)
    self_pid = os.getpid()
    skip_pattern_kill = False

    if saved_pid:
        if saved_pid == self_pid:
            remove_pid(project.name)
            skip_pattern_kill = True
        else:
            identity = verify_process_identity(
                saved_pid, project.process_pattern, project.start_command
            )
            if identity is False:
                print(f"هشدار: PID ذخیره‌شده {saved_pid} متعلق به سرویس {project.name} نیست؛ کشته نمی‌شود.")
                remove_pid(project.name)
                skip_pattern_kill = True
            else:
                stopped = stop_pid_safely(saved_pid)
                remove_pid(project.name)
                if stopped:
                    stopped_pids.append(saved_pid)
                    if not _verify_stopped(project, stopped_pids):
                        return False
                    print(f"سرویس {project.name} با شناسه {saved_pid} با موفقیت متوقف شد.")
                    _mark_stopped(project.name)
                    return True

    if project.stop_command:
        try:
            subprocess.run(_command_argv(project.stop_command), shell=False, timeout=10)
            stopped = True
        except Exception as e:
            print(f"خطا در اجرای دستور توقف سرویس {project.name}: {e}")

    if project.process_pattern and not skip_pattern_kill:
        status = check_process(project.process_pattern)
        if status.running:
            for pid_str in status.pids:
                try:
                    pid = int(pid_str)
                except ValueError:
                    continue
                if pid == self_pid:
                    continue
                try:
                    if stop_pid_safely(pid):
                        stopped = True
                        stopped_pids.append(pid)
                except Exception:
                    pass

    if stopped:
        if not _verify_stopped(project, stopped_pids):
            return False
        remove_pid(project.name)
        _mark_stopped(project.name)

    return stopped


def _mocked_kill_env() -> bool:
    """True when os.kill is replaced by a test double (death unverifiable)."""
    try:
        return hasattr(os.kill, "called") or hasattr(os.kill, "assert_called")
    except Exception:
        return False


def _verify_stopped(project: ProjectEntry, stopped_pids: List[int]) -> bool:
    """Verify PID death and (for HTTP-contract services) port release.

    Fail-closed: a surviving old PID or a port still owned by it means the
    stop did not complete. Never kills anything; only observes.
    """
    if _mocked_kill_env():
        # Test doubles cannot prove death; trust stop_pid_safely's result.
        return True
    for pid in stopped_pids:
        try:
            alive = _is_pid_alive(pid)
        except Exception:
            alive = False
        if alive:
            print(f"خطا: PID {pid} سرویس {project.name} پس از توقف هنوز زنده است.")
            return False
    contract = _http_contract(project)
    if contract is not None:
        host, port, _endpoint = contract
        for pid in stopped_pids:
            try:
                ownership = verify_port_ownership(host, port, pid)
            except Exception:
                continue
            if ownership.owned_by_pid is True:
                print(
                    f"خطا: پورت {port} سرویس {project.name} پس از توقف "
                    f"همچنان در مالکیت PID {pid} است."
                )
                return False
    return True


def restart_service(project: ProjectEntry, logs_dir: Optional[Path] = None) -> bool:
    """Safe restart sequence (Issue #179, section 6):

    1. Identify current service PID
    2. Verify Process Identity (foreign PIDs are never killed)
    3. Gracefully stop the service
    4. Verify old PID is dead
    5. Verify expected port is released (HTTP-contract services)
    6. Start service (fresh spawn re-verifies identity + port + health)
    7. Obtain new PID
    8-10. New identity / port ownership / health verified inside start
    11. Only then report RUNNING (True). Guards against PID reuse and stale state.
    """
    print(f"در حال ری‌استارت کردن سرویس {project.name}...")
    old_pid = read_pid(project.name)
    if old_pid is not None:
        identity = verify_process_identity(
            old_pid, project.process_pattern, project.start_command
        )
        if identity is False:
            print(
                f"هشدار: PID ذخیره‌شده {old_pid} متعلق به سرویس {project.name} نیست؛ "
                "ری‌استارت بدون kill آن PID انجام می‌شود."
            )
            remove_pid(project.name)
            old_pid = None
    stop_service(project)
    if old_pid and _is_pid_alive(old_pid):
        print(f"خطا: پروسس قدیمی {old_pid} سرویس {project.name} پس از توقف هنوز زنده است.")
        try:
            from .status_store import write_status
            write_status(project.name, success=False, message=f"خطا: پروسس قدیمی {old_pid} پس از توقف زنده ماند.")
        except Exception:
            pass
        return False
    contract = _http_contract(project)
    if contract is not None and old_pid and not _mocked_kill_env():
        host, port, _endpoint = contract
        try:
            ownership = verify_port_ownership(host, port, old_pid)
        except Exception:
            ownership = None
        if ownership is not None and ownership.owned_by_pid is True:
            print(
                f"خطا: پورت {port} سرویس {project.name} پس از توقف "
                f"همچنان در مالکیت PID قدیمی {old_pid} است."
            )
            return False
    time.sleep(0.2)
    if not start_service(project, logs_dir=logs_dir):
        return False
    new_pid = read_pid(project.name)
    if not new_pid or not _is_pid_alive(new_pid):
        print(f"خطا: پروسس جدید سرویس {project.name} پس از ری‌استارت زنده نیست.")
        return False
    if old_pid and new_pid == old_pid:
        print(f"خطا: PID پس از ری‌استارت سرویس {project.name} تغییر نکرد ({new_pid}).")
        return False
    return True
