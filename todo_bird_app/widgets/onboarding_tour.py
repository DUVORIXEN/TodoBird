"""
TODO BIRD — INTERACTIVE FIRST-TIME TEACHING NAVIGATION & SPOTLIGHT TOUR
Guides first-time and returning users through Todo Bird's architecture,
navigation dock, WBS & Gantt scheduling engine, World Clock, Razorpay support,
and community feedback system with live UI spotlighting.
"""

import logging
from typing import List, Dict, Any, Optional
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QWidget, QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt, Signal, QRect, QRectF, QPoint
from PySide6.QtGui import QPainter, QColor, QPen, QPainterPath, QFont

logger = logging.getLogger(__name__)


TOUR_STEPS: List[Dict[str, Any]] = [
    {
        "id": "welcome",
        "badge": "STEP 1 OF 7 • WELCOME TO TODO BIRD",
        "title": "👋 Welcome to Your Offline-First Executive Workspace",
        "section": "dashboard",
        "target": None,
        "summary": (
            "Todo Bird is designed for complete privacy, speed, and execution truth. "
            "All your tasks, projects, WBS hierarchies, and schedules live 100% locally on your device."
        ),
        "bullets": [
            "🔒 100% Local SQLite Authority — Zero cloud lock-in, works completely offline.",
            "🎙️ Avocet Voice Companion — Greets you by name and keeps your daily rhythm calm & focused.",
            "⚡ Keyboard-First Speed — Press Ctrl+N for a new task, Ctrl+K for Command Palette, or F1 for the User Manual.",
        ],
        "action_label": "Preview Executive Dashboard",
    },
    {
        "id": "navigation",
        "badge": "STEP 2 OF 7 • ADAPTIVE NAVIGATION DOCK",
        "title": "🧭 Master the Adaptive Navigation Dock",
        "section": "dashboard",
        "target": "sidebar",
        "summary": (
            "The Navigation Dock gives you 1-click access to every stage of your productivity workflow: "
            "Capture (Inbox) → Plan (Projects & Gantt) → Execute (Today & Focus) → Reflect (Daily Review & Analytics)."
        ),
        "bullets": [
            "🖱️ Drag & Drop Reordering — Drag any sidebar item to customize your personal navigation order.",
            "📐 Dock Anywhere — In Settings, move the navigation dock to Left, Right, Top, or Bottom in 6 visual styles (Expanded, Rail, Slim, Tiles, Glass, Minimal).",
            "🔢 Quick Shortcuts — Jump instantly with Ctrl+1 (Dashboard) through Ctrl+7 (Analytics).",
        ],
        "action_label": "Highlight Navigation Dock",
    },
    {
        "id": "capture_wbs",
        "badge": "STEP 3 OF 7 • TASKS, PROJECTS & WBS HIERARCHY",
        "title": "🌳 Capture Tasks & Build Multi-Level WBS Hierarchies",
        "section": "projects",
        "target": "add_btn",
        "summary": (
            "Click '+ New Task' (or press Ctrl+N) from anywhere to capture tasks with rich descriptions, "
            "nested subtasks, planned effort, priority, and smart startup reminders."
        ),
        "bullets": [
            "📂 Projects & WBS View — Break complex goals into multi-level Work Breakdown Structures (WBS).",
            "📈 Automatic Parent Rollups — Parent tasks automatically roll up planned duration, actual effort, and completion % from child subtasks.",
            "📌 Pin Critical Items — Pin key tasks or subtasks with custom colors so they stay top-of-mind.",
        ],
        "action_label": "Show Projects & WBS View",
    },
    {
        "id": "gantt_cpm",
        "badge": "STEP 4 OF 7 • INTERACTIVE GANTT & CRITICAL PATH (CPM)",
        "title": "📊 Interactive Gantt Timeline & Plan vs. Actual Truth",
        "section": "gantt",
        "target": None,
        "summary": (
            "Todo Bird includes an enterprise-grade Critical Path Method (CPM) scheduling engine and "
            "interactive Gantt timeline that compares your Baseline Plan against Actual Execution."
        ),
        "bullets": [
            "🔗 Smart Dependencies — Link tasks with Finish-to-Start (FS), Start-to-Start (SS), Finish-to-Finish (FF), or Start-to-Finish (SF) constraints.",
            "🖱️ Direct Bar Manipulation — Drag task bars to reschedule, resize edges to adjust duration, or double-click to edit details.",
            "📅 Working Calendar Aware — Respects your configured working weekdays and daily capacity hours.",
        ],
        "action_label": "Explore Gantt Timeline",
    },
    {
        "id": "focus_review",
        "badge": "STEP 5 OF 7 • DEEP FOCUS & DAILY REVIEW",
        "title": "🎯 Execute in Focus Mode & Close the Day with Clarity",
        "section": "focus",
        "target": None,
        "summary": (
            "Planning is only half the journey. Todo Bird helps you execute without distraction and "
            "review your daily progress with honesty and calm."
        ),
        "bullets": [
            "⏱️ Focus Mode — Pick a target task, start the deep-work timer, and log actual execution time automatically.",
            "🌅 Daily Review — Morning planning ritual to pick today's priorities & Evening review to inspect Plan vs. Actual variance.",
            "🔔 Smart Reminders — Configure tasks to remind you on app startup, system login, or scheduled times.",
        ],
        "action_label": "Preview Focus Mode",
    },
    {
        "id": "header_tools",
        "badge": "STEP 6 OF 7 • WORLD CLOCK, RAZORPAY SUPPORT & LANGUAGES",
        "title": "🌐 Global World Clock & 💜 Razorpay Support Bar",
        "section": "world_clock",
        "target": "clock_and_razorpay",
        "summary": (
            "Look at the top-right Header Bar! Your essential global tools sit side-by-side for instant access from any screen:"
        ),
        "bullets": [
            "🌐 World Clock (Ctrl+Alt+W) — Track 249 countries & 498+ timezones offline with 5 analog/digital themes and a Cross-Timezone Meeting Scrubber.",
            "💜 Razorpay Support Button (Right Beside World Clock) — Todo Bird is free & ad-free. Click 'Razorpay' anytime to optionally support development via UPI/Cards!",
            "🗣️ 11 UI Languages & Theme Toggle — Switch languages or toggle Dark/Light mode in a single click.",
        ],
        "action_label": "Show World Clock & Razorpay Bar",
    },
    {
        "id": "feedback_community",
        "badge": "STEP 7 OF 7 • SHARE HOW YOU FEEL & COMMUNITY PULSE",
        "title": "💬 Tell Us Who You Are & How You Feel About Todo Bird!",
        "section": "feedback",
        "target": "feedback_btn",
        "summary": (
            "We built Todo Bird for you! Whether you downloaded from Windows Store, Ubuntu Software, or GitHub, "
            "we want to know who is using Todo Bird and how you feel about it."
        ),
        "bullets": [
            "⭐ Rate & Share Your Mood — Click 'Feedback' in the top bar or sidebar to rate Todo Bird (1–5 stars), pick your mood emoji, and introduce yourself.",
            "🚀 Direct to Developer — Send your feedback, feature ideas, or bug reports straight to DUVORIXEN via 1-click GitHub Community Wall, Webhook, or Store Review.",
            "📖 Need Help Later? — Click 'Guide' in the top bar (or press F1) anytime to open the full searchable User Manual or replay this tour!",
        ],
        "action_label": "Open Feedback & Community View",
    },
]


