from __future__ import annotations

import html
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QAbstractListModel, QAbstractTableModel, QModelIndex, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from pig.application.contracts import (
    AdvanceContextRevisionRequest,
    ContextItemLifecycleRequest,
    ContextSectionLifecycleRequest,
    CreateContextSectionRequest,
    ExecuteContextRevisionCleanupRequest,
    GetContextItemDetailsRequest,
    GetContextPackExportsRequest,
    PreflightContextPackExportRequest,
    ExecuteContextPackExportRequest,
    ContextPackRevisionChoice,
    CancelContextPackPreflightRequest,
    RecoverInterruptedContextPackExportsRequest,
    GetProjectContextRequest,
    PlaceContextItemRequest,
    PreflightContextPromotionRequest,
    PreflightProjectContextUpgradeRequest,
    PreviewContextRevisionCleanupRequest,
    PromoteWorkspaceItemToContextRequest,
    SetContextRevisionProtectionRequest,
    UpdateContextSectionRequest,
    UpgradeProjectContextRequest,
    UpsertContextAnnotationRequest,
)
from pig.domain.enums import ContextPackExportStatus, ContextPackFormat, ContextRevisionCaptureStatus
CONTEXT_ID_ROLE = int(Qt.ItemDataRole.UserRole)
CONTEXT_KIND_ROLE = CONTEXT_ID_ROLE + 1


def _format_bytes(value: int) -> str:
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{value} B"


