from __future__ import annotations

import html
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QAbstractListModel, QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QToolButton,
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
from pig.application.content_contracts import (
    ExtractContextRevisionsRequest, SearchContextContentRequest,
    RebuildContextIndexRequest, OpenContextRevisionRequest,
    RecoverInterruptedContentRequest,
)
from pig.application.experience_service import (
    ExperienceEvidenceChoice, ExperienceMutationRequest, ExperienceTransitionRequest,
)
from pig.domain.experience_policy import ExperienceKind, ExperienceStatus
from pig.application.ai_analysis_service import AnalysisPlanRequest
from pig.application.ai_prompts import instruction_for
from pig.domain.ai_policy import AnalysisAction
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
    HEADERS = ("核心文件", "用途", "状态")

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
            freshness = {
                "CURRENT": "已固定版本",
                "WORKSPACE_UPDATED": "有更新待确认",
                "WORKSPACE_MISSING": "工作文件缺失",
                "WORKSPACE_UNREADABLE": "工作文件无法读取",
            }.get(value.freshness.value, value.freshness.value)
            values = (
                title,
                value.item.purpose or "",
                freshness,
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

    def __init__(self, project_name: str, rows, records=(), parent=None) -> None:
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
        self.records = QListWidget()
        for summary in records:
            record = summary.record
            entry = QListWidgetItem(
                f"{summary.title} · {record.kind.value} · {record.status.value}"
            )
            entry.setFlags(entry.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            entry.setCheckState(Qt.CheckState.Unchecked)
            entry.setData(CONTEXT_ID_ROLE, record.id)
            self.records.addItem(entry)
        if records:
            layout.addWidget(QLabel("附带人工记录（仅当所选版本包含全部依据时可导出）"))
            self.records.setMaximumHeight(110)
            layout.addWidget(self.records)
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

    @property
    def selected_record_ids(self) -> tuple[str, ...]:
        return tuple(self.records.item(row).data(CONTEXT_ID_ROLE)
                     for row in range(self.records.count())
                     if self.records.item(row).checkState() == Qt.CheckState.Checked)


class ExperienceDialog(QDialog):
    """Only captures human-authored text and explicit fixed-Revision choices."""

    def __init__(self, revision_choices, *, initial=None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("记录项目脉络" if initial is None else "更正人工记录")
        self.setMinimumWidth(570)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.kind = QComboBox()
        for kind, label in ((ExperienceKind.JUDGMENT, "判断"),
                            (ExperienceKind.DECISION, "决定"),
                            (ExperienceKind.LESSON, "经验")):
            self.kind.addItem(label, kind)
        if initial is not None:
            self.kind.setCurrentIndex(self.kind.findData(initial.record.kind))
            self.kind.setEnabled(False)
        self.body = QTextEdit()
        self.body.setPlainText("" if initial is None else initial.versions[-1].body)
        self.body.setPlaceholderText("写下判断、决定或经验；首行将作为列表摘要")
        form.addRow("类型", self.kind)
        form.addRow("记录内容", self.body)
        layout.addLayout(form)
        layout.addWidget(QLabel("关联固定文件版本"))
        self.evidence = QListWidget()
        linked = set() if initial is None else {
            (link.context_item_id, link.context_revision_id)
            for link in initial.revision_links
        }
        for item_id, revision_id, label, preferred in revision_choices:
            entry = QListWidgetItem(label)
            entry.setFlags(entry.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            entry.setCheckState(Qt.CheckState.Checked if (
                (item_id, revision_id) in linked or (initial is None and preferred)
            ) else Qt.CheckState.Unchecked)
            entry.setData(CONTEXT_ID_ROLE, (item_id, revision_id))
            self.evidence.addItem(entry)
        self.evidence.setMaximumHeight(180)
        layout.addWidget(self.evidence)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept_valid)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept_valid(self) -> None:
        if not self.body.toPlainText().strip() or not self.selected_evidence:
            QMessageBox.warning(self, "项目脉络", "请填写记录内容，并至少关联一个固定版本。")
            return
        self.accept()

    @property
    def derived_title(self) -> str:
        first_line = next(
            (line.strip() for line in self.body.toPlainText().splitlines() if line.strip()),
            "",
        )
        return first_line[:200]

    @property
    def selected_evidence(self) -> tuple[ExperienceEvidenceChoice, ...]:
        return tuple(ExperienceEvidenceChoice(*self.evidence.item(row).data(CONTEXT_ID_ROLE))
                     for row in range(self.evidence.count())
                     if self.evidence.item(row).checkState() == Qt.CheckState.Checked)

class ExperienceHistoryDialog(QDialog):
    def __init__(self, detail, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("人工记录与更正历史")
        self.setMinimumSize(620, 410)
        layout = QVBoxLayout(self)
        self.versions = QComboBox()
        for version in reversed(detail.versions):
            self.versions.addItem(
                f"版本 {version.version} · {version.recorded_at.astimezone():%Y-%m-%d %H:%M} "
                f"· {version.author}", version,
            )
        self.body = QTextEdit()
        self.body.setReadOnly(True)
        self.links = QLabel(
            f"当前版本关联 {len(detail.revision_links)} 个固定 Revision，"
            f"状态：{detail.record.status.value}"
        )
        self.links.setWordWrap(True)
        layout.addWidget(self.versions)
        layout.addWidget(self.body, 1)
        layout.addWidget(self.links)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.versions.currentIndexChanged.connect(self._show_version)
        self._show_version()

    def _show_version(self, _index=None) -> None:
        version = self.versions.currentData()
        if version is not None:
            self.body.setPlainText(version.body)


class AIActionDialog(QDialog):
    def __init__(self, *, profiles, other_revisions, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("AI 辅助分析")
        self.setMinimumWidth(470)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.action = QComboBox()
        self.action.addItem("摘要", AnalysisAction.SUMMARY)
        self.action.addItem("关键事实卡", AnalysisAction.KEY_FACTS)
        if other_revisions:
            self.action.addItem("比较两个固定版本", AnalysisAction.COMPARE)
        self.model = QComboBox()
        for profile in profiles:
            self.model.addItem(f"{profile.provider} · {profile.model}",
                               (profile.provider, profile.model))
        self.other_revision = QComboBox()
        for revision_id, title in other_revisions:
            self.other_revision.addItem(title, revision_id)
        self.other_revision.setEnabled(False)
        self.action.currentIndexChanged.connect(lambda: self.other_revision.setEnabled(
            self.action.currentData() == AnalysisAction.COMPARE))
        form.addRow("任务", self.action)
        form.addRow("Provider / 模型", self.model)
        form.addRow("比较对象", self.other_revision)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("预览输入")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class AIPlanPreviewDialog(QDialog):
    def __init__(self, plan, *, can_execute: bool, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("逐次外发预览")
        self.setMinimumSize(720, 540)
        layout = QVBoxLayout(self)
        title = QLabel(
            f"{plan.request.provider} · {plan.request.model} · {plan.request.action.value} · "
            f"{plan.coverage} · 最多约 ${plan.estimated_max_usd:.4f}（估算）"
        )
        title.setWordWrap(True)
        layout.addWidget(title)
        if not can_execute:
            note = QLabel("当前计划不在已批准的合成外发范围内；只能预览，不会发送。")
            note.setWordWrap(True)
            layout.addWidget(note)
        preview = QTextEdit()
        preview.setReadOnly(True)
        parts = ["[开发者指令 / Developer instruction]", instruction_for(plan.request.action)]
        for element in plan.elements:
            parts.extend((
                f"\n[Element {element.id} | Revision {element.revision_id} | "
                f"{element.locator_kind}: {element.locator_value}]",
                element.text,
            ))
        if plan.omitted_elements:
            parts.append(f"\n[另有 {plan.omitted_elements} 个元素未包含 / omitted]")
        preview.setPlainText("\n".join(parts))
        layout.addWidget(preview, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("确认本次发送")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(can_execute)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("关闭")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class AIResultDialog(QDialog):
    def __init__(self, result, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("AI 草稿 · 待人工核对")
        self.setMinimumSize(660, 470)
        layout = QVBoxLayout(self)
        notices = []
        if result.possibly_stale:
            notices.append("工作区或固定版本可能已变化，请重新核对。")
        if result.coverage == "PARTIAL_INPUT":
            notices.append("仅分析了预览中的部分内容，不代表全文结论。")
        if notices:
            note = QLabel("\n".join(notices))
            note.setWordWrap(True)
            layout.addWidget(note)
        body = QTextEdit()
        body.setReadOnly(True)
        body.setPlainText("\n\n".join(
            f"{index}. {claim.text}"
            + (f"\n对象：{claim.subject}" if claim.subject else "")
            + (f" · 时间：{claim.time}" if claim.time else "")
            for index, claim in enumerate(result.claims, 1)
        ))
        layout.addWidget(body, 1)
        layout.addWidget(QLabel("引用依据（双击打开只读固定版本）"))
        self.citations = QListWidget()
        input_by_id = {value[0]: value for value in result.inputs}
        seen = set()
        for claim in result.claims:
            for element_id in claim.element_ids:
                if element_id in seen:
                    continue
                seen.add(element_id)
                _id, revision_id, kind, locator = input_by_id[element_id]
                entry = QListWidgetItem(
                    f"{revision_id[:8]} · {kind}: {locator} · 元素 {element_id[:8]}"
                )
                entry.setData(CONTEXT_ID_ROLE, revision_id)
                self.citations.addItem(entry)
        self.citations.setMaximumHeight(135)
        layout.addWidget(self.citations)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("打开选中依据")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("关闭")
        buttons.accepted.connect(self._accept_selected)
        buttons.rejected.connect(self.reject)
        self.citations.itemDoubleClicked.connect(lambda *_: self._accept_selected())
        layout.addWidget(buttons)

    def _accept_selected(self) -> None:
        if self.citations.currentItem() is not None:
            self.accept()

    @property
    def selected_revision_id(self) -> str | None:
        item = self.citations.currentItem()
        return None if item is None else item.data(CONTEXT_ID_ROLE)


class ProjectContextView(QWidget):
    workspace_requested = Signal()

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
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.addStretch(1)
        self.add_from_workspace_button = QPushButton("从工作区添加")
        self.add_from_workspace_button.clicked.connect(self.workspace_requested.emit)
        self.export_pack_button = QPushButton("导出交付包")
        self.export_pack_button.setProperty("variant", "primary")
        self.refresh_button = QPushButton("刷新", self)
        self.pack_history_button = QPushButton("交付历史", self)
        self.cleanup_button = QPushButton("清理旧版本", self)
        self.restore_item_button = QPushButton("恢复核心文件", self)
        self.context_more_button = QToolButton()
        self.context_more_button.setText("···")
        self.context_more_button.setToolTip("更多核心文件操作")
        self.context_more_button.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup
        )
        context_more_menu = QMenu(self.context_more_button)
        self.history_action = context_more_menu.addAction("交付历史", self._pack_history)
        self.restore_item_action = context_more_menu.addAction(
            "恢复核心文件", self._restore_item
        )
        self.cleanup_action = context_more_menu.addAction(
            "清理旧版本", self._preview_cleanup
        )
        context_more_menu.addSeparator()
        self.refresh_context_action = context_more_menu.addAction("刷新", self.reload)
        self.rebuild_index_action = context_more_menu.addAction(
            "重建内容索引", self._rebuild_content_index
        )
        self.recover_content_action = context_more_menu.addAction(
            "恢复中断提取", self._recover_content_runs
        )
        self.ai_history_action = context_more_menu.addAction("AI 草稿历史", self._ai_history)
        self.recover_ai_action = context_more_menu.addAction("恢复中断 AI 分析", self._recover_ai_runs)
        context_more_menu.addSeparator()
        self.set_ai_key_action = context_more_menu.addAction("设置模型 API 密钥", self._set_ai_key)
        self.remove_ai_key_action = context_more_menu.addAction("清除模型 API 密钥", self._remove_ai_key)
        self.context_more_button.setMenu(context_more_menu)
        header_layout.addWidget(self.add_from_workspace_button)
        header_layout.addWidget(self.export_pack_button)
        header_layout.addWidget(self.context_more_button)
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
        self.section_pane = section_pane
        section_layout = QVBoxLayout(section_pane)
        section_title = QLabel("分组")
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
        self.section_filter_button = QPushButton("全部核心文件  ▾")
        self.section_filter_button.setProperty("variant", "quiet")
        self.section_filter_button.setCheckable(True)
        self.section_filter_button.toggled.connect(self.section_pane.setVisible)
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
        self.item_view.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        item_layout.addWidget(
            self.section_filter_button, 0, Qt.AlignmentFlag.AlignLeft
        )
        item_layout.addWidget(self.item_view, 1)

        detail_pane = QWidget()
        self.detail_pane = detail_pane
        detail_layout = QVBoxLayout(detail_pane)
        self.detail_title = QLabel("未选择核心文件")
        self.detail_title.setObjectName("detailTitle")
        self.detail_summary = QLabel("")
        self.detail_summary.setWordWrap(True)
        self.detail_summary.setObjectName("detailSubtitle")
        self.detail_summary.setTextFormat(Qt.TextFormat.PlainText)
        self.guidance_preview = QLabel("尚无阅读说明")
        self.guidance_preview.setWordWrap(True)
        self.guidance_preview.setObjectName("guidancePreview")
        self.guidance_preview.setTextFormat(Qt.TextFormat.PlainText)
        self.guidance_edit = QTextEdit()
        self.guidance_edit.setPlaceholderText("写下阅读这份文件时应关注的内容")
        self.guidance_edit.setMaximumHeight(105)
        self.guidance_edit.hide()
        detail_actions = QHBoxLayout()
        self.edit_guidance_button = QPushButton("编辑说明")
        self.edit_guidance_button.clicked.connect(
            lambda: self._set_guidance_editing(True)
        )
        self.save_guidance_button = QPushButton("保存说明")
        self.cancel_guidance_button = QPushButton("取消")
        self.cancel_guidance_button.clicked.connect(
            lambda: self._set_guidance_editing(False)
        )
        self.advance_button = QPushButton("更新固定版本")
        self.remove_item_button = QPushButton("移除 Item")
        self.remove_item_button.hide()
        self.item_more_button = QToolButton()
        self.item_more_button.setText("更多 ···")
        self.item_more_button.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup
        )
        item_more_menu = QMenu(self.item_more_button)
        item_more_menu.addAction("移除核心文件", self._remove_item)
        self.item_more_button.setMenu(item_more_menu)
        detail_actions.addWidget(self.edit_guidance_button)
        detail_actions.addWidget(self.save_guidance_button)
        detail_actions.addWidget(self.cancel_guidance_button)
        detail_actions.addWidget(self.item_more_button)
        self.save_guidance_button.hide()
        self.cancel_guidance_button.hide()
        self.placement_list = QListWidget()
        self.placement_list.setMaximumHeight(95)
        placement_actions = QHBoxLayout()
        self.add_placement_button = QPushButton("加入 Section")
        self.remove_placement_button = QPushButton("移除 Placement")
        self.reorder_placement_button = QPushButton("设置顺序")
        placement_actions.addWidget(self.add_placement_button)
        placement_actions.addWidget(self.remove_placement_button)
        placement_actions.addWidget(self.reorder_placement_button)
        self.revision_table = QTableWidget(0, 5)
        self.revision_table.setHorizontalHeaderLabels(
            ["状态", "捕获时间", "SHA-256", "保护", "内容提取"]
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
        detail_layout.addWidget(QLabel("阅读说明"))
        detail_layout.addWidget(self.guidance_preview)
        detail_layout.addWidget(self.guidance_edit)
        detail_layout.addLayout(detail_actions)
        self.placement_toggle = QToolButton()
        self.placement_toggle.setText("分组与位置")
        self.placement_toggle.setCheckable(True)
        self.placement_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.placement_toggle.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self.placement_panel = QWidget()
        placement_layout = QVBoxLayout(self.placement_panel)
        placement_layout.setContentsMargins(0, 0, 0, 0)
        placement_layout.addWidget(self.placement_list)
        placement_layout.addLayout(placement_actions)
        self.placement_panel.hide()
        self.placement_toggle.toggled.connect(self.placement_panel.setVisible)
        detail_layout.addWidget(self.placement_toggle)
        detail_layout.addWidget(self.placement_panel)
        self.revision_toggle = QToolButton()
        self.revision_toggle.setText("版本与内容")
        self.revision_toggle.setCheckable(True)
        self.revision_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.revision_toggle.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self.revision_panel = QWidget()
        revision_layout = QVBoxLayout(self.revision_panel)
        revision_layout.setContentsMargins(0, 0, 0, 0)
        revision_layout.addWidget(self.revision_table)
        revision_actions = QHBoxLayout()
        revision_actions.addWidget(self.advance_button)
        revision_actions.addWidget(self.protect_button)
        revision_layout.addLayout(revision_actions)
        self.revision_panel.hide()
        self.revision_toggle.toggled.connect(self.revision_panel.setVisible)
        detail_layout.addWidget(self.revision_toggle)
        detail_layout.addWidget(self.revision_panel)

        self.extract_button = QPushButton("提取所选 Revision")
        self.ai_analyze_button = QPushButton("AI 辅助分析")
        self.extract_status = QLabel("")
        self.extract_status.setWordWrap(True)
        self.extract_status.hide()
        revision_layout.addWidget(self.extract_button)
        revision_layout.addWidget(self.ai_analyze_button)
        revision_layout.addWidget(self.extract_status)
        detail_layout.addStretch(1)

        splitter.addWidget(section_pane)
        splitter.addWidget(item_pane)
        splitter.addWidget(detail_pane)
        self.section_pane.hide()
        self.detail_pane.hide()
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 6)
        splitter.setStretchFactor(2, 4)
        splitter.setSizes([0, 700, 430])
        context_layout.addWidget(splitter)
        self.content_search_toggle = QPushButton("搜索内容")
        self.content_search_toggle.setProperty("variant", "quiet")
        self.content_search_toggle.setCheckable(True)
        self.content_search_toggle.toggled.connect(self._toggle_content_search)
        context_layout.addWidget(
            self.content_search_toggle, 0, Qt.AlignmentFlag.AlignLeft
        )
        self.content_search_panel = QWidget()
        content_layout = QVBoxLayout(self.content_search_panel)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(6)
        search_bar = QHBoxLayout()
        self.content_query = QLineEdit()
        self.content_query.setPlaceholderText("搜索核心文件内容")
        self.content_search_button = QPushButton("搜索")
        self.content_rebuild_button = QPushButton("重建索引")
        self.content_recover_button = QPushButton("恢复中断提取")
        search_bar.addWidget(self.content_query, 1)
        search_bar.addWidget(self.content_search_button)
        content_layout.addLayout(search_bar)
        self.content_status = QLabel("")
        self.content_status.hide()
        content_layout.addWidget(self.content_status)
        self.content_results = QTableWidget(0, 3)
        self.content_results.setHorizontalHeaderLabels(["文件", "位置", "命中片段"])
        self.content_results.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.content_results.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.content_results.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.content_results.setMaximumHeight(220)
        content_layout.addWidget(self.content_results)
        self.content_search_panel.hide()
        context_layout.addWidget(self.content_search_panel)
        self.experience_toggle = QPushButton("项目脉络")
        self.experience_toggle.setProperty("variant", "quiet")
        self.experience_toggle.setCheckable(True)
        context_layout.addWidget(self.experience_toggle, 0, Qt.AlignmentFlag.AlignLeft)
        self.experience_panel = QWidget()
        experience_layout = QVBoxLayout(self.experience_panel)
        experience_layout.setContentsMargins(0, 0, 0, 0)
        self.experience_list = QListWidget()
        self.experience_list.setMaximumHeight(180)
        experience_layout.addWidget(self.experience_list)
        experience_actions = QHBoxLayout()
        self.experience_add = QPushButton("记录")
        self.experience_edit = QPushButton("更正")
        self.experience_confirm = QPushButton("确认")
        self.experience_supersede = QPushButton("标记被取代")
        for button in (self.experience_add, self.experience_edit,
                       self.experience_confirm, self.experience_supersede):
            experience_actions.addWidget(button)
        experience_actions.addStretch(1)
        experience_layout.addLayout(experience_actions)
        self.experience_panel.hide()
        context_layout.addWidget(self.experience_panel)
        self.stack.addWidget(self.context_page)
        outer.addWidget(self.stack, 1)

        self.refresh_button.clicked.connect(self.reload)
        self.export_pack_button.clicked.connect(self._export_pack)
        self.pack_history_button.clicked.connect(self._pack_history)
        self.upgrade_button.clicked.connect(self._upgrade)
        self.section_view.selectionModel().selectionChanged.connect(
            lambda *_: self._section_changed()
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
        self.extract_button.clicked.connect(self._extract_selected_revision)
        self.ai_analyze_button.clicked.connect(self._plan_ai)
        self.content_search_button.clicked.connect(self._search_content)
        self.content_query.returnPressed.connect(self._search_content)
        self.content_rebuild_button.clicked.connect(self._rebuild_content_index)
        self.content_recover_button.clicked.connect(self._recover_content_runs)
        self.content_results.cellDoubleClicked.connect(self._open_content_hit)
        self.experience_toggle.toggled.connect(self._toggle_experience)
        self.experience_add.clicked.connect(self._create_experience)
        self.experience_edit.clicked.connect(self._correct_experience)
        self.experience_confirm.clicked.connect(self._confirm_experience)
        self.experience_supersede.clicked.connect(self._supersede_experience)
        self.experience_list.itemSelectionChanged.connect(self._update_experience_buttons)
        self.experience_list.itemDoubleClicked.connect(lambda *_: self._show_experience())
        self.cleanup_button.clicked.connect(self._preview_cleanup)
        self._show_no_project()

    def _section_changed(self) -> None:
        index = self.section_view.currentIndex()
        kind, section = self.section_model.entry(index.row())
        label = (
            section.name if kind == "SECTION" and section is not None
            else "未分组" if kind == "UNSECTIONED"
            else "全部核心文件"
        )
        self.section_filter_button.setText(f"{label}  ▾")
        self._filter_items()

    def _set_guidance_editing(self, editing: bool) -> None:
        if not editing and self._details is not None:
            annotation = (
                self._details.annotations[0]
                if self._details.annotations else None
            )
            self.guidance_edit.setPlainText(
                "" if annotation is None else annotation.body
            )
        self.guidance_preview.setVisible(not editing)
        self.guidance_edit.setVisible(editing)
        self.edit_guidance_button.setVisible(not editing)
        self.save_guidance_button.setVisible(editing)
        self.cancel_guidance_button.setVisible(editing)
        if editing:
            self.guidance_edit.setFocus()

    def _toggle_content_search(self, visible: bool) -> None:
        self.content_search_panel.setVisible(visible)
        self.content_search_toggle.setText(
            "关闭搜索" if visible else "搜索内容"
        )
        if visible:
            self.content_query.setFocus()

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
        self.experience_list.clear()
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
            self.add_from_workspace_button, self.context_more_button,
            self.section_filter_button, self.content_search_toggle,
            self.section_view, self.item_view, self.add_section_button,
            self.rename_section_button, self.remove_section_button,
            self.restore_section_button, self.guidance_edit,
            self.save_guidance_button, self.advance_button,
            self.remove_item_button, self.add_placement_button,
            self.remove_placement_button, self.reorder_placement_button,
            self.revision_table, self.protect_button, self.upgrade_button,
            self.item_more_button,
            self.extract_button, self.content_query, self.content_search_button,
            self.ai_analyze_button,
            self.content_rebuild_button, self.content_results,
            self.content_recover_button,
            self.experience_toggle, self.experience_list, self.experience_add,
            self.experience_edit, self.experience_confirm, self.experience_supersede,
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
        if self.experience_panel.isVisible():
            self._load_experiences()

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
        project_id, database_path = self._project_id, self._database_path
        self._run(
            "加载 Context Item",
            lambda: (
                self._application.get_context_item_details(GetContextItemDetailsRequest(
                    project_id=project_id, database_path=database_path,
                    context_item_id=item_id,
                )),
                self._application.get_content_item_runs(project_id, database_path, item_id),
            ),
            lambda result: self._apply_item_details(*result),
        )

    def _apply_item_details(self, details, runs) -> None:
        self._details = details
        self.detail_pane.show()
        view = details.view
        title = view.item.title_override or view.workspace_item.display_name
        self.detail_title.setText(title)
        freshness = {
            "CURRENT": "已固定版本",
            "WORKSPACE_UPDATED": "有更新待确认",
            "WORKSPACE_MISSING": "工作文件缺失",
            "WORKSPACE_UNREADABLE": "工作文件无法读取",
        }.get(view.freshness.value, view.freshness.value)
        self.detail_summary.setText(
            " · ".join(part for part in (view.item.purpose, freshness) if part)
        )
        annotation = details.annotations[0] if details.annotations else None
        self.guidance_edit.setPlainText("" if annotation is None else annotation.body)
        self.guidance_preview.setText(
            "尚无阅读说明" if annotation is None or not annotation.body
            else annotation.body
        )
        self._set_guidance_editing(False)
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
        run_by_revision = {}
        for run in runs:
            run_by_revision.setdefault(run.context_revision_id, run)
        for value in details.revisions:
            row = self.revision_table.rowCount()
            self.revision_table.insertRow(row)
            cells = (
                value.capture_status.value,
                value.created_at.astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                value.source_observed_sha256 or "",
                "已保护" if value.is_manually_protected else "",
                (run_by_revision[value.id].status.value
                 if value.id in run_by_revision else "未提取"),
            )
            for column, text in enumerate(cells):
                cell = QTableWidgetItem(text)
                if column == 0:
                    cell.setData(CONTEXT_ID_ROLE, value.id)
                self.revision_table.setItem(row, column, cell)
        current_revision_id = view.item.current_context_revision_id
        for row in range(self.revision_table.rowCount()):
            cell = self.revision_table.item(row, 0)
            if cell is not None and cell.data(CONTEXT_ID_ROLE) == current_revision_id:
                self.revision_table.selectRow(row)
                break
        self.extract_status.hide()
        self._update_action_state()

    def _clear_details(self) -> None:
        self._details = None
        if hasattr(self, "detail_title"):
            self.detail_pane.hide()
            self.detail_title.setText("未选择核心文件")
            self.detail_summary.setText("")
            self.guidance_preview.setText("")
            self._set_guidance_editing(False)
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

    def _extract_selected_revision(self) -> None:
        rows = self.revision_table.selectionModel().selectedRows()
        if not self._has_project() or len(rows) != 1:
            return
        revision_id = self.revision_table.item(rows[0].row(), 0).data(CONTEXT_ID_ROLE)
        if QMessageBox.question(
            self, "提取固定版本内容",
            "将把所选固定 Revision 的可检索正文及位置写入本项目 project.sqlite。"
            "不读取后来变化的 Workspace 文件，也不会上传内容。继续？",
        ) != QMessageBox.StandardButton.Yes:
            return
        self._run(
            "提取 Context 内容",
            lambda control: self._application.extract_context_revisions(
                ExtractContextRevisionsRequest(
                    project_id=self._project_id, database_path=self._database_path,
                    revision_ids=(revision_id,), actor=self._actor,
                ), control=control,
            ),
            self._content_extraction_completed,
            progress=True,
        )

    def _content_extraction_completed(self, result) -> None:
        run = result.runs[0]
        self.extract_status.setText(
            f"{run.status.value} · {run.element_count} 个元素"
            + (" · " + run.error_code if run.error_code else "")
        )
        self.extract_status.show()
        if run.status.value not in ("SUCCEEDED", "PARTIAL"):
            QMessageBox.information(self, "提取结果", self.extract_status.text())

    def _plan_ai(self) -> None:
        rows = self.revision_table.selectionModel().selectedRows()
        if not self._has_project() or len(rows) != 1 or self._result is None:
            return
        revision_id = self.revision_table.item(rows[0].row(), 0).data(CONTEXT_ID_ROLE)
        others = [(view.item.current_context_revision_id,
                   view.item.title_override or view.workspace_item.display_name)
                  for view in self._result.items
                  if view.item.current_context_revision_id
                  and view.item.current_context_revision_id != revision_id]
        if self._details is not None:
            title = (self._details.view.item.title_override
                     or self._details.view.workspace_item.display_name)
            known = {value[0] for value in others}
            for revision in self._details.revisions:
                if (revision.id != revision_id
                        and revision.capture_status == ContextRevisionCaptureStatus.READY
                        and revision.id not in known):
                    others.append((revision.id,
                                   f"{title} · {revision.created_at.astimezone():%Y-%m-%d %H:%M}"))
                    known.add(revision.id)
        dialog = AIActionDialog(profiles=self._application.get_analysis_models(),
                                other_revisions=others, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        action = AnalysisAction(dialog.action.currentData())
        revisions = (revision_id, dialog.other_revision.currentData()) if (
            action == AnalysisAction.COMPARE) else (revision_id,)
        provider, model = dialog.model.currentData()
        request = AnalysisPlanRequest(self._project_id, self._database_path,
                                      action, revisions, provider, model)
        self._run("准备 AI 输入预览", lambda: self._application.plan_ai_analysis(request),
                  self._show_ai_plan)

    def _show_ai_plan(self, plan) -> None:
        dialog = AIPlanPreviewDialog(plan,
            can_execute=self._application.can_execute_ai_analysis(plan), parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._run("AI 辅助分析", lambda: self._application.execute_ai_analysis(
            plan, actor=self._actor, confirmed_token=plan.consent_token),
            self._show_ai_result)

    def _show_ai_result(self, result) -> None:
        if result.status.value != "SUCCEEDED":
            QMessageBox.warning(self, "AI 分析未完成",
                                f"草稿状态：{result.status.value} · {result.error_code or '未知错误'}")
            return
        dialog = AIResultDialog(result, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected_revision_id:
            revision_id = dialog.selected_revision_id
            self._run("打开 AI 引用的固定版本", lambda: self._application.open_context_revision(
                OpenContextRevisionRequest(self._project_id, self._database_path,
                                           revision_id)), lambda _result: None)

    def _ai_history(self) -> None:
        if not self._has_project() or self._busy:
            return
        self._run("读取 AI 草稿", lambda: self._application.list_ai_analyses(
            self._project_id, self._database_path), self._choose_ai_history)

    def _recover_ai_runs(self) -> None:
        if not self._has_project() or self._busy:
            return
        if QMessageBox.question(
            self, "恢复中断 AI 分析",
            "请先确认本机没有仍在运行的 AI 请求。此操作仅把上次中断的 RUNNING 草稿"
            "标为 INTERRUPTED，不会重发请求。继续？",
        ) != QMessageBox.StandardButton.Yes:
            return
        self._run("恢复中断 AI 分析", lambda: self._application.recover_interrupted_ai_analyses(
            self._project_id, self._database_path, actor=self._actor),
            lambda count: QMessageBox.information(
                self, "恢复完成", f"已标记 {count} 条中断草稿；未重新外发。"))

    def _choose_ai_provider(self) -> str | None:
        provider, accepted = QInputDialog.getItem(
            self, "模型 Provider", "选择 Provider", ["openai", "deepseek"], 0, False,
        )
        return provider if accepted else None

    def _set_ai_key(self) -> None:
        provider = self._choose_ai_provider()
        if provider is None:
            return
        secret, accepted = QInputDialog.getText(
            self, "设置模型 API 密钥", f"{provider} API 密钥",
            QLineEdit.EchoMode.Password,
        )
        if not accepted or not secret:
            return
        if QMessageBox.question(
            self, "保存密钥",
            "密钥只写入本机 Windows 凭据管理器，不写入项目库。"
            "当前真实外发仍被资格 Gate 禁止；保存密钥不会自动调用 API。继续？",
        ) != QMessageBox.StandardButton.Yes:
            return
        self._run("保存模型密钥", lambda: self._application.save_ai_credential(
            provider, secret),
            lambda _result: QMessageBox.information(self, "密钥已保存",
                                                   "已保存在本机凭据管理器；没有发送资料。"))

    def _remove_ai_key(self) -> None:
        provider = self._choose_ai_provider()
        if provider is None:
            return
        if QMessageBox.question(self, "清除模型密钥",
                                f"从本机凭据管理器清除 {provider} 的 PIG 密钥？") != QMessageBox.StandardButton.Yes:
            return
        self._run("清除模型密钥", lambda: self._application.remove_ai_credential(provider),
                  lambda _result: QMessageBox.information(self, "密钥已清除",
                                                         "本机 PIG 凭据已清除。"))

    def _choose_ai_history(self, rows) -> None:
        if not rows:
            QMessageBox.information(self, "AI 草稿", "尚无 AI 草稿。")
            return
        labels = [f"{row[5].astimezone():%Y-%m-%d %H:%M} · {row[1].value} · "
                  f"{row[2]}/{row[3]} · {row[4].value} · {row[0][:8]}" for row in rows]
        choice, accepted = QInputDialog.getItem(self, "AI 草稿历史", "选择草稿",
                                                labels, 0, False)
        if accepted:
            run_id = rows[labels.index(choice)][0]
            self._run("读取 AI 草稿", lambda: self._application.get_ai_analysis(
                self._project_id, self._database_path, run_id), self._show_ai_result)

    def _search_content(self) -> None:
        query = self.content_query.text().strip()
        if not self._has_project() or not query:
            return
        self._run(
            "搜索 Context 内容",
            lambda: self._application.search_context_content(
                SearchContextContentRequest(
                    project_id=self._project_id, database_path=self._database_path,
                    query=query,
                )
            ),
            self._show_content_hits,
        )

    def _show_content_hits(self, result) -> None:
        self.content_results.setRowCount(0)
        for hit in result.hits:
            row = self.content_results.rowCount()
            self.content_results.insertRow(row)
            values = (
                hit.title,
                f"{hit.locator_kind}: {hit.locator_value}",
                hit.snippet,
            )
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setData(CONTEXT_ID_ROLE, hit.context_revision_id)
                if column == 0:
                    cell.setToolTip("双击打开固定版本的只读副本")
                self.content_results.setItem(row, column, cell)
        self.content_status.setText(f"找到 {result.total} 条")
        self.content_status.show()

    def _open_content_hit(self, row: int, _column: int) -> None:
        item = self.content_results.item(row, 0)
        if item is None or not self._has_project():
            return
        revision_id = item.data(CONTEXT_ID_ROLE)
        self._run(
            "打开固定 Revision 副本",
            lambda: self._application.open_context_revision(
                OpenContextRevisionRequest(
                    project_id=self._project_id, database_path=self._database_path,
                    revision_id=revision_id,
                )
            ),
            lambda _result: None,
        )

    def _rebuild_content_index(self) -> None:
        if not self._has_project():
            return
        if QMessageBox.question(self, "重建内容索引",
                                "从已保存的内容元素重建搜索索引；不重新读取文件。继续？") != QMessageBox.StandardButton.Yes:
            return
        self._run(
            "重建 Context 索引",
            lambda: self._application.rebuild_context_index(
                RebuildContextIndexRequest(
                    project_id=self._project_id, database_path=self._database_path,
                    actor=self._actor,
                )
            ),
            lambda result: QMessageBox.information(self, "索引已重建",
                                                   f"已索引 {result.element_count} 个内容元素。"),
        )

    def _recover_content_runs(self) -> None:
        if not self._has_project():
            return
        if QMessageBox.question(
            self, "恢复中断提取", "确认没有其他 PIG 实例或提取任务仍在处理此项目？"
            "确认后，遗留 RUNNING 记录会标记失败，可再次显式提取。",
        ) != QMessageBox.StandardButton.Yes:
            return
        self._run(
            "恢复中断提取",
            lambda: self._application.recover_interrupted_content(
                RecoverInterruptedContentRequest(
                    project_id=self._project_id, database_path=self._database_path,
                    actor=self._actor, confirmed_no_active_extraction=True,
                )
            ),
            lambda result: QMessageBox.information(self, "恢复完成",
                                                   f"已恢复 {len(result.recovered_run_ids)} 个中断记录。"),
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

    def _toggle_experience(self, visible: bool) -> None:
        self.experience_panel.setVisible(visible)
        if visible:
            self._load_experiences()

    def _load_experiences(self) -> None:
        if not self._has_project() or self._busy:
            return
        self._run(
            "加载项目脉络",
            lambda: self._application.list_experience_summaries(
                project_id=self._project_id, database_path=self._database_path,
                limit=50,
            ),
            self._apply_experiences,
        )

    def _apply_experiences(self, summaries) -> None:
        selected_id = self._selected_experience_id()
        self.experience_list.clear()
        names = {ExperienceKind.JUDGMENT: "判断", ExperienceKind.DECISION: "决定",
                 ExperienceKind.LESSON: "经验"}
        states = {ExperienceStatus.DRAFT: "草稿", ExperienceStatus.CONFIRMED: "已确认",
                  ExperienceStatus.SUPERSEDED: "已取代"}
        for summary in summaries:
            record = summary.record
            entry = QListWidgetItem(
                f"{names[record.kind]} · {summary.title} · {states[record.status]}"
            )
            entry.setData(CONTEXT_ID_ROLE, record.id)
            entry.setToolTip(f"{summary.author} · {record.updated_at.astimezone():%Y-%m-%d %H:%M}")
            self.experience_list.addItem(entry)
            if record.id == selected_id:
                self.experience_list.setCurrentItem(entry)
        self._update_experience_buttons()

    def _selected_experience_id(self) -> str | None:
        item = self.experience_list.currentItem()
        return None if item is None else item.data(CONTEXT_ID_ROLE)

    def _update_experience_buttons(self) -> None:
        selected = self._selected_experience_id() is not None
        self.experience_edit.setEnabled(selected and not self._busy)
        self.experience_confirm.setEnabled(selected and not self._busy)
        self.experience_supersede.setEnabled(selected and not self._busy)

    def _experience_choices(self, detail=None):
        preferred = self._selected_item_id()
        choices = []
        seen = set()
        for view in self._result.items:
            revision_id = view.item.current_context_revision_id
            if revision_id:
                choices.append((view.item.id, revision_id,
                                view.item.title_override or view.workspace_item.display_name,
                                view.item.id == preferred))
                seen.add((view.item.id, revision_id))
        if detail is not None:
            for link in detail.revision_links:
                key = (link.context_item_id, link.context_revision_id)
                if key not in seen:
                    choices.append((*key, f"历史固定版本 · {link.context_revision_id[:8]}", False))
        return tuple(choices)

    def _create_experience(self) -> None:
        if not self._has_project() or self._result is None or self._busy:
            return
        self._show_create_experience()

    def _show_create_experience(self) -> None:
        dialog = ExperienceDialog(self._experience_choices(), parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        request = ExperienceMutationRequest(
            project_id=self._project_id, database_path=self._database_path,
            actor=self._actor, expected_context_revision=self._context_revision,
            kind=ExperienceKind(dialog.kind.currentData()), title=dialog.derived_title,
            body=dialog.body.toPlainText().strip(), evidence=dialog.selected_evidence,
            event_ids=(),
        )
        self._run("记录项目脉络", lambda: self._application.create_experience(request),
                  lambda _result: self.reload())

    def _selected_experience_detail(self, callback) -> None:
        record_id = self._selected_experience_id()
        if not record_id or self._busy:
            return
        self._run("读取人工记录", lambda: self._application.get_experience(
            project_id=self._project_id, database_path=self._database_path,
            record_id=record_id), callback)

    def _show_experience(self) -> None:
        self._selected_experience_detail(
            lambda detail: ExperienceHistoryDialog(detail, self).exec())

    def _correct_experience(self) -> None:
        self._selected_experience_detail(self._show_experience_edit)

    def _show_experience_edit(self, detail) -> None:
        self._show_experience_edit_dialog(detail)

    def _show_experience_edit_dialog(self, detail) -> None:
        dialog = ExperienceDialog(self._experience_choices(detail), initial=detail, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        request = ExperienceMutationRequest(
            project_id=self._project_id, database_path=self._database_path,
            actor=self._actor, expected_context_revision=self._context_revision,
            kind=detail.record.kind, title=dialog.derived_title,
            body=dialog.body.toPlainText().strip(), evidence=dialog.selected_evidence,
            event_ids=tuple(link.event_id for link in detail.event_links),
            record_id=detail.record.id, expected_record_version=detail.record.current_version,
        )
        self._run("更正人工记录", lambda: self._application.correct_experience(request),
                  lambda _result: self.reload())

    def _confirm_experience(self) -> None:
        self._selected_experience_detail(lambda detail: self._transition_experience(detail, True))

    def _supersede_experience(self) -> None:
        self._selected_experience_detail(lambda detail: self._transition_experience(detail, False))

    def _transition_experience(self, detail, confirm: bool) -> None:
        label = "确认" if confirm else "标记被取代"
        if QMessageBox.question(self, label + "人工记录",
                                f"确定要{label}“{detail.versions[-1].title}”吗？") != QMessageBox.StandardButton.Yes:
            return
        request = ExperienceTransitionRequest(
            project_id=self._project_id, database_path=self._database_path,
            actor=self._actor, expected_context_revision=self._context_revision,
            record_id=detail.record.id, expected_record_version=detail.record.current_version,
        )
        action = (self._application.confirm_experience if confirm
                  else self._application.supersede_experience)
        self._run(label + "人工记录", lambda: action(request), lambda _result: self.reload())

    def _export_pack(self) -> None:
        if not self._has_project() or self._result is None or self._busy:
            return
        views = tuple(self._result.items)
        if not views:
            QMessageBox.information(self, "Context Pack", "请先添加核心文件。")
            return
        self._run(
            "读取 Context Revisions",
            lambda: (tuple((view, self._application.get_context_item_details(
                GetContextItemDetailsRequest(
                    project_id=self._project_id, database_path=self._database_path,
                    context_item_id=view.item.id,
                )).revisions) for view in views),
                self._application.list_experience_summaries(
                    project_id=self._project_id, database_path=self._database_path,
                    limit=50,
                )),
            self._show_pack_dialog,
        )

    def _show_pack_dialog(self, payload) -> None:
        rows, records = payload
        dialog = ContextPackDialog(self._result.project.name, rows, records, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        selected_ids = dialog.selected_item_ids
        revision_choices = dialog.revision_choices
        record_ids = dialog.selected_record_ids
        self._run(
            "预检 Context Pack",
            lambda control: self._application.preflight_context_pack_export(
                PreflightContextPackExportRequest(
                    project_id=self._project_id, database_path=self._database_path,
                    destination_path=Path(dialog.destination.text().strip()),
                    format=ContextPackFormat(dialog.format_choice.currentData()), actor=self._actor,
                    selected_item_ids=selected_ids, revision_choices=revision_choices,
                    selected_record_ids=record_ids,
                ), control=control,
            ),
            lambda result: self._confirm_pack_export(result, selected_ids, revision_choices,
                                                     record_ids),
            progress=True,
        )

    def _confirm_pack_export(self, preflight, selected_ids, revision_choices,
                             record_ids) -> None:
        warning = (
            f"\n注意：{len(preflight.plan.warning_item_ids)} 个固定 Revision 对应的 Workspace 已变化。"
            if preflight.plan.warning_item_ids else ""
        )
        answer = QMessageBox.question(
            self, "确认导出 Context Pack",
            f"格式：{preflight.format.value}\n"
            f"文件：{len(preflight.plan.entries)} 个 · {_format_bytes(preflight.plan.total_bytes)}\n"
            f"人工记录：{len(record_ids)} 条 · 清单版本 {preflight.plan.manifest_schema_version}\n"
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
                    revision_choices=revision_choices, selected_record_ids=record_ids,
                    confirm_outdated=bool(warning),
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
        self.add_from_workspace_button.setEnabled(
            self._has_project() and not self._busy
        )
        self.context_more_button.setEnabled(active)
        self.section_filter_button.setEnabled(active)
        self.content_search_toggle.setEnabled(active)
        self.history_action.setEnabled(active)
        self.cleanup_action.setEnabled(active)
        self.refresh_context_action.setEnabled(
            self._has_project() and not self._busy
        )
        self.rebuild_index_action.setEnabled(active)
        self.recover_content_action.setEnabled(active)
        self.ai_history_action.setEnabled(active)
        self.recover_ai_action.setEnabled(active)
        self.set_ai_key_action.setEnabled(active)
        self.remove_ai_key_action.setEnabled(active)
        self.restore_section_button.setEnabled(
            active and bool(self._result.removed_sections)
        )
        self.restore_item_button.setEnabled(active and bool(self._result.removed_items))
        self.restore_item_action.setEnabled(
            active and bool(self._result.removed_items)
        )
        self.add_section_button.setEnabled(active)
        self.rename_section_button.setEnabled(active and section is not None)
        self.remove_section_button.setEnabled(active and section is not None)
        for button in (
            self.save_guidance_button, self.advance_button, self.remove_item_button,
            self.add_placement_button, self.edit_guidance_button,
            self.item_more_button,
        ):
            button.setEnabled(active and item is not None)
        self.placement_toggle.setEnabled(active and item is not None)
        self.revision_toggle.setEnabled(active and item is not None)
        placement = self._selected_placement()
        self.remove_placement_button.setEnabled(active and placement is not None)
        self.reorder_placement_button.setEnabled(active and placement is not None)
        self.protect_button.setEnabled(
            active and len(self.revision_table.selectionModel().selectedRows()) == 1
        )
        selected_revisions = self.revision_table.selectionModel().selectedRows()
        self.extract_button.setEnabled(
            active and len(selected_revisions) == 1 and self._details is not None and
            any(value.id == self.revision_table.item(selected_revisions[0].row(), 0).data(CONTEXT_ID_ROLE)
                and value.capture_status == ContextRevisionCaptureStatus.READY
                for value in self._details.revisions)
        )
        self.ai_analyze_button.setEnabled(self.extract_button.isEnabled())
        self.content_search_button.setEnabled(active)
        self.content_rebuild_button.setEnabled(active)
        self.content_recover_button.setEnabled(active)

    def _show_no_project(self) -> None:
        if not hasattr(self, "stack"):
            return
        self.stack.setCurrentWidget(self.setup_page)
        self.setup_title.setText("尚未打开项目")
        self.setup_message.setText("请先新建或打开一个 PIG Project。")
        self.upgrade_button.hide()

    def _has_project(self) -> bool:
        return self._project_id is not None and self._database_path is not None
