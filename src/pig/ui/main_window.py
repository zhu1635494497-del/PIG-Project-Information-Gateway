from __future__ import annotations

import html
import logging
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, TypeVar

from PySide6.QtCore import (
    QAbstractItemModel,
    QEvent,
    QItemSelectionModel,
    QModelIndex,
    QSize,
    QTimer,
    Qt,
    Signal,
)
from PySide6.QtGui import QAction, QBrush, QColor, QCloseEvent, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStyle,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QToolButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from pig.application import (
    AddWorkspaceInputsRequest,
    CreateProjectRequest,
    CreateWorkspaceFolderRequest,
    ExportWorkspaceItemsRequest,
    GetRecentProjectEventsRequest,
    GetWorkspaceTreeRequest,
    GetWorkspacePhysicalLocationRequest,
    InspectProjectRecoveryRequest,
    LoadProjectRequest,
    MoveWorkspaceItemRequest,
    RenameWorkspaceItemRequest,
    OpenWorkspaceItemRequest,
    OperationControl,
    OperationProgressSnapshot,
    OperationStage,
    PreviewImportUndoRequest,
    PigApplication,
    RefreshWorkingArtifactRequest,
    RecoverWorkbenchProjectRequest,
    RollbackWorkingArtifactRequest,
    RestoreWorkingArtifactRequest,
    RestoreWorkspaceItemRequest,
    SearchWorkspaceItemsRequest,
    SoftDeleteWorkspaceItemRequest,
    UndoImportedItemRequest,
    WorkspaceItemView,
)
from pig.application.errors import ApplicationError
from pig.domain.enums import (
    EventType,
    NodeFormat,
    NodeKind,
    NodeProcessingStatus,
    WorkingContentStatus,
    WorkingRefreshReason,
    WorkspaceItemKind,
    WorkspaceExportKind,
)
from pig.domain.paths import safe_filesystem_segment
from pig.ui.theme import apply_workbench_theme
from pig.ui.context_view import ProjectContextView

T = TypeVar("T")
ITEM_ID_ROLE = int(Qt.ItemDataRole.UserRole)
ITEM_KIND_ROLE = ITEM_ID_ROLE + 1

_SOURCE_FAILURE_STATUSES = frozenset({
    NodeProcessingStatus.INTERRUPTED.value,
    NodeProcessingStatus.UNSUPPORTED.value,
    NodeProcessingStatus.PASSWORD_REQUIRED.value,
    NodeProcessingStatus.CORRUPTED.value,
    NodeProcessingStatus.LIMIT_EXCEEDED.value,
    NodeProcessingStatus.SECURITY_BLOCKED.value,
    NodeProcessingStatus.SOURCE_MISSING.value,
    NodeProcessingStatus.SOURCE_CHANGED.value,
    NodeProcessingStatus.FAILED.value,
})


def _visible_file_status(view: WorkspaceItemView) -> str:
    """Show source failures before the otherwise-correct lazy-copy status."""
    if view.working_artifact is not None:
        return view.working_artifact.content_status.value
    if view.source_node is not None and view.source_node.status.value in _SOURCE_FAILURE_STATUSES:
        return view.source_node.status.value
    return view.item.materialization_status.value


class EnumMultiSelect(QToolButton):
    def __init__(self, values: Iterable, empty_text: str, parent=None) -> None:
        super().__init__(parent)
        self._empty_text = empty_text
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._menu = QMenu(self)
        self._actions = {}
        for value in values:
            action = self._menu.addAction(value.value)
            action.setCheckable(True)
            action.toggled.connect(self._update_text)
            self._actions[value] = action
        self.setMenu(self._menu)
        self._update_text()

    def selected_values(self) -> tuple:
        return tuple(
            value for value, action in self._actions.items() if action.isChecked()
        )

    def set_selected_values(self, values: tuple) -> None:
        selected = set(values)
        for value, action in self._actions.items():
            action.setChecked(value in selected)
        self._update_text()

    def clear_selection(self) -> None:
        self.set_selected_values(())

    def _update_text(self, _checked: bool = False) -> None:
        selected = self.selected_values()
        if not selected:
            self.setText(self._empty_text)
        elif len(selected) == 1:
            self.setText(selected[0].value)
        else:
            self.setText(f"已选 {len(selected)} 项")


class FormatMultiSelect(EnumMultiSelect):
    def __init__(self, parent=None) -> None:
        super().__init__(NodeFormat, "全部格式", parent)


class WorkspaceTreeModel(QAbstractItemModel):
    """Virtual Qt projection over already-loaded typed Workspace views."""

    HEADERS = ("名称", "类型", "格式", "工作状态")

    def __init__(self, icon_provider=None, parent=None) -> None:
        super().__init__(parent)
        self._icon_provider = icon_provider
        self._views: dict[str, WorkspaceItemView] = {}
        self._children: dict[str | None, tuple[str, ...]] = {None: ()}
        self._id_to_key: dict[str, int] = {}
        self._key_to_id: dict[int, str] = {}
        self._row_by_id: dict[str, int] = {}
        self._display_values: dict[str, tuple[str, str, str, str]] = {}
        self._icons: dict[str, object] = {}
        self._drop_target_id: str | None = None

    def set_views(self, views: Iterable[WorkspaceItemView]) -> None:
        values = tuple(views)
        children: dict[str | None, list[WorkspaceItemView]] = {}
        for view in values:
            children.setdefault(
                view.placement.parent_workspace_item_id, []
            ).append(view)
        views = {view.item.id: view for view in values}
        id_to_key = {
            item_id: key for key, item_id in enumerate(views, start=1)
        }
        key_to_id = {key: item_id for item_id, key in id_to_key.items()}
        ordered_children = {
            parent_id: tuple(
                view.item.id
                for view in sorted(
                    child_views,
                    key=lambda value: (
                        value.placement.ordinal,
                        value.item.id,
                    ),
                )
            )
            for parent_id, child_views in children.items()
        }
        ordered_children.setdefault(None, ())
        row_by_id = {
            item_id: row
            for child_ids in ordered_children.values()
            for row, item_id in enumerate(child_ids)
        }
        display_values = {
            item_id: (
                view.item.display_name,
                view.item.item_kind.value,
                "" if view.source_node is None else view.source_node.format.value,
                _visible_file_status(view),
            )
            for item_id, view in views.items()
        }

        self.beginResetModel()
        self._views = views
        self._id_to_key = id_to_key
        self._key_to_id = key_to_id
        self._children = ordered_children
        self._row_by_id = row_by_id
        self._display_values = display_values
        self._icons = {}
        self._drop_target_id = None
        self.endResetModel()

    def set_drop_target(self, item_id: str | None) -> None:
        if item_id == self._drop_target_id:
            return
        previous = self._drop_target_id
        self._drop_target_id = item_id
        for value in (previous, item_id):
            if value is None:
                continue
            index = self.index_for_id(value)
            if index.isValid():
                self.dataChanged.emit(
                    index, index.siblingAtColumn(self.columnCount() - 1),
                    [Qt.ItemDataRole.BackgroundRole],
                )

    @property
    def views(self) -> dict[str, WorkspaceItemView]:
        return self._views

    def index_for_id(self, item_id: str, column: int = 0) -> QModelIndex:
        view = self._views.get(item_id)
        if view is None:
            return QModelIndex()
        row = self._row_by_id.get(item_id)
        if row is None:
            return QModelIndex()
        return self.createIndex(row, column, self._id_to_key[item_id])

    def item_id(self, index: QModelIndex) -> str | None:
        if not index.isValid():
            return None
        return self._key_to_id.get(index.internalId())

    def index(
        self,
        row: int,
        column: int,
        parent: QModelIndex = QModelIndex(),
    ) -> QModelIndex:
        if row < 0 or column < 0 or column >= len(self.HEADERS):
            return QModelIndex()
        parent_id = self.item_id(parent)
        children = self._children.get(parent_id, ())
        if row >= len(children):
            return QModelIndex()
        item_id = children[row]
        return self.createIndex(row, column, self._id_to_key[item_id])

    def parent(self, child: QModelIndex) -> QModelIndex:
        if not child.isValid():
            return QModelIndex()
        view = self._views.get(self.item_id(child))
        if view is None:
            return QModelIndex()
        parent_id = view.placement.parent_workspace_item_id
        if parent_id is None:
            return QModelIndex()
        parent_view = self._views.get(parent_id)
        if parent_view is None:
            return QModelIndex()
        row = self._row_by_id.get(parent_id)
        if row is None:
            return QModelIndex()
        return self.createIndex(row, 0, self._id_to_key[parent_id])

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid() and parent.column() != 0:
            return 0
        parent_id = self.item_id(parent)
        return len(self._children.get(parent_id, ()))

    def columnCount(self, _parent: QModelIndex = QModelIndex()) -> int:
        return len(self.HEADERS)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        view = self._views.get(self.item_id(index))
        if view is None:
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return self._display_values[view.item.id][index.column()]
        if role == Qt.ItemDataRole.DecorationRole and index.column() == 0:
            if self._icon_provider is None:
                return None
            icon = self._icons.get(view.item.id)
            if icon is None:
                icon = self._icon_provider(view)
                self._icons[view.item.id] = icon
            return icon
        if role == Qt.ItemDataRole.BackgroundRole and view.item.id == self._drop_target_id:
            return QBrush(QColor("#d9ede8"))
        if role == Qt.ItemDataRole.ToolTipRole:
            if index.column() == 0:
                return view.workspace_path
            if index.column() == 3:
                return self._display_values[view.item.id][3]
        if role == ITEM_ID_ROLE:
            return view.item.id
        if role == ITEM_KIND_ROLE:
            return view.item.item_kind.value
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if (
            orientation == Qt.Orientation.Horizontal
            and role == Qt.ItemDataRole.DisplayRole
            and 0 <= section < len(self.HEADERS)
        ):
            return self.HEADERS[section]
        return None

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.ItemFlag.ItemIsDropEnabled
        flags = (
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsDragEnabled
        )
        view = self._views.get(self.item_id(index))
        if view is not None and view.item.item_kind in {
            WorkspaceItemKind.FOLDER,
            WorkspaceItemKind.CONTAINER_VIEW,
        }:
            flags |= Qt.ItemFlag.ItemIsDropEnabled
        return flags

    def supportedDropActions(self):
        return Qt.DropAction.MoveAction | Qt.DropAction.CopyAction


class _TreeIndexItem:
    """Small compatibility wrapper; created only for requested QModelIndexes."""

    def __init__(self, tree: "WorkspaceTree", index: QModelIndex) -> None:
        self._tree = tree
        self._index = index.siblingAtColumn(0)

    def data(self, column: int, role: int):
        return self._index.siblingAtColumn(column).data(role)

    def text(self, column: int) -> str:
        value = self._index.siblingAtColumn(column).data(
            Qt.ItemDataRole.DisplayRole
        )
        return "" if value is None else str(value)

    def parent(self):
        parent = self._index.parent()
        return None if not parent.isValid() else _TreeIndexItem(self._tree, parent)

    def child(self, row: int):
        index = self._tree.model().index(row, 0, self._index)
        return None if not index.isValid() else _TreeIndexItem(self._tree, index)

    def childCount(self) -> int:
        return self._tree.model().rowCount(self._index)

    def indexOfChild(self, child: "_TreeIndexItem") -> int:
        return child._index.row()

    def setSelected(self, selected: bool) -> None:
        command = (
            QItemSelectionModel.SelectionFlag.Select
            if selected
            else QItemSelectionModel.SelectionFlag.Deselect
        ) | QItemSelectionModel.SelectionFlag.Rows
        self._tree.selectionModel().select(self._index, command)

    def isSelected(self) -> bool:
        return self._tree.selectionModel().isSelected(self._index)

    def setExpanded(self, expanded: bool) -> None:
        self._tree.setExpanded(self._index, expanded)

    def isExpanded(self) -> bool:
        return self._tree.isExpanded(self._index)


