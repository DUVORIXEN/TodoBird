"""
Reusable Work Effort & Daily Dedication Editor Widget (Batch 3.4 & 3.8)
Shared component ensuring 100% parity across Main Task, Subtask, and Sub-Subtask.
Supports independent Planned Effort and Actual Execution Effort day-by-day tracking.
"""

from datetime import date, datetime, timedelta
from typing import Callable, Dict, Optional, Any
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QSpinBox, QFrame, QMessageBox
)
from PySide6.QtCore import Qt, Signal

from todo_bird_app.utils.working_calendar import (
    calculate_planned_effort,
    get_working_days_between,
    is_working_day,
    parse_date,
    get_configured_working_weekdays,
)
from todo_bird_app.utils.time_math import format_duration_display
from todo_bird_app.services.schedule_calendar_service import (
    CalendarDateStatus,
    ScheduleCalendar,
    classify_calendar_date,
)
from todo_bird_app.utils.qt_cleanup import clear_layout


class WorkEffortEditor(QWidget):
    """
    Unified Work Effort Editor with support for Fixed Daily, Total Effort,
    and Custom by Day allocation with explicit Non-Working Day Overrides
    and day-by-day Actual Execution Effort tracking.
    """
    effortChanged = Signal(int)
    actualEffortChanged = Signal(int)

    def __init__(
        self,
        start_date: Optional[str] = None,
        due_date: Optional[str] = None,
        allocation_mode: str = "fixed_daily",
        daily_dedication_minutes: int = 0,
        planned_effort_minutes: int = 0,
        custom_allocations: Optional[Dict[str, int]] = None,
        custom_actual_allocations: Optional[Dict[str, int]] = None,
        settings_manager: Optional[Any] = None,
        project_calendar_provider: Optional[Callable[[], Any]] = None,
        project_calendar: Optional[Any] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.project_calendar_provider = project_calendar_provider
        self.project_calendar = project_calendar
        self.start_date_str = start_date or date.today().strftime("%Y-%m-%d")
        self.due_date_str = due_date or self.start_date_str
        self._custom_allocations: Dict[str, int] = dict(custom_allocations or {})
        self._custom_actual_allocations: Dict[str, int] = dict(custom_actual_allocations or {})
        self.actual_effort_minutes: int = sum(self._custom_actual_allocations.values())
        self.custom_spinners = {}
        self.custom_actual_spinners = {}
        self._cleaned_up = False
        self._global_working_calendar_connected = False

        self._init_ui()
        self.set_data(
            allocation_mode=allocation_mode,
            daily_dedication_minutes=daily_dedication_minutes,
            planned_effort_minutes=planned_effort_minutes,
            custom_allocations=self._custom_allocations,
            custom_actual_allocations=self._custom_actual_allocations,
        )

        # Connect to global working calendar bus for live sync
        try:
            from todo_bird_app.controllers.task_controller import _GLOBAL_EVENT_BUS
            _GLOBAL_EVENT_BUS.working_calendar_changed.connect(self._on_global_working_calendar_changed)
            self._global_working_calendar_connected = True
        except Exception:
            pass

    def cleanup(self):
        if getattr(self, "_cleaned_up", False):
            return
        self._cleaned_up = True
        try:
            from todo_bird_app.controllers.task_controller import (
                _GLOBAL_EVENT_BUS,
            )
            if getattr(
                self,
                "_global_working_calendar_connected",
                False,
            ):
                try:
                    _GLOBAL_EVENT_BUS.working_calendar_changed.disconnect(
                        self._on_global_working_calendar_changed
                    )
                except Exception:
                    pass
                self._global_working_calendar_connected = False
        except Exception:
            pass

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)

    def deleteLater(self):
        self.cleanup()
        super().deleteLater()

    def _on_global_working_calendar_changed(self):
        if getattr(self, "_cleaned_up", False):
            return

        self._rebuild_custom_table()
        self.recalculate()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(4)

        # Top control rows — three compact rows so the editor fits narrow
        # dialogs (the old single row forced a horizontal scrollbar).
        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        top_row.addWidget(QLabel("Allocation Mode:"))
        self.allocation_mode_combo = QComboBox()
        self.allocation_mode_combo.addItem("Fixed Daily", "fixed_daily")
        self.allocation_mode_combo.addItem("Total Effort", "total_effort")
        self.allocation_mode_combo.addItem("Custom by Day", "custom_by_day")
        top_row.addWidget(self.allocation_mode_combo, 1)
        main_layout.addLayout(top_row)

        dedication_row = QHBoxLayout()
        dedication_row.setSpacing(6)
        self.daily_dedication_label = QLabel("Daily Dedication:")
        dedication_row.addWidget(self.daily_dedication_label)
        self.daily_hours_spin = QSpinBox()
        self.daily_hours_spin.setRange(0, 24)
        self.daily_hours_spin.setSuffix("h")
        self.daily_hours_spin.setFixedWidth(84)
        self.daily_mins_spin = QSpinBox()
        self.daily_mins_spin.setRange(0, 59)
        self.daily_mins_spin.setSuffix("m")
        self.daily_mins_spin.setFixedWidth(84)
        dedication_row.addWidget(self.daily_hours_spin)
        dedication_row.addWidget(self.daily_mins_spin)
        dedication_row.addStretch()
        main_layout.addLayout(dedication_row)

        effort_row = QHBoxLayout()
        effort_row.setSpacing(6)
        self.planned_effort_label = QLabel("Planned Effort:")
        effort_row.addWidget(self.planned_effort_label)
        self.planned_effort_spin = QSpinBox()
        self.planned_effort_spin.setRange(0, 1000000)
        self.planned_effort_spin.setSuffix(" mins")
        self.planned_effort_spin.setFixedWidth(110)
        effort_row.addWidget(self.planned_effort_spin)
        effort_row.addStretch()
        main_layout.addLayout(effort_row)

        # Reactive summary label — wraps so a long summary never dictates
        # the editor's minimum width inside narrow dialogs.
        self.effort_summary_label = QLabel()
        self.effort_summary_label.setWordWrap(True)
        self.effort_summary_label.setStyleSheet("color: #3584E4; font-weight: 600; font-size: 11px;")
        main_layout.addWidget(self.effort_summary_label)

        # Custom-by-day table frame
        self.custom_alloc_frame = QFrame()
        self.custom_alloc_frame.setObjectName("CardWidget")
        self.custom_alloc_layout = QVBoxLayout(self.custom_alloc_frame)
        self.custom_alloc_layout.setContentsMargins(6, 6, 6, 6)
        self.custom_alloc_layout.setSpacing(4)
        main_layout.addWidget(self.custom_alloc_frame)

        # Signal connections
        self.allocation_mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self.daily_hours_spin.valueChanged.connect(lambda _v: self.recalculate())
        self.daily_mins_spin.valueChanged.connect(lambda _v: self.recalculate())
        self.planned_effort_spin.valueChanged.connect(self._on_planned_effort_spin_changed)

    def _active_working_days(self):
        project_calendar = self._active_project_calendar()
        if project_calendar is not None:
            calendar = ScheduleCalendar.from_project_calendar(project_calendar)
            if calendar is not None:
                return set(calendar.working_weekdays)
        return get_configured_working_weekdays(self.settings_manager)

    def _active_project_calendar(self):
        if self.project_calendar_provider is not None:
            try:
                return self.project_calendar_provider()
            except Exception:
                return None
        return self.project_calendar

    def _active_calendar_parts(self):
        project_calendar = self._active_project_calendar()
        if project_calendar is not None:
            calendar = ScheduleCalendar.from_project_calendar(project_calendar)
            if calendar is not None:
                return (
                    set(calendar.working_weekdays),
                    set(calendar.holidays),
                    {iso: 1 for iso in calendar.working_overrides},
                )
        return get_configured_working_weekdays(self.settings_manager), set(), {}

    def _calendar_status_for(self, target: Any) -> CalendarDateStatus:
        project_calendar = self._active_project_calendar()
        if project_calendar is not None:
            return classify_calendar_date(project_calendar, target)

        active_working_days, holidays, working_overrides = self._active_calendar_parts()
        is_work = is_working_day(
            target,
            working_weekdays=active_working_days,
            holidays=holidays,
            custom_overrides=working_overrides,
        )
        iso = target.strftime("%Y-%m-%d") if isinstance(target, date) else str(target)[:10]
        return CalendarDateStatus(
            date_str=iso,
            is_working=is_work,
            label="Working" if is_work else "Non-working",
            source="settings_weekday_rule",
        )

    def set_project_calendar(
        self,
        project_calendar: Optional[Any] = None,
        project_calendar_provider: Optional[Callable[[], Any]] = None,
    ):
        self.project_calendar = project_calendar
        if project_calendar_provider is not None:
            self.project_calendar_provider = project_calendar_provider
        self._rebuild_custom_table()
        self.recalculate()

    def set_dates(self, start_date: str, due_date: str):
        self.start_date_str = start_date or date.today().strftime("%Y-%m-%d")
        self.due_date_str = due_date or self.start_date_str
        self._rebuild_custom_table()
        self.recalculate()

    def set_data(
        self,
        allocation_mode: str = "fixed_daily",
        daily_dedication_minutes: int = 0,
        planned_effort_minutes: int = 0,
        custom_allocations: Optional[Dict[str, int]] = None,
        custom_actual_allocations: Optional[Dict[str, int]] = None,
    ):
        mode = allocation_mode or "fixed_daily"
        idx = self.allocation_mode_combo.findData(mode)
        if idx >= 0:
            self.allocation_mode_combo.blockSignals(True)
            self.allocation_mode_combo.setCurrentIndex(idx)
            self.allocation_mode_combo.blockSignals(False)

        ded = max(0, int(daily_dedication_minutes or 0))
        self.daily_hours_spin.blockSignals(True)
        self.daily_mins_spin.blockSignals(True)
        self.daily_hours_spin.setValue(ded // 60)
        self.daily_mins_spin.setValue(ded % 60)
        self.daily_hours_spin.blockSignals(False)
        self.daily_mins_spin.blockSignals(False)

        if custom_allocations is not None:
            self._custom_allocations = dict(custom_allocations)

        if custom_actual_allocations is not None:
            self._custom_actual_allocations = dict(custom_actual_allocations)
            self.actual_effort_minutes = sum(self._custom_actual_allocations.values())
            self.actualEffortChanged.emit(self.actual_effort_minutes)

        self._rebuild_custom_table()

        if mode == "total_effort":
            self.planned_effort_spin.blockSignals(True)
            self.planned_effort_spin.setValue(max(0, int(planned_effort_minutes or 0)))
            self.planned_effort_spin.blockSignals(False)

        self.recalculate()

    def get_data(self) -> Dict[str, Any]:
        mode = self.allocation_mode_combo.currentData()
        daily_m = self.daily_hours_spin.value() * 60 + self.daily_mins_spin.value()
        effort_m = self.planned_effort_spin.value()
        return {
            "allocation_mode": mode,
            "daily_dedication_minutes": daily_m,
            "planned_effort_minutes": effort_m,
            "custom_allocations": dict(self._custom_allocations),
            "custom_actual_allocations": dict(self._custom_actual_allocations),
            "actual_effort_minutes": int(self.actual_effort_minutes),
        }

    def _on_mode_changed(self, index: int):
        self._rebuild_custom_table()
        self.recalculate()

    def _on_planned_effort_spin_changed(self, value: int):
        mode = self.allocation_mode_combo.currentData()
        if mode == "total_effort":
            disp = format_duration_display(value)
            self.effort_summary_label.setText(f"Total Effort: {disp} ({value} mins) distributed evenly across scheduled days")
            self.planned_effort_spin.setToolTip(f"Planned work effort: {value} mins ({disp})")
            self.effortChanged.emit(value)

    def _rebuild_custom_table(self):
        clear_layout(self.custom_alloc_layout)

        self.custom_spinners.clear()
        self.custom_actual_spinners.clear()
        sd = parse_date(self.start_date_str)
        ed = parse_date(self.due_date_str)
        if not sd:
            return
        if not ed or ed < sd:
            ed = sd

        from PySide6.QtWidgets import QGridLayout
        
        self.grid_layout = QGridLayout()
        self.grid_layout.setSpacing(8)
        self.grid_layout.setColumnMinimumWidth(0, 80)
        self.grid_layout.setColumnMinimumWidth(1, 40)
        self.grid_layout.setColumnMinimumWidth(2, 90)
        self.grid_layout.setColumnMinimumWidth(3, 110)
        self.grid_layout.setColumnMinimumWidth(4, 110)

        h1 = QLabel("Date")
        h2 = QLabel("Day")
        h3 = QLabel("Calendar Status")
        h4 = QLabel("Planned Effort")
        h5 = QLabel("Actual Effort")
        
        for idx, h in enumerate([h1, h2, h3, h4, h5]):
            h.setStyleSheet("font-weight: bold;")
            h.setWordWrap(True)
            self.grid_layout.addWidget(h, 0, idx)

        self.custom_alloc_layout.addLayout(self.grid_layout)

        curr = sd
        active_working_days, holidays, working_overrides = self._active_calendar_parts()
        
        row_idx = 1

        while curr <= ed:
            iso = curr.strftime("%Y-%m-%d")
            lbl_d = QLabel(curr.strftime("%d %b %Y"))
            lbl_day = QLabel(curr.strftime("%a"))

            status = self._calendar_status_for(curr)
            is_work = status.is_working
            status_lbl = QLabel(status.label)
            if status.label == "Holiday":
                style = "color: #DC2626; font-weight: 700;"
            elif is_work:
                style = "color: #10B981; font-weight: 600;"
            else:
                style = "color: #F59E0B; font-weight: 600;"
            status_lbl.setStyleSheet(style)
            status_lbl.setToolTip(status.reason or status.source)
            status_lbl.setWordWrap(True)

            # Planned effort spinners
            h_spin = QSpinBox()
            h_spin.setRange(0, 24)
            h_spin.setSuffix("h")
            m_spin = QSpinBox()
            m_spin.setRange(0, 59)
            m_spin.setSuffix("m")

            cur_m = int(self._custom_allocations.get(iso, 0) or 0)
            h_spin.setValue(cur_m // 60)
            m_spin.setValue(cur_m % 60)

            def make_planned_handler(the_iso=iso, hs=h_spin, ms=m_spin):
                def on_change():
                    tot = hs.value() * 60 + ms.value()
                    self._custom_allocations[the_iso] = tot
                    self.recalculate()
                return on_change

            h_spin.valueChanged.connect(make_planned_handler())
            m_spin.valueChanged.connect(make_planned_handler())
            self.custom_spinners[iso] = (h_spin, m_spin)

            # Actual execution effort spinners
            act_h_spin = QSpinBox()
            act_h_spin.setRange(0, 24)
            act_h_spin.setSuffix("h")
            act_m_spin = QSpinBox()
            act_m_spin.setRange(0, 59)
            act_m_spin.setSuffix("m")

            cur_act_m = int(self._custom_actual_allocations.get(iso, 0) or 0)
            act_h_spin.setValue(cur_act_m // 60)
            act_m_spin.setValue(cur_act_m % 60)

            def make_actual_handler(the_iso=iso, ahs=act_h_spin, ams=act_m_spin):
                def on_act_change():
                    tot = ahs.value() * 60 + ams.value()
                    self._custom_actual_allocations[the_iso] = tot
                    self._recalculate_actual_effort()
                return on_act_change

            act_h_spin.valueChanged.connect(make_actual_handler())
            act_m_spin.valueChanged.connect(make_actual_handler())
            self.custom_actual_spinners[iso] = (act_h_spin, act_m_spin)

            self.grid_layout.addWidget(lbl_d, row_idx, 0)
            self.grid_layout.addWidget(lbl_day, row_idx, 1)
            self.grid_layout.addWidget(status_lbl, row_idx, 2)
            
            planned_w = QWidget()
            planned_l = QHBoxLayout(planned_w)
            planned_l.setContentsMargins(0, 0, 0, 0)
            planned_l.addWidget(h_spin)
            planned_l.addWidget(m_spin)
            self.grid_layout.addWidget(planned_w, row_idx, 3)

            actual_w = QWidget()
            actual_l = QHBoxLayout(actual_w)
            actual_l.setContentsMargins(0, 0, 0, 0)
            actual_l.addWidget(act_h_spin)
            actual_l.addWidget(act_m_spin)
            self.grid_layout.addWidget(actual_w, row_idx, 4)

            row_idx += 1
            curr += timedelta(days=1)

    def _recalculate_actual_effort(self):
        tot = sum(self._custom_actual_allocations.values())
        self.actual_effort_minutes = tot
        self.actualEffortChanged.emit(tot)
        self.recalculate()

    def recalculate(self):
        active_working_days, holidays, working_overrides = self._active_calendar_parts()
        mode = self.allocation_mode_combo.currentData()
        daily_m = self.daily_hours_spin.value() * 60 + self.daily_mins_spin.value()

        self.custom_alloc_frame.setVisible(mode == "custom_by_day")

        working_days = get_working_days_between(
            self.start_date_str,
            self.due_date_str,
            working_weekdays=active_working_days,
            holidays=holidays,
            custom_overrides=working_overrides,
        )
        num_working_days = len(working_days)

        if mode == "fixed_daily":
            self.planned_effort_spin.setReadOnly(True)
            self.daily_hours_spin.setEnabled(True)
            self.daily_mins_spin.setEnabled(True)
            self.daily_dedication_label.setEnabled(True)
            self.planned_effort_label.setEnabled(False)
            eff = num_working_days * daily_m
            self.planned_effort_spin.blockSignals(True)
            self.planned_effort_spin.setValue(eff)
            self.planned_effort_spin.blockSignals(False)
            disp = format_duration_display(eff)
            day_names = [d.strftime("%a") for d in working_days]
            w_str = ", ".join(day_names) if day_names else "None"
            self.effort_summary_label.setText(
                f"Fixed Daily: {self.daily_hours_spin.value()}h {self.daily_mins_spin.value():02d}m/day × {num_working_days} working days ({w_str}) = {disp} total planned effort"
            )

            # Update planned spinners
            for iso, (h_spin, m_spin) in self.custom_spinners.items():
                dt = parse_date(iso)
                is_w = (
                    is_working_day(
                        dt,
                        working_weekdays=active_working_days,
                        holidays=holidays,
                        custom_overrides=working_overrides,
                    )
                    if dt else False
                )
                val = daily_m if is_w else 0
                h_spin.blockSignals(True)
                m_spin.blockSignals(True)
                h_spin.setValue(val // 60)
                m_spin.setValue(val % 60)
                h_spin.setEnabled(False)
                m_spin.setEnabled(False)
                h_spin.blockSignals(False)
                m_spin.blockSignals(False)

        elif mode == "total_effort":
            self.planned_effort_spin.setReadOnly(False)
            self.daily_hours_spin.setEnabled(False)
            self.daily_mins_spin.setEnabled(False)
            self.daily_dedication_label.setEnabled(False)
            self.planned_effort_label.setEnabled(True)
            eff = self.planned_effort_spin.value()
            disp = format_duration_display(eff)
            self.effort_summary_label.setText(f"Total Effort: {disp} ({eff} mins) distributed evenly across scheduled days")

            # Update planned spinners
            base_val = eff // num_working_days if num_working_days > 0 else 0
            remainder = eff % num_working_days if num_working_days > 0 else 0
            
            for iso, (h_spin, m_spin) in self.custom_spinners.items():
                dt = parse_date(iso)
                is_w = (
                    is_working_day(
                        dt,
                        working_weekdays=active_working_days,
                        holidays=holidays,
                        custom_overrides=working_overrides,
                    )
                    if dt else False
                )
                val = 0
                if is_w:
                    val = base_val + (1 if remainder > 0 else 0)
                    if remainder > 0:
                        remainder -= 1

                h_spin.blockSignals(True)
                m_spin.blockSignals(True)
                h_spin.setValue(val // 60)
                m_spin.setValue(val % 60)
                h_spin.setEnabled(False)
                m_spin.setEnabled(False)
                h_spin.blockSignals(False)
                m_spin.blockSignals(False)

        elif mode == "custom_by_day":
            self.planned_effort_spin.setReadOnly(True)
            self.daily_hours_spin.setEnabled(False)
            self.daily_mins_spin.setEnabled(False)
            self.daily_dedication_label.setEnabled(False)
            self.planned_effort_label.setEnabled(False)

            # Enable planned spinners
            for iso, (h_spin, m_spin) in self.custom_spinners.items():
                h_spin.setEnabled(True)
                m_spin.setEnabled(True)

            eff = sum(self._custom_allocations.values())
            self.planned_effort_spin.blockSignals(True)
            self.planned_effort_spin.setValue(eff)
            self.planned_effort_spin.blockSignals(False)

            work_m = sum(
                v
                for k, v in self._custom_allocations.items()
                if is_working_day(
                    k,
                    working_weekdays=active_working_days,
                    holidays=holidays,
                    custom_overrides=working_overrides,
                )
            )
            override_m = sum(
                v
                for k, v in self._custom_allocations.items()
                if not is_working_day(
                    k,
                    working_weekdays=active_working_days,
                    holidays=holidays,
                    custom_overrides=working_overrides,
                )
            )
            act_tot = sum(self._custom_actual_allocations.values())

            w_disp = format_duration_display(work_m)
            o_disp = format_duration_display(override_m)
            t_disp = format_duration_display(eff)
            a_disp = format_duration_display(act_tot)

            summary_parts = [f"Planned: {t_disp}"]
            if override_m > 0:
                summary_parts.append(f"(Work: {w_disp}, Non-work: {o_disp})")
            if act_tot > 0:
                summary_parts.append(f"| Actual Effort: {a_disp}")

            self.effort_summary_label.setText(" | ".join(summary_parts))

        disp = format_duration_display(self.planned_effort_spin.value())
        self.planned_effort_spin.setToolTip(f"Planned work effort: {self.planned_effort_spin.value()} mins ({disp})")
        self.effortChanged.emit(self.planned_effort_spin.value())
