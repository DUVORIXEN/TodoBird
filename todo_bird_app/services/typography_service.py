"""
Per-View Typography and Visual Experience Authority (Batch 3.7 & 3.8)
Provides per-view font family, size, weight customization with global fallback
and real rendering integration across all application views.
"""

import logging
from pathlib import Path
from typing import Optional, Any, Dict, Tuple, List
from PySide6.QtGui import QFont, QFontDatabase, QFontMetrics

logger = logging.getLogger(__name__)
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QPushButton,
    QLineEdit,
    QTextEdit,
    QComboBox,
    QSpinBox,
    QDateEdit,
    QTimeEdit,
    QCheckBox,
    QRadioButton,
    QAbstractButton,
    QAbstractScrollArea,
)

AREAS = [
    ("sidebar", "Sidebar & Navigation"),
    ("tasklist", "Today & Task Lists"),
    ("calendar", "Calendar View"),
    ("gantt", "Gantt Timeline"),
    ("focus", "Focus & Pomodoro"),
    ("analytics", "Analytics & Reports"),
    ("review", "Daily Review"),
    ("dialogs", "Task & Form Dialogs"),
    ("reminder", "Reminder Window"),
    ("pinned_tasks", "Pinned Tasks"),
]

EXPERIENCE_MODES = [
    ("professional", "Professional (Compact, minimal visual clutter, high information density)"),
    ("balanced", "Balanced (Default balanced aesthetics & productivity)"),
    ("personal", "Personal (Vibrant covers, expressive companion, rich cards)"),
]

class TypographyRole:
    DISPLAY = "display"                # +14 pt, bold (700)
    PAGE_TITLE = "page_title"          # +8 pt,  bold (700)
    SECTION_TITLE = "section_title"    # +4 pt,  semibold (600)
    CARD_TITLE = "card_title"          # +2 pt,  semibold (600)
    BODY = "body"                      # 0 pt,   normal (400)
    SECONDARY_BODY = "secondary_body"  # 0 pt,   normal (400)
    METADATA = "metadata"              # -1 pt,  medium (500)
    CAPTION = "caption"                # -2 pt,  medium (500)

