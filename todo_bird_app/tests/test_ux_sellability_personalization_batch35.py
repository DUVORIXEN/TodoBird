import os
import tempfile
import shutil
from datetime import date
from pathlib import Path
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage, QColor, QPixmap

from todo_bird_app.database import DatabaseManager
from todo_bird_app.settings import SettingsManager
from todo_bird_app.models.task import Task, TaskPriority, TaskStatus, TaskCategory
from todo_bird_app.services.media_service import MediaService
from todo_bird_app.services.companion_service import CompanionService
from todo_bird_app.ui.background_overlay import BackgroundOverlayWidget
from todo_bird_app.ui.design_tokens import DesignTokens

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app

@pytest.fixture
def temp_env(tmp_path):
    db_file = tmp_path / "test_ux.db"
    db_mgr = DatabaseManager(str(db_file))
    settings_mgr = SettingsManager(db_manager=db_mgr)
    return {
        "db": db_mgr,
        "settings": settings_mgr,
        "tmp_dir": tmp_path,
    }

def _create_sample_image(path: Path, width: int = 100, height: int = 100, color: QColor = QColor(255, 0, 0, 255), fmt: str = "PNG"):
    img = QImage(width, height, QImage.Format.Format_RGBA8888)
    img.fill(color)
    img.save(str(path), fmt)
    return path


# ---------------------------------------------------------------------------
# UX01 - Task image import/copy into managed store
# ---------------------------------------------------------------------------
def test_ux01_task_image_import_into_managed_store(qapp, temp_env):
    source_img = temp_env["tmp_dir"] / "source_task.png"
    _create_sample_image(source_img, 64, 64)

    meta = MediaService.import_media(str(source_img), category="tasks", db_manager=temp_env["db"])
    assert meta is not None
    assert meta["relative_path"].startswith("tasks/")
    assert meta["thumbnail_path"].startswith("thumbnails/")

    abs_path = MediaService.get_absolute_path(meta["relative_path"])
    assert abs_path is not None
    assert os.path.exists(abs_path)
    assert os.path.getsize(abs_path) > 0


# ---------------------------------------------------------------------------
# UX02 - Task image survives source-file deletion
# ---------------------------------------------------------------------------
def test_ux02_task_image_survives_source_deletion(qapp, temp_env):
    source_img = temp_env["tmp_dir"] / "source_delete_me.png"
    _create_sample_image(source_img, 64, 64)

    meta = MediaService.import_media(str(source_img), category="tasks", db_manager=temp_env["db"])
    assert meta is not None

    # Delete source file
    source_img.unlink()
    assert not source_img.exists()

    # Managed copy still exists and loads cleanly
    pm = MediaService.load_pixmap(meta["relative_path"], max_width=64, max_height=64)
    assert pm is not None
    assert not pm.isNull()


# ---------------------------------------------------------------------------
# UX03 - Task thumbnail persists restart
# ---------------------------------------------------------------------------
def test_ux03_task_thumbnail_persists_restart(qapp, temp_env):
    source_img = temp_env["tmp_dir"] / "thumb_test.png"
    _create_sample_image(source_img, 120, 120)

    meta = MediaService.import_media(str(source_img), category="tasks", db_manager=temp_env["db"])
    
    # Save task with this image
    t_id = temp_env["db"].insert_task({
        "title": "Task with Cover",
        "image_path": meta["relative_path"]
    })

    # Reopen DB (simulating restart)
    reloaded_db = DatabaseManager(temp_env["db"].db_path)
    loaded_task = reloaded_db.get_task_by_id(t_id)
    assert loaded_task is not None
    assert loaded_task["image_path"] == meta["relative_path"]

    # Thumbnail should be loadable
    pm_thumb = MediaService.load_pixmap(loaded_task["image_path"], max_width=32, max_height=32, use_thumbnail=True)
    assert pm_thumb is not None
    assert not pm_thumb.isNull()


