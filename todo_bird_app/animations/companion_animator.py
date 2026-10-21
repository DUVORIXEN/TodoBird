import math
from PySide6.QtCore import QObject, QTimer, Signal, QPoint, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPainter, QColor, QFont, QPen, QBrush

class CompanionAnimator(QObject):
    """
    Animation driver for Avocet Bird, Yoga Ganapathy, Lakshmi Ganapathy, and Male Lion.
    """
    frame_updated = Signal()

    def __init__(self, companion_type: str = "avocet", parent=None):
        super().__init__(parent)
        self.companion_type = companion_type
        self.frame_index = 0
        self.is_flying = False
        self.is_walking = False
        self.is_blinking = False
        self.head_turn = 0  # -1 left, 0 center, 1 right

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._on_tick)
        self.timer.start(100)  # 10 FPS sprite tick

    def set_companion(self, companion_type: str):
        self.companion_type = companion_type
        self.frame_index = 0
        self.frame_updated.emit()

    def start_flight_sequence(self):
        if self.companion_type == "avocet":
            self.is_flying = True
            QTimer.singleShot(2500, self._land)

    def _land(self):
        self.is_flying = False
        self.is_walking = True
        QTimer.singleShot(1000, self._stop_walking)

    def _stop_walking(self):
        self.is_walking = False

    def _on_tick(self):
        self.frame_index = (self.frame_index + 1) % 60
        # Random blink every 30 ticks
        if self.frame_index % 30 == 0:
            self.is_blinking = True
        elif self.frame_index % 30 == 3:
            self.is_blinking = False

        # Random head look
        if self.frame_index % 40 == 0:
            self.head_turn = 1
        elif self.frame_index % 40 == 15:
            self.head_turn = -1
        elif self.frame_index % 40 == 25:
            self.head_turn = 0

        self.frame_updated.emit()

    def draw_companion(self, painter: QPainter, width: int, height: int):
        painter.setRenderHint(QPainter.Antialiasing)

        if self.companion_type == "avocet":
            self._draw_avocet(painter, width, height)
        elif self.companion_type == "yoga_ganapathy":
            self._draw_ganapathy(painter, width, height, title="🧘 Yoga Ganapathy")
        elif self.companion_type == "lakshmi_ganapathy":
            self._draw_ganapathy(painter, width, height, title="✨ Lakshmi Ganapathy")
        else:
            self._draw_lion(painter, width, height)

    def _draw_avocet(self, painter: QPainter, w: int, h: int):
        cx, cy = w // 2, h // 2

        # Wing flap offset if flying
        wing_y = math.sin(self.frame_index * 0.8) * 12 if self.is_flying else math.sin(self.frame_index * 0.1) * 2

        # Draw Avocet Bird Body (Elegant black & white bird with slender recurved beak)
        # Body
        painter.setBrush(QBrush(QColor("#F9FAFB")))
        painter.setPen(QPen(QColor("#111827"), 2))
        painter.drawEllipse(cx - 20, cy - 10, 40, 26)

        # Black Wing Patch
        painter.setBrush(QBrush(QColor("#1F2937")))
        painter.drawEllipse(cx - 10, int(cy - 5 + wing_y), 24, 14)

        # Head & Long Recurved Beak
        head_x = cx + 18 + (4 * self.head_turn)
        head_y = cy - 14
        painter.setBrush(QBrush(QColor("#F9FAFB")))
        painter.drawEllipse(head_x, head_y, 16, 16)

        # Eye
        if not self.is_blinking:
            painter.setBrush(QBrush(QColor("#111827")))
            painter.drawEllipse(head_x + 10, head_y + 4, 4, 4)

        # Slender recurved beak
        painter.setPen(QPen(QColor("#111827"), 2))
        painter.drawLine(head_x + 14, head_y + 10, head_x + 30, head_y + 6)
        painter.drawLine(head_x + 30, head_y + 6, head_x + 38, head_y + 2)  # Upward curve

        # Tail feathers
        tail_wigg = math.sin(self.frame_index * 0.3) * 3
        painter.drawLine(cx - 20, cy + 2, int(cx - 32), int(cy - 4 + tail_wigg))

    def _draw_ganapathy(self, painter: QPainter, w: int, h: int, title: str):
        cx, cy = w // 2, h // 2
        pulse = math.sin(self.frame_index * 0.15) * 4

        # Aura Glow
        painter.setBrush(QBrush(QColor(233, 84, 32, 40)))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(int(cx - 35 - pulse / 2), int(cy - 35 - pulse / 2), int(70 + pulse), int(70 + pulse))

        # Avatar Text Badge
        painter.setPen(QPen(QColor("#F3F4F6")))
        painter.setFont(QFont("Inter", 24))
        painter.drawText(cx - 30, cy + 10, "🐘")

        painter.setFont(QFont("Inter", 10, QFont.Bold))
        painter.drawText(cx - 45, cy + 40, title)

    def _draw_lion(self, painter: QPainter, w: int, h: int):
        cx, cy = w // 2, h // 2
        breath = math.sin(self.frame_index * 0.1) * 2

        # Golden Mane Aura
        painter.setBrush(QBrush(QColor(245, 158, 11, 50)))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(cx - 32, cy - 32, 64, 64)

        painter.setPen(QPen(QColor("#F3F4F6")))
        painter.setFont(QFont("Inter", 28))
        painter.drawText(cx - 24, cy + 12, "🦁")

        painter.setFont(QFont("Inter", 10, QFont.Bold))
        painter.drawText(cx - 35, cy + 40, "👑 Male Lion")