class WorkspaceTree(QTreeView):
    external_paths_dropped = Signal(object, object)
    move_requested = Signal(str, object, int)
    itemSelectionChanged = Signal()
    itemDoubleClicked = Signal(object, int)
    drag_destination_changed = Signal(str)

    def __init__(self, parent=None, *, icon_provider=None) -> None:
        super().__init__(parent)
        self.setModel(WorkspaceTreeModel(icon_provider, self))
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setAnimated(False)
        self.setUniformRowHeights(True)
        self.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column, width in ((1, 110), (2, 100), (3, 140)):
            self.header().setSectionResizeMode(
                column, QHeaderView.ResizeMode.Interactive
            )
            self.header().resizeSection(column, width)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setAutoExpandDelay(-1)
        self.setExpandsOnDoubleClick(False)
        self.selectionModel().selectionChanged.connect(
            lambda *_args: self.itemSelectionChanged.emit()
        )
        self.doubleClicked.connect(
            lambda index: self.itemDoubleClicked.emit(
                _TreeIndexItem(self, index), index.column()
            )
        )

    def set_views(self, views: Iterable[WorkspaceItemView]) -> None:
        self.model().set_views(views)

    def clear(self) -> None:
        self.set_views(())

    def topLevelItemCount(self) -> int:
        return self.model().rowCount()

    def topLevelItem(self, row: int):
        index = self.model().index(row, 0)
        return None if not index.isValid() else _TreeIndexItem(self, index)

    def indexOfTopLevelItem(self, item: _TreeIndexItem) -> int:
        return item._index.row()

    def selectedItems(self) -> list[_TreeIndexItem]:
        return [
            _TreeIndexItem(self, index)
            for index in self.selectionModel().selectedRows(0)
        ]

    def currentItem(self):
        index = self.currentIndex()
        return None if not index.isValid() else _TreeIndexItem(self, index)

    def setCurrentItem(self, item: _TreeIndexItem) -> None:
        self.setCurrentIndex(item._index)

    def itemAt(self, position):
        index = self.indexAt(position)
        return None if not index.isValid() else _TreeIndexItem(self, index)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls() or event.source() is self:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        super().dragMoveEvent(event)
        if not (event.mimeData().hasUrls() or event.source() is self):
            self._clear_drop_target()
            return
        target = self.itemAt(event.position().toPoint())
        indicator = self.dropIndicatorPosition()
        parent_id, _ordinal, hint = self._drop_destination(target, indicator)
        self.model().set_drop_target(parent_id)
        self.drag_destination_changed.emit(hint)
        event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:
        self._clear_drop_target()
        super().dragLeaveEvent(event)

    def _clear_drop_target(self) -> None:
        self.model().set_drop_target(None)
        self.drag_destination_changed.emit("")

    def _drop_destination(self, target, indicator):
        if target is None:
            return None, self.topLevelItemCount(), "放到工作区根目录末尾"
        if indicator == QAbstractItemView.DropIndicatorPosition.OnItem and (
            target.data(0, ITEM_KIND_ROLE) == WorkspaceItemKind.FOLDER.value
        ):
            return (
                target.data(0, ITEM_ID_ROLE), target.childCount(),
                f"放入文件夹「{target.text(0)}」",
            )
        parent = target.parent()
        parent_id = None if parent is None else parent.data(0, ITEM_ID_ROLE)
        row = self.indexOfTopLevelItem(target) if parent is None else parent.indexOfChild(target)
        after = indicator in {
            QAbstractItemView.DropIndicatorPosition.BelowItem,
            QAbstractItemView.DropIndicatorPosition.OnItem,
        }
        destination = "工作区根目录" if parent is None else f"文件夹「{parent.text(0)}」"
        relation = "之后" if after else "之前"
        return parent_id, row + int(after), f"放在「{target.text(0)}」{relation} · {destination}"

    def dropEvent(self, event: QDropEvent) -> None:
        target = self.itemAt(event.position().toPoint())
        indicator = self.dropIndicatorPosition()
        parent_id, ordinal, _hint = self._drop_destination(target, indicator)
        self._clear_drop_target()
        if event.mimeData().hasUrls():
            paths = tuple(
                Path(url.toLocalFile()).absolute()
                for url in event.mimeData().urls()
                if url.isLocalFile()
            )
            if paths:
                self.external_paths_dropped.emit(paths, parent_id)
                event.acceptProposedAction()
            else:
                event.ignore()
            return
        source = self.currentItem()
        if event.source() is not self or source is None or len(self.selectedItems()) != 1:
            event.ignore()
            return
        source_id = source.data(0, ITEM_ID_ROLE)
        self.move_requested.emit(source_id, parent_id, ordinal)
        event.acceptProposedAction()


class WorkbenchDropSurface(QWidget):
    external_paths_dropped = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setProperty("external_drag_active", True)
            self.style().unpolish(self)
            self.style().polish(self)
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:
        self.setProperty("external_drag_active", False)
        self.style().unpolish(self)
        self.style().polish(self)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        self.setProperty("external_drag_active", False)
        self.style().unpolish(self)
        self.style().polish(self)
        paths = tuple(
            Path(url.toLocalFile()).absolute()
            for url in event.mimeData().urls()
            if url.isLocalFile()
        )
        if paths:
            self.external_paths_dropped.emit(paths)
            event.acceptProposedAction()
        else:
            event.ignore()