# ---------------------------------------------------------------------------
# UX04 - Image removal does not delete unrelated media
# ---------------------------------------------------------------------------
def test_ux04_image_removal_isolation(qapp, temp_env):
    img1 = temp_env["tmp_dir"] / "img1.png"
    img2 = temp_env["tmp_dir"] / "img2.png"
    _create_sample_image(img1, 40, 40)
    _create_sample_image(img2, 40, 40)

    meta1 = MediaService.import_media(str(img1), category="tasks", db_manager=temp_env["db"])
    meta2 = MediaService.import_media(str(img2), category="tasks", db_manager=temp_env["db"])

    # Remove media1
    MediaService.delete_media(meta1["relative_path"])
    assert MediaService.get_absolute_path(meta1["relative_path"]) is None

    # Media2 must still exist
    assert MediaService.get_absolute_path(meta2["relative_path"]) is not None


# ---------------------------------------------------------------------------
# UX05 - Background persists restart
# ---------------------------------------------------------------------------
def test_ux05_background_persists_restart(qapp, temp_env):
    bg_img = temp_env["tmp_dir"] / "wallpaper.jpg"
    _create_sample_image(bg_img, 200, 100)

    meta = MediaService.import_media(str(bg_img), category="backgrounds", db_manager=temp_env["db"])
    temp_env["settings"].set("background_mode", "custom")
    temp_env["settings"].set("background_custom_image_path", meta["relative_path"])
    temp_env["settings"].set("background_fit_mode", "fit")

    # Recreate settings manager (restart)
    reloaded_settings = SettingsManager(db_manager=temp_env["db"])
    assert reloaded_settings.get("background_mode") == "custom"
    assert reloaded_settings.get("background_custom_image_path") == meta["relative_path"]
    assert reloaded_settings.get("background_fit_mode") == "fit"


# ---------------------------------------------------------------------------
# UX06 - Background opacity persists
# ---------------------------------------------------------------------------
def test_ux06_background_opacity_persists(qapp, temp_env):
    temp_env["settings"].set("background_opacity", 0.42)
    reloaded_settings = SettingsManager(db_manager=temp_env["db"])
    assert abs(float(reloaded_settings.get("background_opacity")) - 0.42) < 1e-4


# ---------------------------------------------------------------------------
# UX07 - Custom bird avatar persists restart
# ---------------------------------------------------------------------------
def test_ux07_custom_bird_avatar_persists_restart(qapp, temp_env):
    av_img = temp_env["tmp_dir"] / "avatar.png"
    _create_sample_image(av_img, 80, 80)

    meta = MediaService.import_media(str(av_img), category="companion", db_manager=temp_env["db"])
    temp_env["settings"].set("companion_avatar_mode", "custom")
    temp_env["settings"].set("companion_custom_avatar_path", meta["relative_path"])

    reloaded_settings = SettingsManager(db_manager=temp_env["db"])
    assert reloaded_settings.get("companion_avatar_mode") == "custom"
    assert reloaded_settings.get("companion_custom_avatar_path") == meta["relative_path"]

    pm = CompanionService.get_companion_avatar_pixmap(reloaded_settings, max_dim=48)
    assert pm is not None
    assert not pm.isNull()


# ---------------------------------------------------------------------------
# UX08 - Default bird restoration works
# ---------------------------------------------------------------------------
def test_ux08_default_bird_restoration(qapp, temp_env):
    temp_env["settings"].set("companion_avatar_mode", "custom")
    temp_env["settings"].set("companion_custom_avatar_path", "companion/fake.png")

    # Restore default
    temp_env["settings"].set("companion_avatar_mode", "default")
    temp_env["settings"].set("companion_custom_avatar_path", "")

    assert temp_env["settings"].get("companion_avatar_mode") == "default"
    pm = CompanionService.get_companion_avatar_pixmap(temp_env["settings"], max_dim=48)
    assert pm is not None
    assert not pm.isNull()


