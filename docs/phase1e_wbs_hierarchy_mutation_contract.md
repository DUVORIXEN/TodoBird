# Phase 1E — WBS Hierarchy Mutation Contract

## Canonical persistent structure

### Task
- Always a project-level WBS root.
- `tasks.position` is sibling order within project.
- A Task is never converted into a Subtask by indent/outdent/drag-drop.

### Subtask
- Always belongs to one owning Task through `task_id`.
- `parent_subtask_id IS NULL` means direct child of owning Task.
- `parent_subtask_id=<id>` means nested child of another Subtask.
- `position` is sibling-local order.

## Mutation authority

All persistent hierarchy changes must go through
`WBSMutationService`.

Qt item models remain read-only snapshot adapters.

## Safety

Reject:
- self-parenting
- cycles
- implicit cross-main-task moves
- cross-project moves
- task-as-child operations
- unsupported entity conversion

## Ordering

After structural editing, affected sibling scopes use dense positions:

`0, 1, 2, ...`

No duplicate positions are intentionally created.

## Derived data

Hierarchy mutation never writes:
- summary planned dates
- summary Actual dates
- rollup progress
- rollup effort

Those continue to be derived through WBSService/WBSRollupService/Gantt adapter.

## Planned UI chain

UI action
→ WBSMutationService
→ transaction commit
→ rollup cache invalidation
→ WBS snapshot rebuild
→ WBS tree refresh
→ Gantt refresh

## Phase 1E implementation sequence

1. Mutation authority / contract
2. Add Child append-position integration
3. Move Up / Move Down UI
4. Indent / Outdent UI
5. Safe drag/drop
6. keyboard/accessibility/polish
7. human acceptance
