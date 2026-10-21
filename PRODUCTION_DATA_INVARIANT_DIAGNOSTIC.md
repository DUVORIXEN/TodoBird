# PRODUCTION DATA INVARIANT DIAGNOSTIC REPORT

## 1. Executive Summary & Audit Metadata
- **Audit Purpose**: Forensic read-only diagnostic of production database execution states against Todo Bird frozen execution semantics.
- **Audit Execution Date**: 2026-09-18
- **Database Inspected**: `todo_bird_app/data/todo_bird.db`
- **Access Protocol**: Pure read-only SQLite URI mode (`file:/.../todo_bird.db?mode=ro`, `uri=True`).
- **Operational Safety**: Zero writes, zero mutations, zero CLI WAL interactions, zero schema migrations performed.
- **Diagnostic Outcome**: Out of 10 production task records, **4 are consistent** and **6 contain definite state contradictions** requiring human resolution.

---

## 2. Cryptographic Integrity & Database Health
Cryptographic verification confirms zero byte mutations occurred during the audit:

| Metric | Before Diagnostic | After Diagnostic | Integrity Status |
| :--- | :--- | :--- | :--- |
| **Main DB SHA-256** | `1057930f3cf85c99c580609784361df379339db590bc4ba1dbc87f67ae9d4514` | `1057930f3cf85c99c580609784361df379339db590bc4ba1dbc87f67ae9d4514` | **IDENTICAL / UNCHANGED** |
| **Main DB File Size** | 335,872 bytes | 335,872 bytes | **MATCH** |
| **WAL File Size** (`todo_bird.db-wal`) | 2,698,632 bytes | 2,698,632 bytes | **MATCH** |
| **SHM File Size** (`todo_bird.db-shm`) | 32,768 bytes | 32,768 bytes | **MATCH** |

---

## 3. Frozen Execution Semantics & Rules Applied
The diagnostic strictly audited records against the canonical authorities in `ExecutionPerformanceService` and Phase-2E state invariants:
- **State A — NOT TRACKED (`Planned` / `Inbox`)**:
  - No Actual bar rendered.
  - No fabricated or provisional actual timestamps (`actual_start_date` = `NULL`, `actual_end_date` = `NULL`).
- **State B — IN PROGRESS (`In Progress` / Active Execution)**:
  - Requires explicit factual `actual_start_date`.
  - `actual_end_date` must be strictly `NULL`.
  - Actual elapsed calendar time = `current_time − actual_start`.
- **State C — FINISHED (`Completed`)**:
  - Explicit factual `actual_start_date`.
  - Explicit factual `actual_end_date` (`actual_end >= actual_start`).
- **Invariant Rules**:
  1. Never infer Actuals from planned/due dates.
  2. Never infer progress from effort or vice-versa.
  3. Never rewrite Actuals from schedule forecast or CPM calculations.
  4. Work cannot be `Planned` if factual execution start has occurred.
  5. Work cannot be `In Progress` if factual execution finish is recorded.
  6. Stalled or paused execution (`Delayed` / `Blocked`) cannot carry a finished Actual state while remaining an active, uncompleted task.

---

## 4. Production Task Inventory & Classification Summary
- **Total Tasks Inspected**: 10
- **Consistent**: 4 (Tasks 6, 8, 9, 10)
- **Possible Contradictions**: 0
- **Definite Contradictions**: 6 (Tasks 2, 7, 11, 12, 13, 14)
- **Insufficient Evidence**: 0

---

## 5. Task-by-Task Decision Table

