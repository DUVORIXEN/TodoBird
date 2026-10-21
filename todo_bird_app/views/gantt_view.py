import logging
import json
import os
from typing import Optional, List, Dict, Any
from datetime import date, datetime
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox, QCheckBox,
    QFrame, QFileDialog, QMessageBox, QScrollArea, QDateEdit, QSplitter,
    QListView, QWidget, QMenu, QWidgetAction, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer, QCoreApplication, QDate, QPoint
from PySide6.QtGui import QPixmap, QImage, QPainter, QShortcut, QKeySequence

from todo_bird_app.views.base_view import BaseView
from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.models.task import Task, TaskPriority, TaskStatus
from todo_bird_app.controllers.delay_engine import DelayEngine, TimingStatus
from todo_bird_app.gantt.gantt_chart import GanttChartWidget
from todo_bird_app.gantt.gantt_theme import GanttColorProfile
from todo_bird_app.gantt.timescale_engine import ZoomLevel
from todo_bird_app.widgets.task_dialog import TaskDialog
from todo_bird_app.widgets.subtask_dialog import SubtaskDialog
from todo_bird_app.ui.components.schedule_details_popover import ScheduleDetailsPopover
from todo_bird_app.services.schedule_details_formatter import ScheduleDetailsFormatter
from todo_bird_app.widgets.toast_banner import ToastBanner
from todo_bird_app.widgets.justification_dialog import DelayJustificationDialog
from todo_bird_app.voice.appreciation import AppreciationSystem
from todo_bird_app.voice.voice_engine import VoiceEngine
from todo_bird_app.gantt.gantt_dependency_engine import GanttDependencyEngine
from todo_bird_app.gantt.gantt_left_pane import (
    GanttLeftPaneModel,
    GanttLeftPaneDelegate,
    GanttLeftPaneListView,
)
from todo_bird_app.services.wbs_service import EntityRef, WBSService
from todo_bird_app.services.gantt_wbs_adapter import GanttWBSAdapter
from todo_bird_app.ui.components.modern_combobox import ModernComboBox
from todo_bird_app.ui.components.modern_checkbox import ModernCheckBox
from todo_bird_app.ui.components.modern_button import ModernButton, ButtonStyleDesign, ButtonVariant
from todo_bird_app.services.appearance_service import semantic_tokens_for

logger = logging.getLogger(__name__)

