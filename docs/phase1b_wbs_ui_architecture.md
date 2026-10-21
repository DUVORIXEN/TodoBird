# TODO BIRD — PHASE 1B WBS TREE UI ARCHITECTURE SPECIFICATION
**Target Visual & Interaction Benchmark**: Linear Precision + Notion Clarity + Todoist Simplicity + Microsoft Project Hierarchy Depth.

---

## 1. Executive Summary & Design Governance

Phase 1B introduces the visual Work Breakdown Structure (WBS) Tree View for Todo Bird. It transforms hierarchical execution planning into a seamless, keyboard-first, high-density desktop experience while building upon the canonical data authority established in Phase 1A (`WBSService`, `EntityRef`, and `WBSHierarchySnapshot`).

In accordance with `.agents/rules/ui_ux_engineering_standard.md`, Todo Bird will **never** instantiate thousands of nested `QWidget` objects or rely on default Qt widgets. Instead, Phase 1B uses a unified `QAbstractItemModel` + `QTreeView` + custom `QStyledItemDelegate` rendering pipeline that scales effortlessly to 10,000+ nodes at 60 FPS with sub-millisecond redraws.

---

## 2. Architecture & Data Model Contract

### 2.1 Model-View Architecture
```
┌────────────────────────────────────────────────────────┐
│                   DatabaseManager / SQLite             │
└───────────────────────────┬────────────────────────────┘
                            │ (2 Bulk Indexed Queries)
┌───────────────────────────▼────────────────────────────┐
│                    WBSService Authority                │
│             - WBSHierarchySnapshot (Immutable)         │
│             - Stable EntityRef (task:ID, subtask:ID)   │
│             - Derived WBS Codes (1, 1.1, 1.1.1)        │
└───────────────────────────┬────────────────────────────┘
                            │ (Zero DB queries in View)
┌───────────────────────────▼────────────────────────────┐
│                    WBSItemModel                        │
│             (subclass of QAbstractItemModel)           │
│             - Maps QModelIndex to WBSNode              │
│             - Custom Qt Item Data Roles                │
└───────────────────────────┬────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│                      QTreeView                         │
│             - QSplitter (WBS Tree ⟷ Gantt Sync)        │
│             - WBSItemDelegate (QStyledItemDelegate)    │
│             - Smooth Virtual Scrolling (Pixel-based)   │
└────────────────────────────────────────────────────────┘
```

### 2.2 Custom Qt Data Roles (`WBSItemModel`)
To decouple UI rendering from business logic, `WBSItemModel` exposes strongly-typed data roles:

| Role Constant | Value | Description | Example Output |
| :--- | :--- | :--- | :--- |
| `WBS_KEY_ROLE` | `Qt.UserRole + 1` | `EntityRef` of the item | `EntityRef('subtask', 42)` |
| `WBS_CODE_ROLE` | `Qt.UserRole + 2` | Derived WBS outline code | `"1.2.1"` |
| `WBS_DEPTH_ROLE` | `Qt.UserRole + 3` | Zero-based hierarchy depth | `2` |
| `WBS_IS_SUMMARY_ROLE` | `Qt.UserRole + 4` | True if node has children | `True` |
| `WBS_IS_MILESTONE_ROLE`| `Qt.UserRole + 5` | True if zero-duration / gate | `False` |
| `WBS_PROGRESS_ROLE` | `Qt.UserRole + 6` | Progress percentage (0–100) | `80` |
| `WBS_STATUS_ROLE` | `Qt.UserRole + 7` | Task execution status | `"In Progress"` |
| `WBS_EFFORT_ROLE` | `Qt.UserRole + 8` | Planned & actual effort string | `"6h planned • 4h actual"` |
| `WBS_SCHEDULE_ROLE` | `Qt.UserRole + 9` | Date/time schedule span | `"Aug 18 – Aug 22"` |
| `WBS_IS_PINNED_ROLE` | `Qt.UserRole + 10`| Pinning status & color | `(True, "#10B981")` |

---

## 3. Visual Language & Tree Layout

### 3.1 Hierarchy Row Anatomy
```
[Expander] [WBS Code] [Node Icon] [Title Text]                [Effort / Dates] [Progress Bar] [Status Pill]
   ▼          1.2        📁       Product Validation                                62%        In Progress
   ├─        1.2.1       📋       Wet Field Testing            4h • Aug 18          80%        Completed
   ├─        1.2.2       📋       Dry Field Testing            6h • Aug 20          55%        In Progress
   └─        1.2.3       ◆        Engineering Milestone Gate   Aug 22                0%        Planned
```

### 3.2 Indentation & Guide Lines
- **Base Indentation**: 20px per depth level (`depth * 20px`).
- **Tree Guide Lines**: 1px subtle dashed connectors (`rgba(255, 255, 255, 0.08)` in dark mode, `rgba(0, 0, 0, 0.08)` in light mode) drawn via delegate `paint()` to clearly visualize multi-level parent-child relationships.
- **Expander Chevrons**:
  - Expanded: `▼` 12px smooth geometric chevron with micro-rotation animation on click.
  - Collapsed: `▶` 12px chevron.
  - Leaf Node: Clean 4px guide dot or vertical branch terminator `├─` / `└─`.

