# Changelog

## 1.0.0

- Initial stable release of YasinHub
- Lightweight ecosystem status CLI
- JSON-based status store
- Process liveness checks
- Core, Agent, and Relay integration layers
- CLI status reporting
- Test coverage for config, dashboard, integrations, and E2E flows

## Unreleased

- #153: live/supervised process is authoritative over stale FAILED status_store records

- Hardening after #149: canonical token file wins over stale env; runit orphan
  reconciliation; portable logger fallback; Hub HTTP token file fallback
  (`yasinhub.agent_token`)

- #149: Production Termux/runit supervision for Yasin-Agent
  - scripts/termux/yasin-agent run + log scripts
  - install_yasin_agent_service.sh
  - docs/TERMUX_RUNIT_YASIN_AGENT.md
  - idempotent start when agent already supervised
  - regression tests for canonical path, token contract, single-instance

- Documentation and release-readiness cleanup
