from __future__ import annotations

import os
import time
from pathlib import Path
from threading import Event
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPointF, QUrl
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QInputDialog,
    QMessageBox,
)

from pig.application import CreateProjectRequest, OperationStage
from pig.application.contracts import CreateWorkspaceFolderRequest
from pig.bootstrap import create_local_application
from pig.domain.enums import (
    NodeFormat,
    WorkingContentStatus,
    WorkspaceItemKind,
    WorkspaceMaterializationStatus,
)
from pig.ui.main_window import ITEM_ID_ROLE, ITEM_KIND_ROLE, MainWindow, WorkspaceTree


class RecordingOpener:
    def __init__(self) -> None:
        self.paths: list[Path] = []

    def open(self, path: Path) -> None:
        self.paths.append(path)


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


def _wait_idle(qt_app, window: MainWindow, timeout: float = 15) -> None:
    deadline = time.monotonic() + timeout
    idle_since = None
    while time.monotonic() < deadline:
        qt_app.processEvents()
        idle = window._worker_thread is None and not window._reload_after_background
        if idle:
            idle_since = time.monotonic() if idle_since is None else idle_since
            if time.monotonic() - idle_since >= 0.05:
                return
        else:
            idle_since = None
        time.sleep(0.01)
    raise AssertionError(f"desktop did not become idle: {window._busy_operation}")


def test_tree_expansion_drag_target_move_undo_and_rename(
    qt_app, tmp_path: Path, monkeypatch
) -> None:
    application = create_local_application(tmp_path / "projects")
    project = application.create_project(
        CreateProjectRequest(name="Workspace interactions", actor="tester")
    )
    def folder(name: str, revision: int, parent=None):
        return application.create_workspace_folder(CreateWorkspaceFolderRequest(
            project_id=project.project_id,
            database_path=project.database_path,
            display_name=name,
            actor="tester",
            expected_workspace_revision=revision,
            parent_workspace_item_id=parent,
        ))
    first = folder("A", 0)
    second = folder("B", 1)
    child = folder("child", 2, first.item.id)
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *_args: None))
    window = MainWindow(application, actor="tester")
    window._activate_project(project.project_id, project.database_path)
    _wait_idle(qt_app, window)
    first_index = window.tree.model().index_for_id(first.item.id)
    window.tree.setExpanded(first_index, False)
    window._reload_workspace()
    _wait_idle(qt_app, window)
    assert not window.tree.isExpanded(window.tree.model().index_for_id(first.item.id))
    first_item = window.tree.topLevelItem(0)
    window._tree_double_clicked(first_item, 0)
    assert window.tree.isExpanded(window.tree.model().index_for_id(first.item.id))
    second_item = window.tree.topLevelItem(1)
    parent_id, ordinal, hint = window.tree._drop_destination(
        second_item, QAbstractItemView.DropIndicatorPosition.OnItem
    )
    assert (parent_id, ordinal) == (second.item.id, 0)
    assert "放入文件夹「B」" in hint
    window._move_item(first.item.id, first.item.id, 0)
    assert window._worker_thread is None
    assert window._workspace_revision == 3
    window._show_drag_destination(hint)
    assert not window.drag_destination.isHidden()
    window._show_drag_destination("")

    window._move_item(child.item.id, second.item.id, 0)
    _wait_idle(qt_app, window)
    assert window.undo_move_action.isEnabled()
    assert window._views[child.item.id].placement.parent_workspace_item_id == second.item.id
    window._undo_last_move()
    _wait_idle(qt_app, window)
    assert window._views[child.item.id].placement.parent_workspace_item_id == first.item.id
    assert not window.undo_move_action.isEnabled()
    revision_after_undo = window._workspace_revision
    window._move_item(child.item.id, first.item.id, 0)
    assert window._workspace_revision == revision_after_undo
    assert window._worker_thread is None
    activity = [
        window.events.item(row, 2).text()
        for row in range(window.events.rowCount())
    ]
    assert "已撤销移动" in activity
    assert "WORKSPACE_ITEM_MOVED" not in activity

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(
        lambda *_args, **_kwargs: ("renamed", True)
    ))
    window._rename_item(child.item.id)
    _wait_idle(qt_app, window)
    assert window._views[child.item.id].workspace_path == "A/renamed"
    assert window.advanced_panel.layout().itemAt(2).layout().itemAt(2).widget() is window.rollback_button
    window.close()