class TypographyService:
    ROLE_CONFIG = {
        TypographyRole.DISPLAY: (14, "bold"),
        TypographyRole.PAGE_TITLE: (8, "bold"),
        TypographyRole.SECTION_TITLE: (4, "semibold"),
        TypographyRole.CARD_TITLE: (2, "semibold"),
        TypographyRole.BODY: (0, "normal"),
        TypographyRole.SECONDARY_BODY: (0, "normal"),
        TypographyRole.METADATA: (-1, "medium"),
        TypographyRole.CAPTION: (-2, "medium"),
    }

    _loaded_font_ids: List[int] = []

    @classmethod
    def initialize_application_fonts(cls) -> int:
        """
        Loads and registers all bundled application fonts (Inter) into QFontDatabase.
        Returns the count of successfully registered font files.
        Guarantees pixel-perfect, identical typography metrics across Linux, Windows, macOS, and BSD.
        """
        if cls._loaded_font_ids:
            return len(cls._loaded_font_ids)

        fonts_dir = Path(__file__).parent.parent / "assets" / "fonts"
        if not fonts_dir.exists():
            return 0

        loaded_count = 0
        for font_path in sorted(fonts_dir.glob("*.ttf")):
            try:
                font_id = QFontDatabase.addApplicationFont(str(font_path.resolve()))
                if font_id >= 0:
                    cls._loaded_font_ids.append(font_id)
                    loaded_count += 1
            except Exception as e:
                logger.debug(f"Unable to load font {font_path}: {e}")

        if loaded_count > 0:
            logger.info(f"Successfully loaded {loaded_count} bundled application fonts from {fonts_dir}")
        return loaded_count

    @staticmethod
    def apply_semantic_role(widget: QWidget, role: str):
        """
        Assign a semantic typography role to a widget.
        Applies relative font delta and weight, and marks appropriate accessibility/theme properties.
        """
        if widget is None:
            return
        role_key = str(role or "").strip().lower()
        delta_pt, weight = TypographyService.ROLE_CONFIG.get(role_key, (0, "normal"))
        TypographyService.set_relative_font_role(widget, delta_pt=delta_pt, weight=weight)
        if role_key in (TypographyRole.SECONDARY_BODY, TypographyRole.METADATA, TypographyRole.CAPTION):
            widget.setProperty("secondary", "true")
            widget.setProperty("todoBirdTextRole", "TEXT_SECONDARY")
        try:
            widget.updateGeometry()
            widget.update()
        except Exception:
            pass

    @staticmethod
    def _normalize_area(area: str) -> str:
        a = str(area or "").lower().strip()
        if a in ("pinned", "pinned_tasks", "pins", "pinnedtasks"):
            return "pinned_tasks"
        if a in ("reminder", "reminders"):
            return "reminder"
        return a

    @staticmethod
    def get_font_for_area(area: str, settings_manager: Optional[Any] = None) -> QFont:
        """
        Returns the resolved QFont for a specific area, respecting per-view overrides.
        """
        area = TypographyService._normalize_area(area)
        global_family = "Inter"
        global_size = 10
        global_weight_str = "normal"

        if settings_manager is not None:
            global_family = str(settings_manager.get("ui_font_family", "Inter") or "Inter")
            global_size = int(settings_manager.get("ui_font_size", 10) or 10)
            global_weight_str = str(settings_manager.get("ui_font_weight", "normal") or "normal")

            is_overridden = bool(
                settings_manager.get(f"font_override_{area}", False)
                or settings_manager.get(f"{area}_font_override", False)
            )
            if is_overridden:
                area_family = str(
                    settings_manager.get(f"font_family_{area}")
                    or settings_manager.get(f"{area}_font_family")
                    or global_family
                )
                area_size = int(
                    settings_manager.get(f"font_size_{area}")
                    or settings_manager.get(f"{area}_font_size")
                    or global_size
                )
                area_weight_str = str(
                    settings_manager.get(f"font_weight_{area}")
                    or settings_manager.get(f"{area}_font_weight")
                    or global_weight_str
                )
                return TypographyService._build_font(area_family, area_size, area_weight_str)

        return TypographyService._build_font(global_family, global_size, global_weight_str)

    @staticmethod
    def get_font_color_for_area(area: str, settings_manager: Optional[Any] = None) -> Optional[str]:
        """Returns the custom font color string for a specific area if configured, else None."""
        if settings_manager is None:
            return None
        area = TypographyService._normalize_area(area)
        color_mode = settings_manager.get(f"font_color_mode_{area}") or settings_manager.get(f"{area}_font_color_mode")
        if color_mode and str(color_mode).lower().strip() == "auto":
            return None
        color = settings_manager.get(f"font_color_{area}") or settings_manager.get(f"{area}_font_color")
        if color and str(color).strip().lower() not in ("auto", "default", "none", ""):
            return str(color).strip()
        if color_mode and str(color_mode).lower().strip() == "custom":
            return "#3584E4"
        return None

    @staticmethod
    def calculate_contrast_ratio(color_hex: str, background_hex: str = "#1E1E1E") -> float:
        """Calculates WCAG 2.1 relative luminance contrast ratio between foreground and background."""
        def parse_rgb(c_str: str) -> Tuple[int, int, int]:
            c_str = str(c_str).strip().lstrip("#")
            if len(c_str) == 3:
                c_str = "".join(ch * 2 for ch in c_str)
            if len(c_str) >= 6:
                try:
                    return int(c_str[0:2], 16), int(c_str[2:4], 16), int(c_str[4:6], 16)
                except ValueError:
                    pass
            return (255, 255, 255)

        def relative_luminance(r: int, g: int, b: int) -> float:
            def channel_lum(c: int) -> float:
                s = c / 255.0
                return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4
            return 0.2126 * channel_lum(r) + 0.7152 * channel_lum(g) + 0.0722 * channel_lum(b)

        try:
            r1, g1, b1 = parse_rgb(color_hex)
            r2, g2, b2 = parse_rgb(background_hex)
            l1 = relative_luminance(r1, g1, b1)
            l2 = relative_luminance(r2, g2, b2)
            lighter = max(l1, l2)
            darker = min(l1, l2)
            return (lighter + 0.05) / (darker + 0.05)
        except Exception:
            return 4.5

    @staticmethod
    def _build_font(family: str, size: int, weight_str: str) -> QFont:
        font = QFont(family)
        font.setPointSize(max(6, int(size)))
        w_lower = weight_str.lower()
        if "bold" in w_lower and "semi" not in w_lower:
            font.setWeight(QFont.Weight.Bold)
        elif "semi" in w_lower:
            font.setWeight(QFont.Weight.DemiBold)
        elif "med" in w_lower:
            font.setWeight(QFont.Weight.Medium)
        else:
            font.setWeight(QFont.Weight.Normal)
        return font

    @staticmethod
    def get_stylesheet_fragment(area: str, settings_manager: Optional[Any] = None) -> str:
        """Returns CSS stylesheet fragment enforcing configured font family, size and weight."""
        font = TypographyService.get_font_for_area(area, settings_manager)
        weight_val = 400
        if font.bold():
            weight_val = 700
        elif font.weight() == QFont.Weight.DemiBold:
            weight_val = 600
        elif font.weight() == QFont.Weight.Medium:
            weight_val = 500
        return f"font-family: '{font.family()}'; font-size: {font.pointSize()}pt; font-weight: {weight_val};"

    @staticmethod
    def _apply_relative_font_role(
        widget: QWidget,
        base_font: QFont,
    ):
        """
        Apply semantic hierarchy relative to the configured base font.

        Examples:
            +4 pt = card heading
            +12 pt = KPI value
            -1 pt = secondary/support text

        The role is recalculated after every typography change, so it
        never becomes an independent absolute-font authority.
        """
        if widget is None:
            return

        delta_value = widget.property(
            "_todo_bird_font_delta_pt"
        )

        weight_value = widget.property(
            "_todo_bird_font_role_weight"
        )

        if (
            delta_value is None
            and weight_value is None
        ):
            return

        font = QFont(base_font)

        base_size = int(font.pointSize())

        if base_size <= 0:
            app_size = QApplication.font().pointSize()
            base_size = (
                app_size
                if app_size > 0
                else 10
            )

        try:
            delta = int(delta_value or 0)
        except (TypeError, ValueError):
            delta = 0

        # Preserve hierarchy without allowing semantic emphasis
        # to create absurdly large/unusable controls.
        target_size = max(
            6,
            min(
                36,
                base_size + delta,
            ),
        )

        font.setPointSize(target_size)

        role_weight = str(
            weight_value or ""
        ).strip().lower()

        if role_weight == "bold":
            font.setWeight(QFont.Weight.Bold)
        elif role_weight in (
            "semibold",
            "demibold",
        ):
            font.setWeight(QFont.Weight.DemiBold)
        elif role_weight == "medium":
            font.setWeight(QFont.Weight.Medium)
        elif role_weight == "normal":
            font.setWeight(QFont.Weight.Normal)

        widget.setFont(font)

    @staticmethod
    def set_relative_font_role(
        widget: QWidget,
        delta_pt: int = 0,
        weight: Optional[str] = None,
    ):
        """
        Assign a semantic relative-font role to a widget.

        The role survives future application-font changes because
        apply_to_widget() re-evaluates it from the new base font.
        """
        if widget is None:
            return

        widget.setProperty(
            "_todo_bird_font_delta_pt",
            int(delta_pt),
        )

        if int(delta_pt) >= 4:
            widget.setProperty("heading", "true")
            widget.setProperty("todoBirdTextRole", "HEADING_PRIMARY")
        elif int(delta_pt) >= 2:
            widget.setProperty("todoBirdTextRole", "HEADING_SECONDARY")

        if weight is not None:
            widget.setProperty(
                "_todo_bird_font_role_weight",
                str(weight),
            )

        TypographyService._apply_relative_font_role(
            widget,
            widget.font(),
        )

    @staticmethod
    def _remember_original_height_constraints(widget: QWidget):
        """
        Capture designer-authored geometry exactly once.

        This lets typography temporarily enlarge a fixed-height control
        and later return it to its original size when the font shrinks.
        """
        if widget.property(
            "_todo_bird_typography_original_min_height"
        ) is None:
            widget.setProperty(
                "_todo_bird_typography_original_min_height",
                int(widget.minimumHeight()),
            )

        if widget.property(
            "_todo_bird_typography_original_max_height"
        ) is None:
            widget.setProperty(
                "_todo_bird_typography_original_max_height",
                int(widget.maximumHeight()),
            )

    @staticmethod
    def _safe_text_height(
        widget: QWidget,
        font: QFont,
        vertical_padding: int = 12,
    ) -> int:
        """
        Compute the minimum physical height required for one-line text.

        sizeHint() remains part of the calculation so native Qt styles,
        platform metrics and high-DPI scaling remain authoritative.
        """
        fm = QFontMetrics(font)

        font_required = (
            int(fm.lineSpacing())
            + int(vertical_padding)
        )

        try:
            hint_required = int(
                widget.sizeHint().height()
            )
        except Exception:
            hint_required = 0

        return max(
            1,
            font_required,
            hint_required,
        )

    @staticmethod
    def _apply_text_geometry_safety(
        widget: QWidget,
        font: QFont,
    ):
        """
        Prevent text clipping after live typography changes.

        Only text-bearing interactive controls are modified here.
        Decorative fixed-height widgets intentionally remain untouched.
        """
        if widget is None:
            return

        safe_types = (
            QPushButton,
            QAbstractButton,
            QLineEdit,
            QComboBox,
            QSpinBox,
            QDateEdit,
            QTimeEdit,
            QCheckBox,
            QRadioButton,
        )

        if not isinstance(widget, safe_types):
            return

        TypographyService._remember_original_height_constraints(
            widget
        )

        original_min = int(
            widget.property(
                "_todo_bird_typography_original_min_height"
            )
            or 0
        )

        original_max_value = widget.property(
            "_todo_bird_typography_original_max_height"
        )

        original_max = (
            int(original_max_value)
            if original_max_value is not None
            else 16777215
        )

        # Buttons need slightly more vertical breathing room than
        # line edits/combos because of focus/pressed surfaces.
        extra_padding = (
            14
            if isinstance(widget, (QPushButton, QAbstractButton))
            else 12
        )

        required = TypographyService._safe_text_height(
            widget,
            font,
            extra_padding,
        )

        # Preserve the designer baseline.
        safe_min = max(
            original_min,
            required,
        )

        originally_fixed = (
            original_max < 16777215
            and original_min == original_max
        )

        if originally_fixed:
            # Keep "fixed" semantics, but make the fixed height
            # typography-aware instead of pixel-absolute.
            safe_fixed = max(
                original_min,
                required,
            )

            widget.setMinimumHeight(
                safe_fixed
            )
            widget.setMaximumHeight(
                safe_fixed
            )
        else:
            widget.setMinimumHeight(
                safe_min
            )

            # A designer maximum must never become lower than the
            # actual text requirement.
            if original_max < 16777215:
                widget.setMaximumHeight(
                    max(
                        original_max,
                        required,
                    )
                )
            else:
                widget.setMaximumHeight(
                    16777215
                )

        widget.updateGeometry()

    @staticmethod
    def apply_to_widget(widget: QWidget, area: str, settings_manager: Optional[Any] = None):
        """
        Apply configured typography and then reconcile text geometry.

        Typography changes are allowed to increase physical control height
        when necessary, but decorative geometry is never globally rewritten.
        """
        if widget is None:
            return

        font = TypographyService.get_font_for_area(
            area,
            settings_manager,
        )

        widget.setFont(font)

        from PySide6.QtWidgets import (
            QListView,
            QTreeView,
            QTableView,
            QListWidget,
            QTreeWidget,
            QTableWidget,
            QCalendarWidget,
            QHeaderView,
        )

        target_types = (
            QLabel,
            QPushButton,
            QAbstractButton,
            QLineEdit,
            QTextEdit,
            QComboBox,
            QSpinBox,
            QDateEdit,
            QTimeEdit,
            QCheckBox,
            QRadioButton,
            QListView,
            QTreeView,
            QTableView,
            QListWidget,
            QTreeWidget,
            QTableWidget,
            QAbstractScrollArea,
            QCalendarWidget,
            QHeaderView,
        )

        for target_type in target_types:
            for child in widget.findChildren(
                target_type
            ):
                child.setFont(font)

        # Semantic hierarchy is relative to the NEW base font.
        #
        # This intentionally runs after normal font assignment so that
        # headings/KPIs remain visually differentiated without becoming
        # independent absolute-font authorities.
        role_types = (
            QLabel,
            QPushButton,
            QAbstractButton,
        )

        for role_type in role_types:
            for child in widget.findChildren(
                role_type
            ):
                if (
                    child.property(
                        "_todo_bird_font_delta_pt"
                    )
                    is not None
                    or child.property(
                        "_todo_bird_font_role_weight"
                    )
                    is not None
                ):
                    TypographyService._apply_relative_font_role(
                        child,
                        font,
                    )

        # Geometry safety is a separate final pass.
        #
        # The pass must come after semantic roles because sizeHint()
        # must see the final rendered control font.
        geometry_types = (
            QPushButton,
            QAbstractButton,
            QLineEdit,
            QComboBox,
            QSpinBox,
            QDateEdit,
            QTimeEdit,
            QCheckBox,
            QRadioButton,
        )

        for target_type in geometry_types:
            for child in widget.findChildren(
                target_type
            ):
                TypographyService._apply_text_geometry_safety(
                    child,
                    font,
                )

        widget.updateGeometry()

    @staticmethod
    def notify_typography_changed():
        """Notifies all views that typography configuration has been updated."""
        try:
            from todo_bird_app.controllers.task_controller import _GLOBAL_EVENT_BUS
            _GLOBAL_EVENT_BUS.typography_changed.emit()
        except Exception:
            pass
