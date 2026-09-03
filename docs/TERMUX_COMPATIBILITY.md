# Termux / Android ARM64 Compatibility Contract

Issue #190 — Canonical Compatibility Contract for Termux / Android ARM64.

## Overview

Termux on Android ARM64 is a **first-class production target** across the Yasin ecosystem.
This document establishes the architecture, native build rules, cryptography guarantees, and runtime assumptions required for running YasinHub and integrated ecosystem components on Android ARM64.

---

## Target Reference Environment

- **Operating System:** Android 11+ (API Level 30+)
- **Architecture:** ARM64 (`aarch64`)
- **Runtime Environment:** Termux (`/data/data/com.termux/files/usr`)
- **Python Compatibility:** Python 3.9.x through Python 3.14.x (Reference: Python 3.14.6)
- **Process Supervision:** `termux-services` (`runit`)

---

## Native Build & ABI Contract

When building native extensions, C libraries, or Rust/PyO3 components in a Termux environment:

1. **Android API Level Export:**
   `ANDROID_API_LEVEL=30` must be exported prior to compiling native extensions or invoking `pip install`.
2. **Compiler Flags:**
   `CFLAGS` and `LDFLAGS` must target Android API level 30 ABI conventions to prevent missing symbol errors or link failures against Bionic libc (`libc.so`).
3. **PyO3 / Rust Compilations:**
   When compiling PyO3 bindings for Python 3.14+ on Android ARM64, `PYO3_CROSS_PYTHON_VERSION` or standard environment flags must specify Python 3.14 compatibility without disabling type safety or ABI checks.

---

## Cryptography & Security Invariants

1. **No Cryptography Disabling or Weakening:**
   Security controls, TLS certificate verifications, HMAC signature checks, and secret redaction are **never bypassed** or disabled for Termux.
2. **Standard Library Cryptography:**
   Python standard library modules (`ssl`, `hashlib`, `hmac`, `urllib.request`) are leveraged directly for transport security and hash operations, ensuring full functional compatibility on Android ARM64 without requiring broken external binary wheels.
3. **Secret Redaction:**
   All secrets (API keys, authorization tokens, bearer headers) are redacted from logs and error payloads in all environments.

---

## Service Management & Process Supervision

- **Supervisor:** `termux-services` powered by `runit` (`sv`).
- **PID Store:** Process PIDs are tracked under `~/.yasinhub/pids/` with signal-zero verification and zombie process reaping (`os.waitpid`).
- **Process Checkers:** Process detection relies on `pgrep -f` patterns or socket/HTTP availability checks, fully compatible with Termux process isolation rules.

---

## Known Limitations & Considerations

1. **Background Execution:** Android battery optimization may terminate background processes if Termux is placed into deep sleep without wake-locks (`termux-wake-lock`).
2. **Systemd Absence:** Termux does not use `systemd`. Production services rely on `termux-services` (`runit`).
3. **Shared Storage Permissions:** Access to `/sdcard` requires running `termux-setup-storage`.

---

## Bootstrap & Verification

To install and verify in a Termux environment:

```bash
bash scripts/install_termux.sh
```

Verification validates Python version, `yasin-hub` package installation, standard library cryptography, and CLI execution.
