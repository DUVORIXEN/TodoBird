import logging
from PySide6.QtWidgets import QLayout, QWidget, QLayoutItem
from PySide6.QtCore import QCoreApplication, QEvent

logger = logging.getLogger(__name__)

def clear_layout(layout: QLayout, recursive: bool = True):
    """
    Safely and thoroughly clears a QLayout, removing all child widgets and sub-layouts,
    disconnecting signals, unparenting widgets, and scheduling Qt C++ deletion.
    """
    if layout is None:
        return

    while layout.count() > 0:
        item: QLayoutItem = layout.takeAt(0)
        if item is None:
            continue

        widget: QWidget = item.widget()
        if widget is not None:
            try:
                widget.disconnect()
            except Exception:
                pass
            layout.removeWidget(widget)
            widget.setParent(None)
            widget.deleteLater()
        elif recursive and item.layout() is not None:
            clear_layout(item.layout(), recursive=True)
            child_layout = item.layout()
            try:
                child_layout.setParent(None)
            except Exception:
                pass
            child_layout.deleteLater()

def flush_deferred_deletes():
    """
    Flushes all pending DeferredDelete events and processes Qt event queue.
    """
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    QCoreApplication.processEvents()