| Task ID | Title | Current Status | Actual Start | Actual Finish | Classification | Why | Possible Interpretation A | Possible Interpretation B | User Decision Needed |
| :---: | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **2** | OmmLVVN | `Delayed` | `2026-08-13 09:00` | `2026-08-29 21:45` | **DEFINITE CONTRADICTION** | Status is `Delayed` (active, 61% progress) but has finished execution timestamps (`actual_finish` matches planned due date). | Task work concluded or ended on 2026-08-29; status was not updated to Completed. | Task remains delayed/incomplete at 61% progress; `actual_finish` was populated erroneously (cloned from due date). | Confirm if task is finished (change to `Completed`) or active/delayed (clear `actual_finish`). |
| **6** | OmmLaxmiVignaVinashakaya Namaha | `In Progress` | `2026-08-12 05:53` | *None* | **CONSISTENT** | State B valid: explicit actual start recorded, actual finish is NULL, active progress (43%). | N/A (Consistent) | N/A (Consistent) | None required. |
| **7** | Success | `In Progress` | `2026-08-25 09:10` | `2026-08-25 13:00` | **DEFINITE CONTRADICTION** | Status is `In Progress` but carries a persisted `actual_finish` timestamp (violates State B). | Task actually finished on 2026-08-25 13:00; status was never transitioned to Completed. | Task is still active / in progress (progress is 59%); `actual_finish` was checked/entered prematurely. | Confirm if task is finished (change to `Completed`) or still active (clear `actual_finish`). |
| **8** | Win | `Delayed` | `2026-08-13 06:11` | *None* | **CONSISTENT** | Legitimate execution history: work began on 2026-08-13, actual finish is NULL, execution is actively delayed. | N/A (Consistent) | N/A (Consistent) | None required. |
| **9** | Start | `In Progress` | `2026-08-23 08:00` | *None* | **CONSISTENT** | State B valid: explicit actual start recorded, actual finish is NULL, active progress (39%). | N/A (Consistent) | N/A (Consistent) | None required. |
| **10** | Planning | `In Progress` | `2026-08-23 08:00` | *None* | **CONSISTENT** | State B valid: explicit actual start recorded, actual finish is NULL, active progress (10%). | N/A (Consistent) | N/A (Consistent) | None required. |
| **11** | Progress | `Planned` | `2026-08-23 08:00` | *None* | **DEFINITE CONTRADICTION** | Status is `Planned` (unstarted, 0% progress) but has an explicit `actual_start` timestamp. | Task was started on 2026-08-23 08:00; status was left as Planned. | Task has not started yet (progress 0%, planned for 2026-08-24); `actual_start` was recorded unintentionally. | Confirm if task is started (change to `In Progress`) or not started (clear `actual_start`). |
| **12** | Success | `Planned` | `2026-08-23 08:00` | *None* | **DEFINITE CONTRADICTION** | Status is `Planned` (unstarted, 0% progress) but has an explicit `actual_start` timestamp. | Task was started on 2026-08-23 08:00; status was left as Planned. | Task has not started yet (progress 0%, planned for 2026-08-25); `actual_start` was recorded unintentionally. | Confirm if task is started (change to `In Progress`) or not started (clear `actual_start`). |
| **13** | Foundation | `In Progress` | *None* | *None* | **DEFINITE CONTRADICTION** | Status is `In Progress` but lacks `actual_start_date`. State B elapsed time cannot be computed. Subtasks are all Planned (0%). | Work actually started, but actual start timestamp was omitted. | Work has not started (0% progress, subtasks unstarted); status was erroneously marked `In Progress`. | Confirm if task is active (provide factual `actual_start`) or unstarted (revert status to `Planned`). |
| **14** | Foundation | `In Progress` | *None* | *None* | **DEFINITE CONTRADICTION** | Status is `In Progress` but lacks `actual_start_date`. State B elapsed time cannot be computed. Subtasks are all Planned (0%). | Work actually started, but actual start timestamp was omitted. | Work has not started (0% progress, subtasks unstarted); status was erroneously marked `In Progress`. | Confirm if task is active (provide factual `actual_start`) or unstarted (revert status to `Planned`). |

---

## 6. Detailed Record Audit & Forensic Evidence

### Task 2 (`OmmLVVN`)
- **Project**: 3 (`DUVORIXEN TEST`)
- **Fields**: `status='Delayed'`, `progress=61`, `actual_start='2026-08-13 09:00'`, `actual_end='2026-08-29 21:45'`, `due_date='2026-08-29'`, `updated_at='2026-08-23 09:32:24'`.
- **Forensic Observation**: The task record was last updated on August 23, but its `actual_end` is stamped as August 29 21:45 (matching the `due_date`). An active delayed status conflicts with a closed State C execution interval.

### Task 7 (`Success`)
- **Project**: 3 (`DUVORIXEN TEST`)
- **Fields**: `status='In Progress'`, `progress=59`, `actual_start='2026-08-25 09:10'`, `actual_end='2026-08-25 13:00'`, `planned_date='2026-08-25'`, `updated_at='2026-08-23 07:32:12'`.
- **Forensic Observation**: `ExecutionPerformanceService.validate_execution_state()` triggers `STATUS_IN_PROGRESS_BUT_FINISHED`. State B forbids non-null `actual_end`.

### Tasks 11 & 12 (`Progress` & `Success`)
- **Project**: 4 (`THAAVORIX`)
- **Fields**: `status='Planned'`, `progress=0`, `actual_start='2026-08-23 08:00'`, `actual_end=None`, planned dates are 2026-08-24 (Task 11) and 2026-08-25 (Task 12).
- **Forensic Observation**: Both tasks have identical actual start timestamps (`2026-08-23 08:00`), identical update timestamps (`2026-08-26 01:09`), and 0% progress. Under State A, unstarted planned tasks must not carry actual timestamps.