class GanttView(BaseView):
    """
    Enhanced Gantt View with Multi-Year TimescaleEngine, timeline navigation (Prev/Next/Today),
    Gantt theme modes, Plan vs Actual legends, and image export.
    """
    def __init__(
        self,
        db_manager,
        settings_manager=None,
        parent=None,
        task_controller=None,
    ):
        if isinstance(db_manager, TaskController) and settings_manager is None:
            task_controller = db_manager
            db_manager = task_controller.db_manager
            from todo_bird_app.settings.settings_manager import SettingsManager
            settings_manager = SettingsManager(db_manager)

        super().__init__(
            db_manager,
            settings_manager,
            title="Gantt Timeline",
            subtitle="Interactive timeline & Plan vs Actual comparison",
            parent=parent,
            typography_area="gantt",
        )

        # Phase 1D: consume MainWindow's canonical TaskController whenever
        # supplied. Fallback preserves standalone/test construction.
        self._owns_task_controller = task_controller is None
        self._cleaned_up = False
        self.task_controller = (
            task_controller
            if task_controller is not None
            else TaskController(db_manager)
        )
        self._connect_task_controller_signal("tasks_changed", self.refresh_data)

        # Phase 1D hierarchy presentation state.
        raw_collapsed = self.settings_manager.get(
            "gantt_collapsed_wbs_keys",
            [],
        )
        if not isinstance(raw_collapsed, (list, tuple, set)):
            raw_collapsed = []

        self._gantt_collapsed_keys = {
            str(value)
            for value in raw_collapsed
            if value
        }

        self.delay_engine = DelayEngine(settings_manager)
        self.voice_engine = VoiceEngine(settings_manager)
        self.appreciation_system = AppreciationSystem(settings_manager, self.voice_engine)

        self.color_profile = GanttColorProfile()

        # Avoid repeatedly interrupting the operator for the same
        # overdue task during one Todo Bird session.
        self._overdue_prompted_ids = set()
        self._suppress_overdue_prompts = False
        self._overdue_prompt_in_progress = False
        self.current_project_id = self.settings_manager.get("gantt_selected_project_id", None)
        self.selected_compare_version_id = self.settings_manager.get("gantt_selected_compare_version_id", "original")

        self._init_ui()
        self.populate_project_combo()
        self.populate_compare_version_combo()
        self.refresh_data()
        self._sync_gantt_toolbar_typography_height()

    def _load_gantt_profile(self):
        mode = self.settings_manager.get("gantt_theme_mode", "follow_app")
        custom_colors = self.settings_manager.get("gantt_custom_colors", {})
        self.color_profile = GanttColorProfile(mode=mode, colors=custom_colors)

    def _init_ui(self):
        # 1. Primary Toolbar Frame
        toolbar = QFrame()
        toolbar.setObjectName("CardWidget")
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(12, 8, 12, 8)
        tb_layout.setSpacing(8)
        tb_layout.setAlignment(Qt.AlignVCenter)

        def _make_sep() -> QFrame:
            sep = QFrame()
            sep.setObjectName("GanttToolbarSeparator")
            sep.setFrameShape(QFrame.VLine)
            sep.setFrameShadow(QFrame.Plain)
            sep.setFixedHeight(24)
            return sep

        def _add_menu_row(menu: QMenu, label_text: str, widget: QWidget):
            row = QWidget(menu)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(10, 6, 10, 6)
            row_layout.setSpacing(8)
            if label_text:
                label = QLabel(label_text, row)
                label.setMinimumWidth(92)
                row_layout.addWidget(label)
            row_layout.addWidget(widget, 1)
            action = QWidgetAction(menu)
            action.setDefaultWidget(row)
            menu.addAction(action)
            return action

        def _popup_menu(button: QWidget, menu: QMenu):
            menu.popup(button.mapToGlobal(QPoint(0, button.height() + 2)))

        # --- Group 1: Project Scope & Baseline Governance ---
        lbl_proj = QLabel("Project:")
        lbl_proj.setAlignment(Qt.AlignVCenter)
        tb_layout.addWidget(lbl_proj)

        self.project_combo = ModernComboBox()
        self.project_combo.setMinimumWidth(130)
        self.project_combo.setMaximumWidth(220)
        self.project_combo.setSizePolicy(
            QSizePolicy.Preferred,
            QSizePolicy.Fixed,
        )
        self.project_combo.setToolTip("Select project schedule for Gantt view")
        self.project_combo.currentIndexChanged.connect(self.on_gantt_project_changed)
        tb_layout.addWidget(self.project_combo)

        lbl_compare = QLabel("Compare Current Against:")
        lbl_compare.setAlignment(Qt.AlignVCenter)
        tb_layout.addWidget(lbl_compare)

        self.compare_version_combo = ModernComboBox()
        self.compare_version_combo.setMinimumWidth(150)
        self.compare_version_combo.setMaximumWidth(260)
        self.compare_version_combo.setSizePolicy(
            QSizePolicy.Preferred,
            QSizePolicy.Fixed,
        )
        self.compare_version_combo.setToolTip("Select schedule baseline / approved revision for variance comparison")
        self.compare_version_combo.currentIndexChanged.connect(self.on_gantt_compare_version_changed)
        tb_layout.addWidget(self.compare_version_combo)

        # --- Separator ---
        tb_layout.addSpacing(4)
        tb_layout.addWidget(_make_sep())
        tb_layout.addSpacing(4)

        # --- Group 2: Primary Project Actions (Fit Project & Refresh) ---
        self.fit_project_btn = ModernButton("Fit Project", variant=ButtonVariant.SECONDARY)
        self.fit_project_btn.setToolTip("Fit Gantt timeline extent to selected project dates")
        self.fit_project_btn.clicked.connect(self.fit_project_timeline)
        tb_layout.addWidget(self.fit_project_btn)

        self.refresh_btn = ModernButton("⟳ Refresh", variant=ButtonVariant.SECONDARY)
        self.refresh_btn.setToolTip("Refresh Gantt\nRecalculate and redraw the current project schedule.")
        self.refresh_btn.setAccessibleName("Refresh Gantt")
        self.refresh_btn.clicked.connect(self.trigger_refresh)
        tb_layout.addWidget(self.refresh_btn)

        self.wbs_nav_btn = ModernButton("WBS", variant=ButtonVariant.SECONDARY)
        self.wbs_nav_btn.setToolTip("Switch to WBS Hierarchy view for this project")
        self.wbs_nav_btn.clicked.connect(self._navigate_to_wbs)
        tb_layout.addWidget(self.wbs_nav_btn)

        # Keyboard shortcut F5 for refresh
        self.refresh_shortcut = QShortcut(QKeySequence(Qt.Key_F5), self)
        self.refresh_shortcut.activated.connect(self.trigger_refresh)

        # --- Separator ---
        tb_layout.addSpacing(4)
        tb_layout.addWidget(_make_sep())
        tb_layout.addSpacing(4)

        # --- Group 3: Timeline Navigation & Zoom ---
        lbl_zoom = QLabel("Zoom:")
        lbl_zoom.setAlignment(Qt.AlignVCenter)
        tb_layout.addWidget(lbl_zoom)

        self.zoom_combo = ModernComboBox()
        self.zoom_combo.addItems(["Hourly", "Daily", "Weekly", "Monthly", "Yearly", "Multi-Year"])
        self.zoom_combo.setCurrentText("Daily")
        self.zoom_combo.currentTextChanged.connect(self.on_zoom_changed)
        tb_layout.addWidget(self.zoom_combo)

        self.prev_btn = ModernButton("◀ Prev", variant=ButtonVariant.SECONDARY)
        self.prev_btn.setToolTip("Navigate to previous period (Day/Week/Month/Year)")
        self.prev_btn.clicked.connect(lambda: self.navigate_period(-1))

        self.date_picker = QDateEdit()
        self.date_picker.setMinimumHeight(30)
        self.date_picker.setMaximumHeight(16777215)
        self.date_picker.setCalendarPopup(True)
        self.date_picker.setDisplayFormat("yyyy-MM-dd")
        self.date_picker.setDate(QDate.currentDate())
        self.date_picker.setToolTip("Jump directly to date")
        self.date_picker.dateChanged.connect(self.on_date_picker_changed)

        self.next_btn = ModernButton("Next ▶", variant=ButtonVariant.SECONDARY)
        self.next_btn.setToolTip("Navigate to next period (Day/Week/Month/Year)")
        self.next_btn.clicked.connect(lambda: self.navigate_period(1))

        self.today_btn = ModernButton("Today", variant=ButtonVariant.SECONDARY)
        self.today_btn.setToolTip("Center the Gantt timeline on today")
        self.today_btn.setAccessibleName("Go to today")
        self.today_btn.clicked.connect(self.go_to_today)
        tb_layout.addWidget(self.today_btn)

        self.current_period_lbl = QLabel(date.today().strftime('%a, %d %b %Y'))
        self.current_period_lbl.setAlignment(Qt.AlignVCenter)
        self.current_period_lbl.setStyleSheet(
            "color: #3584E4; font-weight: bold; padding: 2px 6px;"
        )

        self.earlier_task_btn = ModernButton(
            "◀ Earlier", variant=ButtonVariant.SECONDARY
        )
        self.earlier_task_btn.setToolTip(
            "Move selected task earlier — "
            "Hourly 15 min • Daily 1 day • "
            "Weekly 1 week • Monthly 1 month"
        )
        self.earlier_task_btn.clicked.connect(
            lambda: self.nudge_selected_gantt_task(-1)
        )

        self.later_task_btn = ModernButton(
            "Later ▶", variant=ButtonVariant.SECONDARY
        )
        self.later_task_btn.setToolTip(
            "Move selected task later — "
            "Hourly 15 min • Daily 1 day • "
            "Weekly 1 week • Monthly 1 month"
        )
        self.later_task_btn.clicked.connect(
            lambda: self.nudge_selected_gantt_task(1)
        )

        self.timeline_menu = QMenu(self)
        _add_menu_row(self.timeline_menu, "", self.current_period_lbl)
        _add_menu_row(self.timeline_menu, "Jump Date", self.date_picker)
        _add_menu_row(self.timeline_menu, "Previous", self.prev_btn)
        _add_menu_row(self.timeline_menu, "Next", self.next_btn)
        _add_menu_row(self.timeline_menu, "Task Earlier", self.earlier_task_btn)
        _add_menu_row(self.timeline_menu, "Task Later", self.later_task_btn)

        self.timeline_options_btn = ModernButton(
            "Timeline",
            variant=ButtonVariant.SECONDARY,
        )
        self.timeline_options_btn.setAccessibleName("Gantt timeline options")
        self.timeline_options_btn.setToolTip("Timeline navigation and selected-task nudges")
        self.timeline_options_btn.clicked.connect(
            lambda: _popup_menu(
                self.timeline_options_btn,
                self.timeline_menu,
            )
        )
        tb_layout.addWidget(self.timeline_options_btn)

        # --- Separator ---
        tb_layout.addSpacing(4)
        tb_layout.addWidget(_make_sep())
        tb_layout.addSpacing(4)

        # --- Group 4: Visual Preferences & Export ---
        lbl_theme = QLabel("Theme:")
        lbl_theme.setAlignment(Qt.AlignVCenter)

        self.theme_combo = ModernComboBox()
        self.theme_combo.addItems(["Follow App", "Light", "Dark", "High Contrast", "Custom"])
        mode_text = self.color_profile.mode.replace("_", " ").title()
        self.theme_combo.setCurrentText(mode_text)
        self.theme_combo.currentTextChanged.connect(self.on_gantt_theme_changed)

        lbl_bar = QLabel("Bar:")
        lbl_bar.setAlignment(Qt.AlignVCenter)

        self.bar_style_combo = ModernComboBox()
        bar_styles = [
            ("Rounded Premium", "rounded"),
            ("Arrow / Chevron", "arrow"),
            ("Bevel", "bevel"),
            ("3D Raised", "3d"),
            ("Capsule", "capsule"),
            ("Executive Glass", "glass"),
        ]

        for label, value in bar_styles:
            self.bar_style_combo.addItem(label, value)

        saved_bar_style = str(self.settings_manager.get("gantt_bar_style", "rounded"))
        idx = self.bar_style_combo.findData(saved_bar_style)
        if idx >= 0:
            self.bar_style_combo.setCurrentIndex(idx)

        self.bar_style_combo.currentIndexChanged.connect(self.on_gantt_bar_style_changed)

        lbl_plan_col = QLabel("Plan Color:")
        lbl_plan_col.setAlignment(Qt.AlignVCenter)

        self.plan_color_combo = ModernComboBox()
        planned_colors = [
            (" Blue", "#3584E4"),
            (" Royal Blue", "#1D4ED8"),
            (" Purple", "#7C3AED"),
            (" Teal", "#0891B2"),
            (" Green", "#059669"),
            (" Orange", "#EA580C"),
            (" Graphite", "#4B5563"),
        ]

        for label, color in planned_colors:
            self.plan_color_combo.addItem(label, color)

        saved_plan_color = str(
            self.settings_manager.get(
                "gantt_planned_bar_color",
                "#3584E4",
            )
        )
        color_index = self.plan_color_combo.findData(saved_plan_color)
        if color_index >= 0:
            self.plan_color_combo.setCurrentIndex(color_index)
        self.plan_color_combo.currentIndexChanged.connect(self.on_gantt_plan_color_changed)

        lbl_btn_style = QLabel("Button Style:")
        lbl_btn_style.setAlignment(Qt.AlignVCenter)

        self.button_design_combo = ModernComboBox()
        b_styles = [
            ("3D Raised / Glass", "3d_raised"),
            ("Flat Modern", "flat"),
            ("Executive Soft 3D", "executive_soft"),
            ("Neumorphic 3D", "neumorphic"),
            ("Glow Outline", "glow"),
        ]
        for b_lbl, b_val in b_styles:
            self.button_design_combo.addItem(b_lbl, b_val)
        saved_b = str(self.settings_manager.get("button_design_mode", "3d_raised"))
        b_i = self.button_design_combo.findData(saved_b)
        if b_i >= 0:
            self.button_design_combo.setCurrentIndex(b_i)
        self.button_design_combo.currentIndexChanged.connect(self.on_button_design_changed)

        self.auto_shift_dependencies_checkbox = ModernCheckBox(
            " Auto-shift successors"
        )
        raw_auto_shift = self.settings_manager.get("gantt_auto_shift_dependencies", False)
        if isinstance(raw_auto_shift, bool):
            auto_shift_enabled = raw_auto_shift
        else:
            auto_shift_enabled = str(raw_auto_shift).strip().lower() in ("1", "true", "yes", "on")

        self.auto_shift_dependencies_checkbox.setChecked(auto_shift_enabled)
        self.auto_shift_dependencies_checkbox.setToolTip(
            "When enabled, moving or resizing a predecessor "
            "automatically shifts Finish→Start successors only "
            "when required to remove dependency violations. "
            "Dependency cycles are never auto-shifted."
        )
        self.auto_shift_dependencies_checkbox.toggled.connect(
            self.on_auto_shift_dependencies_changed
        )

        self.export_btn = ModernButton(" Export", variant=ButtonVariant.SECONDARY)
        self.export_btn.clicked.connect(self.export_chart_image)

        self.appearance_menu = QMenu(self)
        _add_menu_row(self.appearance_menu, "Theme", self.theme_combo)
        _add_menu_row(self.appearance_menu, "Bar Style", self.bar_style_combo)
        _add_menu_row(self.appearance_menu, "Plan Color", self.plan_color_combo)
        _add_menu_row(self.appearance_menu, "Button Style", self.button_design_combo)
        _add_menu_row(self.appearance_menu, "", self.auto_shift_dependencies_checkbox)
        _add_menu_row(self.appearance_menu, "", self.export_btn)

        self.appearance_options_btn = ModernButton(
            "Appearance",
            variant=ButtonVariant.SECONDARY,
        )
        self.appearance_options_btn.setAccessibleName("Gantt appearance options")
        self.appearance_options_btn.setToolTip("Gantt theme, bars, colors, button style and export")
        self.appearance_options_btn.clicked.connect(
            lambda: _popup_menu(
                self.appearance_options_btn,
                self.appearance_menu,
            )
        )
        tb_layout.addWidget(self.appearance_options_btn)

        tb_layout.addStretch()

        # --- Group 5: View Layer Toggles ---
        self.cb_actual = ModernCheckBox("Actual Bars")
        self.cb_actual.setChecked(True)
        self.cb_actual.toggled.connect(self.on_filter_changed)

        self.cb_completed = ModernCheckBox("Completed")
        self.cb_completed.setChecked(True)
        self.cb_completed.toggled.connect(self.on_filter_changed)

        self.layers_menu = QMenu(self)
        _add_menu_row(self.layers_menu, "", self.cb_actual)
        _add_menu_row(self.layers_menu, "", self.cb_completed)

        self.layers_btn = ModernButton(
            "Layers",
            variant=ButtonVariant.SECONDARY,
        )
        self.layers_btn.setAccessibleName("Gantt layer options")
        self.layers_btn.setToolTip("Show or hide Gantt plan, actual, and completed layers")
        self.layers_btn.clicked.connect(
            lambda: _popup_menu(
                self.layers_btn,
                self.layers_menu,
            )
        )
        tb_layout.addWidget(self.layers_btn)

        # Wrap the toolbar in a horizontal QScrollArea so narrow
        # windows get a scrollbar instead of overlapping controls.
        # Widgets/signals above are untouched; self.* attributes
        # remain on the view (the scroll area only reparents the frame).
        toolbar.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        toolbar.setMinimumWidth(toolbar.sizeHint().width())
        toolbar_scroll = QScrollArea()
        toolbar_scroll.setWidgetResizable(False)
        toolbar_scroll.setFrameShape(QFrame.NoFrame)
        toolbar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        toolbar_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        toolbar_scroll.setFixedHeight(
            toolbar.sizeHint().height() + 10
        )
        toolbar_scroll.setWidget(toolbar)
        toolbar.setMinimumWidth(toolbar.sizeHint().width())

        # Typography can change after construction. Keep the toolbar
        # viewport synchronized with its final child-control height.
        self._gantt_toolbar = toolbar
        self._gantt_toolbar_scroll = toolbar_scroll

        try:
            from todo_bird_app.controllers.task_controller import (
                _GLOBAL_EVENT_BUS,
            )

            _GLOBAL_EVENT_BUS.typography_changed.connect(
                self._sync_gantt_toolbar_typography_height
            )
            self._gantt_toolbar_typography_connected = True
        except Exception:
            pass

        self.main_layout.addWidget(toolbar_scroll)

        # Action Feedback Status Banner
        self.status_banner = QLabel("")
        self.status_banner.setStyleSheet(
            "font-weight: 600; color: #10B981; padding: 2px 12px;"
        )
        self.status_banner.setVisible(False)
        self.main_layout.addWidget(self.status_banner)

        # 2. Status Color Legend Bar
        # -------------------------------------------------
        # Executive Gantt health ribbon
        # -------------------------------------------------
        self.health_frame = QFrame()
        self.health_frame.setObjectName(
            "CardWidget"
        )

        health_layout = QHBoxLayout(
            self.health_frame
        )
        health_layout.setContentsMargins(
            12, 6, 12, 6
        )
        health_layout.setSpacing(14)

        self.health_title = QLabel(
            "Schedule Health"
        )
        self.health_title.setStyleSheet(
            "font-weight: 700;"
        )
        health_layout.addWidget(
            self.health_title
        )

        self.kpi_labels = {}

        for key, label in [
            ("overdue", "Overdue"),
            ("at_risk", "At Risk"),
            ("blocked", "Blocked"),
            ("early", "Early"),
            ("overlap", "Overlap"),
            ("critical", "Critical"),
            ("near_critical", "⏳ Near Critical"),
            ("neg_float", "Neg Float"),
            ("deadline", "Deadline Miss"),
            ("cycle", "⟳ Cycle"),
        ]:
            widget = QLabel(
                f"{label} 0"
            )
            chip_styles = {
                "overdue":
                    "background:#7F1D1D; color:#FFFFFF;",
                "at_risk":
                    "background:#92400E; color:#FFFFFF;",
                "blocked":
                    "background:#5B21B6; color:#FFFFFF;",
                "early":
                    "background:#065F46; color:#FFFFFF;",
                "on_time":
                    "background:#047857; color:#FFFFFF;",
                "delayed":
                    "background:#C2410C; color:#FFFFFF;",
                "overlap":
                    "background:#B91C1C; color:#FFFFFF;",
                "critical":
                    "background:#1D4ED8; color:#FFFFFF;",
                "near_critical":
                    "background:#334155; color:#FFFFFF;",
                "neg_float":
                    "background:#991B1B; color:#FFFFFF;",
                "deadline":
                    "background:#B45309; color:#FFFFFF;",
                "cycle":
                    "background:#6D28D9; color:#FFFFFF;",
            }

            widget.setStyleSheet(
                chip_styles.get(key, "")
                + " font-weight:700;"
                + " padding:5px 9px;"
                + " border-radius:8px;"
            )

            self.kpi_labels[key] = widget
            health_layout.addWidget(widget)

        health_layout.addStretch()

        self.review_overdue_btn = ModernButton(
            variant=ButtonVariant.SECONDARY,
        )
        self.review_overdue_btn.setToolTip(
            "Open the 3W1H+ recovery review for an overdue task."
        )
        self.review_overdue_btn.clicked.connect(
            self.review_next_overdue_task
        )
        health_layout.addWidget(
            self.review_overdue_btn
        )

        self.main_layout.addWidget(
            self.health_frame
        )

        legend_frame = QFrame()
        legend_frame.setObjectName("CardWidget")
        l_layout = QHBoxLayout(legend_frame)
        l_layout.setContentsMargins(12, 4, 12, 4)
        l_layout.setSpacing(12)

        l_items = [
            ("■ Planned", "#3584E4"),
            ("■ Early (-)", "#065F46"),
            ("■ On Time", "#10B981"),
            ("■ Slight Delay", "#F59E0B"),
            ("■ Mod Delay", "#F97316"),
            ("■ Severe Delay", "#EF4444"),
            ("■ Very Severe", "#991B1B"),
        ]

        for text, col in l_items:
            lbl = QLabel(text)
            lbl.setStyleSheet(f"color: {col}; font-weight: 600;")
            l_layout.addWidget(lbl)

        l_layout.addStretch()
        self.main_layout.addWidget(legend_frame)

        # 3. Gantt Graphics Engine Canvas Widget
        self.gantt_chart = GanttChartWidget(self.settings_manager, self)
        self.gantt_chart.task_action_requested.connect(
            self.on_gantt_task_action
        )

        self.gantt_chart.schedule_change_requested.connect(
            self.on_gantt_schedule_change
        )
        
        # True Synchronized Gantt Left Pane
        self.splitter = QSplitter(Qt.Horizontal)
        
        self.left_pane_list = GanttLeftPaneListView()
        self.left_pane_list.setSelectionMode(QListView.NoSelection)
        self.left_pane_list.setFocusPolicy(Qt.NoFocus)
        self.left_pane_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.left_pane_list.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff) # Hidden, controlled by sync
        
        self.left_pane_model = GanttLeftPaneModel(self)
        self.left_pane_list.setModel(self.left_pane_model)

        self.left_pane_list.summaryToggleRequested.connect(
            self.on_gantt_summary_toggle
        )
        self.left_pane_list.taskActionRequested.connect(
            self.on_gantt_task_action
        )
        
        # Resolve current theme from settings, not hardcoded
        app_theme = self.settings_manager.get("theme", "dark")
        effective_colors = self.color_profile.get_effective_colors(app_theme)
        
        panel_bg = effective_colors.get("panel_bg", "#1E293B")
        self.left_pane_list.setStyleSheet(f"border: none; background: {panel_bg};")
        
        self.left_pane_delegate = GanttLeftPaneDelegate(row_height=42.0, color_profile=effective_colors, parent=self)
        self.left_pane_list.setItemDelegate(self.left_pane_delegate)
        
        # Connect visible tasks update
        self.gantt_chart.visible_tasks_changed.connect(self.on_visible_tasks_changed)
        
        # Sync Scrollbars
        self.left_pane_list.verticalScrollBar().valueChanged.connect(self.gantt_chart.verticalScrollBar().setValue)
        self.gantt_chart.verticalScrollBar().valueChanged.connect(self.left_pane_list.verticalScrollBar().setValue)
        
        self.splitter.addWidget(self.left_pane_list)
        self.splitter.addWidget(self.gantt_chart)
        self.splitter.setSizes([250, 800])
        self.splitter.setCollapsible(0, False)
        
        self.main_layout.addWidget(self.splitter, 1)

        # Apply color profile
        self.gantt_chart.set_color_profile(self.color_profile, app_theme)

    def on_date_picker_changed(self, qdate: QDate):
        new_date = date(qdate.year(), qdate.month(), qdate.day())
        if self.gantt_chart.anchor_date != new_date:
            self.gantt_chart.anchor_date = new_date
            self.gantt_chart.rebuild_chart()
            self._update_period_label()
            self.show_feedback_message(f"Showing timeline for {new_date.strftime('%d %b %Y')}")

    def _update_period_label(self):
        a_date = self.gantt_chart.anchor_date
        if hasattr(self, "current_period_lbl"):
            self.current_period_lbl.setText(a_date.strftime('%a, %d %b %Y'))
        if hasattr(self, "date_picker"):
            qdate = QDate(a_date.year, a_date.month, a_date.day)
            if self.date_picker.date() != qdate:
                self.date_picker.blockSignals(True)
                self.date_picker.setDate(qdate)
                self.date_picker.blockSignals(False)

    def on_zoom_changed(self, zoom_text: str):
        self.gantt_chart.set_zoom_mode(zoom_text)
        self._update_period_label()
        self.show_feedback_message(f"Zoom level changed to: {zoom_text}")

    def on_visible_tasks_changed(self, tasks):
        self.left_pane_model.set_tasks(tasks)

    def _persist_gantt_collapsed_keys(self):
        self.settings_manager.set(
            "gantt_collapsed_wbs_keys",
            sorted(self._gantt_collapsed_keys),
        )

    def on_gantt_summary_toggle(self, task):
        """
        Toggle one WBS summary branch.

        Rebuild is presentation-only. No task, schedule, dependency,
        progress, effort, Actual, or DB field is changed.
        """
        if task is None:
            return

        if not bool(
            getattr(task, "gantt_is_summary", False)
        ):
            return

        key = str(
            getattr(task, "gantt_wbs_key", "")
            or ""
        )

        if not key:
            return

        if key in self._gantt_collapsed_keys:
            self._gantt_collapsed_keys.remove(key)
            state_text = "Expanded"
        else:
            self._gantt_collapsed_keys.add(key)
            state_text = "Collapsed"

        self._persist_gantt_collapsed_keys()
        self.refresh_data()

        self.show_feedback_message(
            f"{state_text}: {task.title or 'Summary'}"
        )

    def _apply_gantt_collapse_visibility(self, items):
        """
        Remove descendants of collapsed summary rows.

        Input is canonical WBS pre-order, therefore an iterative
        depth stack is enough and avoids rebuilding hierarchy logic.
        """
        visible = []
        collapsed_depths = []

        for task in items:
            depth = int(
                getattr(task, "gantt_depth", 0)
                or 0
            )

            # Leaving a collapsed branch when we return to same/higher level.
            while (
                collapsed_depths
                and depth <= collapsed_depths[-1]
            ):
                collapsed_depths.pop()

            hidden_by_ancestor = bool(collapsed_depths)

            if hidden_by_ancestor:
                continue

            key = str(
                getattr(task, "gantt_wbs_key", "")
                or ""
            )

            is_summary = bool(
                getattr(
                    task,
                    "gantt_is_summary",
                    False,
                )
            )

            is_collapsed = bool(
                is_summary
                and key
                and key in self._gantt_collapsed_keys
            )

            task.gantt_collapsed = is_collapsed
            visible.append(task)

            if is_collapsed:
                collapsed_depths.append(depth)

        return visible

    def navigate_period(self, step: int):
        self.gantt_chart.navigate_period(step)
        self._update_period_label()
        self.show_feedback_message(f"Navigated to: {self.gantt_chart.anchor_date.strftime('%d %b %Y')}")

    def on_auto_shift_dependencies_changed(
        self,
        checked,
    ):
        checked = bool(
            checked
        )

        self.settings_manager.set(
            "gantt_auto_shift_dependencies",
            checked,
        )

        if not checked:
            self.show_feedback_message(
                " Dependency auto-shift disabled"
            )
            return

        tasks = (
            self.task_controller
            .get_all_tasks()
        )

        analysis = (
            GanttDependencyEngine
            .annotate(
                tasks
            )
        )

        cycle_nodes = sorted(
            analysis.get(
                "cycle_nodes",
                set(),
            )
        )

        if cycle_nodes:
            self.show_feedback_message(
                " Auto-shift enabled. "
                "⟳ Dependency cycle protection active for task ID(s): "
                + ", ".join(
                    str(task_id)
                    for task_id
                    in cycle_nodes
                )
                + ". Non-cycle successors can still auto-shift."
            )

        else:
            self.show_feedback_message(
                " Dependency auto-shift enabled"
            )


    def _apply_dependency_auto_shift(
        self,
        changed_task_id,
    ):
        """
        Persist dependency-safe successor shifts after a predecessor
        move/resize.

        Returns:
            (number shifted, cycle IDs)
        """
        if not hasattr(
            self,
            "auto_shift_dependencies_checkbox",
        ):
            return 0, set()

        if not (
            self.auto_shift_dependencies_checkbox
            .isChecked()
        ):
            return 0, set()

        tasks = (
            self.task_controller
            .get_all_tasks()
        )

        shifted, cycle_nodes = (
            GanttDependencyEngine
            .shift_successors(
                tasks,
                int(
                    changed_task_id
                ),
            )
        )

        saved = 0

        for task in shifted:
            if self.task_controller.update_task(
                task
            ):
                saved += 1

        return saved, cycle_nodes

    def on_gantt_plan_color_changed(
        self,
        _index,
    ):
        color = (
            self.plan_color_combo.currentData()
            or "#3584E4"
        )

        self.settings_manager.set(
            "gantt_planned_bar_color",
            color,
        )

        self.gantt_chart.set_planned_bar_color(
            color
        )

        self.show_feedback_message(
            "Planned baseline color changed to: "
            + self.plan_color_combo.currentText()
        )

    def on_gantt_bar_style_changed(self, _index):
        style = (
            self.bar_style_combo.currentData()
            or "rounded"
        )

        self.settings_manager.set(
            "gantt_bar_style",
            style,
        )

        self.gantt_chart.set_bar_style(
            style
        )

        self.show_feedback_message(
            "Gantt bar design changed to: "
            + self.bar_style_combo.currentText()
        )

    def nudge_selected_gantt_task(
        self,
        direction,
    ):
        ok, message = (
            self.gantt_chart.nudge_selected_task(
                direction
            )
        )

        if not ok:
            self.show_feedback_message(
                "ℹ " + message
            )

    def on_gantt_theme_changed(self, text: str):
        mode = text.lower().replace(" ", "_")
        self.color_profile.mode = mode
        self.settings_manager.set("gantt_theme_mode", mode)
        app_theme = self.settings_manager.get("theme", "dark")
        self.gantt_chart.set_color_profile(self.color_profile, app_theme)
        # Update left pane delegate and background to match
        effective_colors = self.color_profile.get_effective_colors(app_theme)
        self.left_pane_delegate.set_color_profile(effective_colors)
        panel_bg = effective_colors.get("panel_bg", "#1E293B")
        self.left_pane_list.setStyleSheet(f"border: none; background: {panel_bg};")
        self.left_pane_list.viewport().update()

    def set_theme(self, is_dark: bool, accent_color: Optional[str] = None):
        self._is_dark = bool(is_dark)
        self._accent_color = accent_color or "#3584E4"
        tokens = semantic_tokens_for(self._is_dark, self._accent_color)

        for child_type in (ModernButton, ModernComboBox, ModernCheckBox):
            for child in self.findChildren(child_type):
                try:
                    child.set_theme(self._is_dark, self._accent_color)
                except RuntimeError:
                    pass

        toolbar = getattr(self, "_gantt_toolbar", None)
        if toolbar is not None:
            toolbar.setStyleSheet(
                f"""
                QFrame#CardWidget {{
                    background-color: {tokens['SURFACE_1']};
                    border: 1px solid {tokens['BORDER_NORMAL']};
                    border-radius: 8px;
                }}
                QFrame#GanttToolbarSeparator {{
                    background-color: {tokens['BORDER_SUBTLE']};
                    color: {tokens['BORDER_SUBTLE']};
                    min-width: 1px;
                    max-width: 1px;
                    margin: 0 4px;
                }}
                """
            )

        for menu in (
            getattr(self, "timeline_menu", None),
            getattr(self, "appearance_menu", None),
            getattr(self, "layers_menu", None),
        ):
            if menu is not None:
                menu.setStyleSheet(
                    f"""
                    QMenu {{
                        background-color: {tokens['SURFACE_1']};
                        color: {tokens['TEXT_PRIMARY']};
                        border: 1px solid {tokens['BORDER_NORMAL']};
                        border-radius: 8px;
                        padding: 4px;
                    }}
                    QMenu::item:selected {{
                        background-color: {tokens['ACCENT_SUBTLE']};
                    }}
                    """
                )

        if hasattr(self, "current_period_lbl"):
            self.current_period_lbl.setStyleSheet(
                f"color: {tokens['ACCENT']}; font-weight: 700; padding: 2px 6px;"
            )
        if hasattr(self, "status_banner"):
            self.status_banner.setStyleSheet(
                f"font-weight: 600; color: {tokens['SUCCESS']}; padding: 2px 12px;"
            )

        app_theme = "dark" if self._is_dark else "light"
        if hasattr(self, "gantt_chart"):
            try:
                self.gantt_chart.set_color_profile(
                    self.color_profile,
                    app_theme,
                )
            except Exception:
                pass
        if hasattr(self, "left_pane_delegate") and hasattr(self, "left_pane_list"):
            try:
                effective_colors = self.color_profile.get_effective_colors(app_theme)
                self.left_pane_delegate.set_color_profile(effective_colors)
                panel_bg = effective_colors.get("panel_bg", tokens["SURFACE_1"])
                self.left_pane_list.setStyleSheet(
                    f"border: none; background: {panel_bg};"
                )
                self.left_pane_list.viewport().update()
            except Exception:
                pass

        self._sync_gantt_toolbar_typography_height()
        self.update()

    def on_filter_changed(self):
        self.gantt_chart.set_filters(
            show_actual=self.cb_actual.isChecked(),
            show_completed=self.cb_completed.isChecked()
        )

    def go_to_today(self):
        self.gantt_chart.auto_center_today()
        self._update_period_label()
        today_str = date.today().strftime("%d %B %Y")
        self.show_feedback_message(f"Showing today — {today_str}")

    def trigger_refresh(self):
        if hasattr(self, "refresh_btn") and self.refresh_btn:
            self.refresh_btn.setEnabled(False)
            self.refresh_btn.setText("⏳ Refreshed")
            QCoreApplication.processEvents()

        count = self.refresh_project_schedule()
        self.show_feedback_message(f"Gantt refreshed — {count} tasks loaded")

        QTimer.singleShot(300, self._restore_refresh_btn)

    def _restore_refresh_btn(self):
        if hasattr(self, "refresh_btn") and self.refresh_btn:
            self.refresh_btn.setText("⟳ Refresh")
            self.refresh_btn.setEnabled(True)

    def show_feedback_message(self, text: str):
        self.status_banner.setText(text)
        self.status_banner.setVisible(True)
        QTimer.singleShot(3000, lambda: self.status_banner.setVisible(False))

    def export_chart_image(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Export Gantt Chart Image", "gantt_timeline.png", "PNG Images (*.png)")
        if not file_path:
            return

        rect = self.gantt_chart.scene.sceneRect()
        image = QImage(int(rect.width()), int(rect.height()), QImage.Format_ARGB32)
        image.fill(Qt.transparent)

        painter = QPainter(image)
        self.gantt_chart.scene.render(painter)
        painter.end()

        image.save(file_path)
        QMessageBox.information(self, "Export Successful", f"Gantt timeline saved to:\n{file_path}")

    def _hourly_overlap_task_ids(
        self,
        tasks,
    ):
        """
        Return IDs of every unfinished main task involved in an
        actual same-date time collision.

        Zero-length schedules such as 00:00-00:00 are ignored because
        they do not occupy capacity.
        """
        active = []

        for task in tasks:
            if task.id is None:
                continue

            if task.status in (
                TaskStatus.COMPLETED,
                TaskStatus.CANCELLED,
            ):
                continue

            if not task.planned_date:
                continue

            start = self._time_to_minutes(
                task.planned_start_time
            )

            end = self._time_to_minutes(
                task.planned_end_time
            )

            duration = int(
                task.estimated_duration
                or 0
            )

            if (
                start is not None
                and (
                    end is None
                    or end <= start
                )
                and duration > 0
            ):
                end = (
                    start
                    + duration
                )

            if (
                start is None
                or end is None
                or end <= start
            ):
                continue

            active.append(
                (
                    int(task.id),
                    task.planned_date,
                    start,
                    end,
                )
            )

        conflict_ids = set()

        for index, first in enumerate(
            active
        ):
            for second in active[
                index + 1:
            ]:
                if first[1] != second[1]:
                    continue

                if (
                    first[2] < second[3]
                    and first[3] > second[2]
                ):
                    conflict_ids.add(
                        first[0]
                    )
                    conflict_ids.add(
                        second[0]
                    )

        return conflict_ids


    def _count_hourly_overlap_pairs(
        self,
        tasks,
    ):
        """
        Count unique schedule collision PAIRS for the KPI.
        """
        active = []

        for task in tasks:
            if task.id is None:
                continue

            if task.status in (
                TaskStatus.COMPLETED,
                TaskStatus.CANCELLED,
            ):
                continue

            if not task.planned_date:
                continue

            start = self._time_to_minutes(
                task.planned_start_time
            )

            end = self._time_to_minutes(
                task.planned_end_time
            )

            duration = int(
                task.estimated_duration
                or 0
            )

            if (
                start is not None
                and (
                    end is None
                    or end <= start
                )
                and duration > 0
            ):
                end = start + duration

            if (
                start is None
                or end is None
                or end <= start
            ):
                continue

            active.append(
                (
                    int(task.id),
                    task.planned_date,
                    start,
                    end,
                )
            )

        pair_count = 0

        for index, first in enumerate(
            active
        ):
            for second in active[
                index + 1:
            ]:
                if first[1] != second[1]:
                    continue

                if (
                    first[2] < second[3]
                    and first[3] > second[2]
                ):
                    pair_count += 1

        return pair_count

    def _update_gantt_health(
        self,
        tasks,
    ):
        """
        Executive health authority.

        IMPORTANT:
        This receives ALL application tasks, not merely rows currently
        visible in Gantt. Overdue recovery cannot depend on show_in_gantt.
        """
        counts = {
            "overdue": 0,
            "at_risk": 0,
            "blocked": 0,
            "early": 0,
            "on_time": 0,
            "delayed": 0,
            "overlap": 0,
        }

        overdue_candidates = []

        for task in tasks:
            if task.status == TaskStatus.BLOCKED:
                counts["blocked"] += 1

            (
                timing_status,
                delay_mins,
                _,
            ) = (
                self.delay_engine
                .analyze_task_timing(task)
            )

            if timing_status == TimingStatus.OVERDUE:
                counts["overdue"] += 1

                if (
                    task.id is not None
                    and task.status
                    not in (
                        TaskStatus.COMPLETED,
                        TaskStatus.CANCELLED,
                    )
                    and not (
                        task.delay_notes
                        or ""
                    ).strip()
                ):
                    overdue_candidates.append(
                        (
                            task,
                            delay_mins,
                        )
                    )

            elif timing_status == TimingStatus.AT_RISK:
                counts["at_risk"] += 1

            elif (
                timing_status
                == TimingStatus.COMPLETED_BEFORE_TIME
            ):
                counts["early"] += 1

            elif (
                timing_status
                == TimingStatus.COMPLETED_ON_TIME
                and task.status
                == TaskStatus.COMPLETED
            ):
                counts["on_time"] += 1

            elif timing_status in (
                TimingStatus.SLIGHT_DELAY,
                TimingStatus.MODERATE_DELAY,
                TimingStatus.SEVERE_DELAY,
                TimingStatus.VERY_SEVERE_DELAY,
            ):
                counts["delayed"] += 1

        counts["overlap"] = (
            self._count_hourly_overlap_pairs(
                tasks
            )
        )

        # CPM schedule-health digest (critical path, float, engine
        # diagnostics) — surfaces the scheduling engine's findings that
        # previously lived only in invisible task attributes.
        schedule_health = None
        try:
            schedule_health = GanttDependencyEngine.schedule_health_summary(
                tasks
            )
        except Exception:
            schedule_health = None
        self.schedule_health = schedule_health

        label_names = {
            "overdue": "Overdue",
            "at_risk": "At Risk",
            "blocked": "Blocked",
            "early": "Early",
            "overlap": "Overlap",
            "critical": "Critical",
            "near_critical": "⏳ Near Critical",
            "neg_float": "Neg Float",
            "deadline": "Deadline Miss",
            "cycle": "⟳ Cycle",
        }

        for key, widget in self.kpi_labels.items():
            if key in counts:
                widget.setText(
                    f"{label_names[key]} "
                    f"{counts[key]}"
                )

        if schedule_health:
            chip_values = {
                "critical": schedule_health["critical"],
                "near_critical": schedule_health["near_critical"],
                "neg_float": schedule_health["negative_float"],
                "deadline": schedule_health["deadline_missed"],
                "cycle": schedule_health["cycles"],
            }
            for key, value in chip_values.items():
                widget = self.kpi_labels[key]
                widget.setText(f"{label_names[key]} {value}")
                # Issue chips only earn ribbon space when nonzero; the
                # informational critical/near-critical chips always show.
                widget.setVisible(
                    key in ("critical", "near_critical") or value > 0
                )
            near_ids = ", ".join(str(i) for i in schedule_health["near_critical_ids"]) or "none"
            neg_ids = ", ".join(str(i) for i in schedule_health["negative_float_ids"]) or "none"
            dl_ids = ", ".join(str(i) for i in schedule_health["deadline_missed_ids"]) or "none"
            self.kpi_labels["near_critical"].setToolTip(
                "Tasks with 1 day or less of slack before they become critical: " + near_ids
            )
            self.kpi_labels["neg_float"].setToolTip(
                "Tasks already past their latest allowed date: " + neg_ids
            )
            self.kpi_labels["deadline"].setToolTip(
                "Forecast finishes missing their deadlines: " + dl_ids
            )
            finish = schedule_health.get("project_finish")
            score_chip = (
                f" Health {schedule_health['health_score']} "
                f"({schedule_health['verdict']})"
            )
            self.kpi_labels["critical"].setToolTip(
                "Zero-float tasks driving the project finish: "
                f"{finish.strftime('%d %b %Y') if finish else '—'} • {score_chip}"
            )
        else:
            for key in ("critical", "near_critical", "neg_float", "deadline", "cycle"):
                self.kpi_labels[key].setVisible(False)

        if hasattr(
            self,
            "review_overdue_btn",
        ):
            self.review_overdue_btn.setText(
                "Review Overdue"
                + (
                    f" ({counts['overdue']})"
                    if counts["overdue"]
                    else ""
                )
            )

            self.review_overdue_btn.setEnabled(
                counts["overdue"] > 0
            )

        # One automatic recovery dialogue at a time.
        # show_in_gantt has deliberately NO influence here.
        for task, delay_mins in overdue_candidates:
            if (
                task.id
                not in self._overdue_prompted_ids
            ):
                self._overdue_prompted_ids.add(
                    task.id
                )

                QTimer.singleShot(
                    800,
                    lambda
                        task_id=task.id,
                        d=delay_mins:
                    self._auto_prompt_overdue_by_id(
                        task_id,
                        d,
                    )
                )

                break

    def _find_task_by_id(
        self,
        task_id,
    ):
        try:
            return self.task_controller.get_task(
                int(task_id)
            )
        except Exception:
            return None

    def _auto_prompt_overdue_by_id(
        self,
        task_id,
        delay_minutes,
    ):
        if (
            os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen"
            or os.environ.get("PYTEST_CURRENT_TEST")
            or os.environ.get("PYTEST_DISABLE_PLUGIN_AUTOLOAD")
        ):
            return

        if (
            getattr(self, "_cleaned_up", False)
            or getattr(self, "_suppress_overdue_prompts", False)
            or getattr(self, "_overdue_prompt_in_progress", False)
        ):
            return

        task = self._find_task_by_id(
            task_id
        )

        if not task:
            return

        timing_status, current_delay, _ = (
            self.delay_engine
            .analyze_task_timing(task)
        )

        if timing_status != TimingStatus.OVERDUE:
            return

        if (
            task.delay_notes
            or ""
        ).strip():
            return

        self._prompt_overdue_recovery(
            task,
            current_delay
            or delay_minutes,
        )

    def review_next_overdue_task(self):
        """
        Manual recovery action.

        This guarantees the operator can open 3W1H even when an
        automatic dialog was dismissed or previously suppressed.
        """
        candidates = []

        for task in (
            self.task_controller
            .get_all_tasks()
        ):
            if task.status in (
                TaskStatus.COMPLETED,
                TaskStatus.CANCELLED,
            ):
                continue

            timing_status, delay_mins, _ = (
                self.delay_engine
                .analyze_task_timing(task)
            )

            if timing_status == TimingStatus.OVERDUE:
                candidates.append(
                    (
                        task,
                        delay_mins,
                    )
                )

        if not candidates:
            self.show_feedback_message(
                "No overdue tasks require recovery review."
            )
            return

        # Prefer overdue task without a recovery note.
        candidates.sort(
            key=lambda item: (
                bool(
                    (
                        item[0].delay_notes
                        or ""
                    ).strip()
                ),
                -int(item[1] or 0),
            )
        )

        task, delay_mins = candidates[0]

        self._prompt_overdue_recovery(
            task,
            delay_mins,
        )

    def _prompt_overdue_recovery(
        self,
        task,
        delay_minutes,
    ):
        if (
            getattr(self, "_cleaned_up", False)
            or getattr(self, "_suppress_overdue_prompts", False)
            or getattr(self, "_overdue_prompt_in_progress", False)
        ):
            return

        if task.status in (
            TaskStatus.COMPLETED,
            TaskStatus.CANCELLED,
        ):
            return

        self._overdue_prompt_in_progress = True
        jdlg = DelayJustificationDialog(
            task,
            delay_minutes=int(
                delay_minutes or 0
            ),
            parent=self,
        )

        try:
            if (
                jdlg.exec()
                != DelayJustificationDialog.Accepted
            ):
                self.show_feedback_message(
                    "Recovery review postponed for: "
                    + task.title
                )
                return
        finally:
            self._overdue_prompt_in_progress = False

        if (
            getattr(self, "_cleaned_up", False)
            or getattr(self, "_suppress_overdue_prompts", False)
        ):
            return

        task.delay_reason = (
            jdlg.selected_reason
        )

        task.delay_notes = (
            jdlg.notes
        )

        task.delay_minutes = int(
            delay_minutes or 0
        )

        task.delay_recorded_at = (
            datetime.now().strftime(
                "%Y-%m-%d %H:%M"
            )
        )

        if task.status not in (
            TaskStatus.BLOCKED,
            TaskStatus.CANCELLED,
        ):
            task.status = TaskStatus.DELAYED

        self.task_controller.update_task(
            task
        )

        self.show_feedback_message(
            "Recovery 3W1H+ recorded — "
            + task.title
        )

        QTimer.singleShot(
            100,
            self.refresh_data,
        )

    def _build_phase1d_wbs_gantt_items(self, all_tasks):
        """
        Build live Gantt rows from the canonical WBS hierarchy.

        Project-backed work uses WBSService + GanttWBSAdapter.
        Unassigned/Inbox main tasks retain the existing flat behavior.

        This method creates presentation Task objects only where needed.
        It never writes to DB and never mutates parent stored schedule fields.
        """
        task_by_id = {
            int(task.id): task
            for task in all_tasks
            if getattr(task, "id", None) is not None
        }

        def priority_from_value(value):
            if isinstance(value, TaskPriority):
                return value
            try:
                return TaskPriority(value or "Medium")
            except Exception:
                return TaskPriority.MEDIUM

        def status_from_row(row, payload):
            if row.is_summary:
                if int(row.blocked_count or 0) > 0:
                    return TaskStatus.BLOCKED
                if int(row.delayed_count or 0) > 0:
                    return TaskStatus.DELAYED
                if int(row.progress_percent or 0) >= 100:
                    return TaskStatus.COMPLETED
                if int(row.progress_percent or 0) > 0:
                    return TaskStatus.IN_PROGRESS
                return TaskStatus.PLANNED

            raw = (
                payload.get("status")
                if isinstance(payload, dict)
                else getattr(payload, "status", None)
            )

            if isinstance(raw, TaskStatus):
                return raw

            normalized = str(
                getattr(raw, "value", raw)
                or "Planned"
            ).strip().lower().replace("_", " ")

            mapping = {
                "inbox": TaskStatus.INBOX,
                "planned": TaskStatus.PLANNED,
                "in progress": TaskStatus.IN_PROGRESS,
                "blocked": TaskStatus.BLOCKED,
                "completed": TaskStatus.COMPLETED,
                "delayed": TaskStatus.DELAYED,
                "moved": TaskStatus.MOVED,
                "cancelled": TaskStatus.CANCELLED,
            }
            return mapping.get(normalized, TaskStatus.PLANNED)

        def payload_value(payload, name, default=None):
            if payload is None:
                return default
            if isinstance(payload, dict):
                return payload.get(name, default)
            return getattr(payload, name, default)

        def dt_date(value):
            return value.strftime("%Y-%m-%d") if value else None

        def dt_time(value):
            return value.strftime("%H:%M") if value else None

        def raw_payload_or_source(payload, source_task, name, default=None):
            value = payload_value(payload, name, None)
            if value not in (None, ""):
                return value
            if source_task is not None:
                source_value = getattr(source_task, name, None)
                if source_value not in (None, ""):
                    return source_value
            return default

        def raw_int_payload_or_source(payload, source_task, name, default=0):
            try:
                return int(
                    raw_payload_or_source(
                        payload,
                        source_task,
                        name,
                        default,
                    )
                    or 0
                )
            except (TypeError, ValueError):
                return int(default or 0)

        def attach_cpm_metadata(task, row):
            def display_dt(value):
                if hasattr(value, "isoformat"):
                    return value.isoformat()
                return value

            diagnostics = [
                getattr(item, "value", str(item))
                for item in (getattr(row, "cpm_diagnostics", ()) or ())
            ]
            metadata = {
                "earliest_start": getattr(row, "cpm_earliest_start", None),
                "earliest_finish": getattr(row, "cpm_earliest_finish", None),
                "latest_start": getattr(row, "cpm_latest_start", None),
                "latest_finish": getattr(row, "cpm_latest_finish", None),
                "total_float": getattr(row, "cpm_total_float_minutes", None),
                "free_float": getattr(row, "cpm_free_float_minutes", None),
                "is_critical": bool(getattr(row, "cpm_is_critical", False)),
                "schedulable": bool(getattr(row, "cpm_schedulable", False)),
                "diagnostics": diagnostics,
                "analysis_status": getattr(row, "cpm_analysis_status", "not_analyzed"),
                "dependency_summary": getattr(row, "dependency_summary", ""),
            }
            task.gantt_cpm_metadata = metadata
            task.gantt_cpm_analysis_status = metadata["analysis_status"]
            task.gantt_dependency_summary = metadata["dependency_summary"]
            task.cpm_total_float = metadata["total_float"]
            task.cpm_free_float = metadata["free_float"]
            task.cpm_is_critical = metadata["is_critical"]
            task.cpm_earliest_start = display_dt(metadata["earliest_start"])
            task.cpm_earliest_finish = display_dt(metadata["earliest_finish"])
            task.cpm_latest_start = display_dt(metadata["latest_start"])
            task.cpm_latest_finish = display_dt(metadata["latest_finish"])
            task.cpm_diagnostics = diagnostics
            if metadata["schedulable"]:
                task.gantt_critical_path = metadata["is_critical"]

        result = []
        represented_task_ids = set()

        def build_unassigned_snapshot():
            unassigned_tasks = [
                task
                for task in all_tasks
                if (
                    getattr(task, "project_id", None) is None
                    and getattr(task, "id", None) is not None
                )
            ]
            unassigned_task_ids = [
                int(task.id)
                for task in unassigned_tasks
            ]

            if not unassigned_task_ids:
                return None

            placeholders = ",".join(
                "?" for _ in unassigned_task_ids
            )

            with self.db_manager.get_connection() as conn:
                subtask_rows = conn.execute(
                    f"""
                    SELECT s.id, s.task_id, s.parent_subtask_id,
                           s.title, s.position, s.is_completed,
                           s.created_at, t.project_id
                    FROM subtasks s
                    JOIN tasks t ON t.id = s.task_id
                    WHERE t.project_id IS NULL
                      AND t.id IN ({placeholders})
                    ORDER BY s.parent_subtask_id,
                             s.position ASC,
                             s.created_at ASC,
                             s.id ASC;
                    """,
                    tuple(unassigned_task_ids),
                ).fetchall()

            if not subtask_rows:
                return None

            raw_items = []

            for task in unassigned_tasks:
                status = getattr(task, "status", None)
                raw_items.append(
                    {
                        "key": EntityRef.task(int(task.id)),
                        "parent_key": None,
                        "project_id": None,
                        "title": getattr(task, "title", "") or "",
                        "position": int(
                            getattr(task, "position", 0) or 0
                        ),
                        "status": status,
                        "is_completed": (
                            status == TaskStatus.COMPLETED
                            or str(
                                getattr(status, "value", status)
                                or ""
                            ).lower() == "completed"
                        ),
                        "is_milestone": bool(
                            "milestone"
                            in (
                                getattr(task, "tags", None)
                                or []
                            )
                        ),
                        "created_at": (
                            getattr(task, "created_at", None)
                            or ""
                        ),
                    }
                )

            for row in subtask_rows:
                sub_parent = row["parent_subtask_id"]
                parent_ref = (
                    EntityRef.subtask(sub_parent)
                    if sub_parent is not None
                    else EntityRef.task(row["task_id"])
                )
                raw_items.append(
                    {
                        "key": EntityRef.subtask(row["id"]),
                        "parent_key": parent_ref,
                        "project_id": row["project_id"],
                        "title": row["title"] or "",
                        "position": int(row["position"] or 0),
                        "status": (
                            "Completed"
                            if bool(row["is_completed"])
                            else "Planned"
                        ),
                        "is_completed": bool(row["is_completed"]),
                        "is_milestone": False,
                        "created_at": row["created_at"] or "",
                    }
                )

            return WBSService.build_from_raw(
                raw_items,
                project_id=None,
            )

        # ----------------------------------------------------
        # Filter project_ids by current_project_id when selected
        # ----------------------------------------------------
        cur_pid = getattr(self, "current_project_id", None)
        all_pids = list({getattr(t, "project_id", None) for t in all_tasks if getattr(t, "project_id", None) is not None})
        if cur_pid is not None and cur_pid not in all_pids and all_pids:
            cur_pid = all_pids[0]
            self.current_project_id = cur_pid

        if cur_pid is not None:
            project_ids = [cur_pid]
        else:
            project_ids = []
            seen_projects = set()

            for task in all_tasks:
                pid = getattr(task, "project_id", None)
                if pid is None or pid in seen_projects:
                    continue
                seen_projects.add(pid)
                project_ids.append(pid)

        # ----------------------------------------------------
        # Canonical project WBS rows.
        # ----------------------------------------------------
        snapshots = []
        for project_id in project_ids:
            snapshots.append(
                WBSService.build_project_hierarchy(
                    self.db_manager,
                    project_id=project_id,
                )
            )

        unassigned_snapshot = build_unassigned_snapshot()
        if unassigned_snapshot is not None:
            snapshots.append(unassigned_snapshot)

        for snapshot in snapshots:

            rows = GanttWBSAdapter.build_project_rows(
                snapshot,
                self.db_manager,
            )

            for row in rows:
                payload = row.source_payload or {}

                # --------------------------------------------
                # Main-task leaf:
                # preserve the real Task instance exactly.
                # --------------------------------------------
                if (
                    row.key.entity_type == "task"
                    and not row.is_summary
                ):
                    represented_task_ids.add(
                        int(row.key.entity_id)
                    )
                    task = task_by_id.get(
                        int(row.key.entity_id)
                    )
                    if task is None:
                        continue

                    task.gantt_depth = int(row.depth)
                    task.gantt_item_type = "task"
                    task.gantt_is_summary = False
                    task.gantt_read_only = False
                    task.gantt_is_milestone = bool(row.is_milestone)
                    task.gantt_wbs_code = str(row.wbs_code or "")
                    task.gantt_entity_type = "task"
                    task.gantt_entity_id = int(row.key.entity_id)

                    # CPM / WBS calculated schedule start & finish date authority
                    task.gantt_planned_start = row.planned_start
                    task.gantt_planned_finish = row.planned_finish
                    attach_cpm_metadata(task, row)

                    result.append(task)
                    continue

                # --------------------------------------------
                # Resolve owning real task for category/priority
                # defaults and nested edit identity.
                # --------------------------------------------
                if row.key.entity_type == "task":
                    represented_task_ids.add(
                        int(row.key.entity_id)
                    )

                if row.key.entity_type == "task":
                    source_task_id = int(row.key.entity_id)
                else:
                    source_task_id = int(
                        payload_value(
                            payload,
                            "task_id",
                            0,
                        )
                        or 0
                    )

                source_task = task_by_id.get(source_task_id)

                if source_task is not None:
                    priority = source_task.priority
                    category = source_task.category
                    base_tags = list(source_task.tags or [])
                    description = (
                        payload_value(payload, "description", None)
                        or source_task.description
                        or ""
                    )
                else:
                    priority = priority_from_value(
                        payload_value(
                            payload,
                            "priority",
                            "Medium",
                        )
                    )
                    category = payload_value(
                        payload,
                        "category",
                        None,
                    )
                    base_tags = []
                    description = payload_value(
                        payload,
                        "description",
                        "",
                    ) or ""

                if row.key.entity_type == "subtask":
                    item_id = -int(row.key.entity_id)
                    item_type = "subtask"
                    if "subtask" not in base_tags:
                        base_tags.append("subtask")
                else:
                    item_id = int(row.key.entity_id)
                    item_type = "task"

                if row.is_summary and "summary" not in base_tags:
                    base_tags.append("summary")

                if row.is_milestone and "milestone" not in base_tags:
                    base_tags.append("milestone")

                source_for_raw = (
                    source_task
                    if row.key.entity_type == "task"
                    else None
                )

                # --------------------------------------------
                # Raw Task fields stay DB-backed, even for WBS summaries.
                # Derived summary dates live only in gantt_* metadata below.
                # --------------------------------------------
                if row.is_summary:
                    planned_date = raw_payload_or_source(
                        payload,
                        source_for_raw,
                        "planned_date",
                        None,
                    )
                    due_date = raw_payload_or_source(
                        payload,
                        source_for_raw,
                        "due_date",
                        None,
                    )
                    planned_start_time = raw_payload_or_source(
                        payload,
                        source_for_raw,
                        "planned_start_time",
                        None,
                    )
                    planned_end_time = raw_payload_or_source(
                        payload,
                        source_for_raw,
                        "planned_end_time",
                        None,
                    )
                    estimated_duration = raw_int_payload_or_source(
                        payload,
                        source_for_raw,
                        "estimated_duration",
                        0,
                    )
                    planned_effort = raw_int_payload_or_source(
                        payload,
                        source_for_raw,
                        "planned_effort_minutes",
                        0,
                    )
                    daily_dedication = raw_int_payload_or_source(
                        payload,
                        source_for_raw,
                        "daily_dedication_minutes",
                        0,
                    )
                    progress = raw_int_payload_or_source(
                        payload,
                        source_for_raw,
                        "progress",
                        0,
                    )

                    # Phase 1D summary Actual semantics.
                    #
                    # Stored Task fields remain presentation-only here;
                    # nothing is written to DB for a summary.
                    #
                    # actual_finish may intentionally be None while the
                    # branch is still executing.
                    actual_start_date = dt_date(row.actual_start)
                    actual_end_date = dt_date(row.actual_finish)
                    actual_start_time = dt_time(row.actual_start)
                    actual_end_time = dt_time(row.actual_finish)

                    # IMPORTANT:
                    # Task.actual_duration means Actual Work Effort.
                    # Do not put rolled elapsed time into this field.
                    actual_duration = 0
                else:
                    planned_date = raw_payload_or_source(
                        payload,
                        source_for_raw,
                        "planned_date",
                        None,
                    )
                    due_date = raw_payload_or_source(
                        payload,
                        source_for_raw,
                        "due_date",
                        None,
                    )
                    planned_start_time = raw_payload_or_source(
                        payload,
                        source_for_raw,
                        "planned_start_time",
                        None,
                    )
                    planned_end_time = raw_payload_or_source(
                        payload,
                        source_for_raw,
                        "planned_end_time",
                        None,
                    )
                    estimated_duration = raw_int_payload_or_source(
                        payload,
                        source_for_raw,
                        "estimated_duration",
                        0,
                    )
                    planned_effort = raw_int_payload_or_source(
                        payload,
                        source_for_raw,
                        "planned_effort_minutes",
                        0,
                    )
                    daily_dedication = raw_int_payload_or_source(
                        payload,
                        source_for_raw,
                        "daily_dedication_minutes",
                        0,
                    )
                    progress = raw_int_payload_or_source(
                        payload,
                        source_for_raw,
                        "progress",
                        0,
                    )

                    if bool(
                        payload_value(
                            payload,
                            "is_completed",
                            False,
                        )
                    ):
                        progress = 100

                    actual_start_date = payload_value(
                        payload,
                        "actual_start_date",
                        None,
                    )
                    actual_end_date = payload_value(
                        payload,
                        "actual_end_date",
                        None,
                    )
                    actual_start_time = payload_value(
                        payload,
                        "actual_start_time",
                        None,
                    )
                    actual_end_time = payload_value(
                        payload,
                        "actual_end_time",
                        None,
                    )
                    actual_duration = int(
                        payload_value(
                            payload,
                            "actual_duration",
                            0,
                        )
                        or 0
                    )

                presentation_task = Task(
                    id=item_id,
                    title=row.title or "Untitled",
                    project_id=row.project_id,
                    priority=priority,
                    tags=base_tags,
                    category=category,
                    description=description,
                    planned_date=planned_date,
                    due_date=due_date,
                    planned_start_time=planned_start_time,
                    planned_end_time=planned_end_time,
                    estimated_duration=estimated_duration,
                    planned_effort_minutes=planned_effort,
                    daily_dedication_minutes=daily_dedication,
                    progress=max(
                        0,
                        min(100, progress),
                    ),
                    dependencies=(
                        []
                        if row.is_summary
                        else (
                            json.loads(
                                payload_value(
                                    payload,
                                    "dependencies",
                                    "[]",
                                )
                            )
                            if isinstance(
                                payload_value(
                                    payload,
                                    "dependencies",
                                    [],
                                ),
                                str,
                            )
                            else (
                                payload_value(
                                    payload,
                                    "dependencies",
                                    [],
                                )
                                or []
                            )
                        )
                    ),
                    status=status_from_row(row, payload),
                    show_in_gantt=True,
                    is_pinned=bool(
                        payload_value(
                            payload,
                            "is_pinned",
                            False,
                        )
                    ),
                    pin_color=(
                        payload_value(
                            payload,
                            "pin_color",
                            "#E95420",
                        )
                        or "#E95420"
                    ),
                    pin_position=int(
                        payload_value(
                            payload,
                            "pin_position",
                            0,
                        )
                        or 0
                    ),
                    actual_start_date=actual_start_date,
                    actual_end_date=actual_end_date,
                    actual_start_time=actual_start_time,
                    actual_end_time=actual_end_time,
                    actual_duration=actual_duration,
                )

                # --------------------------------------------
                # Phase 1D metadata consumed by chart/left pane.
                # --------------------------------------------
                presentation_task.gantt_depth = int(row.depth)
                presentation_task.gantt_item_type = item_type
                presentation_task.gantt_is_summary = bool(row.is_summary)
                presentation_task.gantt_read_only = bool(row.is_read_only)
                presentation_task.gantt_is_milestone = bool(row.is_milestone)
                presentation_task.gantt_wbs_code = str(row.wbs_code or "")
                presentation_task.gantt_entity_type = row.key.entity_type
                presentation_task.gantt_entity_id = int(row.key.entity_id)
                presentation_task.gantt_planned_start = row.planned_start
                presentation_task.gantt_planned_finish = row.planned_finish
                attach_cpm_metadata(presentation_task, row)

                presentation_task.gantt_wbs_key = (
                    f"{row.key.entity_type}:{int(row.key.entity_id)}"
                )

                if row.parent_key is not None:
                    presentation_task.gantt_parent_wbs_key = (
                        f"{row.parent_key.entity_type}:"
                        f"{int(row.parent_key.entity_id)}"
                    )
                else:
                    presentation_task.gantt_parent_wbs_key = None

                presentation_task.gantt_rollup_progress = int(
                    row.progress_percent or 0
                )
                presentation_task.gantt_rollup_leaf_count = int(
                    row.leaf_count or 0
                )
                presentation_task.gantt_rollup_planned_effort = int(
                    row.planned_effort_minutes or 0
                )
                presentation_task.gantt_rollup_actual_effort = int(
                    row.actual_effort_minutes or 0
                )

                # Explicit derived Planned-summary metadata. The chart reads
                # gantt_planned_* for geometry; dialogs/persistence read the
                # raw Task fields above.
                presentation_task.gantt_summary_planned_start = (
                    row.planned_start
                )
                presentation_task.gantt_summary_planned_finish = (
                    row.planned_finish
                )
                presentation_task.gantt_summary_planned_elapsed_minutes = (
                    row.planned_elapsed_minutes
                )

                # Explicit derived Actual-envelope metadata.
                # Chart rendering consumes these values without changing
                # persistent Task scheduling fields.
                presentation_task.gantt_summary_actual_start = (
                    row.actual_start
                )
                presentation_task.gantt_summary_actual_finish = (
                    row.actual_finish
                )
                presentation_task.gantt_summary_actual_activity_end = (
                    row.actual_finish
                    or row.latest_actual_activity_at
                )
                presentation_task.gantt_summary_actual_complete = bool(
                    row.actual_finish is not None
                )

                presentation_task.gantt_rollup_confidence = str(
                    row.confidence or "empty"
                )

                if row.key.entity_type == "subtask":
                    presentation_task.source_subtask_id = int(
                        row.key.entity_id
                    )
                    presentation_task.parent_task_id = source_task_id

                result.append(presentation_task)

        # ----------------------------------------------------
        # Preserve unassigned/Inbox main tasks.
        # This avoids changing non-project Gantt semantics in Batch 2B.
        # ----------------------------------------------------
        for task in all_tasks:
            if getattr(task, "project_id", None) is not None:
                continue

            if not bool(
                getattr(task, "show_in_gantt", False)
            ):
                continue

            if int(task.id or 0) in represented_task_ids:
                continue

            task.gantt_depth = 0
            task.gantt_item_type = "task"
            task.gantt_is_summary = False
            task.gantt_read_only = False
            task.gantt_is_milestone = bool(
                "milestone" in (task.tags or [])
            )
            task.gantt_wbs_code = ""
            task.gantt_entity_type = "task"
            task.gantt_entity_id = int(task.id or 0)
            task.gantt_wbs_key = (
                f"inbox-task:{int(task.id or 0)}"
            )
            task.gantt_parent_wbs_key = None

            result.append(task)

        return result

    def _sync_gantt_toolbar_typography_height(self):
        if getattr(self, "_cleaned_up", False):
            return
        toolbar = getattr(self, "_gantt_toolbar", None)
        toolbar_scroll = getattr(self, "_gantt_toolbar_scroll", None)
        if toolbar is None or toolbar_scroll is None:
            return
        try:
            toolbar.adjustSize()
            toolbar.setMinimumWidth(toolbar.sizeHint().width())
            toolbar_scroll.setFixedHeight(
                toolbar.sizeHint().height() + 10
            )
        except RuntimeError:
            pass

    def cleanup(self):
        """Stops chart timers and releases resources on shutdown."""
        if getattr(self, "_cleaned_up", False):
            return
        self._cleaned_up = True
        self._suppress_overdue_prompts = True
        self._overdue_prompt_in_progress = False
        if getattr(self, "_gantt_toolbar_typography_connected", False):
            try:
                from todo_bird_app.controllers.task_controller import (
                    _GLOBAL_EVENT_BUS,
                )
                _GLOBAL_EVENT_BUS.typography_changed.disconnect(
                    self._sync_gantt_toolbar_typography_height
                )
            except Exception:
                pass
            self._gantt_toolbar_typography_connected = False
        if hasattr(self, "gantt_chart") and self.gantt_chart and hasattr(self.gantt_chart, "cleanup"):
            try:
                self.gantt_chart.cleanup()
            except Exception:
                pass
        try:
            super().cleanup()
        except Exception:
            pass

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)

    def populate_project_combo(self):
        if not hasattr(self, "project_combo") or self.project_combo is None:
            return
        self.project_combo.blockSignals(True)
        self.project_combo.clear()
        projects = self.task_controller.get_all_projects() if hasattr(self, "task_controller") and self.task_controller else []

        selected_idx = 0
        for idx, proj in enumerate(projects):
            p_id = proj.get("id") if isinstance(proj, dict) else getattr(proj, "id", None)
            p_name = proj.get("name") if isinstance(proj, dict) else getattr(proj, "name", "Project")
            self.project_combo.addItem(p_name, p_id)
            if self.current_project_id is not None and p_id == self.current_project_id:
                selected_idx = idx

        if projects:
            self.project_combo.setCurrentIndex(selected_idx)
            if self.current_project_id is None:
                self.current_project_id = self.project_combo.itemData(selected_idx)

        self.project_combo.blockSignals(False)

    def populate_compare_version_combo(self):
        if not hasattr(self, "compare_version_combo") or self.compare_version_combo is None:
            return
        self.compare_version_combo.blockSignals(True)
        self.compare_version_combo.clear()

        if self.current_project_id is not None and self.db_manager is not None:
            from todo_bird_app.services.schedule_version_service import ScheduleVersionService
            if ScheduleVersionService.has_original_baseline(
                self.db_manager,
                self.current_project_id,
                include_legacy=True,
            ):
                self.compare_version_combo.addItem("Original Baseline", "original")
            versions = self.db_manager.get_schedule_versions_for_project(self.current_project_id)
            for v in versions:
                if not v.get("is_original_baseline"):
                    self.compare_version_combo.addItem(v["name"], v["id"])

        self.compare_version_combo.addItem("None", "none")
        self.compare_version_combo.blockSignals(False)

    def on_gantt_project_changed(self, index: int):
        proj_id = self.project_combo.itemData(index)
        if proj_id is not None:
            self.set_current_project(proj_id)

    def on_gantt_compare_version_changed(self, index: int):
        ver_id = self.compare_version_combo.itemData(index)
        self.selected_compare_version_id = ver_id
        if hasattr(self, "settings_manager") and self.settings_manager:
            self.settings_manager.set("gantt_selected_compare_version_id", ver_id)
        self.refresh_data()

    def set_current_project(self, project_id: int):
        self.current_project_id = project_id
        if hasattr(self, "settings_manager") and self.settings_manager:
            self.settings_manager.set("gantt_selected_project_id", project_id)
        self.populate_project_combo()
        self.populate_compare_version_combo()
        self.refresh_data()

    def set_project_scope(self, project_id: int):
        """
        Called by NavigationController when Dashboard navigates to Gantt with explicit project_id.
        This has higher priority than last-viewed project.
        """
        self.set_current_project(project_id)

    def _navigate_to_wbs(self):
        try:
            window = self.window()
            if hasattr(window, "navigation_controller"):
                window.navigation_controller.set_active_section("wbs", self.current_project_id)
        except Exception as e:
            logger.warning(f"Failed to navigate to WBS: {e}")

    def fit_project_timeline(self):
        if hasattr(self, "gantt_chart") and self.gantt_chart and hasattr(self.gantt_chart, "go_to_today"):
            self.gantt_chart.go_to_today()

    def on_button_design_changed(self, index: int):
        val = self.button_design_combo.itemData(index)
        if not val:
            return
        if hasattr(self, "settings_manager") and self.settings_manager:
            self.settings_manager.set("button_design_mode", str(val))
        app_window = self.window()
        if hasattr(app_window, "theme_controller") and app_window.theme_controller:
            app_window.theme_controller.apply_theme(
                button_style=str(val),
            )
            return
        try:
            mode = ButtonStyleDesign(str(val))
            ModernButton.set_global_design_mode(mode)
        except Exception:
            pass
        self.update()

    def refresh_project_schedule(self, project_id: Optional[int] = None) -> int:
        """
        Single canonical project schedule refresh route.
        Reloads project tasks from DB, recalculates CPM schedule via WBSRollupService / CPMSchedulingService,
        rebuilds Gantt items, and repaints chart viewport.
        """
        count = self.refresh_data()
        if hasattr(self, "gantt_chart") and self.gantt_chart and hasattr(self.gantt_chart, "viewport"):
            vp = self.gantt_chart.viewport()
            if vp and hasattr(vp, "update"):
                vp.update()
        return count

    def refresh_data(self) -> int:
        all_tasks = self.task_controller.get_all_tasks()

        # Phase 1D canonical hierarchy authority.
        # Project rows now come from the same WBS snapshot + Phase1C rollups
        # used by the WBS planning view.
        gantt_items = self._build_phase1d_wbs_gantt_items(
            all_tasks
        )

        # --------------------------------------------------
        # Schedule-conflict authority
        # --------------------------------------------------
        overlap_ids = (
            self._hourly_overlap_task_ids(
                all_tasks
            )
        )

        for task in all_tasks:
            task.gantt_overlap = (
                task.id is not None
                and int(task.id)
                in overlap_ids
            )

        # gantt_items contains the SAME task objects for main rows,
        # so conflict metadata is now available to GanttTaskItem.
        # Nested rows are deliberately not marked until nested
        # resource/dependency semantics are introduced.

        projects = {
            p.id: p.name
            for p in self.task_controller.get_all_projects()
        }

        self._load_gantt_profile()
        app_theme = self.settings_manager.get("theme", "dark")
        self.gantt_chart.set_color_profile(
            self.color_profile,
            app_theme
        )
        # Ensure chart receives the currently selected bar design.
        if hasattr(self, "bar_style_combo"):
            self.gantt_chart.bar_style = (
                self.bar_style_combo.currentData()
                or "rounded"
            )

        if hasattr(self, "plan_color_combo"):
            self.gantt_chart.planned_bar_color = (
                self.plan_color_combo.currentData()
                or "#3584E4"
            )

        # Phase 1D presentation-only hierarchy collapse.
        # Both chart and left pane receive the SAME resulting row list.
        gantt_items = self._apply_gantt_collapse_visibility(
            gantt_items
        )

        self.gantt_chart.set_tasks(
            gantt_items,
            projects,
        )

        # Health/recovery authority must evaluate every task,
        # including tasks intentionally hidden from the Gantt chart.
        self._update_gantt_health(
            all_tasks
        )

        return len(gantt_items)

    def _time_to_minutes(self, value):
        if not value or ":" not in str(value):
            return None

        try:
            hh, mm = map(
                int,
                str(value).split(":")[:2],
            )
            return hh * 60 + mm
        except Exception:
            return None

    def _hourly_conflicts(
        self,
        payload,
    ):
        """
        Advisory-only Hourly overlap detection.

        Uses the application's normal TaskController rather than
        direct SQL so database connection differences cannot silently
        disable overlap detection.
        """
        if payload.get("zoom_mode") != "hourly":
            return []

        planned_date = payload.get(
            "planned_date"
        )

        start = self._time_to_minutes(
            payload.get(
                "planned_start_time"
            )
        )

        end = self._time_to_minutes(
            payload.get(
                "planned_end_time"
            )
        )

        if (
            not planned_date
            or start is None
            or end is None
        ):
            return []

        task_id = int(
            payload.get("task_id") or 0
        )

        conflicts = []

        try:
            candidates = (
                self.task_controller
                .get_all_tasks()
            )
        except Exception as exc:
            logger.exception(
                "Unable to check Gantt overlap: %s",
                exc,
            )
            return []

        for other in candidates:
            if other.id is None:
                continue

            if (
                task_id > 0
                and int(other.id)
                == task_id
            ):
                continue

            if other.status in (
                TaskStatus.COMPLETED,
                TaskStatus.CANCELLED,
            ):
                continue

            if other.planned_date != planned_date:
                continue

            other_start = self._time_to_minutes(
                other.planned_start_time
            )

            other_end = self._time_to_minutes(
                other.planned_end_time
            )

            # If end time is absent, derive it from duration.
            if (
                other_start is not None
                and other_end is None
                and int(
                    other.estimated_duration or 0
                ) > 0
            ):
                other_end = (
                    other_start
                    + int(
                        other.estimated_duration
                    )
                )

            if (
                other_start is None
                or other_end is None
            ):
                continue

            # Standard scheduling overlap:
            # A.start < B.end AND A.end > B.start.
            if (
                start < other_end
                and end > other_start
            ):
                conflicts.append(
                    other.title
                    or "Untitled"
                )

        return conflicts

    def _gantt_schedule_payload_targets_summary(
        self,
        item_type,
        task_id,
        payload,
    ):
        if bool(
            payload.get("gantt_is_summary")
            or payload.get("is_summary")
            or payload.get("gantt_read_only")
            or payload.get("read_only")
        ):
            return True

        if self.db_manager is None or int(task_id or 0) == 0:
            return False

        try:
            with self.db_manager.get_connection() as conn:
                if item_type == "subtask":
                    subtask_id = int(
                        payload.get("source_subtask_id")
                        or abs(int(task_id))
                    )
                    row = conn.execute(
                        """
                        SELECT 1
                        FROM subtasks
                        WHERE parent_subtask_id = ?
                        LIMIT 1;
                        """,
                        (subtask_id,),
                    ).fetchone()
                else:
                    row = conn.execute(
                        """
                        SELECT 1
                        FROM subtasks
                        WHERE task_id = ?
                        LIMIT 1;
                        """,
                        (int(task_id),),
                    ).fetchone()
        except Exception as exc:
            logger.warning(
                "Unable to prove Gantt schedule payload is leaf-only: %s",
                exc,
            )
            return True

        return row is not None


    def on_gantt_schedule_change(
        self,
        payload,
    ):
        if not payload:
            return

        item_type = payload.get(
            "item_type",
            "task",
        )

        task_id = int(
            payload.get(
                "task_id"
            )
            or 0
        )

        if self._gantt_schedule_payload_targets_summary(
            item_type,
            task_id,
            payload,
        ):
            logger.warning(
                "Ignored derived WBS summary schedule change payload: %s",
                payload.get("title") or payload.get("task_id"),
            )
            try:
                self.show_feedback_message(
                    "WBS summary schedules are derived from children."
                )
            except Exception:
                pass
            return

        planned_date = payload.get(
            "planned_date"
        )

        due_date = payload.get(
            "due_date"
        )

        start_time = payload.get(
            "planned_start_time"
        )

        end_time = payload.get(
            "planned_end_time"
        )

        estimated_duration = int(
            payload.get(
                "estimated_duration"
            )
            or 0
        )

        # --------------------------------------------------
        # Persist using narrow SQL updates.
        #
        # This deliberately avoids overwriting dependency,
        # progress, pin, blocker, icon or hierarchy metadata.
        # --------------------------------------------------
        with self.db_manager.get_connection() as conn:
            if item_type == "subtask":
                subtask_id = int(
                    payload.get(
                        "source_subtask_id"
                    )
                    or abs(task_id)
                )

                conn.execute(
                    """
                    UPDATE subtasks
                    SET planned_date = ?,
                        due_date = ?,
                        planned_start_time = ?,
                        planned_end_time = ?,
                        estimated_duration = ?
                    WHERE id = ?;
                    """,
                    (
                        planned_date,
                        due_date,
                        start_time,
                        end_time,
                        estimated_duration,
                        subtask_id,
                    ),
                )

            else:
                conn.execute(
                    """
                    UPDATE tasks
                    SET planned_date = ?,
                        due_date = ?,
                        planned_start_time = ?,
                        planned_end_time = ?,
                        estimated_duration = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?;
                    """,
                    (
                        planned_date,
                        due_date,
                        start_time,
                        end_time,
                        estimated_duration,
                        task_id,
                    ),
                )

            conn.commit()

        # --------------------------------------------------
        # Human-readable interaction feedback
        # --------------------------------------------------
        if payload.get("zoom_mode") == "hourly":
            message = (
                "Schedule updated — "
                f"{start_time} to {end_time}"
            )

            conflicts = self._hourly_conflicts(
                payload
            )

            if conflicts:
                preview = ", ".join(
                    conflicts[:3]
                )

                if len(conflicts) > 3:
                    preview += (
                        f" +{len(conflicts) - 3} more"
                    )

                message += (
                    "OVERLAP DETECTED — schedule saved anyway: "
                    + preview
                )

        else:
            delta_days = int(
                payload.get(
                    "delta_days"
                )
                or 0
            )

            sign = "+" if delta_days > 0 else ""

            message = (
                "Schedule moved "
                f"{sign}{delta_days} day(s) — "
                f"{planned_date}"
            )

            if due_date:
                message += (
                    f" → {due_date}"
                )

        # --------------------------------------------------
        # OPTIONAL DEPENDENCY AUTO-SHIFT
        #
        # Only main-task Finish→Start successors are moved.
        # Subtask dependency automation is intentionally deferred
        # until nested dependencies have an operator-facing editor.
        # --------------------------------------------------
        shifted_count = 0
        dependency_cycles = set()

        if (
            item_type == "task"
            and task_id > 0
        ):
            (
                shifted_count,
                dependency_cycles,
            ) = (
                self._apply_dependency_auto_shift(
                    task_id
                )
            )

        if shifted_count:
            message += (
                f"    {shifted_count} successor"
                + (
                    "s"
                    if shifted_count != 1
                    else ""
                )
                + " auto-shifted"
            )

        if (
            dependency_cycles
            and task_id
            in dependency_cycles
        ):
            message += (
                "   ⟳ dependency cycle detected — "
                "auto-shift skipped for cycle"
            )

        if (
            payload.get(
                "edit_kind"
            )
            == "resize"
        ):
            message = (
                "↔ Duration resized — "
                + message
            )

        self.show_feedback_message(
            message
        )

        # Rebuild from database truth.
        QTimer.singleShot(
            0,
            self.refresh_data,
        )

    def on_gantt_task_action(self, action: str, task_id: int):
        # Synthetic negative IDs are nested hierarchy rows.
        is_nested = task_id < 0

        chart_task = next(
            (
                candidate
                for candidate
                in self.gantt_chart.tasks
                if int(candidate.id or 0)
                == int(task_id)
            ),
            None,
        )

        if action == "copy_details":
            if chart_task is not None:
                proj_name = self._schedule_details_project_name(chart_task)
                model = ScheduleDetailsFormatter.build_from_entity(chart_task, project_name=proj_name, db_manager=self.db_manager)
                plain_text = ScheduleDetailsFormatter.format_plain_text(model)
                clipboard = QApplication.clipboard()
                if clipboard:
                    clipboard.setText(plain_text)
                ToastBanner.show_message(self, "Schedule details copied to clipboard!", "success")
            return

        if action == "view_details":
            if chart_task is not None:
                from PySide6.QtGui import QCursor
                proj_name = self._schedule_details_project_name(chart_task)
                popover = ScheduleDetailsPopover(
                    chart_task,
                    parent=self,
                    project_name=proj_name,
                    db_manager=self.db_manager,
                    is_dark=self._is_dark,
                    accent_color=self._accent_color,
                )
                popover.popup_at_point(QCursor.pos())
            return

        if action == "open":
            # Check if this is a subtask (nested, synthetic negative id, or subtask item type)
            is_subtask = is_nested or (chart_task and getattr(chart_task, "gantt_item_type", "task") != "task")
            if is_subtask and self.db_manager:
                subtask_id = getattr(chart_task, "gantt_entity_id", None) or abs(task_id)
                subtask_dict = self.db_manager.get_subtask_by_id(int(subtask_id))
                if subtask_dict:
                    parent_task_id = subtask_dict.get("task_id") or getattr(chart_task, "parent_task_id", None)
                    parent_task = self.task_controller.get_task(int(parent_task_id)) if parent_task_id else None
                    dlg = SubtaskDialog(
                        subtask=subtask_dict,
                        parent_task=parent_task or parent_task_id or 0,
                        db_manager=self.db_manager,
                        settings_manager=self.settings_manager,
                        parent=self,
                    )
                    if dlg.exec() == SubtaskDialog.Accepted:
                        if hasattr(self, "refresh_project_schedule"):
                            self.refresh_project_schedule(self.selected_project_id)
                        self.refresh_data()
                        ToastBanner.show_message(self, "Subtask updated successfully!", "success")
                    return

            # Check if this is a summary row
            if chart_task and getattr(chart_task, "gantt_is_summary", False):
                raw_parent_id = getattr(chart_task, "parent_task_id", None) or getattr(chart_task, "id", None)
                if raw_parent_id and int(raw_parent_id) > 0:
                    parent_task = self.task_controller.get_task(int(raw_parent_id))
                    if parent_task:
                        projects = self.task_controller.get_all_projects()
                        dlg = TaskDialog(projects, parent_task, db_manager=self.db_manager, settings_manager=self.settings_manager, parent=self)
                        if dlg.exec() == TaskDialog.Accepted:
                            self.task_controller.update_task(dlg.get_task())
                            if hasattr(self, "refresh_project_schedule"):
                                self.refresh_project_schedule(self.selected_project_id)
                            self.refresh_data()
                            ToastBanner.show_message(self, "Task updated successfully!", "success")
                        return
                ToastBanner.show_message(self, "Summary row displays rolled-up schedule metrics.", "info")
                return

            # Main Task
            task = self.task_controller.get_task(int(task_id))
            if not task:
                return
            projects = self.task_controller.get_all_projects()
            dlg = TaskDialog(projects, task, db_manager=self.db_manager, settings_manager=self.settings_manager, parent=self)
            if dlg.exec() == TaskDialog.Accepted:
                self.task_controller.update_task(dlg.get_task())
                if hasattr(self, "refresh_project_schedule"):
                    self.refresh_project_schedule(self.selected_project_id)
                self.refresh_data()
                ToastBanner.show_message(self, "Task updated successfully!", "success")
            return

        if is_nested:
            parent_task_id = (
                getattr(
                    chart_task,
                    "parent_task_id",
                    None,
                )
                if chart_task is not None
                else None
            )
            if parent_task_id is None:
                return
            task = self.task_controller.get_task(int(parent_task_id))
        else:
            task = self.task_controller.get_task(task_id)

        if not task:
            return
        elif action == "complete":
            timing_status, delay_mins, delay_pct = self.delay_engine.analyze_task_timing(task)
            task.delay_minutes = delay_mins
            task.delay_percentage = delay_pct

            if self.delay_engine.requires_justification(timing_status):
                jdlg = DelayJustificationDialog(task, delay_minutes=delay_mins, parent=self)
                if jdlg.exec() == DelayJustificationDialog.Accepted:
                    task.delay_reason = jdlg.selected_reason
                    task.delay_notes = jdlg.notes
                    task.delay_recorded_at = date.today().strftime("%Y-%m-%d %H:%M")

            self.task_controller.toggle_task_complete(task_id)

            is_must = (task.priority == TaskPriority.URGENT) or ("must_do" in task.tags)
            msg = self.appreciation_system.get_appreciation(timing_status, is_must_do=is_must)
            if msg:
                QMessageBox.information(self, "Appreciation", msg)

        elif action == "start":
            task.status = TaskStatus.IN_PROGRESS
            task.actual_start_time = datetime.now().strftime("%H:%M")
            self.task_controller.update_task(task)
        elif action == "pause":
            task.status = TaskStatus.INBOX
            if "paused" not in task.tags:
                task.tags.append("paused")
            self.task_controller.update_task(task)
        elif action == "add_delay_reason":
            timing_status, delay_mins, _ = self.delay_engine.analyze_task_timing(task)
            jdlg = DelayJustificationDialog(task, delay_minutes=delay_mins, parent=self)
            if jdlg.exec() == DelayJustificationDialog.Accepted:
                task.delay_reason = jdlg.selected_reason
                task.delay_notes = jdlg.notes
                task.delay_recorded_at = date.today().strftime("%Y-%m-%d %H:%M")
                self.task_controller.update_task(task)
        elif action == "mark_milestone":
            if "milestone" not in task.tags:
                task.tags.append("milestone")
            self.task_controller.update_task(task)

    def _schedule_details_project_name(self, task) -> str:
        project_id = getattr(task, "project_id", None)
        if project_id is None:
            return "Inbox"
        projects_map = getattr(self, "projects_map", {}) or {}
        if project_id in projects_map:
            return str(projects_map[project_id])
        chart = getattr(self, "gantt_chart", None)
        chart_map = getattr(chart, "projects_map", {}) or {}
        if project_id in chart_map:
            return str(chart_map[project_id])
        if self.db_manager is not None:
            try:
                project = self.db_manager.get_project(int(project_id))
                if isinstance(project, dict):
                    return str(project.get("name") or f"Project #{project_id}")
                name = getattr(project, "name", None)
                if name:
                    return str(name)
            except Exception:
                pass
        return f"Project #{project_id}"