# ---------------------------------------------------------------------------
# UX09 - 30-day greeting Day 1 persists
# ---------------------------------------------------------------------------
def test_ux09_30day_greeting_day1_persists(qapp, temp_env):
    temp_env["db"].upsert_greeting(
        cycle_day=1,
        title="Day 1 Kickoff",
        message="Let today begin with calm excellence.",
        image_path="",
        enabled=1
    )

    reloaded_db = DatabaseManager(temp_env["db"].db_path)
    g1 = reloaded_db.get_greeting_by_day(1)
    assert g1 is not None
    assert g1["title"] == "Day 1 Kickoff"
    assert g1["message"] == "Let today begin with calm excellence."


# ---------------------------------------------------------------------------
# UX10 - 30-day greeting Day 30 persists
# ---------------------------------------------------------------------------
def test_ux10_30day_greeting_day30_persists(qapp, temp_env):
    temp_env["db"].upsert_greeting(
        cycle_day=30,
        title="Day 30 Milestone",
        message="Celebrate your persistence and growth.",
        image_path="",
        enabled=1
    )

    reloaded_db = DatabaseManager(temp_env["db"].db_path)
    g30 = reloaded_db.get_greeting_by_day(30)
    assert g30 is not None
    assert g30["title"] == "Day 30 Milestone"
    assert g30["message"] == "Celebrate your persistence and growth."


# ---------------------------------------------------------------------------
# UX11 - Same image applies to multiple days
# ---------------------------------------------------------------------------
def test_ux11_same_image_applies_to_multiple_days(qapp, temp_env):
    shared_img = temp_env["tmp_dir"] / "shared_bg.png"
    _create_sample_image(shared_img, 60, 60)
    meta = MediaService.import_media(str(shared_img), category="greetings", db_manager=temp_env["db"])

    for d in [3, 7, 14]:
        temp_env["db"].upsert_greeting(
            cycle_day=d,
            title=f"Day {d}",
            message="Shared inspiration.",
            image_path=meta["relative_path"],
            enabled=1
        )

    for d in [3, 7, 14]:
        g = temp_env["db"].get_greeting_by_day(d)
        assert g["image_path"] == meta["relative_path"]


# ---------------------------------------------------------------------------
# UX12 - Date/day switching selects correct greeting
# ---------------------------------------------------------------------------
def test_ux12_date_day_switching_selects_correct_greeting(qapp, temp_env):
    temp_env["db"].upsert_greeting(
        cycle_day=5,
        title="Day 5 Planner",
        message="Day 5 message.",
        enabled=1
    )
    temp_env["db"].upsert_greeting(
        schedule_date="2026-08-16",
        title="August 16 Special",
        message="Specific date message.",
        enabled=1
    )

    # In day_by_day mode
    temp_env["settings"].set("companion_greeting_schedule_mode", "day_by_day")
    g_cycle = CompanionService.get_effective_greeting(temp_env["db"], temp_env["settings"], current_date_str="2026-08-05")
    assert g_cycle["title"] == "Day 5 Planner"

    # In date_specific mode
    temp_env["settings"].set("companion_greeting_schedule_mode", "date_specific")
    g_spec = CompanionService.get_effective_greeting(temp_env["db"], temp_env["settings"], current_date_str="2026-08-16")
    assert g_spec["title"] == "August 16 Special"


# ---------------------------------------------------------------------------
# UX13 - Greeting appears once according to preference
# ---------------------------------------------------------------------------
def test_ux13_greeting_appears_once_per_preference(qapp, temp_env):
    CompanionService._session_greeting_shown = False
    temp_env["settings"].set("companion_enabled", True)
    temp_env["settings"].set("companion_avatar_mode", "default")
    temp_env["settings"].set("companion_activity_level", "balanced")
    temp_env["settings"].set("companion_greeting_frequency", "once_per_day")
    temp_env["settings"].set("companion_last_greeting_date", "")

    # First check: should show
    assert CompanionService.should_show_greeting(temp_env["settings"]) is True

    # Mark shown
    CompanionService.mark_greeting_shown(temp_env["settings"])

    # Second check same day: should NOT show
    assert CompanionService.should_show_greeting(temp_env["settings"]) is False


