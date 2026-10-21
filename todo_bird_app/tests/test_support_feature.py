import pytest
import os
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QUrl

from todo_bird_app.database import DatabaseManager
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.services.support_service import SupportService
from todo_bird_app.widgets.support_dialog import SupportTodoBirdDialog
from todo_bird_app.models.task import Task, TaskStatus

@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app

@pytest.fixture
def temp_db(tmp_path):
    db_path = tmp_path / "test_support.db"
    return DatabaseManager.temporary(str(db_path))

@pytest.fixture
def settings(temp_db, tmp_path):
    # Use isolated config directory
    config_dir = tmp_path / "config"
    sm = SettingsManager(temp_db, config_dir=config_dir)
    return sm

@pytest.fixture
def support_service(settings, temp_db):
    with patch("todo_bird_app.services.support_service.SUPPORT_AUTOMATIC_PROMPTS_ENABLED", True):
        yield SupportService(settings, temp_db)

def test_support_url_is_https(support_service):
    """Test 4: support button opens only approved HTTPS URL"""
    url = support_service.get_support_url()
    assert url.startswith("https://")

def test_user_below_threshold_not_prompted(support_service, temp_db):
    """Test 10: user below usage threshold is not prompted."""
    # Insert 1 recent task
    t = Task(title="Recent Task", status=TaskStatus.INBOX)
    temp_db.insert_task(t.to_dict())
    
    assert support_service.is_eligible_for_automatic_prompt() is False

def test_eligible_user_prompted(support_service, temp_db):
    """Test 11: eligible user can be prompted."""
    # Insert 30 completed tasks
    for i in range(30):
        t = Task(title=f"Completed {i}", status=TaskStatus.COMPLETED)
        temp_db.insert_task(t.to_dict())
        
    assert support_service.is_eligible_for_automatic_prompt() is True

def test_cooldown_prevents_repeated_prompts(support_service, settings, temp_db):
    """Test 12: cooldown prevents repeated prompts."""
    for i in range(30):
        t = Task(title=f"Completed {i}", status=TaskStatus.COMPLETED)
        temp_db.insert_task(t.to_dict())
        
    # Eligible initially
    assert support_service.is_eligible_for_automatic_prompt() is True
    
    # Record prompt shown
    support_service.record_support_prompt_shown()
    
    # No longer eligible (cooldown)
    assert support_service.is_eligible_for_automatic_prompt() is False
    
    # Fast forward 31 days
    past_date = datetime.now() - timedelta(days=31)
    settings.set("last_support_prompt_date", past_date.isoformat())
    
    # Eligible again
    assert support_service.is_eligible_for_automatic_prompt() is True

def test_dont_ask_again_disables_prompts(support_service, temp_db):
    """Test 14: Don't ask again permanently disables automatic prompts."""
    for i in range(30):
        t = Task(title=f"Completed {i}", status=TaskStatus.COMPLETED)
        temp_db.insert_task(t.to_dict())
        
    support_service.disable_automatic_prompts()
    assert support_service.is_eligible_for_automatic_prompt() is False

@patch("PySide6.QtGui.QDesktopServices.openUrl")
def test_invalid_url_scheme_is_rejected(mock_open, qapp, support_service):
    """Test 5: invalid URL scheme is rejected."""
    support_service.SUPPORT_URL = "http://support.todobird.local"
    dialog = SupportTodoBirdDialog(support_service)
    
    with patch("PySide6.QtWidgets.QMessageBox.critical") as mock_critical:
        dialog._on_support_clicked()
        mock_critical.assert_called_once()
        mock_open.assert_not_called()
