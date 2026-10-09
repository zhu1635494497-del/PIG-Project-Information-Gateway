"""Offscreen smoke test for the Context Pack desktop action."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from pig.application import CreateProjectRequest
from pig.bootstrap import create_local_application
from pig.ui.context_view import ContextPackDialog, PromotionDialog
from pig.ui.main_window import ITEM_ID_ROLE, MainWindow


def _idle(qt_app, window, timeout=30):
    deadline = time.monotonic() + timeout
    idle_since = None
    while time.monotonic() < deadline:
        qt_app.processEvents()
        if window._worker_thread is None and not window._reload_after_background:
            idle_since = time.monotonic() if idle_since is None else idle_since
            if time.monotonic() - idle_since >= 0.08:
                return
        else:
            idle_since = None
        time.sleep(0.01)
    raise AssertionError("Context Pack UI did not become idle")


def test_context_pack_button_publishes_directory_without_ui_file_logic(tmp_path: Path, monkeypatch) -> None:
    qt_app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *_args: None))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *_args: QMessageBox.StandardButton.Yes))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *_args: None))
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *_args: None))
    monkeypatch.setattr(PromotionDialog, "exec", lambda _self: QDialog.DialogCode.Accepted)
    target = tmp_path / "desktop-handoff"

    def choose_pack(dialog):
        dialog.destination.setText(str(target))
        assert dialog.selected_item_ids
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(ContextPackDialog, "exec", choose_pack)
    app = create_local_application(tmp_path / "projects")
    project = app.create_project(CreateProjectRequest(name="Pack UI", actor="tester"))
    source = tmp_path / "decision.txt"
    source.write_bytes(b"fixed context material")
    window = MainWindow(app, actor="tester")
    failures = []
    window._show_failure = lambda operation, exc: failures.append((operation, exc))
    window.context_view._show_failure = window._show_failure
    window._activate_project(project.project_id, project.database_path)
    _idle(qt_app, window)
    window._add_inputs((source,), None)
    _idle(qt_app, window)
    item = window.tree.topLevelItem(0)
    window.context_view.promote_workspace_item(item.data(0, ITEM_ID_ROLE), "decision.txt")
    _idle(qt_app, window)
    window.mode_tabs.setCurrentWidget(window.context_view)
    _idle(qt_app, window)
    assert window.context_view.export_pack_button.isEnabled()
    window.context_view.export_pack_button.click()
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and not (target / "manifest.json").exists():
        qt_app.processEvents()
        time.sleep(0.01)
    assert not failures, failures
    assert (target / "manifest.json").exists()
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    assert (target / manifest["entries"][0]["relative_path"]).read_bytes() == b"fixed context material"
    _idle(qt_app, window)
    window.close()