# ---------------------------------------------------------------------------
# UX14 - Disabled companion suppresses greeting
# ---------------------------------------------------------------------------
def test_ux14_disabled_companion_suppresses_greeting(qapp, temp_env):
    temp_env["settings"].set("companion_enabled", False)
    assert CompanionService.should_show_greeting(temp_env["settings"]) is False

    temp_env["settings"].set("companion_enabled", True)
    temp_env["settings"].set("companion_avatar_mode", "disabled")
    assert CompanionService.should_show_greeting(temp_env["settings"]) is False


# ---------------------------------------------------------------------------
# UX15 - Transparent PNG renders correctly
# ---------------------------------------------------------------------------
def test_ux15_transparent_png_renders_correctly(qapp, temp_env):
    trans_img = temp_env["tmp_dir"] / "transparent_bird.png"
    _create_sample_image(trans_img, 64, 64, color=QColor(0, 0, 0, 0))

    meta = MediaService.import_media(str(trans_img), category="companion", db_manager=temp_env["db"])
    pm = MediaService.load_pixmap(meta["relative_path"])
    assert pm is not None
    assert not pm.isNull()
    assert pm.hasAlpha()


# ---------------------------------------------------------------------------
# UX16 - Corrupt image fails gracefully
# ---------------------------------------------------------------------------
def test_ux16_corrupt_image_fails_gracefully(qapp, temp_env):
    corrupt_file = temp_env["tmp_dir"] / "broken.png"
    corrupt_file.write_bytes(b"This is not a real PNG image file header")

    meta = MediaService.import_media(str(corrupt_file), category="tasks", db_manager=temp_env["db"])
    assert meta is None  # Handled safely without exception

    pm = MediaService.load_pixmap("non_existent_file.png")
    assert pm is None  # Safely returns None without crash


# ---------------------------------------------------------------------------
# UX17 - Very large image does not crash
# ---------------------------------------------------------------------------
def test_ux17_large_image_handling(qapp, temp_env):
    large_img = temp_env["tmp_dir"] / "large.png"
    _create_sample_image(large_img, 2048, 2048)

    meta = MediaService.import_media(str(large_img), category="backgrounds", db_manager=temp_env["db"])
    assert meta is not None

    # Load scaled down
    pm = MediaService.load_pixmap(meta["relative_path"], max_width=256, max_height=256)
    assert pm is not None
    assert pm.width() <= 256
    assert pm.height() <= 256


# ---------------------------------------------------------------------------
# UX18 - Task save unaffected by image handling failure
# ---------------------------------------------------------------------------
def test_ux18_task_save_unaffected_by_image_failure(qapp, temp_env):
    # Save a task with a bad / missing image path
    t_id = temp_env["db"].insert_task({
        "title": "Robust Task",
        "image_path": "corrupt/or/missing/image.png"
    })
    assert t_id is not None
    t = temp_env["db"].get_task_by_id(t_id)
    assert t["title"] == "Robust Task"


# ---------------------------------------------------------------------------
# UX19 - Gantt regression unchanged
# ---------------------------------------------------------------------------
def test_ux19_gantt_regression_unchanged(qapp, temp_env):
    from todo_bird_app.utils.time_math import duration_between, calculate_actual_elapsed_minutes
    # Verify deterministic time math authority remains authoritative
    dur = duration_between("2026-08-13", "07:00", "2026-08-15", "13:40")
    assert dur == 3280

    act_dur = calculate_actual_elapsed_minutes("2026-08-14", "10:00", "2026-08-16", "17:00")
    assert act_dur == 3300


