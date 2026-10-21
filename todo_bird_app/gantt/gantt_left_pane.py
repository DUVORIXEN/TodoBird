from PySide6.QtWidgets import QListView, QStyledItemDelegate, QWidget, QStyle
from PySide6.QtCore import Qt, QAbstractListModel, QModelIndex, QSize, QRect, Signal
from PySide6.QtGui import QPainter, QColor, QFont, QPen, QBrush

from todo_bird_app.models.task import Task, TaskStatus

class GanttLeftPaneListView(QListView):
    """
    Phase 1D hierarchy-aware Gantt row list.

    Only the summary chevron hit-zone toggles branches.
    Normal row behavior remains untouched.
    """

    summaryToggleRequested = Signal(object)
    taskDoubleClicked = Signal(object)
    taskActionRequested = Signal(str, int)

    def mousePressEvent(self, event):
        index = self.indexAt(event.position().toPoint())

        if index.isValid() and index.row() > 0:
            task = index.data(Qt.UserRole)

            if (
                task is not None
                and bool(
                    getattr(
                        task,
                        "gantt_is_summary",
                        False,
                    )
                )
            ):
                # The delegate paints the hierarchy chevron at the
                # same left origin for every hierarchy depth.
                #
                # Depth indentation is part of the TITLE STRING after
                # the chevron, so moving this hit-box by depth causes
                # nested summary toggles to miss their visible icon.
                row_rect = self.visualRect(index)

                hit_left = row_rect.left() + 4
                hit_right = row_rect.left() + 38

                x = event.position().x()

                if hit_left <= x <= hit_right:
                    self.summaryToggleRequested.emit(task)
                    event.accept()
                    return

        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        index = self.indexAt(event.position().toPoint())
        if index.isValid() and index.row() > 0:
            task = index.data(Qt.UserRole)
            if task is not None and hasattr(task, "id"):
                self.taskDoubleClicked.emit(task)
                self.taskActionRequested.emit("open", int(task.id))
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            cur = self.currentIndex()
            if cur.isValid() and cur.row() > 0:
                task = cur.data(Qt.UserRole)
                if task is not None and hasattr(task, "id"):
                    self.taskDoubleClicked.emit(task)
                    self.taskActionRequested.emit("open", int(task.id))
                    event.accept()
                    return
        super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        from PySide6.QtWidgets import QMenu
        index = self.indexAt(event.pos())
        if not index.isValid() or index.row() <= 0:
            return
        task = index.data(Qt.UserRole)
        if not task or not hasattr(task, "id"):
            return

        menu = QMenu(self)
        is_nested = getattr(task, "gantt_item_type", "task") != "task"
        action_open_text = "✏ Edit Subtask" if is_nested else "✏ Open Task"

        open_action = menu.addAction(action_open_text)
        copy_action = menu.addAction("📋 Copy Schedule Details")
        view_action = menu.addAction("🔍 View Schedule Details...")

        chosen = menu.exec(event.globalPos())
        if chosen == open_action:
            self.taskActionRequested.emit("open", int(task.id))
        elif chosen == copy_action:
            self.taskActionRequested.emit("copy_details", int(task.id))
        elif chosen == view_action:
            self.taskActionRequested.emit("view_details", int(task.id))


class GanttLeftPaneModel(QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._tasks = []
        
    def set_tasks(self, tasks):
        self.beginResetModel()
        self._tasks = tasks
        self.endResetModel()
        
    def rowCount(self, parent=QModelIndex()):
        return len(self._tasks) + 1 # +1 for the header
        
    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
            
        row = index.row()
        if row == 0:
            if role == Qt.UserRole:
                return "HEADER"
            return None
            
        task = self._tasks[row - 1]
        if role == Qt.UserRole:
            return task
        return None


class GanttLeftPaneDelegate(QStyledItemDelegate):
    def __init__(self, row_height=42.0, color_profile=None, parent=None):
        super().__init__(parent)
        self.row_height = row_height
        self.color_profile = color_profile or {}
        
    def set_color_profile(self, profile):
        self.color_profile = profile or {}
        
    def sizeHint(self, option, index):
        if index.row() == 0:
            return QSize(250, 60) # Header height
        return QSize(250, int(self.row_height))
        
    def paint(self, painter, option, index):
        data = index.data(Qt.UserRole)
        if not data:
            return
            
        painter.save()
        rect = option.rect
        
        if data == "HEADER":
            header_bg = QColor(self.color_profile.get("panel_header_bg", "#1E293B"))
            painter.fillRect(rect, header_bg)
            grid_color = QColor(self.color_profile.get("panel_grid_color", "#374151"))
            painter.setPen(QPen(grid_color, 1))
            painter.drawLine(rect.bottomLeft(), rect.bottomRight())
            
            font = option.font
            font.setBold(True)
            painter.setFont(font)
            secondary_text = QColor(self.color_profile.get("panel_secondary_text", "#9CA3AF"))
            painter.setPen(secondary_text)
            
            text_rect = QRect(rect.x() + 10, rect.y(), rect.width() - 20, rect.height())
            painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, "Tasks")
            painter.restore()
            return
            
        task = data
        
        # Background — always from current color profile
        bg_color = QColor(self.color_profile.get("panel_bg", "#1E293B"))
        if option.state & QStyle.State_Selected:
            bg_color = bg_color.lighter(110)
            
        painter.fillRect(rect, bg_color)
        
        # Bottom border
        grid_color = QColor(self.color_profile.get("panel_grid_color", "#374151"))
        painter.setPen(QPen(grid_color, 1))
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())
        
        # Title
        depth = int(getattr(task, "gantt_depth", 0) or 0)
        item_type = getattr(task, "gantt_item_type", "task")
        is_summary = bool(getattr(task, "gantt_is_summary", False))
        is_milestone = bool(getattr(task, "gantt_is_milestone", False))
        wbs_code = str(getattr(task, "gantt_wbs_code", "") or "").strip()

        if is_summary:
            hierarchy_icon = (
                "▸"
                if bool(
                    getattr(
                        task,
                        "gantt_collapsed",
                        False,
                    )
                )
                else "▾"
            )
        elif is_milestone:
            hierarchy_icon = "◆"
        else:
            hierarchy_icon = "📌" if item_type == "task" else "↳"

        clean_title = (task.title or "Untitled").replace("↳", "").strip()
        display_title = ("   " * max(0, depth)) + clean_title

        if wbs_code:
            title_text = f"{hierarchy_icon} {wbs_code}  {display_title}"
        else:
            title_text = f"{hierarchy_icon} {display_title}"

        font = option.font
        font.setBold(
            bool(is_summary or item_type == "task")
        )
            
        painter.setFont(font)
        text_color = QColor(self.color_profile.get("panel_text_color", "#F3F4F6"))
        painter.setPen(text_color)
        
        text_rect = QRect(rect.x() + 10, rect.y(), rect.width() - 20, rect.height())
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, title_text)
        
        painter.restore()
