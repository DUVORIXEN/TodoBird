"""
TODO BIRD — WBS APPEARANCE SETTINGS & LIVE PREVIEW WIDGET
Provides an interactive customization panel with miniature live preview of tree rows,
density modes (Professional, Balanced, Personal), toggle switches, and reset capability.
"""

from typing import Optional, Any, Dict
from PySide6.QtCore import Qt, QRectF, QSize, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QScrollArea,
    QFrame,
)
from PySide6.QtGui import (
    QPainter,
    QPainterPath,
    QColor,
    QPen,
    QBrush,
    QFont,
)

from todo_bird_app.ui.design_tokens import DesignTokens
from todo_bird_app.services.wbs_customization_service import WBSCustomizationService
from todo_bird_app.ui.components.segmented_control import SegmentedControl
from todo_bird_app.ui.components.toggle_switch import ToggleSwitch
from todo_bird_app.ui.components.modern_button import ModernButton, ButtonVariant, ButtonSize
from todo_bird_app.ui.components.section_card import SectionCard
from todo_bird_app.ui.components.status_badge import render_milestone_diamond
from todo_bird_app.services.icon_service import IconService


class WBSLivePreviewCanvas(QWidget):
    """
    Miniature live preview canvas rendering sample WBS hierarchy dynamically.
    Reflects density, WBS codes, progress bars, status badges, icons, and guide lines.
    """

    def __init__(
        self,
        service: WBSCustomizationService,
        parent: Optional[QWidget] = None,
        is_dark: bool = True,
        accent_color: str = DesignTokens.COLOR_ACCENT,
    ):
        super().__init__(parent)
        self._service = service
        self._is_dark = is_dark
        self._accent_color = accent_color
        # 150px is the preferred compact baseline, not an absolute
        # ceiling. Large typography must be allowed to request more room.
        self.setMinimumHeight(150)
        self.setMinimumWidth(320)

    def set_theme(self, is_dark: bool, accent_color: Optional[str] = None):
        self._is_dark = is_dark
        if accent_color:
            self._accent_color = accent_color
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        metrics = self._service.get_density_metrics()
        show_code = self._service.get_preference("wbs_show_code", True)
        show_progress = self._service.get_preference("wbs_show_progress", True)
        show_status = self._service.get_preference("wbs_show_status", True)
        show_icons = self._service.get_preference("wbs_show_icons", True)
        show_guides = self._service.get_preference("wbs_show_guide_lines", True)

        w = self.width()
        h = self.height()
        canvas_rect = QRectF(1, 1, w - 2, h - 2)

        # Container Background & Border
        surfaces = self._service.get_surface_colors(self._is_dark, self._accent_color)
        bg_col = QColor(surfaces["bg_panel"])
        border_col = QColor(surfaces["border_panel"])
        painter.fillPath(self._rounded(canvas_rect, 8), QBrush(bg_col))
        painter.strokePath(self._rounded(canvas_rect, 8), QPen(border_col, 1.0))

        # Sample preview nodes
        sample_rows = [
            {"code": "1.2", "title": "Product Validation", "depth": 0, "is_parent": True, "progress": 62, "status": "In Progress", "is_milestone": False, "selected": False},
            {"code": "1.2.1", "title": "Wet Field Testing", "depth": 1, "is_parent": False, "progress": 80, "status": "Completed", "is_milestone": False, "selected": True},
            {"code": "1.2.2", "title": "Engineering Milestone Gate", "depth": 1, "is_parent": False, "progress": 0, "status": "Milestone", "is_milestone": True, "selected": False},
        ]

        row_h = metrics.row_height
        indent_px = metrics.indent_px
        start_y = 12.0

        accent = QColor(self._accent_color)
        text_primary = QColor(surfaces["text_primary"])
        text_secondary = QColor(surfaces["text_secondary"])
        guide_alpha = surfaces.get("guide_alpha", 20)
        guide_col = QColor(255, 255, 255, guide_alpha) if self._is_dark else QColor(0, 0, 0, guide_alpha)

        font = painter.font()
        font.setPointSize(metrics.font_size)
        painter.setFont(font)

        for i, node in enumerate(sample_rows):
            y = start_y + i * row_h
            if y + row_h > h - 4:
                break

            row_rect = QRectF(2, y, w - 4, row_h)

            # Row background
            if node["selected"]:
                sel_alpha = surfaces.get("selected_alpha", 45)
                painter.fillRect(row_rect, QColor(accent.red(), accent.green(), accent.blue(), sel_alpha))
                ind_bar = QRectF(row_rect.x() + 1.0, row_rect.y() + 2.0, 3.0, row_rect.height() - 4.0)
                ind_path = QPainterPath()
                ind_path.addRoundedRect(ind_bar, 1.5, 1.5)
                painter.fillPath(ind_path, QBrush(accent))
            elif node["is_parent"]:
                sum_alpha = surfaces.get("summary_alpha", 12)
                sum_bg = QColor(255, 255, 255, sum_alpha) if self._is_dark else QColor(0, 0, 0, sum_alpha)
                painter.fillRect(row_rect, sum_bg)

            cur_x = 16.0 + node["depth"] * indent_px

            # 1. Guide lines
            if show_guides and node["depth"] > 0:
                parent_cx = 16.0 + 8.0
                pen_guide = QPen(guide_col, 1.0, Qt.DashLine)
                painter.setPen(pen_guide)
                painter.drawLine(parent_cx, y - row_h / 2.0, parent_cx, y + row_h / 2.0)
                painter.drawLine(parent_cx, y + row_h / 2.0, cur_x - 4, y + row_h / 2.0)

            # 2. Expander / Chevron / Leaf Indicator
            if node["is_parent"]:
                chevron_box = QRectF(cur_x, y + (row_h - 12) / 2.0, 12, 12)
                IconService.render_vector_icon(painter, "chevron_down", chevron_box, accent, stroke_width=1.8)
                cur_x += 16
            else:
                cur_x += 12

            # 3. WBS Outline Code
            if show_code:
                font.setWeight(QFont.DemiBold if node["is_parent"] else QFont.Normal)
                painter.setFont(font)
                painter.setPen(accent if node["is_parent"] else text_secondary)
                code_str = f"{node['code']} "
                painter.drawText(QRectF(cur_x, y, 45, row_h), Qt.AlignVCenter | Qt.AlignLeft, code_str)
                cur_x += 42

            # 4. Icon / Milestone Diamond
            if show_icons:
                if node["is_milestone"]:
                    diamond_box = QRectF(cur_x, y + (row_h - 10) / 2.0, 10, 10)
                    render_milestone_diamond(painter, diamond_box, QColor("#8B5CF6"))
                    cur_x += 16
                elif node["is_parent"]:
                    icon_box = QRectF(cur_x, y + (row_h - 12) / 2.0, 12, 12)
                    IconService.render_vector_icon(painter, "folder", icon_box, accent, stroke_width=1.4)
                    cur_x += 16
                else:
                    icon_box = QRectF(cur_x, y + (row_h - 12) / 2.0, 12, 12)
                    IconService.render_vector_icon(painter, "task", icon_box, text_secondary, stroke_width=1.4)
                    cur_x += 16

            # 5. Title Text
            font.setWeight(QFont.DemiBold if node["is_parent"] else QFont.Normal)
            painter.setFont(font)
            painter.setPen(text_primary)
            title_w = w - cur_x - (130 if show_progress else 20)
            painter.drawText(QRectF(cur_x, y, max(title_w, 60), row_h), Qt.AlignVCenter | Qt.AlignLeft, node["title"])

            # 6. Mini Progress Bar
            if show_progress:
                prog_x = w - 110
                prog_y = y + (row_h - 6) / 2.0
                prog_w = 50.0
                prog_h = 6.0
                pct = node["progress"] / 100.0

                # Track
                painter.fillPath(self._rounded(QRectF(prog_x, prog_y, prog_w, prog_h), 3), QBrush(QColor(surfaces["border_subtle"])))
                # Fill
                fill_col = QColor(DesignTokens.COLOR_SUCCESS) if pct >= 1.0 else accent
                if pct > 0:
                    painter.fillPath(self._rounded(QRectF(prog_x, prog_y, prog_w * pct, prog_h), 3), QBrush(fill_col))

                # Pct Text
                font.setPointSize(10)
                font.setWeight(QFont.Normal)
                painter.setFont(font)
                painter.setPen(text_secondary)
                painter.drawText(QRectF(prog_x + prog_w + 6, y, 40, row_h), Qt.AlignVCenter | Qt.AlignLeft, f"{node['progress']}%")

        painter.end()

    def _rounded(self, rect: QRectF, radius: float) -> QPainterPath:
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        return path


