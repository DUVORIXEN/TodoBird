"""
TODO BIRD — IN-APP USER MANUAL & INTERACTIVE LEARNING CENTER
Comprehensive searchable user guide, workflow reference, keyboard shortcuts cheat-sheet,
and one-click interactive tour launcher.
"""

import logging
from typing import List, Dict, Any
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QWidget, QFrame, QGridLayout
)
from PySide6.QtCore import Qt, Signal

from todo_bird_app.views.base_view import BaseView
from todo_bird_app.__version__ import __version__

logger = logging.getLogger(__name__)


MANUAL_CHAPTERS: List[Dict[str, Any]] = [
    {
        "id": "getting_started",
        "icon": "🚀",
        "title": "1. Getting Started & The 4-Stage Productivity Workflow",
        "section_link": "dashboard",
        "link_label": "Go to Dashboard",
        "summary": "Understand how Todo Bird turns scattered ideas into structured, measurable execution.",
        "items": [
            ("Stage 1 — Capture (Inbox)", "Press Ctrl+N or click '+ New Task' from anywhere. Drop ideas, tasks, and commitments into Inbox immediately so nothing is forgotten."),
            ("Stage 2 — Structure & Plan (Projects & WBS)", "Assign tasks to Projects, break large initiatives into multi-level WBS subtasks, estimate duration/effort, and link dependencies."),
            ("Stage 3 — Execute (Today & Focus Mode)", "Start your day in Today's Plan. Launch Focus Mode to work deeply on one task at a time while automatically recording actual effort."),
            ("Stage 4 — Review & Adapt (Daily Review & Gantt)", "Compare your Baseline Plan against Actual execution in Daily Review, Gantt Timeline, and Productivity Analytics."),
        ],
    },
    {
        "id": "navigation_dock",
        "icon": "🧭",
        "title": "2. Adaptive Navigation Dock & Personalization",
        "section_link": "settings",
        "link_label": "Customize in Settings",
        "summary": "Personalize where your navigation lives and which sections appear first.",
        "items": [
            ("Drag & Drop Reordering", "Click and drag any destination in the Sidebar to reorder your navigation bar. Or focus an item and press Alt+Shift+Up/Down."),
            ("4 Dock Positions", "Move the Navigation Dock to Left, Right, Top, or Bottom from Settings → Appearance & Navigation."),
            ("6 Visual Styles", "Switch between Expanded Sidebar, Compact Icon Rail, Slim, Tiles, Glass Dock, or Minimal styles."),
            ("Favorites & Hidden Sections", "Right-click any navigation item to mark it as Favorite or hide sections you rarely use."),
        ],
    },
    {
        "id": "wbs_hierarchy",
        "icon": "🌳",
        "title": "3. Projects, Subtasks & WBS Hierarchy Authority",
        "section_link": "projects",
        "link_label": "Open Projects & WBS",
        "summary": "Build multi-level Work Breakdown Structures with automatic parent summary rollups.",
        "items": [
            ("Infinite Subtask Nesting", "Inside any task or the WBS Tree View, add child subtasks and sub-subtasks to break down complex deliverables."),
            ("Automatic Parent Rollups", "Parent summary rows automatically compute rolled-up Planned Duration, Actual Effort, Progress %, and earliest/latest schedule dates."),
            ("Pinning Important Tasks", "Pin high-priority tasks or subtasks with custom pin colors so they stay anchored at the top of your lists."),
            ("Rich Text Descriptions", "Format task notes with Bold (Ctrl+B), Italic (Ctrl+I), Underline (Ctrl+U), bullet lists, and custom typography."),
        ],
    },
    {
        "id": "gantt_cpm",
        "icon": "📊",
        "title": "4. Interactive Gantt Timeline & Critical Path (CPM)",
        "section_link": "gantt",
        "link_label": "Open Gantt Timeline",
        "summary": "Enterprise scheduling engine with dependencies, critical path highlighting, and Plan vs. Actual bars.",
        "items": [
            ("4 Dependency Types", "Link tasks using Finish-to-Start (FS), Start-to-Start (SS), Finish-to-Finish (FF), or Start-to-Finish (SF) with optional lead/lag days."),
            ("Interactive Bar Editing", "Drag a task bar horizontally to shift dates, drag bar edges to resize duration, or double-click any bar to open the full editor."),
            ("Plan vs. Actual Comparison", "Blue bars represent your Planned Schedule; Emerald Green/Red bars show Actual Execution and schedule variance."),
            ("Working Calendar Authority", "Configure working weekdays (e.g., Mon–Fri or Mon–Sat) and daily capacity hours in Settings so CPM math skips non-working days."),
        ],
    },
    {
        "id": "world_clock_razorpay",
        "icon": "🌐",
        "title": "5. Global World Clock & 💜 Razorpay Support Bar",
        "section_link": "world_clock",
        "link_label": "Open World Clock View",
        "summary": "Track global timezones offline and support Todo Bird directly from the top Header Bar.",
        "items": [
            ("World Clock Button (Ctrl+Alt+W)", "Click 'World Clock' in the top bar for a quick floating popover, or open the full World Clock View in the sidebar."),
            ("249 Countries & 5 Visual Themes", "Add any city worldwide offline. Choose Analog or Digital clocks across Modern Minimal, Classic Luxury, Cyberpunk HUD, Retro Matrix LCD, or Solar Day-Night themes."),
            ("Cross-Timezone Meeting Scrubber", "Drag the interactive time slider in World Clock View to find the best meeting overlap across multiple international teams."),
            ("💜 Razorpay Support Button (Beside World Clock)", "Click 'Razorpay' right beside the World Clock button in the top bar to support Todo Bird's independent development via https://razorpay.me/@duvorixen."),
        ],
    },
    {
        "id": "voice_reminders",
        "icon": "🎙️",
        "title": "6. Avocet Voice Companion & Smart Reminders",
        "section_link": "settings",
        "link_label": "Configure Voice & Reminders",
        "summary": "Local-time aware voice greetings and deterministic reminder triggers.",
        "items": [
            ("Avocet Desktop Companion", "Greets you with uplifting morning, afternoon, evening, or night messages tailored to your name/salutation."),
            ("Startup & Periodic Reminders", "Set tasks to remind you on every app open, first launch of the day, system login, or at exact scheduled times."),
            ("Snooze & Quick Complete", "When a Reminder Dialog pops up, snooze it by 5/15/60 minutes or mark the task Completed in one click."),
        ],
    },
    {
        "id": "feedback_community",
        "icon": "💬",
        "title": "7. Sharing How You Feel — Feedback, Ratings & Community Pulse",
        "section_link": "feedback",
        "link_label": "Open Feedback & Community",
        "summary": "Let the creator (DUVORIXEN) know who is using Todo Bird and how you feel about the app.",
        "items": [
            ("Rate & Share Your Mood", "Click 'Feedback' in the Header Bar or Sidebar. Pick your mood emoji (🤩 Loving It, 😊 Happy, 🙂 Good, 🤔 Confused, 🐛 Bug) and 1–5 Star Rating."),
            ("Community Check-In", "Optionally share your Name, Role/Profession, and Country so we know who is downloading and enjoying Todo Bird across Windows & Ubuntu."),
            ("Direct Delivery to Developer", "Submit feedback directly via our 1-Click GitHub Community Wall, configured Cloud Webhook, or official Microsoft Store / Ubuntu Snap Store review links!"),
        ],
    },
]

