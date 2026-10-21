import logging
from typing import Any
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QStackedWidget,
    QFileDialog, QMessageBox, QApplication, QToolTip, QMenuBar, QMenu
)
from PySide6.QtGui import QShortcut, QKeySequence, QAction
from PySide6.QtCore import QPoint, QTimer

from todo_bird_app.widgets.sidebar import SidebarWidget
from todo_bird_app.widgets.headerbar import HeaderBarWidget
from todo_bird_app.widgets.project_dialog import ProjectDialog
from todo_bird_app.widgets.task_dialog import TaskDialog
from todo_bird_app.widgets.command_palette import CommandPalette
from todo_bird_app.widgets.toast_banner import ToastBanner
from todo_bird_app.services.report_exporter import ReportExporterService
from todo_bird_app.widgets.reminder_dialog import ReminderDialog
from todo_bird_app.widgets.support_dialog import SupportTodoBirdDialog
from todo_bird_app.services.support_service import SupportService
from todo_bird_app.services.support_bundle_service import SupportBundleService
from todo_bird_app.services.window_interaction_service import WindowInteractionService
from todo_bird_app.services.command_registry import CommandRegistry
from todo_bird_app.services.appearance_service import AppearanceService
from todo_bird_app.controllers.navigation_controller import NavigationController
from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.views.dashboard_view import DashboardView
from todo_bird_app.views.inbox_view import InboxView
from todo_bird_app.views.today_view import TodayView
from todo_bird_app.views.focus_view import FocusView
from todo_bird_app.views.upcoming_view import UpcomingView
from todo_bird_app.views.projects_view import ProjectsView
from todo_bird_app.views.completed_view import CompletedView
from todo_bird_app.views.daily_review_view import DailyReviewView
from todo_bird_app.views.gantt_view import GanttView
from todo_bird_app.views.settings_view import SettingsView
from todo_bird_app.views.pilot_feedback_view import PilotFeedbackView
from todo_bird_app.views.calendar_view import CalendarView
from todo_bird_app.views.analytics_view import AnalyticsView
from todo_bird_app.views.world_clock_view import WorldClockView
from todo_bird_app.ui.background_overlay import BackgroundOverlayWidget
from todo_bird_app.services.language_service import LanguageService
from todo_bird_app.services.companion_service import CompanionService

logger = logging.getLogger(__name__)