def test_search_open_and_new_folder_resume_after_confirmed_recovery(
    qt_app, tmp_path: Path, monkeypatch
) -> None:
    opener = RecordingOpener()
    application = create_local_application(tmp_path / "projects", file_opener=opener)
    project = application.create_project(
        CreateProjectRequest(name="Recovery B01 B02", actor="tester")
    )
    source = tmp_path / "项目简报.txt"
    source.write_bytes(b"synthetic brief")
    questions = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *_args: None))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(
        lambda _parent, title, message: (
            questions.append((title, message)) or QMessageBox.StandardButton.Yes
        )
    ))
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(
        lambda *_args, **_kwargs: ("待确认", True)
    ))
    window = MainWindow(application, actor="tester")
    window._activate_project(project.project_id, project.database_path)
    _wait_idle(qt_app, window)
    window._add_inputs((source,), None)
    _wait_idle(qt_app, window)
    residue = project.workspace_path / ".staging" / "materializations" / "interrupted-test"
    residue.mkdir(parents=True)
    (residue / "partial").write_bytes(b"incomplete synthetic data")

    window.search_text.setText("项目简报")
    window._search()
    _wait_idle(qt_app, window)
    assert window.search_results.rowCount() == 1
    window._search_double_clicked(window.search_results.item(0, 0), 0)
    _wait_idle(qt_app, window)
    assert any(title == "项目需要恢复" for title, _message in questions)
    assert not residue.exists()
    assert not window._recovery_required

    window._search_double_clicked(window.search_results.item(0, 0), 0)
    _wait_idle(qt_app, window)
    assert len(opener.paths) == 1
    window._create_folder()
    _wait_idle(qt_app, window)
    assert any(view.item.display_name == "待确认" for view in window._views.values())
    window.close()


def test_complete_workbench_ui_flow_uses_workspace_actions(
    qt_app, tmp_path: Path, monkeypatch
) -> None:
    opener = RecordingOpener()
    app = create_local_application(tmp_path / "projects", file_opener=opener)
    project = app.create_project(CreateProjectRequest(name="W7 Desktop", actor="tester"))
    source = tmp_path / "报价.txt"
    source.write_bytes(b"original quote")
    messages = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        staticmethod(lambda _parent, title, message: messages.append((title, message))),
    )
    monkeypatch.setattr(
        QMessageBox,
        "question",
        staticmethod(lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes),
    )
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        staticmethod(lambda _parent, title, message: messages.append((title, message))),
    )
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        staticmethod(lambda _parent, title, message: messages.append((title, message))),
    )
    window = MainWindow(app, actor="tester")
    window._activate_project(project.project_id, project.database_path)
    _wait_idle(qt_app, window)
    assert window.tree.topLevelItemCount() == 0

    window._add_inputs((source,), None)
    _wait_idle(qt_app, window)
    assert window.tree.topLevelItemCount() == 1
    assert window._workspace_revision == 1
    file_item = window.tree.topLevelItem(0)
    assert file_item.text(0) == "报价.txt"
    assert file_item.text(3) == "VIRTUAL"

    window.tree.setCurrentItem(file_item)
    window._tree_double_clicked(file_item, 0)
    _wait_idle(qt_app, window)
    assert len(opener.paths) == 1
    assert opener.paths[0] != source
    assert opener.paths[0].read_bytes() == b"original quote"
    assert window.tree.topLevelItem(0).text(3) == "CLEAN"

    file_item = window.tree.topLevelItem(0)
    window.tree.setCurrentItem(file_item)
    window._refresh_selected_file()
    _wait_idle(qt_app, window)
    opener.paths[0].write_bytes(b"edited quote")
    file_item = window.tree.topLevelItem(0)
    window.tree.setCurrentItem(file_item)
    window._focus_refresh_selected()
    _wait_idle(qt_app, window)
    assert window.tree.topLevelItem(0).text(3) == "MODIFIED"

    window.search_text.setText("报价")
    window.format_filter.set_selected_values((NodeFormat.TXT,))
    window.content_filter.set_selected_values((WorkingContentStatus.MODIFIED,))
    window._search()
    _wait_idle(qt_app, window)
    assert window.search_results.rowCount() == 1
    assert window.search_results.item(0, 4).text() == "MODIFIED"
    window.search_results.selectRow(0)
    window._search_double_clicked(window.search_results.item(0, 0), 0)
    _wait_idle(qt_app, window)
    assert opener.paths == [opener.paths[0], opener.paths[0]]

    monkeypatch.setattr(
        QInputDialog,
        "getText",
        staticmethod(lambda *_args, **_kwargs: ("最终资料", True)),
    )
    window.left_tabs.setCurrentWidget(window.tree)
    window.tree.clearSelection()
    window._create_folder()
    _wait_idle(qt_app, window)
    assert window._workspace_revision == 2
    roots = [window.tree.topLevelItem(index) for index in range(window.tree.topLevelItemCount())]
    folder_item = next(item for item in roots if item.text(0) == "最终资料")
    file_item = next(item for item in roots if item.text(0) == "报价.txt")
    window._move_item(
        file_item.data(0, 256),
        folder_item.data(0, 256),
        0,
    )
    _wait_idle(qt_app, window)
    assert window._workspace_revision == 3
    folder_item = next(
        window.tree.topLevelItem(index)
        for index in range(window.tree.topLevelItemCount())
        if window.tree.topLevelItem(index).text(0) == "最终资料"
    )
    assert folder_item.child(0).text(0) == "报价.txt"

    window.tree.setCurrentItem(folder_item.child(0))
    window._delete_selected()
    _wait_idle(qt_app, window)
    folder_item = next(
        window.tree.topLevelItem(index)
        for index in range(window.tree.topLevelItemCount())
        if window.tree.topLevelItem(index).text(0) == "最终资料"
    )
    assert folder_item.childCount() == 0
    assert window.deleted_items.rowCount() == 1
    window.deleted_items.selectRow(0)
    qt_app.processEvents()
    window._restore_deleted_item()
    _wait_idle(qt_app, window)
    folder_item = window.tree.topLevelItem(0)
    assert folder_item.child(0).text(0) == "报价.txt"
    assert folder_item.child(0).text(3) == "MODIFIED"
    window.tree.setCurrentItem(folder_item.child(0))
    window._restore_working_file()
    _wait_idle(qt_app, window)
    folder_item = window.tree.topLevelItem(0)
    assert folder_item.child(0).text(3) == "CLEAN"
    assert opener.paths[0].read_bytes() == b"original quote"
    assert source.read_bytes() == b"original quote"
    assert any(title == "添加完成" for title, _message in messages)
    window.close()


