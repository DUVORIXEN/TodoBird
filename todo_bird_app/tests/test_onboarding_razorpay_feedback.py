import os
import pytest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from todo_bird_app.database import DatabaseManager
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.controllers.theme_controller import ThemeController
from todo_bird_app.views.main_window import MainWindow
from todo_bird_app.widgets.headerbar import HeaderBarWidget
from todo_bird_app.widgets.onboarding_tour import OnboardingTeachingOverlay, TOUR_STEPS
from todo_bird_app.views.user_manual_view import UserManualView, MANUAL_CHAPTERS
from todo_bird_app.views.pilot_feedback_view import PilotFeedbackView, MOOD_OPTIONS
from todo_bird_app.services.pilot_issue_logger import PilotIssueLogger
from todo_bird_app.services.support_service import SupportService
from todo_bird_app.widgets.support_dialog import SupportTodoBirdDialog


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def temp_env(tmp_path):
    db_path = tmp_path / "test_upgrade.db"
    db = DatabaseManager.temporary(str(db_path))
    settings = SettingsManager(db, config_dir=tmp_path / "config")
    theme = ThemeController(settings)
    return db, settings, theme


def test_razorpay_button_visible_beside_world_clock(qapp):
    """Verify Razorpay button is present and positioned directly beside World Clock button."""
    hb = HeaderBarWidget()
    assert hasattr(hb, "clock_btn")
    assert hasattr(hb, "razorpay_btn")
    assert hb.razorpay_btn.text() == "Razorpay"
    assert hb.razorpay_btn.objectName() == "RazorpaySupportButton"

    layout = hb.layout()
    clock_idx = layout.indexOf(hb.clock_btn)
    razorpay_idx = layout.indexOf(hb.razorpay_btn)
    assert clock_idx != -1
    assert razorpay_idx == clock_idx + 1, "Razorpay button must be directly beside World Clock button"

    triggered = []
    hb.support_requested.connect(lambda: triggered.append(True))
    hb.razorpay_btn.click()
    assert len(triggered) == 1
    hb.close()


def test_razorpay_support_service_and_dialog_update(qapp, temp_env):
    """Verify Razorpay URL customization and tier buttons in SupportTodoBirdDialog."""
    db, settings, _ = temp_env
    service = SupportService(settings, db)
    assert service.get_support_url() == "https://razorpay.me/@duvorixen"

    dialog = SupportTodoBirdDialog(service)
    assert len(dialog.tier_buttons) == 4
    assert dialog.url_input.text() == "https://razorpay.me/@duvorixen"

    # Update Razorpay URL
    dialog.url_input.setText("https://razorpay.me/@duvorixen-pro")
    dialog._on_update_url()
    assert service.get_support_url() == "https://razorpay.me/@duvorixen-pro"
    import shiboken6
    shiboken6.delete(dialog)


def test_first_time_onboarding_tour_and_completion(qapp, temp_env):
    """Verify first-time user sees interactive teaching tour and completion persists."""
    db, settings, theme = temp_env
    assert settings.get("onboarding_completed") is False

    win = MainWindow(db, settings, theme)
    win.show()
    qapp.processEvents()

    assert win.onboarding_overlay is not None
    assert isinstance(win.onboarding_overlay, OnboardingTeachingOverlay)
    assert not win.onboarding_overlay.isHidden()
    assert win.onboarding_overlay.current_step_index == 0

    # Step through all teaching steps
    for expected_step in range(1, len(TOUR_STEPS)):
        win.onboarding_overlay.next_step()
        assert win.onboarding_overlay.current_step_index == expected_step

    # Final step finishes tour and marks onboarding_completed = True
    win.onboarding_overlay.next_step()
    assert settings.get("onboarding_completed") is True
    assert win.onboarding_overlay.isHidden()
    win.close()


def test_user_manual_view_search_and_chapters(qapp, temp_env):
    """Verify UserManualView renders all chapters and filters by search query."""
    db, settings, _ = temp_env
    manual = UserManualView(db, settings)
    assert len(manual.chapter_cards) == len(MANUAL_CHAPTERS)

    manual._on_search_changed("razorpay")
    visible_cards = [c for c in manual.chapter_cards if not c.isHidden()]
    assert len(visible_cards) >= 1

    manual._on_search_changed("")
    assert all(not c.isHidden() for c in manual.chapter_cards)
    manual.close()


