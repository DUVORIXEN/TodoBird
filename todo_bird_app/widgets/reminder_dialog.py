"""
Modern Reminder Dialog (Batch 3.10E Polish)
Polished card-based notification with full action suite:
Complete, Snooze, Open Task, Dismiss.
Features independent typography, custom font color with contrast safety,
experience-mode responsiveness, and fluid large-font layout.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Any

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QMenu, QSizePolicy, QWidget, QApplication, QSizeGrip, QScrollArea
)
from PySide6.QtCore import Qt, QPoint, QRect, QSize, QTimer, QEvent
from PySide6.QtGui import (
    QFont, QColor, QAction, QPainter, QPainterPath, QPixmap, QBrush, QPen, QPalette
)

from todo_bird_app.models.task import Task, TaskStatus
from todo_bird_app.services.typography_service import TypographyService
from todo_bird_app.services.reminder_policy_service import ReminderPolicyService
from todo_bird_app.services.experience_profile import ExperienceProfileService
from todo_bird_app.services.media_service import MediaService
from todo_bird_app.services.appearance_service import semantic_tokens_for

logger = logging.getLogger(__name__)

REMINDER_SIZE_PRESETS = {
    "compact": (460, 280),
    "standard": (540, 340),
    "large": (680, 440),
}
MIN_WIDTH = 360
MIN_HEIGHT = 220
RESIZE_MARGIN = 8


def get_reminder_corner_radius(settings_manager: Optional[Any], width: int, height: int) -> int:
    """Calculates corner radius based on configured style."""
    if not settings_manager:
        return 24
    style = str(settings_manager.get("reminder_corner_style", "rounded") or "rounded").lower().strip()
    if style == "soft":
        return 14
    elif style == "capsule":
        return min(36, max(18, int(min(height * 0.20, width * 0.10))))
    elif style == "custom":
        return max(8, min(48, int(settings_manager.get("reminder_corner_radius", 18) or 18)))
    return 24


def paint_reminder_card_background(painter: QPainter, rect: QRect, settings_manager: Optional[Any], width: int, height: int):
    """Paints rounded/capsule card background with background image, fit modes, opacity, and legibility overlay."""
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

    radius = get_reminder_corner_radius(settings_manager, width, height)
    draw_rect = rect.adjusted(1, 1, -1, -1)

    path = QPainterPath()
    path.addRoundedRect(draw_rect, radius, radius)

    painter.save()
    painter.setClipPath(path)

    is_dark = True
    if settings_manager:
        is_dark = str(settings_manager.get("theme", "dark")).lower() == "dark"

    # 1. Base Card Background
    base_color = QColor(24, 29, 38) if is_dark else QColor(248, 250, 252)
    painter.fillPath(path, base_color)

    # 2. Background Image
    bg_mode = "none"
    bg_img_path = ""
    fit_mode = "fill"
    opacity = 0.35
    overlay_val = 0.70

    if settings_manager:
        bg_mode = str(settings_manager.get("reminder_background_mode", "none") or "none").lower()
        if bg_mode == "global":
            bg_img_path = str(settings_manager.get("background_custom_image_path", "") or "")
            fit_mode = str(settings_manager.get("background_fit_mode", "fill") or "fill").lower()
            opacity = float(settings_manager.get("background_opacity", 0.35) or 0.35)
        elif bg_mode == "custom":
            bg_img_path = str(settings_manager.get("reminder_background_image", "") or "")
            fit_mode = str(settings_manager.get("reminder_background_fit", "fill") or "fill").lower()
            opacity = float(settings_manager.get("reminder_background_opacity", 0.40) or 0.40)
            overlay_val = float(settings_manager.get("reminder_background_overlay", 0.70) or 0.70)

    if bg_mode != "none" and bg_img_path:
        pixmap = MediaService.load_pixmap(bg_img_path)
        if pixmap and not pixmap.isNull():
            painter.setOpacity(max(0.0, min(1.0, opacity)))
            w, h = draw_rect.width(), draw_rect.height()
            if fit_mode == "fill":
                painter.drawPixmap(draw_rect, pixmap)
            elif fit_mode == "fit":
                scaled = pixmap.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                x = draw_rect.x() + (w - scaled.width()) // 2
                y = draw_rect.y() + (h - scaled.height()) // 2
                painter.drawPixmap(x, y, scaled)
            elif fit_mode == "center":
                cw, ch = pixmap.width(), pixmap.height()
                x = draw_rect.x() + (w - cw) // 2
                y = draw_rect.y() + (h - ch) // 2
                painter.drawPixmap(x, y, pixmap)
            elif fit_mode == "tile":
                brush = QBrush(pixmap)
                painter.fillRect(draw_rect, brush)

            # 3. Legibility contrast overlay
            painter.setOpacity(max(0.0, min(1.0, overlay_val)))
            if is_dark:
                painter.fillRect(draw_rect, QColor(15, 23, 42, int(220 * overlay_val + 25)))
            else:
                painter.fillRect(draw_rect, QColor(255, 255, 255, int(210 * overlay_val + 30)))

    painter.restore()

    # 4. Subtle Outer Border
    border_color = QColor(255, 255, 255, 30) if is_dark else QColor(0, 0, 0, 30)
    painter.setPen(QPen(border_color, 1.2))
    painter.setBrush(Qt.NoBrush)
    painter.drawRoundedRect(draw_rect, radius, radius)


class ReminderCardFrame(QFrame):
    """
    Outer card container rendering rounded/capsule corners, background image (Fill/Fit/Center/Tile),
    opacity, and adaptive legibility overlay.
    """
    def __init__(self, settings_manager: Optional[Any] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.setObjectName("ReminderOuterCard")
        self.setAttribute(Qt.WA_Hover, True)

    def get_corner_radius(self) -> int:
        return get_reminder_corner_radius(self.settings_manager, self.width(), self.height())

    def paintEvent(self, event):
        painter = QPainter(self)
        paint_reminder_card_background(painter, self.rect(), self.settings_manager, self.width(), self.height())


class ReminderDialog(QDialog):
    """
    Modern Capsule Card-Based Todo Bird Reminder Dialog with Visual Polish.
    """
    def __init__(self, task: Task, task_controller: Optional[Any] = None, settings_manager: Optional[Any] = None, parent=None):
        super().__init__(parent)
        if settings_manager is None and parent is not None:
            settings_manager = getattr(parent, "settings_manager", None)
        self.settings_manager = settings_manager
        self.task_controller = task_controller
        self.task = task
        self._drag_pos = None
        self._resize_edge = None
        self._drag_start_geo = None
        self._drag_start_pos = None
        self._is_resizing = False
        self._is_moving = False
        self._action_taken = False

        self.setWindowTitle(f"Reminder — {task.title or 'Task'}")
        self.setModal(False)
        self.setWindowModality(Qt.NonModal)
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowSystemMenuHint | Qt.WindowMinMaxButtonsHint | Qt.WindowCloseButtonHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setMinimumSize(MIN_WIDTH, MIN_HEIGHT)
        self.setMouseTracking(True)

        from todo_bird_app.services.window_registry import WindowRegistry
        WindowRegistry.register(self, role=f"reminder_{task.id}" if task and task.id else None)

        self._init_ui()
        self.restore_geometry_from_settings()
        self._apply_reminder_typography()

    def closeEvent(self, event):
        if not getattr(self, "_action_taken", False):
            self._action_taken = True
            if self.task and self.task.id is not None:
                ReminderPolicyService.hide_for_session(self.task.id)
        from todo_bird_app.services.window_registry import WindowRegistry
        WindowRegistry.unregister(self)
        super().closeEvent(event)

    def reject(self):
        if not getattr(self, "_action_taken", False):
            self._action_taken = True
            if self.task and self.task.id is not None:
                ReminderPolicyService.hide_for_session(self.task.id)
        from todo_bird_app.services.window_registry import WindowRegistry
        WindowRegistry.unregister(self)
        super().reject()

    def get_corner_radius(self) -> int:
        return get_reminder_corner_radius(self.settings_manager, self.width(), self.height())

    def paintEvent(self, event):
        painter = QPainter(self)
        paint_reminder_card_background(painter, self.rect(), self.settings_manager, self.width(), self.height())

    def _init_ui(self):
        exp_mode = "balanced"
        if self.settings_manager:
            exp_mode = str(self.settings_manager.get("experience_mode", "balanced") or "balanced").lower()

        profile = ExperienceProfileService.get_profile(exp_mode)
        card_radius = profile.get("card_radius", 10)
        base_margin = 14 if exp_mode == "professional" else (22 if exp_mode == "personal" else 18)
        base_spacing = 10 if exp_mode == "professional" else (16 if exp_mode == "personal" else 14)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(base_margin, base_margin, base_margin, base_margin)
        main_layout.setSpacing(base_spacing)

        # 1. Header Row:  Reminder (left) ... Time Badge (right)
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        self.lbl_header_icon = QLabel("Reminder")
        from todo_bird_app.services.icon_service import IconService as _IS
        self._header_bell = QLabel()
        self._header_bell.setPixmap(_IS.get_pixmap("bell", 18, "#6FA8F5"))
        self.lbl_header_icon.setStyleSheet("font-weight: 700; color: #3584E4;")
        header_layout.addWidget(self._header_bell)
        header_layout.addWidget(self.lbl_header_icon)

        header_layout.addStretch()

        # Date & Time Live Clock Pill (Top Right)
        self.lbl_time_badge = QLabel()
        self.lbl_time_badge.setStyleSheet(
            "background: rgba(53, 132, 228, 0.14); color: #3584E4; "
            "border: 1px solid rgba(53, 132, 228, 0.30); "
            "border-radius: 12px; padding: 3px 12px; font-weight: 600;"
        )
        self._clock_timer = QTimer(self)
        self._clock_timer.setInterval(1000)
        self._clock_timer.timeout.connect(self._update_time_badge)
        self._clock_timer.start()
        self._update_time_badge()
        header_layout.addWidget(self.lbl_time_badge)
        main_layout.addLayout(header_layout)

        # 2. Scrollable Body Container
        body_scroll = QScrollArea()
        body_scroll.setWidgetResizable(True)
        body_scroll.setFrameShape(QFrame.NoFrame)
        body_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        body_scroll.viewport().setStyleSheet("background: transparent;")
        body_widget = QWidget()
        body_widget.setStyleSheet("background: transparent;")
        body_layout = QVBoxLayout(body_widget)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(base_spacing)

        # Task Title
        self.title_label = QLabel(self.task.title or "Untitled Task")
        self.title_label.setWordWrap(True)
        self.title_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.title_label.setStyleSheet("font-weight: 700; color: inherit;")
        body_layout.addWidget(self.title_label)

        # Subtitle / Project & Schedule Meta
        proj_name = "Inbox"
        if self.task_controller and self.task.project_id:
            try:
                proj = self.task_controller.get_project(self.task.project_id)
                if proj:
                    proj_name = proj.name
            except Exception:
                pass

        sub_parts = []
        if self.task.planned_date:
            sub_parts.append(f"Planned: {self.task.planned_date}")
        if proj_name:
            sub_parts.append(f" {proj_name}")

        subtitle_text = " • ".join(sub_parts) if sub_parts else "Today"
        self.subtitle_label = QLabel(subtitle_text)
        self.subtitle_label.setStyleSheet("color: palette(mid); margin-bottom: 2px;")
        body_layout.addWidget(self.subtitle_label)

        # Description Card Frame
        self.desc_frame = QFrame()
        self.desc_frame.setObjectName("CardWidget")
        self.desc_frame.setStyleSheet(
            f"background: rgba(128, 128, 128, 0.10); border: 1px solid palette(midlight); "
            f"border-radius: {card_radius}px;"
        )
        desc_layout = QVBoxLayout(self.desc_frame)
        desc_layout.setContentsMargins(14, 12, 14, 12)

        desc_text = self.task.description or "No additional description."
        self.desc_label = QLabel(desc_text)
        self.desc_label.setWordWrap(True)
        self.desc_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.desc_label.setStyleSheet("color: palette(mid);")
        desc_layout.addWidget(self.desc_label)

        body_layout.addWidget(self.desc_frame, 1)

        body_scroll.setWidget(body_widget)
        main_layout.addWidget(body_scroll, 1)

        # 3. Action Buttons Row: Smart, Compact & High-Legibility
        button_row = QHBoxLayout()
        button_row.setSpacing(10)

        # Complete Action (Emerald capsule)
        self.btn_complete = QPushButton("Complete")
        self.btn_complete.setMinimumHeight(32)
        self.btn_complete.setMaximumHeight(40)
        self.btn_complete.setShortcut("Alt+C")
        self.btn_complete.setToolTip("Complete this task (Alt+C)")
        self.btn_complete.setStyleSheet(
            "QPushButton { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #10B981, stop:1 #059669); "
            "color: #FFFFFF; font-weight: 700; border: none; border-radius: 16px; padding: 0 16px; } "
            "QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #34D399, stop:1 #10B981); } "
            "QPushButton:pressed { background: #047857; }"
        )
        self.btn_complete.setCursor(Qt.PointingHandCursor)
        self.btn_complete.clicked.connect(self.on_complete_clicked)
        button_row.addWidget(self.btn_complete)

        # Snooze Action (Amber capsule with menu)
        self.btn_snooze = QPushButton("Snooze ▾")
        self.btn_snooze.setMinimumHeight(32)
        self.btn_snooze.setMaximumHeight(40)
        self.btn_snooze.setShortcut("Alt+S")
        self.btn_snooze.setToolTip("Snooze reminder for later (Alt+S)")
        self.btn_snooze.setStyleSheet(
            "QPushButton { background: rgba(245, 158, 11, 0.16); color: #F59E0B; font-weight: 600; "
            "border: 1px solid rgba(245, 158, 11, 0.35); border-radius: 16px; padding: 0 14px; } "
            "QPushButton:hover { background: rgba(245, 158, 11, 0.28); border-color: rgba(245, 158, 11, 0.6); color: #FBBF24; } "
            "QPushButton:pressed { background: rgba(245, 158, 11, 0.38); }"
        )
        self.btn_snooze.setCursor(Qt.PointingHandCursor)
        self.btn_snooze.clicked.connect(self._on_snooze_button_clicked)
        button_row.addWidget(self.btn_snooze)

        # Open Task Action (Blue glass capsule)
        self.btn_open = QPushButton("Open Task")
        self.btn_open.setMinimumHeight(32)
        self.btn_open.setMaximumHeight(40)
        self.btn_open.setShortcut("Alt+O")
        self.btn_open.setToolTip("Open task editor dialog (Alt+O)")
        self.btn_open.setStyleSheet(
            "QPushButton { background: rgba(53, 132, 228, 0.14); color: #3584E4; font-weight: 600; "
            "border: 1px solid rgba(53, 132, 228, 0.32); border-radius: 16px; padding: 0 14px; } "
            "QPushButton:hover { background: rgba(53, 132, 228, 0.25); border-color: rgba(53, 132, 228, 0.55); color: #60A5FA; } "
            "QPushButton:pressed { background: rgba(53, 132, 228, 0.35); }"
        )
        self.btn_open.setCursor(Qt.PointingHandCursor)
        self.btn_open.clicked.connect(self.on_open_task_clicked)
        button_row.addWidget(self.btn_open)

        button_row.addStretch()

        # Dismiss Action (Subtle glass capsule)
        self.btn_dismiss = QPushButton("Dismiss")
        self.btn_dismiss.setMinimumHeight(32)
        self.btn_dismiss.setMaximumHeight(40)
        self.btn_dismiss.setShortcut("Alt+D")
        self.btn_dismiss.setToolTip("Dismiss this reminder (Alt+D or Esc)")
        self.btn_dismiss.setObjectName("CancelButton")
        self.btn_dismiss.setCursor(Qt.PointingHandCursor)
        self.btn_dismiss.clicked.connect(self.on_dismiss_clicked)
        button_row.addWidget(self.btn_dismiss)

        main_layout.addLayout(button_row)
        self._install_chrome_filters()

    def _update_time_badge(self):
        """Live updates the top-right time pill with current clock time and schedule context."""
        now = datetime.now()
        current_clock = now.strftime("%I:%M %p").lstrip("0")

        sched_part = ""
        if self.task.planned_start_time and str(self.task.planned_start_time).strip():
            sched_part = f" • Due {self.task.planned_start_time}"
        elif self.task.due_date:
            sched_part = f" • Due {self.task.due_date}"

        self.lbl_time_badge.setText(f" {current_clock}{sched_part}")

    def _install_chrome_filters(self):
        """Installs centralized event filter for reliable native resize/move delivery."""
        from todo_bird_app.services.window_interaction_service import WindowInteractionService
        self.installEventFilter(self)
        for child in self.findChildren(QWidget):
            if not WindowInteractionService.is_interactive_child_widget(child):
                child.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            from todo_bird_app.services.window_interaction_service import WindowInteractionService
            global_pos = event.globalPosition().toPoint() if hasattr(event, "globalPosition") else event.globalPos()
            local_pos = self.mapFromGlobal(global_pos)
            edge = self._get_resize_edge(local_pos)
            if edge:
                if WindowInteractionService.begin_system_resize(self, event, edge):
                    return True
            else:
                if WindowInteractionService.begin_system_move(self, event):
                    return True
        elif event.type() == QEvent.MouseMove:
            if not getattr(self, "_is_resizing", False) and not getattr(self, "_is_moving", False):
                global_pos = event.globalPosition().toPoint() if hasattr(event, "globalPosition") else event.globalPos()
                local_pos = self.mapFromGlobal(global_pos)
                edge = self._get_resize_edge(local_pos)
                if edge in ("left", "right"):
                    self.setCursor(Qt.SizeHorCursor)
                elif edge in ("top", "bottom"):
                    self.setCursor(Qt.SizeVerCursor)
                elif edge in ("top_left", "bottom_right"):
                    self.setCursor(Qt.SizeFDiagCursor)
                elif edge in ("top_right", "bottom_left"):
                    self.setCursor(Qt.SizeBDiagCursor)
                else:
                    self.setCursor(Qt.ArrowCursor)
        return super().eventFilter(obj, event)

    def _get_resize_edge(self, pos: QPoint) -> str:
        """Determines which edge or corner the cursor is currently hovering over."""
        rect = self.rect()
        x, y, w, h = pos.x(), pos.y(), rect.width(), rect.height()
        left = x <= RESIZE_MARGIN
        right = x >= w - RESIZE_MARGIN
        top = y <= RESIZE_MARGIN
        bottom = y >= h - RESIZE_MARGIN

        if top and left: return "top_left"
        if top and right: return "top_right"
        if bottom and left: return "bottom_left"
        if bottom and right: return "bottom_right"
        if left: return "left"
        if right: return "right"
        if top: return "top"
        if bottom: return "bottom"
        return ""


    def mouseMoveEvent(self, event):
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        global_pos = event.globalPosition().toPoint() if hasattr(event, "globalPosition") else event.globalPos()

        if self._is_resizing and self._resize_edge and self._drag_start_geo is not None:
            delta = global_pos - self._drag_start_pos
            geo = QRect(self._drag_start_geo)
            edge = self._resize_edge

            if "left" in edge:
                new_w = max(MIN_WIDTH, geo.width() - delta.x())
                geo.setLeft(geo.right() - new_w)
            elif "right" in edge:
                new_w = max(MIN_WIDTH, geo.width() + delta.x())
                geo.setWidth(new_w)

            if "top" in edge:
                new_h = max(MIN_HEIGHT, geo.height() - delta.y())
                geo.setTop(geo.bottom() - new_h)
            elif "bottom" in edge:
                new_h = max(MIN_HEIGHT, geo.height() + delta.y())
                geo.setHeight(new_h)

            # Smooth local resize without triggering circular broadcasts or DB writes
            self.setGeometry(geo)
            event.accept()
        elif self._is_moving and self._drag_pos is not None and (event.buttons() & Qt.LeftButton):
            self.move(global_pos - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        was_resizing = self._is_resizing
        was_moving = self._is_moving

        self._resize_edge = None
        self._is_resizing = False
        self._is_moving = False
        self._drag_pos = None
        self._drag_start_geo = None
        self._drag_start_pos = None
        self.setCursor(Qt.ArrowCursor)

        # On drag release, persist final dimensions and broadcast cleanly once
        if was_resizing or was_moving:
            w = max(MIN_WIDTH, self.width())
            h = max(MIN_HEIGHT, self.height())
            if self.settings_manager:
                if self.settings_manager.get("reminder_window_width") != w:
                    self.settings_manager.set("reminder_window_width", w)
                if self.settings_manager.get("reminder_window_height") != h:
                    self.settings_manager.set("reminder_window_height", h)
                self.settings_manager.set("reminder_window_x", self.x())
                self.settings_manager.set("reminder_window_y", self.y())
                cur_mode = str(self.settings_manager.get("reminder_window_size_mode", "standard")).lower()
                if cur_mode in REMINDER_SIZE_PRESETS:
                    pw, ph = REMINDER_SIZE_PRESETS[cur_mode]
                    if abs(w - pw) > 10 or abs(h - ph) > 10:
                        self.settings_manager.set("reminder_window_size_mode", "custom")

            from todo_bird_app.services.window_registry import WindowRegistry
            WindowRegistry.notify_reminder_resized(w, h)

        event.accept()

    def leaveEvent(self, event):
        if not (hasattr(self, "_resize_edge") and self._resize_edge) and self._drag_pos is None:
            self.setCursor(Qt.ArrowCursor)
        super().leaveEvent(event)

    def apply_preset(self, preset_name: str):
        """Applies a size preset (compact, standard, large, custom)."""
        preset_key = str(preset_name or "standard").lower().strip()
        if preset_key in REMINDER_SIZE_PRESETS:
            w, h = REMINDER_SIZE_PRESETS[preset_key]
            self.resize(w, h)
            if self.settings_manager:
                self.settings_manager.set("reminder_window_size_mode", preset_key)
                self.settings_manager.set("reminder_window_width", w)
                self.settings_manager.set("reminder_window_height", h)

    def restore_geometry_from_settings(self):
        """Restores and clamps reminder window dimensions and position from settings."""
        if not self.settings_manager:
            self.resize(*REMINDER_SIZE_PRESETS["standard"])
            return

        mode = str(self.settings_manager.get("reminder_window_size_mode", "standard") or "standard").lower().strip()
        default_w, default_h = REMINDER_SIZE_PRESETS.get(mode, REMINDER_SIZE_PRESETS["standard"])

        w = int(self.settings_manager.get("reminder_window_width", default_w) or default_w)
        h = int(self.settings_manager.get("reminder_window_height", default_h) or default_h)

        w = max(MIN_WIDTH, w)
        h = max(MIN_HEIGHT, h)

        # Screen geometry clamping via WindowInteractionService
        from todo_bird_app.services.window_interaction_service import WindowInteractionService, PlatformCapabilities
        saved_x = self.settings_manager.get("reminder_window_x")
        saved_y = self.settings_manager.get("reminder_window_y")

        if saved_x is not None and saved_y is not None:
            try:
                target_rect = QRect(int(saved_x), int(saved_y), w, h)
                clamped_rect = WindowInteractionService.ensure_window_on_screen(target_rect, target_widget=self, min_width=MIN_WIDTH, min_height=MIN_HEIGHT)
                if PlatformCapabilities.supports_manual_top_level_positioning():
                    self.setGeometry(clamped_rect)
                else:
                    self.resize(clamped_rect.width(), clamped_rect.height())
                return
            except Exception:
                pass

        self.resize(w, h)

    def update_from_settings(self):
        """Live updates dimensions, typography, background, and corner radius from current settings."""
        self.restore_geometry_from_settings()
        self._apply_reminder_typography()
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if getattr(self, "_is_resizing", False):
            return

        w = max(MIN_WIDTH, self.width())
        h = max(MIN_HEIGHT, self.height())
        if self.settings_manager:
            if self.settings_manager.get("reminder_window_width") != w:
                self.settings_manager.set("reminder_window_width", w)
            if self.settings_manager.get("reminder_window_height") != h:
                self.settings_manager.set("reminder_window_height", h)
            cur_mode = str(self.settings_manager.get("reminder_window_size_mode", "standard")).lower()
            if cur_mode in REMINDER_SIZE_PRESETS:
                pw, ph = REMINDER_SIZE_PRESETS[cur_mode]
                if abs(w - pw) > 10 or abs(h - ph) > 10:
                    self.settings_manager.set("reminder_window_size_mode", "custom")

            from todo_bird_app.services.window_registry import WindowRegistry
            WindowRegistry.notify_reminder_resized(w, h)

    def moveEvent(self, event):
        super().moveEvent(event)
        if self.settings_manager:
            self.settings_manager.set("reminder_window_x", self.x())
            self.settings_manager.set("reminder_window_y", self.y())

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.on_hide_for_session_clicked()
            event.accept()
        else:
            super().keyPressEvent(event)

    def on_hide_for_session_clicked(self):
        """Temporarily hides the reminder for this session only without acknowledging/dismissing it."""
        if not getattr(self, "_action_taken", False):
            self._action_taken = True
            if self.task and self.task.id is not None:
                ReminderPolicyService.hide_for_session(self.task.id)
        from todo_bird_app.services.window_registry import WindowRegistry
        WindowRegistry.unregister(self)
        self.reject()
        self.close()

    def _apply_reminder_typography(self):
        """Applies configured reminder typography and optional custom color."""
        font = TypographyService.get_font_for_area("reminder", self.settings_manager)
        self.setFont(font)
        TypographyService.apply_to_widget(self, "reminder", self.settings_manager)

        # Title gets slightly larger scale proportional to area font
        title_font = QFont(font)
        title_font.setPointSize(max(10, font.pointSize() + 4))
        title_font.setWeight(font.weight())
        self.title_label.setFont(title_font)

        # Custom Font Color if configured
        custom_color = TypographyService.get_font_color_for_area("reminder", self.settings_manager)
        if custom_color:
            self.title_label.setStyleSheet(f"color: {custom_color}; font-weight: 700;")
            self.desc_label.setStyleSheet(f"color: {custom_color}; line-height: 1.4;")
        else:
            self.title_label.setStyleSheet("color: inherit; font-weight: 700;")
            self.desc_label.setStyleSheet("color: palette(mid);")

    def show_snooze_menu(self, exec_menu: bool = True):
        menu = QMenu(self)
        menu.setObjectName("reminder_snooze_menu")
        self._apply_snooze_menu_theme(menu)
        snooze_options = [
            ("5 minutes", 5),
            ("10 minutes", 10),
            ("20 minutes", 20),
            ("30 minutes", 30),
            ("1 hour", 60),
            ("24 hours / 1 day", 1440),
        ]
        for label, minutes in snooze_options:
            action = QAction(label, self)
            action.triggered.connect(
                lambda _checked=False, m=minutes: self.on_snooze_selected(m)
            )
            menu.addAction(action)

        if exec_menu:
            menu.exec(self.btn_snooze.mapToGlobal(QPoint(0, self.btn_snooze.height() + 4)))
        return menu

    def _on_snooze_button_clicked(self, _checked: bool = False):
        self.show_snooze_menu(exec_menu=True)

    def _apply_snooze_menu_theme(self, menu: QMenu) -> None:
        is_dark = True
        accent = "#E95420"
        if self.settings_manager:
            is_dark = str(self.settings_manager.get("theme", "dark")).lower().strip() == "dark"
            accent = str(self.settings_manager.get("accent_color", accent) or accent)
        else:
            app = QApplication.instance()
            if app is not None:
                theme = str(app.property("todoBirdTheme") or "").lower().strip()
                if theme in {"dark", "light"}:
                    is_dark = theme == "dark"
                else:
                    is_dark = app.palette().color(QPalette.Window).lightness() < 128
                app_accent = str(app.property("todoBirdAccent") or "")
                if QColor(app_accent).isValid():
                    accent = app_accent

        tokens = semantic_tokens_for(is_dark, accent)
        menu.setStyleSheet(
            "QMenu { "
            f"background-color: {tokens['SURFACE_1']}; "
            f"color: {tokens['TEXT_PRIMARY']}; "
            f"border: 1px solid {tokens['BORDER_NORMAL']}; "
            "border-radius: 8px; padding: 6px; "
            "} "
            "QMenu::item { padding: 7px 18px; border-radius: 6px; } "
            "QMenu::item:selected { "
            f"background-color: {tokens['ACCENT_SUBTLE']}; "
            f"color: {tokens['TEXT_PRIMARY']}; "
            "} "
            "QMenu::item:disabled { "
            f"color: {tokens['TEXT_DISABLED']}; "
            "}"
        )

    def on_snooze_selected(self, minutes: int):
        self._action_taken = True
        if self.task.id is not None:
            ReminderPolicyService.snooze_reminder(self.task.id, minutes, settings_manager=self.settings_manager)
        from todo_bird_app.services.window_registry import WindowRegistry
        WindowRegistry.unregister(self)
        self.accept()
        self.close()

    def on_complete_clicked(self):
        self._action_taken = True
        if self.task_controller and self.task:
            ReminderPolicyService.complete_reminder(self.task, self.task_controller, settings_manager=self.settings_manager)
        elif self.task.id is not None:
            occ_key = ReminderPolicyService.get_occurrence_key(self.task)
            ReminderPolicyService.dismiss_reminder(self.task.id, occurrence_key=occ_key, settings_manager=self.settings_manager)
        from todo_bird_app.services.window_registry import WindowRegistry
        WindowRegistry.unregister(self)
        self.accept()
        self.close()

    def on_dismiss_clicked(self):
        self._action_taken = True
        if self.task.id is not None:
            occ_key = ReminderPolicyService.get_occurrence_key(self.task)
            ReminderPolicyService.dismiss_reminder(self.task.id, occurrence_key=occ_key, settings_manager=self.settings_manager)
        from todo_bird_app.services.window_registry import WindowRegistry
        WindowRegistry.unregister(self)
        self.accept()
        self.close()

    def on_open_task_clicked(self):
        self._action_taken = True
        from todo_bird_app.widgets.task_dialog import TaskDialog
        projects = []
        if self.task_controller:
            projects = self.task_controller.get_all_projects()

        dlg = TaskDialog(
            projects, self.task,
            db_manager=getattr(self.task_controller, "db_manager", None),
            settings_manager=self.settings_manager,
            parent=self.parent()
        )
        if dlg.exec() == TaskDialog.Accepted:
            if self.task_controller:
                self.task_controller.update_task(dlg.get_task())
        self.accept()