class MainWindow(QMainWindow):
    """
    Main Application Window for TODO BIRD.
    Combines Sidebar, HeaderBar, and QStackedWidget view container.
    """
    def __init__(self, db_manager, settings_manager, theme_controller):
        super().__init__()
        self.db_manager = db_manager
        self.settings_manager = settings_manager
        self.theme_controller = theme_controller
        self.task_controller = TaskController(self.db_manager)
        self.startup_reminder_dialogs: list = []
        self._world_clock_popover = None
        self.support_service = SupportService(self.settings_manager, self.db_manager)

        app = QApplication.instance()
        if app is not None:
            app.theme_controller = theme_controller

        self.language_service = LanguageService.instance(self.settings_manager)
        self.language_service.initialize()

        self.setWindowTitle("TODO BIRD — Offline Productivity Companion")
        self.setMinimumSize(900, 600)

        # Restore the persisted window geometry (it was saved on close but
        # never read back — every launch reset the window to 1200x800).
        try:
            saved_w = int(self.settings_manager.get("main_window_width", 1200) or 1200)
            saved_h = int(self.settings_manager.get("main_window_height", 800) or 800)
            saved_x = self.settings_manager.get("main_window_x", None)
            saved_y = self.settings_manager.get("main_window_y", None)
            from todo_bird_app.services.window_interaction_service import (
                WindowInteractionService,
            )
            from PySide6.QtCore import QRect as _QRect

            rect = _QRect(0, 0, max(900, saved_w), max(600, saved_h))
            if saved_x is not None and saved_y is not None:
                rect.moveTopLeft(_QPoint(int(saved_x), int(saved_y)))
            restored = WindowInteractionService.ensure_window_on_screen(
                rect, target_widget=self, min_width=900, min_height=600
            )
            self.setGeometry(restored)
        except Exception:
            self.resize(1200, 800)

        self.view_stack_map = {}
        self._init_ui()
        self._init_menu_bar()
        try:
            self.theme_controller.appearance_changed.connect(
                self._on_appearance_changed
            )
        except Exception:
            pass

        # Navigation Controller
        self.navigation_controller = NavigationController(self)
        self.sidebar.section_changed.connect(self.navigation_controller.set_active_section)

        # Register global keyboard shortcuts via CommandRegistry
        self.command_registry = CommandRegistry()
        self._register_global_shortcuts()

        # Initial view selection
        self.navigation_controller.set_active_section("dashboard")

        # Startup Greeting evaluation
        self._evaluate_startup_greeting()

        # Apply font density AFTER UI is fully created to ensure child widgets scale correctly
        self.apply_font_density(self.settings_manager.get("font_density", "comfortable"))

    def apply_font_density(self, density="comfortable"):
        """Legacy compatibility hook.

        UI density is owned by the appearance engine (the ``ui_density``
        setting drives QSS padding/metrics tokens at theme-apply time), so a
        separate font-density pass would fight it. Kept as a no-op for saved
        settings that may still carry the legacy ``font_density`` key.
        """
        return None

    def _register_global_shortcuts(self):
        """Register all global keyboard shortcuts via CommandRegistry."""
        reg = self.command_registry

        reg.register(
            command_id="new_task",
            display_name="Create New Task",
            callback=self.open_quick_add_dialog,
            shortcut="Ctrl+N",
            scope="global",
            tooltip="Open the new task creation dialog",
            parent=self,
            allow_override=True,
        )
        reg.register(
            command_id="open_command_palette",
            display_name="Command Palette",
            callback=self.open_command_palette,
            shortcut="Ctrl+K",
            scope="global",
            tooltip="Open the quick command palette",
            parent=self,
            allow_override=True,
        )
        reg.register(
            command_id="open_settings",
            display_name="Settings",
            callback=lambda: self.navigation_controller.set_active_section("settings"),
            shortcut="Ctrl+,",
            scope="global",
            tooltip="Navigate to application settings",
            parent=self,
            allow_override=True,
        )
        reg.register(
            command_id="quit_application",
            display_name="Quit Application",
            callback=self.close,
            shortcut="Ctrl+Q",
            scope="global",
            tooltip="Close Todo Bird",
            parent=self,
            allow_override=True,
        )
        reg.register(
            command_id="open_world_clock",
            display_name="World Clock",
            callback=self.open_world_clock_popover,
            shortcut="Ctrl+Alt+W",
            scope="global",
            tooltip="Open the interactive World Clock",
            parent=self,
            allow_override=True,
        )

        # Register rich-text local shortcuts for documentation/tooltip purposes
        for cmd_id, name, shortcut in [
            ("format_bold", "Bold", "Ctrl+B"),
            ("format_italic", "Italic", "Ctrl+I"),
            ("format_underline", "Underline", "Ctrl+U"),
        ]:
            reg.register(
                command_id=cmd_id,
                display_name=name,
                callback=lambda: None,  # Handled locally by RichTextEditor
                shortcut=shortcut,
                scope="local",
                tooltip=f"Toggle {name} formatting in rich text editor",
                allow_override=True,
            )

    def _init_ui(self):
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        # Mount background overlay beneath layout
        self.bg_overlay = BackgroundOverlayWidget(central_widget)
        self.bg_overlay.reload_from_settings(self.settings_manager)
        self.bg_overlay.lower()

        # Phase 1F.6.1 — adaptive navigation host architecture.
        #
        # Root is vertical so navigation can occupy Top / Bottom while the
        # middle body owns Left / Right placement around the main content.
        self.root_layout = QVBoxLayout(central_widget)
        self.root_layout.setContentsMargins(0, 0, 0, 0)
        self.root_layout.setSpacing(0)

        self.top_navigation_host = QWidget(central_widget)
        self.top_navigation_layout = QHBoxLayout(
            self.top_navigation_host
        )
        self.top_navigation_layout.setContentsMargins(0, 0, 0, 0)
        self.top_navigation_layout.setSpacing(0)
        self.root_layout.addWidget(
            self.top_navigation_host
        )

        self.body_container = QWidget(central_widget)
        self.body_layout = QHBoxLayout(
            self.body_container
        )
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(0)
        self.root_layout.addWidget(
            self.body_container,
            1,
        )

        self.left_navigation_host = QWidget(
            self.body_container
        )
        self.left_navigation_layout = QHBoxLayout(
            self.left_navigation_host
        )
        self.left_navigation_layout.setContentsMargins(
            0, 0, 0, 0
        )
        self.left_navigation_layout.setSpacing(0)

        self.right_navigation_host = QWidget(
            self.body_container
        )
        self.right_navigation_layout = QHBoxLayout(
            self.right_navigation_host
        )
        self.right_navigation_layout.setContentsMargins(
            0, 0, 0, 0
        )
        self.right_navigation_layout.setSpacing(0)

        self.body_layout.addWidget(
            self.left_navigation_host
        )

        # Main Content Panel (HeaderBar + Stacked Views)
        self.right_panel = QWidget(self.body_container)
        right_panel = self.right_panel
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # HeaderBar
        self.headerbar = HeaderBarWidget(self)
        self.headerbar.toggle_theme_requested.connect(self.theme_controller.toggle_theme)
        self.headerbar.quick_add_requested.connect(self.open_quick_add_dialog)
        self.headerbar.world_clock_requested.connect(self.open_world_clock_popover)
        self.headerbar.support_requested.connect(lambda: self._show_support_dialog(is_automatic=False))
        self.headerbar.diagnostics_requested.connect(self._show_diagnostics)
        self.headerbar.about_requested.connect(self._show_about)
        self.theme_controller.theme_changed.connect(self.headerbar.update_theme_icon)
        self.headerbar.update_theme_icon(self.theme_controller.current_mode)
        self.headerbar.language_selected.connect(self._on_language_selected)
        self.language_service.language_changed.connect(
            lambda _code: self._apply_language_to_chrome()
        )
        right_layout.addWidget(self.headerbar)

        # QStackedWidget Container
        self.stacked_widget = QStackedWidget(self)
        right_layout.addWidget(self.stacked_widget, 1)

        self.body_layout.addWidget(
            right_panel,
            1,
        )
        self.body_layout.addWidget(
            self.right_navigation_host
        )

        self.bottom_navigation_host = QWidget(
            central_widget
        )
        self.bottom_navigation_layout = QHBoxLayout(
            self.bottom_navigation_host
        )
        self.bottom_navigation_layout.setContentsMargins(
            0, 0, 0, 0
        )
        self.bottom_navigation_layout.setSpacing(0)
        self.root_layout.addWidget(
            self.bottom_navigation_host
        )

        # One navigation widget; MainWindow moves the SAME live widget
        # among host positions. Navigation state/signals are not rebuilt.
        self.sidebar = SidebarWidget(
            settings_manager=self.settings_manager,
            parent=self,
        )
        self.sidebar.navigation_preferences_changed.connect(
            self.apply_navigation_preferences
        )

        self.apply_navigation_preferences(
            self.sidebar.navigation_position,
            self.sidebar.navigation_style,
            self.sidebar.navigation_alignment,
        )

        # Register section views
        self._setup_views()

        # Periodic Reminder Evaluation Timer (Every 2 seconds)
        self._reminder_poll_timer = QTimer(self)
        self._reminder_poll_timer.setInterval(2000)
        self._reminder_poll_timer.timeout.connect(self._check_periodic_reminders)
        self._reminder_poll_timer.start()

    def _init_menu_bar(self):
        """
        Initializes native application menu bar with platform-standard shortcuts.
        On macOS, seamlessly binds to the global top Apple system menu bar.
        """
        import sys
        menubar = self.menuBar()
        menubar.setNativeMenuBar(True)

        # File Menu
        file_menu = menubar.addMenu("&File")

        act_new = QAction("&New Task...", self)
        act_new.setShortcut(QKeySequence.New)
        act_new.triggered.connect(self.open_quick_add_dialog)
        file_menu.addAction(act_new)

        act_palette = QAction("Command &Palette...", self)
        act_palette.setShortcut(QKeySequence("Ctrl+K"))
        act_palette.triggered.connect(self.open_command_palette)
        file_menu.addAction(act_palette)

        file_menu.addSeparator()

        act_export_csv = QAction("Export &CSV Report...", self)
        act_export_csv.triggered.connect(self.export_csv_report)
        file_menu.addAction(act_export_csv)

        act_export_pdf = QAction("Export &PDF Report...", self)
        act_export_pdf.triggered.connect(self.export_pdf_report)
        file_menu.addAction(act_export_pdf)

        file_menu.addSeparator()

        act_quit = QAction("&Quit TODO BIRD", self)
        act_quit.setShortcut(QKeySequence.Quit)
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

        # Edit Menu (Standard Clipboard & Undo)
        edit_menu = menubar.addMenu("&Edit")
        act_undo = QAction("&Undo", self)
        act_undo.setShortcut(QKeySequence.Undo)
        edit_menu.addAction(act_undo)

        act_redo = QAction("&Redo", self)
        act_redo.setShortcut(QKeySequence.Redo)
        edit_menu.addAction(act_redo)

        edit_menu.addSeparator()

        act_cut = QAction("Cu&t", self)
        act_cut.setShortcut(QKeySequence.Cut)
        edit_menu.addAction(act_cut)

        act_copy = QAction("&Copy", self)
        act_copy.setShortcut(QKeySequence.Copy)
        edit_menu.addAction(act_copy)

        act_paste = QAction("&Paste", self)
        act_paste.setShortcut(QKeySequence.Paste)
        edit_menu.addAction(act_paste)

        act_select_all = QAction("Select &All", self)
        act_select_all.setShortcut(QKeySequence.SelectAll)
        edit_menu.addAction(act_select_all)

        # View Menu
        view_menu = menubar.addMenu("&View")

        nav_items = [
            ("Dashboard", "dashboard", "1"),
            ("Inbox", "inbox", "2"),
            ("Today", "today", "3"),
            ("Gantt Timeline", "gantt", "4"),
            ("Projects", "projects", "5"),
            ("Calendar", "calendar", "6"),
            ("Analytics", "analytics", "7"),
            ("Settings", "settings", ","),
        ]
        for name, section, shortcut_key in nav_items:
            act_nav = QAction(f"&{name}", self)
            if shortcut_key == ",":
                act_nav.setShortcut(QKeySequence.Preferences)
            else:
                act_nav.setShortcut(QKeySequence(f"Ctrl+{shortcut_key}"))
            act_nav.triggered.connect(lambda checked=False, s=section: self.navigation_controller.set_active_section(s))
            view_menu.addAction(act_nav)

        view_menu.addSeparator()

        act_theme = QAction("Toggle &Theme Mode", self)
        act_theme.triggered.connect(self.theme_controller.toggle_theme)
        view_menu.addAction(act_theme)

        act_clock = QAction("&World Clock", self)
        act_clock.setShortcut(QKeySequence("Ctrl+Alt+W"))
        act_clock.triggered.connect(self.open_world_clock_popover)
        view_menu.addAction(act_clock)

        # Help Menu
        help_menu = menubar.addMenu("&Help")

        act_about = QAction("&About TODO BIRD", self)
        act_about.triggered.connect(self._show_about)
        help_menu.addAction(act_about)

        act_support = QAction("&Support & Feedback...", self)
        act_support.triggered.connect(lambda: self._show_support_dialog(is_automatic=False))
        help_menu.addAction(act_support)

        act_diag = QAction("System &Diagnostics...", self)
        act_diag.triggered.connect(self._show_diagnostics)
        help_menu.addAction(act_diag)

        # On non-macOS systems, hide in-window menu bar by default if header bar is present,
        # but let users access it via Alt hotkey (standard Windows/Linux UX pattern).
        if sys.platform != "darwin":
            menubar.setVisible(False)

    def _clear_navigation_host_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            # Never delete the sidebar widget; only detach layout ownership.

    def apply_navigation_preferences(
        self,
        position=None,
        style=None,
        alignment=None,
    ):
        """
        MainWindow is the physical navigation-placement authority.

        SidebarWidget owns appearance and destination behavior.
        MainWindow owns where that one live widget is mounted.
        """
        if not hasattr(self, "sidebar"):
            return

        position = str(
            position
            or self.settings_manager.get(
                "navigation_position",
                "left",
            )
            or "left"
        ).lower().strip()

        style = str(
            style
            or self.settings_manager.get(
                "navigation_style",
                "expanded",
            )
            or "expanded"
        ).lower().strip()

        alignment = str(
            alignment
            or self.settings_manager.get(
                "navigation_alignment",
                "left",
            )
            or "left"
        ).lower().strip()

        if position not in self.sidebar.VALID_POSITIONS:
            position = "left"

        if style not in self.sidebar.VALID_STYLES:
            style = "expanded"

        if alignment not in self.sidebar.VALID_ALIGNMENTS:
            alignment = "left"

        hosts = (
            (
                self.top_navigation_host,
                self.top_navigation_layout,
            ),
            (
                self.left_navigation_host,
                self.left_navigation_layout,
            ),
            (
                self.right_navigation_host,
                self.right_navigation_layout,
            ),
            (
                self.bottom_navigation_host,
                self.bottom_navigation_layout,
            ),
        )

        for host, layout in hosts:
            self._clear_navigation_host_layout(
                layout
            )
            host.hide()

        if position == "top":
            host = self.top_navigation_host
            layout = self.top_navigation_layout

        elif position == "right":
            host = self.right_navigation_host
            layout = self.right_navigation_layout

        elif position == "bottom":
            host = self.bottom_navigation_host
            layout = self.bottom_navigation_layout

        else:
            host = self.left_navigation_host
            layout = self.left_navigation_layout

        # Sidebar appearance updates without recursively re-emitting the
        # physical placement request.
        self.sidebar.apply_navigation_preferences(
            position,
            style,
            alignment,
            persist=False,
            emit_change=False,
        )

        if position in ("top", "bottom"):
            if alignment == "right":
                layout.addStretch(1)
                layout.addWidget(
                    self.sidebar
                )

            elif alignment == "center":
                layout.addStretch(1)
                layout.addWidget(
                    self.sidebar
                )
                layout.addStretch(1)

            else:
                layout.addWidget(
                    self.sidebar
                )
                layout.addStretch(1)

        else:
            layout.addWidget(
                self.sidebar
            )

        host.show()
        self.sidebar.show()

        self.settings_manager.set(
            "navigation_position",
            position,
        )
        self.settings_manager.set(
            "navigation_style",
            style,
        )
        self.settings_manager.set(
            "navigation_alignment",
            alignment,
        )

        if self.centralWidget():
            self.centralWidget().updateGeometry()

    def _check_periodic_reminders(self):
        """Periodically checks and pops up due scheduled or snoozed reminders."""
        if hasattr(self, "task_controller") and self.task_controller:
            from todo_bird_app.services.reminder_policy_service import ReminderPolicyService
            ReminderPolicyService.check_and_trigger_due_reminders(
                self, self.task_controller, self.settings_manager
            )

    def _setup_views(self):
        views_config = [
            ("dashboard", DashboardView(self.db_manager, self.settings_manager)),
            ("inbox", InboxView(self.db_manager, self.settings_manager)),
            ("today", TodayView(self.db_manager, self.settings_manager)),
            ("focus", FocusView(self.db_manager, self.settings_manager)),
            ("upcoming", UpcomingView(self.db_manager, self.settings_manager)),
            ("projects", ProjectsView(self.db_manager, self.settings_manager)),
            ("completed", CompletedView(self.db_manager, self.settings_manager)),
            ("calendar", CalendarView(self.db_manager, self.settings_manager)),
            (
                "gantt",
                GanttView(
                    self.db_manager,
                    self.settings_manager,
                    task_controller=self.task_controller,
                ),
            ),
            ("analytics", AnalyticsView(self.db_manager, self.settings_manager)),
            ("daily_review", DailyReviewView(self.db_manager, self.settings_manager)),
            ("feedback", PilotFeedbackView(self.db_manager, self.settings_manager)),
            ("world_clock", WorldClockView(self.db_manager, self.settings_manager)),
            ("settings", SettingsView(self.db_manager, self.settings_manager)),
        ]

        for key, view_widget in views_config:
            idx = self.stacked_widget.addWidget(view_widget)
            self.view_stack_map[key] = (idx, view_widget)
            setattr(self, f"{key}_view", view_widget)
            if hasattr(view_widget, "on_theme_changed"):
                self.theme_controller.theme_changed.connect(view_widget.on_theme_changed)

        self._on_appearance_changed(
            AppearanceService.read(
                self.settings_manager,
                app=QApplication.instance(),
            )
        )

    def _on_appearance_changed(self, appearance):
        if appearance is None:
            appearance = AppearanceService.read(
                self.settings_manager,
                app=QApplication.instance(),
            )

        self.update_background_overlay()

        for _, view_widget in getattr(self, "view_stack_map", {}).values():
            if hasattr(view_widget, "set_theme"):
                try:
                    view_widget.set_theme(
                        appearance.is_dark,
                        appearance.accent_color,
                    )
                except TypeError:
                    pass
            if hasattr(view_widget, "apply_appearance"):
                try:
                    view_widget.apply_appearance(appearance)
                except TypeError:
                    view_widget.apply_appearance()

        try:
            AppearanceService.apply_to_widget(self.headerbar, appearance)
            AppearanceService.apply_to_widget(self.sidebar, appearance)
        except Exception:
            pass

        self.updateGeometry()
        self.update()

    def open_quick_add_dialog(self, initial_title: str = ""):
        task_controller = self.task_controller
        projects = task_controller.get_all_projects()
        dlg = TaskDialog(projects, db_manager=self.db_manager, settings_manager=self.settings_manager, parent=self)
        if initial_title:
            dlg.title_input.setText(initial_title)
        if dlg.exec() == TaskDialog.Accepted:
            new_task = dlg.get_task()
            task_id = task_controller.add_task(new_task)

            # -------------------------------------------------
            # Recursive hierarchy persistence for BRAND-NEW tasks.
            #
            # Previously this path saved only first-level title,
            # completed flag and position. Sub-subtasks and rich
            # metadata were silently lost.
            # -------------------------------------------------
            def save_new_hierarchy(
                nodes,
                parent_subtask_id=None,
            ):
                for fallback_position, subtask in enumerate(nodes):
                    position = int(
                        subtask.get(
                            "position",
                            fallback_position,
                        )
                    )

                    new_subtask_id = (
                        self.db_manager.insert_subtask(
                            task_id=task_id,
                            title=subtask.get(
                                "title",
                                "",
                            ),
                            is_completed=bool(
                                subtask.get(
                                    "is_completed",
                                    False,
                                )
                            ),
                            position=position,
                            parent_subtask_id=parent_subtask_id,
                            description=subtask.get(
                                "description",
                                "",
                            ),
                            planned_date=subtask.get(
                                "planned_date"
                            ),
                            due_date=subtask.get(
                                "due_date"
                            ),
                            planned_start_time=subtask.get(
                                "planned_start_time"
                            ),
                            planned_end_time=subtask.get(
                                "planned_end_time"
                            ),
                            estimated_duration=int(
                                subtask.get(
                                    "estimated_duration"
                                )
                                or 0
                            ),
                            priority=subtask.get(
                                "priority",
                                "Medium",
                            ),
                            progress=int(
                                subtask.get(
                                    "progress"
                                )
                                or 0
                            ),
                            show_in_gantt=bool(
                                subtask.get(
                                    "show_in_gantt",
                                    False,
                                )
                            ),

                            # Migration v8 nested pin data
                            is_pinned=bool(
                                subtask.get(
                                    "is_pinned",
                                    False,
                                )
                            ),
                            pin_color=subtask.get(
                                "pin_color",
                                "#E95420",
                            ),
                            pin_position=int(
                                subtask.get(
                                    "pin_position"
                                )
                                or 0
                            ),
                        )
                    )

                    # insert_subtask returns the newly-created id
                    # in the current DB implementation.
                    if new_subtask_id is None:
                        raise RuntimeError(
                            "Unable to create hierarchy item: "
                            + subtask.get(
                                "title",
                                "Untitled",
                            )
                        )

                    save_new_hierarchy(
                        subtask.get(
                            "children",
                            [],
                        ),
                        new_subtask_id,
                    )

            save_new_hierarchy(
                dlg.get_pending_subtasks()
            )

            self.navigation_controller.refresh_active_view()
            ToastBanner.show_message(self, f"Task '{new_task.title}' created successfully!", "success")

    def open_command_palette(self):
        palette = CommandPalette(self.db_manager, parent=self)
        palette.action_triggered.connect(self.handle_command_palette_action)
        palette.exec()

    def handle_command_palette_action(self, action_type: str, payload: Any):
        if action_type == "navigate":
            self.navigation_controller.set_active_section(str(payload))
        elif action_type == "create_task":
            self.open_quick_add_dialog()
        elif action_type == "quick_create":
            self.open_quick_add_dialog(initial_title=str(payload))
        elif action_type == "custom_action":
            code = str(payload)
            if code == "toggle_theme":
                self.theme_controller.toggle_theme()
            elif code == "export_pdf":
                self.export_pdf_report()
            elif code == "export_csv":
                self.export_csv_report()
            elif code == "open_world_clock":
                self.open_world_clock_popover()

    def _on_language_selected(self, code: str):
        """Header-bar language menu: switch, persist, retranslate chrome."""
        changed = self.language_service.set_language(code)
        if changed != code:
            return

    def _apply_language_to_chrome(self):
        """Retranslate every live chrome surface after a language change."""
        try:
            self.headerbar.retranslate_ui()
        except Exception:
            pass
        try:
            self.sidebar.retranslate_ui()
        except Exception:
            pass
        try:
            self._retranslate_menu_bar()
        except Exception:
            pass
        try:
            settings_view = getattr(self, "settings_view", None)
            if settings_view is not None and hasattr(settings_view, "retranslate_ui"):
                settings_view.retranslate_ui()
        except Exception:
            pass
        try:
            from todo_bird_app.widgets.toast_banner import ToastBanner
            ToastBanner.show_message(
                self,
                LanguageService.instance().t("Language updated"),
                "success",
            )
        except Exception:
            pass

    def _retranslate_menu_bar(self):
        """Rewrite the menu bar labels in the active language."""
        menubar = self.menuBar()
        menus = menubar.actions()
        if not menus:
            return
        labels = ["&File", "&Edit", "&View", "&Help"]
        for action, label in zip(menus, labels):
            action.setText(LanguageService.instance().t(label))

    def open_world_clock_popover(self):
        """Opens or toggles the persistent World Clock Popover."""
        # The popover uses WA_DeleteOnClose: after its first close the C++
        # object is gone while self._world_clock_popover still holds a dead
        # wrapper, and isVisible() on it raised RuntimeError — every click
        # after the first open/close cycle silently died. Validate first.
        pop = getattr(self, "_world_clock_popover", None)
        if pop is not None:
            alive = True
            try:
                alive = pop.isVisible()
            except RuntimeError:
                alive = False
            if alive:
                pop.close()
                return
            self._world_clock_popover = None

        from todo_bird_app.ui.components.world_clock_popover import WorldClockPopover
        self._world_clock_popover = WorldClockPopover(
            settings_manager=self.settings_manager,
            parent=self,
            is_dark=self.theme_controller.current_mode == "dark",
        )
        # Clear the reference the moment the widget is destroyed so the
        # toggle above can never see a dangling wrapper again.
        self._world_clock_popover.destroyed.connect(
            lambda: setattr(self, "_world_clock_popover", None)
        )

        # Drop the popover from the World Clock button (top-right), GNOME-style.
        pop_w = self._world_clock_popover.width()
        pop_h = self._world_clock_popover.height()
        try:
            btn = self.headerbar.clock_btn
            anchor = btn.mapToGlobal(QPoint(btn.width() - pop_w // 2, btn.height() + 6))
        except Exception:
            anchor = self.geometry().topLeft() + QPoint(
                max(10, (self.width() - pop_w) // 2), 65
            )

        from PySide6.QtGui import QGuiApplication
        screen = QGuiApplication.screenAt(anchor + QPoint(pop_w // 2, 0))
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            x = max(avail.left() + 8, min(anchor.x(), avail.right() - pop_w - 8))
            y = max(avail.top() + 8, min(anchor.y(), avail.bottom() - pop_h - 8))
        else:
            x, y = max(10, anchor.x()), max(10, anchor.y())
        self._world_clock_popover.move(x, y)
        self._world_clock_popover.show()

    def export_pdf_report(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Export PDF Performance Report", "todo_bird_report.pdf", "PDF Files (*.pdf)")
        if file_path:
            success = ReportExporterService.export_analytics_to_pdf(self.db_manager, file_path)
            if success:
                QMessageBox.information(self, "Export Success", f"Report successfully exported to:\n{file_path}")
            else:
                QMessageBox.warning(self, "Export Failed", "Failed to generate PDF report.")

    def export_csv_report(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Export CSV Tasks Data", "todo_bird_tasks.csv", "CSV Files (*.csv)")
        if file_path:
            success = ReportExporterService.export_tasks_to_csv(self.db_manager, file_path)
            if success:
                QMessageBox.information(self, "Export Success", f"Tasks data successfully exported to:\n{file_path}")
            else:
                QMessageBox.warning(self, "Export Failed", "Failed to export CSV file.")

    def update_background_overlay(self):
        if hasattr(self, "bg_overlay") and self.bg_overlay is not None:
            view_id = None
            nav = getattr(self, "navigation_controller", None)
            if nav is not None:
                view_id = getattr(nav, "current_section", None)
            self.bg_overlay.reload_from_settings(
                self.settings_manager,
                view_id=view_id,
            )
            if self.centralWidget():
                self.bg_overlay.setGeometry(self.centralWidget().rect())
                self.bg_overlay.lower()
                self.centralWidget().update()
            self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "bg_overlay") and self.bg_overlay is not None and self.centralWidget():
            self.bg_overlay.setGeometry(self.centralWidget().rect())
            self.bg_overlay.lower()

    def _evaluate_startup_greeting(self):
        try:
            if CompanionService.should_show_greeting(self.settings_manager):
                # Mark shown for today / session
                CompanionService.mark_greeting_shown(self.settings_manager)
        except Exception as e:
            logger.debug(f"Startup greeting evaluation skipped: {e}")

    # ── Help / Support ───────────────────────────────────────────────────────

    def _show_support_dialog(self, is_automatic=False):
        dialog = SupportTodoBirdDialog(
            support_service=self.support_service,
            parent=self,
            is_automatic_prompt=is_automatic
        )
        dialog.exec()

    def _show_diagnostics(self):
        try:
            bundle_path = SupportBundleService.generate_support_bundle()
            QMessageBox.information(
                self,
                "Diagnostics Generated",
                f"A support bundle containing non-sensitive diagnostics and logs has been generated.\n\n"
                f"Location:\n{bundle_path}\n\n"
                f"Please attach this file if you are reporting a problem."
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to generate support bundle:\n{e}")

    def _show_about(self):
        from todo_bird_app.__version__ import __version__, APP_NAME, RELEASE_STAGE
        QMessageBox.about(
            self,
            "About Todo Bird",
            f"<b>{APP_NAME}</b><br>"
            f"Version: {__version__} ({RELEASE_STAGE})<br><br>"
            f"Offline-first, desktop-first productivity and scheduling."
        )

    def closeEvent(self, event):
        """
        Deterministic application shutdown path:
        - Reentrancy guard prevents recursive execution
        - Persists state and geometry
        - Stops view timers and active background workers
        - Cleans up desktop companion
        - Closes all registered modeless/floating windows and transient dialogs
        - Cleans up reminders
        - Accepts event cleanly
        """
        if getattr(self, "_shutdown_in_progress", False):
            event.accept()
            return
        self._shutdown_in_progress = True

        try:
            logger.info("MainWindow: Initiating clean application shutdown...")

            try:
                QToolTip.hideText()
            except Exception:
                pass

            try:
                self.theme_controller.appearance_changed.disconnect(
                    self._on_appearance_changed
                )
            except Exception:
                pass

            try:
                self.theme_controller.theme_changed.disconnect(
                    self.headerbar.update_theme_icon
                )
            except Exception:
                pass

            try:
                self.headerbar.toggle_theme_requested.disconnect(
                    self.theme_controller.toggle_theme
                )
            except Exception:
                pass

            for _, view in getattr(self, "view_stack_map", {}).values():
                on_theme_changed = getattr(view, "on_theme_changed", None)
                if callable(on_theme_changed):
                    try:
                        self.theme_controller.theme_changed.disconnect(
                            on_theme_changed
                        )
                    except Exception:
                        pass

            # 1. Persist window geometry
            if self.settings_manager:
                self.settings_manager.set("main_window_width", self.width())
                self.settings_manager.set("main_window_height", self.height())
                self.settings_manager.set("main_window_x", self.x())
                self.settings_manager.set("main_window_y", self.y())

            # 2. Stop active view timers (e.g. GanttChartWidget, FocusView)
            if hasattr(self, "view_stack_map") and self.view_stack_map:
                for _, view in self.view_stack_map.values():
                    if hasattr(view, "cleanup"):
                        try:
                            view.cleanup()
                        except Exception as e:
                            logger.debug(f"Error cleaning view on shutdown: {e}")

            # 3. Cleanup Desktop Companion
            if hasattr(self, "desktop_companion") and self.desktop_companion is not None:
                try:
                    self.desktop_companion.cleanup()
                except Exception as e:
                    logger.debug(f"Error cleaning desktop companion on shutdown: {e}")
                self.desktop_companion = None

            # 4. Close all registered floating, companion, reminder, and top-level dialog windows
            from todo_bird_app.services.window_registry import WindowRegistry
            WindowRegistry.close_all_on_shutdown()

            # 5. Clean up startup reminder dialogs list
            if hasattr(self, "startup_reminder_dialogs") and self.startup_reminder_dialogs:
                for dlg in list(self.startup_reminder_dialogs):
                    try:
                        dlg.close()
                        dlg.deleteLater()
                    except Exception:
                        pass
                self.startup_reminder_dialogs.clear()

            # 6. Clear global shortcuts
            if hasattr(self, "command_registry") and self.command_registry is not None:
                try:
                    self.command_registry.clear_shortcuts()
                except Exception:
                    pass

            # 7. Stop periodic reminder poll timer
            if hasattr(self, "_reminder_poll_timer") and self._reminder_poll_timer is not None:
                try:
                    self._reminder_poll_timer.stop()
                except Exception:
                    pass

            # 8. Close single instance socket server if attached
            app_inst = QApplication.instance()
            if app_inst and hasattr(app_inst, "_single_instance_server") and app_inst._single_instance_server is not None:
                try:
                    app_inst._single_instance_server.close()
                    app_inst._single_instance_server = None
                except Exception:
                    pass

            if app_inst and getattr(app_inst, "theme_controller", None) is self.theme_controller:
                try:
                    app_inst.theme_controller = None
                except Exception:
                    pass

            event.accept()
        except Exception as e:
            logger.error(f"Error during MainWindow closeEvent: {e}", exc_info=True)
            event.accept()
