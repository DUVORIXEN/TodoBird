from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QFrame, QToolButton, QMenu
from PySide6.QtCore import Qt, QSize, Signal

from todo_bird_app.services.language_service import LanguageService, t

class HeaderBarWidget(QWidget):
    """
    GNOME AdwHeaderBar replica for TODO BIRD.
    """
    quick_add_requested = Signal()
    toggle_theme_requested = Signal()
    world_clock_requested = Signal()
    support_requested = Signal()
    feedback_requested = Signal()
    user_manual_requested = Signal()
    onboarding_tour_requested = Signal()
    diagnostics_requested = Signal()
    about_requested = Signal()
    language_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("HeaderBar")
        self.setMinimumHeight(52)
        self._current_theme_mode = "dark"
        self._is_supporter = False
        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(10)

        # Title & Subtitle container
        titles_layout = QHBoxLayout()
        titles_layout.setSpacing(8)

        self.title_label = QLabel("Inbox")
        self.title_label.setObjectName("HeaderTitle")

        self.subtitle_label = QLabel("— All captured tasks")
        self.subtitle_label.setObjectName("HeaderSubtitle")

        titles_layout.addWidget(self.title_label)
        titles_layout.addWidget(self.subtitle_label)
        titles_layout.addStretch()

        layout.addLayout(titles_layout, 1)

        from todo_bird_app.services.icon_service import IconService as _IconService

        # Quick Add Button
        self.add_btn = QPushButton(t("+  New Task"))
        self.add_btn.setObjectName("PrimaryButton")
        self.add_btn.setCursor(Qt.PointingHandCursor)
        self.add_btn.clicked.connect(self.quick_add_requested.emit)
        layout.addWidget(self.add_btn)

        # Language Button — one click to switch UI language from anywhere
        self.language_btn = QPushButton()
        self.language_btn.setObjectName("LanguageButton")
        self.language_btn.setCursor(Qt.PointingHandCursor)
        self.language_btn.setToolTip(t("UI Language"))
        self._language_menu = QMenu(self.language_btn)
        self._rebuild_language_menu()
        self.language_btn.setMenu(self._language_menu)
        layout.addWidget(self.language_btn)
        self._refresh_language_button_text()

        # World Clock Button
        self.clock_btn = QPushButton(t("World Clock"))
        self.clock_btn.setIcon(_IconService.get_icon("globe", "#9AA6BD"))
        self.clock_btn.setIconSize(QSize(16, 16))
        self.clock_btn.setObjectName("WorldClockButton")
        self.clock_btn.setCursor(Qt.PointingHandCursor)
        self.clock_btn.setToolTip(t("Open World Clock (Ctrl+Alt+W)"))
        self.clock_btn.clicked.connect(self.world_clock_requested.emit)
        layout.addWidget(self.clock_btn)

        # Razorpay Support Button — directly beside World Clock Button
        self.razorpay_btn = QPushButton(t("Razorpay"))
        self.razorpay_btn.setIcon(_IconService.get_icon("heart", "#F43F5E"))
        self.razorpay_btn.setIconSize(QSize(16, 16))
        self.razorpay_btn.setObjectName("RazorpaySupportButton")
        self.razorpay_btn.setCursor(Qt.PointingHandCursor)
        self.razorpay_btn.setToolTip(t("Support Todo Bird via Razorpay (https://razorpay.me/@duvorixen)"))
        self.razorpay_btn.clicked.connect(self.support_requested.emit)
        layout.addWidget(self.razorpay_btn)

        # Feedback & Rating Button — quick access to share how users feel
        self.feedback_btn = QPushButton(t("Feedback"))
        self.feedback_btn.setIcon(_IconService.get_icon("chat", "#9AA6BD"))
        self.feedback_btn.setIconSize(QSize(16, 16))
        self.feedback_btn.setObjectName("HeaderFeedbackButton")
        self.feedback_btn.setCursor(Qt.PointingHandCursor)
        self.feedback_btn.setToolTip(t("Share how you feel about Todo Bird & view community pulse"))
        self.feedback_btn.clicked.connect(self.feedback_requested.emit)
        layout.addWidget(self.feedback_btn)

        # User Guide / Teaching Manual Button
        self.guide_btn = QPushButton(t("Guide"))
        self.guide_btn.setIcon(_IconService.get_icon("book", "#9AA6BD"))
        self.guide_btn.setIconSize(QSize(16, 16))
        self.guide_btn.setObjectName("HeaderGuideButton")
        self.guide_btn.setCursor(Qt.PointingHandCursor)
        self.guide_btn.setToolTip(t("Open User Manual & Interactive Teaching Tour (F1)"))
        self.guide_btn.clicked.connect(self.user_manual_requested.emit)
        layout.addWidget(self.guide_btn)

        # Theme Toggle Button
        self.theme_btn = QPushButton(t("Mode"))
        self.theme_btn.setCursor(Qt.PointingHandCursor)
        self.theme_btn.clicked.connect(self.toggle_theme_requested.emit)
        layout.addWidget(self.theme_btn)

        # Help Menu Button
        self.help_btn = QToolButton()
        self.help_btn.setText("? Help")
        self.help_btn.setCursor(Qt.PointingHandCursor)
        self.help_btn.setPopupMode(QToolButton.InstantPopup)

        self.help_menu = QMenu(self.help_btn)

        self.action_user_manual = self.help_menu.addAction(t("📖 User Manual & Guide (F1)"))
        self.action_user_manual.triggered.connect(self.user_manual_requested.emit)

        self.action_tour = self.help_menu.addAction(t("🧭 Interactive Teaching Tour"))
        self.action_tour.triggered.connect(self.onboarding_tour_requested.emit)

        self.help_menu.addSeparator()

        self.action_feedback = self.help_menu.addAction(t("💬 Share Feedback & Rating"))
        self.action_feedback.triggered.connect(self.feedback_requested.emit)

        self.action_support = self.help_menu.addAction(t("💜 Support Todo Bird (Razorpay)"))
        self.action_support.triggered.connect(self.support_requested.emit)

        self.help_menu.addSeparator()

        self.action_diagnostics = self.help_menu.addAction(t("Diagnostics"))
        self.action_diagnostics.triggered.connect(self.diagnostics_requested.emit)

        self.action_about = self.help_menu.addAction(t("About"))
        self.action_about.triggered.connect(self.about_requested.emit)

        self.help_btn.setMenu(self.help_menu)
        layout.addWidget(self.help_btn)

    def set_section_title(self, title: str, subtitle: str = ""):
        self.title_label.setText(title)
        self.subtitle_label.setText(f"— {subtitle}" if subtitle else "")

    def set_supporter_badge(self, is_supporter: bool):
        """Updates the Razorpay button to display a Supporter star badge when enabled."""
        self._is_supporter = bool(is_supporter)
        base_lbl = t("Razorpay")
        self.razorpay_btn.setText(f"{base_lbl} ★" if self._is_supporter else base_lbl)
        if self._is_supporter:
            self.razorpay_btn.setToolTip(t("Thank you for being a Todo Bird Supporter! 💜 (Razorpay)"))
        else:
            self.razorpay_btn.setToolTip(t("Support Todo Bird via Razorpay (https://razorpay.me/@duvorixen)"))

    # ------------------------------------------------------------------
    # Language selection & live retranslation
    # ------------------------------------------------------------------

    def _rebuild_language_menu(self):
        self._language_menu.clear()
        service = LanguageService.instance()
        current = service.current_language()
        for code, native, _english, flag, _rtl in LanguageService.available_languages():
            label = f"{flag}  {native}" if flag else native
            action = self._language_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(code == current)
            action.triggered.connect(
                lambda _checked=False, c=code: self.language_selected.emit(c)
            )

    def _refresh_language_button_text(self):
        service = LanguageService.instance()
        current = service.current_language()
        flag = ""
        for code, _native, _english, f, _rtl in LanguageService.available_languages():
            if code == current:
                flag = f
                break
        self.language_btn.setText(f"{flag} {current.upper()}")

    def retranslate_ui(self):
        """Live retranslation of every header-bar string (language switch)."""
        self.add_btn.setText(t("+  New Task"))
        self.clock_btn.setText(t("World Clock"))
        self.clock_btn.setToolTip(t("Open World Clock (Ctrl+Alt+W)"))
        base_lbl = t("Razorpay")
        self.razorpay_btn.setText(f"{base_lbl} ★" if self._is_supporter else base_lbl)
        self.razorpay_btn.setToolTip(t("Support Todo Bird via Razorpay (https://razorpay.me/@duvorixen)"))
        self.feedback_btn.setText(t("Feedback"))
        self.feedback_btn.setToolTip(t("Share how you feel about Todo Bird & view community pulse"))
        self.guide_btn.setText(t("Guide"))
        self.guide_btn.setToolTip(t("Open User Manual & Interactive Teaching Tour (F1)"))
        self.language_btn.setToolTip(t("UI Language"))
        self._refresh_language_button_text()
        self._rebuild_language_menu()
        self.update_theme_icon(self._current_theme_mode)

    def update_theme_icon(self, mode: str):
        """Updates theme button icon/text based on active mode."""
        self._current_theme_mode = str(mode)
        if str(mode).lower() == "dark":
            self.theme_btn.setText(t("Light"))
            from todo_bird_app.services.icon_service import IconService as _IS
            self.theme_btn.setIcon(_IS.get_icon("sun", "#9AA6BD"))
            self.theme_btn.setIconSize(QSize(16, 16))
            self.theme_btn.setToolTip(t("Switch to Light Mode"))
        else:
            self.theme_btn.setText(t("Dark"))
            from todo_bird_app.services.icon_service import IconService as _IS
            self.theme_btn.setIcon(_IS.get_icon("moon", "#9AA6BD"))
            self.theme_btn.setIconSize(QSize(16, 16))
            self.theme_btn.setToolTip(t("Switch to Dark Mode"))
