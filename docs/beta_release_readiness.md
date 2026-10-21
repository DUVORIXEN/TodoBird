# Todo Bird Beta Release Readiness Matrix

| Gate | Requirement | Implemented | Automated Evidence | Native Evidence | Human Evidence | Release Blocker | Notes |
|---|---|---|---|---|---|---|---|
| G1 | Functional Correctness | YES | Isolated Regression Suite | N/A | N/A | YES | 100% pass on 3313 tests. |
| G2 | Data Safety & Recovery | PARTIAL | Test Suite Pass | Pending | Pending | YES | Startup integrity checks & recovery UX required. |
| G3 | Performance & Long-Run Stability | YES | Beta Soak Test | Pending | Pending | YES | Automated 1k/5k/10k dataset loading script added. |
| G4 | Native Platform Readiness (Linux) | YES | Yes | Pending | Wayland/X11 Tested | YES | Window logic explicitly fixed for Wayland. |
| G4 | Native Platform Readiness (Win/Mac) | NO | N/A | Pending | Pending | YES | Awaiting user manual testing. |
| G5 | Install / Update / Uninstall | NO | N/A | N/A | N/A | NO | Postponed; user must rely on manual installs for now. |
| G6 | Trust, Privacy & Diagnostics | PARTIAL | Yes | N/A | N/A | NO | Support Bundle export required. |
| G7 | First-Run Experience | YES | Yes | N/A | Pending | NO | Clean identity; no DB pollution. |
| G8 | "Support Todo Bird ❤️" | PARTIAL | Yes | N/A | Pending | YES | Non-blocking support dialog with URL safe checking needed. |