def test_busy_gate_keeps_window_responsive_and_serializes_actions(
    qt_app, tmp_path: Path, monkeypatch
) -> None:
    app = create_local_application(tmp_path / "projects")
    window = MainWindow(app, actor="tester")
    started = Event()
    release = Event()
    notices = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        staticmethod(lambda _parent, title, message: notices.append((title, message))),
    )

    def blocking_action():
        started.set()
        assert release.wait(5)
        return "done"

    results = []
    window._run_background("长操作", blocking_action, results.append)
    deadline = time.monotonic() + 5
    while not started.is_set() and time.monotonic() < deadline:
        qt_app.processEvents()
        time.sleep(0.01)
    assert started.is_set()
    assert not window.new_project_action.isEnabled()
    window._run_background("冲突操作", lambda: "bad", results.append)
    assert notices and "请等待当前操作完成" in notices[0][1]
    window.search_text.setText("仍可响应")
    assert window.search_text.text() == "仍可响应"
    release.set()
    _wait_idle(qt_app, window)
    assert results == ["done"]
    window.close()


def test_typed_progress_appears_quickly_and_cancel_keeps_ui_responsive(
    qt_app, tmp_path: Path, monkeypatch
) -> None:
    app = create_local_application(tmp_path / "projects")
    window = MainWindow(app, actor="tester")
    messages = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        staticmethod(lambda _parent, title, message: messages.append((title, message))),
    )
    started = Event()

    def cancellable_action(control):
        control.start_stage(
            OperationStage.SNAPSHOT_COPY,
            total_count=1,
            total_bytes=1024,
            current_item="large.bin",
        )
        started.set()
        while True:
            control.checkpoint()
            time.sleep(0.01)

    started_at = time.monotonic()
    window._run_background(
        "可取消操作",
        cancellable_action,
        lambda _result: None,
        progress=True,
    )
    while time.monotonic() - started_at < 0.5:
        qt_app.processEvents()
        if not window.cancel_operation_button.isHidden():
            break
        time.sleep(0.01)

    assert started.is_set()
    assert not window.cancel_operation_button.isHidden()
    assert window.cancel_operation_button.isEnabled()
    assert "large.bin" in window.statusBar().currentMessage()
    window.search_text.setText("窗口仍可响应")
    assert window.search_text.text() == "窗口仍可响应"
    window.cancel_operation_button.click()
    _wait_idle(qt_app, window)
    assert messages[-1][0] == "可取消操作"
    assert "安全检查点" in messages[-1][1]
    window.close()


