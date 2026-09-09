# PWA BROWSER VERIFICATION REPORT

HEAD: fe0c4ef6849332b17a5d0ccd024580263be7c7a1 (main)

## Inspected

- `.github/workflows/` — only `ci.yml` (pytest on ubuntu-latest,
  Python 3.9–3.14-dev; zero browser steps, zero browser deps)
- Device binaries — `chromium/chromium-browser/google-chrome/chrome/firefox/
  headless_shell`: all absent; `/usr/lib/chromium` absent; `/opt` absent;
  `*chrom*` filesystem scan: nothing
- Python — no `playwright/pyppeteer/selenium` module (pip scan clean)
- Node/npm present but no browser packages globally; repo has no
  `package.json`, no playwright config, no browser scripts
- Repo-wide grep — only hits are the historical audit docs describing this
  same limitation, plus the runtime verification report
- Historical docs — `docs/audits/yasinhub-pwa-mobile-audit.md` already
  records "browser automation unavailable" and prescribes future
  Playwright/Chromium (6 viewports + scrollWidth assertions);
  `yasinhub-pwa-mobile-fix.md` confirms fixes were static-equivalent only

## Mobile contract vs CURRENT implementation (source-verified, not rendered)

- `@media(max-width:800px){.nav-toggle{display:none}.sidebar{display:none}}`
  + `.main{width:100%}` → mobile is full-width, no hamburger, no drawer,
  no sidebar at 390px — matches contract
- Sidebar contains only «نمای کلی»; «اجراها»/«ناوها»/«رویدادها» do not exist
  in DOM — matches contract (Observer-menu removal)
- Responsive tables (`responsive-cards`), `100dvh` with `100vh` fallback,
  skip-link rules present
- 96/96 PWA automated tests pass; full suite 559/559; Hub live on :7000

## Results

- Environment: Termux Android aarch64, Hub 127.0.0.1:7000
- Browser: NONE — NOT VERIFIED (desktop, mobile, console)
- Automation: NONE exists to run
- Desktop: NOT VERIFIED (server 200 + static DOM/CSS only)
- Mobile 390x844: NOT VERIFIED (contract matches source statically; no
  rendered measurement)
- Console: NOT VERIFIED (JS cannot execute here)
- Network: PASS server-side only (all dashboard assets HTTP 200, manifest
  valid, zero hardcoded ports, Hub-API-only wiring)
- Manifest: PASS (valid JSON, served 200)
- Service Worker: served 200; registration/execution NOT VERIFIED
- Responsive: NOT VERIFIED (execution)
- Screenshots: none (no tooling; none committed)
- Existing PWA automated tests: 96/96
- Full YasinHub suite: 559/559
- Code changes: NONE

## Minimal external environment required for final acceptance

Any Linux/macOS runner with Chromium (or `pip install playwright &&
playwright install chromium`) serving this repo's Hub on :7000, running:
desktop viewport load + console-error + failed-request capture, mobile
390x844 overflow assertion
(`scrollingElement.scrollWidth <= innerWidth`), SW registration check, and
two screenshots. The repo's CI (`ci.yml`) cannot do this today — it would
need a new `playwright`-based job.

## FINAL VERDICT — PASS_WITH_LIMITATION
