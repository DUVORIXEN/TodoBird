from PySide6.QtWidgets import (
    QGraphicsItemGroup, QGraphicsRectItem, QGraphicsSimpleTextItem,
    QGraphicsPolygonItem, QGraphicsItem, QGraphicsPathItem, QApplication,
    QGraphicsLineItem
)
from PySide6.QtGui import (
    QBrush, QPen, QColor, QPolygonF, QFont,
    QPainterPath, QLinearGradient
)
from PySide6.QtCore import QRectF, QPointF, Qt
from datetime import date, datetime

from todo_bird_app.models.task import Task, TaskStatus, TaskPriority
from todo_bird_app.controllers.delay_engine import TimingStatus
from todo_bird_app.services.cpm_scheduling_service import format_float_duration, format_cpm_datetime

class GanttTaskItem(QGraphicsItemGroup):
    """
    Graphics item representing a task on the Gantt timeline.
    Displays dynamic status colors, dual Plan vs Actual bars, and rich tooltips.
    """
    def __init__(
        self,
        task: Task,
        row: int,
        col_start: float,
        duration_cols: float,
        col_width: int,
        color_profile: dict,
        timing_status: TimingStatus = TimingStatus.COMPLETED_ON_TIME,
        project_name: str = "Inbox",
        row_height: int = 40,
        show_actual_bars: bool = True,
        show_baseline: bool = True,
        bar_style: str = "rounded",
        zoom_mode: str = "daily",
        anchor_date=None,
        font_family: str = "",
        parent=None
    ):
        super().__init__(parent)
        self.task = task
        self.font_family = font_family
        self.row = row
        self.col_start = col_start
        self.duration_cols = max(duration_cols, 0.5)
        self.col_width = col_width
        self.color_profile = color_profile
        self.timing_status = timing_status
        self.project_name = project_name
        self.row_height = row_height
        self.show_actual_bars = show_actual_bars
        self.show_baseline = show_baseline
        self.bar_style = (
            bar_style
            or "rounded"
        )
        self.zoom_mode = str(zoom_mode or "daily").lower()
        self.anchor_date = anchor_date

        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemIsMovable, False)
        self.setAcceptHoverEvents(True)

        self._render_item()
        self._set_rich_tooltip()

    def _get_status_color(self) -> str:
        cp = self.color_profile
        if self.task.status == TaskStatus.CANCELLED:
            return cp.get("cancelled_color", "#6B7280")
        if self.task.status == TaskStatus.INBOX and "paused" in self.task.tags:
            return cp.get("paused_color", "#8B5CF6")

        status_map = {
            TimingStatus.ON_TRACK:
                cp.get("planned_color", "#3584E4"),
            TimingStatus.AT_RISK:
                cp.get("slight_delay_color", "#F59E0B"),
            TimingStatus.OVERDUE:
                cp.get("severe_delay_color", "#EF4444"),
            TimingStatus.COMPLETED_BEFORE_TIME: cp.get("completed_early_color", "#065F46"),
            TimingStatus.COMPLETED_ON_TIME: cp.get("completed_ontime_color", "#10B981"),
            TimingStatus.SLIGHT_DELAY: cp.get("slight_delay_color", "#F59E0B"),
            TimingStatus.MODERATE_DELAY: cp.get("moderate_delay_color", "#F97316"),
            TimingStatus.SEVERE_DELAY: cp.get("severe_delay_color", "#EF4444"),
            TimingStatus.VERY_SEVERE_DELAY: cp.get("very_severe_delay_color", "#991B1B"),
        }
        return status_map.get(self.timing_status, cp.get("actual_color", "#10B981"))

    def _make_bar_shape(
        self,
        x,
        y,
        w,
        h,
        color,
        border_pen,
    ):
        """
        Premium selectable Gantt-bar design factory.
        """
        style = (
            self.bar_style
            or "rounded"
        ).lower()

        c = QColor(color)

        if style == "arrow":
            tip = min(
                18.0,
                max(8.0, w * 0.16),
            )
            poly = QPolygonF([
                QPointF(x, y),
                QPointF(x + w - tip, y),
                QPointF(x + w, y + h / 2),
                QPointF(x + w - tip, y + h),
                QPointF(x, y + h),
            ])
            item = QGraphicsPolygonItem(poly)
            item.setBrush(QBrush(c))
            item.setPen(border_pen)
            return item

        if style == "bevel":
            bevel = min(
                8.0,
                max(4.0, h * 0.30),
            )
            poly = QPolygonF([
                QPointF(x + bevel, y),
                QPointF(x + w - bevel, y),
                QPointF(x + w, y + bevel),
                QPointF(x + w, y + h - bevel),
                QPointF(x + w - bevel, y + h),
                QPointF(x + bevel, y + h),
                QPointF(x, y + h - bevel),
                QPointF(x, y + bevel),
            ])
            item = QGraphicsPolygonItem(poly)
            item.setBrush(QBrush(c))
            item.setPen(border_pen)
            return item

        path = QPainterPath()

        radius = (
            h / 2
            if style == "capsule"
            else 6.0
        )

        path.addRoundedRect(
            QRectF(x, y, w, h),
            radius,
            radius,
        )

        item = QGraphicsPathItem(path)

        if style in (
            "glass",
            "3d",
        ):
            grad = QLinearGradient(
                x,
                y,
                x,
                y + h,
            )

            lighter = QColor(c)
            lighter = lighter.lighter(
                145 if style == "glass" else 125
            )

            darker = QColor(c)
            darker = darker.darker(
                125
            )

            grad.setColorAt(
                0.0,
                lighter,
            )
            grad.setColorAt(
                0.50,
                c,
            )
            grad.setColorAt(
                1.0,
                darker,
            )

            item.setBrush(
                QBrush(grad)
            )
        else:
            item.setBrush(
                QBrush(c)
            )

        if style == "3d":
            pen = QPen(
                QColor(c).lighter(160),
                2.0,
            )
            item.setPen(pen)
        else:
            item.setPen(border_pen)

        return item

    def _render_item(self):
        cp = self.color_profile
        if hasattr(cp, "colors"):
            cp = cp.colors
        if not isinstance(cp, dict):
            cp = {}
        x = 0.0
        y = 6.0
        w = max(self.duration_cols * self.col_width, 36.0)
        h = self.row_height - 12

        # Chart interaction authority uses this exact rendered width
        # for left/right resize-edge hit testing.
        self.bar_pixel_width = float(w)
        # Match the chart's dynamic edge geometry so item metadata
        # agrees with the hit-testing authority: shrink the handle
        # for short bars, never below 6px.
        self.resize_handle_width = float(min(14.0, max(6.0, w * 0.25)))

        is_critical = (self.task.priority == TaskPriority.URGENT) or ("critical" in self.task.tags)
        # Phase 1D:
        # Milestone is a BUSINESS SEMANTIC, never a pixel-width heuristic.
        #
        # In Hourly mode a perfectly valid 15–30 minute task can have
        # duration_cols <= 0.5. Treating that as a milestone makes its
        # normal Planned bar disappear and replaces it with a diamond.
        is_milestone = bool(
            getattr(
                self.task,
                "gantt_is_milestone",
                False,
            )
            or (
                "milestone"
                in (
                    self.task.tags
                    or []
                )
            )
        )

        # Phase 1D professional WBS summary semantics.
        # Summary schedule geometry is derived from descendants and therefore
        # must never expose leaf-style editing affordances.
        is_summary = bool(
            getattr(self.task, "gantt_is_summary", False)
        )
        is_read_only = bool(
            getattr(self.task, "gantt_read_only", False)
            or is_summary
        )

        border_pen = QPen(QColor(cp.get("critical_color", "#DC2626")), 2) if is_critical else QPen(Qt.NoPen)

        # 1. Milestone Diamond Rendering
        if is_milestone:
            poly = QPolygonF([
                QPointF(x + w / 2, y),
                QPointF(x + w, y + h / 2),
                QPointF(x + w / 2, y + h),
                QPointF(x, y + h / 2),
            ])
            diamond = QGraphicsPolygonItem(poly)
            diamond.setBrush(QBrush(QColor(cp.get("milestone_color", "#E95420"))))
            diamond.setPen(QPen(QColor("#FFFFFF"), 1))
            self.addToGroup(diamond)
        else:
            # 2. Dual Bar Rendering (Plan vs Actual)
            execution_statuses = {
                TaskStatus.IN_PROGRESS,
                TaskStatus.BLOCKED,
                TaskStatus.COMPLETED,
                TaskStatus.DELAYED,
            }

            has_actual_time = bool(
                self.task.actual_start_time
                and ":" in str(self.task.actual_start_time)
            )

            has_planned_today = True
            has_actual_today = False
            if self.zoom_mode == "hourly":
                p_iso = getattr(self.task, "planned_date", None)
                d_iso = getattr(self.task, "due_date", None) or p_iso
                s_iso = self.anchor_date.strftime("%Y-%m-%d") if self.anchor_date else None
                if hasattr(
                    self.task,
                    "gantt_hourly_has_planned_segment",
                ):
                    # Chart is the single Hourly geometry/date authority.
                    has_planned_today = bool(
                        getattr(
                            self.task,
                            "gantt_hourly_has_planned_segment",
                            False,
                        )
                    )

                elif s_iso:
                    # Compatibility fallback for standalone item tests.
                    if p_iso and d_iso:
                        has_planned_today = (
                            p_iso <= s_iso <= d_iso
                        )
                    elif p_iso:
                        has_planned_today = (
                            p_iso == s_iso
                        )
                    elif d_iso:
                        has_planned_today = (
                            d_iso == s_iso
                        )
                    else:
                        has_planned_today = False

                act_s_d = getattr(self.task, "actual_start_date", None)
                act_e_d = getattr(self.task, "actual_end_date", None) or act_s_d
                if act_s_d and self.anchor_date:
                    if act_e_d:
                        has_actual_today = (act_s_d <= s_iso <= act_e_d)
                    else:
                        has_actual_today = (act_s_d == s_iso)
                elif has_actual_time:
                    # Legacy fallback if actual date was not stamped
                    if p_iso and s_iso:
                        has_actual_today = (p_iso == s_iso)
                    else:
                        has_actual_today = True
            else:
                has_actual_today = bool(has_actual_time or int(self.task.actual_duration or 0) > 0)

            self.has_planned_today = has_planned_today
            self.has_actual_today = has_actual_today

            has_actual_execution = (
                (has_actual_today and (has_actual_time or int(self.task.actual_duration or 0) > 0 or self.task.status in execution_statuses))
                if self.zoom_mode == "hourly"
                else (
                    has_actual_time
                    or self.task.status in execution_statuses
                    or int(self.task.progress or 0) > 0
                    or int(self.task.actual_duration or 0) > 0
                )
            )

            # A task can carry schedule-health information before
            # execution begins. This is NOT actual work; it is the
            # lower Health lane.
            has_health_warning = (
                self.task.status
                not in (
                    TaskStatus.COMPLETED,
                    TaskStatus.CANCELLED,
                )
                and self.timing_status
                in (
                    TimingStatus.AT_RISK,
                    TimingStatus.OVERDUE,
                )
            )

            summary_actual_visible = bool(
                getattr(
                    self.task,
                    "gantt_summary_actual_visible",
                    False,
                )
            )

            show_execution_lane = (
                self.show_actual_bars
                and (
                    summary_actual_visible
                    or (
                        (not is_summary)
                        and (
                            has_actual_execution
                            or has_health_warning
                        )
                    )
                )
            )

            if summary_actual_visible:
                # Explicit Phase1C-derived Actual envelope.
                # Prevent all legacy inference from progress/effort.
                has_actual_execution = True
                has_health_warning = False

            half_h = (
                (h - 2) / 2
                if show_execution_lane
                else h
            )

            # Top Bar: Planned Timeline
            # -------------------------------------------------
            # PLANNED BASELINE
            #
            # The planned bar is the approved schedule baseline.
            # It must NEVER change color because execution becomes
            # early / at-risk / overdue.
            # -------------------------------------------------
            planned_color = cp.get(
                "planned_color",
                "#3584E4",
            )

            planned_pen = border_pen

            if is_summary:
                summary_border = QColor(planned_color)
                summary_border = summary_border.lighter(150)
                planned_pen = QPen(summary_border, 2.0)
                planned_pen.setCosmetic(True)

            has_schedule_conflict = bool(
                getattr(
                    self.task,
                    "gantt_overlap",
                    False,
                )
            )

            if has_schedule_conflict:
                # Conflict changes the OUTLINE only.
                # Baseline fill remains the user's chosen Plan Color.
                planned_pen = QPen(
                    QColor("#DC2626"),
                    3.0,
                )

            if has_planned_today:
                planned_bar = self._make_bar_shape(
                    x,
                    y,
                    w,
                    half_h,
                    planned_color,
                    planned_pen,
                )

                self.addToGroup(
                    planned_bar
                )

                # -------------------------------------------------
                # PHASE 1D SUMMARY PROGRESS INDICATOR
                #
                # Thin, style-independent progress line below the
                # derived parent schedule span.
                # -------------------------------------------------
                if is_summary:
                    summary_progress = max(
                        0,
                        min(
                            100,
                            int(
                                getattr(
                                    self.task,
                                    "gantt_rollup_progress",
                                    self.task.progress,
                                )
                                or 0
                            ),
                        ),
                    )

                    if summary_progress > 0:
                        progress_w = max(
                            2.0,
                            w * summary_progress / 100.0,
                        )

                        progress_color = QColor(
                            cp.get(
                                "actual_color",
                                "#10B981",
                            )
                        )

                        progress_line = QGraphicsRectItem(
                            x,
                            y + half_h - 3,
                            progress_w,
                            3,
                        )
                        progress_line.setBrush(
                            QBrush(progress_color)
                        )
                        progress_line.setPen(
                            QPen(Qt.NoPen)
                        )
                        progress_line.setZValue(4.0)
                        progress_line.setToolTip(
                            f"Summary progress: {summary_progress}%"
                        )
                        self.addToGroup(
                            progress_line
                        )

                # -------------------------------------------------
                # INTERACTIVE RESIZE EDGE HANDLES
                #
                # They are deliberately subtle. Mouse interaction itself
                # is owned by GanttChartWidget, preserving one scheduling
                # authority instead of putting logic in graphics children.
                # -------------------------------------------------
                handle_color = QColor(
                    "#FFFFFF"
                )
                handle_color.setAlpha(
                    185
                )

                left_handle = QGraphicsRectItem(
                    x - 4,
                    y + 2,
                    8,
                    max(
                        6,
                        half_h - 4,
                    ),
                )
                left_handle.setBrush(
                    QBrush(handle_color)
                )
                left_handle.setPen(
                    QPen(
                        Qt.NoPen
                    )
                )
                left_handle.setZValue(
                    5.0
                )
                left_handle.setVisible(
                    not is_read_only
                )
                self.addToGroup(
                    left_handle
                )

                right_handle = QGraphicsRectItem(
                    x + w - 4,
                    y + 2,
                    8,
                    max(
                        6,
                        half_h - 4,
                    ),
                )
                right_handle.setBrush(
                    QBrush(handle_color)
                )
                right_handle.setPen(
                    QPen(
                        Qt.NoPen
                    )
                )
                right_handle.setZValue(
                    5.0
                )
                right_handle.setVisible(
                    not is_read_only
                )
                self.addToGroup(
                    right_handle
                )

            # -------------------------------------------------
            # DEPENDENCY / CRITICAL-PATH INDICATORS
            # -------------------------------------------------
            if bool(
                getattr(
                    self.task,
                    "gantt_dependency_cycle",
                    False,
                )
            ):
                dep_marker = QGraphicsSimpleTextItem(
                    "⟳ CYCLE"
                )
                dep_marker.setBrush(
                    QBrush(
                        QColor(
                            "#DC2626"
                        )
                    )
                )
                dep_marker.setPos(
                    x + 4,
                    y - 18,
                )
                dep_marker.setToolTip(
                    "Dependency cycle detected. "
                    "Automatic successor shifting is disabled "
                    "for this cycle."
                )
                self.addToGroup(
                    dep_marker
                )

            elif bool(
                getattr(
                    self.task,
                    "gantt_dependency_violation",
                    False,
                )
            ):
                dep_marker = QGraphicsSimpleTextItem(
                    "⚠ DEP"
                )
                dep_marker.setBrush(
                    QBrush(
                        QColor(
                            "#F97316"
                        )
                    )
                )
                dep_marker.setPos(
                    x + 4,
                    y - 18,
                )
                dep_marker.setToolTip(
                    "Finish→Start dependency timing violation."
                )
                self.addToGroup(
                    dep_marker
                )

            is_critical = bool(getattr(self.task, "cpm_is_critical", getattr(self.task, "gantt_critical_path", False)))
            is_cycle = bool(getattr(self.task, "gantt_dependency_cycle", False)) or ("DEPENDENCY_CYCLE" in getattr(self.task, "cpm_diagnostics", []))

            if is_critical and not is_cycle:
                cp_marker = QGraphicsSimpleTextItem(
                    "◆ CP"
                )
                cp_marker.setBrush(
                    QBrush(
                        QColor(
                            "#DC2626"
                        )
                    )
                )
                cp_marker.setPos(
                    x + max(
                        30,
                        w - 42,
                    ),
                    y + half_h + 1,
                )
                cp_marker.setToolTip(
                    "Critical Path — zero total float on project critical path."
                )
                self.addToGroup(
                    cp_marker
                )

            if has_schedule_conflict:
                conflict_marker = (
                    QGraphicsSimpleTextItem(
                        "🔀"
                    )
                )

                conflict_font = QFont(
                    self.font_family or QApplication.font().family(),
                    10,
                )

                conflict_font.setBold(
                    True
                )

                conflict_marker.setFont(
                    conflict_font
                )

                conflict_marker.setBrush(
                    QBrush(
                        QColor(
                            "#DC2626"
                        )
                    )
                )

                conflict_marker.setPos(
                    max(
                        x + 2,
                        x + w - 20,
                    ),
                    y - 17,
                )

                conflict_marker.setToolTip(
                    "Schedule conflict: this task overlaps "
                    "another unfinished task on the same date/time."
                )

                self.addToGroup(
                    conflict_marker
                )

            # -------------------------------------------------
            # Phase 2E: CONSTRAINT & DEADLINE MARKERS
            # -------------------------------------------------
            c_type = getattr(self.task, "constraint_type", "ASAP") or "ASAP"
            c_dt = getattr(self.task, "constraint_datetime", None)
            if c_type not in ("ASAP", "ALAP") and c_dt:
                const_marker = QGraphicsSimpleTextItem("🔒")
                const_marker.setBrush(QBrush(QColor("#6366F1")))
                const_marker.setPos(x - 2, y - 16)
                const_marker.setToolTip(f"Constraint: {c_type} ({c_dt})")
                self.addToGroup(const_marker)

            d_dt = getattr(self.task, "deadline_datetime", None)
            if d_dt:
                dead_marker = QGraphicsSimpleTextItem("⚑")
                dead_marker.setBrush(QBrush(QColor("#EF4444")))
                dead_marker.setPos(x + w - 12, y - 16)
                dead_marker.setToolTip(f"Target Deadline: {d_dt}")
                self.addToGroup(dead_marker)

            # -------------------------------------------------
            # LOWER LANE = ACTUAL EXECUTION OR SCHEDULE HEALTH
            #
            # Planned baseline above remains untouched.
            # -------------------------------------------------
            if show_execution_lane:
                lower_y = y + half_h + 2

                # -----------------------------------------
                # HEALTH LANE BEFORE EXECUTION
                # -----------------------------------------
                if (
                    has_health_warning
                    and not has_actual_execution
                ):
                    lower_bg = QGraphicsRectItem(
                        x,
                        lower_y,
                        w,
                        half_h,
                    )
                    lower_bg.setBrush(
                        QBrush(
                            QColor(
                                255,
                                255,
                                255,
                                20,
                            )
                        )
                    )
                    lower_bg.setPen(Qt.NoPen)
                    self.addToGroup(lower_bg)

                    if (
                        self.timing_status
                        == TimingStatus.OVERDUE
                    ):
                        lane_color = cp.get(
                            "severe_delay_color",
                            "#EF4444",
                        )

                        lane_pen = QPen(
                            QColor(
                                cp.get(
                                    "critical_color",
                                    "#DC2626",
                                )
                            ),
                            3.0,
                        )

                    else:
                        lane_color = cp.get(
                            "slight_delay_color",
                            "#F59E0B",
                        )

                        lane_pen = QPen(
                            QColor(lane_color),
                            2.0,
                        )

                    health_bar = self._make_bar_shape(
                        x,
                        lower_y,
                        w,
                        half_h,
                        lane_color,
                        lane_pen,
                    )

                    self.addToGroup(
                        health_bar
                    )

                # -----------------------------------------
                # ACTUAL EXECUTION LANE
                # -----------------------------------------
                elif has_actual_execution:
                    act_x = x
                    act_w = 0.0

                    if summary_actual_visible:
                        # Geometry is relative to the parent planned item's
                        # scene position and was calculated by GanttChartWidget.
                        act_x = x + float(
                            getattr(
                                self.task,
                                "gantt_summary_actual_x_offset",
                                0.0,
                            )
                            or 0.0
                        )
                        act_w = max(
                            8.0,
                            float(
                                getattr(
                                    self.task,
                                    "gantt_summary_actual_width",
                                    0.0,
                                )
                                or 0.0
                            ),
                        )

                    elif self.zoom_mode == "hourly":
                        from todo_bird_app.utils.time_math import (
                            segment_interval_by_day,
                            parse_hhmm,
                            minutes_to_x,
                            duration_to_width,
                        )

                        raw_act_s = getattr(self.task, "actual_start_date", None)
                        act_s_d = str(raw_act_s).strip() if raw_act_s and str(raw_act_s).strip() else (str(getattr(self.task, "planned_date", "")).strip() or None)
                        raw_act_e = getattr(self.task, "actual_end_date", None)
                        act_e_d = str(raw_act_e).strip() if raw_act_e and str(raw_act_e).strip() else (date.today().strftime("%Y-%m-%d") if act_s_d and act_s_d <= date.today().strftime("%Y-%m-%d") else act_s_d)

                        act_end_t = self.task.actual_end_time
                        if not act_end_t and raw_act_e is None and act_s_d:
                            from datetime import datetime
                            act_end_t = datetime.now().strftime("%H:%M")

                        segments = segment_interval_by_day(
                            start_date=act_s_d,
                            start_time=self.task.actual_start_time,
                            end_date=act_e_d,
                            end_time=act_end_t,
                        )
                        seg_today = next((s for s in segments if s.date == self.anchor_date), None)

                        if seg_today:
                            act_start_m = seg_today.start_minute
                            act_end_m = seg_today.end_minute_exclusive
                        elif self.task.actual_start_time is not None:
                            act_start_m = parse_hhmm(self.task.actual_start_time)
                            act_end_m = parse_hhmm(act_end_t) if act_end_t else None
                        else:
                            act_start_m, act_end_m = None, None

                        if act_start_m is not None:
                            p_iso = getattr(self.task, "planned_date", None)
                            base_start_m = 8 * 60
                            if p_iso == s_iso and self.task.planned_start_time is not None:
                                p_min = parse_hhmm(self.task.planned_start_time)
                                if p_min is not None:
                                    base_start_m = p_min
                            elif seg_today:
                                base_start_m = seg_today.start_minute
                            elif self.task.actual_start_time is not None:
                                a_min = parse_hhmm(self.task.actual_start_time)
                                if a_min is not None:
                                    base_start_m = a_min

                            if (act_end_m is None or act_end_m <= act_start_m) and act_s_d:
                                from datetime import datetime
                                now = datetime.now()
                                act_dur = int(getattr(self.task, "actual_duration", 0) or 0) or 15
                                act_end_m = max(act_start_m + act_dur, now.hour * 60 + now.minute)
                                if act_end_m <= act_start_m:
                                    act_end_m = act_start_m + act_dur

                            if act_end_m is not None and act_end_m > act_start_m:
                                col_w = float(self.col_width)
                                act_x = x + minutes_to_x(act_start_m - base_start_m, col_w)
                                act_w = max(16.0, duration_to_width(act_end_m - act_start_m, col_w))

                    # Execution health is authoritative here.
                    if (
                        self.timing_status
                        == TimingStatus.OVERDUE
                    ):
                        act_color = cp.get(
                            "severe_delay_color",
                            "#EF4444",
                        )

                    elif (
                        self.timing_status
                        == TimingStatus.AT_RISK
                    ):
                        act_color = cp.get(
                            "slight_delay_color",
                            "#F59E0B",
                        )

                    elif (
                        self.task.status
                        == TaskStatus.BLOCKED
                    ):
                        act_color = cp.get(
                            "paused_color",
                            "#8B5CF6",
                        )

                    elif (
                        self.timing_status
                        == TimingStatus.COMPLETED_BEFORE_TIME
                    ):
                        act_color = cp.get(
                            "completed_early_color",
                            "#065F46",
                        )

                    elif (
                        self.timing_status
                        == TimingStatus.COMPLETED_ON_TIME
                    ):
                        act_color = cp.get(
                            "completed_ontime_color",
                            "#10B981",
                        )

                    elif (
                        self.timing_status
                        == TimingStatus.SLIGHT_DELAY
                    ):
                        act_color = cp.get(
                            "slight_delay_color",
                            "#F59E0B",
                        )

                    elif (
                        self.timing_status
                        == TimingStatus.MODERATE_DELAY
                    ):
                        act_color = cp.get(
                            "moderate_delay_color",
                            "#F97316",
                        )

                    elif (
                        self.timing_status
                        == TimingStatus.SEVERE_DELAY
                    ):
                        act_color = cp.get(
                            "severe_delay_color",
                            "#EF4444",
                        )

                    elif (
                        self.timing_status
                        == TimingStatus.VERY_SEVERE_DELAY
                    ):
                        act_color = cp.get(
                            "very_severe_delay_color",
                            "#991B1B",
                        )

                    else:
                        act_color = cp.get(
                            "actual_color",
                            "#10B981",
                        )

                    actual_pen = QPen(
                        QColor(act_color),
                        1.0,
                    )

                    if self.timing_status in (
                        TimingStatus.OVERDUE,
                        TimingStatus.SEVERE_DELAY,
                        TimingStatus.VERY_SEVERE_DELAY,
                    ):
                        actual_pen = QPen(
                            QColor(
                                cp.get(
                                    "critical_color",
                                    "#DC2626",
                                )
                            ),
                            3.0,
                        )

                    elif self.timing_status == TimingStatus.EARLY_START:
                        act_color = "#059669"
                        actual_pen = QPen(
                            QColor("#10B981"),
                            3.5,
                        )

                    elif self.timing_status == TimingStatus.DELAYED_START:
                        act_color = "#D97706"
                        actual_pen = QPen(
                            QColor("#F59E0B"),
                            2.5,
                        )

                    elif self.timing_status in (
                        TimingStatus.COMPLETED_BEFORE_TIME,
                        TimingStatus.COMPLETED_ON_TIME,
                    ):
                        actual_pen = QPen(
                            QColor(act_color),
                            3.0,
                        )

                    is_open_actual = bool(
                        (getattr(self.task, "actual_start_date", None) or getattr(self.task, "actual_start_time", None) or int(getattr(self.task, "actual_duration", 0) or 0) > 0)
                        and not getattr(self.task, "actual_end_date", None)
                        and not (getattr(self.task, "actual_end_time", None) and self.task.status == TaskStatus.COMPLETED)
                        and self.task.status != TaskStatus.COMPLETED
                    )

                    if is_open_actual:
                        actual_pen = QPen(
                            QColor(act_color),
                            2.0,
                            Qt.DashLine,
                        )

                    # Translucent track covering full actual & planned extent
                    track_x = min(x, act_x)
                    track_right = max(x + w, act_x + act_w)
                    track_w = max(w, track_right - track_x)

                    lower_bg = QGraphicsRectItem(
                        track_x,
                        lower_y,
                        track_w,
                        half_h,
                    )
                    lower_bg.setBrush(
                        QBrush(
                            QColor(
                                255,
                                255,
                                255,
                                20,
                            )
                        )
                    )
                    lower_bg.setPen(Qt.NoPen)
                    self.addToGroup(lower_bg)

                    if act_w > 0:
                        actual_bar = self._make_bar_shape(
                            act_x,
                            lower_y,
                            act_w,
                            half_h,
                            act_color,
                            actual_pen,
                        )
                        actual_bar.setZValue(1.0)

                        if is_open_actual:
                            actual_bar.setToolTip("Actual Execution — In Progress")

                        self.addToGroup(
                            actual_bar
                        )

            # -------------------------------------------------
            # Phase 2D: FROZEN BASELINE 1 BAR RENDERING
            #
            # Renders a thin, non-interactive snapshot bar underneath
            # the current working schedule bar when show_baseline is true.
            # -------------------------------------------------
            has_baseline = bool(
                getattr(self.task, "baseline_start", None)
                or getattr(self.task, "has_baseline", False)
                or getattr(self.task, "gantt_has_baseline", False)
            )

            if self.show_baseline and has_baseline:
                baseline_y = y + h - 3.0
                baseline_h = 3.0
                b_color = QColor(cp.get("baseline_color", "#94A3B8"))
                b_color.setAlpha(180)

                baseline_bar = QGraphicsRectItem(
                    x,
                    baseline_y,
                    w,
                    baseline_h,
                )
                baseline_bar.setBrush(QBrush(b_color))
                baseline_bar.setPen(QPen(Qt.NoPen))
                baseline_bar.setZValue(2.0)
                baseline_bar.setToolTip("Approved Baseline 1 schedule snapshot (frozen)")
                self.addToGroup(baseline_bar)

        # Premium Program-Management Status Label
        status_visuals = {
            TaskStatus.INBOX: ("○", "NOT STARTED"),
            TaskStatus.PLANNED: ("🗓", "PLANNED"),
            TaskStatus.IN_PROGRESS: ("▶", "IN PROGRESS"),
            TaskStatus.BLOCKED: ("⛔", "BLOCKED"),
            TaskStatus.DELAYED: ("⚠", "DELAYED"),
            TaskStatus.MOVED: ("↪", "MOVED"),
            TaskStatus.COMPLETED: ("✓", "COMPLETED"),
            TaskStatus.CANCELLED: ("✕", "CANCELLED"),
        }

        status_icon, status_text = status_visuals.get(
            self.task.status,
            ("○", str(getattr(self.task.status, "value", self.task.status)).upper())
        )

        live_delay = int(
            getattr(
                self.task,
                "gantt_timing_delay_minutes",
                0,
            )
            or 0
        )

        def compact_minutes(minutes):
            minutes = abs(int(minutes))
            hours = minutes // 60
            mins = minutes % 60

            if hours and mins:
                return f"{hours}h {mins}m"
            if hours:
                return f"{hours}h"
            return f"{mins}m"

        if self.timing_status == TimingStatus.OVERDUE:
            status_icon = "🔴"
            status_text = (
                "OVERDUE "
                + compact_minutes(live_delay)
            )

        elif self.timing_status == TimingStatus.AT_RISK:
            status_icon = "🟠"
            status_text = "AT RISK"

        elif (
            self.timing_status
            == TimingStatus.COMPLETED_BEFORE_TIME
            and self.task.status
            == TaskStatus.COMPLETED
        ):
            status_icon = "🏆"
            status_text = "COMPLETED EARLY"

        elif (
            self.timing_status
            == TimingStatus.COMPLETED_ON_TIME
            and self.task.status
            == TaskStatus.COMPLETED
        ):
            status_icon = "✓"
            status_text = "COMPLETED ON TIME"

        item_type = getattr(self.task, "gantt_item_type", "task")
        depth = int(getattr(self.task, "gantt_depth", 0) or 0)

        if item_type == "task":
            hierarchy_icon = "📌"
            display_title = self.task.title
        else:
            hierarchy_icon = "↳"
            clean_title = self.task.title.replace("↳", "").strip()
            display_title = ("   " * max(0, depth - 1)) + clean_title

        # Floating sticky labels, status pill, and progress badge removed.
        # This information will be displayed in the synchronized QTreeView left pane.

    def _set_rich_tooltip(self):
        t = self.task
        depth = int(getattr(t, "gantt_depth", 0) or 0)
        item_type = getattr(t, "gantt_item_type", "task")

        if item_type == "task":
            hierarchy_text = "Main Task"
            hierarchy_icon = "📌"
        else:
            hierarchy_text = (
                "Subtask"
                if depth == 1
                else f"Level {depth} Subtask"
            )
            hierarchy_icon = "↳"

        cpm_tf = getattr(t, "cpm_total_float", None)
        cpm_ff = getattr(t, "cpm_free_float", None)
        cpm_es = getattr(t, "cpm_earliest_start", None)
        cpm_ef = getattr(t, "cpm_earliest_finish", None)
        cpm_ls = getattr(t, "cpm_latest_start", None)
        cpm_lf = getattr(t, "cpm_latest_finish", None)
        cpm_crit = bool(getattr(t, "cpm_is_critical", getattr(t, "gantt_critical_path", False)))
        is_cycle_node = bool(getattr(t, "gantt_dependency_cycle", False)) or ("DEPENDENCY_CYCLE" in getattr(t, "cpm_diagnostics", []))
        forecast_start = getattr(t, "gantt_planned_start", None) or cpm_es
        forecast_finish = getattr(t, "gantt_planned_finish", None) or cpm_ef
        dep_summary = str(getattr(t, "gantt_dependency_summary", "") or "").strip()
        dep_line = f"<br/>🔗 Dependencies: {dep_summary}" if dep_summary else ""

        if is_cycle_node:
            cpm_block = "📊 CPM: <i>Not analyzed (Dependency Cycle)</i>"
        elif cpm_tf is not None:
            critical_path_text = "<b>YES</b>" if cpm_crit else "No"
            cpm_block = (
                f"📊 Current Forecast Start: {format_cpm_datetime(forecast_start)}<br/>"
                f"📊 Current Forecast Finish: {format_cpm_datetime(forecast_finish)}<br/>"
                f"🎯 Critical: {'<b>Yes</b>' if cpm_crit else 'No'} | Critical Path: {critical_path_text}<br/>"
                f"⏳ Total Float: {format_float_duration(cpm_tf)} | Free Float: {format_float_duration(cpm_ff)}<br/>"
                f"⏱️ ES: {format_cpm_datetime(cpm_es)} | EF: {format_cpm_datetime(cpm_ef)}<br/>"
                f"⏱️ LS: {format_cpm_datetime(cpm_ls)} | LF: {format_cpm_datetime(cpm_lf)}"
                f"{dep_line}"
            )
        else:
            cpm_block = "📊 CPM: <i>Not analyzed</i>"

        b_start = getattr(t, "baseline_start", None)
        b_finish = getattr(t, "baseline_finish", None)
        b_var = getattr(t, "finish_variance_minutes", getattr(t, "gantt_finish_variance", None))

        if b_start and b_finish:
            from todo_bird_app.services.schedule_variance_service import format_variance_duration
            v_str = format_variance_duration(b_var)
            b_block = f"📐 Baseline 1: {b_start} → {b_finish} (Variance: {v_str})"
        elif getattr(t, "has_baseline", False) or getattr(t, "gantt_has_baseline", False):
            b_block = "📐 Baseline 1: Active"
        else:
            b_block = "📐 Baseline 1: <i>Not Baselined</i>"

        from todo_bird_app.services.execution_performance_service import ExecutionPerformanceService, ExecutionState
        exec_res = ExecutionPerformanceService.analyze_task_execution(t)

        is_open_actual = exec_res.execution_state == ExecutionState.IN_PROGRESS
        if exec_res.execution_state == ExecutionState.NOT_STARTED:
            actual_line = "⌛ Actual: <i>Not Tracked / Not Started</i>"
        elif exec_res.execution_state == ExecutionState.IN_PROGRESS:
            act_s_part = f"{t.actual_start_date or ''} {t.actual_start_time or ''}".strip() or "Started"
            actual_line = (
                f"⌛ Actual: {act_s_part} → <i>In Progress (Active)</i><br/>"
                f"⏱️ Execution Performance: <b>{exec_res.start_variance_display}</b> ({t.actual_duration or 0}m effort logged)"
            )
        else:
            act_s_part = f"{t.actual_start_date or ''} {t.actual_start_time or ''}".strip() or "N/A"
            act_e_part = f"{t.actual_end_date or ''} {t.actual_end_time or ''}".strip() or "N/A"
            actual_line = (
                f"⌛ Actual: {act_s_part} → {act_e_part}<br/>"
                f"⏱️ Execution Performance: <b>{exec_res.finish_variance_display}</b> ({t.actual_duration or 0}m effort logged)"
            )

        diag_block = ""
        if exec_res.diagnostics:
            diag_lines = "<br/>".join(f"• {d}" for d in exec_res.diagnostics[:3])
            diag_block = f"<br/>⚠️ Execution Diagnostics:<br/>{diag_lines}"

        tooltip = (
            f"{hierarchy_icon} <b>{t.title}</b><br/>"
            f"🧭 Level: {hierarchy_text}<br/>"
            f"📁 Project: {self.project_name}<br/>"
            f"🔥 Priority: {t.priority.value}<br/>"
            f"📅 Planned Date: {t.planned_date or 'N/A'}<br/>"
            f"🎯 Due Date: {t.due_date or 'N/A'}<br/>"
            f"⏱️ Planned: {t.planned_start_time or 'N/A'} - "
            f"{t.planned_end_time or 'N/A'} ({t.estimated_duration}m)<br/>"
            f"{actual_line}<br/>"
            f"🚀 Velocity: {getattr(self.timing_status, 'value', str(self.timing_status))}<br/>"
            f"⚠️ Delay: {t.delay_minutes}m "
            f"({t.delay_percentage:.1f}%)<br/>"
            f"💡 Reason: {t.delay_reason or 'None'}<br/>"
            f"📊 Status: {t.status.value} ({t.progress}%)<br/>"
            f"🔀 Schedule Conflict: "
            f"{'YES' if bool(getattr(t, 'gantt_overlap', False)) else 'No'}<br/>"
            f"🔗 Dependency Violation: "
            f"{'YES' if bool(getattr(t, 'gantt_dependency_violation', False)) else 'No'}<br/>"
            f"⟳ Dependency Cycle: "
            f"{'YES' if is_cycle_node else 'No'}<br/>"
            f"{cpm_block}<br/>"
            f"{b_block}"
            f"{diag_block}"
        )
        self.setToolTip(tooltip)
