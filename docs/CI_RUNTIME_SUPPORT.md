# CI Runtime Support & Platform Matrix

YasinHub declares Python `>=3.9` and its test matrix covers Python 3.9 through 3.14 (`3.14-dev`).

## Environment Targets

1. **Linux x86_64 / ARM64:** Python 3.9, 3.10, 3.11, 3.12, 3.13, 3.14.x
2. **Termux on Android ARM64:**
   - **Android API Level:** 30+ (Android 11+)
   - **Architecture:** ARM64 (`aarch64`)
   - **Python:** Python 3.9 through Python 3.14.x (Reference: Python 3.14.6)
   - **Native Build Contract:** Export `ANDROID_API_LEVEL=30` and standard `CFLAGS` / `LDFLAGS` prior to building native binary extensions.

The CI matrix and Termux bootstrap installer are intentionally aligned with the package's declared runtime contract and do not use compatibility bypasses or cryptography weakenings.
