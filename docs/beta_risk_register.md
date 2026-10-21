# Todo Bird Beta Risk Register

| ID | Area | Scenario | Severity | Likelihood | Detectability | Mitigation | Test | Owner | Status |
|---|---|---|---|---|---|---|---|---|---|
| R1 | Data Safety | DB corruption on start | CRITICAL | Low | High | Add startup `PRAGMA integrity_check` and safe restore flow | `test_db_startup_check` | Eng | OPEN |
| R2 | Migration | Migration failure loses data | CRITICAL | Medium | High | `BackupManager` creates pre-migration DB copy | `test_failed_migration` | Eng | MITIGATED |
| R3 | Performance | Gantt/Dashboard memory leak | HIGH | Medium | Medium | Soak test script automating 1k/10k task cycles | `beta_soak_test.py` | Eng | OPEN |
| R4 | Windowing | Wayland explicit ownership fail | HIGH | Low | Medium | Strict `parent=None` and Wayland offset guards | `test_batch310j` | Eng | MITIGATED |
| R5 | Security | Malicious Support URL injection | HIGH | Low | High | Hardcoded HTTPS validation for support service | `test_support_url_safe` | Eng | OPEN |
| R6 | UX | Annoying new users with support popup | MEDIUM | High | High | Implement 7-day or 30-task eligibility | `test_support_eligibility` | Eng | OPEN |