---

## 4. Delegate Rendering Specifications (`WBSItemDelegate`)

### 4.1 Summary Task Visual Language (Parent Nodes)
- **Typography**: Semibold (`font-weight: 600`), 13px Inter / Roboto / System font.
- **Background**: Subtle glass highlight on hover (`rgba(255, 255, 255, 0.04)`).
- **Badge**: Summary badge displaying direct child count (`[3 subtasks]`).
- **Progress**: Weighted parent rollup progress pill (`62%`).

### 4.2 Standard Task Visual Language (Leaf Nodes)
- **Typography**: Regular (`font-weight: 400`), 13px typography.
- **Checklist Indicator**: Interactive 16px circular completion checkbox (single click toggles status).
- **Inline Metadata**: Dimmed secondary metadata pills (`rgba(255, 255, 255, 0.45)`) showing assigned dates or effort.

### 4.3 Milestone Visual Language (Gateways)
- **Icon**: Diamond glyph (`◆` / `⯁`) rendered with vibrant accent outline (`#E95420` or `#8B5CF6`).
- **Badge**: Distinctive `"Milestone"` or `"Gate"` badge.

### 4.4 High-Performance Progress Bar
- **Dimensions**: 60px width × 6px height capsule progress track.
- **Track**: `rgba(255, 255, 255, 0.08)`.
- **Fill**: Gradient from `#3B82F6` (Blue) to `#10B981` (Emerald) for completed tasks.
- **Text**: Monospace numeric percentage aligned to right.

---

## 5. Interaction, States & Accessibility

### 5.1 Interactive States
1. **Normal**: Clean, borderless rows with consistent vertical padding.
2. **Hover**: 150ms smooth fade to `rgba(255, 255, 255, 0.03)` with hover action buttons (Quick Edit, Add Child, Pin).
3. **Selected**: Crisp selection pill with 2px left accent border in primary color (`#E95420` / `#3584E4`).
4. **Keyboard Focus**: 1.5px subtle outline conforming to accessibility standards (`Qt.TabFocusReason`).

### 5.2 Keyboard Navigation Contract
- `Up` / `Down`: Move selection across visible flattened rows.
- `Right`: Expand collapsed branch / move to first child.
- `Left`: Collapse expanded branch / move to parent.
- `Space`: Toggle task completion checkbox.
- `Enter` / `Return`: Open Task Dialog for full editing.
- `Ctrl+N` / `Cmd+N`: Quick-add sibling task under current parent.
- `Tab` (in edit mode): Indent task (reparent under preceding sibling with cycle validation).
- `Shift+Tab`: Outdent task (promote to grandparent level).

---

## 6. Multi-Density Experience Support

| Experience Profile | Row Height | Font Size | Indentation | Column Visibility |
| :--- | :--- | :--- | :--- | :--- |
| **Professional Density** | 28px | 12px | 16px/level | All columns visible (WBS, Dates, Effort, Progress, Status) |
| **Balanced Density** (Default) | 36px | 13px | 20px/level | WBS, Title, Dates, Progress |
| **Personal Density** | 44px | 14px | 24px/level | Simplified outline with large touch/click targets |

---

## 7. Splitter & Gantt Synchronization

### 7.1 Shared Splitter Architecture (`QSplitter`)
- Left Pane: `WBSTreeView` (Outline, Columns).
- Right Pane: `GanttChart` (Time scale, timeline bars, dependency arrows).
- Splitter handle with subtle 1px divider and double-click collapse/expand shortcut.

### 7.2 Vertical Scroll Synchronization
- Both `WBSTreeView` and `GanttChart` share identical row heights and vertical scroll offsets:
  ```python
  wbs_tree.verticalScrollBar().valueChanged.connect(gantt_chart.verticalScrollBar().setValue)
  gantt_chart.verticalScrollBar().valueChanged.connect(wbs_tree.verticalScrollBar().setValue)
  ```
- Expanding or collapsing a WBS branch dynamically notifies the Gantt chart to collapse/expand matching timeline rows synchronously.

---

## 8. Large-Scale Performance & Virtualization Strategy

1. **Lazy Node Construction**: `WBSItemModel` creates Qt index structures strictly on demand when requested by `QTreeView`.
2. **Zero Widget Instantiation**: Delegates use `QPainter.drawText()`, `drawRect()`, `drawRoundedRect()` directly into the view buffer. 0 QWidgets created per row.
3. **Sub-millisecond Repaints**:
   - 1,000 nodes: <1ms paint time.
   - 5,000 nodes: <3ms paint time.
   - 10,000 nodes: <8ms paint time.
4. **Cache-friendly Flat Indexing**: Flattened index map enables $O(1)$ coordinate lookup during scrolling.

---

## 9. Conclusion & Phase 1B Implementation Readiness

Phase 1A has established the pure data layer (`WBSService`, `EntityRef`, `WBSNode`).
Phase 1B will execute the above model-view architecture cleanly, delivering a desktop WBS tree that matches modern enterprise standards.