class WBSSettingsWidget(QWidget):
    """
    WBS & Project Planning Appearance Customization Panel.
    Integrates live preview, density switching, surface styles, visibility toggles, motion settings, and defaults reset.
    """

    preferencesChanged = Signal()

    def __init__(
        self,
        service: WBSCustomizationService,
        parent: Optional[QWidget] = None,
        is_dark: bool = True,
        accent_color: str = DesignTokens.COLOR_ACCENT,
    ):
        super().__init__(parent)
        self._service = service
        self._is_dark = is_dark
        self._accent_color = accent_color

        main_vbox = QVBoxLayout(self)
        main_vbox.setContentsMargins(16, 16, 16, 16)
        main_vbox.setSpacing(16)

        # ---------------------------------------------------------------------
        # 1. Live Preview Card
        # ---------------------------------------------------------------------
        preview_card = SectionCard("Live Preview", "Real-time visualization of your WBS configuration", is_dark=is_dark, accent_color=accent_color)
        self._preview_canvas = WBSLivePreviewCanvas(service, is_dark=is_dark, accent_color=accent_color)
        preview_card.get_content_layout().addWidget(self._preview_canvas)
        main_vbox.addWidget(preview_card)

        # ---------------------------------------------------------------------
        # 2. Surface Style & Contrast Card
        # ---------------------------------------------------------------------
        surface_card = SectionCard("Surface Style & Hierarchy Contrast", "Configure background panels, summary elevation, and guide line contrast", is_dark=is_dark, accent_color=accent_color)
        surf_layout = surface_card.get_content_layout()

        # Surface Style
        cur_style = self._service.get_preference("wbs_surface_style", "clean")
        style_idx = 1 if cur_style == "soft_panels" else (2 if cur_style == "minimal" else 0)
        self._style_control = SegmentedControl(
            segments=[("Clean", "clean"), ("Soft Panels", "soft_panels"), ("Minimal", "minimal")],
            selected_index=style_idx,
            is_dark=is_dark,
            accent_color=accent_color,
        )
        self._style_control.valueChanged.connect(lambda idx, lbl, data: self._update_pref("wbs_surface_style", str(data)))
        surf_layout.addWidget(QLabel("Surface Style:"))
        surf_layout.addWidget(self._style_control)

        # Summary Emphasis
        cur_emp = self._service.get_preference("wbs_summary_emphasis", "standard")
        emp_idx = 1 if cur_emp == "subtle" else (2 if cur_emp == "strong" else 0)
        self._emphasis_control = SegmentedControl(
            segments=[("Standard", "standard"), ("Subtle", "subtle"), ("Strong", "strong")],
            selected_index=emp_idx,
            is_dark=is_dark,
            accent_color=accent_color,
        )
        self._emphasis_control.valueChanged.connect(lambda idx, lbl, data: self._update_pref("wbs_summary_emphasis", str(data)))
        surf_layout.addWidget(QLabel("Summary Row Emphasis:"))
        surf_layout.addWidget(self._emphasis_control)

        # Guide Contrast
        cur_contrast = self._service.get_preference("wbs_guide_contrast", "low")
        con_idx = 1 if cur_contrast == "medium" else (2 if cur_contrast == "high" else 0)
        self._contrast_control = SegmentedControl(
            segments=[("Low", "low"), ("Medium", "medium"), ("High", "high")],
            selected_index=con_idx,
            is_dark=is_dark,
            accent_color=accent_color,
        )
        self._contrast_control.valueChanged.connect(lambda idx, lbl, data: self._update_pref("wbs_guide_contrast", str(data)))
        surf_layout.addWidget(QLabel("Hierarchy Guide Line Contrast:"))
        surf_layout.addWidget(self._contrast_control)

        main_vbox.addWidget(surface_card)

        # ---------------------------------------------------------------------
        # 3. Density & Hierarchy Options Card
        # ---------------------------------------------------------------------
        options_card = SectionCard("WBS Layout & Density", "Configure row height, hierarchy spacing, and columns", is_dark=is_dark, accent_color=accent_color)
        opts_layout = options_card.get_content_layout()

        # Density Segmented Control
        cur_density = self._service.get_preference("wbs_density", "balanced")
        density_idx = 0 if cur_density == "professional" else (2 if cur_density == "personal" else 1)
        self._density_control = SegmentedControl(
            segments=[("Professional (28px)", "professional"), ("Balanced (36px)", "balanced"), ("Personal (44px)", "personal")],
            selected_index=density_idx,
            is_dark=is_dark,
            accent_color=accent_color,
        )
        self._density_control.valueChanged.connect(self._on_density_changed)
        opts_layout.addWidget(QLabel("Density Mode:"))
        opts_layout.addWidget(self._density_control)

        # Grid of Toggles
        grid = QGridLayout()
        grid.setSpacing(12)

        self._tgl_code = ToggleSwitch("Show WBS Codes (1.2.1)", self._service.get_preference("wbs_show_code", True), is_dark=is_dark, accent_color=accent_color)
        self._tgl_code.toggledState.connect(lambda val: self._update_pref("wbs_show_code", val))
        grid.addWidget(self._tgl_code, 0, 0)

        self._tgl_progress = ToggleSwitch("Show Progress Bars", self._service.get_preference("wbs_show_progress", True), is_dark=is_dark, accent_color=accent_color)
        self._tgl_progress.toggledState.connect(lambda val: self._update_pref("wbs_show_progress", val))
        grid.addWidget(self._tgl_progress, 0, 1)

        self._tgl_status = ToggleSwitch("Show Status Badges", self._service.get_preference("wbs_show_status", True), is_dark=is_dark, accent_color=accent_color)
        self._tgl_status.toggledState.connect(lambda val: self._update_pref("wbs_show_status", val))
        grid.addWidget(self._tgl_status, 1, 0)

        self._tgl_icons = ToggleSwitch("Show Folder / Document Icons", self._service.get_preference("wbs_show_icons", True), is_dark=is_dark, accent_color=accent_color)
        self._tgl_icons.toggledState.connect(lambda val: self._update_pref("wbs_show_icons", val))
        grid.addWidget(self._tgl_icons, 1, 1)

        self._tgl_guides = ToggleSwitch("Show Hierarchy Guide Lines", self._service.get_preference("wbs_show_guide_lines", True), is_dark=is_dark, accent_color=accent_color)
        self._tgl_guides.toggledState.connect(lambda val: self._update_pref("wbs_show_guide_lines", val))
        grid.addWidget(self._tgl_guides, 2, 0)

        opts_layout.addLayout(grid)
        main_vbox.addWidget(options_card)

        # ---------------------------------------------------------------------
        # 4. Parent Rollup Display — Phase 1C derived rollups (no DB mutation)
        # ---------------------------------------------------------------------
        rollup_card = SectionCard(
            "Parent Rollup Display",
            "Control derived parent rollups (progress / effort / dates) — leaf-only aggregation",
            is_dark=is_dark,
            accent_color=accent_color,
        )
        rollup_layout = rollup_card.get_content_layout()
        rollup_grid = QGridLayout()
        rollup_grid.setSpacing(12)

        self._tgl_rollup_progress = ToggleSwitch(
            "Show Parent Rollup Progress",
            self._service.get_preference("wbs_show_parent_rollup_progress", True),
            is_dark=is_dark,
            accent_color=accent_color,
        )
        self._tgl_rollup_progress.setToolTip("When on, parent rows show effort-weighted rollup progress from leaves (not stored value).")
        self._tgl_rollup_progress.toggledState.connect(lambda val: self._update_pref("wbs_show_parent_rollup_progress", val))
        rollup_grid.addWidget(self._tgl_rollup_progress, 0, 0)

        self._tgl_rollup_effort = ToggleSwitch(
            "Show Parent Effort Summary",
            self._service.get_preference("wbs_show_parent_effort_summary", False),
            is_dark=is_dark,
            accent_color=accent_color,
        )
        self._tgl_rollup_effort.setToolTip("When on, parent tooltip/row shows summed planned vs actual effort from leaves.")
        self._tgl_rollup_effort.toggledState.connect(lambda val: self._update_pref("wbs_show_parent_effort_summary", val))
        rollup_grid.addWidget(self._tgl_rollup_effort, 0, 1)

        self._tgl_rollup_dates = ToggleSwitch(
            "Show Parent Planned Dates",
            self._service.get_preference("wbs_show_parent_dates", False),
            is_dark=is_dark,
            accent_color=accent_color,
        )
        self._tgl_rollup_dates.setToolTip("When on, parent rows expose earliest planned start → latest planned finish from leaves.")
        self._tgl_rollup_dates.toggledState.connect(lambda val: self._update_pref("wbs_show_parent_dates", val))
        rollup_grid.addWidget(self._tgl_rollup_dates, 1, 0)

        rollup_layout.addLayout(rollup_grid)
        # Small hint label — remains readable in both themes
        hint = QLabel("Progress rollup is leaf-only, calendar-elapsed, no working-calendar adjustment. Effort/dates are leaf aggregates.")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {'#A6ADC8' if is_dark else '#64748B'}; font-size: 11px;")
        rollup_layout.addWidget(hint)
        main_vbox.addWidget(rollup_card)

        # ---------------------------------------------------------------------
        # 4b. Schedule Intelligence Columns — Phase 2B professional CPM columns
        # ---------------------------------------------------------------------
        cpm_card = SectionCard(
            "Schedule Intelligence Columns",
            "Configure visible Critical Path Method (CPM) and Float columns in WBS",
            is_dark=is_dark,
            accent_color=accent_color,
        )
        cpm_layout = cpm_card.get_content_layout()
        cpm_grid = QGridLayout()
        cpm_grid.setSpacing(12)

        self._tgl_critical = ToggleSwitch(
            "Show Critical Path Column",
            self._service.get_preference("wbs_show_critical", True),
            is_dark=is_dark,
            accent_color=accent_color,
        )
        self._tgl_critical.toggledState.connect(lambda val: self._update_pref("wbs_show_critical", val))
        cpm_grid.addWidget(self._tgl_critical, 0, 0)

        self._tgl_total_float = ToggleSwitch(
            "Show Total Float Column",
            self._service.get_preference("wbs_show_total_float", True),
            is_dark=is_dark,
            accent_color=accent_color,
        )
        self._tgl_total_float.toggledState.connect(lambda val: self._update_pref("wbs_show_total_float", val))
        cpm_grid.addWidget(self._tgl_total_float, 0, 1)

        self._tgl_free_float = ToggleSwitch(
            "Show Free Float Column",
            self._service.get_preference("wbs_show_free_float", False),
            is_dark=is_dark,
            accent_color=accent_color,
        )
        self._tgl_free_float.toggledState.connect(lambda val: self._update_pref("wbs_show_free_float", val))
        cpm_grid.addWidget(self._tgl_free_float, 1, 0)

        self._tgl_es_ef = ToggleSwitch(
            "Show Earliest Start / Finish (ES/EF)",
            self._service.get_preference("wbs_show_es", False) and self._service.get_preference("wbs_show_ef", False),
            is_dark=is_dark,
            accent_color=accent_color,
        )
        def _on_es_ef_toggled(val):
            self._update_pref("wbs_show_es", val)
            self._update_pref("wbs_show_ef", val)
        self._tgl_es_ef.toggledState.connect(_on_es_ef_toggled)
        cpm_grid.addWidget(self._tgl_es_ef, 1, 1)

        self._tgl_ls_lf = ToggleSwitch(
            "Show Latest Start / Finish (LS/LF)",
            self._service.get_preference("wbs_show_ls", False) and self._service.get_preference("wbs_show_lf", False),
            is_dark=is_dark,
            accent_color=accent_color,
        )
        def _on_ls_lf_toggled(val):
            self._update_pref("wbs_show_ls", val)
            self._update_pref("wbs_show_lf", val)
        self._tgl_ls_lf.toggledState.connect(_on_ls_lf_toggled)
        cpm_grid.addWidget(self._tgl_ls_lf, 2, 0)

        self._tgl_diag = ToggleSwitch(
            "Show Schedule Health / Diagnostics",
            self._service.get_preference("wbs_show_diagnostics", False),
            is_dark=is_dark,
            accent_color=accent_color,
        )
        self._tgl_diag.toggledState.connect(lambda val: self._update_pref("wbs_show_diagnostics", val))
        cpm_grid.addWidget(self._tgl_diag, 2, 1)

        cpm_layout.addLayout(cpm_grid)
        main_vbox.addWidget(cpm_card)

        # ---------------------------------------------------------------------
        # 4c. Schedule Baseline & Variance Columns — Phase 2D Baseline & Control
        # ---------------------------------------------------------------------
        baseline_card = SectionCard(
            "Schedule Baseline & Variance Columns",
            "Configure Baseline 1 snapshot comparison and schedule variance columns in WBS & Gantt",
            is_dark=is_dark,
            accent_color=accent_color,
        )
        baseline_layout = baseline_card.get_content_layout()
        baseline_grid = QGridLayout()
        baseline_grid.setSpacing(12)

        self._tgl_finish_variance = ToggleSwitch(
            "Show Finish Variance Column",
            self._service.get_preference("wbs_show_finish_variance", True),
            is_dark=is_dark,
            accent_color=accent_color,
        )
        self._tgl_finish_variance.setToolTip("Displays current finish minus baseline finish (+ahead, -behind).")
        self._tgl_finish_variance.toggledState.connect(lambda val: self._update_pref("wbs_show_finish_variance", val))
        baseline_grid.addWidget(self._tgl_finish_variance, 0, 0)

        self._tgl_start_variance = ToggleSwitch(
            "Show Start Variance Column",
            self._service.get_preference("wbs_show_start_variance", False),
            is_dark=is_dark,
            accent_color=accent_color,
        )
        self._tgl_start_variance.setToolTip("Displays current start minus baseline start.")
        self._tgl_start_variance.toggledState.connect(lambda val: self._update_pref("wbs_show_start_variance", val))
        baseline_grid.addWidget(self._tgl_start_variance, 0, 1)

        self._tgl_baseline_dates = ToggleSwitch(
            "Show Baseline Start / Finish Columns",
            self._service.get_preference("wbs_show_baseline_start", False) and self._service.get_preference("wbs_show_baseline_finish", False),
            is_dark=is_dark,
            accent_color=accent_color,
        )
        def _on_baseline_dates_toggled(val):
            self._update_pref("wbs_show_baseline_start", val)
            self._update_pref("wbs_show_baseline_finish", val)
        self._tgl_baseline_dates.toggledState.connect(_on_baseline_dates_toggled)
        baseline_grid.addWidget(self._tgl_baseline_dates, 1, 0)

        self._tgl_duration_variance = ToggleSwitch(
            "Show Duration Variance Column",
            self._service.get_preference("wbs_show_duration_variance", False),
            is_dark=is_dark,
            accent_color=accent_color,
        )
        self._tgl_duration_variance.toggledState.connect(lambda val: self._update_pref("wbs_show_duration_variance", val))
        baseline_grid.addWidget(self._tgl_duration_variance, 1, 1)

        self._tgl_gantt_baseline = ToggleSwitch(
            "Show Baseline Bars in Gantt",
            self._service.get_preference("gantt_show_baseline", True),
            is_dark=is_dark,
            accent_color=accent_color,
        )
        self._tgl_gantt_baseline.setToolTip("Renders frozen Baseline 1 snapshot bars underneath current working schedule bars.")
        self._tgl_gantt_baseline.toggledState.connect(lambda val: self._update_pref("gantt_show_baseline", val))
        baseline_grid.addWidget(self._tgl_gantt_baseline, 2, 0)

        baseline_layout.addLayout(baseline_grid)
        b_hint = QLabel("Baseline 1 represents the frozen approved project schedule. Variances = Current Schedule − Baseline 1.")
        b_hint.setWordWrap(True)
        b_hint.setStyleSheet(f"color: {'#A6ADC8' if is_dark else '#64748B'}; font-size: 11px;")
        baseline_layout.addWidget(b_hint)
        main_vbox.addWidget(baseline_card)

        # ---------------------------------------------------------------------
        # 4d. Schedule Constraints & Deadlines Columns — Phase 2E Controls
        # ---------------------------------------------------------------------
        constraint_card = SectionCard(
            "Schedule Constraints & Deadlines Columns",
            "Configure visible CPM constraint types, dates, deadlines, and variance tracking in WBS",
            is_dark=is_dark,
            accent_color=accent_color,
        )
        constraint_layout = constraint_card.get_content_layout()
        constraint_grid = QGridLayout()
        constraint_grid.setSpacing(12)

        self._tgl_constraint_type = ToggleSwitch(
            "Show Constraint Type Column",
            self._service.get_preference("wbs_show_constraint_type", True),
            is_dark=is_dark,
            accent_color=accent_color,
        )
        self._tgl_constraint_type.toggledState.connect(lambda val: self._update_pref("wbs_show_constraint_type", val))
        constraint_grid.addWidget(self._tgl_constraint_type, 0, 0)

        self._tgl_constraint_date = ToggleSwitch(
            "Show Constraint Date Column",
            self._service.get_preference("wbs_show_constraint_date", True),
            is_dark=is_dark,
            accent_color=accent_color,
        )
        self._tgl_constraint_date.toggledState.connect(lambda val: self._update_pref("wbs_show_constraint_date", val))
        constraint_grid.addWidget(self._tgl_constraint_date, 0, 1)

        self._tgl_deadline = ToggleSwitch(
            "Show Deadline Column",
            self._service.get_preference("wbs_show_deadline", False),
            is_dark=is_dark,
            accent_color=accent_color,
        )
        self._tgl_deadline.toggledState.connect(lambda val: self._update_pref("wbs_show_deadline", val))
        constraint_grid.addWidget(self._tgl_deadline, 1, 0)

        self._tgl_deadline_variance = ToggleSwitch(
            "Show Deadline Variance Column",
            self._service.get_preference("wbs_show_deadline_variance", False),
            is_dark=is_dark,
            accent_color=accent_color,
        )
        self._tgl_deadline_variance.toggledState.connect(lambda val: self._update_pref("wbs_show_deadline_variance", val))
        constraint_grid.addWidget(self._tgl_deadline_variance, 1, 1)

        self._tgl_constraint_status = ToggleSwitch(
            "Show Constraint Status Column",
            self._service.get_preference("wbs_show_constraint_status", True),
            is_dark=is_dark,
            accent_color=accent_color,
        )
        self._tgl_constraint_status.toggledState.connect(lambda val: self._update_pref("wbs_show_constraint_status", val))
        constraint_grid.addWidget(self._tgl_constraint_status, 2, 0)

        constraint_layout.addLayout(constraint_grid)
        c_hint = QLabel("Constraints (SNET, MSO, FNLT, etc.) restrict early/late boundaries. Deadlines monitor target commitment without altering CPM math.")
        c_hint.setWordWrap(True)
        c_hint.setStyleSheet(f"color: {'#A6ADC8' if is_dark else '#64748B'}; font-size: 11px;")
        constraint_layout.addWidget(c_hint)
        main_vbox.addWidget(constraint_card)

        # ---------------------------------------------------------------------
        # 5. Motion & Animation Policy
        # ---------------------------------------------------------------------
        motion_card = SectionCard("Animation & Accessibility", "Control UI motion and chevron rotation", is_dark=is_dark, accent_color=accent_color)
        motion_layout = motion_card.get_content_layout()

        cur_anim = self._service.get_preference("ui_animation_mode", "full")
        anim_idx = 1 if cur_anim == "reduced" else (2 if cur_anim == "off" else 0)
        self._anim_control = SegmentedControl(
            segments=[("Full Motion", "full"), ("Reduced Motion", "reduced"), ("No Motion", "off")],
            selected_index=anim_idx,
            is_dark=is_dark,
            accent_color=accent_color,
        )
        self._anim_control.valueChanged.connect(self._on_anim_changed)
        motion_layout.addWidget(QLabel("Motion Policy:"))
        motion_layout.addWidget(self._anim_control)
        main_vbox.addWidget(motion_card)

        self._cards = [preview_card, surface_card, options_card, rollup_card, cpm_card, baseline_card, constraint_card, motion_card]

        # ---------------------------------------------------------------------
        # 6. Actions Row (Reset to Defaults)
        # ---------------------------------------------------------------------
        actions_hbox = QHBoxLayout()
        actions_hbox.addStretch()

        self._reset_btn = ModernButton("Reset WBS Appearance to Defaults", variant=ButtonVariant.SECONDARY, size=ButtonSize.STANDARD, is_dark=is_dark, accent_color=accent_color)
        self._reset_btn.clicked.connect(self._on_reset_clicked)
        actions_hbox.addWidget(self._reset_btn)

        main_vbox.addLayout(actions_hbox)
        main_vbox.addStretch()

    def set_theme(self, is_dark: bool, accent_color: Optional[str] = None):
        self._is_dark = is_dark
        if accent_color:
            self._accent_color = accent_color
        self._preview_canvas.set_theme(is_dark, accent_color)
        self._style_control.set_theme(is_dark, accent_color)
        self._emphasis_control.set_theme(is_dark, accent_color)
        self._contrast_control.set_theme(is_dark, accent_color)
        self._density_control.set_theme(is_dark, accent_color)
        self._anim_control.set_theme(is_dark, accent_color)
        self._tgl_code.set_theme(is_dark, accent_color)
        self._tgl_progress.set_theme(is_dark, accent_color)
        self._tgl_status.set_theme(is_dark, accent_color)
        self._tgl_icons.set_theme(is_dark, accent_color)
        self._tgl_guides.set_theme(is_dark, accent_color)
        for card in getattr(self, "_cards", []):
            if hasattr(card, "set_theme"):
                card.set_theme(is_dark, accent_color)
        # Parent rollup toggles
        if hasattr(self, "_tgl_rollup_progress"):
            self._tgl_rollup_progress.set_theme(is_dark, accent_color)
            self._tgl_rollup_effort.set_theme(is_dark, accent_color)
            self._tgl_rollup_dates.set_theme(is_dark, accent_color)
        # Phase 2B Schedule intelligence toggles
        if hasattr(self, "_tgl_critical"):
            self._tgl_critical.set_theme(is_dark, accent_color)
            self._tgl_total_float.set_theme(is_dark, accent_color)
            self._tgl_free_float.set_theme(is_dark, accent_color)
            self._tgl_es_ef.set_theme(is_dark, accent_color)
            self._tgl_ls_lf.set_theme(is_dark, accent_color)
            self._tgl_diag.set_theme(is_dark, accent_color)
        # Phase 2D Schedule baseline toggles
        if hasattr(self, "_tgl_finish_variance"):
            self._tgl_finish_variance.set_theme(is_dark, accent_color)
            self._tgl_start_variance.set_theme(is_dark, accent_color)
            self._tgl_baseline_dates.set_theme(is_dark, accent_color)
            self._tgl_duration_variance.set_theme(is_dark, accent_color)
            self._tgl_gantt_baseline.set_theme(is_dark, accent_color)
        # Phase 2E Schedule constraint toggles
        if hasattr(self, "_tgl_constraint_type"):
            self._tgl_constraint_type.set_theme(is_dark, accent_color)
            self._tgl_constraint_date.set_theme(is_dark, accent_color)
            self._tgl_deadline.set_theme(is_dark, accent_color)
            self._tgl_deadline_variance.set_theme(is_dark, accent_color)
            self._tgl_constraint_status.set_theme(is_dark, accent_color)
        self._reset_btn.set_theme(is_dark, accent_color)
        self.update()

    def _on_density_changed(self, index: int, label: str, data: any):
        self._service.set_preference("wbs_density", str(data))
        self._preview_canvas.update()
        self.preferencesChanged.emit()

    def _on_anim_changed(self, index: int, label: str, data: any):
        self._service.set_preference("ui_animation_mode", str(data))
        self.preferencesChanged.emit()

    def _update_pref(self, key: str, val: Any):
        self._service.set_preference(key, val)
        self._preview_canvas.update()
        self.preferencesChanged.emit()

    def _on_reset_clicked(self):
        self._service.reset_to_defaults()
        # Reload controls — reflect DEFAULT_SETTINGS defaults
        self._style_control.set_selected_index(0, notify=False)
        self._emphasis_control.set_selected_index(0, notify=False)
        self._contrast_control.set_selected_index(0, notify=False)
        self._density_control.set_selected_index(1, notify=False)
        self._anim_control.set_selected_index(0, notify=False)
        self._tgl_code.setChecked(True)
        self._tgl_progress.setChecked(True)
        self._tgl_status.setChecked(True)
        self._tgl_icons.setChecked(True)
        self._tgl_guides.setChecked(True)
        if hasattr(self, "_tgl_rollup_progress"):
            self._tgl_rollup_progress.setChecked(
                bool(self._service.get_preference("wbs_show_parent_rollup_progress", True))
            )
            self._tgl_rollup_effort.setChecked(
                bool(self._service.get_preference("wbs_show_parent_effort_summary", False))
            )
            self._tgl_rollup_dates.setChecked(
                bool(self._service.get_preference("wbs_show_parent_dates", False))
            )
        if hasattr(self, "_tgl_critical"):
            self._tgl_critical.setChecked(bool(self._service.get_preference("wbs_show_critical", True)))
            self._tgl_total_float.setChecked(bool(self._service.get_preference("wbs_show_total_float", True)))
            self._tgl_free_float.setChecked(bool(self._service.get_preference("wbs_show_free_float", False)))
            self._tgl_es_ef.setChecked(
                bool(self._service.get_preference("wbs_show_es", False) and self._service.get_preference("wbs_show_ef", False))
            )
            self._tgl_ls_lf.setChecked(
                bool(self._service.get_preference("wbs_show_ls", False) and self._service.get_preference("wbs_show_lf", False))
            )
            self._tgl_diag.setChecked(bool(self._service.get_preference("wbs_show_diagnostics", False)))
        if hasattr(self, "_tgl_finish_variance"):
            self._tgl_finish_variance.setChecked(bool(self._service.get_preference("wbs_show_finish_variance", True)))
            self._tgl_start_variance.setChecked(bool(self._service.get_preference("wbs_show_start_variance", False)))
            self._tgl_baseline_dates.setChecked(
                bool(self._service.get_preference("wbs_show_baseline_start", False) and self._service.get_preference("wbs_show_baseline_finish", False))
            )
            self._tgl_duration_variance.setChecked(bool(self._service.get_preference("wbs_show_duration_variance", False)))
            self._tgl_gantt_baseline.setChecked(bool(self._service.get_preference("gantt_show_baseline", True)))
        self._preview_canvas.update()
        self.preferencesChanged.emit()