def test_new_project_uses_selected_storage_and_loads_empty_workspace(
    qt_app, tmp_path: Path, monkeypatch
) -> None:
    default_root = tmp_path / "default"
    selected_root = tmp_path / "selected"
    selected_root.mkdir()
    app = create_local_application(default_root)
    window = MainWindow(app, actor="tester")
    messages = []
    monkeypatch.setattr(
        QInputDialog,
        "getText",
        staticmethod(lambda *_args, **_kwargs: ("用户项目", True)),
    )
    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        staticmethod(lambda *_args, **_kwargs: str(selected_root)),
    )
    monkeypatch.setattr(
        QMessageBox,
        "information",
        staticmethod(lambda _parent, title, message: messages.append((title, message))),
    )
    window._new_project()
    _wait_idle(qt_app, window)
    assert window._database_path is not None
    assert window._database_path == selected_root / "用户项目" / "project.sqlite"
    assert window.tree.topLevelItemCount() == 0
    assert "用户项目" in window.project_location.text()
    assert messages[0][0] == "项目已创建"
    assert not default_root.exists()
    window.close()


def test_new_project_permission_failure_explains_storage_access(
    qt_app, tmp_path: Path, monkeypatch
) -> None:
    app = create_local_application(tmp_path / "default")
    window = MainWindow(app, actor="tester")
    warnings = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        staticmethod(lambda _parent, title, message: warnings.append((title, message))),
    )
    denied_path = str(tmp_path / "selected")
    window._show_failure(
        "创建项目", PermissionError(13, "Permission denied", denied_path)
    )
    assert warnings[0][0] == "创建项目"
    assert "无法写入" in warnings[0][1]
    assert denied_path in warnings[0][1]
    window.close()


def test_workspace_tree_drop_translates_external_paths_and_internal_move(
    qt_app, tmp_path: Path
) -> None:
    tree = WorkspaceTree()
    tree.set_views(
        (
            SimpleNamespace(
                item=SimpleNamespace(
                    id="source-id",
                    display_name="source",
                    item_kind=WorkspaceItemKind.FILE,
                    materialization_status=WorkspaceMaterializationStatus.VIRTUAL,
                ),
                placement=SimpleNamespace(
                    parent_workspace_item_id=None,
                    ordinal=0,
                ),
                source_node=None,
                working_artifact=None,
                workspace_path="source",
            ),
        )
    )
    source = tree.topLevelItem(0)
    tree.setCurrentItem(source)
    external = []
    moves = []
    tree.external_paths_dropped.connect(
        lambda paths, target: external.append((paths, target))
    )
    tree.move_requested.connect(
        lambda item_id, parent_id, ordinal: moves.append(
            (item_id, parent_id, ordinal)
        )
    )
    first = tmp_path / "a.txt"
    second = tmp_path / "folder"

    class Mime:
        def __init__(self, urls=()):
            self._urls = urls

        def hasUrls(self):
            return bool(self._urls)

        def urls(self):
            return self._urls

    class Event:
        def __init__(self, mime, event_source=None):
            self._mime = mime
            self._source = event_source
            self.accepted = False

        def mimeData(self):
            return self._mime

        def source(self):
            return self._source

        def position(self):
            return QPointF(10000, 10000)

        def acceptProposedAction(self):
            self.accepted = True

        def ignore(self):
            self.accepted = False

    external_event = Event(
        Mime((QUrl.fromLocalFile(str(first)), QUrl.fromLocalFile(str(second))))
    )
    tree.dropEvent(external_event)
    assert external_event.accepted is True
    assert external == [((first.absolute(), second.absolute()), None)]

    internal_event = Event(Mime(), tree)
    tree.dropEvent(internal_event)
    assert internal_event.accepted is True
    assert moves == [("source-id", None, 1)]
