import logging
from datetime import date, datetime, timedelta
from typing import List, Dict, Optional

from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsItem, QMenu
from PySide6.QtCore import Qt, Signal, QRectF, QTimer
from PySide6.QtGui import QPainter, QBrush, QColor, QPen, QFont, QAction

from todo_bird_app.gantt.gantt_theme import GanttColorProfile, DEFAULT_GANTT_COLORS
from todo_bird_app.gantt.gantt_items import GanttTaskItem
from todo_bird_app.gantt.timescale_engine import TimescaleEngine, ZoomLevel, TimelineColumn
from todo_bird_app.controllers.delay_engine import DelayEngine, TimingStatus
from todo_bird_app.models.task import Task, TaskStatus
from todo_bird_app.gantt.gantt_dependency_engine import GanttDependencyEngine
from PySide6.QtGui import QPainterPath, QPolygonF, QColor, QPen, QBrush
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QGraphicsPathItem, QGraphicsPolygonItem, QGraphicsRectItem

logger = logging.getLogger(__name__)

class GanttChartWidget(QGraphicsView):
    """
    High-performance, interactive PySide6 QGraphicsView Gantt timeline canvas.
    Supports Multi-Year TimescaleEngine, ISO week headers, range-aware filtering,
    and responsive navigation.
    """
    task_action_requested = Signal(str, int)  # (action_type, task_id)

    # Interactive schedule edit payload.
    # Contains main-task or nested-subtask identity plus updated
    # planned dates/times/duration.
    schedule_change_requested = Signal(object)
    
    # Emitted when the chart rebuilds, passing the flat list of rendered tasks in order.
    visible_tasks_changed = Signal(list)

    def __init__(self, settings_manager=None, parent=None):
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)

        self.zoom_mode = ZoomLevel.DAILY
        self.anchor_date = date.today()
        self.header_height = 60.0
        self.row_height = 42.0

        self.color_profile = GanttColorProfile()
        self.delay_engine = DelayEngine(settings_manager) if settings_manager else None

        self.tasks: List[Task] = []
        self.projects_map: Dict[int, str] = {}
        self.show_actual_bars = True
        self.show_baseline = True
        self.show_completed = True
        self.filter_project_id = None
        self.filter_priority = None

        self.columns: List[TimelineColumn] = []
        self.current_time_line_item = None

        # -------------------------------------------------
        # Interactive Gantt state
        # -------------------------------------------------
        self._drag_item = None
        self._drag_start_scene_x = 0.0
        self._drag_start_item_x = 0.0
        self._drag_start_item_y = 0.0
        self._drag_moved = False
        self._drag_threshold_px = 9.0

        # -------------------------------------------------
        # Edge-resize interaction state
        # -------------------------------------------------
        self._resize_mode = None
        self._resize_item = None
        self._resize_start_scene_x = 0.0
        self._resize_start_item_x = 0.0
        self._resize_start_item_y = 0.0
        self._resize_preview = None
        self._resize_moved = False
        self._resize_edge_px = 14.0

        # Render-time item registry used by dependency routing.
        self._rendered_task_items = {}
        self._dependency_graphics = []
        self._current_empty_message = None

        # Commercial scheduling behaviour:
        # Hourly editing snaps to quarter-hours.
        self.hourly_snap_minutes = 15

        self.bar_style = (
            str(
                self.settings_manager.get(
                    "gantt_bar_style",
                    "rounded",
                )
            )
            if self.settings_manager
            else "rounded"
        )

        self.planned_bar_color = (
            str(
                self.settings_manager.get(
                    "gantt_planned_bar_color",
                    "#3584E4",
                )
            )
            if self.settings_manager
            else "#3584E4"
        )

        self._setup_view_properties()

        # Required for reliable resize-edge cursor feedback.
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)

        self.timer = QTimer(self)
        self.timer.setInterval(60000)
        self.timer.timeout.connect(self._on_minute_tick)
        self.timer.start()

    def cleanup(self):
        """Stops all active chart timers on shutdown."""
        if hasattr(self, "timer") and self.timer is not None:
            try:
                self.timer.stop()
            except Exception:
                pass

    def _setup_view_properties(self):
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setRenderHint(QPainter.TextAntialiasing, True)
        self.setViewportUpdateMode(QGraphicsView.BoundingRectViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scene.drawBackground = self._draw_scene_background

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Adapt scene dimensions dynamically to screen resolution and window resize
        if hasattr(self, "scene") and self.scene:
            try:
                new_size = event.size()
                w = float(new_size.width())
                h = float(new_size.height())
                curr_rect = self.scene.sceneRect()
                if curr_rect.isValid() and (curr_rect.width() > 0 or curr_rect.height() > 0):
                    new_w = max(curr_rect.width(), w)
                    new_h = max(curr_rect.height(), h)
                    if new_w != curr_rect.width() or new_h != curr_rect.height():
                        self.scene.setSceneRect(0, 0, new_w, new_h)
                elif w > 0 and h > 0:
                    self.scene.setSceneRect(0, 0, w, h)
            except Exception:
                pass

    def drawBackground(self, painter: QPainter, rect: QRectF):
        """
        Rock-solid, tear-free background & grid rendering directly via QPainter.
        Background and grid lines never disappear on mouse hover or partial redraws.
        """
        self._draw_scene_background(painter, rect)

    def _draw_scene_background(self, painter: QPainter, rect: QRectF):
        app_theme = self.settings_manager.get("theme", "dark") if self.settings_manager else "dark"
        colors = self.color_profile.get_effective_colors(app_theme)
        scene_rect = self.scene.sceneRect()
        if scene_rect.isNull():
            return

        painter.save()
        # 1. Canvas Background Fill
        bg_col = QColor(colors.get("background", "#1E1E2E" if app_theme == "dark" else "#FFFFFF"))
        painter.fillRect(rect, bg_col)

        # 2. Header Area Fill
        header_h = float(self.header_height)
        header_rect = QRectF(scene_rect.left(), 0, scene_rect.width(), header_h)
        if rect.intersects(header_rect):
            header_col = QColor(colors.get("header_color", "#181825" if app_theme == "dark" else "#F3F4F6"))
            painter.fillRect(header_rect.intersected(rect), header_col)

        # 3. Columns, Weekend Shading & Vertical Grid Lines
        if self.columns:
            from todo_bird_app.services.working_week import WorkingWeekService
            ww_service = WorkingWeekService(self.settings_manager) if self.settings_manager else None
            enable_shading = self.settings_manager.get("enable_weekend_shading", True) if self.settings_manager else True
            weekend_opacity = self.settings_manager.get("weekend_opacity", 30) if self.settings_manager else 30

            grid_minor_col = QColor(colors.get("gantt_grid_minor", "#374151" if app_theme == "dark" else "#E5E7EB"))
            if app_theme == "dark":
                # Ensure crisp, visible grid lines on dark background
                grid_minor_col = QColor("#4B5563")
            grid_minor_pen = QPen(grid_minor_col, 1.0)
            grid_minor_pen.setCosmetic(True)
            
            grid_major_col = QColor(colors.get("gantt_grid_major", "#6B7280" if app_theme == "dark" else "#D1D5DB"))
            grid_major_pen = QPen(grid_major_col, 1.5)
            grid_major_pen.setCosmetic(True)

            # Fonts and colors for deterministic header text rendering
            from todo_bird_app.services.typography_service import TypographyService
            base_g_font = TypographyService.get_font_for_area("gantt", self.settings_manager)
            font_primary = QFont(base_g_font)
            font_primary.setPointSize(max(7, base_g_font.pointSize() - 2))
            font_primary.setBold(True)

            font_secondary = QFont(base_g_font)
            font_secondary.setBold(True)

            font_sub = QFont(base_g_font)
            font_sub.setPointSize(max(6, base_g_font.pointSize() - 3))

            text_sec_col = QColor(colors.get("gantt_header_muted", "#9CA3AF" if app_theme == "dark" else "#6B7280"))
            text_pri_col = QColor(colors.get("gantt_header_text", "#F9FAFB" if app_theme == "dark" else "#111827"))
            today_marker_col = QColor(colors.get("gantt_today_accent", "#EF4444" if app_theme == "dark" else "#DC2626"))

            for col in self.columns:
                col_x = float(col.x_offset)
                col_w = float(col.width)
                col_rect = QRectF(col_x, header_h, col_w, scene_rect.height() - header_h)
                header_col_rect = QRectF(col_x, 0, col_w, header_h)

                # 1. Weekend shading in Daily mode
                if self.zoom_mode == ZoomLevel.DAILY and ww_service and enable_shading:
                    if ww_service.is_weekend(col.start_date) and rect.intersects(col_rect):
                        w_col = QColor(colors.get("weekend_background", "#2A2F3A" if app_theme == "dark" else "#F3F4F6"))
                        w_col.setAlphaF(max(0.0, min(1.0, weekend_opacity / 100.0)))
                        painter.fillRect(col_rect.intersected(rect), w_col)

                # 2. Vertical grid line
                if rect.left() - 1.0 <= col_x <= rect.right() + 1.0:
                    painter.setPen(grid_major_pen if col.primary_header else grid_minor_pen)
                    painter.drawLine(QPointF(col_x, header_h), QPointF(col_x, scene_rect.bottom()))

                # 3. Header Text Labels (Painted deterministically into header rect)
                if rect.intersects(header_col_rect):
                    if col.primary_header:
                        painter.setFont(font_primary)
                        painter.setPen(text_sec_col)
                        painter.drawText(QRectF(col_x + 4, 2, col_w - 4, 16), Qt.AlignLeft | Qt.AlignVCenter, col.primary_header)

                    sec_color = today_marker_col if col.is_today_period else text_pri_col
                    painter.setFont(font_secondary)
                    painter.setPen(sec_color)
                    painter.drawText(QRectF(col_x + 4, 18, col_w - 4, 18), Qt.AlignLeft | Qt.AlignVCenter, col.secondary_header)

                    if col.sub_label:
                        painter.setFont(font_sub)
                        painter.setPen(text_sec_col)
                        painter.drawText(QRectF(col_x + 4, 36, col_w - 4, 14), Qt.AlignLeft | Qt.AlignVCenter, col.sub_label)

            # Header bottom separator line
            painter.setPen(grid_major_pen)
            painter.drawLine(QPointF(scene_rect.left(), header_h), QPointF(scene_rect.right(), header_h))

            # Horizontal row separator lines
            row_h = float(self.row_height)
            y = header_h + row_h
            painter.setPen(grid_minor_pen)
            while y <= scene_rect.bottom():
                if y >= rect.top() - row_h and y <= rect.bottom() + row_h:
                    painter.drawLine(QPointF(scene_rect.left(), y), QPointF(scene_rect.right(), y))
                y += row_h

            # Today column marker line (if today is visible)
            if self._today_visible():
                today = date.today()
                today_x = TimescaleEngine.date_to_x(today, self.columns)
                today_pen = QPen(QColor(colors.get("today_marker_color", "#E95420")), 2.0, Qt.DashLine)
                today_pen.setCosmetic(True)
                painter.setPen(today_pen)
                painter.drawLine(QPointF(today_x, 0), QPointF(today_x, scene_rect.bottom()))

        # 4. Empty State Message (Drawn deterministically on canvas, zero hover disappearance)
        if getattr(self, "_current_empty_message", None):
            empty_rect = QRectF(50, 80, 750, 160)
            if rect.intersects(empty_rect):
                painter.setFont(QFont("Inter", 12))
                painter.setPen(QColor(colors.get("text_color", "#9CA3AF")))
                painter.drawText(empty_rect, Qt.AlignLeft | Qt.AlignTop, self._current_empty_message)

        painter.restore()

    # ========================================================
    # LIVE-TIME MARKER (lightweight, never clears the scene)
    # ========================================================
    def _on_minute_tick(self):
        """Lightweight live-time marker update. Never clears the scene."""
        self.update_current_time_marker()

    def _today_visible(self) -> bool:
        if not self.columns:
            return False
        today = date.today()
        if self.zoom_mode == ZoomLevel.HOURLY:
            return self.anchor_date == today
        return self.columns[0].start_date <= today <= self.columns[-1].end_date

    def _clear_current_time_marker(self):
        marker = self.current_time_line_item
        self.current_time_line_item = None
        if marker is None:
            return
        try:
            marker_scene = marker.scene()
        except RuntimeError:
            return
        except Exception:
            return
        if marker_scene is self.scene:
            try:
                self.scene.removeItem(marker)
            except RuntimeError:
                pass
            except Exception:
                pass

    def update_current_time_marker(self):
        """Paint-only current-time line update. No scene.clear()."""
        if not self.columns:
            self.current_time_line_item = None
            return
        if not self._today_visible():
            self._clear_current_time_marker()
            return
        app_theme = self.settings_manager.get("theme", "dark") if self.settings_manager else "dark"
        colors = self.color_profile.get_effective_colors(app_theme)
        today = date.today()
        now = datetime.now()
        col_width = float(self.columns[0].width) if self.columns else 60.0
        if self.zoom_mode == ZoomLevel.HOURLY:
            cur_time_x = TimescaleEngine.time_to_x(now.hour, now.minute, col_width)
        else:
            today_x = TimescaleEngine.date_to_x(today, self.columns)
            minute_offset = (now.hour * 60 + now.minute) / 1440.0
            cur_time_x = today_x + (minute_offset * col_width)
        rect = self.scene.sceneRect()
        total_height = float(rect.height()) if rect is not None and not rect.isNull() else 600.0
        pen = QPen(QColor(colors.get("current_time_marker_color", "#EF4444")), 2)
        if self.current_time_line_item is not None:
            try:
                line = self.current_time_line_item.line()
                line.setP1(QPointF(cur_time_x, 0))
                line.setP2(QPointF(cur_time_x, total_height))
                self.current_time_line_item.setLine(line)
                self.current_time_line_item.setPen(pen)
                return
            except RuntimeError:
                self.current_time_line_item = None
            except Exception:
                self.current_time_line_item = None
        marker = self.scene.addLine(cur_time_x, 0, cur_time_x, total_height)
        marker.setPen(pen)
        marker.setZValue(5000)
        self.current_time_line_item = marker

    # ========================================================
    # INTERACTIVE GANTT EDITING
    # ========================================================
    def _event_view_pos(self, event):
        """Qt5/Qt6 compatible event position helper."""
        try:
            return event.position().toPoint()
        except Exception:
            return event.pos()

    def _gantt_item_at(self, view_pos):
        """
        Return the GanttTaskItem owning whatever graphics child
        is under the cursor.
        """
        graphics_item = self.itemAt(view_pos)

        while graphics_item is not None:
            if isinstance(graphics_item, GanttTaskItem):
                return graphics_item
            graphics_item = graphics_item.parentItem()

        return None

    def _bar_interaction_mode(
        self,
        item,
        scene_pos,
    ):
        """
        Determine whether the pointer is on the actual schedule bar.

        Returns:
            "left"  -> resize start
            "right" -> resize finish
            "move"  -> move whole schedule
            None    -> title/status/empty area; do NOT reschedule

        This prevents clicks on task labels/status pills from causing
        accidental schedule movement.
        """
        if item is None:
            return None

        local_x = (
            float(scene_pos.x())
            - float(item.scenePos().x())
        )

        local_y = (
            float(scene_pos.y())
            - float(item.scenePos().y())
        )

        bar_width = float(
            getattr(
                item,
                "bar_pixel_width",
                max(
                    36.0,
                    float(
                        item.duration_cols
                        * item.col_width
                    ),
                ),
            )
        )

        configured_edge_px = float(self._resize_edge_px)
        minimum_edge_px = 6.0
        edge_px = min(
            configured_edge_px,
            max(minimum_edge_px, bar_width * 0.25),
        )

        # The bar itself occupies this row-height region.
        # Labels/status to the RIGHT of bar_width are excluded.
        if (
            local_y < 2.0
            or local_y
            > float(self.row_height) - 2.0
        ):
            return None

        if (
            local_x < -edge_px
            or local_x
            > bar_width + edge_px
        ):
            return None

        if bar_width <= (2.0 * edge_px):
            # Very short bar: left half = left resize, right half = right resize.
            # No move zone — prevents both edges resolving to "left".
            if local_x <= bar_width / 2.0:
                return "left"
            return "right"

        if abs(local_x) <= edge_px:
            return "left"

        if abs(
            local_x
            - bar_width
        ) <= edge_px:
            return "right"

        if (
            0.0
            <= local_x
            <= bar_width
        ):
            return "move"

        return None

    def mouseMoveEvent_hover_cursor(
        self,
        event,
    ):
        """
        Compatibility helper retained for static inspection.
        Real hover routing is performed inside mouseMoveEvent.
        """
        pass

    def _schedule_editable(self, item):
        """
        Phase 1D scheduling gate.

        WBS summary bars are derived from descendant schedule truth and are
        immutable. Every existing leaf-specific scheduling rule remains in
        _schedule_editable_leaf_authority().
        """
        if item is None:
            return False

        task = getattr(item, "task", None)
        if task is None:
            return False

        if bool(
            getattr(task, "gantt_read_only", False)
            or getattr(task, "gantt_is_summary", False)
        ):
            return False

        return self._schedule_editable_leaf_authority(item)

    def _schedule_editable_leaf_authority(self, item):
        if item is None:
            return False

        task = item.task

        # Historical/closed execution should not be accidentally
        # rescheduled by a mouse slip.
        if task.status in (
            TaskStatus.COMPLETED,
            TaskStatus.CANCELLED,
        ):
            return False

        # Interactive scheduling is supported where movement maps
        # cleanly to calendar units.
        return self.zoom_mode in (
            ZoomLevel.HOURLY,
            ZoomLevel.DAILY,
            ZoomLevel.WEEKLY,
            ZoomLevel.MONTHLY,
        )

    def _clear_resize_preview(self):
        # Capture and release our persistent reference FIRST.
        #
        # This prevents later code from retaining a Shiboken wrapper
        # after QGraphicsScene.clear() has destroyed the C++ object.
        preview = self._resize_preview
        self._resize_preview = None

        if preview is None:
            return

        try:
            preview_scene = preview.scene()
        except RuntimeError:
            # Underlying C++ object has already been deleted.
            return
        except Exception:
            return

        if preview_scene is self.scene:
            try:
                self.scene.removeItem(
                    preview
                )
            except RuntimeError:
                pass
            except Exception:
                pass


    def _reset_drag_state(self):
        self._clear_resize_preview()

        self._drag_item = None
        self._drag_start_scene_x = 0.0
        self._drag_start_item_x = 0.0
        self._drag_start_item_y = 0.0
        self._drag_moved = False

        self._resize_mode = None
        self._resize_item = None
        self._resize_start_scene_x = 0.0
        self._resize_start_item_x = 0.0
        self._resize_start_item_y = 0.0
        self._resize_moved = False

        try:
            self.viewport().setCursor(
                Qt.CursorShape.ArrowCursor
            )
        except Exception:
            pass

    def _parse_date(self, value, fallback=None):
        if value:
            try:
                return datetime.strptime(
                    str(value),
                    "%Y-%m-%d",
                ).date()
            except Exception:
                pass

        return fallback or date.today()

    def _parse_minutes(self, value, default=8 * 60):
        if value and ":" in str(value):
            try:
                hh, mm = map(
                    int,
                    str(value).split(":")[:2],
                )
                return max(
                    0,
                    min(
                        hh * 60 + mm,
                        1439,
                    ),
                )
            except Exception:
                pass

        return default

    @staticmethod
    def _shift_months(value, month_delta):
        """
        Calendar-safe month shifting preserving day where possible.
        Example: 31 Jan + 1 month -> 28/29 Feb.
        """
        import calendar

        month_index = (
            value.year * 12
            + (value.month - 1)
            + int(month_delta)
        )

        year = month_index // 12
        month = month_index % 12 + 1

        day = min(
            value.day,
            calendar.monthrange(
                year,
                month,
            )[1],
        )

        return date(
            year,
            month,
            day,
        )

    @staticmethod
    def _minutes_text(total_minutes):
        total_minutes = max(
            0,
            min(int(total_minutes), 1439),
        )
        hh = total_minutes // 60
        mm = total_minutes % 60
        return f"{hh:02d}:{mm:02d}"

    def _build_schedule_payload(
        self,
        item,
        delta_x,
    ):
        """
        Convert horizontal mouse movement into scheduling data.

        HOURLY:
          pixel movement -> 15 minute snapped time shift.

        DAILY:
          pixel movement -> whole-day date shift preserving span.

        WEEKLY:
          one timeline column -> one calendar week.

        MONTHLY:
          one timeline column -> one calendar month using
          calendar-safe month arithmetic.
        """
        task = item.task

        item_type = getattr(
            task,
            "gantt_item_type",
            "task",
        )

        payload = {
            "item_type": item_type,
            "task_id": int(task.id),
            "gantt_is_summary": bool(
                getattr(task, "gantt_is_summary", False)
            ),
            "gantt_read_only": bool(
                getattr(task, "gantt_read_only", False)
            ),
            "source_subtask_id": getattr(
                task,
                "source_subtask_id",
                None,
            ),
            "parent_task_id": getattr(
                task,
                "parent_task_id",
                None,
            ),
            "zoom_mode": self.zoom_mode.value,
            "title": task.title,
        }

        if not self.columns:
            return None

        col_width = float(
            self.columns[0].width
        )

        if col_width <= 0:
            return None

        # --------------------------------------------------
        # HOURLY — snap to 15-minute increments
        # --------------------------------------------------
        if self.zoom_mode == ZoomLevel.HOURLY:
            raw_minutes = (
                float(delta_x)
                / col_width
                * 60.0
            )

            snap = max(
                1,
                int(self.hourly_snap_minutes),
            )

            minute_delta = int(
                round(
                    raw_minutes / snap
                )
                * snap
            )

            if minute_delta == 0:
                return None

            start_minutes = self._parse_minutes(
                task.planned_start_time,
                8 * 60,
            )

            duration = int(
                task.estimated_duration
                or 30
            )

            # Keep Hourly-mode edits within the visible 24h day.
            # Cross-midnight scheduling remains supported by the
            # normal Task Dialog, but direct Gantt dragging remains
            # deterministic.
            duration = max(
                snap,
                min(duration, 1439),
            )

            latest_start = max(
                0,
                1440 - duration,
            )

            new_start = max(
                0,
                min(
                    start_minutes + minute_delta,
                    latest_start,
                ),
            )

            actual_delta = (
                new_start - start_minutes
            )

            if actual_delta == 0:
                return None

            new_end = min(
                new_start + duration,
                1439,
            )

            planned_date = self._parse_date(
                task.planned_date,
                self.anchor_date,
            )

            payload.update(
                {
                    "planned_date":
                        planned_date.strftime(
                            "%Y-%m-%d"
                        ),
                    "due_date":
                        task.due_date,
                    "planned_start_time":
                        self._minutes_text(
                            new_start
                        ),
                    "planned_end_time":
                        self._minutes_text(
                            new_end
                        ),
                    "estimated_duration":
                        duration,
                    "delta_minutes":
                        actual_delta,
                    "delta_days": 0,
                }
            )

            return payload

        # --------------------------------------------------
        # DAILY — whole-day movement preserving Due span
        # --------------------------------------------------
        if self.zoom_mode == ZoomLevel.DAILY:
            day_delta = int(
                round(
                    float(delta_x)
                    / col_width
                )
            )

            if day_delta == 0:
                return None

            old_start = self._parse_date(
                task.planned_date
            )

            old_due = self._parse_date(
                task.due_date,
                old_start,
            )

            # Prevent corrupt historical inversions.
            if old_due < old_start:
                old_due = old_start

            new_start = (
                old_start
                + timedelta(
                    days=day_delta
                )
            )

            new_due = (
                old_due
                + timedelta(
                    days=day_delta
                )
            )

            payload.update(
                {
                    "planned_date":
                        new_start.strftime(
                            "%Y-%m-%d"
                        ),
                    "due_date":
                        new_due.strftime(
                            "%Y-%m-%d"
                        ),
                    "planned_start_time":
                        task.planned_start_time,
                    "planned_end_time":
                        task.planned_end_time,
                    "estimated_duration":
                        int(
                            task.estimated_duration
                            or 0
                        ),
                    "delta_minutes": 0,
                    "delta_days":
                        day_delta,
                }
            )

            return payload

        # --------------------------------------------------
        # WEEKLY — exact whole-week movement
        # --------------------------------------------------
        if self.zoom_mode == ZoomLevel.WEEKLY:
            period_delta = int(
                round(
                    float(delta_x)
                    / col_width
                )
            )

            if period_delta == 0:
                return None

            day_delta = period_delta * 7

            old_start = self._parse_date(
                task.planned_date
            )

            old_due = self._parse_date(
                task.due_date,
                old_start,
            )

            if old_due < old_start:
                old_due = old_start

            new_start = (
                old_start
                + timedelta(days=day_delta)
            )

            new_due = (
                old_due
                + timedelta(days=day_delta)
            )

            payload.update(
                {
                    "planned_date":
                        new_start.strftime(
                            "%Y-%m-%d"
                        ),
                    "due_date":
                        new_due.strftime(
                            "%Y-%m-%d"
                        ),
                    "planned_start_time":
                        task.planned_start_time,
                    "planned_end_time":
                        task.planned_end_time,
                    "estimated_duration":
                        int(
                            task.estimated_duration
                            or 0
                        ),
                    "delta_minutes": 0,
                    "delta_days":
                        day_delta,
                    "delta_weeks":
                        period_delta,
                    "delta_months": 0,
                }
            )

            return payload

        # --------------------------------------------------
        # MONTHLY — calendar-safe month movement
        # --------------------------------------------------
        if self.zoom_mode == ZoomLevel.MONTHLY:
            month_delta = int(
                round(
                    float(delta_x)
                    / col_width
                )
            )

            if month_delta == 0:
                return None

            old_start = self._parse_date(
                task.planned_date
            )

            old_due = self._parse_date(
                task.due_date,
                old_start,
            )

            if old_due < old_start:
                old_due = old_start

            new_start = self._shift_months(
                old_start,
                month_delta,
            )

            new_due = self._shift_months(
                old_due,
                month_delta,
            )

            payload.update(
                {
                    "planned_date":
                        new_start.strftime(
                            "%Y-%m-%d"
                        ),
                    "due_date":
                        new_due.strftime(
                            "%Y-%m-%d"
                        ),
                    "planned_start_time":
                        task.planned_start_time,
                    "planned_end_time":
                        task.planned_end_time,
                    "estimated_duration":
                        int(
                            task.estimated_duration
                            or 0
                        ),
                    "delta_minutes": 0,
                    "delta_days": 0,
                    "delta_weeks": 0,
                    "delta_months":
                        month_delta,
                }
            )

            return payload

        return None

    def _build_resize_payload(
        self,
        item,
        edge,
        delta_x,
    ):
        """
        Convert an edge drag into persisted scheduling data.

        left:
            changes planned start while finish remains authoritative.

        right:
            changes planned finish while start remains authoritative.

        Hourly  -> 15-minute snap
        Daily   -> 1-day snap
        Weekly  -> 7-day snap
        Monthly -> calendar-month snap
        """
        if (
            not self.columns
            or edge
            not in ("left", "right")
        ):
            return None

        task = item.task

        # Closed/historical tasks are non-editable (TEST-G16): never
        # build a resize payload for them.
        if task.status in (
            TaskStatus.COMPLETED,
            TaskStatus.CANCELLED,
        ):
            return None

        col_width = float(
            self.columns[0].width
        )

        if col_width <= 0:
            return None

        item_type = getattr(
            task,
            "gantt_item_type",
            "task",
        )

        payload = {
            "item_type": item_type,
            "task_id": int(task.id),
            "gantt_is_summary": bool(
                getattr(task, "gantt_is_summary", False)
            ),
            "gantt_read_only": bool(
                getattr(task, "gantt_read_only", False)
            ),
            "source_subtask_id": getattr(
                task,
                "source_subtask_id",
                None,
            ),
            "parent_task_id": getattr(
                task,
                "parent_task_id",
                None,
            ),
            "zoom_mode": self.zoom_mode.value,
            "title": task.title,
            "edit_kind": "resize",
            "resize_edge": edge,
        }

        planned_day = self._parse_date(
            task.planned_date
        )

        due_day = self._parse_date(
            task.due_date,
            fallback=planned_day,
        )

        start_minutes = self._parse_minutes(
            task.planned_start_time,
            default=8 * 60,
        )

        end_minutes = self._parse_minutes(
            task.planned_end_time,
            default=(
                start_minutes
                + max(
                    15,
                    int(
                        task.estimated_duration
                        or 60
                    ),
                )
            ),
        )

        # -------------------------------------------------
        # HOURLY
        # -------------------------------------------------
        if self.zoom_mode == ZoomLevel.HOURLY:
            raw_minutes = (
                float(delta_x)
                / col_width
                * 60.0
            )

            snapped = int(
                round(
                    raw_minutes
                    / self.hourly_snap_minutes
                )
                * self.hourly_snap_minutes
            )

            if snapped == 0:
                # No movement after snapping — do not write an empty change.
                return None

            if edge == "left":
                new_start = max(
                    0,
                    min(
                        start_minutes
                        + snapped,
                        end_minutes
                        - self.hourly_snap_minutes,
                    ),
                )

                new_end = end_minutes

            else:
                new_start = start_minutes

                new_end = max(
                    start_minutes
                    + self.hourly_snap_minutes,
                    min(
                        end_minutes
                        + snapped,
                        1439,
                    ),
                )

            if new_start == start_minutes and new_end == end_minutes:
                # Boundary saturation or minimum duration clamp -> unchanged schedule
                return None

            duration = max(
                self.hourly_snap_minutes,
                new_end - new_start,
            )

            payload.update(
                {
                    "planned_date":
                        planned_day.strftime(
                            "%Y-%m-%d"
                        ),

                    "due_date":
                        planned_day.strftime(
                            "%Y-%m-%d"
                        ),

                    "planned_start_time":
                        self._minutes_text(
                            new_start
                        ),

                    "planned_end_time":
                        self._minutes_text(
                            new_end
                        ),

                    "estimated_duration":
                        duration,

                    "delta_minutes":
                        snapped,

                    "delta_days":
                        0,

                    "delta_weeks":
                        0,

                    "delta_months":
                        0,
                }
            )

            return payload

        # -------------------------------------------------
        # DAILY / WEEKLY
        # -------------------------------------------------
        if self.zoom_mode in (
            ZoomLevel.DAILY,
            ZoomLevel.WEEKLY,
        ):
            columns_delta = int(
                round(
                    float(delta_x)
                    / col_width
                )
            )

            step_days = (
                7
                if self.zoom_mode
                == ZoomLevel.WEEKLY
                else 1
            )

            day_delta = (
                columns_delta
                * step_days
            )

            if edge == "left":
                new_start_day = (
                    planned_day
                    + timedelta(
                        days=day_delta
                    )
                )

                # minimum one-day schedule
                if new_start_day > due_day:
                    new_start_day = due_day

                new_due_day = due_day

            else:
                new_start_day = planned_day

                new_due_day = (
                    due_day
                    + timedelta(
                        days=day_delta
                    )
                )

                if new_due_day < planned_day:
                    new_due_day = planned_day

            if new_start_day == planned_day and new_due_day == due_day:
                # Sub-snap or minimum clamp -> no date change
                return None

            duration_days = (
                new_due_day
                - new_start_day
            ).days + 1

            payload.update(
                {
                    "planned_date":
                        new_start_day.strftime(
                            "%Y-%m-%d"
                        ),

                    "due_date":
                        new_due_day.strftime(
                            "%Y-%m-%d"
                        ),

                    "planned_start_time":
                        task.planned_start_time,

                    "planned_end_time":
                        task.planned_end_time,

                    # Preserve effort minutes for date-span tasks.
                    "estimated_duration":
                        int(
                            task.estimated_duration
                            or max(
                                1,
                                duration_days
                            )
                            * 480
                        ),

                    "delta_minutes":
                        0,

                    "delta_days":
                        day_delta,

                    "delta_weeks":
                        (
                            columns_delta
                            if self.zoom_mode
                            == ZoomLevel.WEEKLY
                            else 0
                        ),

                    "delta_months":
                        0,
                }
            )

            return payload

        # -------------------------------------------------
        # MONTHLY
        # -------------------------------------------------
        if self.zoom_mode == ZoomLevel.MONTHLY:
            month_delta = int(
                round(
                    float(delta_x)
                    / col_width
                )
            )

            if edge == "left":
                new_start_day = (
                    self._shift_months(
                        planned_day,
                        month_delta,
                    )
                )

                if new_start_day > due_day:
                    new_start_day = due_day

                new_due_day = due_day

            else:
                new_start_day = planned_day

                new_due_day = (
                    self._shift_months(
                        due_day,
                        month_delta,
                    )
                )

                if new_due_day < planned_day:
                    new_due_day = planned_day

            if new_start_day == planned_day and new_due_day == due_day:
                # Sub-snap or clamp -> no date change
                return None

            payload.update(
                {
                    "planned_date":
                        new_start_day.strftime(
                            "%Y-%m-%d"
                        ),

                    "due_date":
                        new_due_day.strftime(
                            "%Y-%m-%d"
                        ),

                    "planned_start_time":
                        task.planned_start_time,

                    "planned_end_time":
                        task.planned_end_time,

                    "estimated_duration":
                        int(
                            task.estimated_duration
                            or 0
                        ),

                    "delta_minutes":
                        0,

                    "delta_days":
                        0,

                    "delta_weeks":
                        0,

                    "delta_months":
                        month_delta,
                }
            )

            return payload

        return None

    def _apply_payload_to_task(
        self,
        item,
        payload,
    ):
        task = item.task

        if bool(
            getattr(task, "gantt_is_summary", False)
            or getattr(task, "gantt_read_only", False)
        ):
            return

        task.planned_date = payload.get(
            "planned_date"
        )

        task.due_date = payload.get(
            "due_date"
        )

        task.planned_start_time = payload.get(
            "planned_start_time"
        )

        task.planned_end_time = payload.get(
            "planned_end_time"
        )

        task.estimated_duration = int(
            payload.get(
                "estimated_duration"
            )
            or 0
        )

    # --------------------------------------------------------
    # Mouse interaction
    # --------------------------------------------------------
    def mousePressEvent(self, event):
        if (
            event.button()
            != Qt.MouseButton.LeftButton
        ):
            super().mousePressEvent(
                event
            )
            return

        view_pos = self._event_view_pos(
            event
        )

        item = self._gantt_item_at(
            view_pos
        )

        if (
            item is None
            or not self._schedule_editable(
                item
            )
        ):
            super().mousePressEvent(
                event
            )
            return

        scene_pos = self.mapToScene(
            view_pos
        )

        interaction_mode = (
            self._bar_interaction_mode(
                item,
                scene_pos,
            )
        )

        # Clicking title, status, progress, dependency markers, etc.
        # must remain a selection/open action — never a schedule drag.
        if interaction_mode is None:
            super().mousePressEvent(
                event
            )
            return

        if interaction_mode in (
            "left",
            "right",
        ):
            self._resize_mode = (
                interaction_mode
            )

            self._resize_item = item

            self._resize_start_scene_x = (
                scene_pos.x()
            )

            self._resize_start_item_x = (
                item.pos().x()
            )

            self._resize_start_item_y = (
                item.pos().y()
            )

            self._resize_moved = False

            item.setSelected(
                True
            )

            try:
                self.viewport().setCursor(
                    Qt.CursorShape.SizeHorCursor
                )
            except Exception:
                pass

            event.accept()
            return

        # Interior of the actual bar = existing move behaviour.
        self._drag_item = item

        self._drag_start_scene_x = (
            scene_pos.x()
        )

        self._drag_start_item_x = (
            item.pos().x()
        )

        self._drag_start_item_y = (
            item.pos().y()
        )

        self._drag_moved = False

        item.setSelected(
            True
        )

        try:
            self.viewport().setCursor(
                Qt.CursorShape.ClosedHandCursor
            )
        except Exception:
            pass

        event.accept()


    def mouseMoveEvent(self, event):
        # --------------------------------------------------
        # HOVER AFFORDANCE — tells operator exactly where resize works.
        # --------------------------------------------------
        if not (
            event.buttons()
            & Qt.MouseButton.LeftButton
        ):
            view_pos = self._event_view_pos(
                event
            )

            item = None
            if view_pos.y() > self.header_height:
                item = self._gantt_item_at(
                    view_pos
                )

            mode = None

            if (
                item is not None
                and self._schedule_editable(
                    item
                )
            ):
                scene_pos = self.mapToScene(
                    view_pos
                )

                mode = (
                    self._bar_interaction_mode(
                        item,
                        scene_pos,
                    )
                )

            desired_cursor = Qt.CursorShape.ArrowCursor
            if mode in ("left", "right"):
                desired_cursor = Qt.CursorShape.SizeHorCursor
            elif mode == "move":
                desired_cursor = Qt.CursorShape.OpenHandCursor

            try:
                if self.viewport().cursor().shape() != desired_cursor:
                    self.viewport().setCursor(desired_cursor)
            except Exception:
                pass

            super().mouseMoveEvent(
                event
            )
            return

        # --------------------------------------------------
        # RESIZE PREVIEW
        # --------------------------------------------------
        if (
            self._resize_item is not None
            and (
                event.buttons()
                & Qt.MouseButton.LeftButton
            )
        ):
            view_pos = self._event_view_pos(
                event
            )

            scene_pos = self.mapToScene(
                view_pos
            )

            delta_x = (
                scene_pos.x()
                - self._resize_start_scene_x
            )

            if (
                abs(delta_x)
                >= self._drag_threshold_px
            ):
                self._resize_moved = True

            if self._resize_moved:
                item = self._resize_item

                original_x = (
                    self._resize_start_item_x
                )

                original_w = float(
                    getattr(
                        item,
                        "bar_pixel_width",
                        36.0,
                    )
                )

                if (
                    self._resize_mode
                    == "left"
                ):
                    preview_x = min(
                        original_x
                        + delta_x,
                        original_x
                        + original_w
                        - 12,
                    )

                    preview_w = max(
                        12.0,
                        original_w
                        - (
                            preview_x
                            - original_x
                        ),
                    )

                else:
                    preview_x = (
                        original_x
                    )

                    preview_w = max(
                        12.0,
                        original_w
                        + delta_x,
                    )

                self._clear_resize_preview()

                preview = QGraphicsRectItem(
                    preview_x,
                    self._resize_start_item_y
                    + 6,
                    preview_w,
                    max(
                        10,
                        self.row_height
                        - 12,
                    ),
                )

                brush_color = QColor(
                    self.planned_bar_color
                    or "#3584E4"
                )

                brush_color.setAlpha(
                    70
                )

                preview.setBrush(
                    QBrush(
                        brush_color
                    )
                )

                preview.setPen(
                    QPen(
                        QColor(
                            "#FFFFFF"
                        ),
                        1.5,
                        Qt.PenStyle.DashLine,
                    )
                )

                preview.setZValue(
                    10000
                )

                self.scene.addItem(
                    preview
                )

                self._resize_preview = (
                    preview
                )

                try:
                    self.viewport().setCursor(
                        Qt.CursorShape.SizeHorCursor
                    )
                except Exception:
                    pass

                try:
                    item.setOpacity(
                        0.55
                    )
                except Exception:
                    pass

            event.accept()
            return

        # --------------------------------------------------
        # EXISTING MOVE PREVIEW
        # --------------------------------------------------
        if (
            self._drag_item is None
            or not (
                event.buttons()
                & Qt.MouseButton.LeftButton
            )
        ):
            super().mouseMoveEvent(
                event
            )
            return

        view_pos = self._event_view_pos(
            event
        )

        scene_pos = self.mapToScene(
            view_pos
        )

        delta_x = (
            scene_pos.x()
            - self._drag_start_scene_x
        )

        if (
            abs(delta_x)
            >= self._drag_threshold_px
        ):
            self._drag_moved = True

        if self._drag_moved:
            self._drag_item.setPos(
                self._drag_start_item_x
                + delta_x,
                self._drag_start_item_y,
            )

            try:
                self._drag_item.setOpacity(
                    0.82
                )
            except Exception:
                pass

        event.accept()


    def mouseReleaseEvent(self, event):
        # --------------------------------------------------
        # RESIZE COMMIT
        # --------------------------------------------------
        if self._resize_item is not None:
            item = self._resize_item

            view_pos = self._event_view_pos(
                event
            )

            scene_pos = self.mapToScene(
                view_pos
            )

            delta_x = (
                scene_pos.x()
                - self._resize_start_scene_x
            )

            payload = None

            if self._resize_moved:
                payload = (
                    self._build_resize_payload(
                        item,
                        self._resize_mode,
                        delta_x,
                    )
                )

            try:
                item.setOpacity(
                    1.0
                )
            except Exception:
                pass

            if payload:
                self._apply_payload_to_task(
                    item,
                    payload,
                )

                self.schedule_change_requested.emit(
                    payload
                )

            self._reset_drag_state()

            event.accept()
            return

        # --------------------------------------------------
        # EXISTING MOVE COMMIT
        # --------------------------------------------------
        item = self._drag_item

        if item is None:
            super().mouseReleaseEvent(
                event
            )
            return

        view_pos = self._event_view_pos(
            event
        )

        scene_pos = self.mapToScene(
            view_pos
        )

        delta_x = (
            scene_pos.x()
            - self._drag_start_scene_x
        )

        # Restore preview position. Database truth rebuilds chart.
        item.setPos(
            self._drag_start_item_x,
            self._drag_start_item_y,
        )

        try:
            item.setOpacity(
                1.0
            )
        except Exception:
            pass

        payload = None

        if self._drag_moved:
            payload = (
                self._build_schedule_payload(
                    item,
                    delta_x,
                )
            )

        if payload:
            self._apply_payload_to_task(
                item,
                payload,
            )

            self.schedule_change_requested.emit(
                payload
            )

        self._reset_drag_state()

        super().mouseReleaseEvent(
            event
        )


    def mouseDoubleClickEvent(self, event):
        item = self._gantt_item_at(
            self._event_view_pos(event)
        )

        if item is not None:
            self.task_action_requested.emit(
                "open",
                int(item.task.id),
            )
            event.accept()
            return

        super().mouseDoubleClickEvent(event)

    # --------------------------------------------------------
    # Right-click professional task actions
    # --------------------------------------------------------
    def contextMenuEvent(self, event):
        item = self._gantt_item_at(
            event.pos()
        )

        if item is None:
            super().contextMenuEvent(event)
            return

        task = item.task
        is_nested = (
            getattr(
                task,
                "gantt_item_type",
                "task",
            )
            != "task"
        )

        menu = QMenu(self)

        action_open_text = "✏ Edit Subtask" if is_nested else "✏ Open Task"
        open_action = menu.addAction(action_open_text)
        copy_details_action = menu.addAction("📋 Copy Schedule Details")
        view_details_action = menu.addAction("🔍 View Schedule Details...")

        menu.addSeparator()

        start_action = menu.addAction(
            "▶ Start"
        )

        pause_action = menu.addAction(
            "⏸ Pause"
        )

        complete_action = menu.addAction(
            "✓ Complete"
        )

        # Execution status actions are only valid for real main tasks.
        for action in (
            start_action,
            pause_action,
            complete_action,
        ):
            action.setEnabled(
                not is_nested
                and task.status
                not in (
                    TaskStatus.COMPLETED,
                    TaskStatus.CANCELLED,
                )
            )

        chosen = menu.exec(
            event.globalPos()
        )

        if chosen is None:
            return

        if chosen == open_action:
            action_name = "open"
        elif chosen == copy_details_action:
            action_name = "copy_details"
        elif chosen == view_details_action:
            action_name = "view_details"
        elif chosen == start_action:
            action_name = "start"
        elif chosen == pause_action:
            action_name = "pause"
        elif chosen == complete_action:
            action_name = "complete"
        else:
            return

        self.task_action_requested.emit(
            action_name,
            int(task.id),
        )

    # --------------------------------------------------------
    # Keyboard precision nudging
    # --------------------------------------------------------
    def nudge_selected_task(self, direction):
        """
        Visible-toolbar equivalent of keyboard Left/Right.

        direction:
          -1 = Earlier
          +1 = Later
        """
        selected = [
            item
            for item in self.scene.selectedItems()
            if isinstance(
                item,
                GanttTaskItem,
            )
        ]

        if not selected:
            return False, "Select a Gantt task first."

        item = selected[0]

        if not self._schedule_editable(item):
            return (
                False,
                "This task cannot be rescheduled in the current mode.",
            )

        if not self.columns:
            return False, "Timeline is not ready."

        col_width = float(
            self.columns[0].width
        )

        if self.zoom_mode == ZoomLevel.HOURLY:
            pixel_delta = (
                int(direction)
                * col_width
                * self.hourly_snap_minutes
                / 60.0
            )
        else:
            pixel_delta = (
                int(direction)
                * col_width
            )

        payload = self._build_schedule_payload(
            item,
            pixel_delta,
        )

        if not payload:
            return False, "No schedule change was produced."

        self._apply_payload_to_task(
            item,
            payload,
        )

        self.schedule_change_requested.emit(
            payload
        )

        return True, ""

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            selected = [
                item
                for item in self.scene.selectedItems()
                if isinstance(
                    item,
                    GanttTaskItem,
                )
            ]
            if selected and hasattr(selected[0], "task"):
                self.task_action_requested.emit("open", int(selected[0].task.id))
                event.accept()
                return

        if event.key() not in (
            Qt.Key.Key_Left,
            Qt.Key.Key_Right,
        ):
            super().keyPressEvent(event)
            return

        selected = [
            item
            for item in self.scene.selectedItems()
            if isinstance(
                item,
                GanttTaskItem,
            )
        ]

        if not selected:
            super().keyPressEvent(event)
            return

        item = selected[0]

        if not self._schedule_editable(
            item
        ):
            super().keyPressEvent(event)
            return

        direction = (
            -1
            if event.key()
            == Qt.Key.Key_Left
            else 1
        )

        if not self.columns:
            return

        col_width = float(
            self.columns[0].width
        )

        if self.zoom_mode == ZoomLevel.HOURLY:
            pixel_delta = (
                direction
                * col_width
                * self.hourly_snap_minutes
                / 60.0
            )
        else:
            # Daily / Weekly / Monthly each move by one
            # visible calendar column.
            pixel_delta = (
                direction
                * col_width
            )

        payload = self._build_schedule_payload(
            item,
            pixel_delta,
        )

        if payload:
            self._apply_payload_to_task(
                item,
                payload,
            )

            self.schedule_change_requested.emit(
                payload
            )

        event.accept()

    def _clear_dependency_graphics(
        self,
    ):
        # Detach Python references before touching Qt objects.
        #
        # This method is for dependency-only redraws. During a full
        # rebuild, rebuild_chart() intentionally clears this list and
        # lets QGraphicsScene.clear() own destruction.
        graphics = list(
            self._dependency_graphics
            or []
        )

        self._dependency_graphics = []

        for graphic in graphics:
            try:
                graphic_scene = (
                    graphic.scene()
                )
            except RuntimeError:
                # Shiboken wrapper whose C++ item was already deleted.
                continue
            except Exception:
                continue

            if graphic_scene is self.scene:
                try:
                    self.scene.removeItem(
                        graphic
                    )
                except RuntimeError:
                    pass
                except Exception:
                    pass


    def _draw_dependency_arrows(
        self,
    ):
        """
        Draw routed Finish→Start dependency arrows.

        Colors:
          grey/blue : valid FS dependency
          orange    : timing violation
          red       : critical-path dependency
        """
        self._clear_dependency_graphics()

        item_map = dict(
            self._rendered_task_items
            or {}
        )

        task_map = {
            int(task.id): task
            for task in self.tasks
            if (
                task.id is not None
                and getattr(
                    task,
                    "gantt_item_type",
                    "task",
                )
                == "task"
            )
        }

        from todo_bird_app.services.cpm_scheduling_service import parse_dependency_specs, DependencyType, format_lag_duration

        for successor_id, successor in task_map.items():
            successor_item = item_map.get(
                successor_id
            )

            if successor_item is None:
                continue

            specs = parse_dependency_specs(successor.dependencies, successor_id=successor_id)
            for spec in specs:
                predecessor_id = spec.predecessor_id
                predecessor = task_map.get(
                    predecessor_id
                )
                predecessor_item = item_map.get(
                    predecessor_id
                )

                if (
                    predecessor is None
                    or predecessor_item is None
                ):
                    continue

                pred_left = predecessor_item.scenePos().x()
                pred_right = pred_left + float(
                    getattr(
                        predecessor_item,
                        "bar_pixel_width",
                        36.0,
                    )
                )
                pred_y = predecessor_item.scenePos().y() + self.row_height / 2

                succ_left = successor_item.scenePos().x()
                succ_right = succ_left + float(
                    getattr(
                        successor_item,
                        "bar_pixel_width",
                        36.0,
                    )
                )
                succ_y = successor_item.scenePos().y() + self.row_height / 2

                dtype = spec.dependency_type
                lag_m = spec.lag_minutes

                # Anchor selection based on dependency type
                if dtype == DependencyType.FS:
                    start = QPointF(pred_right, pred_y)
                    end = QPointF(succ_left, succ_y)
                elif dtype == DependencyType.SS:
                    start = QPointF(pred_left, pred_y)
                    end = QPointF(succ_left, succ_y)
                elif dtype == DependencyType.FF:
                    start = QPointF(pred_right, pred_y)
                    end = QPointF(succ_right, succ_y)
                elif dtype == DependencyType.SF:
                    start = QPointF(pred_left, pred_y)
                    end = QPointF(succ_right, succ_y)
                else:
                    start = QPointF(pred_right, pred_y)
                    end = QPointF(succ_left, succ_y)

                violation = (
                    GanttDependencyEngine
                    .edge_violation(
                        predecessor,
                        successor,
                        spec=spec,
                    )
                )

                pred_crit = bool(getattr(predecessor, "cpm_is_critical", getattr(predecessor, "gantt_critical_path", False)))
                succ_crit = bool(getattr(successor, "cpm_is_critical", getattr(successor, "gantt_critical_path", False)))
                pred_cycle = bool(getattr(predecessor, "gantt_dependency_cycle", False))
                succ_cycle = bool(getattr(successor, "gantt_dependency_cycle", False))
                critical_edge = pred_crit and succ_crit and not (pred_cycle or succ_cycle)

                if violation:
                    color = QColor(
                        "#F97316"
                    )
                    width = 2.5

                elif critical_edge:
                    color = QColor(
                        "#DC2626"
                    )
                    width = 2.5

                else:
                    color = QColor(
                        "#64748B"
                    )
                    width = 1.5

                path = QPainterPath()
                path.moveTo(
                    start
                )

                # Orthogonal routing provides better readability than
                # diagonal lines across task bars.
                route_x = max(
                    start.x() + 14,
                    (
                        start.x()
                        + end.x()
                    )
                    / 2,
                ) if end.x() >= start.x() else min(
                    start.x() - 14,
                    (
                        start.x()
                        + end.x()
                    )
                    / 2,
                )

                path.lineTo(
                    route_x,
                    start.y(),
                )

                path.lineTo(
                    route_x,
                    end.y(),
                )

                path.lineTo(
                    end.x() - 7,
                    end.y(),
                )

                arrow = QGraphicsPathItem(
                    path
                )

                pen = QPen(
                    color,
                    width,
                )

                if violation:
                    pen.setStyle(
                        Qt.PenStyle.DashLine
                    )

                arrow.setPen(
                    pen
                )
                arrow.setBrush(
                    Qt.NoBrush
                )
                arrow.setZValue(
                    8000
                )

                lag_desc = f" ({format_lag_duration(lag_m)})" if lag_m != 0 else ""
                type_name = {
                    DependencyType.FS: "Finish→Start",
                    DependencyType.SS: "Start→Start",
                    DependencyType.FF: "Finish→Finish",
                    DependencyType.SF: "Start→Finish",
                }.get(dtype, dtype.value)

                prefix = (
                    f"⚠ {type_name} dependency violation"
                    if violation
                    else (
                        "◆ Critical-path dependency"
                        if critical_edge
                        else f"{type_name} dependency{lag_desc}"
                    )
                )

                arrow.setToolTip(
                    f"{prefix}\n{predecessor.title} → {successor.title}"
                )

                self.scene.addItem(
                    arrow
                )

                self._dependency_graphics.append(
                    arrow
                )

                # Arrow head.
                tip = QPointF(
                    end.x(),
                    end.y(),
                )

                head = QPolygonF([
                    tip,
                    QPointF(
                        tip.x() - 8,
                        tip.y() - 5,
                    ),
                    QPointF(
                        tip.x() - 8,
                        tip.y() + 5,
                    ),
                ])

                head_item = QGraphicsPolygonItem(
                    head
                )

                head_item.setBrush(
                    QBrush(color)
                )

                head_item.setPen(
                    QPen(
                        color,
                        1.0,
                    )
                )

                head_item.setZValue(
                    8001
                )

                self.scene.addItem(
                    head_item
                )

                self._dependency_graphics.append(
                    head_item
                )

    def set_planned_bar_color(
        self,
        color,
    ):
        self.planned_bar_color = (
            color
            or "#3584E4"
        )

        if self.settings_manager:
            self.settings_manager.set(
                "gantt_planned_bar_color",
                self.planned_bar_color,
            )

        self.rebuild_chart()

    def set_bar_style(self, style):
        self.bar_style = (
            style
            or "rounded"
        )

        if self.settings_manager:
            self.settings_manager.set(
                "gantt_bar_style",
                self.bar_style,
            )

        self.rebuild_chart()

    def set_color_profile(self, profile: GanttColorProfile, app_theme: str = "dark"):
        self.color_profile = profile
        self.rebuild_chart()

    def set_zoom_mode(self, mode_str: str):
        mode_str = mode_str.lower().replace("-", "_").replace(" ", "_")
        try:
            self.zoom_mode = ZoomLevel(mode_str)
        except ValueError:
            self.zoom_mode = ZoomLevel.DAILY
        self.rebuild_chart()

    def set_tasks(self, tasks: List[Task], projects_map: Dict[int, str]):
        self.tasks = list(tasks)
        self.projects_map = dict(projects_map)

        # One transient dependency/critical-path analysis per
        # authoritative task refresh.
        GanttDependencyEngine.annotate(
            self.tasks
        )

        self.rebuild_chart()

    def set_filters(self, show_actual=True, show_completed=True, project_id=None, priority=None, show_baseline=True):
        self.show_actual_bars = show_actual
        self.show_completed = show_completed
        self.show_baseline = show_baseline
        self.filter_project_id = project_id
        self.filter_priority = priority
        self.rebuild_chart()

    def auto_center_today(self):
        self.anchor_date = date.today()
        self.rebuild_chart()

    def navigate_period(self, step: int):
        if self.zoom_mode == ZoomLevel.HOURLY:
            self.anchor_date += timedelta(days=step)
        elif self.zoom_mode == ZoomLevel.DAILY:
            self.anchor_date += timedelta(days=step)
        elif self.zoom_mode == ZoomLevel.WEEKLY:
            self.anchor_date += timedelta(weeks=step)
        elif self.zoom_mode == ZoomLevel.MONTHLY:
            from todo_bird_app.gantt.timescale_engine import add_months
            self.anchor_date = add_months(self.anchor_date, step)
        elif self.zoom_mode == ZoomLevel.YEARLY:
            self.anchor_date = date(self.anchor_date.year + step, self.anchor_date.month, 1)
        elif self.zoom_mode == ZoomLevel.MULTI_YEAR:
            self.anchor_date = date(self.anchor_date.year + (step * 5), self.anchor_date.month, 1)
        self.rebuild_chart()

    @staticmethod
    def _parse_date(value, fallback: Optional[date] = None) -> Optional[date]:
        if not value:
            return fallback
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        try:
            return datetime.strptime(str(value).strip()[:10], "%Y-%m-%d").date()
        except Exception:
            return fallback

    def _gantt_planned_date_range(
        self,
        task,
        include_due_date: bool = False,
    ):
        p = (
            self._parse_date(getattr(task, "gantt_planned_start", None))
            or self._parse_date(getattr(task, "cpm_earliest_start", None))
            or self._parse_date(getattr(task, "planned_date", None))
        )
        d = (
            self._parse_date(getattr(task, "gantt_planned_finish", None))
            or self._parse_date(getattr(task, "cpm_earliest_finish", None))
            or self._parse_date(getattr(task, "due_date", None))
        )
        if include_due_date:
            raw_due = self._parse_date(getattr(task, "due_date", None))
            if raw_due is not None:
                d = max(d, raw_due) if d is not None else raw_due
        return p, d

    def _hourly_visible_task_count(self, tasks):
        """
        Read-only count of tasks active on the current anchor date
        (including planned, due, actual work, and multi-day spans).
        """
        count = 0
        s_iso = self.anchor_date.strftime("%Y-%m-%d")
        for task in tasks:
            p, d = self._gantt_planned_date_range(
                task,
                include_due_date=True,
            )
            act_s = getattr(task, "actual_start_date", None)
            act_e = getattr(task, "actual_end_date", None) or act_s

            is_active = False
            if p and d:
                start = min(p, d)
                end = max(p, d)
                if start <= self.anchor_date <= end:
                    is_active = True
            elif p and p == self.anchor_date:
                is_active = True
            elif d and d == self.anchor_date:
                is_active = True

            if not is_active and act_s:
                if act_e:
                    is_active = (act_s <= s_iso <= act_e)
                else:
                    is_active = (act_s == s_iso)

            if is_active:
                count += 1
        return count

    def _hourly_timed_task_count(self, tasks):
        """
        Read-only count of tasks that have a renderable timed Planned
        or Actual segment on the Hourly anchor date.

        Planned Hourly work is timed only on the explicit planned/current
        start day. Due dates and intermediate span days keep the row
        active, but they do not fabricate a timed Planned segment.
        """
        count = 0
        s_iso = self.anchor_date.strftime("%Y-%m-%d")

        for task in tasks:
            p, d = self._gantt_planned_date_range(task)

            pst = getattr(
                task,
                "planned_start_time",
                None,
            )
            pet = getattr(
                task,
                "planned_end_time",
                None,
            )
            est = int(
                getattr(
                    task,
                    "estimated_duration",
                    0,
                )
                or 0
            )

            has_timed_plan = False

            if p and p == self.anchor_date:
                has_timed_plan = bool(
                    pst is not None
                    or pet is not None
                    or est > 0
                )

            elif p is None and d == self.anchor_date:
                has_timed_plan = bool(
                    pst is not None
                    or pet is not None
                    or est > 0
                )

            act_s = getattr(
                task,
                "actual_start_date",
                None,
            )
            act_e = (
                getattr(
                    task,
                    "actual_end_date",
                    None,
                )
                or act_s
            )

            has_timed_act = False

            if act_s:
                if (
                    (
                        act_e
                        and act_s <= s_iso <= act_e
                    )
                    or act_s == s_iso
                ):
                    has_timed_act = bool(
                        getattr(
                            task,
                            "actual_start_time",
                            None,
                        )
                        or int(
                            getattr(
                                task,
                                "actual_duration",
                                0,
                            )
                            or 0
                        ) > 0
                        or bool(
                            getattr(
                                task,
                                "gantt_summary_actual_visible",
                                False,
                            )
                        )
                    )

            if has_timed_plan or has_timed_act:
                count += 1

        return count

    def _nearest_scheduled_date(self, tasks):
        """
        Read-only helper: nearest parseable planned/due/actual date to the anchor date.
        Returns None when no task has a parseable date.
        """
        best = None
        best_delta = None
        for task in tasks:
            p = self._parse_date(task.planned_date)
            d = self._parse_date(task.due_date)
            a_s = self._parse_date(getattr(task, "actual_start_date", None))
            a_e = self._parse_date(getattr(task, "actual_end_date", None))
            for cand in (p, d, a_s, a_e):
                if cand:
                    delta = abs((cand - self.anchor_date).days)
                    if best_delta is None or delta < best_delta:
                        best, best_delta = cand, delta
        return best

    def rebuild_chart(self):
        # -------------------------------------------------
        # QT / SHIBOKEN OBJECT-LIFETIME AUTHORITY
        #
        # QGraphicsScene.clear() destroys the underlying C++
        # QGraphicsItems. Any Python wrapper retained afterwards
        # becomes invalid and can segfault when later replaced,
        # inspected or garbage-collected.
        #
        # Therefore ALL persistent Python references to scene-owned
        # graphics must be released BEFORE scene.clear().
        # -------------------------------------------------

        self.current_time_line_item = None

        self._resize_preview = None
        self._resize_item = None
        self._drag_item = None

        # Do NOT individually remove dependency graphics here.
        # The scene owns them and scene.clear() will destroy them
        # exactly once.
        self._dependency_graphics = []

        # GanttTaskItem wrappers are also scene-owned.
        self._rendered_task_items = {}

        self.scene.clear()
        app_theme = self.settings_manager.get("theme", "dark") if self.settings_manager else "dark"
        colors = self.color_profile.get_effective_colors(
            app_theme
        )

        from todo_bird_app.services.typography_service import TypographyService
        base_g_font = TypographyService.get_font_for_area("gantt", self.settings_manager)

        # Planned baseline color is a user preference independent
        # of timing-performance colors.
        colors["planned_color"] = (
            self.planned_bar_color
            or "#3584E4"
        )

        today = date.today()

        # 1. Apply filters
        filtered_tasks = [t for t in self.tasks if bool(t.show_in_gantt)]
        if not self.show_completed:
            filtered_tasks = [t for t in filtered_tasks if t.status != TaskStatus.COMPLETED]
        if self.filter_project_id:
            filtered_tasks = [t for t in filtered_tasks if t.project_id == self.filter_project_id]
        if self.filter_priority:
            filtered_tasks = [t for t in filtered_tasks if t.priority.value == self.filter_priority]

        # 2. Generate non-repeating timeline columns from TimescaleEngine
        self.columns = TimescaleEngine.generate_columns(
            self.zoom_mode, self.anchor_date, filtered_tasks
        )

        if not self.columns:
            return

        # Explicit Z-Value Layering
        Z_BACKGROUND = -1000.0
        Z_GRID = -500.0
        Z_TASK = 100.0
        Z_OVERLAY = 500.0
        Z_HEADER_BG = 1000.0
        Z_HEADER_TEXT = 1100.0
        Z_CURRENT_TIME = 5000.0

        total_width = self.columns[-1].x_offset + self.columns[-1].width
        total_height = self.header_height + max(len(filtered_tasks), 5) * self.row_height + 60.0
        vp_w = float(self.viewport().width()) if self.viewport() else 800.0
        vp_h = float(self.viewport().height()) if self.viewport() else 600.0
        self.scene.setSceneRect(0, 0, max(total_width, vp_w, 800.0), max(total_height, vp_h, 600.0))

        # 3. Render Live Current Time Line (paint-only update; no scene.clear)
        self.update_current_time_marker()

        if not filtered_tasks:
            message = "No tasks to display in Gantt view."
            if self.zoom_mode == ZoomLevel.HOURLY:
                message = "No tasks scheduled for " + self.anchor_date.strftime("%d %b %Y")
            self._current_empty_message = message
            return

        # Hourly: check timed tasks vs active tasks on the anchor date
        if self.zoom_mode == ZoomLevel.HOURLY:
            timed_count = self._hourly_timed_task_count(filtered_tasks)
            active_count = self._hourly_visible_task_count(filtered_tasks)
            if timed_count == 0:
                if active_count == 0:
                    message = "No tasks scheduled for " + self.anchor_date.strftime("%d %b %Y")
                    nearest = self._nearest_scheduled_date(filtered_tasks)
                    if nearest is not None:
                        message += "\nNearest scheduled date: " + nearest.strftime("%d %b") + " →"
                    self._current_empty_message = message
                    return
                else:
                    plural = "task is" if active_count == 1 else "tasks are"
                    self._current_empty_message = f"{active_count} {plural} active today, but none have a timed schedule."
            else:
                self._current_empty_message = None
        else:
            self._current_empty_message = None

        # 7. Render Task Bars mapped to Timescale Engine X coordinates
        visible_start = self.columns[0].start_date
        visible_end = self.columns[-1].end_date
        row_idx = 0
        
        rendered_tasks_list = []

        for task in filtered_tasks:
            g_start = getattr(task, "gantt_planned_start", None)
            if g_start is None and getattr(task, "cpm_earliest_start", None):
                cpm_s = task.cpm_earliest_start
                if isinstance(cpm_s, (datetime, date)):
                    g_start = cpm_s
                elif isinstance(cpm_s, str) and cpm_s:
                    try:
                        g_start = datetime.fromisoformat(cpm_s)
                    except Exception:
                        try:
                            g_start = datetime.strptime(cpm_s[:10], "%Y-%m-%d")
                        except Exception:
                            g_start = None

            if isinstance(g_start, datetime):
                p_start = g_start.date()
            elif isinstance(g_start, date):
                p_start = g_start
            else:
                p_date_str = task.planned_date
                try:
                    p_start = datetime.strptime(p_date_str, "%Y-%m-%d").date() if p_date_str else None
                except Exception:
                    p_start = None

            g_finish = getattr(task, "gantt_planned_finish", None)
            if g_finish is None and getattr(task, "cpm_earliest_finish", None):
                cpm_f = task.cpm_earliest_finish
                if isinstance(cpm_f, (datetime, date)):
                    g_finish = cpm_f
                elif isinstance(cpm_f, str) and cpm_f:
                    try:
                        g_finish = datetime.fromisoformat(cpm_f)
                    except Exception:
                        try:
                            g_finish = datetime.strptime(cpm_f[:10], "%Y-%m-%d")
                        except Exception:
                            g_finish = None

            if isinstance(g_finish, datetime):
                p_finish = g_finish.date()
            elif isinstance(g_finish, date):
                p_finish = g_finish
            else:
                p_finish = None

            if self.zoom_mode == ZoomLevel.HOURLY:
                # Active on anchor date if planned/current schedule spans it,
                # due date reaches it, or actual execution explicitly spans it.
                p = p_start if p_start else self._parse_date(task.planned_date)
                d = p_finish if p_finish else self._parse_date(task.due_date)
                act_s = getattr(task, "actual_start_date", None)
                act_e = getattr(task, "actual_end_date", None) or act_s
                s_iso = self.anchor_date.strftime("%Y-%m-%d")

                is_active_today = False
                if p and d:
                    start = min(p, d)
                    end = max(p, d)
                    if start <= self.anchor_date <= end:
                        is_active_today = True
                elif p and p == self.anchor_date:
                    is_active_today = True
                elif d and d == self.anchor_date:
                    is_active_today = True

                if not is_active_today and act_s:
                    if act_e:
                        is_active_today = (act_s <= s_iso <= act_e)
                    else:
                        is_active_today = (act_s == s_iso)

                if not is_active_today:
                    continue

                from todo_bird_app.utils.time_math import (
                    parse_hhmm,
                    minutes_to_x,
                    duration_to_width,
                    segment_interval_by_day,
                )

                col_w = float(self.columns[0].width)

                # --------------------------------------------------
                # PHASE 1D — HOURLY PLANNED-DAY SEGMENT
                #
                # Never use the entire multi-day estimated_duration
                # as the width of one Hourly day.
                # --------------------------------------------------
                planned_active_today = False

                if p:
                    planned_active_today = (
                        p == self.anchor_date
                    )
                elif d:
                    planned_active_today = (
                        d == self.anchor_date
                    )

                start_minutes = 8 * 60
                duration_m = 30
                actual_segment_today = False

                if planned_active_today:
                    pst_m = parse_hhmm(
                        task.planned_start_time
                    )
                    pet_m = parse_hhmm(
                        task.planned_end_time
                    )

                    start_minutes = (
                        pst_m
                        if pst_m is not None
                        else 8 * 60
                    )

                    if (
                        pet_m is not None
                        and pet_m > start_minutes
                    ):
                        duration_m = (
                            pet_m - start_minutes
                        )

                    elif int(
                        task.estimated_duration or 0
                    ) > 0:
                        duration_m = min(
                            1440 - start_minutes,
                            int(
                                task.estimated_duration
                                or 0
                            ),
                        )

                    else:
                        duration_m = 30

                # --------------------------------------------------
                # ACTUAL-ONLY ACTIVE DAY FALLBACK
                #
                # Preserve existing behavior for a row visible today
                # because of Actual execution rather than Planned.
                # --------------------------------------------------
                else:
                    if act_s and s_iso:
                        segments = segment_interval_by_day(
                            start_date=act_s,
                            start_time=task.actual_start_time,
                            end_date=act_e,
                            end_time=task.actual_end_time,
                        )

                        seg_today = next(
                            (
                                seg
                                for seg in segments
                                if seg.date
                                == self.anchor_date
                            ),
                            None,
                        )

                        if seg_today:
                            actual_segment_today = True
                            start_minutes = (
                                seg_today.start_minute
                            )
                            duration_m = max(
                                1,
                                seg_today.end_minute_exclusive
                                - seg_today.start_minute,
                            )

                        elif act_s == s_iso:
                            a_min = parse_hhmm(
                                task.actual_start_time
                            )

                            if a_min is not None:
                                actual_segment_today = True
                                start_minutes = a_min

                            duration_m = max(
                                1,
                                int(
                                    task.actual_duration
                                    or 30
                                ),
                            )

                        elif act_s < s_iso:
                            actual_segment_today = True
                            start_minutes = 0
                            duration_m = 1440

                if (
                    not planned_active_today
                    and not actual_segment_today
                ):
                    continue

                # GanttTaskItem must not independently reinterpret
                # Hourly date visibility after the chart has already
                # resolved the selected-day planned segment.
                task.gantt_hourly_has_planned_segment = bool(
                    planned_active_today
                )

                # Strict 24-hour Hourly geometry.
                start_minutes = max(
                    0,
                    min(1439, int(start_minutes)),
                )

                duration_m = max(
                    1,
                    min(
                        1440 - start_minutes,
                        int(duration_m),
                    ),
                )

                col_x_start = minutes_to_x(
                    start_minutes,
                    col_w,
                )

                bar_width = max(
                    16.0,
                    duration_to_width(
                        duration_m,
                        col_w,
                    ),
                )

                start_col_index = int(
                    start_minutes // 60
                )

                dur_cols = max(
                    0.25,
                    bar_width / col_w,
                )
            else:
                # Multi-day / Daily modes:
                if not p_start:
                    p_start = self._parse_date(task.due_date, fallback=self.anchor_date)

                if p_finish:
                    p_end = p_finish
                else:
                    p_end = p_start

                    if task.due_date:
                        try:
                            due_date = datetime.strptime(
                                task.due_date,
                                "%Y-%m-%d"
                            ).date()

                            if due_date >= p_start:
                                p_end = due_date
                        except Exception:
                            pass

                    if p_end == p_start and not task.due_date:
                        est_days = (
                            max(
                                1,
                                int(
                                    (task.estimated_duration + 479) / 480
                                )
                            )
                            if task.estimated_duration > 0
                            else 1
                        )
                        p_end = p_start + timedelta(days=est_days - 1)

                if not TimescaleEngine.intersects_visible_range(p_start, p_end, visible_start, visible_end):
                    continue

                col_x_start = TimescaleEngine.date_to_x(p_start, self.columns)
                col_x_end = TimescaleEngine.date_to_x(p_end + timedelta(days=1), self.columns)
                bar_width = max(24.0, col_x_end - col_x_start)

                start_col_index = max(0, int(col_x_start / self.columns[0].width))
                dur_cols = max(1.0, bar_width / self.columns[0].width)

            # --------------------------------------------------
            # PHASE 1D — DERIVED SUMMARY ACTUAL GEOMETRY
            #
            # Parent Actual is independent of parent Planned geometry.
            # Compute an explicit local X-offset + width so the graphics
            # item never estimates Actual from progress or effort.
            # --------------------------------------------------
            task.gantt_summary_actual_visible = False
            task.gantt_summary_actual_x_offset = 0.0
            task.gantt_summary_actual_width = 0.0

            if bool(
                getattr(task, "gantt_is_summary", False)
            ):
                actual_start_dt = getattr(
                    task,
                    "gantt_summary_actual_start",
                    None,
                )
                actual_visual_end_dt = getattr(
                    task,
                    "gantt_summary_actual_activity_end",
                    None,
                )
            else:
                from todo_bird_app.utils.time_math import combine_date_time, get_current_datetime
                act_s_d = getattr(task, "actual_start_date", None)
                act_s_t = getattr(task, "actual_start_time", None)
                act_e_d = getattr(task, "actual_end_date", None)
                act_e_t = getattr(task, "actual_end_time", None)

                if act_s_d:
                    actual_start_dt = combine_date_time(act_s_d, act_s_t or "08:00")
                    if act_e_d:
                        actual_finish_dt = combine_date_time(act_e_d, act_e_t or "17:00")
                    elif act_e_t and task.status == TaskStatus.COMPLETED:
                        actual_finish_dt = combine_date_time(act_s_d, act_e_t)
                    else:
                        actual_finish_dt = None

                    if actual_finish_dt is not None:
                        actual_visual_end_dt = actual_finish_dt
                    else:
                        cur_now = get_current_datetime()
                        actual_visual_end_dt = max(actual_start_dt, cur_now)
                else:
                    actual_start_dt = None
                    actual_visual_end_dt = None

            if (
                actual_start_dt is not None
                and actual_visual_end_dt is not None
                and actual_visual_end_dt >= actual_start_dt
            ):
                if self.zoom_mode == ZoomLevel.HOURLY:
                    # Render only the portion intersecting the
                    # currently visible anchor day.
                    day_start = datetime.combine(
                        self.anchor_date,
                        datetime.min.time(),
                    )
                    day_end = day_start + timedelta(days=1)

                    seg_start = max(
                        actual_start_dt,
                        day_start,
                    )
                    seg_end = min(
                        actual_visual_end_dt,
                        day_end,
                    )

                    if seg_end > seg_start:
                        from todo_bird_app.utils.time_math import (
                            minutes_to_x,
                            duration_to_width,
                        )

                        start_m = (
                            seg_start.hour * 60
                            + seg_start.minute
                        )
                        end_m = (
                            1440
                            if seg_end >= day_end
                            else (
                                seg_end.hour * 60
                                + seg_end.minute
                            )
                        )

                        if end_m > start_m:
                            cw = float(self.columns[0].width)
                            actual_abs_x = minutes_to_x(
                                start_m,
                                cw,
                            )
                            actual_w = max(
                                8.0,
                                duration_to_width(
                                    end_m - start_m,
                                    cw,
                                ),
                            )

                            task.gantt_summary_actual_visible = True
                            task.gantt_summary_actual_x_offset = (
                                actual_abs_x - col_x_start
                            )
                            task.gantt_summary_actual_width = (
                                actual_w
                            )

                else:
                    a_start_date = actual_start_dt.date()
                    a_end_date = actual_visual_end_dt.date()

                    if TimescaleEngine.intersects_visible_range(
                        a_start_date,
                        a_end_date,
                        visible_start,
                        visible_end,
                    ):
                        actual_abs_x = TimescaleEngine.date_to_x(
                            a_start_date,
                            self.columns,
                        )
                        actual_abs_end = TimescaleEngine.date_to_x(
                            a_end_date + timedelta(days=1),
                            self.columns,
                        )

                        actual_w = max(
                            8.0,
                            actual_abs_end - actual_abs_x,
                        )

                        task.gantt_summary_actual_visible = True
                        task.gantt_summary_actual_x_offset = (
                            actual_abs_x - col_x_start
                        )
                        task.gantt_summary_actual_width = actual_w

            timing_status = TimingStatus.ON_TRACK
            timing_delay_minutes = 0
            timing_delay_percentage = 0.0

            if self.delay_engine:
                (
                    timing_status,
                    timing_delay_minutes,
                    timing_delay_percentage,
                ) = self.delay_engine.analyze_task_timing(
                    task
                )

            task.gantt_timing_delay_minutes = (
                timing_delay_minutes
            )
            task.gantt_timing_delay_percentage = (
                timing_delay_percentage
            )

            proj_name = self.projects_map.get(task.project_id, "Inbox")
            item = GanttTaskItem(
                task, row=row_idx, col_start=start_col_index, duration_cols=dur_cols,
                col_width=self.columns[0].width, color_profile=colors, timing_status=timing_status,
                project_name=proj_name,
                row_height=self.row_height,
                show_actual_bars=self.show_actual_bars,
                show_baseline=self.show_baseline,
                bar_style=self.bar_style,
                zoom_mode=self.zoom_mode.value,
                anchor_date=self.anchor_date,
                font_family=base_g_font.family(),
            )
            task.gantt_bar_left_x = float(col_x_start)
            task.gantt_bar_right_x = float(
                col_x_start
                + float(getattr(item, "bar_pixel_width", bar_width))
            )
            item.setPos(col_x_start, self.header_height + row_idx * self.row_height)
            item.setZValue(Z_TASK)
            self.scene.addItem(item)

            if task.id is not None:
                self._rendered_task_items[
                    int(task.id)
                ] = item

            rendered_tasks_list.append(task)
            row_idx += 1

        self._draw_dependency_arrows()
        self.visible_tasks_changed.emit(rendered_tasks_list)