class MainWindow(QMainWindow):
    """One-screen Workbench UI backed only by typed Application contracts."""

    def __init__(self, application: PigApplication, *, actor: str) -> None:
        super().__init__()
        self._application = application
        self._actor = actor
        self._project_id: str | None = None
        self._database_path: Path | None = None
        self._workspace_revision = 0
        self._views: dict[str, WorkspaceItemView] = {}
        self._tree_initialized = False
        self._last_move_undo: tuple[str, str, str | None, int, int] | None = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pig-ui")
        self._worker_thread: Future | None = None
        self._background_success: Callable[[object], None] | None = None
        self._background_operation: str | None = None
        self._background_control: OperationControl | None = None
        self._background_progress_sequence = 0
        self._background_timer = QTimer(self)
        self._background_timer.setInterval(20)
        self._background_timer.timeout.connect(self._poll_background)
        self._busy_operation: str | None = None
        self._focus_refresh_pending = False
        self._reload_after_background = False
        self._closed = False
        self._opened_names: dict[str, str] = {}
        self._workspace_icons: dict[WorkspaceItemKind, object] = {}
        self._project_name = "PIG-Workspace"
        self._recovery_required = False
        self._recovery_inspection_token: str | None = None
        self._logger = logging.getLogger(__name__)

        self.setWindowTitle("PIG — Project Information Gateway")
        self.resize(1380, 860)
        self.setMinimumSize(1080, 680)
        self.setAcceptDrops(True)
        apply_workbench_theme(self)
        self._build_actions()
        self._build_ui()
        self._set_project_actions_enabled(False)

    def _build_actions(self) -> None:
        self.new_project_action = QAction("新建项目", self)
        self.open_project_action = QAction("打开项目", self)
        self.recovery_action = QAction("恢复项目", self)
        self.add_files_action = QAction("添加文件", self)
        self.add_folder_action = QAction("添加文件夹", self)
        self.create_folder_action = QAction("新建工作区文件夹", self)
        self.undo_move_action = QAction("撤销上次移动", self)
        self.undo_move_action.setShortcut("Ctrl+Z")
        self.undo_move_action.setEnabled(False)
        self.delete_action = QAction("软删除", self)
        self.refresh_action = QAction("刷新工作区", self)
        self.export_action = QAction("导出", self)
        standard_icons = {
            self.new_project_action: QStyle.StandardPixmap.SP_FileDialogNewFolder,
            self.open_project_action: QStyle.StandardPixmap.SP_DialogOpenButton,
            self.recovery_action: QStyle.StandardPixmap.SP_MessageBoxWarning,
            self.add_files_action: QStyle.StandardPixmap.SP_FileIcon,
            self.add_folder_action: QStyle.StandardPixmap.SP_DirIcon,
            self.create_folder_action: QStyle.StandardPixmap.SP_FileDialogNewFolder,
            self.delete_action: QStyle.StandardPixmap.SP_TrashIcon,
            self.refresh_action: QStyle.StandardPixmap.SP_BrowserReload,
            self.export_action: QStyle.StandardPixmap.SP_DialogSaveButton,
        }
        tooltips = {
            self.new_project_action: "新建一个独立的 PIG 项目（Ctrl+N）",
            self.open_project_action: "打开已有 project.sqlite（Ctrl+O）",
            self.recovery_action: "检查并恢复中断的项目操作",
            self.add_files_action: "把一个或多个文件加入当前文件夹",
            self.add_folder_action: "把文件夹及其结构加入当前工作区",
            self.create_folder_action: "在工作区中创建整理用文件夹",
            self.delete_action: "将所选项目移到已删除项目",
            self.refresh_action: "重新载入当前工作区（F5）",
            self.export_action: "按当前工作区结构导出所选项目",
        }
        for action, standard_icon in standard_icons.items():
            action.setIcon(self.style().standardIcon(standard_icon))
            action.setToolTip(tooltips[action])
        self.new_project_action.setShortcut("Ctrl+N")
        self.open_project_action.setShortcut("Ctrl+O")
        self.refresh_action.setShortcut("F5")
        self.new_project_action.triggered.connect(self._new_project)
        self.open_project_action.triggered.connect(self._choose_project)
        self.recovery_action.triggered.connect(self._inspect_active_project_recovery)
        self.add_files_action.triggered.connect(self._choose_files)
        self.add_folder_action.triggered.connect(self._choose_folder)
        self.create_folder_action.triggered.connect(self._create_folder)
        self.undo_move_action.triggered.connect(self._undo_last_move)
        self.delete_action.triggered.connect(self._delete_selected)
        self.refresh_action.triggered.connect(self._reload_workspace)
        self.export_action.triggered.connect(self._export_selected)
        self.toolbar = self.addToolBar("Workbench")
        self.toolbar.setObjectName("mainToolbar")
        self.toolbar.setMovable(False)
        self.toolbar.setFloatable(False)
        self.toolbar.setIconSize(QSize(18, 18))
        self.toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        for action in (self.new_project_action, self.open_project_action):
            self.toolbar.addAction(action)
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.recovery_action)
        self.toolbar.addSeparator()
        for action in (
            self.add_files_action,
            self.add_folder_action,
            self.create_folder_action,
        ):
            self.toolbar.addAction(action)
        self.toolbar.addSeparator()
        for action in (self.refresh_action, self.export_action, self.delete_action):
            self.toolbar.addAction(action)
        # Keep shortcut-bearing actions on the window when the legacy toolbar is hidden.
        for action in (self.new_project_action, self.open_project_action, self.refresh_action,
                       self.undo_move_action):
            self.addAction(action)
        self.toolbar.hide()

    def _build_ui(self) -> None:
        root = WorkbenchDropSurface(self)
        self.drop_surface = root
        root.external_paths_dropped.connect(lambda paths: self._add_inputs(paths, None))
        layout = QVBoxLayout(root)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        shell = QWidget()
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(12, 10, 12, 10)
        shell_layout.setSpacing(8)

        project_header = QFrame()
        project_header.setObjectName("projectHeader")
        project_header_layout = QHBoxLayout(project_header)
        project_header_layout.setContentsMargins(16, 12, 16, 12)
        project_header_layout.setSpacing(12)
        project_identity = QHBoxLayout()
        project_identity.setSpacing(10)
        product_eyebrow = QLabel("PIG")
        product_eyebrow.setObjectName("productEyebrow")
        self.project_location = QLabel("尚未打开项目")
        self.project_location.setObjectName("projectTitle")
        self.project_location.setTextFormat(Qt.TextFormat.PlainText)
        self.project_location.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.project_meta = QLabel("新建或打开一个项目，然后将文件拖入窗口任意位置")
        self.project_meta.setObjectName("projectMeta")
        self.project_meta.setTextFormat(Qt.TextFormat.PlainText)
        self.project_meta.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        project_identity.addWidget(product_eyebrow)
        project_identity.addWidget(self.project_location)
        self.project_meta.hide()
        self.project_meta.setParent(project_header)
        project_header_layout.addLayout(project_identity, 1)
        self.project_state = QLabel("未打开")
        self.project_state.setObjectName("projectState")
        self.project_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.project_state.hide()
        project_header_layout.addWidget(
            self.project_state, 0, Qt.AlignmentFlag.AlignVCenter
        )
        self.project_menu_button = QToolButton()
        self.project_menu_button.setText("项目")
        self.project_menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        project_menu = QMenu(self.project_menu_button)
        project_menu.addAction(self.new_project_action)
        project_menu.addAction(self.open_project_action)
        project_menu.addSeparator()
        project_menu.addAction(self.recovery_action)
        self.project_menu_button.setMenu(project_menu)
        self.import_button = QToolButton()
        self.import_button.setText("＋ 导入")
        self.import_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        import_menu = QMenu(self.import_button)
        import_menu.addAction(self.add_files_action)
        import_menu.addAction(self.add_folder_action)
        self.import_button.setMenu(import_menu)
        self.export_button = QToolButton()
        self.export_button.setDefaultAction(self.export_action)
        self.export_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.more_button = QToolButton()
        self.more_button.setText("···")
        self.more_button.setToolTip("更多工作区操作")
        self.more_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        more_menu = QMenu(self.more_button)
        more_menu.addAction(self.create_folder_action)
        more_menu.addAction(self.undo_move_action)
        more_menu.addAction(self.refresh_action)
        more_menu.addSeparator()
        more_menu.addAction(self.delete_action)
        self.more_button.setMenu(more_menu)
        for button in (
            self.project_menu_button, self.import_button,
            self.export_button, self.more_button,
        ):
            project_header_layout.addWidget(button)
        shell_layout.addWidget(project_header)

        self.recovery_banner = QLabel()
        self.recovery_banner.setObjectName("recoveryBanner")
        self.recovery_banner.setWordWrap(True)
        self.recovery_banner.hide()
        shell_layout.addWidget(self.recovery_banner)

        search_panel = QFrame()
        search_panel.setObjectName("searchPanel")
        search_panel_layout = QHBoxLayout(search_panel)
        search_panel_layout.setContentsMargins(12, 9, 12, 9)
        search_panel_layout.setSpacing(8)
        self.search_text = QLineEdit()
        self.search_text.setPlaceholderText("查找文件")
        self.search_text.setClearButtonEnabled(True)
        self.format_filter = FormatMultiSelect()
        self.format_filter.setProperty("filter", True)
        self.format_filter.setToolTip("可同时选择多个文件格式")
        self.content_filter = EnumMultiSelect(WorkingContentStatus, "全部工作状态")
        self.content_filter.setProperty("filter", True)
        self.content_filter.setToolTip("可同时选择多个工作状态")
        self.search_button = QPushButton("搜索")
        self.search_button.setProperty("variant", "primary")
        self.clear_search_button = QPushButton("重置")
        self.clear_search_button.setProperty("variant", "quiet")
        self.search_button.clicked.connect(self._search)
        self.clear_search_button.clicked.connect(self._clear_search)
        self.search_text.returnPressed.connect(self._search)
        self.search_filters = QWidget()
        filter_layout = QHBoxLayout(self.search_filters)
        filter_layout.setContentsMargins(0, 0, 0, 0)
        filter_layout.setSpacing(6)
        filter_layout.addWidget(self.format_filter)
        filter_layout.addWidget(self.content_filter)
        self.search_filters.hide()
        self.filter_button = QPushButton("筛选")
        self.filter_button.setCheckable(True)
        self.filter_button.setProperty("variant", "quiet")
        self.filter_button.toggled.connect(self.search_filters.setVisible)
        search_panel_layout.addWidget(self.search_text, 1)
        search_panel_layout.addWidget(self.search_filters)
        search_panel_layout.addWidget(self.filter_button)
        search_panel_layout.addWidget(self.search_button)
        self.clear_search_button.hide()
        search_panel_layout.addWidget(self.clear_search_button)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(8)
        left_pane = QWidget()
        left_layout = QVBoxLayout(left_pane)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(7)
        list_header = QHBoxLayout()
        self.list_heading = QLabel("全部文件")
        self.list_heading.setObjectName("sectionTitle")
        self.new_folder_button = QToolButton()
        self.new_folder_button.setDefaultAction(self.create_folder_action)
        self.new_folder_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        list_header.addWidget(self.list_heading)
        list_header.addStretch(1)
        list_header.addWidget(self.new_folder_button)
        self.drag_destination = QLabel("")
        self.drag_destination.setObjectName("dragDestination")
        self.drag_destination.hide()
        left_layout.addLayout(list_header)
        left_layout.addWidget(self.drag_destination)
        left_layout.addWidget(search_panel)
        self.left_tabs = QTabWidget()
        self.left_tabs.setMinimumWidth(520)
        self.tree = WorkspaceTree(icon_provider=self._workspace_item_icon)
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setIndentation(20)
        self.tree.header().setHighlightSections(False)
        self.tree.hideColumn(1)
        self.tree.hideColumn(2)
        self.tree.itemSelectionChanged.connect(self._tree_selection_changed)
        self.tree.itemDoubleClicked.connect(self._tree_double_clicked)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_tree_context_menu)
        self.tree.external_paths_dropped.connect(self._add_inputs)
        self.tree.move_requested.connect(self._move_item)
        self.tree.drag_destination_changed.connect(self._show_drag_destination)
        self.search_results = QTableWidget(0, 5)
        self.search_results.setHorizontalHeaderLabels(
            ["名称", "Workspace Path", "类型", "格式", "工作状态"]
        )
        self.search_results.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.search_results.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.search_results.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._polish_table(self.search_results, stretch_column=1)
        self.search_results.hideColumn(2)
        self.search_results.itemSelectionChanged.connect(self._search_selection_changed)
        self.search_results.itemDoubleClicked.connect(self._search_double_clicked)
        self.search_results.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.search_results.customContextMenuRequested.connect(
            self._show_search_context_menu
        )
        self.deleted_items = QTableWidget(0, 4)
        self.deleted_items.setHorizontalHeaderLabels(
            ["名称", "原 Workspace Path", "类型", "删除时间"]
        )
        self.deleted_items.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.deleted_items.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._polish_table(self.deleted_items, stretch_column=1)
        self.deleted_items.itemSelectionChanged.connect(self._deleted_selection_changed)
        self.deleted_items.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.deleted_items.customContextMenuRequested.connect(
            self._show_deleted_context_menu
        )
        self.left_tabs.addTab(self.tree, "工作区")
        self.left_tabs.addTab(self.search_results, "搜索结果")
        self.left_tabs.addTab(self.deleted_items, "回收站")
        self.left_tabs.tabBar().hide()
        self.left_tabs.currentChanged.connect(self._workspace_page_changed)
        left_layout.addWidget(self.left_tabs, 1)
        list_footer = QHBoxLayout()
        self.back_to_tree_button = QPushButton("返回工作区")
        self.back_to_tree_button.setProperty("variant", "quiet")
        self.back_to_tree_button.clicked.connect(self._return_to_tree)
        self.back_to_tree_button.hide()
        self.trash_button = QPushButton("回收站")
        self.trash_button.setProperty("variant", "quiet")
        self.trash_button.clicked.connect(
            lambda: self.left_tabs.setCurrentWidget(self.deleted_items)
        )
        self.activity_button = QPushButton("活动记录")
        self.activity_button.setProperty("variant", "quiet")
        self.activity_button.clicked.connect(self._toggle_activity)
        list_footer.addWidget(self.back_to_tree_button)
        list_footer.addStretch(1)
        list_footer.addWidget(self.trash_button)
        list_footer.addWidget(self.activity_button)
        left_layout.addLayout(list_footer)

        self.right_tabs = QTabWidget()
        self.right_tabs.setMinimumWidth(315)
        self.right_tabs.tabBar().hide()
        details_page = QWidget()
        self.details_page = details_page
        details_layout = QVBoxLayout(details_page)
        details_layout.setContentsMargins(12, 12, 12, 10)
        details_layout.setSpacing(8)
        self.detail_title = QLabel("未选择项目")
        self.detail_title.setObjectName("detailTitle")
        self.detail_title.setTextFormat(Qt.TextFormat.PlainText)
        self.detail_subtitle = QLabel("在左侧选择一个文件或文件夹查看详情")
        self.detail_subtitle.setObjectName("detailSubtitle")
        self.detail_subtitle.setTextFormat(Qt.TextFormat.PlainText)
        self.detail_subtitle.setWordWrap(True)
        details_layout.addWidget(self.detail_title)
        details_layout.addWidget(self.detail_subtitle)
        self.detail_status = QLabel("")
        self.detail_status.setObjectName("detailStatus")
        self.detail_status.hide()
        details_layout.addWidget(self.detail_status)
        self.details = QTextBrowser()
        self.details.setObjectName("itemDetails")
        self.details.setReadOnly(True)
        self.details.setAcceptDrops(False)
        self.details.setOpenExternalLinks(False)
        self.details.setHtml(self._empty_detail_html())
        version_group = QVBoxLayout()
        version_title = QLabel("版本保护")
        version_title.setObjectName("sectionTitle")
        self.versions = QTableWidget(0, 4)
        self.versions.setHorizontalHeaderLabels(
            ["版本", "文件修改时间", "PIG 检测时间", "SHA-256"]
        )
        self.versions.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.versions.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.versions.setMaximumHeight(128)
        self._polish_table(self.versions, stretch_column=3)
        self.rollback_button = QPushButton("回滚到上一版本")
        self.rollback_button.clicked.connect(self._rollback_working_file)
        self.rollback_button.setEnabled(False)
        version_group.addWidget(version_title)
        version_group.addWidget(self.versions)
        button_row = QHBoxLayout()
        button_row.setSpacing(7)
        self.open_selected_button = QPushButton("打开")
        self.open_selected_button.setProperty("variant", "primary")
        self.add_to_context_button = QPushButton("加入核心文件")
        self.add_to_context_button.clicked.connect(self._promote_selected_to_context)
        self.more_file_button = QToolButton()
        self.more_file_button.setText("更多 ···")
        self.more_file_button.clicked.connect(self._show_selected_more_menu)
        self.refresh_file_button = QPushButton("刷新状态")
        self.restore_working_button = QPushButton("从原始备份恢复")
        self.restore_deleted_button = QPushButton("恢复到工作区")
        self.open_selected_button.clicked.connect(self._open_selected)
        self.refresh_file_button.clicked.connect(
            lambda: self._refresh_selected_file()
        )
        self.restore_working_button.clicked.connect(self._restore_working_file)
        self.restore_deleted_button.clicked.connect(self._restore_deleted_item)
        for button in (
            self.open_selected_button,
            self.add_to_context_button,
            self.restore_deleted_button,
        ):
            button.setEnabled(False)
            button_row.addWidget(button)
        button_row.addWidget(self.more_file_button)
        button_row.addStretch(1)
        details_layout.addLayout(button_row)
        self.advanced_toggle = QToolButton()
        self.advanced_toggle.setText("来源与版本")
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.advanced_toggle.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self.advanced_toggle.toggled.connect(self._toggle_advanced_details)
        self.advanced_panel = QWidget()
        advanced_layout = QVBoxLayout(self.advanced_panel)
        advanced_layout.setContentsMargins(0, 0, 0, 0)
        advanced_layout.addWidget(self.details)
        advanced_layout.addLayout(version_group)
        advanced_actions = QHBoxLayout()
        advanced_actions.addWidget(self.refresh_file_button)
        advanced_actions.addWidget(self.restore_working_button)
        advanced_actions.addWidget(self.rollback_button)
        advanced_layout.addLayout(advanced_actions)
        self.advanced_panel.hide()
        details_layout.addWidget(self.advanced_toggle)
        details_layout.addWidget(self.advanced_panel)
        details_layout.addStretch(1)
        self.right_tabs.addTab(details_page, "文件详情")
        self.events = QTableWidget(0, 5)
        self.events.setHorizontalHeaderLabels(
            ["本地时间", "级别", "事件", "Workspace Item", "错误码"]
        )
        self.events.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._polish_table(self.events, stretch_column=2)
        self.right_tabs.addTab(self.events, "活动记录")
        splitter.addWidget(left_pane)
        splitter.addWidget(self.right_tabs)
        splitter.setStretchFactor(0, 7)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([900, 400])
        layout.addWidget(splitter, 1)
        self.context_view = ProjectContextView(
            self._application,
            actor=self._actor,
            run_background=self._run_background,
            show_failure=self._show_failure,
        )
        self.mode_tabs = QTabWidget()
        self.mode_tabs.setObjectName("projectModeTabs")
        self.mode_tabs.addTab(root, "工作区")
        self.mode_tabs.addTab(self.context_view, "核心文件")
        self.mode_tabs.currentChanged.connect(self._project_mode_changed)
        self.context_view.workspace_requested.connect(
            lambda: self.mode_tabs.setCurrentWidget(root)
        )
        shell_layout.addWidget(self.mode_tabs, 1)
        self.setCentralWidget(shell)
        for widget in (
            self.search_text,
            self.search_results,
            self.deleted_items,
            self.events,
        ):
            widget.setAcceptDrops(False)
            viewport = getattr(widget, "viewport", None)
            if callable(viewport):
                viewport().setAcceptDrops(False)

        self.busy_indicator = QProgressBar()
        self.busy_indicator.setRange(0, 100)
        self.busy_indicator.setMaximumWidth(180)
        self.busy_indicator.setTextVisible(True)
        self.busy_indicator.hide()
        self.cancel_operation_button = QPushButton("取消")
        self.cancel_operation_button.setToolTip("在下一个安全检查点停止当前操作")
        self.cancel_operation_button.clicked.connect(self._cancel_background)
        self.cancel_operation_button.hide()
        self.statusBar().addPermanentWidget(self.cancel_operation_button)
        self.statusBar().addPermanentWidget(self.busy_indicator)
        self.statusBar().showMessage("请新建或打开项目")

    def _workspace_page_changed(self, _index: int) -> None:
        current = self.left_tabs.currentWidget()
        self.list_heading.setText(
            "搜索结果" if current is self.search_results
            else "回收站" if current is self.deleted_items
            else "全部文件"
        )
        self.back_to_tree_button.setVisible(current is not self.tree)
        self.new_folder_button.setVisible(current is self.tree)
        self.search_text.setEnabled(
            current is not self.deleted_items and self._worker_thread is None
        )

    def _return_to_tree(self) -> None:
        if self.left_tabs.currentWidget() is self.search_results:
            self._clear_search()
        else:
            self.left_tabs.setCurrentWidget(self.tree)
        self.right_tabs.setCurrentWidget(self.details_page)
        self.activity_button.setText("活动记录")

    def _toggle_activity(self) -> None:
        showing_events = self.right_tabs.currentWidget() is self.events
        self.right_tabs.setCurrentWidget(
            self.details_page if showing_events else self.events
        )
        self.activity_button.setText("活动记录" if showing_events else "文件详情")

    def _toggle_advanced_details(self, expanded: bool) -> None:
        self.advanced_panel.setVisible(expanded)
        self.advanced_toggle.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )

    def _promote_selected_to_context(self) -> None:
        item_id = self.add_to_context_button.property("workspace_item_id")
        view = self._views.get(item_id)
        if view is not None:
            self.context_view.promote_workspace_item(
                item_id, view.item.display_name
            )

    def _show_selected_more_menu(self) -> None:
        item_id = self.more_file_button.property("workspace_item_id")
        view = self._views.get(item_id)
        if view is None:
            return
        if view.effectively_active:
            menu = self._active_context_menu(item_id)
        else:
            menu = QMenu(self)
            menu.addAction("恢复到工作区", lambda: self._restore_item(item_id))
            if self._is_import_root(view):
                menu.addAction(
                    "撤销此次误导入（彻底移除）",
                    lambda: self._undo_import_item(item_id),
                )
        if menu is not None:
            menu.exec(self.more_file_button.mapToGlobal(
                self.more_file_button.rect().bottomLeft()
            ))

    @staticmethod
    def _polish_table(table: QTableWidget, *, stretch_column: int) -> None:
        table.setShowGrid(False)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(32)
        table.horizontalHeader().setHighlightSections(False)
        table.horizontalHeader().setSectionResizeMode(
            stretch_column, QHeaderView.ResizeMode.Stretch
        )

    @staticmethod
    def _empty_detail_html() -> str:
        return (
            "<div style='color:#7b8794; padding:18px 4px;'>"
            "选择工作区中的项目后，这里会显示工作位置、来源和文件状态。"
            "</div>"
        )

    def _set_project_state(self, text: str, state: str = "idle") -> None:
        self.project_state.setText(text)
        self.project_state.setProperty("state", state)
        self.project_state.setVisible(state == "warning")
        self.project_state.style().unpolish(self.project_state)
        self.project_state.style().polish(self.project_state)

    def _workspace_item_icon(self, view: WorkspaceItemView):
        cached = self._workspace_icons.get(view.item.item_kind)
        if cached is not None:
            return cached
        standard_icon = (
            QStyle.StandardPixmap.SP_FileIcon
            if view.item.item_kind == WorkspaceItemKind.FILE
            else QStyle.StandardPixmap.SP_DirIcon
        )
        icon = self.style().standardIcon(standard_icon)
        self._workspace_icons[view.item.item_kind] = icon
        return icon

    def _new_project(self) -> None:
        name, accepted = QInputDialog.getText(self, "新建项目", "项目名称")
        if not accepted or not name.strip():
            return
        root = QFileDialog.getExistingDirectory(self, "选择项目存储根目录")
        if not root:
            return
        self._run_background(
            "创建项目",
            lambda: self._application.create_project(
                CreateProjectRequest(
                    name=name, actor=self._actor, workspace_root=Path(root).absolute()
                )
            ),
            self._project_created,
        )

    def _project_created(self, result) -> None:
        self._activate_project(result.project_id, result.database_path)
        QMessageBox.information(
            self,
            "项目已创建",
            f"项目已保存到：\n{result.workspace_path}",
        )

    def _choose_project(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "打开 PIG Project", "", "PIG Project (project.sqlite)"
        )
        if filename:
            path = Path(filename).absolute()
            self._run_background(
                "打开项目",
                lambda: self._application.load_project(
                    LoadProjectRequest(database_path=path)
                ),
                lambda result: self._project_loaded(result.project.id, path),
            )

    def _project_loaded(self, project_id: str, database_path: Path) -> None:
        self._project_id = project_id
        self._database_path = Path(database_path)
        self.tree.clear()
        self._tree_initialized = False
        self._last_move_undo = None
        self.undo_move_action.setEnabled(False)
        self.context_view.set_project(project_id, database_path)
        self._recovery_required = True
        self._set_project_state("检查恢复状态", "warning")
        self._set_project_actions_enabled(False)
        self._inspect_active_project_recovery()

    def _inspect_active_project_recovery(self) -> None:
        if not self._has_project():
            return
        self._run_background(
            "检查项目恢复状态",
            lambda: self._application.inspect_project_recovery(
                InspectProjectRecoveryRequest(
                    project_id=self._project_id,
                    database_path=self._database_path,
                )
            ),
            self._recovery_inspected,
        )

    def _recovery_inspected(self, result) -> None:
        self._recovery_required = result.recovery_required
        self._recovery_inspection_token = result.inspection_token
        if not result.recovery_required:
            self.recovery_banner.hide()
            self._set_project_state("正在载入")
            self._set_project_actions_enabled(True)
            self._reload_workspace()
            return
        self.recovery_banner.setText(
            f"检测到 {len(result.candidates)} 个中断操作或未登记对象。"
            "项目当前为只读状态；确认恢复前不会移动或删除任何数据。"
        )
        self._set_project_state("需要恢复", "warning")
        self.recovery_banner.show()
        self._set_project_actions_enabled(False)
        preview = "\n".join(
            f"• {value.action.value} · {value.storage_key}"
            for value in result.candidates[:8]
        )
        if len(result.candidates) > 8:
            preview += f"\n• 另有 {len(result.candidates) - 8} 项"
        answer = QMessageBox.question(
            self,
            "项目需要恢复",
            "PIG 发现上次未完整结束的文件操作：\n\n"
            f"{preview}\n\n"
            "是否现在执行已规划的恢复？未知对象只会被可逆隔离，"
            "已登记的 Working 文件不会被自动覆盖。",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._run_background(
                "恢复项目",
                lambda: self._application.recover_workbench_project(
                    RecoverWorkbenchProjectRequest(
                        project_id=self._project_id,
                        database_path=self._database_path,
                        actor=self._actor,
                        inspection_token=result.inspection_token,
                        confirmed=True,
                    )
                ),
                self._recovery_completed,
            )
        else:
            self._reload_workspace()

    def _recovery_completed(self, result) -> None:
        if result.remaining_candidate_count:
            QMessageBox.warning(
                self,
                "恢复未完全结束",
                f"仍有 {result.remaining_candidate_count} 个项目需要处理。",
            )
            self._inspect_active_project_recovery()
            return
        self._recovery_required = False
        self._recovery_inspection_token = None
        self._set_project_state("正在载入")
        self.recovery_banner.hide()
        QMessageBox.information(
            self,
            "恢复完成",
            f"已处理 {result.recovery_run.recovered_count} 项，"
            f"失败 {result.recovery_run.failed_count} 项。",
        )
        self._reload_workspace()

    def _activate_project(self, project_id: str, database_path: Path) -> None:
        self._project_id = project_id
        self._database_path = Path(database_path)
        self.tree.clear()
        self._tree_initialized = False
        self._last_move_undo = None
        self.undo_move_action.setEnabled(False)
        self.context_view.set_project(project_id, database_path)
        self._recovery_required = False
        self._recovery_inspection_token = None
        self._set_project_state("正在载入")
        self.recovery_banner.hide()
        self._set_project_actions_enabled(self._worker_thread is None)
        self._reload_workspace()

    def _choose_files(self) -> None:
        filenames, _ = QFileDialog.getOpenFileNames(self, "添加多个文件")
        if filenames:
            paths = tuple(Path(value).absolute() for value in filenames)
            self._add_inputs(paths, self._selected_folder_id())

    def _choose_folder(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "添加文件夹")
        if directory:
            self._add_inputs((Path(directory).absolute(),), self._selected_folder_id())

    def _add_inputs(self, paths, target_id) -> None:
        if not self._has_project() or not paths:
            return
        self._run_background(
            "添加项目资料",
            lambda control: self._application.add_workspace_inputs(
                AddWorkspaceInputsRequest(
                    project_id=self._project_id,
                    database_path=self._database_path,
                    input_paths=tuple(paths),
                    actor=self._actor,
                    expected_workspace_revision=self._workspace_revision,
                    target_workspace_parent_id=target_id,
                ),
                control=control,
            ),
            self._inputs_added,
            progress=True,
        )

    def _inputs_added(self, result) -> None:
        imported = result.import_result
        QMessageBox.information(
            self,
            "添加完成",
            f"请求：{imported.requested_item_count}\n"
            f"接受：{imported.accepted_item_count}\n"
            f"失败：{imported.failed_item_count}",
        )
        self._reload_workspace()

    def _create_folder(self) -> None:
        self._create_folder_in(self._selected_folder_id())

    def _create_folder_in(self, parent_id: str | None) -> None:
        if not self._has_project():
            return
        name, accepted = QInputDialog.getText(self, "新建工作区文件夹", "文件夹名称")
        if not accepted:
            return
        self._run_background(
            "创建文件夹",
            lambda: self._application.create_workspace_folder(
                CreateWorkspaceFolderRequest(
                    project_id=self._project_id,
                    database_path=self._database_path,
                    display_name=name,
                    actor=self._actor,
                    expected_workspace_revision=self._workspace_revision,
                    parent_workspace_item_id=parent_id,
                )
            ),
            lambda _result: self._reload_workspace(),
        )

    def _move_item(self, item_id: str, parent_id, ordinal: int) -> None:
        if not self._has_project():
            return
        if parent_id == item_id:
            return
        view = self._views.get(item_id)
        if view is None:
            return
        old_parent = view.placement.parent_workspace_item_id
        old_ordinal = view.placement.ordinal
        if parent_id == old_parent and ordinal > old_ordinal:
            ordinal -= 1
        if parent_id == old_parent and ordinal == old_ordinal:
            return
        project_id = self._project_id
        self._run_background(
            "移动工作区项目",
            lambda: self._application.move_workspace_item(
                MoveWorkspaceItemRequest(
                    project_id=self._project_id,
                    database_path=self._database_path,
                    workspace_item_id=item_id,
                    actor=self._actor,
                    expected_workspace_revision=self._workspace_revision,
                    new_parent_workspace_item_id=parent_id,
                    new_ordinal=ordinal,
                )
            ),
            lambda result: self._move_completed(
                project_id, item_id, old_parent, old_ordinal, result.workspace_revision
            ),
        )

    def _move_completed(
        self, project_id: str, item_id: str, old_parent: str | None,
        old_ordinal: int, revision: int,
    ) -> None:
        self._last_move_undo = (project_id, item_id, old_parent, old_ordinal, revision)
        self.undo_move_action.setEnabled(True)
        self._reload_workspace()

    def _undo_last_move(self) -> None:
        pending = self._last_move_undo
        if pending is None or not self._has_project() or self._worker_thread is not None:
            return
        project_id, item_id, old_parent, old_ordinal, revision = pending
        if project_id != self._project_id or revision != self._workspace_revision:
            self._last_move_undo = None
            self.undo_move_action.setEnabled(False)
            self._reload_workspace()
            return
        self._run_background(
            "撤销上次移动",
            lambda: self._application.move_workspace_item(
                MoveWorkspaceItemRequest(
                    project_id=project_id,
                    database_path=self._database_path,
                    workspace_item_id=item_id,
                    actor=self._actor,
                    expected_workspace_revision=revision,
                    new_parent_workspace_item_id=old_parent,
                    new_ordinal=old_ordinal,
                    undo_of_workspace_revision=revision,
                )
            ),
            self._move_undone,
        )

    def _move_undone(self, _result) -> None:
        self._last_move_undo = None
        self.undo_move_action.setEnabled(False)
        self.statusBar().showMessage("已撤销上次移动")
        self._reload_workspace()

    def _show_drag_destination(self, hint: str) -> None:
        self.drag_destination.setText(hint)
        self.drag_destination.setVisible(bool(hint))

    def _rename_item(self, item_id: str) -> None:
        view = self._views.get(item_id)
        if view is None or not view.effectively_active or not self._has_project():
            return
        name, accepted = QInputDialog.getText(
            self, "重命名工作区项目",
            "新名称（保留文件扩展名；仅改变工作区与导出名称，"
            "不重命名已生成的工作副本）",
            text=view.item.display_name,
        )
        if not accepted or name.strip() == view.item.display_name:
            return
        self._run_background(
            "重命名工作区项目",
            lambda: self._application.rename_workspace_item(
                RenameWorkspaceItemRequest(
                    project_id=self._project_id,
                    database_path=self._database_path,
                    workspace_item_id=item_id,
                    display_name=name,
                    actor=self._actor,
                    expected_workspace_revision=self._workspace_revision,
                )
            ),
            lambda _result: self._reload_workspace(),
        )

    def _delete_selected(self) -> None:
        item_id = self._selected_active_id()
        self._soft_delete_item(item_id)

    def _soft_delete_item(self, item_id) -> None:
        if item_id is None or not self._has_project() or item_id not in self._views:
            return
        view = self._views[item_id]
        answer = QMessageBox.question(
            self,
            "确认软删除",
            f"从正常工作区隐藏“{view.item.display_name}”？\n\n"
            "Original、Source 和 Working File 不会被删除。",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._run_background(
            "软删除",
            lambda: self._application.soft_delete_workspace_item(
                SoftDeleteWorkspaceItemRequest(
                    project_id=self._project_id,
                    database_path=self._database_path,
                    workspace_item_id=item_id,
                    actor=self._actor,
                    expected_workspace_revision=self._workspace_revision,
                    confirmed=True,
                )
            ),
            lambda _result: self._reload_workspace(),
        )

    def _undo_import_item(self, item_id) -> None:
        if item_id is None or not self._has_project():
            return
        self._run_background(
            "检查误导入撤销范围",
            lambda: self._application.preview_import_undo(
                PreviewImportUndoRequest(
                    project_id=self._project_id,
                    database_path=self._database_path,
                    workspace_item_id=item_id,
                )
            ),
            self._confirm_import_undo,
        )

    def _confirm_import_undo(self, impact) -> None:
        answer = QMessageBox.question(
            self,
            "确认撤销误导入",
            f"将从本项目彻底移除顶层导入项“{impact.display_name}”及其来源树。\n\n"
            f"Workspace 项目：{impact.workspace_item_count}\n"
            f"Working File：{impact.working_file_count}\n"
            f"其中已修改：{impact.modified_working_file_count}\n"
            f"项目内待移除数据：{self._format_bytes(impact.original_byte_count + impact.working_byte_count)}\n\n"
            "外部原始文件不会被删除；该操作在 PIG 项目内不可恢复。是否继续？",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._run_background(
            "撤销误导入",
            lambda: self._application.undo_imported_item(
                UndoImportedItemRequest(
                    project_id=self._project_id,
                    database_path=self._database_path,
                    workspace_item_id=impact.workspace_item_id,
                    actor=self._actor,
                    expected_workspace_revision=self._workspace_revision,
                    confirmed=True,
                )
            ),
            self._import_undo_completed,
        )

    def _import_undo_completed(self, result) -> None:
        QMessageBox.information(
            self,
            "已撤销误导入",
            f"已从项目移除 {result.purged_workspace_item_count} 个 Workspace 项目，"
            f"清理 {self._format_bytes(result.removed_byte_count)}。\n\n"
            "外部原始文件未被修改。",
        )
        self._reload_workspace()

    def _restore_deleted_item(self) -> None:
        item_id = self.restore_deleted_button.property("workspace_item_id")
        self._restore_item(item_id)

    def _restore_item(self, item_id) -> None:
        if item_id is None or not self._has_project():
            return
        self._run_background(
            "恢复已删除项目",
            lambda: self._application.restore_workspace_item(
                RestoreWorkspaceItemRequest(
                    project_id=self._project_id,
                    database_path=self._database_path,
                    workspace_item_id=item_id,
                    actor=self._actor,
                    expected_workspace_revision=self._workspace_revision,
                )
            ),
            lambda result: self._deleted_restored(result),
        )

    def _deleted_restored(self, result) -> None:
        if result.restore_fallback:
            QMessageBox.information(self, "恢复完成", "原位置不可用，项目已恢复到根目录。")
        self._reload_workspace()

    def _open_selected(self) -> None:
        self._open_item(self.open_selected_button.property("workspace_item_id"))

    def _open_item(self, item_id) -> None:
        if item_id is None or not self._has_project():
            return
        view = self._views.get(item_id)
        if view is None:
            return
        effective_name = (
            Path(view.working_artifact.storage_key).name
            if view.working_artifact is not None
            else view.item.display_name
        ).casefold()
        other = self._opened_names.get(effective_name)
        if other is not None and other != item_id:
            answer = QMessageBox.question(
                self,
                "可能存在 Host Application 同名冲突",
                "本次会话中已向 Host Application 交接过一个同名文件。\n\n"
                "Excel 等程序可能拒绝同时打开不同目录中的同名文件。"
                "请确认另一个文件已经关闭，或取消本次打开。\n\n是否继续？",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._run_background(
            "打开文件",
            lambda: self._application.open_workspace_item(
                OpenWorkspaceItemRequest(
                    project_id=self._project_id,
                    database_path=self._database_path,
                    workspace_item_id=item_id,
                    actor=self._actor,
                )
            ),
            self._file_opened,
        )

    def _file_opened(self, result) -> None:
        self._opened_names[result.path.name.casefold()] = result.workspace_item_id
        self.statusBar().showMessage(f"已交给系统打开：{result.path.name}")
        self._reload_workspace()

    def _refresh_selected_file(self, reason=WorkingRefreshReason.EXPLICIT) -> None:
        item_id = self.refresh_file_button.property("workspace_item_id")
        if item_id is None or not self._has_project():
            return
        self._run_background(
            "刷新文件状态",
            lambda: self._application.refresh_working_artifact(
                RefreshWorkingArtifactRequest(
                    project_id=self._project_id,
                    database_path=self._database_path,
                    workspace_item_id=item_id,
                    actor=self._actor,
                    reason=reason,
                )
            ),
            lambda _result: self._reload_workspace(),
        )

    def _restore_working_file(self) -> None:
        item_id = self.restore_working_button.property("workspace_item_id")
        view = self._views.get(item_id)
        if view is None or view.working_artifact is None or not self._has_project():
            return
        status = view.working_artifact.content_status
        confirmed = False
        if status in {WorkingContentStatus.MODIFIED, WorkingContentStatus.UNREADABLE}:
            confirmed = QMessageBox.question(
                self,
                "确认恢复原始内容",
                "该操作会覆盖当前 Working File。是否继续？",
            ) == QMessageBox.StandardButton.Yes
            if not confirmed:
                return
        self._run_background(
            "恢复 Working File",
            lambda: self._application.restore_working_artifact(
                RestoreWorkingArtifactRequest(
                    project_id=self._project_id,
                    database_path=self._database_path,
                    workspace_item_id=item_id,
                    actor=self._actor,
                    confirmed_replace=confirmed,
                )
            ),
            lambda _result: self._reload_workspace(),
        )

    def _rollback_working_file(self) -> None:
        item_id = self.rollback_button.property("workspace_item_id")
        view = self._views.get(item_id)
        if view is None or view.previous_revision is None or not self._has_project():
            return
        answer = QMessageBox.question(
            self,
            "确认回滚到上一版本",
            "该操作会用上一版本覆盖当前 Working File。\n"
            "当前版本会被保留为新的上一版本，因此可以再次切换回来。\n\n是否继续？",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._run_background(
            "回滚 Working File",
            lambda: self._application.rollback_working_artifact(
                RollbackWorkingArtifactRequest(
                    project_id=self._project_id,
                    database_path=self._database_path,
                    workspace_item_id=item_id,
                    actor=self._actor,
                    confirmed_replace=True,
                )
            ),
            lambda _result: self._reload_workspace(),
        )

    def _export_selected(self) -> None:
        if not self._has_project():
            return
        item_ids = self._selected_export_ids()
        if not item_ids:
            QMessageBox.information(self, "导出", "请先选择一个或多个项目。")
            return
        selected = tuple(self._views[item_id] for item_id in item_ids)
        single = selected[0] if len(selected) == 1 else None
        directory_export = (
            single is not None and single.item.item_kind in {
                WorkspaceItemKind.FOLDER, WorkspaceItemKind.CONTAINER_VIEW,
            }
        )
        if directory_export:
            parent = QFileDialog.getExistingDirectory(self, "选择导出文件夹的上级目录")
            if not parent:
                return
            destination = (
                Path(parent).absolute()
                / safe_filesystem_segment(
                    single.item.display_name + "-展开"
                    if single.item.item_kind == WorkspaceItemKind.CONTAINER_VIEW
                    else single.item.display_name
                )
            )
            if destination.exists() or destination.is_symlink():
                QMessageBox.warning(
                    self,
                    "导出文件夹",
                    f"目标文件夹已存在：\n{destination}\n\n"
                    "为避免合并或覆盖，请选择其他上级目录。",
                )
                return
            confirmed = False
        elif single is not None:
            default_name = single.item.display_name
            filename, _ = QFileDialog.getSaveFileName(self, "导出文件", default_name)
            if not filename:
                return
            destination = Path(filename).absolute()
            confirmed = False
            if destination.exists() or destination.is_symlink():
                confirmed = QMessageBox.question(
                    self,
                    "确认覆盖导出文件",
                    f"目标已存在：\n{destination}\n\n是否覆盖？",
                ) == QMessageBox.StandardButton.Yes
                if not confirmed:
                    return
        else:
            filename, _ = QFileDialog.getSaveFileName(
                self,
                "将所选项目导出为 ZIP",
                f"{self._project_name}-导出.zip",
                "ZIP Archive (*.zip)",
            )
            if not filename:
                return
            destination = Path(filename).absolute()
            confirmed = False
            if destination.exists() or destination.is_symlink():
                confirmed = QMessageBox.question(
                    self,
                    "确认覆盖导出文件",
                    f"目标已存在：\n{destination}\n\n是否覆盖？",
                ) == QMessageBox.StandardButton.Yes
                if not confirmed:
                    return
        self._run_background(
            "导出 Workspace 文件",
            lambda control: self._application.export_workspace_items(
                ExportWorkspaceItemsRequest(
                    project_id=self._project_id,
                    database_path=self._database_path,
                    workspace_item_ids=item_ids,
                    destination_path=destination,
                    actor=self._actor,
                    confirmed_replace=confirmed,
                ),
                control=control,
            ),
            self._export_completed,
            progress=True,
        )

    def _export_completed(self, result) -> None:
        kind = {
            WorkspaceExportKind.FILE: "文件",
            WorkspaceExportKind.DIRECTORY: "文件夹",
            WorkspaceExportKind.ZIP: "ZIP 包",
        }[result.export_kind]
        QMessageBox.information(
            self,
            "导出成功",
            f"已导出{kind}（{result.entry_count} 个文件）：\n{result.destination_path}",
        )
        self._reload_workspace()

    def _search(self) -> None:
        if not self._has_project():
            return
        self._run_background(
            "搜索工作区",
            lambda: self._application.search_workspace_items(
                SearchWorkspaceItemsRequest(
                    project_id=self._project_id,
                    database_path=self._database_path,
                    query=self.search_text.text(),
                    formats=self.format_filter.selected_values(),
                    content_statuses=self.content_filter.selected_values(),
                )
            ),
            self._show_search_results,
        )

    def _show_search_results(self, result) -> None:
        self.search_results.setRowCount(0)
        for view in result.items:
            row = self.search_results.rowCount()
            self.search_results.insertRow(row)
            values = (
                view.item.display_name,
                view.workspace_path,
                view.item.item_kind.value,
                "" if view.source_node is None else view.source_node.format.value,
                self._working_status(view),
            )
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if column == 0:
                    cell.setData(ITEM_ID_ROLE, view.item.id)
                    cell.setIcon(self._workspace_item_icon(view))
                self.search_results.setItem(row, column, cell)
        self.left_tabs.setCurrentWidget(self.search_results)
        suffix = "（仅显示前 200 条）" if result.has_more else ""
        self.statusBar().showMessage(f"找到 {result.total} 项{suffix}")

    def _clear_search(self) -> None:
        self.search_text.clear()
        self.format_filter.clear_selection()
        self.content_filter.clear_selection()
        self.search_results.setRowCount(0)
        self.left_tabs.setCurrentWidget(self.tree)

    def _reload_workspace(self) -> None:
        if not self._has_project():
            return
        if self._worker_thread is not None:
            self._reload_after_background = True
            return
        self._run_background(
            "加载工作区",
            lambda: (
                self._application.get_workspace_tree(
                    GetWorkspaceTreeRequest(
                        project_id=self._project_id,
                        database_path=self._database_path,
                    )
                ),
                self._application.get_recent_project_events(
                    GetRecentProjectEventsRequest(
                        project_id=self._project_id,
                        database_path=self._database_path,
                    )
                ),
            ),
            lambda result: self._apply_workspace(result[0], result[1].events),
        )

    def _apply_workspace(self, result, events) -> None:
        selected_id = self.open_selected_button.property("workspace_item_id")
        expanded_ids = (
            tuple(
                item_id for item_id in self.tree.model().views
                if self.tree.isExpanded(self.tree.model().index_for_id(item_id))
            ) if self._tree_initialized else ()
        )
        self._workspace_revision = result.workspace_revision
        if self._last_move_undo is not None and (
            self._last_move_undo[0] != self._project_id
            or self._last_move_undo[4] != result.workspace_revision
        ):
            self._last_move_undo = None
        self.undo_move_action.setEnabled(
            self._last_move_undo is not None and not self._recovery_required
        )
        self.context_view.update_workspace_revision(result.workspace_revision)
        self._views = {
            view.item.id: view for view in (*result.items, *result.deleted_items)
        }
        self.setWindowTitle(f"PIG — {result.project.name}")
        self._project_name = result.project.name
        self.project_location.setText(result.project.name)
        self.project_meta.setText(
            f"Revision {result.workspace_revision}  ·  {self._database_path.parent}"
        )
        self.project_location.setToolTip(str(self._database_path))
        self.project_meta.setToolTip(str(self._database_path))
        self._set_project_state("工作区就绪", "ready")
        self.tree.set_views(result.items)
        if self._tree_initialized:
            for item_id in expanded_ids:
                index = self.tree.model().index_for_id(item_id)
                if index.isValid():
                    self.tree.setExpanded(index, True)
        else:
            self.tree.expandToDepth(1)
            self._tree_initialized = True
        self.deleted_items.setRowCount(0)
        for view in result.deleted_items:
            row = self.deleted_items.rowCount()
            self.deleted_items.insertRow(row)
            values = (
                view.item.display_name,
                view.workspace_path,
                view.item.item_kind.value,
                "" if view.item.deleted_at is None else self._local_event_time(view.item.deleted_at),
            )
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if column == 0:
                    cell.setData(ITEM_ID_ROLE, view.item.id)
                    cell.setIcon(self._workspace_item_icon(view))
                self.deleted_items.setItem(row, column, cell)
        self._populate_events(events)
        selected_index = self.tree.model().index_for_id(selected_id)
        if selected_index.isValid():
            self.tree.setCurrentIndex(selected_index)
            self._show_view(selected_id)
        else:
            self._show_view(None)
        self.statusBar().showMessage(
            f"{len(result.items)} 项文件与文件夹 · {len(result.deleted_items)} 项在回收站"
        )

    def _tree_selection_changed(self) -> None:
        selected = self.tree.selectedItems()
        self._show_view(
            selected[0].data(0, ITEM_ID_ROLE) if len(selected) == 1 else None
        )

    def _search_selection_changed(self) -> None:
        rows = self.search_results.selectionModel().selectedRows()
        self._show_view(
            self._selected_table_id(self.search_results, rows[0].row())
            if len(rows) == 1
            else None
        )

    def _deleted_selection_changed(self) -> None:
        item_id = self._selected_table_id(self.deleted_items)
        self.restore_deleted_button.setProperty("workspace_item_id", item_id)
        self.restore_deleted_button.setEnabled(
            item_id is not None and self._worker_thread is None
        )
        self._show_view(item_id)

    def _tree_double_clicked(self, item, _column) -> None:
        item_id = item.data(0, ITEM_ID_ROLE)
        view = self._views.get(item_id)
        if view is not None and view.item.item_kind == WorkspaceItemKind.FILE:
            self._open_item(item_id)
        else:
            item.setExpanded(not item.isExpanded())

    def _search_double_clicked(self, item, _column) -> None:
        item_id = self._selected_table_id(self.search_results, item.row())
        view = self._views.get(item_id)
        if view is not None and view.item.item_kind == WorkspaceItemKind.FILE:
            self._open_item(item_id)

    def _show_tree_context_menu(self, position) -> None:
        item = self.tree.itemAt(position)
        if item is None:
            if self._has_project() and self._worker_thread is None:
                menu = QMenu(self)
                menu.addAction("在根目录新建文件夹", lambda: self._create_folder_in(None))
                menu.exec(self.tree.viewport().mapToGlobal(position))
            return
        if not item.isSelected():
            self.tree.clearSelection()
            self.tree.setCurrentItem(item)
            item.setSelected(True)
        self._show_active_context_menu(
            self.tree.viewport().mapToGlobal(position),
            item.data(0, ITEM_ID_ROLE),
        )

    def _show_search_context_menu(self, position) -> None:
        item = self.search_results.itemAt(position)
        if item is None:
            return
        row = item.row()
        if not self.search_results.selectionModel().isRowSelected(
            row, self.search_results.rootIndex()
        ):
            self.search_results.clearSelection()
            self.search_results.selectRow(row)
        self._show_active_context_menu(
            self.search_results.viewport().mapToGlobal(position),
            self._selected_table_id(self.search_results, row),
        )

    def _show_active_context_menu(self, global_position, item_id) -> None:
        menu = self._active_context_menu(item_id)
        if menu is not None:
            menu.exec(global_position)

    def _active_context_menu(self, item_id):
        view = self._views.get(item_id)
        if view is None or not view.effectively_active or self._worker_thread is not None:
            return None
        menu = QMenu(self)
        selected_ids = self._selected_export_ids()
        if view.item.item_kind == WorkspaceItemKind.FOLDER and len(selected_ids) == 1:
            menu.addAction(
                "在此新建文件夹", lambda: self._create_folder_in(item_id)
            )
            menu.addSeparator()
        if len(selected_ids) == 1 and view.item.item_kind in {
            WorkspaceItemKind.FILE, WorkspaceItemKind.FOLDER,
        }:
            menu.addAction("重命名", lambda: self._rename_item(item_id))
            menu.addSeparator()
        if len(selected_ids) == 1 and view.item.item_kind == WorkspaceItemKind.FILE:
            menu.addAction("查看物理位置", lambda: self._show_physical_location(item_id))
            menu.addSeparator()
        if (
            view.item.item_kind == WorkspaceItemKind.FILE
            and view.source_node is not None
            and view.source_node.kind == NodeKind.FILE
            and len(selected_ids) == 1
        ):
            menu.addAction("打开", lambda: self._open_item(item_id))
            menu.addAction(
                "加入 Project Context",
                lambda: self.context_view.promote_workspace_item(
                    item_id, view.item.display_name
                ),
            )
            if view.working_artifact is not None:
                menu.addAction("刷新文件状态", self._refresh_selected_file)
                if view.working_artifact.content_status != WorkingContentStatus.CLEAN:
                    menu.addAction("从原始备份恢复", self._restore_working_file)
            if view.previous_revision is not None:
                menu.addAction("回滚到上一版本", self._rollback_working_file)
            menu.addSeparator()
        elif (
            view.item.item_kind == WorkspaceItemKind.CONTAINER_VIEW
            and view.source_node is not None
            and view.source_node.format == NodeFormat.EML
            and len(selected_ids) == 1
        ):
            menu.addAction(
                "加入 Project Context（EML 原邮件）",
                lambda: self.context_view.promote_workspace_item(
                    item_id, view.item.display_name
                ),
            )
            menu.addSeparator()
        menu.addAction(
            "导出所选" if len(selected_ids) > 1 else "导出",
            self._export_selected,
        )
        if len(selected_ids) == 1:
            menu.addAction("软删除", lambda: self._soft_delete_item(item_id))
            if self._is_import_root(view):
                menu.addSeparator()
                menu.addAction(
                    "撤销此次误导入（彻底移除）",
                    lambda: self._undo_import_item(item_id),
                )
        return menu

    def _show_physical_location(self, item_id: str) -> None:
        if not self._has_project():
            return
        self._run_background(
            "读取物理位置",
            lambda: self._application.get_workspace_physical_location(
                GetWorkspacePhysicalLocationRequest(
                    project_id=self._project_id,
                    database_path=self._database_path,
                    workspace_item_id=item_id,
                )
            ),
            self._physical_location_ready,
        )

    def _physical_location_ready(self, result) -> None:
        working = (str(result.working_path) if result.working_path is not None
                   else "尚未生成独立工作文件；打开此文件后再查看。")
        original = (str(result.original_path) if result.original_path is not None
                    else "无可用的独立原始文件路径。")
        if result.original_is_parent_container and result.original_path is not None:
            original += "\n（这是所在原始容器，文件本身不是独立物理文件。）"
        box = QMessageBox(self)
        box.setWindowTitle("文件物理位置")
        box.setText(
            f"当前工作文件：\n{working}\n\n"
            f"原始备份或所在容器：\n{original}\n\n"
            f"工作区相对位置：\n{result.logical_path}"
        )
        box.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        box.exec()

    def _show_deleted_context_menu(self, position) -> None:
        item = self.deleted_items.itemAt(position)
        if item is None or self._worker_thread is not None:
            return
        row = item.row()
        self.deleted_items.clearSelection()
        self.deleted_items.selectRow(row)
        item_id = self._selected_table_id(self.deleted_items, row)
        menu = QMenu(self)
        menu.addAction("恢复到工作区", lambda: self._restore_item(item_id))
        view = self._views.get(item_id)
        if view is not None and self._is_import_root(view):
            menu.addSeparator()
            menu.addAction(
                "撤销此次误导入（彻底移除）",
                lambda: self._undo_import_item(item_id),
            )
        menu.exec(self.deleted_items.viewport().mapToGlobal(position))

    @staticmethod
    def _is_import_root(view: WorkspaceItemView) -> bool:
        return (
            view.source is not None
            and view.source_node is not None
            and view.source.root_node_id == view.source_node.id
        )

    def _show_view(self, item_id) -> None:
        view = self._views.get(item_id)
        for button in (
            self.open_selected_button,
            self.add_to_context_button,
            self.more_file_button,
            self.refresh_file_button,
            self.restore_working_button,
            self.rollback_button,
        ):
            button.setProperty("workspace_item_id", item_id)
        if view is None:
            self.detail_title.setText("未选择文件")
            self.detail_subtitle.setText("")
            self.detail_status.hide()
            self.details.setHtml(self._empty_detail_html())
            self.versions.setRowCount(0)
            self._update_item_buttons(None)
            return
        self.detail_title.setText(view.item.display_name)
        self.detail_subtitle.setText(view.workspace_path)
        self.detail_status.setText(
            self._friendly_value(self._working_status(view))
            if (view.item.item_kind == WorkspaceItemKind.FILE
                or self._working_status(view) in _SOURCE_FAILURE_STATUSES)
            else self._friendly_value(view.item.item_kind.value)
        )
        self.detail_status.show()
        self.details.setHtml(self._detail_html(view))
        self._show_versions(view)
        self._update_item_buttons(view)
        if self.right_tabs.currentWidget() is self.events:
            self.right_tabs.setCurrentWidget(self.details_page)
            self.activity_button.setText("活动记录")

    def _detail_html(self, view: WorkspaceItemView) -> str:
        def row(label: str, value: object, *, code: bool = False) -> str:
            safe_label = html.escape(label)
            safe_value = html.escape(str(value))
            family = "font-family:Consolas,'Courier New',monospace;" if code else ""
            return (
                "<tr>"
                "<td style='width:112px;color:#73808d;padding:5px 10px 5px 0;"
                "vertical-align:top;'>"
                f"{safe_label}</td>"
                f"<td style='color:#263442;padding:5px 0;{family}'>"
                f"{safe_value}</td>"
                "</tr>"
            )

        sections = [
            "<div class='section'>工作区信息</div>",
            "<table width='100%' cellspacing='0'>",
            row("工作区路径", view.workspace_path),
            row("项目类型", self._friendly_value(view.item.item_kind.value)),
            row("生命周期", self._friendly_value(view.item.lifecycle_status.value)),
            row(
                "准备状态",
                self._friendly_value(view.item.materialization_status.value),
            ),
            row("文件状态", self._friendly_value(self._working_status(view))),
            "</table>",
        ]
        node = view.source_node
        if node is not None:
            sections.extend(
                (
                    "<div class='section'>来源</div>",
                    "<table width='100%' cellspacing='0'>",
                    row("原始名称", node.original_name),
                    row("来源路径", node.logical_path),
                    row("格式", node.format.value),
                    row("处理状态", self._friendly_value(node.status.value)),
                    row("来源节点 ID", node.id, code=True),
                    "</table>",
                )
            )
        working = view.working_artifact
        if working is not None:
            sections.extend(
                (
                    "<div class='section'>当前工作副本</div>",
                    "<table width='100%' cellspacing='0'>",
                    row("存储标识", working.storage_key, code=True),
                    row("原始基线大小", self._format_bytes(working.baseline_size)),
                    row("当前大小", self._format_bytes(working.current_size)),
                    row("原始基线 SHA-256", working.baseline_sha256, code=True),
                    row("当前 SHA-256", working.current_sha256, code=True),
                    "</table>",
                )
            )
        return (
            "<style>"
            "body{font-family:'Microsoft YaHei UI';font-size:12px;color:#263442;}"
            ".section{margin-top:8px;padding:7px 0 5px 0;color:#315f86;"
            "font-size:13px;font-weight:600;border-bottom:1px solid #e6ebef;}"
            "td{word-wrap:break-word;}"
            "</style>"
            + "".join(sections)
        )

    @staticmethod
    def _friendly_value(value: str) -> str:
        return {
            "FILE": "文件",
            "FOLDER": "文件夹",
            "CONTAINER_VIEW": "容器结构",
            "ACTIVE": "使用中",
            "DELETED": "已移到回收站",
            "PURGED": "已撤销导入",
            "VIRTUAL": "按需准备（尚未打开）",
            "MATERIALIZING": "正在准备",
            "MATERIALIZED": "工作副本已就绪",
            "CLEAN": "未检测到修改",
            "CHECKING": "正在检查",
            "MODIFIED": "已修改",
            "MISSING": "工作文件缺失",
            "UNREADABLE": "工作文件无法读取",
            "DISCOVERED": "已发现",
            "PENDING": "等待处理",
            "PROCESSING": "正在处理",
            "SUCCESS": "处理成功",
            "PARTIAL_SUCCESS": "部分成功",
            "UNSUPPORTED": "暂不支持",
            "PASSWORD_REQUIRED": "需要密码",
            "CORRUPTED": "文件损坏",
            "LIMIT_EXCEEDED": "超过安全限制",
            "SECURITY_BLOCKED": "已被安全策略阻止",
            "SOURCE_MISSING": "来源缺失",
            "SOURCE_CHANGED": "来源已变化",
            "FAILED": "处理失败",
            "SKIPPED": "已跳过",
            "INTERRUPTED": "操作中断",
        }.get(value, value)

    def _show_versions(self, view) -> None:
        self.versions.setRowCount(0)
        for label, revision in (
            ("当前", view.current_revision),
            ("上一版本", view.previous_revision),
        ):
            if revision is None:
                continue
            row = self.versions.rowCount()
            self.versions.insertRow(row)
            values = (
                label,
                self._local_event_time(revision.file_modified_at),
                self._local_event_time(revision.detected_at),
                revision.sha256,
            )
            for column, value in enumerate(values):
                self.versions.setItem(row, column, QTableWidgetItem(value))

    def _update_item_buttons(self, view) -> None:
        available = (
            view is not None
            and view.effectively_active
            and self._worker_thread is None
            and not self._recovery_required
        )
        is_file = available and view.item.item_kind == WorkspaceItemKind.FILE
        working = None if view is None else view.working_artifact
        promotable_shape = (
            view is not None and view.effectively_active
            and view.source_node is not None
            and (
                (view.item.item_kind == WorkspaceItemKind.FILE
                 and view.source_node.kind == NodeKind.FILE)
                or (view.item.item_kind == WorkspaceItemKind.CONTAINER_VIEW
                    and view.source_node.format == NodeFormat.EML)
            )
        )
        self.open_selected_button.setVisible(
            view is not None and view.item.item_kind == WorkspaceItemKind.FILE
            and view.effectively_active
        )
        self.add_to_context_button.setVisible(promotable_shape)
        self.restore_deleted_button.setVisible(
            view is not None and not view.effectively_active
        )
        self.more_file_button.setVisible(view is not None)
        self.more_file_button.setEnabled(available or (
            view is not None and not view.effectively_active
            and self._worker_thread is None and not self._recovery_required
        ))
        self.advanced_toggle.setVisible(view is not None)
        self.open_selected_button.setEnabled(is_file)
        self.add_to_context_button.setEnabled(available and promotable_shape)
        self.refresh_file_button.setEnabled(is_file and working is not None)
        self.restore_working_button.setEnabled(
            is_file
            and working is not None
            and working.content_status != WorkingContentStatus.CLEAN
        )
        self.rollback_button.setEnabled(
            is_file and view is not None and view.previous_revision is not None
        )
        self.export_action.setEnabled(
            bool(self._selected_export_ids())
            and self._worker_thread is None
            and not self._recovery_required
        )

    def _selected_export_ids(self) -> tuple[str, ...]:
        if self.left_tabs.currentWidget() is self.search_results:
            rows = sorted(
                index.row()
                for index in self.search_results.selectionModel().selectedRows()
            )
            values = [self._selected_table_id(self.search_results, row) for row in rows]
        elif self.left_tabs.currentWidget() is self.tree:
            values = [item.data(0, ITEM_ID_ROLE) for item in self.tree.selectedItems()]
        else:
            values = []
        return tuple(value for value in values if value in self._views)

    def _selected_folder_id(self):
        item_id = self._selected_active_id()
        view = self._views.get(item_id)
        return (
            item_id
            if view is not None and view.item.item_kind == WorkspaceItemKind.FOLDER
            else None
        )

    def _selected_active_id(self):
        if self.left_tabs.currentWidget() is self.search_results:
            rows = self.search_results.selectionModel().selectedRows()
            return (
                self._selected_table_id(self.search_results, rows[0].row())
                if len(rows) == 1 else None
            )
        selected = self.tree.selectedItems()
        return None if not selected else selected[0].data(0, ITEM_ID_ROLE)

    @staticmethod
    def _selected_table_id(table, row=None):
        if row is None:
            selected = table.selectedItems()
            if not selected:
                return None
            row = selected[0].row()
        first = table.item(row, 0)
        return None if first is None else first.data(ITEM_ID_ROLE)

    @staticmethod
    def _working_status(view: WorkspaceItemView) -> str:
        return _visible_file_status(view)

    @staticmethod
    def _format_bytes(value: int) -> str:
        size = float(value)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if size < 1024 or unit == "TB":
                return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
            size /= 1024
        return f"{value} B"

    def _populate_events(self, events) -> None:
        recent = list(events)[-300:]
        undone_revisions = {
            event.details.get("undo_of_workspace_revision")
            for event in recent
            if event.event_type == EventType.WORKSPACE_ITEM_MOVED
            and event.details.get("undo_of_workspace_revision") is not None
        }
        recent = [
            event for event in recent
            if not (
                event.event_type == EventType.WORKSPACE_ITEM_MOVED
                and event.details.get("workspace_revision") in undone_revisions
            )
        ]
        self.events.setRowCount(len(recent))
        for row, event in enumerate(reversed(recent)):
            event_label = (
                "已撤销移动"
                if event.event_type == EventType.WORKSPACE_ITEM_MOVED
                and event.details.get("undo_of_workspace_revision") is not None
                else event.event_type.value
            )
            values = (
                self._local_event_time(event.occurred_at),
                event.severity.value,
                event_label,
                event.workspace_item_id or "",
                "" if event.error_code is None else event.error_code.value,
            )
            for column, value in enumerate(values):
                self.events.setItem(row, column, QTableWidgetItem(value))

    def _run_background(
        self,
        operation,
        action,
        on_success,
        *,
        progress: bool = False,
    ) -> None:
        if self._worker_thread is not None:
            QMessageBox.information(
                self, operation, f"请等待当前操作完成：{self._busy_operation}"
            )
            return
        self._background_control = OperationControl() if progress else None
        self._background_progress_sequence = 0
        self._worker_thread = self._executor.submit(
            action,
            self._background_control,
        ) if progress else self._executor.submit(action)
        self._background_success = on_success
        self._background_operation = operation
        self._busy_operation = operation
        self._set_busy(True)
        self.statusBar().showMessage(f"正在{operation}…")
        self._background_timer.start()

    def _poll_background(self) -> None:
        future = self._worker_thread
        if self._background_control is not None:
            snapshot = self._background_control.latest
            if (
                snapshot is not None
                and snapshot.sequence != self._background_progress_sequence
            ):
                self._background_progress_sequence = snapshot.sequence
                self._render_operation_progress(snapshot)
        if future is None or not future.done():
            return
        self._background_timer.stop()
        success = self._background_success
        operation = self._background_operation or "操作"
        self._worker_thread = None
        self._background_success = None
        self._background_operation = None
        self._busy_operation = None
        self._background_control = None
        self._set_busy(False)
        try:
            result = future.result()
        except BaseException as exc:
            if isinstance(exc, ApplicationError) and exc.code == "RECOVERY_REQUIRED":
                self._recovery_required = True
                self._set_project_state("需要恢复", "warning")
                self.statusBar().showMessage(
                    "项目存在未完成的文件操作；请先检查并恢复，再重试当前操作"
                )
                self._inspect_active_project_recovery()
                return
            self._show_failure(operation, exc)
            if isinstance(exc, ApplicationError):
                if exc.code in {
                    "WORKSPACE_REVISION_CONFLICT",
                    "WORKSPACE_CHANGED_DURING_CAPTURE",
                }:
                    self._reload_workspace()
                if exc.code in {
                    "CONTEXT_WRITE_CONFLICT",
                    "CONTEXT_CLEANUP_PREVIEW_STALE",
                }:
                    self.context_view.reload()
            return
        if success is not None:
            success(result)

    def _set_busy(self, busy: bool) -> None:
        self.busy_indicator.setVisible(busy)
        if busy and self._background_control is None:
            self.busy_indicator.setRange(0, 0)
        elif busy:
            self.busy_indicator.setRange(0, 100)
            self.busy_indicator.setValue(0)
        else:
            self.cancel_operation_button.hide()
        self.new_project_action.setEnabled(not busy)
        self.open_project_action.setEnabled(not busy)
        self._set_project_actions_enabled(self._has_project() and not busy)
        for widget in (
            self.search_text,
            self.format_filter,
            self.content_filter,
            self.filter_button,
            self.search_button,
            self.clear_search_button,
            self.trash_button,
            self.activity_button,
            self.tree,
        ):
            widget.setEnabled(not busy)
        if not busy and self.left_tabs.currentWidget() is self.deleted_items:
            self.search_text.setEnabled(False)
        current = self._views.get(
            self.open_selected_button.property("workspace_item_id")
        )
        self._update_item_buttons(None if busy else current)
        self.restore_deleted_button.setEnabled(
            not busy
            and self.restore_deleted_button.property("workspace_item_id") is not None
        )
        self.context_view.set_busy(busy)

    def _set_project_actions_enabled(self, enabled: bool) -> None:
        enabled = enabled and not self._recovery_required
        for action in (
            self.add_files_action,
            self.add_folder_action,
            self.create_folder_action,
            self.delete_action,
            self.refresh_action,
            self.export_action,
        ):
            action.setEnabled(enabled)
        if enabled:
            self.export_action.setEnabled(bool(self._selected_export_ids()))
        self.recovery_action.setEnabled(
            self._has_project()
            and self._recovery_required
            and self._worker_thread is None
        )

    def _show_failure(self, operation: str, exc: BaseException) -> None:
        if isinstance(exc, ApplicationError):
            if exc.code == "OPERATION_CANCELLED":
                QMessageBox.information(self, operation, "操作已在安全检查点停止。")
            elif exc.code in {
                "UNSUPPORTED_PROJECT_SCHEMA_REVISION",
                "PROJECT_UPGRADE_REQUIRED",
            }:
                QMessageBox.warning(
                    self, operation,
                    "此项目使用旧版数据库结构，当前源码不会自动迁移或改写它。"
                    "请新建项目并重新导入测试资料；如需保留旧项目数据，请单独提出迁移需求。"
                    f"\n\n错误码：{exc.code}",
                )
            else:
                QMessageBox.warning(self, operation, f"{exc.message}\n\n错误码：{exc.code}")
        elif isinstance(exc, PermissionError):
            self._logger.error(
                "desktop operation denied by filesystem permissions: %s",
                operation,
                exc_info=(type(exc), exc, exc.__traceback__),
            )
            QMessageBox.warning(
                self,
                operation,
                "当前程序无法写入所选位置。请检查文件夹权限；如果程序是从受限的"
                "测试环境启动，请改从本机终端启动源码桌面端后重试。"
                f"\n\n位置：{exc.filename or '未提供'}",
            )
        else:
            self._logger.error(
                "desktop background operation failed: %s",
                operation,
                exc_info=(type(exc), exc, exc.__traceback__),
            )
            QMessageBox.critical(self, operation, "操作失败。技术细节已写入应用日志。")

    def _cancel_background(self) -> None:
        control = self._background_control
        if control is None:
            return
        control.cancel()
        self.cancel_operation_button.setEnabled(False)
        self.statusBar().showMessage("已请求取消，正在等待安全检查点…")

    def _render_operation_progress(
        self, snapshot: OperationProgressSnapshot
    ) -> None:
        labels = {
            OperationStage.PREFLIGHT: "正在检查输入",
            OperationStage.SNAPSHOT_COPY: "正在建立原始备份",
            OperationStage.STRUCTURE_INSPECTION: "正在分析文件结构",
            OperationStage.EXPORT_PREPARATION: "正在准备导出",
            OperationStage.EXPORT_WRITE: "正在写入导出文件",
            OperationStage.EXPORT_VERIFICATION: "正在校验导出文件",
            OperationStage.FINALIZING: "正在完成原子发布",
            OperationStage.CONTEXT_CAPTURE: "正在捕获 Context Revision",
            OperationStage.CONTENT_EXTRACTION: "正在提取固定 Revision 内容",
            OperationStage.COMPLETED: "操作完成",
        }
        ratio = snapshot.ratio
        if ratio is None:
            self.busy_indicator.setRange(0, 0)
        else:
            self.busy_indicator.setRange(0, 100)
            self.busy_indicator.setValue(round(ratio * 100))
        self.cancel_operation_button.setVisible(
            snapshot.stage != OperationStage.COMPLETED
        )
        self.cancel_operation_button.setEnabled(
            snapshot.cancellable and not snapshot.cancellation_requested
        )
        message = labels[snapshot.stage]
        if snapshot.current_item:
            message += f"：{snapshot.current_item}"
        if snapshot.warning:
            message += f"（{snapshot.warning}）"
        if snapshot.cancellation_requested:
            message = "已请求取消，正在等待安全检查点…"
        elif not snapshot.cancellable and snapshot.stage != OperationStage.COMPLETED:
            message += "（正在完成，暂不可取消）"
        self.statusBar().showMessage(message)

    def _project_mode_changed(self, index: int) -> None:
        if (
            hasattr(self, "context_view")
            and self.mode_tabs.widget(index) is self.context_view
            and self._worker_thread is None
        ):
            self.context_view.activate()

    def event(self, event: QEvent) -> bool:
        result = super().event(event)
        if (
            event.type() == QEvent.Type.WindowActivate
            and hasattr(self, "refresh_file_button")
            and not self._closed
            and not self._focus_refresh_pending
        ):
            self._focus_refresh_pending = True
            QTimer.singleShot(500, self._focus_refresh_selected)
        return result

    def _focus_refresh_selected(self) -> None:
        self._focus_refresh_pending = False
        if self._closed or self._worker_thread is not None:
            return
        item_id = self.refresh_file_button.property("workspace_item_id")
        view = self._views.get(item_id)
        if view is not None and view.working_artifact is not None:
            self._refresh_selected_file(WorkingRefreshReason.FOCUS_GAINED)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._worker_thread is not None:
            QMessageBox.warning(
                self,
                "操作仍在执行",
                "PIG 正在执行持久化或文件操作，请等待完成后再关闭。",
            )
            event.ignore()
            return
        self._closed = True
        self._executor.shutdown(wait=False, cancel_futures=True)
        super().closeEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = tuple(
            Path(url.toLocalFile()).absolute()
            for url in event.mimeData().urls()
            if url.isLocalFile()
        )
        if paths and self._has_project():
            self._add_inputs(paths, None)
            event.acceptProposedAction()
        else:
            event.ignore()

    def _has_project(self) -> bool:
        return self._project_id is not None and self._database_path is not None

    @staticmethod
    def _event_datetime(value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value

    @classmethod
    def _local_event_time(cls, value: datetime) -> str:
        return cls._event_datetime(value).astimezone().strftime("%Y-%m-%d %H:%M:%S")
