from __future__ import annotations

import os
import time
from pathlib import Path
from zipfile import ZipFile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QInputDialog, QMessageBox

from pig.application import CreateProjectRequest
from pig.bootstrap import create_local_application
from pig.ui.context_view import PromotionDialog
from pig.ui.main_window import ITEM_ID_ROLE, MainWindow


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


def _wait_idle(qt_app, window: MainWindow, timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    idle_since = None
    while time.monotonic() < deadline:
        qt_app.processEvents()
        idle = window._worker_thread is None and not window._reload_after_background
        if idle:
            idle_since = time.monotonic() if idle_since is None else idle_since
            if time.monotonic() - idle_since >= 0.08:
                return
        else:
            idle_since = None
        time.sleep(0.01)
    raise AssertionError(f"desktop did not become idle: {window._busy_operation}")


def _silence_dialogs(monkeypatch) -> None:
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *_args: None))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *_args: None))
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *_args: None))
    monkeypatch.setattr(
        QMessageBox,
        "question",
        staticmethod(lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes),
    )


def test_dual_view_promote_and_three_pane_context_flow(
    qt_app, tmp_path: Path, monkeypatch
) -> None:
    _silence_dialogs(monkeypatch)
    monkeypatch.setattr(
        PromotionDialog, "exec", lambda _self: QDialog.DialogCode.Accepted
    )
    app = create_local_application(tmp_path / "projects")
    project = app.create_project(CreateProjectRequest(name="V214 UI", actor="tester"))
    source = tmp_path / "decision.txt"
    source.write_bytes(b"fixed context bytes")
    window = MainWindow(app, actor="tester")
    window._activate_project(project.project_id, project.database_path)
    _wait_idle(qt_app, window)
    window._add_inputs((source,), None)
    _wait_idle(qt_app, window)

    assert window.mode_tabs.tabText(0) == "Workspace"
    assert window.mode_tabs.tabText(1) == "Project Context"
    workspace_item = window.tree.topLevelItem(0)
    window.tree.setCurrentItem(workspace_item)
    workspace_item.setSelected(True)
    item_id = workspace_item.data(0, ITEM_ID_ROLE)
    menu = window._active_context_menu(item_id)
    assert "加入 Project Context" in {action.text() for action in menu.actions()}

    window.context_view.promote_workspace_item(item_id, "decision.txt")
    _wait_idle(qt_app, window)
    window.mode_tabs.setCurrentWidget(window.context_view)
    _wait_idle(qt_app, window)

    context = window.context_view
    assert context.stack.currentWidget() is context.context_page
    assert context.section_model.rowCount() == 2
    assert context.item_model.rowCount() == 1
    context.item_view.selectRow(0)
    qt_app.processEvents()
    assert context.detail_title.text() == "decision.txt"
    assert "CURRENT" in context.detail_summary.text()

    monkeypatch.setattr(
        QInputDialog,
        "getText",
        staticmethod(lambda *_args, **_kwargs: ("关键决定", True)),
    )
    context._create_section()
    _wait_idle(qt_app, window)
    assert context.section_model.rowCount() == 3

    context.item_view.selectRow(0)
    qt_app.processEvents()
    context.guidance_edit.setPlainText("先阅读结论，再核对来源文件。")
    context._save_guidance()
    _wait_idle(qt_app, window)
    context.item_view.selectRow(0)
    qt_app.processEvents()
    assert context.guidance_edit.toPlainText() == "先阅读结论，再核对来源文件。"
    window.close()


def test_folder_context_menu_does_not_offer_promotion(
    qt_app, tmp_path: Path, monkeypatch
) -> None:
    _silence_dialogs(monkeypatch)
    app = create_local_application(tmp_path / "projects")
    project = app.create_project(CreateProjectRequest(name="Folder Guard", actor="tester"))
    source = tmp_path / "folder"
    source.mkdir()
    (source / "inside.txt").write_bytes(b"inside")
    window = MainWindow(app, actor="tester")
    window._activate_project(project.project_id, project.database_path)
    _wait_idle(qt_app, window)
    window._add_inputs((source,), None)
    _wait_idle(qt_app, window)

    folder_item = window.tree.topLevelItem(0)
    window.tree.setCurrentItem(folder_item)
    folder_item.setSelected(True)
    menu = window._active_context_menu(folder_item.data(0, ITEM_ID_ROLE))
    assert "加入 Project Context" not in {action.text() for action in menu.actions()}
    window.close()


def test_container_context_menu_does_not_offer_promotion(
    qt_app, tmp_path: Path, monkeypatch
) -> None:
    _silence_dialogs(monkeypatch)
    app = create_local_application(tmp_path / "projects")
    project = app.create_project(CreateProjectRequest(name="Container Guard", actor="tester"))
    source = tmp_path / "container.zip"
    with ZipFile(source, "w") as archive:
        archive.writestr("inside.txt", b"inside")
    window = MainWindow(app, actor="tester")
    window._activate_project(project.project_id, project.database_path)
    _wait_idle(qt_app, window)
    window._add_inputs((source,), None)
    _wait_idle(qt_app, window)

    container_item = window.tree.topLevelItem(0)
    window.tree.setCurrentItem(container_item)
    container_item.setSelected(True)
    menu = window._active_context_menu(container_item.data(0, ITEM_ID_ROLE))
    assert "加入 Project Context" not in {action.text() for action in menu.actions()}
    window.close()