SHORTCUTS_REFERENCE = [
    ("Ctrl + N", "Create New Task from anywhere"),
    ("Ctrl + K", "Open Quick Command Palette"),
    ("Ctrl + Alt + W", "Toggle Global World Clock Popover"),
    ("F1", "Open User Manual & Interactive Guide"),
    ("Ctrl + ,", "Open Preferences & Settings"),
    ("Ctrl + 1 .. 7", "Jump to Dashboard, Inbox, Today, Gantt, Projects, Calendar, Analytics"),
    ("Alt + Shift + Arrows", "Reorder focused Sidebar Navigation item"),
    ("Ctrl + B / I / U", "Bold / Italic / Underline in Task Description Editor"),
    ("Ctrl + Q", "Cleanly Quit Todo Bird"),
]


class UserManualView(BaseView):
    """
    Searchable In-App User Manual & Interactive Teaching Center.
    """
    start_tour_requested = Signal()
    navigate_section_requested = Signal(str)
    support_requested = Signal()

    def __init__(self, db_manager, settings_manager, parent=None):
        super().__init__(
            db_manager,
            settings_manager,
            title="User Manual & Interactive Guide",
            subtitle=f"Complete Feature Walkthrough, Workflows & Shortcuts (v{__version__})",
            parent=parent,
        )
        self.chapter_cards: List[QFrame] = []
        self._init_ui()

    def _init_ui(self):
        # Top Hero Action Bar
        hero_frame = QFrame()
        hero_frame.setObjectName("CardWidget")
        hero_layout = QVBoxLayout(hero_frame)
        hero_layout.setContentsMargins(18, 16, 18, 16)
        hero_layout.setSpacing(12)

        top_row = QHBoxLayout()
        hero_title = QLabel("📖 Welcome to the Todo Bird Official User Manual & Teaching Center")
        hero_title.setStyleSheet("font-weight: 700; font-size: 15px; color: #E95420;")
        top_row.addWidget(hero_title)
        top_row.addStretch()

        self.launch_tour_btn = QPushButton("🧭 Start Interactive Teaching Tour")
        self.launch_tour_btn.setObjectName("PrimaryButton")
        self.launch_tour_btn.setCursor(Qt.PointingHandCursor)
        self.launch_tour_btn.clicked.connect(self.start_tour_requested.emit)
        top_row.addWidget(self.launch_tour_btn)

        self.sample_demo_btn = QPushButton("✨ Load Sample Demo Project")
        self.sample_demo_btn.setCursor(Qt.PointingHandCursor)
        self.sample_demo_btn.clicked.connect(self._on_toggle_sample_demo)
        top_row.addWidget(self.sample_demo_btn)
        self._refresh_sample_demo_btn()

        self.feedback_jump_btn = QPushButton("💬 Rate & Share Feedback")
        self.feedback_jump_btn.setCursor(Qt.PointingHandCursor)
        self.feedback_jump_btn.clicked.connect(lambda: self.navigate_section_requested.emit("feedback"))
        top_row.addWidget(self.feedback_jump_btn)

        self.support_jump_btn = QPushButton("💜 Support (Razorpay)")
        self.support_jump_btn.setCursor(Qt.PointingHandCursor)
        self.support_jump_btn.clicked.connect(self.support_requested.emit)
        top_row.addWidget(self.support_jump_btn)

        hero_layout.addLayout(top_row)

        # Search Filter Bar
        search_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Search the User Manual (e.g. 'Gantt', 'WBS', 'World Clock', 'Razorpay', 'Shortcuts', 'Reminders')...")
        self.search_input.textChanged.connect(self._on_search_changed)
        search_row.addWidget(self.search_input, 1)

        clear_btn = QPushButton("Clear")
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.clicked.connect(self.search_input.clear)
        search_row.addWidget(clear_btn)

        hero_layout.addLayout(search_row)
        self.main_layout.addWidget(hero_frame)

        # Scrollable Chapters Area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        content_widget = QWidget()
        self.content_layout = QVBoxLayout(content_widget)
        self.content_layout.setContentsMargins(0, 4, 8, 24)
        self.content_layout.setSpacing(14)

        # Build Chapter Cards
        for chapter in MANUAL_CHAPTERS:
            card = self._build_chapter_card(chapter)
            self.content_layout.addWidget(card)
            self.chapter_cards.append(card)

        # Build Keyboard Shortcuts Reference Card
        self.shortcuts_card = self._build_shortcuts_card()
        self.content_layout.addWidget(self.shortcuts_card)

        self.content_layout.addStretch(1)
        scroll.setWidget(content_widget)
        self.main_layout.addWidget(scroll, 1)

    def _build_chapter_card(self, chapter: Dict[str, Any]) -> QFrame:
        card = QFrame()
        card.setObjectName("CardWidget")
        searchable_blob = (
            chapter["title"] + " " + chapter["summary"] + " " +
            " ".join(f"{k} {v}" for k, v in chapter["items"])
        ).lower()
        card.setProperty("searchBlob", searchable_blob)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        header_row = QHBoxLayout()
        title_lbl = QLabel(f"{chapter['icon']}  {chapter['title']}")
        title_lbl.setStyleSheet("font-weight: 700; font-size: 14px;")
        header_row.addWidget(title_lbl)
        header_row.addStretch()

        sec_link = chapter.get("section_link")
        if sec_link:
            jump_btn = QPushButton(f"{chapter.get('link_label', 'Open')} →")
            jump_btn.setCursor(Qt.PointingHandCursor)
            jump_btn.clicked.connect(lambda _c=False, s=sec_link: self.navigate_section_requested.emit(s))
            header_row.addWidget(jump_btn)

        layout.addLayout(header_row)

        sum_lbl = QLabel(chapter["summary"])
        sum_lbl.setWordWrap(True)
        sum_lbl.setStyleSheet("color: #94A3B8; font-size: 12.5px;")
        layout.addWidget(sum_lbl)

        for item_title, item_desc in chapter["items"]:
            item_row = QVBoxLayout()
            item_row.setSpacing(2)
            t_lbl = QLabel(f"• {item_title}")
            t_lbl.setStyleSheet("font-weight: 600; font-size: 12.5px; color: #E95420;")
            d_lbl = QLabel(f"   {item_desc}")
            d_lbl.setWordWrap(True)
            d_lbl.setStyleSheet("font-size: 12px;")
            item_row.addWidget(t_lbl)
            item_row.addWidget(d_lbl)
            layout.addLayout(item_row)

        return card

    def _build_shortcuts_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("CardWidget")
        blob = "keyboard shortcuts hotkeys f1 ctrl+n ctrl+k ctrl+alt+w " + " ".join(
            f"{k} {v}" for k, v in SHORTCUTS_REFERENCE
        ).lower()
        card.setProperty("searchBlob", blob)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        title_lbl = QLabel("⌨️  8. Global Keyboard Shortcuts & Hotkeys Cheat-Sheet")
        title_lbl.setStyleSheet("font-weight: 700; font-size: 14px;")
        layout.addWidget(title_lbl)

        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(8)

        for row_idx, (keys, desc) in enumerate(SHORTCUTS_REFERENCE):
            k_lbl = QLabel(keys)
            k_lbl.setStyleSheet(
                "font-family: monospace; font-weight: 700; color: #38BDF8; "
                "background: rgba(56, 189, 248, 0.12); padding: 3px 8px; border-radius: 5px;"
            )
            d_lbl = QLabel(desc)
            grid.addWidget(k_lbl, row_idx, 0)
            grid.addWidget(d_lbl, row_idx, 1)

        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        return card

    def _on_search_changed(self, text: str):
        query = str(text or "").strip().lower()
        for card in self.chapter_cards + [self.shortcuts_card]:
            blob = str(card.property("searchBlob") or "")
            card.setVisible(not query or (query in blob))

    def _refresh_sample_demo_btn(self):
        if not self.db_manager or not hasattr(self, "sample_demo_btn"):
            return
        from todo_bird_app.services.sample_project_service import SampleProjectService
        if SampleProjectService.has_sample_project(self.db_manager):
            self.sample_demo_btn.setText("🗑️ Remove Demo Project")
        else:
            self.sample_demo_btn.setText("✨ Load Sample Demo Project")

    def _on_toggle_sample_demo(self):
        if not self.db_manager:
            return
        from todo_bird_app.services.sample_project_service import SampleProjectService
        if SampleProjectService.has_sample_project(self.db_manager):
            SampleProjectService.remove_sample_project(self.db_manager)
            self._refresh_sample_demo_btn()
        else:
            SampleProjectService.load_sample_project(self.db_manager)
            self._refresh_sample_demo_btn()
            self.navigate_section_requested.emit("gantt")

    def refresh_data(self):
        self._refresh_sample_demo_btn()

