# FINAL-G3 — Hub Status-Only vs Control-Plane Decision

**Issue:** YasinHub #45  
**Date:** 2026-08-16  
**Related:** #31, #41, FINAL-09 (#43)

## Decision

**STATUS-ONLY (with optional local lifecycle helpers).**

YasinHub remains a status / lifecycle observer CLI + dashboard. It does **not** become the ecosystem control plane under this gate.

## Evidence

| Claim | Reality |
|-------|---------|
| README | Status CLI (“نه یک داشبورد سنگین”) |
| Implementation | status_store, report, pid_store, optional start/stop |
| Tests | 110 passed — status/lifecycle focus |
| Control-plane product | **Not implemented** |

## Overclaim fixes in this Issue

- `pyproject.toml` description no longer says “control-plane / orchestration hub”
- `AUDIT_REPORT.md` aligned with status-plane role

## Dispositions

| Issue | Disposition |
|-------|-------------|
| #31 YasinRelay Production Activation | **NOT PLANNED** for Hub status-plane — live Relay ops are product work outside Hub’s declared role |
| #41 Complete Ecosystem Integration Control Plane | **NOT PLANNED** under current architecture — would need a new product-approved implementation Issue with contracts/security/CI scope |
| #45 FINAL-G3 | **DONE** — decision recorded; docs reconciled |

## Acceptance

| Criterion | Status |
|-----------|--------|
| Explicit architecture decision | Status-only |
| Implementation ↔ public claims consistent | Yes |
| No false “already a control plane” claim | Yes |
| No unrelated feature work | Yes |
