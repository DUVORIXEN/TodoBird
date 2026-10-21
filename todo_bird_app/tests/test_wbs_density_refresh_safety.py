
from pathlib import Path


VIEW = Path(
    "todo_bird_app/views/wbs_project_view.py"
).read_text()

DELEGATE = Path(
    "todo_bird_app/views/wbs_tree_delegate.py"
).read_text()

CUSTOM = Path(
    "todo_bird_app/services/wbs_customization_service.py"
).read_text()


def _appearance_method_source():
    start = VIEW.index(
        "    def refresh_wbs_appearance(self):"
    )
    end = VIEW.index(
        "    def on_wbs_preferences_changed",
        start,
    )
    return VIEW[start:end]


def test_appearance_refresh_never_emits_layout_changed():
    method = _appearance_method_source()

    assert "layoutChanged.emit" not in method
    assert "beginResetModel" not in method
    assert "endResetModel" not in method
    assert "refresh_hierarchy()" not in method


def test_density_refresh_is_deferred_out_of_control_callback():
    method = _appearance_method_source()

    assert "QTimer.singleShot(0, self._apply_wbs_appearance_refresh)" in method


def test_density_refresh_is_view_only():
    assert "def _apply_wbs_appearance_refresh(self)" in VIEW
    assert "tree.scheduleDelayedItemsLayout()" in VIEW
    assert "tree.doItemsLayout()" in VIEW
    assert "tree.updateGeometry()" in VIEW
    assert "viewport.update()" in VIEW


def test_density_delegate_reads_live_metrics():
    assert "def sizeHint(" in DELEGATE
    assert "self._custom_service.get_density_metrics()" in DELEGATE

    # Phase 1F.8.1 typography-safety contract:
    # density remains a live compactness input, but it is no longer
    # permitted to force a row below the physical font requirement.
    assert "density_height = int(metrics.row_height)" in DELEGATE
    assert "text_minimum" in DELEGATE
    assert "return max(" in DELEGATE
    assert "density_height" in DELEGATE


def test_density_profiles_remain_distinct():
    assert '"professional": WBSDensityMetrics(' in CUSTOM
    assert "row_height=28" in CUSTOM

    assert '"balanced": WBSDensityMetrics(' in CUSTOM
    assert "row_height=36" in CUSTOM

    assert '"personal": WBSDensityMetrics(' in CUSTOM
    assert "row_height=44" in CUSTOM


def test_density_change_does_not_rebuild_wbs_hierarchy():
    method = _appearance_method_source()

    forbidden = (
        "WBSService.build_project_hierarchy",
        "set_snapshot(",
        "WBSMutationService",
        "notify_tasks_changed",
    )

    for token in forbidden:
        assert token not in method
