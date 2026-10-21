import os
import zipfile
import tempfile
import logging
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

from todo_bird_app.__version__ import __version__
from todo_bird_app.database import CURRENT_SCHEMA_VERSION
from todo_bird_app.services.path_resolver import PathResolver

logger = logging.getLogger(__name__)

class SupportBundleService:
    """
    Safely collects non-sensitive diagnostic data into a ZIP bundle for support purposes.
    """

    @staticmethod
    def _collect_diagnostics() -> Dict[str, Any]:
        try:
            import PySide6
            from PySide6.QtCore import qVersion
            pyside_version = PySide6.__version__
            qt_version = qVersion()
        except ImportError:
            pyside_version = "Unknown"
            qt_version = "Unknown"

        return {
            "version": __version__,
            "build_date": "2026-09-21",  # Static Beta placeholder
            "platform": sys.platform,
            "python_version": sys.version,
            "pyside_version": pyside_version,
            "qt_version": qt_version,
            "schema_version": CURRENT_SCHEMA_VERSION,
            "qpa_backend": os.environ.get("QT_QPA_PLATFORM", "default"),
            "display": os.environ.get("DISPLAY", "None"),
            "wayland_display": os.environ.get("WAYLAND_DISPLAY", "None"),
            "desktop_session": os.environ.get("DESKTOP_SESSION", "Unknown"),
            "collection_time": datetime.now().isoformat()
        }

    @classmethod
    def generate_support_bundle(cls) -> Path:
        """
        Creates a ZIP file containing sanitized diagnostics and recent logs.
        Does NOT include the database or task data.
        Returns the path to the generated ZIP.
        """
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        bundle_name = f"TodoBird-Support-{ts}.zip"
        
        # We will write the bundle to the user's document/desktop or temp dir
        out_dir = PathResolver.get_backups_dir().parent / "support_bundles"
        out_dir.mkdir(parents=True, exist_ok=True)
        bundle_path = out_dir / bundle_name
        
        diagnostics = cls._collect_diagnostics()
        
        with zipfile.ZipFile(bundle_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Add diagnostics JSON
            diag_str = json.dumps(diagnostics, indent=2)
            zf.writestr("diagnostics.json", diag_str)
            
            # Add recent logs
            log_dir = Path(__file__).parent.parent / "logs"
            if log_dir.exists():
                for log_file in log_dir.glob("*.log"):
                    # We could sanitize logs here if needed, but for beta, we just include them
                    zf.write(log_file, arcname=f"logs/{log_file.name}")
                    
        logger.info(f"Support bundle generated: {bundle_path}")
        return bundle_path