class OnboardingTeachingOverlay(QFrame):
    """
    In-window interactive teaching tour overlay with live target spotlighting.
    Mounted inside MainWindow.centralWidget() so it works identically across
    X11, Wayland, Windows 11, and macOS without creating stray modal dialogs.
    """
    tour_completed = Signal()
    open_manual_requested = Signal()
    open_feedback_requested = Signal()
    open_support_requested = Signal()

    def __init__(self, main_window, settings_manager=None, parent=None):
        super().__init__(parent or main_window.centralWidget() or main_window)
        self.main_window = main_window
        self.settings_manager = settings_manager or getattr(main_window, "settings_manager", None)
        self.current_step_index = 0

        self.setObjectName("OnboardingTeachingOverlay")
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setFocusPolicy(Qt.StrongFocus)

        self._init_ui()
        self._load_step(0, navigate_live=False)

    def _init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(32, 32, 32, 32)
        root_layout.addStretch(1)

        center_row = QHBoxLayout()
        center_row.addStretch(1)

        # Main Teaching Card
        self.card = QFrame(self)
        self.card.setObjectName("OnboardingTourCard")
        self.card.setMinimumWidth(620)
        self.card.setMaximumWidth(700)
        self.card.setStyleSheet(
            "QFrame#OnboardingTourCard {"
            "  background-color: #161925;"
            "  border: 2px solid #E95420;"
            "  border-radius: 16px;"
            "}"
            "QFrame#OnboardingTourCard QLabel {"
            "  color: #F8FAFC;"
            "  background: transparent;"
            "}"
        )

        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(36)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(0, 0, 0, 180))
        self.card.setGraphicsEffect(shadow)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(28, 24, 28, 24)
        card_layout.setSpacing(14)

        # Top row: Badge + Step Dots + Skip Button
        top_row = QHBoxLayout()
        self.badge_label = QLabel("STEP 1 OF 7")
        self.badge_label.setStyleSheet(
            "background-color: rgba(233, 84, 32, 0.22); color: #FF7A45; "
            "font-weight: 700; font-size: 11px; padding: 4px 10px; border-radius: 8px;"
        )
        top_row.addWidget(self.badge_label)
        top_row.addStretch()

        # Step indicator pills
        self.step_dots_layout = QHBoxLayout()
        self.step_dots_layout.setSpacing(6)
        self.step_dot_buttons: List[QPushButton] = []
        for idx in range(len(TOUR_STEPS)):
            dot = QPushButton(str(idx + 1))
            dot.setFixedSize(26, 26)
            dot.setCursor(Qt.PointingHandCursor)
            dot.setToolTip(f"Jump to Step {idx + 1}: {TOUR_STEPS[idx]['title']}")
            dot.clicked.connect(lambda _checked=False, i=idx: self._load_step(i, navigate_live=True))
            self.step_dots_layout.addWidget(dot)
            self.step_dot_buttons.append(dot)
        top_row.addLayout(self.step_dots_layout)

        top_row.addSpacing(8)
        self.skip_btn = QPushButton("✕ Close Tour")
        self.skip_btn.setCursor(Qt.PointingHandCursor)
        self.skip_btn.setStyleSheet(
            "QPushButton { background: rgba(255,255,255,0.08); color: #CBD5E1; "
            "border-radius: 6px; padding: 4px 10px; font-size: 11px; }"
            "QPushButton:hover { background: rgba(255,255,255,0.16); color: #FFFFFF; }"
        )
        self.skip_btn.clicked.connect(self.finish_tour)
        top_row.addWidget(self.skip_btn)
        card_layout.addLayout(top_row)

        # Title
        self.title_label = QLabel()
        self.title_label.setWordWrap(True)
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        self.title_label.setFont(title_font)
        card_layout.addWidget(self.title_label)

        # Summary
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet("color: #CBD5E1; font-size: 13px; line-height: 1.45;")
        card_layout.addWidget(self.summary_label)

        # Bullets Frame
        self.bullets_frame = QFrame()
        self.bullets_frame.setStyleSheet(
            "QFrame { background-color: rgba(30, 41, 59, 0.75); border: 1px solid rgba(148, 163, 184, 0.25); "
            "border-radius: 10px; }"
        )
        self.bullets_layout = QVBoxLayout(self.bullets_frame)
        self.bullets_layout.setContentsMargins(16, 12, 16, 12)
        self.bullets_layout.setSpacing(8)
        self.bullet_labels: List[QLabel] = []
        for _ in range(3):
            b_lbl = QLabel()
            b_lbl.setWordWrap(True)
            b_lbl.setStyleSheet("color: #E2E8F0; font-size: 12.5px; border: none; background: transparent;")
            self.bullets_layout.addWidget(b_lbl)
            self.bullet_labels.append(b_lbl)
        card_layout.addWidget(self.bullets_frame)

        # Step 1 Interactive Quick-Setup Panel (Salutation + Country)
        self.quick_setup_frame = QFrame()
        self.quick_setup_frame.setStyleSheet(
            "QFrame { background-color: rgba(37, 99, 235, 0.14); border: 1px solid rgba(59, 130, 246, 0.4); "
            "border-radius: 10px; }"
        )
        qs_layout = QHBoxLayout(self.quick_setup_frame)
        qs_layout.setContentsMargins(14, 10, 14, 10)
        qs_layout.setSpacing(10)

        qs_lbl = QLabel("✨ Quick Personalize:")
        qs_lbl.setStyleSheet("font-weight: 700; font-size: 12px; color: #93C5FD; border: none;")
        qs_layout.addWidget(qs_lbl)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Your Name (e.g. Friend / Alex)")
        if self.settings_manager:
            current_sal = str(self.settings_manager.get("user_salutation", "friend") or "")
            if current_sal and current_sal != "friend":
                self.name_input.setText(current_sal)
        self.name_input.setStyleSheet(
            "QLineEdit { background: #0F172A; color: #F8FAFC; border: 1px solid #475569; "
            "border-radius: 6px; padding: 5px 8px; }"
        )
        qs_layout.addWidget(self.name_input, 1)

        self.country_input = QLineEdit()
        self.country_input.setPlaceholderText("Country / City (optional)")
        if self.settings_manager:
            self.country_input.setText(str(self.settings_manager.get("user_country", "") or ""))
        self.country_input.setStyleSheet(
            "QLineEdit { background: #0F172A; color: #F8FAFC; border: 1px solid #475569; "
            "border-radius: 6px; padding: 5px 8px; }"
        )
        qs_layout.addWidget(self.country_input, 1)

        save_qs_btn = QPushButton("Save")
        save_qs_btn.setCursor(Qt.PointingHandCursor)
        save_qs_btn.setStyleSheet(
            "QPushButton { background: #2563EB; color: white; font-weight: 600; "
            "padding: 5px 12px; border-radius: 6px; }"
        )
        save_qs_btn.clicked.connect(self._save_quick_personalization)
        qs_layout.addWidget(save_qs_btn)
        card_layout.addWidget(self.quick_setup_frame)

        # Interactive Action Row (Try Live + Full Manual)
        action_row = QHBoxLayout()
        action_row.setSpacing(10)

        self.try_live_btn = QPushButton("🔍 Show Me This Section Live")
        self.try_live_btn.setCursor(Qt.PointingHandCursor)
        self.try_live_btn.setStyleSheet(
            "QPushButton { background-color: rgba(16, 185, 129, 0.18); color: #34D399; "
            "border: 1px solid #10B981; border-radius: 8px; padding: 6px 14px; font-weight: 600; }"
            "QPushButton:hover { background-color: rgba(16, 185, 129, 0.30); }"
        )
        self.try_live_btn.clicked.connect(self._on_try_live_clicked)
        action_row.addWidget(self.try_live_btn)

        self.manual_btn = QPushButton("📖 Open Full User Manual (F1)")
        self.manual_btn.setCursor(Qt.PointingHandCursor)
        self.manual_btn.setStyleSheet(
            "QPushButton { background-color: rgba(255, 255, 255, 0.08); color: #E2E8F0; "
            "border: 1px solid rgba(255, 255, 255, 0.18); border-radius: 8px; padding: 6px 14px; }"
            "QPushButton:hover { background-color: rgba(255, 255, 255, 0.15); }"
        )
        self.manual_btn.clicked.connect(self._on_open_manual_clicked)
        action_row.addWidget(self.manual_btn)

        self.sample_project_btn = QPushButton("✨ Load Sample Demo Project")
        self.sample_project_btn.setCursor(Qt.PointingHandCursor)
        self.sample_project_btn.setStyleSheet(
            "QPushButton { background-color: rgba(59, 130, 246, 0.20); color: #93C5FD; "
            "border: 1px solid #3B82F6; border-radius: 8px; padding: 6px 14px; font-weight: 600; }"
            "QPushButton:hover { background-color: rgba(59, 130, 246, 0.35); }"
        )
        self.sample_project_btn.clicked.connect(self._on_toggle_sample_project)
        action_row.addWidget(self.sample_project_btn)
        self._refresh_sample_button_label()

        action_row.addStretch()
        card_layout.addLayout(action_row)

        # Bottom Navigation Footer
        footer_row = QHBoxLayout()
        footer_row.setSpacing(10)

        self.prev_btn = QPushButton("← Previous")
        self.prev_btn.setCursor(Qt.PointingHandCursor)
        self.prev_btn.setStyleSheet(
            "QPushButton { background-color: #1E293B; color: #F8FAFC; border: 1px solid #475569; "
            "border-radius: 8px; padding: 8px 16px; font-weight: 600; }"
            "QPushButton:disabled { color: #64748B; border-color: #334155; }"
        )
        self.prev_btn.clicked.connect(self.prev_step)
        footer_row.addWidget(self.prev_btn)

        footer_row.addStretch()

        self.next_btn = QPushButton("Next Step →")
        self.next_btn.setObjectName("PrimaryButton")
        self.next_btn.setCursor(Qt.PointingHandCursor)
        self.next_btn.setStyleSheet(
            "QPushButton { background-color: #E95420; color: #FFFFFF; border: none; "
            "border-radius: 8px; padding: 8px 20px; font-weight: 700; font-size: 13px; }"
            "QPushButton:hover { background-color: #FF6933; }"
        )
        self.next_btn.clicked.connect(self.next_step)
        footer_row.addWidget(self.next_btn)

        card_layout.addLayout(footer_row)

        center_row.addWidget(self.card)
        center_row.addStretch(1)
        root_layout.addLayout(center_row)
        root_layout.addStretch(1)

    def _save_quick_personalization(self):
        if not self.settings_manager:
            return
        name = self.name_input.text().strip()
        country = self.country_input.text().strip()
        if name:
            self.settings_manager.set("user_salutation", name)
            self.settings_manager.set("user_display_name", name)
        if country:
            self.settings_manager.set("user_country", country)

    def _load_step(self, index: int, navigate_live: bool = True):
        if index < 0 or index >= len(TOUR_STEPS):
            return
        self.current_step_index = index
        step = TOUR_STEPS[index]

        self.badge_label.setText(step["badge"])
        self.title_label.setText(step["title"])
        self.summary_label.setText(step["summary"])

        bullets = step.get("bullets", [])
        for i, lbl in enumerate(self.bullet_labels):
            if i < len(bullets):
                lbl.setText(bullets[i])
                lbl.setVisible(True)
            else:
                lbl.setVisible(False)

        self.quick_setup_frame.setVisible(index == 0)
        self.try_live_btn.setText(f"🔍 {step.get('action_label', 'Show Section Live')}")

        # Update dot styles
        for i, dot in enumerate(self.step_dot_buttons):
            if i == index:
                dot.setStyleSheet(
                    "QPushButton { background-color: #E95420; color: #FFFFFF; font-weight: 700; "
                    "border-radius: 13px; border: none; font-size: 11px; }"
                )
            elif i < index:
                dot.setStyleSheet(
                    "QPushButton { background-color: rgba(16, 185, 129, 0.25); color: #34D399; "
                    "font-weight: 600; border-radius: 13px; border: 1px solid #10B981; font-size: 11px; }"
                )
            else:
                dot.setStyleSheet(
                    "QPushButton { background-color: rgba(255, 255, 255, 0.08); color: #94A3B8; "
                    "border-radius: 13px; border: none; font-size: 11px; }"
                )

        self.prev_btn.setEnabled(index > 0)
        if index == len(TOUR_STEPS) - 1:
            self.next_btn.setText("🚀 Finish & Start Todo Bird")
        else:
            self.next_btn.setText("Next Step →")

        if navigate_live and self.main_window and hasattr(self.main_window, "navigation_controller"):
            sec = step.get("section")
            if sec:
                try:
                    self.main_window.navigation_controller.set_active_section(sec)
                except Exception:
                    pass

        self.update()

    def _on_try_live_clicked(self):
        step = TOUR_STEPS[self.current_step_index]
        sec = step.get("section")
        if self.main_window and hasattr(self.main_window, "navigation_controller") and sec:
            self.main_window.navigation_controller.set_active_section(sec)
        self.update()

    def _refresh_sample_button_label(self):
        db = getattr(self.main_window, "db_manager", None) if self.main_window else None
        if not db:
            return
        from todo_bird_app.services.sample_project_service import SampleProjectService
        if SampleProjectService.has_sample_project(db):
            self.sample_project_btn.setText("🗑️ Clear Demo Project")
        else:
            self.sample_project_btn.setText("✨ Load Sample Demo Project")

    def _on_toggle_sample_project(self):
        db = getattr(self.main_window, "db_manager", None) if self.main_window else None
        if not db:
            return
        from todo_bird_app.services.sample_project_service import SampleProjectService
        if SampleProjectService.has_sample_project(db):
            SampleProjectService.remove_sample_project(db)
        else:
            pid = SampleProjectService.load_sample_project(db)
            if pid and self.main_window and hasattr(self.main_window, "navigation_controller"):
                self.main_window.navigation_controller.set_active_section("gantt", project_id=pid)
        self._refresh_sample_button_label()
        if self.main_window and hasattr(self.main_window, "navigation_controller"):
            self.main_window.navigation_controller.refresh_active_view()

    def _on_open_manual_clicked(self):
        self._save_quick_personalization()
        if self.settings_manager:
            self.settings_manager.set("onboarding_completed", True)
        self.hide()
        self.open_manual_requested.emit()

    def next_step(self):
        if self.current_step_index == 0:
            self._save_quick_personalization()
        if self.current_step_index + 1 < len(TOUR_STEPS):
            self._load_step(self.current_step_index + 1, navigate_live=True)
        else:
            self.finish_tour()

    def prev_step(self):
        if self.current_step_index > 0:
            self._load_step(self.current_step_index - 1, navigate_live=True)

    def finish_tour(self):
        self._save_quick_personalization()
        if self.settings_manager:
            self.settings_manager.set("onboarding_completed", True)
        self.hide()
        self.tour_completed.emit()

    def _resolve_spotlight_rect(self) -> Optional[QRect]:
        """Finds the bounding rect of the current step's target widget in overlay coordinates."""
        if not self.main_window:
            return None
        step = TOUR_STEPS[self.current_step_index]
        target_name = step.get("target")
        if not target_name:
            return None

        try:
            hb = getattr(self.main_window, "headerbar", None)
            if target_name == "sidebar":
                w = getattr(self.main_window, "sidebar", None)
                if w and w.isVisible():
                    tl = self.mapFromGlobal(w.mapToGlobal(QPoint(0, 0)))
                    return QRect(tl, w.size()).adjusted(-4, -4, 4, 4)
            elif target_name == "add_btn" and hb:
                w = getattr(hb, "add_btn", None)
                if w and w.isVisible():
                    tl = self.mapFromGlobal(w.mapToGlobal(QPoint(0, 0)))
                    return QRect(tl, w.size()).adjusted(-6, -6, 6, 6)
            elif target_name == "clock_and_razorpay" and hb:
                w1 = getattr(hb, "clock_btn", None)
                w2 = getattr(hb, "razorpay_btn", None)
                if w1 and w2 and w1.isVisible() and w2.isVisible():
                    tl1 = self.mapFromGlobal(w1.mapToGlobal(QPoint(0, 0)))
                    tl2 = self.mapFromGlobal(w2.mapToGlobal(QPoint(0, 0)))
                    r1 = QRect(tl1, w1.size())
                    r2 = QRect(tl2, w2.size())
                    return r1.united(r2).adjusted(-8, -6, 8, 6)
            elif target_name == "feedback_btn" and hb:
                w = getattr(hb, "feedback_btn", None)
                if w and w.isVisible():
                    tl = self.mapFromGlobal(w.mapToGlobal(QPoint(0, 0)))
                    return QRect(tl, w.size()).adjusted(-6, -6, 6, 6)
        except Exception:
            return None
        return None

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        full_rect = QRectF(self.rect())
        spotlight = self._resolve_spotlight_rect()

        if spotlight and not spotlight.isEmpty():
            outer_path = QPainterPath()
            outer_path.addRect(full_rect)

            hole_path = QPainterPath()
            hole_path.addRoundedRect(QRectF(spotlight), 10.0, 10.0)

            dim_path = outer_path.subtracted(hole_path)
            painter.fillPath(dim_path, QColor(8, 12, 22, 185))

            # Draw glowing spotlight ring around the target widget
            pen_glow = QPen(QColor(233, 84, 32, 110), 6.0)
            painter.setPen(pen_glow)
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(QRectF(spotlight).adjusted(-2, -2, 2, 2), 12.0, 12.0)

            pen_crisp = QPen(QColor("#E95420"), 2.5)
            painter.setPen(pen_crisp)
            painter.drawRoundedRect(QRectF(spotlight), 10.0, 10.0)
        else:
            painter.fillRect(full_rect, QColor(8, 12, 22, 175))

        painter.end()
        super().paintEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.finish_tour()
            event.accept()
            return
        elif event.key() in (Qt.Key_Right, Qt.Key_Return, Qt.Key_Enter):
            self.next_step()
            event.accept()
            return
        elif event.key() == Qt.Key_Left:
            self.prev_step()
            event.accept()
            return
        super().keyPressEvent(event)

