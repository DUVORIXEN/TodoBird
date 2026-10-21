import logging
from typing import Optional
from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)

SECTION_INFO = {
    "dashboard": ("Actionable Dashboard", "Executive command center & execution overview"),
    "inbox": ("Inbox", "Capture ideas & unscheduled tasks"),
    "today": ("Today's Plan", "Focus on tasks scheduled for today"),
    "focus": ("Focus Mode", "Deep work timer & execution tracking"),
    "upcoming": ("Upcoming Schedule", "Look ahead at upcoming tasks & deadlines"),
    "projects": ("Projects", "Organize tasks into structured projects"),
    "wbs": ("WBS Hierarchy", "Work breakdown structure & schedule rollups"),
    "completed": ("Completed Tasks", "Review accomplished milestones & history"),
    "calendar": ("Calendar View", "Monthly and weekly schedule overview"),
    "gantt": ("Gantt Timeline", "Interactive timeline & Plan vs Actual comparison"),
    "analytics": ("Productivity Analytics", "Track execution rates, completion trends & efficiency"),
    "daily_review": ("Daily Review", "Morning planning & Evening Plan vs Actual review"),
    "feedback": ("Pilot Feedback", "Parallel Pilot Issue Tracker & Diagnostic Export"),
    "world_clock": ("World Clock & Timezone Planner", "Multi-country global time tracking & meeting overlap finder"),
    "settings": ("Preferences & Settings", "Theme, Voice, Companion, and Systemd Shutdown Guard"),
}

class NavigationController(QObject):
    """
    Controller responsible for view switching and header synchronization.
    """
    navigate_to_section = Signal(str, object)  # (section_key, project_id or None)

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.current_section = "dashboard"

    def refresh_active_view(self):
        """Re-runs refresh_data() on the view for the current section."""
        target_section = self.current_section
        if target_section == "wbs":
            target_section = "projects"
        elif target_section == "tasks":
            target_section = "today"
        entry = self.main_window.view_stack_map.get(target_section)
        if entry is None:
            logger.warning(f"Cannot refresh unknown section: {target_section}")
            return
        view_widget = entry[1]
        if hasattr(view_widget, "refresh_data"):
            view_widget.refresh_data()

    def set_active_section(self, section_key: str, project_id: Optional[int] = None):
        target_section = section_key
        target_mode = None
        if section_key == "wbs":
            target_section = "projects"
            target_mode = "wbs"
        elif section_key == "tasks":
            target_section = "today"

        if target_section not in self.main_window.view_stack_map:
            logger.warning(f"Unknown section key: {section_key}")
            return

        self.current_section = section_key
        index, view_widget = self.main_window.view_stack_map[target_section]

        # Switch stacked widget view
        self.main_window.stacked_widget.setCurrentIndex(index)

        # If navigating to Gantt with explicit project_id, apply it BEFORE refresh
        if target_section == "gantt" and project_id is not None:
            if hasattr(view_widget, "set_project_scope"):
                view_widget.set_project_scope(project_id)
            elif hasattr(view_widget, "current_project_id"):
                view_widget.current_project_id = project_id
                # Persist so Gantt remembers this explicit selection
                view_widget.settings_manager.set("gantt_selected_project_id", project_id)

        # If navigating to Projects/WBS with explicit project_id or mode
        if target_section == "projects":
            if hasattr(view_widget, "set_project_scope"):
                view_widget.set_project_scope(
                    project_id=project_id,
                    mode=target_mode or ("wbs" if section_key == "wbs" else None),
                )
            else:
                if project_id is not None:
                    view_widget.selected_project_id = project_id
                if target_mode == "wbs":
                    if hasattr(view_widget, "view_mode_control"):
                        view_widget.view_mode_control.set_selected_index(0, notify=False)
                    if hasattr(view_widget, "view_stack"):
                        view_widget.view_stack.setCurrentIndex(0)
                    if hasattr(view_widget, "wbs_view") and project_id is not None:
                        view_widget.wbs_view.set_project(project_id)

        # Trigger data refresh on active view
        if hasattr(view_widget, "refresh_data"):
            view_widget.refresh_data()

        # Update headerbar title & subtitle
        title, subtitle = SECTION_INFO.get(section_key, SECTION_INFO.get(target_section, (section_key.capitalize(), "")))
        self.main_window.headerbar.set_section_title(title, subtitle)

        # Sync sidebar selection state without recursive signal loop
        self.main_window.sidebar.blockSignals(True)
        self.main_window.sidebar.select_item(target_section)
        self.main_window.sidebar.blockSignals(False)

        if hasattr(self.main_window, "update_background_overlay"):
            self.main_window.update_background_overlay()

        self.navigate_to_section.emit(section_key, project_id)
        logger.info(f"Navigated to section: {section_key}" + (f" (project_id={project_id})" if project_id else ""))
