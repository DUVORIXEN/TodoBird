# Todo Bird: Cross-Platform Support Matrix

This document establishes the explicit platform compatibility and validation targets for Todo Bird, ensuring stable support across modern operating systems while maintaining the core Qt 6.11/PySide6 stack without introducing fragmented legacy code paths.

## Linux Support Policy

### Supported Platforms
*   **Minimum Supported Ubuntu:** Ubuntu 22.04 LTS x86_64
*   **Primary Validation Targets:** Ubuntu 22.04 LTS, Ubuntu 24.04 LTS, Ubuntu 26.04 LTS

### Technical Requirements
*   **Qt Compatibility:** The application uses Qt 6.11/PySide6. Linux binaries require **glibc 2.34-class compatibility** or higher.
*   The production baseline must remain compatible with the current modern Qt stack. 

### Unsupported / Legacy Platforms
*   **Ubuntu 20.04 and 18.04** are explicitly classified as legacy/unsupported for the current Qt 6.11/PySide6 build.
*   **Do not claim support for Ubuntu 18.04.**
*   **Do not downgrade Qt/PySide6** merely to support Ubuntu 18.04 or older distributions.
*   **Do not introduce a second legacy Qt code path** to bypass these requirements.

---

## Windows Support Policy

### Supported Platforms
*   **Minimum Supported:** Windows 10 1809 x64
*   **Primary Validation Targets:** Windows 10 22H2 x64 and Windows 11 x64

### Architecture Readiness
*   **Windows 11 ARM64:** Architecture readiness is preserved where Qt supports it. However, we do not claim official validation or support without native testing.

### Portability Guidelines
*   **Cross-Platform Parity:** Do not introduce Linux-only or Windows-only imports directly into portable application modules (e.g., standard views, models, and core services).
*   All platform-specific functionality (such as window management, desktop integration, audio, or DBus) must be wrapped behind standard adapter interfaces (e.g., `LinuxPlatformService`, `WindowsPlatformService`).

---

## macOS Support Policy

### Supported Platforms
*   **Minimum Supported:** macOS 13 Ventura (Intel and Apple Silicon)
*   **Primary Validation Targets:** macOS 13, macOS 14, macOS 15

### Technical Notes
*   The application resolves per-OS data locations through the path resolver
    (`~/Library/Application Support` on macOS) and routes window management
    through `MacOSPlatformService`.
*   Menu-bar integration uses native Qt menus; autostart, where enabled, is
    provided by a LaunchAgent.

## ChromeOS Support Policy

### Supported Platforms
*   **Delivery Channel:** Linux (Crostini) runtime on Chromebooks with the
    Linux development environment enabled.
*   **Requirement:** The device must support Crostini and provide a current
    glibc (2.34-class) userland, matching the Linux support policy.

### Technical Notes
*   Todo Bird runs as a desktop Linux application inside Crostini; no
    separate Android runtime is required or provided.

## Mobile Platforms (Android / iOS / iPadOS)

*   **Not supported by this codebase.** Todo Bird is a Qt 6 / PySide6 desktop
    application; Qt for Python does not provide production Android or iOS
    targets. A mobile companion would be a separate native project that
    reuses the planning core (models, services, controllers) which is kept
    free of GUI imports by design.

## Final Validation Metrics (Isolated Regression Suite)

A full run of the isolated regression suite (`python3 tools/run_isolated_pytest.py`) was conducted to validate cross-platform readiness, path portability, and startup identity integrity. 

*   **Total Test Files Executed:** 138
*   **Total Tests Passed:** 3229
*   **Tests Failed:** 0
*   **Tests Skipped:** 0
*   **Peak RSS:** 536,876 KB
*   **Final Summary JSON Path:** `build/test_reports/isolated_pytest_summary.json`
