"""
TODO BIRD — WBS TREE ITEM DELEGATE (QStyledItemDelegate)
Premium, high-DPI vector rendering delegate for Todo Bird WBS hierarchy.
Renders custom selection surfaces, modern chevrons, hierarchy indentation,
guide lines, WBS codes, semantic status badges, progress bars, and milestone diamonds.
"""

from datetime import datetime
from typing import Optional, Any
from PySide6.QtCore import Qt, QRectF, QSize, QModelIndex, QEvent
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QStyle, QToolTip
from PySide6.QtGui import (
    QPainter,
    QPainterPath,
    QColor,
    QPen,
    QBrush,
    QFont,
    QFontMetricsF,
    QHelpEvent,
)

from todo_bird_app.ui.design_tokens import DesignTokens
from todo_bird_app.services.icon_service import IconService
from todo_bird_app.services.wbs_customization_service import WBSCustomizationService
from todo_bird_app.services.typography_service import TypographyService
from todo_bird_app.models.wbs_item_model import WBSItemModel
from todo_bird_app.ui.components.status_badge import StatusBadge, BadgeStatus


class WBSTreeItemDelegate(QStyledItemDelegate):
    """
    High-polish custom item delegate for WBS Tree View.
    Zero default Qt look.
    """

    def __init__(
        self,
        custom_service: Optional[WBSCustomizationService] = None,
        parent=None,
        is_dark: bool = True,
        accent_color: str = DesignTokens.COLOR_ACCENT,
        settings_manager=None,
    ):
        super().__init__(parent)
        self._custom_service = custom_service
        self._is_dark = is_dark
        self._accent_color = accent_color
        self._settings_manager = settings_manager

    def set_theme(self, is_dark: bool, accent_color: Optional[str] = None):
        self._is_dark = is_dark
        if accent_color:
            self._accent_color = accent_color

    def set_customization_service(self, service: WBSCustomizationService):
        self._custom_service = service

    def set_settings_manager(self, settings_manager):
        """Update typography authority without recreating the delegate."""
        self._settings_manager = settings_manager

    def _resolved_font(self, option=None) -> QFont:
        """
        WBS typography authority.

        WBS belongs to the task-list typography area. Density is not
        allowed to replace font family/size; it only influences spacing.
        """
        if self._settings_manager is not None:
            font = TypographyService.get_font_for_area(
                "tasklist",
                self._settings_manager,
            )
        elif option is not None:
            font = QFont(option.font)
        else:
            parent = self.parent()
            font = (
                QFont(parent.font())
                if parent is not None
                else QFont()
            )

        return QFont(font)

    def _effective_row_height(self, option=None) -> int:
        """
        Font-safe WBS row height.

        density row height = preferred compactness
        measured text height + padding = hard minimum
        """
        if self._custom_service:
            metrics = self._custom_service.get_density_metrics()
            density_height = int(metrics.row_height)
        else:
            density_height = 36

        font = self._resolved_font(option)
        fm = QFontMetricsF(font)

        # Enough room for ascenders, descenders and selection/focus surfaces.
        text_minimum = int(
            fm.height() + 12
        )

        return max(
            density_height,
            text_minimum,
        )

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        row_h = self._effective_row_height(option)

        return QSize(
            option.rect.width() if option else 120,
            row_h,
        )

    # -------------------------------------------------------------------------
    # Custom Paint Engine
    # -------------------------------------------------------------------------

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        rect = QRectF(option.rect)
        col = index.column()
        is_selected = bool(option.state & QStyle.State_Selected)
        is_hovered = bool(option.state & QStyle.State_MouseOver)
        has_focus = bool(option.state & QStyle.State_HasFocus)

        # Retrieve Data Roles
        wbs_code = str(index.data(WBSItemModel.WBSCodeRole) or "")
        title = str(index.data(WBSItemModel.TitleRole) or "")
        status = str(index.data(WBSItemModel.StatusRole) or "planned").lower()
        progress = int(index.data(WBSItemModel.ProgressRole) or 0)
        depth = int(index.data(WBSItemModel.DepthRole) or 0)
        has_children = bool(index.data(WBSItemModel.HasChildrenRole))
        is_milestone = bool(index.data(WBSItemModel.IsMilestoneRole))
        is_expanded = bool(option.state & QStyle.State_Open)

        # Customization Preferences
        metrics = self._custom_service.get_density_metrics() if self._custom_service else None
        indent_px = metrics.indent_px if metrics else 20
        show_code = self._custom_service.get_preference("wbs_show_code", True) if self._custom_service else True
        show_status = self._custom_service.get_preference("wbs_show_status", True) if self._custom_service else True
        show_progress = self._custom_service.get_preference("wbs_show_progress", True) if self._custom_service else True
        show_icons = self._custom_service.get_preference("wbs_show_icons", True) if self._custom_service else True
        show_guides = self._custom_service.get_preference("wbs_show_guide_lines", True) if self._custom_service else True
        # Phase 1C rollup toggles (parent-derived)
        show_parent_rollup = self._custom_service.get_preference("wbs_show_parent_rollup_progress", True) if self._custom_service else True
        show_parent_effort = self._custom_service.get_preference("wbs_show_parent_effort_summary", False) if self._custom_service else False
        show_parent_dates = self._custom_service.get_preference("wbs_show_parent_dates", False) if self._custom_service else False
        # Suppress progress for parent rows when toggle off
        if has_children and not show_parent_rollup:
            show_progress = False

        accent = QColor(self._accent_color)
        if self._custom_service:
            surfaces = self._custom_service.get_surface_colors(self._is_dark, self._accent_color)
            text_primary = QColor(surfaces.get("text_primary", "#F8FAFC" if self._is_dark else "#0F172A"))
            text_secondary = QColor(surfaces.get("text_secondary", "#A6ADC8" if self._is_dark else "#475569"))
        else:
            text_primary = QColor("#F8FAFC") if self._is_dark else QColor("#0F172A")
            text_secondary = QColor("#A6ADC8") if self._is_dark else QColor("#475569")

        # 1. Selection & Hover Background Surface
        self._paint_background(painter, rect, is_selected, is_hovered, has_focus, has_children, col)

        # 2. Font configuration
        # Typography owns family/size. Hierarchy owns only emphasis.
        font = self._resolved_font(option)

        if has_children:
            font.setWeight(QFont.DemiBold)
        else:
            font.setWeight(QFont.Normal)

        painter.setFont(font)

        # Preference gates for parent rollups (Phase 1C) — no DB, derived cache only
        show_rollup_progress = self._custom_service.get_preference("wbs_show_parent_rollup_progress", True) if self._custom_service else True

        # Resolve rollup progress/effort/dates without DB hit
        rollup_progress_val = None
        rollup_leaf_count = None
        rollup_blocked = None
        rollup_delayed = None
        if has_children and show_rollup_progress:
            try:
                rp = index.data(WBSItemModel.RollupProgressRole)
                if rp is not None:
                    rollup_progress_val = int(rp)
                # Leaf counts for tooltip-style bar context (not painted in tooltip here)
                lc = index.data(WBSItemModel.RollupLeafCountRole)
                if lc is not None:
                    rollup_leaf_count = int(lc)
                bc = index.data(WBSItemModel.RollupDataRole)
                # RollupDataRole gives full object for blocked/delayed if available
                if bc is not None and hasattr(bc, "blocked_count"):
                    rollup_blocked = int(getattr(bc, "blocked_count", 0))
                    rollup_delayed = int(getattr(bc, "delayed_count", 0))
            except Exception:
                pass

        # 3. Column-Specific Rendering
        if col == WBSItemModel.COL_WBS:
            self._paint_wbs_column(
                painter, rect, depth, indent_px, has_children, is_expanded,
                is_milestone, wbs_code, show_code, show_guides, accent, text_secondary
            )
        elif col == WBSItemModel.COL_TITLE:
            self._paint_title_column(
                painter, rect, title, has_children, is_milestone, show_icons,
                text_primary, accent, text_secondary,
                rollup_progress=rollup_progress_val if has_children and show_rollup_progress else None,
            )
        elif col == WBSItemModel.COL_STATUS:
            if show_status:
                self._paint_status_column(painter, rect, status, is_milestone)
        elif col == WBSItemModel.COL_PROGRESS:
            if show_progress:
                # For summary nodes, prefer rollup progress when gate enabled
                paint_progress = progress
                if has_children and show_rollup_progress and rollup_progress_val is not None:
                    paint_progress = rollup_progress_val
                self._paint_progress_column(painter, rect, paint_progress, accent, text_secondary,
                                            is_rollup=bool(has_children and show_rollup_progress and rollup_progress_val is not None))
        elif col == WBSItemModel.COL_CRITICAL:
            self._paint_critical_column(painter, rect, index, text_primary, text_secondary)
        elif col in (WBSItemModel.COL_TOTAL_FLOAT, WBSItemModel.COL_FREE_FLOAT):
            self._paint_float_column(painter, rect, index, col, text_primary, text_secondary)
        elif col in (WBSItemModel.COL_ES, WBSItemModel.COL_EF, WBSItemModel.COL_LS, WBSItemModel.COL_LF, WBSItemModel.COL_BASELINE_START, WBSItemModel.COL_BASELINE_FINISH):
            self._paint_date_column(painter, rect, index, col, text_primary, text_secondary)
        elif col in (WBSItemModel.COL_START_VARIANCE, WBSItemModel.COL_FINISH_VARIANCE, WBSItemModel.COL_DURATION_VARIANCE):
            self._paint_variance_column(painter, rect, index, col, text_primary, text_secondary)
        elif col == WBSItemModel.COL_DIAGNOSTICS:
            self._paint_diagnostics_column(painter, rect, index, text_primary, text_secondary)

        painter.restore()

    # -------------------------------------------------------------------------
    # Sub-painters
    # -------------------------------------------------------------------------

    def _paint_background(
        self,
        painter: QPainter,
        rect: QRectF,
        is_selected: bool,
        is_hovered: bool,
        has_focus: bool,
        has_children: bool,
        col: int,
    ):
        """Paints modern layered background surfaces, summary row elevation, and selection indicator."""
        bg_rect = rect.adjusted(0, 0, 0, 0)
        accent = QColor(self._accent_color)

        if self._custom_service:
            surfaces = self._custom_service.get_surface_colors(self._is_dark, self._accent_color)
        else:
            surfaces = {
                "summary_alpha": 12 if self._is_dark else 10,
                "hover_alpha": 18 if self._is_dark else 12,
                "selected_alpha": 45 if self._is_dark else 25,
                "guide_alpha": 22 if self._is_dark else 24,
            }

        # 1. Summary / Parent Row Tonal Elevation
        if has_children and not is_selected:
            alpha = surfaces.get("summary_alpha", 12)
            summary_bg = QColor(255, 255, 255, alpha) if self._is_dark else QColor(0, 0, 0, alpha)
            painter.fillRect(bg_rect, summary_bg)

        # 2. Hover Surface
        if is_hovered and not is_selected:
            h_alpha = surfaces.get("hover_alpha", 18)
            hover_bg = QColor(255, 255, 255, h_alpha) if self._is_dark else QColor(0, 0, 0, h_alpha)
            painter.fillRect(bg_rect, hover_bg)

        # 3. Selected Surface
        elif is_selected:
            s_alpha = surfaces.get("selected_alpha", 45)
            sel_bg = QColor(accent.red(), accent.green(), accent.blue(), s_alpha)
            painter.fillRect(bg_rect, sel_bg)

            # Left Edge Accent Indicator Bar on column 0
            if col == WBSItemModel.COL_WBS:
                ind_bar = QRectF(bg_rect.x() + 1.0, bg_rect.y() + 2.0, 3.0, bg_rect.height() - 4.0)
                ind_path = QPainterPath()
                ind_path.addRoundedRect(ind_bar, 1.5, 1.5)
                painter.fillPath(ind_path, QBrush(accent))

        # 4. Focus Ring on active row
        if has_focus and is_selected:
            pen = QPen(accent, 1.2)
            painter.setPen(pen)
            painter.drawLine(bg_rect.topLeft(), bg_rect.topRight())
            painter.drawLine(bg_rect.bottomLeft(), bg_rect.bottomRight())

    def _paint_wbs_column(
        self,
        painter: QPainter,
        rect: QRectF,
        depth: int,
        indent_px: int,
        has_children: bool,
        is_expanded: bool,
        is_milestone: bool,
        wbs_code: str,
        show_code: bool,
        show_guides: bool,
        accent: QColor,
        text_sec: QColor,
    ):
        """Paints indentation, hierarchy guides, modern vector chevron, and WBS code."""
        start_x = rect.x() + 8.0 + depth * indent_px
        cy = rect.y() + rect.height() / 2.0

        if self._custom_service:
            surfaces = self._custom_service.get_surface_colors(self._is_dark, self._accent_color)
            guide_alpha = surfaces.get("guide_alpha", 22)
        else:
            guide_alpha = 22 if self._is_dark else 24

        # Hierarchy Guide Lines
        if show_guides and depth > 0:
            guide_col = QColor(255, 255, 255, guide_alpha) if self._is_dark else QColor(0, 0, 0, guide_alpha)
            painter.setPen(QPen(guide_col, 1.0, Qt.DashLine))
            # Connecting horizontal tick
            painter.drawLine(start_x - indent_px / 2.0, cy, start_x - 4, cy)

        # Expander / Chevron / Leaf Indicator
        if has_children:
            chevron_size = 14.0
            icon_name = "chevron_down" if is_expanded else "chevron_right"
            chevron_box = QRectF(start_x, cy - chevron_size / 2.0, chevron_size, chevron_size)
            IconService.render_vector_icon(painter, icon_name, chevron_box, accent, stroke_width=1.8)
            cur_x = start_x + 20.0
        elif is_milestone:
            diamond_box = QRectF(start_x + 2, cy - 5.0, 10, 10)
            IconService.render_vector_icon(painter, "milestone", diamond_box, QColor("#8B5CF6"), filled=True)
            cur_x = start_x + 20.0
        else:
            cur_x = start_x + 14.0

        # WBS Code
        if show_code and wbs_code:
            painter.setPen(accent if has_children else text_sec)
            code_w = rect.right() - cur_x - 4
            if code_w > 10:
                painter.drawText(QRectF(cur_x, rect.y(), code_w, rect.height()), Qt.AlignVCenter | Qt.AlignLeft, wbs_code)

    def _paint_title_column(
        self,
        painter: QPainter,
        rect: QRectF,
        title: str,
        has_children: bool,
        is_milestone: bool,
        show_icons: bool,
        text_pri: QColor,
        accent: QColor,
        text_sec: QColor,
        rollup_progress: Optional[int] = None,
    ):
        """Paints task name with optional summary folder or task icon.
        For summary nodes, draws a subtle 3px compact rollup bar below the title when
        rollup_progress is not None (gate already applied in paint()). No DB hit.
        """
        cur_x = rect.x() + 8.0
        cy = rect.y() + rect.height() / 2.0
        # Reserve bottom 4px for rollup bar if present so text stays vertically centered with offset
        has_rollup_bar = has_children and rollup_progress is not None
        text_rect_y = rect.y()
        text_rect_h = rect.height() - (4.0 if has_rollup_bar else 0.0)

        if show_icons:
            icon_size = 14.0
            # Shift icon slightly up when bar present to keep visual balance
            icon_cy = cy - (2.0 if has_rollup_bar else 0.0)
            icon_box = QRectF(cur_x, icon_cy - icon_size / 2.0, icon_size, icon_size)
            if is_milestone:
                IconService.render_vector_icon(painter, "milestone", icon_box, QColor("#8B5CF6"), stroke_width=1.6)
            elif has_children:
                IconService.render_vector_icon(painter, "folder", icon_box, accent, stroke_width=1.5)
            else:
                IconService.render_vector_icon(painter, "task", icon_box, text_sec, stroke_width=1.5)
            cur_x += 20.0

        painter.setPen(text_pri)
        text_w = rect.right() - cur_x - 8
        if text_w > 10:
            elided = painter.fontMetrics().elidedText(title, Qt.ElideRight, int(text_w))
            painter.drawText(QRectF(cur_x, text_rect_y, text_w, text_rect_h), Qt.AlignVCenter | Qt.AlignLeft, elided)

        # Subtle compact rollup bar below title (high-DPI, 3px)
        if has_rollup_bar:
            try:
                pct = max(0.0, min(1.0, float(rollup_progress) / 100.0))
                bar_x = cur_x
                # Width spans text area but capped to keep subtle
                bar_w_full = max(0.0, rect.right() - bar_x - 8.0)
                # Compact: use full available but track is subtle
                bar_h = 3.0
                bar_y = rect.bottom() - bar_h - 2.0
                painter.save()
                painter.setRenderHint(QPainter.Antialiasing, True)
                track_bg = QColor("#313244") if self._is_dark else QColor("#E2E8F0")
                fill_col = QColor(DesignTokens.COLOR_SUCCESS) if int(rollup_progress) >= 100 else accent
                # Track
                track_rect = QRectF(bar_x, bar_y, bar_w_full, bar_h)
                track_path = QPainterPath()
                track_path.addRoundedRect(track_rect, 1.5, 1.5)
                painter.fillPath(track_path, QBrush(track_bg))
                # Fill
                if pct > 0:
                    fill_rect = QRectF(bar_x, bar_y, bar_w_full * pct, bar_h)
                    fill_path = QPainterPath()
                    fill_path.addRoundedRect(fill_rect, 1.5, 1.5)
                    painter.fillPath(fill_path, QBrush(fill_col))
                painter.restore()
            except Exception:
                pass

    def _paint_status_column(
        self,
        painter: QPainter,
        rect: QRectF,
        status_str: str,
        is_milestone: bool,
    ):
        """Paints calibrated semantic status pill."""
        st_enum = BadgeStatus.MILESTONE if is_milestone else BadgeStatus.PLANNED
        for s in BadgeStatus:
            if s.value == status_str:
                st_enum = s
                break

        cfg = StatusBadge.STATUS_CONFIG.get(st_enum, StatusBadge.STATUS_CONFIG[BadgeStatus.PLANNED])
        label = cfg["label"]

        label_font = QFont(painter.font())
        base_pt = int(label_font.pointSize())

        if base_pt > 0:
            label_font.setPointSize(
                max(6, base_pt - 1)
            )

        fm = QFontMetricsF(label_font)

        pill_h = max(
            20.0,
            float(fm.height()) + 6.0,
        )

        pill_y = (
            rect.y()
            + (rect.height() - pill_h) / 2.0
        )

        pill_w = (
            fm.horizontalAdvance(label)
            + 20.0
        )
        pill_rect = QRectF(rect.x() + 8, pill_y, min(pill_w, rect.width() - 16), pill_h)

        bg_col = QColor(cfg["dark_bg"] if self._is_dark else cfg["light_bg"])
        border_col = QColor(cfg["dark_border"] if self._is_dark else cfg["light_border"])
        text_col = QColor(cfg["dark_fg"] if self._is_dark else cfg["light_fg"])
        dot_col = QColor(cfg["dot"])

        path = QPainterPath()
        path.addRoundedRect(pill_rect, 4.0, 4.0)
        painter.fillPath(path, QBrush(bg_col))
        painter.strokePath(path, QPen(border_col, 1.0))

        # Dot
        dot_cy = pill_rect.y() + pill_rect.height() / 2.0
        painter.setBrush(QBrush(dot_col))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QRectF(pill_rect.x() + 6, dot_cy - 2.5, 5, 5))

        # Label Text — one semantic step below row title.
        # Never replace the user's configured typography with 10pt.
        painter.setFont(label_font)
        painter.setPen(text_col)
        painter.drawText(QRectF(pill_rect.x() + 15, pill_rect.y(), pill_rect.width() - 17, pill_rect.height()), Qt.AlignVCenter | Qt.AlignLeft, label)

    def _paint_progress_column(
        self,
        painter: QPainter,
        rect: QRectF,
        progress: int,
        accent: QColor,
        text_sec: QColor,
        is_rollup: bool = False,
    ):
        """Paints mini progress bar with text percentage.
        When is_rollup True, uses subtly muted track opacity for parent distinction
        while keeping percentage text in secondary color for readability (dark/light).
        No DB query.
        """
        bar_w = 60.0
        bar_h = 6.0
        bar_x = rect.x() + 8.0
        bar_y = rect.y() + (rect.height() - bar_h) / 2.0

        track_bg = QColor("#313244") if self._is_dark else QColor("#E2E8F0")
        fill_col = QColor(DesignTokens.COLOR_SUCCESS) if progress >= 100 else accent
        pct = max(0.0, min(1.0, progress / 100.0))

        # For rollup, keep same track but fill is subtly standard (no extra work); distinction via text tone handled below
        # Track
        track_path = QPainterPath()
        track_path.addRoundedRect(QRectF(bar_x, bar_y, bar_w, bar_h), 3, 3)
        painter.fillPath(track_path, QBrush(track_bg))

        # Fill
        if pct > 0:
            fill_path = QPainterPath()
            fill_path.addRoundedRect(QRectF(bar_x, bar_y, bar_w * pct, bar_h), 3, 3)
            painter.fillPath(fill_path, QBrush(fill_col))

        # Text % — secondary semantic typography.
        # Use the configured row font one step smaller rather than
        # forcing an unrelated absolute 10pt size.
        f = QFont(painter.font())
        base_pt = int(f.pointSize())

        if base_pt > 0:
            f.setPointSize(
                max(6, base_pt - 1)
            )

        painter.setFont(f)
        painter.setPen(text_sec)
        text_rect = QRectF(bar_x + bar_w + 8, rect.y(), rect.width() - (bar_w + 16), rect.height())
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, f"{progress}%")

    # -------------------------------------------------------------------------
    # Tooltip — derived rollup, no DB, calendar elapsed never working_calendar
    # -------------------------------------------------------------------------
    @staticmethod
    def _format_rollup_date(dt: Optional[datetime]) -> str:
        if dt is None:
            return ""
        try:
            # Example: 18 Aug — strip leading zero from day
            s = dt.strftime("%d %b")
            if s.startswith("0"):
                s = s[1:]
            # Include year only if not current year? Keep compact: add year if >0 but omit for tooltip brevity; keep as day month
            return s
        except Exception:
            return str(dt)

    @staticmethod
    def _format_effort(minutes: Optional[int]) -> str:
        if minutes is None:
            return "0h"
        try:
            m = int(minutes)
        except Exception:
            return "0h"
        if m % 60 == 0:
            return f"{m // 60}h"
        # One decimal for fractional hours
        h = m / 60.0
        # Keep .1 precision, strip trailing zeros
        s = f"{h:.1f}h"
        if s.endswith(".0h"):
            s = s[:-3] + "h"
        return s

    def _build_rollup_tooltip(self, index: QModelIndex) -> Optional[str]:
        """Constructs tooltip string from cached rollup roles. No DB."""
        if not index.isValid():
            return None
        try:
            # Prefer full RollupDataRole object when available
            data = index.data(WBSItemModel.RollupDataRole)
            if data is not None and hasattr(data, "leaf_count"):
                r = data
                ps = getattr(r, "planned_start", None)
                pf = getattr(r, "planned_finish", None)
                planned = "No schedule"
                if ps is not None and pf is not None:
                    planned = f"{self._format_rollup_date(ps)} → {self._format_rollup_date(pf)}"
                elif ps is not None:
                    planned = f"{self._format_rollup_date(ps)} → —"
                elif pf is not None:
                    planned = f"— → {self._format_rollup_date(pf)}"
                pe = getattr(r, "planned_effort_minutes", 0)
                ae = getattr(r, "actual_effort_minutes", 0)
                prog = getattr(r, "progress_percent", 0)
                lc = getattr(r, "leaf_count", 0)
                bc = getattr(r, "blocked_count", 0)
                dc = getattr(r, "delayed_count", 0)
                # Format: Planned: 18 Aug → 2 Sep / Planned effort: 74h / Actual effort: 39h / Progress: 53% / Children: 8 (Blocked:1 Delayed:0)
                effort_plan = self._format_effort(pe)
                effort_actual = self._format_effort(ae)
                blocked_delayed = f" (Blocked:{bc} Delayed:{dc})" if (bc or dc) else ""
                return f"Planned: {planned} / Planned effort: {effort_plan} / Actual effort: {effort_actual} / Progress: {int(prog)}% / Children: {int(lc)}{blocked_delayed}"
            # Fallback via individual roles
            has_children = bool(index.data(WBSItemModel.HasChildrenRole))
            if not has_children:
                return None
            ps = index.data(WBSItemModel.RollupPlannedStartRole)
            pf = index.data(WBSItemModel.RollupPlannedFinishRole)
            if ps is None and pf is None:
                planned = "No schedule"
            else:
                planned = f"{self._format_rollup_date(ps) if ps else '—'} → {self._format_rollup_date(pf) if pf else '—'}"
                if planned.strip() == "→":
                    planned = "No schedule"
                else:
                    # Handle empty parts
                    if not ps and not pf:
                        planned = "No schedule"
            pe = index.data(WBSItemModel.RollupPlannedEffortRole) or 0
            ae = index.data(WBSItemModel.RollupActualEffortRole) or 0
            prog = index.data(WBSItemModel.RollupProgressRole) or 0
            lc = index.data(WBSItemModel.RollupLeafCountRole) or 0
            # Counts via data role fallback zero
            return f"Planned: {planned} / Planned effort: {self._format_effort(int(pe))} / Actual effort: {self._format_effort(int(ae))} / Progress: {int(prog)}% / Children: {int(lc)}"
        except Exception:
            return None

    def _paint_critical_column(
        self,
        painter: QPainter,
        rect: QRectF,
        index: QModelIndex,
        text_primary: QColor,
        text_secondary: QColor,
    ):
        has_children = bool(index.data(WBSItemModel.HasChildrenRole))
        if has_children:
            label = str(index.data(Qt.DisplayRole) or "N/A (Summary)")
            painter.setPen(QPen(text_secondary))
            painter.drawText(rect.adjusted(8, 0, -8, 0), int(Qt.AlignVCenter | Qt.AlignLeft), label)
            return

        is_critical = bool(index.data(WBSItemModel.CPMCriticalRole))
        schedulable = bool(index.data(WBSItemModel.CPMSchedulableRole))
        diag_codes = index.data(WBSItemModel.CPMDiagnosticsRole) or []
        is_cycle = "DEPENDENCY_CYCLE" in diag_codes

        if is_cycle:
            badge_bg = QColor(239, 68, 68, 35) if self._is_dark else QColor(254, 226, 226)
            badge_border = QColor("#EF4444")
            text_col = QColor("#F87171") if self._is_dark else QColor("#DC2626")
            label = "⟳ Blocked"
        elif not schedulable:
            badge_bg = QColor(245, 158, 11, 30) if self._is_dark else QColor(254, 243, 199)
            badge_border = QColor("#F59E0B")
            text_col = QColor("#FBBF24") if self._is_dark else QColor("#D97706")
            label = "Not analyzed"
        elif is_critical:
            badge_bg = QColor(239, 68, 68, 45) if self._is_dark else QColor(254, 226, 226)
            badge_border = QColor("#EF4444")
            text_col = QColor("#FCA5A5") if self._is_dark else QColor("#B91C1C")
            label = "● Critical"
        else:
            badge_bg = QColor(255, 255, 255, 10) if self._is_dark else QColor(241, 245, 249)
            badge_border = QColor("#475569") if self._is_dark else QColor("#CBD5E1")
            text_col = text_secondary
            label = "Non-critical"

        fm = painter.fontMetrics()
        text_w = fm.horizontalAdvance(label)
        pill_w = max(70.0, float(text_w + 14))
        pill_h = min(22.0, float(rect.height() - 6))
        pill_x = rect.x() + 4.0
        pill_y = rect.y() + (rect.height() - pill_h) / 2.0
        pill_rect = QRectF(pill_x, pill_y, pill_w, pill_h)

        path = QPainterPath()
        path.addRoundedRect(pill_rect, 4.0, 4.0)
        painter.fillPath(path, QBrush(badge_bg))
        painter.strokePath(path, QPen(badge_border, 1.0))

        painter.setPen(QPen(text_col))
        painter.drawText(pill_rect, int(Qt.AlignCenter), label)

    def _paint_float_column(
        self,
        painter: QPainter,
        rect: QRectF,
        index: QModelIndex,
        col: int,
        text_primary: QColor,
        text_secondary: QColor,
    ):
        text = str(index.data(Qt.DisplayRole) or "—")
        is_critical = bool(index.data(WBSItemModel.CPMCriticalRole))
        schedulable = bool(index.data(WBSItemModel.CPMSchedulableRole))

        if text == "0m" and is_critical and schedulable:
            painter.setPen(QPen(QColor("#EF4444") if self._is_dark else QColor("#DC2626")))
            f = painter.font()
            f.setBold(True)
            painter.setFont(f)
        elif text == "—":
            painter.setPen(QPen(text_secondary))
        else:
            painter.setPen(QPen(text_primary))

        painter.drawText(rect.adjusted(4, 0, -8, 0), int(Qt.AlignVCenter | Qt.AlignRight), text)

    def _paint_date_column(
        self,
        painter: QPainter,
        rect: QRectF,
        index: QModelIndex,
        col: int,
        text_primary: QColor,
        text_secondary: QColor,
    ):
        text = str(index.data(Qt.DisplayRole) or "—")
        painter.setPen(QPen(text_secondary if text in ("—", "Not Baselined") else text_primary))
        align = int(Qt.AlignVCenter | (Qt.AlignLeft if text == "Not Baselined" else Qt.AlignRight))
        painter.drawText(rect.adjusted(4, 0, -8, 0), align, text)

    def _paint_variance_column(
        self,
        painter: QPainter,
        rect: QRectF,
        index: QModelIndex,
        col: int,
        text_primary: QColor,
        text_secondary: QColor,
    ):
        text = str(index.data(Qt.DisplayRole) or "—")
        if text.startswith("+"):
            # Behind / Later / Longer -> Warning or Danger
            if col == WBSItemModel.COL_FINISH_VARIANCE:
                painter.setPen(QPen(QColor("#EF4444") if self._is_dark else QColor("#DC2626")))
            else:
                painter.setPen(QPen(QColor("#F59E0B") if self._is_dark else QColor("#D97706")))
        elif text.startswith("-"):
            # Ahead / Earlier / Shorter -> Success Green
            painter.setPen(QPen(QColor("#10B981") if self._is_dark else QColor("#059669")))
        elif text == "0":
            painter.setPen(QPen(text_secondary))
        else:
            painter.setPen(QPen(text_secondary))

        painter.drawText(rect.adjusted(4, 0, -8, 0), int(Qt.AlignVCenter | Qt.AlignRight), text)

    def _paint_diagnostics_column(
        self,
        painter: QPainter,
        rect: QRectF,
        index: QModelIndex,
        text_primary: QColor,
        text_secondary: QColor,
    ):
        text = str(index.data(Qt.DisplayRole) or "—")
        if text == "Healthy":
            painter.setPen(QPen(QColor("#10B981")))
        elif "Cycle" in text:
            painter.setPen(QPen(QColor("#EF4444")))
        elif text in ("Unscheduled", "Invalid Duration", "Missing Ref"):
            painter.setPen(QPen(QColor("#F59E0B")))
        else:
            painter.setPen(QPen(text_secondary))

        painter.drawText(rect.adjusted(8, 0, -8, 0), int(Qt.AlignVCenter | Qt.AlignLeft), text)

    def helpEvent(self, event: QHelpEvent, view, option: QStyleOptionViewItem, index: QModelIndex) -> bool:  # type: ignore[override]
        """Shows rich rollup or schedule intelligence tooltip. No DB hit."""
        if event is None or not index.isValid():
            return super().helpEvent(event, view, option, index)  # type: ignore

        try:
            has_children = bool(index.data(WBSItemModel.HasChildrenRole))
        except Exception:
            has_children = False

        if has_children:
            tip = self._build_rollup_tooltip(index)
        else:
            tip = index.data(Qt.ToolTipRole)

        if tip:
            try:
                global_pos = event.globalPos()  # type: ignore[attr-defined]
            except Exception:
                try:
                    global_pos = event.globalPosition().toPoint()  # type: ignore
                except Exception:
                    global_pos = event.pos()
            QToolTip.showText(global_pos, tip, view)
            return True

        return super().helpEvent(event, view, option, index)  # type: ignore