### Tasks 13 & 14 (`Foundation`)
- **Project**: 5 (`SCHEDULING WITNESS FRESH`) & 6 (`SCHEDULING WITNESS FINAL`)
- **Fields**: `status='In Progress'`, `progress=0`, `actual_start=None`, `actual_end=None`.
- **Forensic Observation**: Under frozen State B semantics, `actual_start` is the foundational anchor for elapsed time calculation (`now - actual_start`). Without it, runtime analytics, Gantt actual bars, and CPM tracking cannot function.

---

## 7. Subtask & Related Table Forensic Evidence
Inspection of the `subtasks` table revealed that subtasks mirror several parent task contradictions:
- **Task 2 Subtasks**:
  - Subtask 7 (`I am Lucky`): `status='Planned'`, `progress=59%`, `actual_start='2026-08-13'`, `actual_end='2026-08-15'`.
  - Subtask 8 (`I am Perfect`): `status='Planned'`, `progress=90%`, `actual_start='2026-08-13'`, `actual_end='2026-08-20'`.
  - Subtask 9 (`Testing`): `status='Planned'`, `progress=82%`, `actual_start='2026-08-13'`, `actual_end='2026-08-15'`.
  - *Finding*: Subtasks are marked `Planned` despite having both actual start and actual finish dates recorded.
- **Task 13 Subtasks**: Subtasks 12 (`Excavation`) & 13 (`Reinforcement`) are `Planned`, 0% progress, actuals `NULL`.
- **Task 14 Subtasks**: Subtasks 14 (`Excavation Final`) & 15 (`Reinforcement Final`) are `Planned`, 0% progress, actuals `NULL`.
- **Task Allocations**: Task 2 has 6 allocation records and Task 7 has 4 allocation records in `task_allocations`.

---

## 8. User Decision Plan (Definite Contradictions)

For each affected record, two distinct, non-destructive resolution paths are presented. No choice is made automatically.

### Task 2 (`OmmLVVN`)
- **Current State**: `status='Delayed'`, `progress=61%`, `actual_start='2026-08-13 09:00'`, `actual_end='2026-08-29 21:45'`.
- **Resolution Option A (Completed Work)**: If work actually finished on August 29:
  - Transition `status` → `Completed`.
  - Update `progress` → `100`.
- **Resolution Option B (Active Delayed Work)**: If work was stalled and is not finished:
  - Retain `status` → `Delayed`.
  - Clear `actual_end_date` → `NULL`, `actual_end_time` → `NULL`.

### Task 7 (`Success`)
- **Current State**: `status='In Progress'`, `progress=59%`, `actual_start='2026-08-25 09:10'`, `actual_end='2026-08-25 13:00'`.
- **Resolution Option A (Completed Work)**: If work finished on 2026-08-25 at 13:00:
  - Transition `status` → `Completed`.
  - Update `progress` → `100`.
- **Resolution Option B (Active In-Progress Work)**: If work is ongoing:
  - Retain `status` → `In Progress`.
  - Clear `actual_end_date` → `NULL`, `actual_end_time` → `NULL`.

### Task 11 (`Progress`)
- **Current State**: `status='Planned'`, `progress=0%`, `actual_start='2026-08-23 08:00'`, `actual_end=None`.
- **Resolution Option A (Work Has Started)**: If work actually commenced on August 23:
  - Transition `status` → `In Progress`.
- **Resolution Option B (Work Is Unstarted)**: If work has not started:
  - Retain `status` → `Planned`.
  - Clear `actual_start_date` → `NULL`, `actual_start_time` → `NULL`.

### Task 12 (`Success`)
- **Current State**: `status='Planned'`, `progress=0%`, `actual_start='2026-08-23 08:00'`, `actual_end=None`.
- **Resolution Option A (Work Has Started)**: If work actually commenced on August 23:
  - Transition `status` → `In Progress`.
- **Resolution Option B (Work Is Unstarted)**: If work has not started:
  - Retain `status` → `Planned`.
  - Clear `actual_start_date` → `NULL`, `actual_start_time` → `NULL`.

### Task 13 (`Foundation`)
- **Current State**: `status='In Progress'`, `progress=0%`, `actual_start=None`, `actual_end=None`.
- **Resolution Option A (Work Has Started)**: If work is active:
  - Supply factual `actual_start_date` and `actual_start_time`.
- **Resolution Option B (Work Is Unstarted)**: If work has not started:
  - Revert `status` → `Planned`.

### Task 14 (`Foundation`)
- **Current State**: `status='In Progress'`, `progress=0%`, `actual_start=None`, `actual_end=None`.
- **Resolution Option A (Work Has Started)**: If work is active:
  - Supply factual `actual_start_date` and `actual_start_time`.
- **Resolution Option B (Work Is Unstarted)**: If work has not started:
  - Revert `status` → `Planned`.

---

## 9. Data-Migration Preview: Option A (Status Harmonization)
### `PREVIEW ONLY — NOT EXECUTED`

