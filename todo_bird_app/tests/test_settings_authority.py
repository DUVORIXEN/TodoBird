import os
import json
import pytest
from pathlib import Path
from todo_bird_app.database import DatabaseManager
from todo_bird_app.settings.settings_manager import SettingsManager

@pytest.fixture
def temp_config_and_db(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_file = config_dir / "config.json"
    
    # Write initial JSON settings
    json_settings = {
        "reminder_trigger_mode": "disabled",
        "companion_visible_seconds": 10
    }
    with open(config_file, "w") as f:
        json.dump(json_settings, f)
        
    db_file = tmp_path / "test_authority.db"
    
    db = DatabaseManager.production(str(db_file))
    
    # Inject override into database
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            ("reminder_trigger_mode", '"app_startup"')
        )
        conn.commit()
        
    yield db, config_dir

def test_settings_authority_database_overrides_json(temp_config_and_db):
    """
    GAP 4 Proof:
    SettingsManager must load config.json first, and then override those values
    with the ones found in the production SQLite database.
    """
    db, config_dir = temp_config_and_db
    
    # We initialize the real SettingsManager, passing the DB manager
    settings = SettingsManager(db_manager=db, config_dir=config_dir)
    
    # Check that companion_visible_seconds came from config.json (because it wasn't in DB)
    assert settings.get("companion_visible_seconds") == 10
    
    # Check that reminder_trigger_mode came from DB (overriding JSON 'disabled' with 'app_startup')
    assert settings.get("reminder_trigger_mode") == "app_startup"
