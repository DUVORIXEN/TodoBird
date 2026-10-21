# TODO BIRD Windows Installer Return Codes

This document describes the exit and return code values for the TODO BIRD Windows setup installer (`TodoBird-Setup-*.exe`), compiled using Inno Setup.

---

### Exit / Return Codes Summary

| Return Code | Status | Meaning / Scenario |
| :---: | :--- | :--- |
| **0** | **Success** | Setup completed successfully without errors. |
| **1** | **Initialization Error** | Setup failed to initialize (e.g. unsupported operating system architecture). |
| **2** | **Cancelled** | The user cancelled the installation wizard before file copying began. |
| **3** | **Pre-Install Error** | A fatal error occurred while preparing the installation environment. |
| **4** | **Installation Error** | A fatal error occurred during the installation process (e.g. disk write failure). |
| **5** | **Aborted** | The user cancelled the installation process midway while files were being copied. |

---

### Silent Installation Switches

The installer supports standard silent and unattended installation commands for enterprise deployment and Microsoft Store distribution:

- **Silent Install:** `TodoBird-Setup-1.0.1.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART`
- **Silent Uninstall:** `unins000.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART`

For further details regarding Inno Setup installer exit codes, see the [Inno Setup Command-line Parameters Documentation](https://jrsoftware.org/ishelp/index.php?topic=setupcmdline).