Under Option A, task statuses are updated to reflect the presence of actual timestamps (assuming timestamps represent ground truth):

```sql
-- PREVIEW ONLY — NOT EXECUTED
-- Option A: Status Harmonization
BEGIN TRANSACTION;

-- Task 2: Harmonize to Completed based on populated actual_end
UPDATE tasks 
SET status = 'Completed', progress = 100, updated_at = CURRENT_TIMESTAMP 
WHERE id = 2;

-- Task 7: Harmonize to Completed based on populated actual_end
UPDATE tasks 
SET status = 'Completed', progress = 100, updated_at = CURRENT_TIMESTAMP 
WHERE id = 7;

-- Tasks 11 & 12: Harmonize to In Progress based on populated actual_start
UPDATE tasks 
SET status = 'In Progress', updated_at = CURRENT_TIMESTAMP 
WHERE id IN (11, 12);

-- Tasks 13 & 14: Require explicit human input for actual_start before execution
-- (Cannot auto-populate without fabricating timestamps)

COMMIT;
```

---

## 10. Data-Migration Preview: Option B (Actuals Normalization)
### `PREVIEW ONLY — NOT EXECUTED`

Under Option B, spurious actual timestamps are cleared to honor the current lifecycle status and 0% progress markers:

```sql
-- PREVIEW ONLY — NOT EXECUTED
-- Option B: Actuals Normalization
BEGIN TRANSACTION;

-- Task 2: Keep Delayed, clear premature actual_finish
UPDATE tasks 
SET actual_end_date = NULL, actual_end_time = NULL, updated_at = CURRENT_TIMESTAMP 
WHERE id = 2;

-- Task 7: Keep In Progress, clear premature actual_finish
UPDATE tasks 
SET actual_end_date = NULL, actual_end_time = NULL, updated_at = CURRENT_TIMESTAMP 
WHERE id = 7;

-- Tasks 11 & 12: Keep Planned, clear spurious actual_start
UPDATE tasks 
SET actual_start_date = NULL, actual_start_time = NULL, updated_at = CURRENT_TIMESTAMP 
WHERE id IN (11, 12);

-- Tasks 13 & 14: Revert status to Planned (matching 0% progress and unstarted subtasks)
UPDATE tasks 
SET status = 'Planned', updated_at = CURRENT_TIMESTAMP 
WHERE id IN (13, 14);

COMMIT;
```

---

## 11. Test Coverage Gap Analysis
An audit of existing tests in `todo_bird_app/tests/` revealed the following coverage characteristics and gaps:
1. **Domain Service Coverage**:
   - `test_actual_execution_state_authority.py` extensively verifies `ExecutionPerformanceService` anomaly detection for `ACTUAL_FINISH_WITHOUT_START`, `ACTUAL_FINISH_BEFORE_START`, and `STATUS_IN_PROGRESS_BUT_FINISHED`.
2. **Identified Invariant Gaps**:
   - **Gap 1**: `ExecutionPerformanceService.validate_execution_state()` does not currently define codes for:
     - `STATUS_PLANNED_WITH_ACTUAL_START` (`Planned` with non-null `actual_start_date`).
     - `STATUS_IN_PROGRESS_WITHOUT_ACTUAL_START` (`In Progress` with null `actual_start_date`).
     - `STATUS_DELAYED_WITH_ACTUAL_FINISH` (`Delayed` with non-null `actual_end_date`).
   - **Gap 2 (Database Layer)**:
     - Neither `DatabaseManager.insert_task()` nor `DatabaseManager.update_task()` validates execution state invariants before writing to SQLite.
   - **Gap 3 (TaskDialog UI Layer)**:
     - `TaskDialog.on_save()` checks if `actual_start > actual_end`, but allows saving a task with `status = 'In Progress'` and `actual_finish_check` checked, or `status = 'Planned'` with `actual_enabled_check` checked.

---

## 12. Recommended Invariant Tests & DB Enforcement
*(To be implemented only in subsequent implementation phases, not in this diagnostic phase)*:
1. **Targeted Service Tests**:
   - Add unit test: `test_reject_planned_task_with_actual_start()`.
   - Add unit test: `test_reject_in_progress_task_without_actual_start()`.
   - Add unit test: `test_reject_delayed_task_with_actual_finish()`.
2. **Repository Guard Hook**:
   - Integrate an invariant pre-save check inside `DatabaseManager.update_task()` and `insert_task()` to prevent invalid execution states from being persisted.
3. **UI Dialog Constraint**:
   - Update `TaskDialog.on_save()` to enforce alignment between the selected status and the actuals tracking checkboxes prior to saving.

---

## 13. Final Classification
`todo_bird_production_data_invariant_diagnostic_complete_human_decision_required`