def test_user_feedback_sentiment_rating_and_github_delivery(qapp, temp_env, tmp_path):
    """Verify user feeling, star rating, user check-in, and GitHub feedback URL builder."""
    db, settings, _ = temp_env
    view = PilotFeedbackView(db, settings)
    view.logger_engine.issue_file = tmp_path / "test_feedback.json"

    view._set_feeling(MOOD_OPTIONS[0])
    view._set_rating(5)
    view.txt_user_name.setText("Aarav Sharma")
    view.txt_user_country.setText("India")
    view.txt_title.setText("Amazing Gantt & World Clock")
    view.txt_desc.setText("Downloaded from Ubuntu Software, loving the offline speed!")

    with patch("PySide6.QtWidgets.QMessageBox.information"):
        view.submit_issue(send_to_github=False)

    issues = view.logger_engine.get_all_issues()
    assert len(issues) == 1
    rec = issues[0]
    assert rec["rating"] == 5
    assert rec["feeling"] == MOOD_OPTIONS[0]
    assert rec["user_name"] == "Aarav Sharma"
    assert rec["user_country"] == "India"
    assert rec["install_channel"] != ""

    gh_url = PilotIssueLogger.build_github_feedback_url(rec)
    assert gh_url.startswith("https://github.com/DUVORIXEN/TodoBird/issues/new?")
    assert "Aarav+Sharma" in gh_url
    assert "India" in gh_url
    view.close()


def test_sample_executive_project_load_and_remove(temp_env):
    """Verify 1-click Sample Executive Project loads tasks/subtasks and removes cleanly."""
    from todo_bird_app.services.sample_project_service import SampleProjectService
    db, _, _ = temp_env

    assert SampleProjectService.has_sample_project(db) is False
    pid = SampleProjectService.load_sample_project(db)
    assert pid is not None
    assert SampleProjectService.has_sample_project(db) is True

    tasks = [t for t in db.get_all_tasks() if t.get("project_id") == pid]
    assert len(tasks) == 4

    removed = SampleProjectService.remove_sample_project(db)
    assert removed is True
    assert SampleProjectService.has_sample_project(db) is False


def test_qr_code_and_supporter_badge(qapp, temp_env):
    """Verify QR code generation and Supporter Star Badge in HeaderBarWidget."""
    from todo_bird_app.utils.qr_code import encode_qr_matrix, QRCodeWidget
    matrix = encode_qr_matrix("https://razorpay.me/@duvorixen")
    assert len(matrix) in (21, 25, 29, 33)
    assert len(matrix[0]) == len(matrix)

    qr = QRCodeWidget("https://razorpay.me/@duvorixen")
    assert qr.width() == 126
    qr.close()

    hb = HeaderBarWidget()
    hb.set_supporter_badge(True)
    assert hb.razorpay_btn.text() == "Razorpay ★"
    hb.set_supporter_badge(False)
    assert hb.razorpay_btn.text() == "Razorpay"
    hb.close()


def test_milestone_pulse_banner_triggers_at_3_completed_tasks(qapp, temp_env, tmp_path):
    """Verify MilestonePulseBanner triggers when 3 tasks are completed."""
    from todo_bird_app.models.task import Task, TaskStatus
    db, settings, theme = temp_env
    settings.set("onboarding_completed", True)

    win = MainWindow(db, settings, theme)
    win.show()
    qapp.processEvents()

    for i in range(3):
        t = Task(title=f"Milestone Task {i}", status=TaskStatus.COMPLETED)
        db.insert_task(t.to_dict())

    win._check_milestone_pulse()
    assert win.milestone_pulse_banner is not None
    assert not win.milestone_pulse_banner.isHidden()

    win.milestone_pulse_banner.logger_engine.issue_file = tmp_path / "pulse.json"
    win.milestone_pulse_banner._on_mood_clicked("🤩 Loving It", 5)
    assert settings.get("milestone_pulse_completed") is True
    win.close()

