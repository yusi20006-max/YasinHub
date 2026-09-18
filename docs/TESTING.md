# YasinHub Test Verification

## CI is authoritative

GitHub Actions runs the complete discovered pytest suite with the supported Python matrix:

- Python 3.9
- Python 3.10
- Python 3.11
- Python 3.12
- Python 3.13
- Python 3.14-dev

The CI command remains:

```text
python -m pytest -q
```

No tests are skipped, excluded, or conditionally removed by the Termux strategy.

## Normal local verification

From the repository root:

```text
python -m pytest -q
```

Use this when the device has sufficient memory and process capacity.

## Resource-constrained Termux verification

Use the repository runner when a full in-process pytest run has previously been terminated by Android/Termux resource pressure:

```text
bash scripts/test_termux_full.sh
```

The runner discovers every `tests/test_*.py` module, sorts them deterministically, and runs them in separate pytest processes. The default is one test module per process. This reduces peak process/test-state accumulation while preserving complete local coverage.

The runner never turns a failing test into a pass. It records assertion/test failures separately from process termination and exits non-zero if any batch fails.

For a faster device, batches can be increased explicitly:

```text
YASINHUB_TERMUX_BATCH_SIZE=2 bash scripts/test_termux_full.sh
```

Keep the default of `1` on memory-constrained devices.

A timestamped log is written to `termux-pytest.log` by default. Set `YASINHUB_TERMUX_LOG` to choose another path.

## Diagnosing signal 9

Exit status `137` means the pytest child exited after signal 9 (SIGKILL). This is process termination, not a pytest assertion result. On Android/Termux it should be investigated as a resource/environment event, especially memory pressure, process limits, or the OS killing a process.

The runner reports signal-based exits as `ENVIRONMENT TERMINATION` and continues with the remaining test modules, so other failures remain visible. If the runner itself is killed, inspect Android/Termux memory pressure and rerun with the default one-module batches; the log contains all completed batches.

Do not interpret a signal 9 termination as evidence that the underlying test assertion passed or failed. CI remains the authoritative complete-suite result.

## Resource-sensitive tests

The `resource_sensitive` pytest marker identifies tests that exercise real process/service lifecycle resources rather than only mocks. It is intentionally narrow and does not exclude these tests from either local verification or CI.

Currently marked modules include:

- `tests/test_final_ecosystem_e2e_acceptance.py`
- `tests/test_issue182_selfhealing_services.py`
- `tests/test_service_management_ops.py`
- `tests/test_yasinrelay_control_plane_e2e.py`

These tests start/stop/restart real child processes and/or exercise live loopback sockets, so they can create higher transient process and OS-resource pressure on constrained Android environments.

The marker is for identification and diagnostics only. CI still executes all marked tests as part of the complete suite.

## Coverage policy

This infrastructure change does not use `skip`, `xfail`, `ignore`, reduced CI matrices, or test deletion to make resource failures disappear. A full Termux run means every discovered test module is executed; any failed module makes the overall command fail.
