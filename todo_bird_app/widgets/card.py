from PySide6.QtWidgets import QFrame, QVBoxLayout, QWidget

class CardWidget(QFrame):
    """
    Modern elevated Card Container component.
    """
    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.setObjectName("CardWidget")
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(16, 16, 16, 16)
        self.layout.setSpacing(12)

    def add_widget(self, widget: QWidget):
        self.layout.addWidget(widget)