class ContextSectionModel(QAbstractListModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._rows: tuple[tuple[str, object | None], ...] = ()

    def set_sections(self, sections) -> None:
        self.beginResetModel()
        self._rows = (
            ("ALL", None),
            ("UNSECTIONED", None),
            *(("SECTION", value) for value in sections),
        )
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        kind, section = self._rows[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            if kind == "ALL":
                return "全部核心文件"
            if kind == "UNSECTIONED":
                return "未分组"
            return section.name
        if role == CONTEXT_KIND_ROLE:
            return kind
        if role == CONTEXT_ID_ROLE:
            return None if section is None else section.id
        if role == Qt.ItemDataRole.ToolTipRole and section is not None:
            return section.description or section.name
        return None

    def entry(self, row: int):
        return self._rows[row] if 0 <= row < len(self._rows) else (None, None)


class ContextItemModel(QAbstractTableModel):
    HEADERS = ("核心文件", "用途", "新鲜度", "Revision")

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._rows = ()

    def set_items(self, values) -> None:
        self.beginResetModel()
        self._rows = tuple(values)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if (
            role == Qt.ItemDataRole.DisplayRole
            and orientation == Qt.Orientation.Horizontal
            and 0 <= section < len(self.HEADERS)
        ):
            return self.HEADERS[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        value = self._rows[index.row()]
        if role == CONTEXT_ID_ROLE:
            return value.item.id
        if role == Qt.ItemDataRole.DisplayRole:
            title = value.item.title_override or value.workspace_item.display_name
            revision = value.current_revision
            values = (
                title,
                value.item.purpose or "",
                value.freshness.value,
                "—" if revision is None else revision.capture_status.value,
            )
            return values[index.column()]
        if role == Qt.ItemDataRole.ToolTipRole:
            return value.workspace_item.display_name
        return None

    def view_at(self, row: int):
        return self._rows[row] if 0 <= row < len(self._rows) else None


class PromotionDialog(QDialog):
    def __init__(self, display_name: str, preflight, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("加入 Project Context")
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        summary = QLabel(
            f"<b>{html.escape(display_name)}</b><br>"
            f"捕获来源：{preflight.source_kind.value}<br>"
            f"预计大小：{_format_bytes(preflight.estimated_size_bytes)}<br>"
            f"Context Store：{_format_bytes(preflight.context_store_bytes)} / "
            f"软提醒 {_format_bytes(preflight.soft_quota_bytes)}<br>"
            f"磁盘可用：{_format_bytes(preflight.available_bytes)}"
        )
        summary.setWordWrap(True)
        layout.addWidget(summary)
        if preflight.quota_warning:
            warning = QLabel("本次捕获将超过 Context Store 软提醒阈值，但不会自动清理。")
            warning.setObjectName("recoveryBanner")
            warning.setWordWrap(True)
            layout.addWidget(warning)
        form = QFormLayout()
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("可选；留空时使用 Workspace 文件名")
        self.purpose_edit = QTextEdit()
        self.purpose_edit.setPlaceholderText("可选；说明为什么它是项目核心文件")
        self.purpose_edit.setMaximumHeight(100)
        form.addRow("Context 标题", self.title_edit)
        form.addRow("用途说明", self.purpose_edit)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("确认捕获")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(
            preflight.capture_allowed
        )
        layout.addWidget(buttons)
        if not preflight.capture_allowed:
            blocked = QLabel(f"捕获已被安全策略阻止：{preflight.blocking_code}")
            blocked.setObjectName("recoveryBanner")
            layout.insertWidget(1, blocked)

    @property
    def title_override(self) -> str | None:
        return self.title_edit.text().strip() or None

    @property
    def purpose(self) -> str | None:
        return self.purpose_edit.toPlainText().strip() or None


class ContextPackDialog(QDialog):
    """Select a portable pack format, items, fixed revisions, and destination."""

    def __init__(self, project_name: str, rows, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("导出 Context Pack")
        self.setMinimumWidth(680)
        layout = QVBoxLayout(self)
        explanation = QLabel("选择核心文件和固定版本。目录包与 ZIP 使用相同的内容清单；目标必须尚不存在。")
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        self.items = QTableWidget(len(rows), 2)
        self.items.setHorizontalHeaderLabels(["包含文件", "固定 Revision"])
        self.items.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.items.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for index, (view, revisions) in enumerate(rows):
            label = QTableWidgetItem(view.item.title_override or view.workspace_item.display_name)
            label.setFlags(label.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            label.setCheckState(Qt.CheckState.Checked)
            label.setData(CONTEXT_ID_ROLE, view.item.id)
            self.items.setItem(index, 0, label)
            choices = QComboBox()
            for revision in revisions:
                if revision.capture_status == ContextRevisionCaptureStatus.READY:
                    marker = "当前" if revision.id == view.item.current_context_revision_id else "历史"
                    choices.addItem(f"{marker} · {revision.created_at.astimezone():%Y-%m-%d %H:%M} · {revision.id[:8]}", revision.id)
            current = choices.findData(view.item.current_context_revision_id)
            if current >= 0:
                choices.setCurrentIndex(current)
            self.items.setCellWidget(index, 1, choices)
        layout.addWidget(self.items)
        form = QFormLayout()
        self.format_choice = QComboBox()
        self.format_choice.addItem("普通目录", ContextPackFormat.DIRECTORY)
        self.format_choice.addItem("ZIP", ContextPackFormat.ZIP)
        self.destination = QLineEdit()
        self.destination.setPlaceholderText("选择尚不存在的目录或 ZIP 路径")
        browse = QPushButton("浏览…")
        browse.clicked.connect(lambda: self._browse(project_name))
        destination_row = QHBoxLayout()
        destination_row.addWidget(self.destination, 1)
        destination_row.addWidget(browse)
        form.addRow("格式", self.format_choice)
        form.addRow("交付位置", destination_row)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("预检")
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse(self, project_name: str) -> None:
        name = project_name.strip() or "PIG-Context-Pack"
        if self.format_choice.currentData() == ContextPackFormat.ZIP:
            name += ".zip"
        selected, _ = QFileDialog.getSaveFileName(self, "选择 Context Pack 目标", name)
        if selected:
            self.destination.setText(selected)

    def _accept_if_valid(self) -> None:
        if not self.selected_item_ids or not self.destination.text().strip():
            QMessageBox.warning(self, "Context Pack", "至少选择一个文件并指定交付位置。")
            return
        self.accept()

    @property
    def selected_item_ids(self) -> tuple[str, ...]:
        return tuple(self.items.item(row, 0).data(CONTEXT_ID_ROLE)
                     for row in range(self.items.rowCount())
                     if self.items.item(row, 0).checkState() == Qt.CheckState.Checked)

    @property
    def revision_choices(self) -> tuple[ContextPackRevisionChoice, ...]:
        selected = set(self.selected_item_ids)
        return tuple(ContextPackRevisionChoice(
            context_item_id=self.items.item(row, 0).data(CONTEXT_ID_ROLE),
            context_revision_id=self.items.cellWidget(row, 1).currentData(),
        ) for row in range(self.items.rowCount())
            if self.items.item(row, 0).data(CONTEXT_ID_ROLE) in selected)


class ProjectContextView(QWidget):
    """Minimum V2.1.4 UI over typed Context Application contracts only."""

    def __init__(
        self,
        application,
        *,
        actor: str,
        run_background: Callable,
        show_failure: Callable,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._application = application
        self._actor = actor
        self._run = run_background
        self._show_failure = show_failure
        self._project_id: str | None = None
        self._database_path: Path | None = None
        self._workspace_revision = 0
        self._context_revision = 0
        self._result = None
        self._details = None
        self._busy = False
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 14, 18, 14)
        outer.setSpacing(10)
        header = QFrame()
        header.setObjectName("projectHeader")
        header_layout = QHBoxLayout(header)
        titles = QVBoxLayout()
        eyebrow = QLabel("PIG  ·  PROJECT CONTEXT")
        eyebrow.setObjectName("productEyebrow")
        title = QLabel("核心文件与确定版本")
        title.setObjectName("projectTitle")
        hint = QLabel("从 Workspace 选择真正重要的文件，并记录用途、分组与版本。")
        hint.setObjectName("projectMeta")
        titles.addWidget(eyebrow)
        titles.addWidget(title)
        titles.addWidget(hint)
        header_layout.addLayout(titles, 1)
        self.refresh_button = QPushButton("刷新 Context")
        self.export_pack_button = QPushButton("导出 Context Pack")
        self.export_pack_button.setProperty("variant", "primary")
        self.pack_history_button = QPushButton("交付历史")
        self.cleanup_button = QPushButton("清理旧 Revision")
        self.restore_item_button = QPushButton("恢复 Item")
        header_layout.addWidget(self.restore_item_button)
        header_layout.addWidget(self.pack_history_button)
        header_layout.addWidget(self.export_pack_button)
        header_layout.addWidget(self.cleanup_button)
        header_layout.addWidget(self.refresh_button)
        outer.addWidget(header)

        self.stack = QStackedWidget()
        self.setup_page = QWidget()
        setup_layout = QVBoxLayout(self.setup_page)
        setup_layout.addStretch(1)
        self.setup_title = QLabel("打开项目后可使用 Project Context")
        self.setup_title.setObjectName("detailTitle")
        self.setup_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setup_message = QLabel()
        self.setup_message.setWordWrap(True)
        self.setup_message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.upgrade_button = QPushButton("启用 Project Context")
        self.upgrade_button.setProperty("variant", "primary")
        setup_layout.addWidget(self.setup_title)
        setup_layout.addWidget(self.setup_message)
        setup_layout.addWidget(
            self.upgrade_button, 0, Qt.AlignmentFlag.AlignHCenter
        )
        setup_layout.addStretch(1)
        self.stack.addWidget(self.setup_page)

        self.context_page = QWidget()
        context_layout = QVBoxLayout(self.context_page)
        context_layout.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        section_pane = QWidget()
        section_layout = QVBoxLayout(section_pane)
        section_title = QLabel("Sections")
        section_title.setObjectName("detailTitle")
        self.section_view = QListView()
        self.section_model = ContextSectionModel(self)
        self.section_view.setModel(self.section_model)
        section_buttons = QHBoxLayout()
        self.add_section_button = QPushButton("新建")
        self.rename_section_button = QPushButton("编辑")
        self.remove_section_button = QPushButton("移除")
        self.restore_section_button = QPushButton("恢复")
        for button in (
            self.add_section_button,
            self.rename_section_button,
            self.remove_section_button,
            self.restore_section_button,
        ):
            section_buttons.addWidget(button)
        section_layout.addWidget(section_title)
        section_layout.addWidget(self.section_view, 1)
        section_layout.addLayout(section_buttons)

        item_pane = QWidget()
        item_layout = QVBoxLayout(item_pane)
        item_title = QLabel("Context Items")
        item_title.setObjectName("detailTitle")
        self.item_view = QTableView()
        self.item_model = ContextItemModel(self)
        self.item_view.setModel(self.item_model)
        self.item_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.item_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.item_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.item_view.verticalHeader().setVisible(False)
        self.item_view.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.item_view.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        item_layout.addWidget(item_title)
        item_layout.addWidget(self.item_view, 1)

        detail_pane = QWidget()
        detail_layout = QVBoxLayout(detail_pane)
        self.detail_title = QLabel("未选择 Context Item")
        self.detail_title.setObjectName("detailTitle")
        self.detail_summary = QLabel("从中间列表选择核心文件。")
        self.detail_summary.setWordWrap(True)
        self.detail_summary.setTextFormat(Qt.TextFormat.RichText)
        self.guidance_edit = QTextEdit()
        self.guidance_edit.setPlaceholderText("人工阅读说明（显式保存）")
        self.guidance_edit.setMaximumHeight(105)
        detail_actions = QHBoxLayout()
        self.save_guidance_button = QPushButton("保存说明")
        self.advance_button = QPushButton("创建新 Revision")
        self.remove_item_button = QPushButton("移除 Item")
        detail_actions.addWidget(self.save_guidance_button)
        detail_actions.addWidget(self.advance_button)
        detail_actions.addWidget(self.remove_item_button)
        self.placement_list = QListWidget()
        self.placement_list.setMaximumHeight(95)
        placement_actions = QHBoxLayout()
        self.add_placement_button = QPushButton("加入 Section")
        self.remove_placement_button = QPushButton("移除 Placement")
        self.reorder_placement_button = QPushButton("设置顺序")
        placement_actions.addWidget(self.add_placement_button)
        placement_actions.addWidget(self.remove_placement_button)
        placement_actions.addWidget(self.reorder_placement_button)
        self.revision_table = QTableWidget(0, 4)
        self.revision_table.setHorizontalHeaderLabels(
            ["状态", "捕获时间", "SHA-256", "保护"]
        )
        self.revision_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.revision_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.revision_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.revision_table.verticalHeader().setVisible(False)
        self.revision_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        self.revision_table.itemSelectionChanged.connect(self._update_action_state)
        self.placement_list.itemSelectionChanged.connect(self._update_action_state)
        self.protect_button = QPushButton("保护 / 取消保护")
        detail_layout.addWidget(self.detail_title)
        detail_layout.addWidget(self.detail_summary)
        detail_layout.addWidget(QLabel("人工说明"))
        detail_layout.addWidget(self.guidance_edit)
        detail_layout.addLayout(detail_actions)
        detail_layout.addWidget(QLabel("Placements"))
        detail_layout.addWidget(self.placement_list)
        detail_layout.addLayout(placement_actions)
        detail_layout.addWidget(QLabel("Revisions"))
        detail_layout.addWidget(self.revision_table, 1)
        detail_layout.addWidget(self.protect_button)

        splitter.addWidget(section_pane)
        splitter.addWidget(item_pane)
        splitter.addWidget(detail_pane)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 4)
        splitter.setStretchFactor(2, 4)
        splitter.setSizes([240, 500, 500])
        context_layout.addWidget(splitter)
        self.stack.addWidget(self.context_page)
        outer.addWidget(self.stack, 1)

        self.refresh_button.clicked.connect(self.reload)
        self.export_pack_button.clicked.connect(self._export_pack)
        self.pack_history_button.clicked.connect(self._pack_history)
        self.upgrade_button.clicked.connect(self._upgrade)
        self.section_view.selectionModel().selectionChanged.connect(
            lambda *_: self._filter_items()
        )
        self.item_view.selectionModel().selectionChanged.connect(
            lambda *_: self._item_selected()
        )
        self.add_section_button.clicked.connect(self._create_section)
        self.rename_section_button.clicked.connect(self._edit_section)
        self.remove_section_button.clicked.connect(self._remove_section)
        self.restore_section_button.clicked.connect(self._restore_section)
        self.restore_item_button.clicked.connect(self._restore_item)
        self.save_guidance_button.clicked.connect(self._save_guidance)
        self.advance_button.clicked.connect(self._advance_revision)
        self.remove_item_button.clicked.connect(self._remove_item)
        self.add_placement_button.clicked.connect(self._add_placement)
        self.remove_placement_button.clicked.connect(self._remove_placement)
        self.reorder_placement_button.clicked.connect(self._reorder_placement)
        self.protect_button.clicked.connect(self._toggle_protection)
        self.cleanup_button.clicked.connect(self._preview_cleanup)
        self._show_no_project()

    def set_project(
        self, project_id: str | None, database_path: Path | None,
        workspace_revision: int = 0,
    ) -> None:
        self._project_id = project_id
        self._database_path = None if database_path is None else Path(database_path)
        self._workspace_revision = workspace_revision
        self._context_revision = 0
        self._result = None
        self._details = None
        self.section_model.set_sections(())
        self.item_model.set_items(())
        self._clear_details()
        if project_id is None:
            self._show_no_project()

    def update_workspace_revision(self, revision: int) -> None:
        self._workspace_revision = revision

    def activate(self) -> None:
        if not self._has_project():
            self._show_no_project()
            return
        try:
            preflight = self._application.preflight_project_context_upgrade(
                PreflightProjectContextUpgradeRequest(database_path=self._database_path)
            )
        except BaseException as exc:
            self._show_failure("检查 Project Context", exc)
            return
        if preflight.requires_upgrade:
            self.stack.setCurrentWidget(self.setup_page)
            self.setup_title.setText("此项目需要启用 Project Context")
            self.setup_message.setText(
                f"数据库将从 {preflight.current_schema_revision} 升级到 "
                f"{preflight.target_schema_revision}。\n"
                "PIG 会先建立并验证 project.sqlite 备份；Original 和 Working 文件不会改变。"
            )
            self.upgrade_button.show()
            return
        self.stack.setCurrentWidget(self.context_page)
        self.reload()

    def reload(self) -> None:
        if not self._has_project() or self._busy:
            return
        self._run(
            "加载 Project Context",
            lambda: self._application.get_project_context(
                GetProjectContextRequest(
                    project_id=self._project_id,
                    database_path=self._database_path,
                )
            ),
            self._apply_context,
        )

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        for widget in (
            self.refresh_button, self.export_pack_button, self.pack_history_button,
            self.cleanup_button, self.restore_item_button,
            self.section_view, self.item_view, self.add_section_button,
            self.rename_section_button, self.remove_section_button,
            self.restore_section_button, self.guidance_edit,
            self.save_guidance_button, self.advance_button,
            self.remove_item_button, self.add_placement_button,
            self.remove_placement_button, self.reorder_placement_button,
            self.revision_table, self.protect_button, self.upgrade_button,
        ):
            widget.setEnabled(not busy)
        if not busy:
            self._update_action_state()

    def promote_workspace_item(self, workspace_item_id: str, display_name: str) -> None:
        if not self._has_project() or self._busy:
            return
        self._run(
            "检查 Context 捕获",
            lambda: self._application.preflight_context_promotion(
                PreflightContextPromotionRequest(
                    project_id=self._project_id,
                    database_path=self._database_path,
                    workspace_item_id=workspace_item_id,
                    expected_workspace_revision=self._workspace_revision,
                )
            ),
            lambda result: self._confirm_promotion(result, display_name),
        )

    def _confirm_promotion(self, preflight, display_name: str) -> None:
        if preflight.already_active:
            QMessageBox.information(self, "Project Context", "该文件已经在 Project Context 中。")
            return
        dialog = PromotionDialog(display_name, preflight, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._run(
            "加入 Project Context",
            lambda control: self._application.promote_workspace_item_to_context(
                PromoteWorkspaceItemToContextRequest(
                    project_id=self._project_id,
                    database_path=self._database_path,
                    workspace_item_id=preflight.workspace_item_id,
                    actor=self._actor,
                    expected_workspace_revision=preflight.workspace_revision,
                    expected_context_revision=preflight.context_revision,
                    title_override=dialog.title_override,
                    purpose=dialog.purpose,
                ),
                control=control,
            ),
            self._promotion_completed,
            progress=True,
        )

    def _promotion_completed(self, result) -> None:
        QMessageBox.information(self, "Project Context", "文件已加入 Project Context。")
        self.reload()

    def _apply_context(self, result) -> None:
        selected_item_id = self._selected_item_id()
        self._result = result
        self._context_revision = result.project.context_revision
        self._workspace_revision = result.project.workspace_revision
        self.stack.setCurrentWidget(self.context_page)
        self.section_model.set_sections(result.sections)
        self.section_view.setCurrentIndex(self.section_model.index(0, 0))
        self._filter_items(preferred_item_id=selected_item_id)
        self._update_action_state()

    def _filter_items(self, *, preferred_item_id: str | None = None) -> None:
        if self._result is None:
            self.item_model.set_items(())
            self._clear_details()
            return
        index = self.section_view.currentIndex()
        kind, section = self.section_model.entry(index.row())
        if kind == "SECTION":
            values = tuple(
                value for value in self._result.items
                if any(
                    placement.context_section_id == section.id
                    for placement in value.effective_placements
                )
            )
        elif kind == "UNSECTIONED":
            unsectioned = set(self._result.unsectioned_item_ids)
            values = tuple(
                value for value in self._result.items if value.item.id in unsectioned
            )
        else:
            values = tuple(self._result.items)
        self.item_model.set_items(values)
        target_row = next(
            (row for row, value in enumerate(values) if value.item.id == preferred_item_id),
            -1,
        )
        if target_row >= 0:
            self.item_view.selectRow(target_row)
        else:
            self.item_view.clearSelection()
            self._clear_details()
        self._update_action_state()

    def _item_selected(self) -> None:
        item_id = self._selected_item_id()
        if item_id is None or not self._has_project():
            self._clear_details()
            return
        try:
            details = self._application.get_context_item_details(
                GetContextItemDetailsRequest(
                    project_id=self._project_id,
                    database_path=self._database_path,
                    context_item_id=item_id,
                )
            )
        except BaseException as exc:
            self._show_failure("加载 Context Item", exc)
            return
        self._details = details
        view = details.view
        revision = view.current_revision
        title = view.item.title_override or view.workspace_item.display_name
        self.detail_title.setText(title)
        self.detail_summary.setText(
            "<table>"
            f"<tr><td>Workspace 文件</td><td>{html.escape(view.workspace_item.display_name)}</td></tr>"
            f"<tr><td>Freshness</td><td><b>{view.freshness.value}</b></td></tr>"
            f"<tr><td>Current Revision</td><td>{'—' if revision is None else html.escape(revision.id)}</td></tr>"
            f"<tr><td>SHA-256</td><td>{'—' if revision is None else html.escape(revision.source_observed_sha256 or '—')}</td></tr>"
            "</table>"
        )
        annotation = details.annotations[0] if details.annotations else None
        self.guidance_edit.setPlainText("" if annotation is None else annotation.body)
        sections = {value.id: value for value in self._result.sections}
        self.placement_list.clear()
        for placement in view.effective_placements:
            section = sections.get(placement.context_section_id)
            if section is None:
                continue
            self.placement_list.addItem(f"{section.name}  ·  顺序 {placement.ordinal}")
            row = self.placement_list.count() - 1
            self.placement_list.item(row).setData(CONTEXT_ID_ROLE, section.id)
            self.placement_list.item(row).setData(CONTEXT_KIND_ROLE, placement.id)
        self.revision_table.setRowCount(0)
        for value in details.revisions:
            row = self.revision_table.rowCount()
            self.revision_table.insertRow(row)
            cells = (
                value.capture_status.value,
                value.created_at.astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                value.source_observed_sha256 or "",
                "已保护" if value.is_manually_protected else "",
            )
            for column, text in enumerate(cells):
                cell = QTableWidgetItem(text)
                if column == 0:
                    cell.setData(CONTEXT_ID_ROLE, value.id)
                self.revision_table.setItem(row, column, cell)
        self._update_action_state()

    def _clear_details(self) -> None:
        self._details = None
        if hasattr(self, "detail_title"):
            self.detail_title.setText("未选择 Context Item")
            self.detail_summary.setText("从中间列表选择核心文件。")
            self.guidance_edit.clear()
            self.placement_list.clear()
            self.revision_table.setRowCount(0)
            self._update_action_state()

    def _create_section(self) -> None:
        name, accepted = QInputDialog.getText(self, "新建 Section", "Section 名称")
        if not accepted or not name.strip():
            return
        self._write(
            "创建 Section",
            lambda: self._application.create_context_section(
                CreateContextSectionRequest(
                    project_id=self._project_id, database_path=self._database_path,
                    name=name, actor=self._actor,
                    expected_context_revision=self._context_revision,
                )
            ),
        )

    def _edit_section(self) -> None:
        section = self._selected_section()
        if section is None:
            return
        name, accepted = QInputDialog.getText(
            self, "编辑 Section", "Section 名称", text=section.name
        )
        if not accepted or not name.strip():
            return
        ordinal, accepted = QInputDialog.getInt(
            self, "Section 顺序", "非负顺序值", section.ordinal, 0
        )
        if not accepted:
            return
        self._write(
            "更新 Section",
            lambda: self._application.update_context_section(
                UpdateContextSectionRequest(
                    project_id=self._project_id, database_path=self._database_path,
                    context_section_id=section.id, actor=self._actor,
                    expected_context_revision=self._context_revision,
                    name=name, ordinal=ordinal,
                )
            ),
        )

    def _remove_section(self) -> None:
        section = self._selected_section()
        if section is None:
            return
        if QMessageBox.question(
            self, "移除 Section",
            "Section 将被软删除；Item、Revision 和 Placement 事实会保留。是否继续？",
        ) != QMessageBox.StandardButton.Yes:
            return
        self._write(
            "移除 Section",
            lambda: self._application.remove_context_section(
                ContextSectionLifecycleRequest(
                    project_id=self._project_id, database_path=self._database_path,
                    context_section_id=section.id, actor=self._actor,
                    expected_context_revision=self._context_revision,
                )
            ),
        )

    def _restore_section(self) -> None:
        values = () if self._result is None else self._result.removed_sections
        by_name = {f"{value.name} · {value.id[:8]}": value for value in values}
        if not by_name:
            QMessageBox.information(self, "恢复 Section", "没有已移除的 Section。")
            return
        label, accepted = QInputDialog.getItem(
            self, "恢复 Section", "选择 Section", tuple(by_name), editable=False
        )
        if not accepted:
            return
        section = by_name[label]
        self._write(
            "恢复 Section",
            lambda: self._application.restore_context_section(
                ContextSectionLifecycleRequest(
                    project_id=self._project_id, database_path=self._database_path,
                    context_section_id=section.id, actor=self._actor,
                    expected_context_revision=self._context_revision,
                )
            ),
        )

    def _restore_item(self) -> None:
        values = () if self._result is None else self._result.removed_items
        by_name = {
            f"{value.item.title_override or value.workspace_item.display_name} · {value.item.id[:8]}": value
            for value in values
        }
        if not by_name:
            QMessageBox.information(self, "恢复 Item", "没有已移除的 Context Item。")
            return
        label, accepted = QInputDialog.getItem(
            self, "恢复 Item", "选择 Item", tuple(by_name), editable=False
        )
        if not accepted:
            return
        item = by_name[label].item
        self._write(
            "恢复 Context Item",
            lambda: self._application.restore_context_item(
                ContextItemLifecycleRequest(
                    project_id=self._project_id, database_path=self._database_path,
                    context_item_id=item.id, actor=self._actor,
                    expected_context_revision=self._context_revision,
                )
            ),
        )

    def _remove_item(self) -> None:
        item_id = self._selected_item_id()
        if item_id is None:
            return
        if QMessageBox.question(
            self, "移除 Context Item",
            "Item 将从 Context 软移除；Workspace、Original 和 Revision 不会删除。是否继续？",
        ) != QMessageBox.StandardButton.Yes:
            return
        self._write(
            "移除 Context Item",
            lambda: self._application.remove_context_item(
                ContextItemLifecycleRequest(
                    project_id=self._project_id, database_path=self._database_path,
                    context_item_id=item_id, actor=self._actor,
                    expected_context_revision=self._context_revision,
                )
            ),
        )

    def _save_guidance(self) -> None:
        item_id = self._selected_item_id()
        body = self.guidance_edit.toPlainText().strip()
        if item_id is None or not body:
            QMessageBox.information(self, "保存说明", "说明不能为空。")
            return
        self._write(
            "保存 Context 说明",
            lambda: self._application.upsert_context_annotation(
                UpsertContextAnnotationRequest(
                    project_id=self._project_id, database_path=self._database_path,
                    context_item_id=item_id, body=body, actor=self._actor,
                    expected_context_revision=self._context_revision,
                )
            ),
        )

    def _advance_revision(self) -> None:
        item_id = self._selected_item_id()
        if item_id is None:
            return
        self._run(
            "创建 Context Revision",
            lambda control: self._application.advance_context_revision(
                AdvanceContextRevisionRequest(
                    project_id=self._project_id, database_path=self._database_path,
                    context_item_id=item_id, actor=self._actor,
                    expected_workspace_revision=self._workspace_revision,
                    expected_context_revision=self._context_revision,
                ), control=control,
            ),
            lambda _result: self.reload(),
            progress=True,
        )

    def _add_placement(self) -> None:
        item_id = self._selected_item_id()
        if item_id is None or self._result is None:
            return
        existing = {
            value.context_section_id for value in self._details.view.effective_placements
        } if self._details is not None else set()
        choices = {
            f"{value.name} · {value.id[:8]}": value for value in self._result.sections
            if value.id not in existing
        }
        if not choices:
            QMessageBox.information(self, "Placement", "没有可加入的其他 Section。")
            return
        label, accepted = QInputDialog.getItem(
            self, "加入 Section", "Section", tuple(choices), editable=False
        )
        if not accepted:
            return
        section = choices[label]
        self._write(
            "创建 Placement",
            lambda: self._application.place_context_item(
                PlaceContextItemRequest(
                    project_id=self._project_id, database_path=self._database_path,
                    context_item_id=item_id, context_section_id=section.id,
                    actor=self._actor,
                    expected_context_revision=self._context_revision,
                )
            ),
        )

    def _selected_placement(self):
        row = self.placement_list.currentRow()
        if row < 0 or self._details is None:
            return None
        placement_id = self.placement_list.item(row).data(CONTEXT_KIND_ROLE)
        return next(
            (value for value in self._details.view.effective_placements
             if value.id == placement_id), None
        )

    def _remove_placement(self) -> None:
        placement = self._selected_placement()
        if placement is None:
            return
        self._write(
            "移除 Placement",
            lambda: self._application.remove_context_placement(
                PlaceContextItemRequest(
                    project_id=self._project_id, database_path=self._database_path,
                    context_item_id=placement.context_item_id,
                    context_section_id=placement.context_section_id,
                    actor=self._actor,
                    expected_context_revision=self._context_revision,
                )
            ),
        )

    def _reorder_placement(self) -> None:
        placement = self._selected_placement()
        if placement is None:
            return
        ordinal, accepted = QInputDialog.getInt(
            self, "Placement 顺序", "非负顺序值", placement.ordinal, 0
        )
        if not accepted:
            return
        self._write(
            "调整 Placement",
            lambda: self._application.reorder_context_placement(
                PlaceContextItemRequest(
                    project_id=self._project_id, database_path=self._database_path,
                    context_item_id=placement.context_item_id,
                    context_section_id=placement.context_section_id,
                    actor=self._actor, ordinal=ordinal,
                    expected_context_revision=self._context_revision,
                )
            ),
        )

    def _toggle_protection(self) -> None:
        rows = self.revision_table.selectionModel().selectedRows()
        if len(rows) != 1 or self._details is None:
            return
        revision_id = self.revision_table.item(rows[0].row(), 0).data(CONTEXT_ID_ROLE)
        revision = next(value for value in self._details.revisions if value.id == revision_id)
        protected = not revision.is_manually_protected
        reason = None
        if protected:
            reason, accepted = QInputDialog.getText(
                self, "保护 Revision", "保护原因"
            )
            if not accepted or not reason.strip():
                return
        elif QMessageBox.question(
            self, "取消保护", "取消该 Revision 的人工保护？"
        ) != QMessageBox.StandardButton.Yes:
            return
        self._write(
            "更新 Revision 保护",
            lambda: self._application.set_context_revision_protection(
                SetContextRevisionProtectionRequest(
                    project_id=self._project_id, database_path=self._database_path,
                    context_revision_id=revision.id, protected=protected,
                    reason=reason, actor=self._actor,
                    expected_context_revision=self._context_revision,
                )
            ),
        )

    def _preview_cleanup(self) -> None:
        if not self._has_project():
            return
        self._run(
            "预览 Context 清理",
            lambda: self._application.preview_context_revision_cleanup(
                PreviewContextRevisionCleanupRequest(
                    project_id=self._project_id, database_path=self._database_path,
                    actor=self._actor,
                )
            ),
            self._confirm_cleanup,
        )

    def _confirm_cleanup(self, preview) -> None:
        if not preview.candidates:
            QMessageBox.information(self, "清理旧 Revision", "当前没有可安全清理的 Revision。")
            return
        answer = QMessageBox.question(
            self, "确认清理旧 Revision",
            f"候选 Revision：{len(preview.candidates)}\n"
            f"预计可回收：{_format_bytes(preview.reclaimable_bytes)}\n\n"
            "当前、上一版本、人工保护及被引用 Revision 不会删除。是否继续？",
        )
        if answer != QMessageBox.StandardButton.Yes:
            self._run(
                "取消 Context Pack 预检",
                lambda: self._application.cancel_context_pack_preflight(
                    CancelContextPackPreflightRequest(
                        project_id=self._project_id, database_path=self._database_path,
                        export_id=preflight.export_id, plan_token=preflight.plan_token,
                        actor=self._actor,
                    )
                ),
                lambda _result: None,
            )
            return
        self._run(
            "清理旧 Revision",
            lambda: self._application.execute_context_revision_cleanup(
                ExecuteContextRevisionCleanupRequest(
                    project_id=self._project_id, database_path=self._database_path,
                    actor=self._actor,
                    expected_context_revision=preview.context_revision,
                    preview_token=preview.preview_token, confirmed=True,
                )
            ),
            self._cleanup_completed,
        )

    def _cleanup_completed(self, result) -> None:
        message = (
            f"已清理 {len(result.deleted_revision_ids)} 个 Revision，"
            f"回收 {_format_bytes(result.reclaimed_bytes)}。"
        )
        if result.orphaned_object_keys:
            message += f"\n有 {len(result.orphaned_object_keys)} 个对象等待恢复扫描。"
        QMessageBox.information(self, "Context 清理完成", message)
        self.reload()

    def _export_pack(self) -> None:
        if not self._has_project() or self._result is None or self._busy:
            return
        views = tuple(self._result.items)
        if not views:
            QMessageBox.information(self, "Context Pack", "请先添加核心文件。")
            return
        self._run(
            "读取 Context Revisions",
            lambda: tuple((view, self._application.get_context_item_details(
                GetContextItemDetailsRequest(
                    project_id=self._project_id, database_path=self._database_path,
                    context_item_id=view.item.id,
                )).revisions) for view in views),
            self._show_pack_dialog,
        )

    def _show_pack_dialog(self, rows) -> None:
        dialog = ContextPackDialog(self._result.project.name, rows, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        selected_ids = dialog.selected_item_ids
        revision_choices = dialog.revision_choices
        self._run(
            "预检 Context Pack",
            lambda control: self._application.preflight_context_pack_export(
                PreflightContextPackExportRequest(
                    project_id=self._project_id, database_path=self._database_path,
                    destination_path=Path(dialog.destination.text().strip()),
                    format=ContextPackFormat(dialog.format_choice.currentData()), actor=self._actor,
                    selected_item_ids=selected_ids, revision_choices=revision_choices,
                ), control=control,
            ),
            lambda result: self._confirm_pack_export(result, selected_ids, revision_choices),
            progress=True,
        )

    def _confirm_pack_export(self, preflight, selected_ids, revision_choices) -> None:
        warning = (
            f"\n注意：{len(preflight.plan.warning_item_ids)} 个固定 Revision 对应的 Workspace 已变化。"
            if preflight.plan.warning_item_ids else ""
        )
        answer = QMessageBox.question(
            self, "确认导出 Context Pack",
            f"格式：{preflight.format.value}\n"
            f"文件：{len(preflight.plan.entries)} 个 · {_format_bytes(preflight.plan.total_bytes)}\n"
            f"位置：{preflight.destination_path}{warning}\n\n"
            "将仅使用已锁定的 Context 字节，不回退到 Workspace 或 Original。是否继续？",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._run(
            "导出 Context Pack",
            lambda control: self._application.execute_context_pack_export(
                ExecuteContextPackExportRequest(
                    project_id=self._project_id, database_path=self._database_path,
                    export_id=preflight.export_id, plan_token=preflight.plan_token,
                    actor=self._actor, selected_item_ids=selected_ids,
                    revision_choices=revision_choices, confirm_outdated=bool(warning),
                ), control=control,
            ),
            lambda result: QMessageBox.information(
                self, "Context Pack 已导出", f"交付位置：{result.destination_path}"
            ),
            progress=True,
        )

    def _pack_history(self) -> None:
        if not self._has_project() or self._busy:
            return
        self._run(
            "读取交付历史",
            lambda: self._application.get_context_pack_exports(GetContextPackExportsRequest(
                project_id=self._project_id, database_path=self._database_path,
            )),
            self._show_pack_history,
        )

    def _show_pack_history(self, result) -> None:
        if not result.exports:
            QMessageBox.information(self, "Context Pack 历史", "尚无交付记录。")
            return
        lines = [f"{value.created_at.astimezone():%Y-%m-%d %H:%M} · {value.status.value} · {value.format.value}\n{value.destination_locator}"
                 for value in reversed(result.exports[-10:])]
        QMessageBox.information(self, "最近 10 次 Context Pack 交付", "\n\n".join(lines))
        if any(value.status == ContextPackExportStatus.RUNNING for value in result.exports):
            if QMessageBox.question(
                self, "处理未完成的交付",
                "存在 RUNNING 记录。如果上次运行已中断，可标记为失败以便重新预检；"
                "外部目标若已出现不会自动删除，需人工检查。确认当前没有导出任务在运行后继续？",
            ) == QMessageBox.StandardButton.Yes:
                self._run(
                    "处理未完成交付",
                    lambda: self._application.recover_interrupted_context_pack_exports(
                        RecoverInterruptedContextPackExportsRequest(
                            project_id=self._project_id, database_path=self._database_path,
                            actor=self._actor, confirmed=True,
                        )
                    ),
                    lambda recovery: QMessageBox.information(
                        self, "处理完成",
                        f"已标记 {len(recovery.recovered_export_ids)} 项。"
                        f"外部目标待人工检查：{len(recovery.external_paths_to_review)} 项。",
                    ),
                )

    def _upgrade(self) -> None:
        try:
            preflight = self._application.preflight_project_context_upgrade(
                PreflightProjectContextUpgradeRequest(database_path=self._database_path)
            )
        except BaseException as exc:
            self._show_failure("检查 Project Context 升级", exc)
            return
        if QMessageBox.question(
            self, "启用 Project Context",
            f"将升级数据库到 {preflight.target_schema_revision}。\n"
            "PIG 会先建立并验证备份；Original 和 Working 文件不会改变。是否继续？",
        ) != QMessageBox.StandardButton.Yes:
            return
        self._run(
            "启用 Project Context",
            lambda: self._application.upgrade_project_context(
                UpgradeProjectContextRequest(
                    database_path=self._database_path,
                    actor=self._actor,
                    confirmed=True,
                )
            ),
            self._upgrade_completed,
        )

    def _upgrade_completed(self, result) -> None:
        QMessageBox.information(
            self, "Project Context 已启用",
            "数据库升级和备份校验已完成。"
            + ("" if result.backup_path is None else f"\n备份：{result.backup_path}"),
        )
        self.stack.setCurrentWidget(self.context_page)
        self.reload()

    def _write(self, operation: str, action: Callable[[], object]) -> None:
        self._run(operation, action, lambda _result: self.reload())

    def _selected_section(self):
        index = self.section_view.currentIndex()
        kind, section = self.section_model.entry(index.row())
        return section if kind == "SECTION" else None

    def _selected_item_id(self) -> str | None:
        rows = self.item_view.selectionModel().selectedRows()
        if len(rows) != 1:
            return None
        return rows[0].data(CONTEXT_ID_ROLE)

    def _update_action_state(self) -> None:
        if not hasattr(self, "add_section_button"):
            return
        active = self._has_project() and not self._busy and self._result is not None
        section = self._selected_section()
        item = self._selected_item_id()
        self.refresh_button.setEnabled(self._has_project() and not self._busy)
        self.cleanup_button.setEnabled(active)
        self.export_pack_button.setEnabled(active and bool(self._result.items))
        self.pack_history_button.setEnabled(active)
        self.restore_section_button.setEnabled(
            active and bool(self._result.removed_sections)
        )
        self.restore_item_button.setEnabled(active and bool(self._result.removed_items))
        self.add_section_button.setEnabled(active)
        self.rename_section_button.setEnabled(active and section is not None)
        self.remove_section_button.setEnabled(active and section is not None)
        for button in (
            self.save_guidance_button, self.advance_button, self.remove_item_button,
            self.add_placement_button,
        ):
            button.setEnabled(active and item is not None)
        placement = self._selected_placement()
        self.remove_placement_button.setEnabled(active and placement is not None)
        self.reorder_placement_button.setEnabled(active and placement is not None)
        self.protect_button.setEnabled(
            active and len(self.revision_table.selectionModel().selectedRows()) == 1
        )

    def _show_no_project(self) -> None:
        if not hasattr(self, "stack"):
            return
        self.stack.setCurrentWidget(self.setup_page)
        self.setup_title.setText("尚未打开项目")
        self.setup_message.setText("请先新建或打开一个 PIG Project。")
        self.upgrade_button.hide()

    def _has_project(self) -> bool:
        return self._project_id is not None and self._database_path is not None