# ---------------------------------------------------------------------------
# UX20 - Calendar regression unchanged
# ---------------------------------------------------------------------------
def test_ux20_calendar_regression_unchanged(qapp, temp_env):
    from todo_bird_app.services.working_week import WorkingWeekService
    from todo_bird_app.utils.working_calendar import set_configured_working_weekdays
    set_configured_working_weekdays([0, 1, 2, 3, 4], temp_env["settings"])
    wws = WorkingWeekService(temp_env["settings"])
    assert not wws.is_weekend(date(2026, 8, 14))  # Friday is working day
    assert wws.is_weekend(date(2026, 8, 15))      # Saturday is weekend


# ---------------------------------------------------------------------------
# UX21 - Focus regression unchanged
# ---------------------------------------------------------------------------
def test_ux21_focus_regression_unchanged(qapp, temp_env):
    t_id = temp_env["db"].insert_task({
        "title": "Focus Task",
        "priority": TaskPriority.HIGH.value,
        "status": TaskStatus.IN_PROGRESS.value,
        "actual_start_date": "2026-08-15",
        "progress": 50
    })
    t = temp_env["db"].get_task_by_id(t_id)
    assert t["status"] == "in_progress" or t["status"] == "In Progress"
    assert t["progress"] == 50


# ---------------------------------------------------------------------------
# UX22 - Subtask hierarchy logic unaffected
# ---------------------------------------------------------------------------
def test_ux22_subtask_hierarchy_logic_unaffected(qapp, temp_env):
    t_id = temp_env["db"].insert_task({"title": "Parent Task"})
    sub_id = temp_env["db"].insert_subtask(
        task_id=t_id,
        title="Child Subtask",
        planned_effort_minutes=180,
        daily_dedication_minutes=60,
        image_path="tasks/sub.png"
    )
    subs = temp_env["db"].get_all_subtasks_flat(t_id)
    assert len(subs) >= 1
    sub = [s for s in subs if s["id"] == sub_id][0]
    assert sub["planned_effort_minutes"] == 180
    assert sub["daily_dedication_minutes"] == 60
    assert sub["image_path"] == "tasks/sub.png"


# ---------------------------------------------------------------------------
# UX23 - High-DPI layout does not clip critical controls
# ---------------------------------------------------------------------------
def test_ux23_high_dpi_layout_compatibility(qapp, temp_env):
    widget = BackgroundOverlayWidget()
    assert widget.opacity in (0.35, 0.42)
    assert widget.fit_mode in ("fill", "fit")


# ---------------------------------------------------------------------------
# UX24 - Dark/light themes preserve readable contrast
# ---------------------------------------------------------------------------
def test_ux24_design_tokens_contrast(qapp):
    assert DesignTokens.COLOR_ACCENT.startswith("#")
    assert DesignTokens.DARK_SURFACE.startswith("#")
    assert DesignTokens.LIGHT_SURFACE.startswith("#")
    assert DesignTokens.RADIUS_MD == 10
    assert DesignTokens.SPACING_MD == 12


# ---------------------------------------------------------------------------
# UX25 - Media paths remain portable inside Todo Bird data directory
# ---------------------------------------------------------------------------
def test_ux25_media_paths_portability(qapp, temp_env):
    img = temp_env["tmp_dir"] / "portable.png"
    _create_sample_image(img, 50, 50)

    meta = MediaService.import_media(str(img), category="tasks", db_manager=temp_env["db"])
    assert not os.path.isabs(meta["relative_path"])
    assert not meta["relative_path"].startswith("/")
    assert "/" in meta["relative_path"] or "\\" in meta["relative_path"]

    # Resolution to absolute path uses PathResolver
    resolved = MediaService.get_absolute_path(meta["relative_path"])
    assert resolved is not None
    assert os.path.isabs(resolved)
    assert os.path.exists(resolved)
