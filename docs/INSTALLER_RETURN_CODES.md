# TODO BIRD Windows Installer Return Codes

This document defines the exit and return code values for the TODO BIRD Windows setup installer (`TodoBird-Setup-*.exe`), compiled with Inno Setup.

---

### Standard Installation Scenarios and Return Codes

| Scenario | Return Code | Description |
| :--- | :---: | :--- |
| **Installation successful** | `0` | The installation completed successfully without errors. |
| **Installation cancelled by user** | `2` | The installation was cancelled by the user before or during file copying. |
| **Application already exists** | `1638` | An existing version of TODO BIRD is already present on the system. |
| **Installation already in progress** | `1618` | Another installation process is currently running on the system. |
| **Disk space is full** | `112` | Insufficient disk space to complete file extraction and installation. |
| **Reboot required** | `3010` | Installation completed, but requires a system restart (not typical for Todo Bird). |
| **Network failure** | `12029` | Network connection failure occurred during the operation. |
| **Package rejected during installation** | `1625` | Installation was blocked by system group policy or security settings. |
| **Miscellaneous install failure** | `1` | General unclassified initialization or runtime error. |

---

### Silent Installation Parameters

- **Silent Install:** `TodoBird-Setup-1.0.1.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART`
- **Silent Uninstall:** `unins000.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART`

For further details regarding Inno Setup parameters, see the [Inno Setup Command-line Parameters Documentation](https://jrsoftware.org/ishelp/index.php?topic=setupcmdline).
