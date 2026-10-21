from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout, QPushButton
from PySide6.QtCore import Qt
from todo_bird_app.views.base_view import BaseView
from todo_bird_app.widgets.card import CardWidget

class SectionPlaceholderView(BaseView):
    """
    Standard view placeholder for sections being incrementally developed across phases.
    """
    def __init__(self, db_manager, settings_manager, section_id: str, title: str, icon: str, subtitle: str, parent=None):
        super().__init__(db_manager, settings_manager, title=title, subtitle=subtitle, parent=parent)
        self.section_id = section_id
        self.icon = icon
        self._init_ui()

    def _init_ui(self):
        card = CardWidget(self)

        content_layout = QVBoxLayout()
        content_layout.setSpacing(12)
        content_layout.setAlignment(Qt.AlignCenter)

        icon_label = QLabel()
        from todo_bird_app.services.icon_service import IconService
        if IconService.has_icon(self.icon):
            icon_label.setPixmap(IconService.get_pixmap(self.icon, 48, "#9AA6BD"))
        else:
            icon_label.setText(self.icon)
            icon_label.setStyleSheet("font-size: 48px;")
        icon_label.setAlignment(Qt.AlignCenter)

        title_label = QLabel(self.title)
        title_label.setStyleSheet("font-size: 22px; font-weight: 700;")
        title_label.setAlignment(Qt.AlignCenter)

        sub_label = QLabel(self.subtitle)
        sub_label.setStyleSheet("font-size: 13px; color: #9CA3AF;")
        sub_label.setAlignment(Qt.AlignCenter)

        content_layout.addWidget(icon_label)
        content_layout.addWidget(title_label)
        content_layout.addWidget(sub_label)

        card.layout.addLayout(content_layout)
        self.main_layout.addWidget(card)
        self.main_layout.addStretch()


class InboxView(SectionPlaceholderView):
    def __init__(self, db, settings, parent=None):
        super().__init__(db, settings, "inbox", "Inbox", "inbox", "Capture ideas & unscheduled tasks", parent)

class TodayView(SectionPlaceholderView):
    def __init__(self, db, settings, parent=None):
        super().__init__(db, settings, "today", "Today's Plan", "star", "Focus on tasks scheduled for today", parent)

class UpcomingView(SectionPlaceholderView):
    def __init__(self, db, settings, parent=None):
        super().__init__(db, settings, "upcoming", "Upcoming Schedule", "calendar", "Look ahead at upcoming tasks & deadlines", parent)

class ProjectsView(SectionPlaceholderView):
    def __init__(self, db, settings, parent=None):
        super().__init__(db, settings, "projects", "Projects", "folder", "Organize tasks into structured projects", parent)

class CompletedView(SectionPlaceholderView):
    def __init__(self, db, settings, parent=None):
        super().__init__(db, settings, "completed", "Completed Tasks", "check_circle", "Review accomplished milestones & history", parent)

class CalendarView(SectionPlaceholderView):
    def __init__(self, db, settings, parent=None):
        super().__init__(db, settings, "calendar", "Calendar View", "calendar", "Monthly and weekly schedule overview", parent)

class GanttView(SectionPlaceholderView):
    def __init__(self, db, settings, parent=None):
        super().__init__(db, settings, "gantt", "Gantt Timeline", "chart", "Interactive timeline & Plan vs Actual comparison", parent)

class AnalyticsView(SectionPlaceholderView):
    def __init__(self, db, settings, parent=None):
        super().__init__(db, settings, "analytics", "Productivity Analytics", "chart", "Track execution rates, completion trends & efficiency", parent)

class DailyReviewView(SectionPlaceholderView):
    def __init__(self, db, settings, parent=None):
        super().__init__(db, settings, "daily_review", "Daily Review", "search", "Morning planning & Evening Plan vs Actual review", parent)

class SettingsView(SectionPlaceholderView):
    def __init__(self, db, settings, parent=None):
        super().__init__(db, settings, "settings", "Preferences & Settings", "settings", "Theme, Voice, Companion, and Systemd Shutdown Guard", parent)
