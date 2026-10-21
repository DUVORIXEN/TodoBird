# Dashboard Health Signal Authority

Generated: 2026-09-06

## Executive Summary
Complete forensic audit of S (Schedule), X (Execution), and R (Risk) health signals with transparent trigger-based rules.

---

## Signal Definitions

### S — Schedule Health
**Purpose**: Measures forecast schedule variance against approved baseline.
**Authority**: `DashboardDataService.build()` → CPM `finish_variance_days` vs baseline.

### X — Execution Health
**Purpose**: Measures overdue commitment burden and urgency.
**Authority**: `DashboardDataService.build()` → overdue task count + priority analysis.

### R — Risk Health
**Purpose**: Measures forward-looking schedule exposure and threat to future delivery.
**Authority**: `DashboardDataService.build()` → comprehensive risk trigger evaluation.

---

## Schedule Health (S) Rules

| Color | Trigger Condition | Reason Text |
|-------|-------------------|-------------|
| 🟢 GREEN | `finish_var_days is None OR finish_var_days <= 0` | "No baseline set — cannot evaluate schedule variance" OR "Forecast finish is X days vs baseline (on track)" |
| 🟡 YELLOW | `0 < finish_var_days <= 2.0` | "Forecast finish is +X days behind baseline (slip ≤2 days)" |
| 🔴 RED | `finish_var_days > 2.0` | "Forecast finish is +X days behind baseline (slip >2 days)" |

**Note**: Schedule variance is purely CPM forecast vs approved baseline. Does not double-count execution delays.

---

## Execution Health (X) Rules

| Color | Trigger Condition | Reason Text |
|-------|-------------------|-------------|
| 🟢 GREEN | `overdue_count == 0` | "No overdue commitments" |
| 🟡 YELLOW | `overdue_count <= 2 AND no urgent overdue` | "X overdue task(s) — no urgent priority" |
| 🔴 RED | `overdue_count > 2 OR any urgent overdue` | "X overdue task(s) including Y urgent" OR "X overdue task(s) — exceeds threshold" |

**Note**: Urgent = priority "urgent" or "high". Execution health is purely about overdue commitments.

---

## Risk Health (R) Rules — Comprehensive Forward-Looking Exposure

### Critical Triggers (→ RED)

| Trigger | Condition | Reason Text |
|---------|-----------|-------------|
| Negative Float | `negative_float_count > 0` | "X task(s) with negative total float (schedule infeasible)" |
| Dependency Cycles | `cycle_count > 0` | "X dependency cycle(s) detected" |
| Critical Path Blocked | `critical_blocked_count > 0` | "X critical path task(s) blocked" |
| Critical Path Delayed | `critical_delayed_count > 0` | "X critical path task(s) delayed" |
| Missed Hard Deadline | Any overdue task on critical path | "X critical task(s) missed hard deadline" |

### Warning Triggers (→ AMBER if no Critical)

| Trigger | Condition | Reason Text |
|---------|-----------|-------------|
| Blocked Tasks | `blocked_tasks > 0 AND no critical triggers` | "X task(s) blocked (avg blocker age: Y days)" — if ≤2 blocked<br>"X task(s) blocked (avg blocker age: Y days)" — if >2 blocked (becomes CRITICAL) |
| Delayed Tasks | `delayed_tasks > 0 AND no critical triggers` | "X task(s) delayed" — if ≤2 delayed<br>"X task(s) delayed" — if >2 delayed (becomes CRITICAL) |
| Near-Critical Tasks | `near_critical_count > 0 AND no critical triggers` | "X near-critical task(s) (float ≤1 day)" |
| Upcoming Critical Deadline with Thin Float | Critical task due ≤7 days with float <2 days | "X critical deadline(s) within 7 days with float <2 days" |
| High Blocker Ageing | `avg_blocker_age > 5 AND blocked_tasks > 0 AND no critical triggers` | "Blocker ageing high: X days average" |

### Green Condition
**No triggers active**: "No blocked, delayed-critical, negative-float, cycle, deadline, or constraint risk currently detected"

---

## Portfolio Health Aggregation

| Signal | Aggregation Method |
|--------|-------------------|
| S | Worst of active projects (Red > Yellow > Green) |
| X | Worst of active projects (Red > Yellow > Green) |
| R | Worst of active projects (Red > Yellow > Green) |

**Portfolio Risk Drill-Down**: When Portfolio R = RED, tooltip shows:
- Count of projects with critical schedule risk
- Top 3 projects with details (name, blocked count, critical count)

---

## Explainability Implementation

### Health Card Tooltip (Hover)
Shows color + summary reason per signal:
```
Project Health: GREEN
• Schedule (S): GREEN (Forecast finish is +0.0d vs baseline)
• Execution (X): YELLOW (2 overdue task(s) — no urgent priority)
• Risk (R): GREEN (No blocked, delayed-critical, negative-float, cycle, deadline, or constraint risk currently detected)
```

### Health Card Click Dialog
Shows detailed diagnostics per signal:
- **Schedule (S)**: Finish variance, baseline status, critical path count, near-critical count
- **Execution (X)**: Overdue count, due today, completed today, headroom
- **Risk (R)**: All active triggers with [CRITICAL]/[WARNING] prefix, blocked count, delayed count, dependency cycles, negative float, fidelity score

---

## Forensic Trace: Why R = GREEN in Live Witness

Given live data:
- `blocked_tasks = 0`
- `delayed_tasks = 0`
- `negative_float_count = 0`
- `cycle_count = 0`
- `critical_blocked_count = 0`
- `critical_delayed_count = 0`
- No overdue critical tasks
- `near_critical_count = 0`
- No upcoming critical deadlines with thin float
- `avg_blocker_age = 0` (no blocked tasks)

**Result**: No triggers active → R = GREEN ✓

**If R were YELLOW/RED**, the tooltip would show exactly which trigger(s) fired.

---

## Rule Independence Verification

| Signal Pair | Overlap Check | Status |
|-------------|---------------|--------|
| S vs X | S = baseline variance, X = overdue count | ✓ Independent |
| S vs R | S = baseline variance, R = forward exposure (cycles, float, blockers) | ✓ Independent |
| X vs R | X = overdue (past), R = blocked/critical/float (future threat) | ✓ Independent |

**No double-counting**: Schedule variance (S) does not feed Risk (R). Risk considers only forward-looking exposure that threatens future delivery beyond what S already captures.

---

## Threshold Documentation

| Threshold | Value | Rationale |
|-----------|-------|-----------|
| Schedule Yellow | >0 to ≤2 days | Minor slip, recoverable |
| Schedule Red | >2 days | Significant slip requiring intervention |
| Execution Yellow | 1-2 overdue, non-urgent | Manageable backlog |
| Execution Red | >2 overdue OR any urgent | Overwhelming or high-priority backlog |
| Risk Yellow | 1-2 blocked/delayed, near-critical, thin float | Warning-level exposure |
| Risk Red | Negative float, cycles, critical blocked/delayed, >2 blocked/delayed, missed critical deadline | Critical schedule threat |
| Near-Critical Float | ≤1 day (1440 min) | Standard CPM definition |
| Thin Float for Deadline | <2 days (2880 min) | Insufficient buffer for critical deadline |
| Blocker Age Warning | >5 days | Stale blocker requiring escalation |

---

## Authority
All health signals computed in **single pass** by `DashboardDataService.build()` — no duplicate computation, no external dependencies beyond CPM scheduling service.