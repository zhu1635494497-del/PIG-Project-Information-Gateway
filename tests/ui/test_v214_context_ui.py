from __future__ import annotations

import os
import time
from pathlib import Path
from zipfile import ZipFile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QInputDialog, QMessageBox, QTextEdit,
)
from PySide6.QtCore import QTimer
from PySide6.QtCore import Qt

from pig.application import CreateProjectRequest
from pig.bootstrap import create_local_application
from pig.ui.context_view import (
    PromotionDialog, AIActionDialog, AIPlanPreviewDialog, AIResultDialog, ExperienceDialog,
)
from pig.domain.experience_policy import ExperienceKind
from pig.application.ai_analysis_service import AnalysisPlan, AnalysisPlanRequest, AnalysisRunResult
from pig.domain.ai_policy import AnalysisAction, AnalysisElement, AnalysisStatus, ModelClaim
from datetime import datetime, timezone
from decimal import Decimal
from pig.ui.main_window import ITEM_ID_ROLE, MainWindow
from pig.ui.main_window import WorkspaceTreeModel
from pig.application.contracts import GetWorkspaceTreeRequest, ImportProjectItemsRequest, InspectImportSessionRequest


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

    assert window.mode_tabs.tabText(0) == "工作区"
    assert window.mode_tabs.tabText(1) == "核心文件"
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
    assert context.section_pane.isHidden()
    assert context.content_search_panel.isHidden()
    assert context.experience_panel.isHidden()
    assert context.revision_panel.isHidden()
    context.item_view.selectRow(0)
    _wait_idle(qt_app, window)
    assert context.detail_title.text() == "decision.txt"
    assert "已固定版本" in context.detail_summary.text()
    assert context.guidance_edit.isHidden()
    assert context.guidance_preview.text() == "尚无阅读说明"


    context.edit_guidance_button.click()
    assert not context.guidance_edit.isHidden()
    context.cancel_guidance_button.click()
    assert context.guidance_edit.isHidden()
    context.content_search_toggle.click()
    assert not context.content_search_panel.isHidden()

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


def test_unqualified_ai_plan_is_preview_only(qt_app, tmp_path: Path) -> None:
    request = AnalysisPlanRequest("project", tmp_path / "project.sqlite",
                                  AnalysisAction.SUMMARY, ("revision",),
                                  "openai", "gpt-6-luna")
    plan = AnalysisPlan(request, (AnalysisElement("element", "revision", "LINE", "1",
                                                  "synthetic content"),),
                        "COMPLETE_INPUT", 0, "fingerprint", "token", Decimal("0.01"),
                        100, 4000, 1, datetime.now(timezone.utc))
    dialog = AIPlanPreviewDialog(plan, can_execute=False)
    box = dialog.findChild(QDialogButtonBox)
    assert not box.button(QDialogButtonBox.StandardButton.Ok).isEnabled()
    assert "synthetic content" in dialog.findChild(QTextEdit).toPlainText()


def test_ai_preview_passes_typed_action_from_qt_choice(qt_app, tmp_path: Path, monkeypatch) -> None:
    _silence_dialogs(monkeypatch)
    monkeypatch.setattr(PromotionDialog, "exec", lambda _self: QDialog.DialogCode.Accepted)
    app = create_local_application(tmp_path / "projects")
    project = app.create_project(CreateProjectRequest(name="AI UI", actor="tester"))
    source = tmp_path / "brief.txt"
    source.write_bytes(b"brief")
    window = MainWindow(app, actor="tester")
    window._activate_project(project.project_id, project.database_path)
    _wait_idle(qt_app, window)
    window._add_inputs((source,), None)
    _wait_idle(qt_app, window)
    window.context_view.promote_workspace_item(
        window.tree.topLevelItem(0).data(0, ITEM_ID_ROLE), "brief.txt"
    )
    _wait_idle(qt_app, window)
    context = window.context_view
    context.item_view.selectRow(0)
    _wait_idle(qt_app, window)
    context.revision_table.selectRow(0)
    captured = []
    monkeypatch.setattr(AIActionDialog, "exec", lambda _self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(app, "plan_ai_analysis", lambda request: captured.append(request) or object())
    monkeypatch.setattr(context, "_run", lambda _title, action, _done: action())
    context._plan_ai()
    assert len(captured) == 1
    assert captured[0].action is AnalysisAction.SUMMARY
    window.close()


def test_corrupt_zip_tree_displays_source_failure_not_virtual(qt_app, tmp_path: Path) -> None:
    app = create_local_application(tmp_path / "projects")
    project = app.create_project(CreateProjectRequest(name="Corrupt ZIP UI", actor="tester"))
    source = tmp_path / "corrupt.zip"
    source.write_bytes(b"PK\x03\x04not-a-zip")
    imported = app.import_project_items(ImportProjectItemsRequest(
        project_id=project.project_id, database_path=project.database_path,
        input_paths=(source,), actor="tester",
    ))
    app.inspect_import_session(InspectImportSessionRequest(
        project_id=project.project_id, database_path=project.database_path,
        import_session_id=imported.import_session_id, actor="tester",
    ))
    tree = app.get_workspace_tree(GetWorkspaceTreeRequest(
        project_id=project.project_id, database_path=project.database_path,
    ))
    assert len(tree.items) == 1
    assert MainWindow._working_status(tree.items[0]) == "CORRUPTED"
    model = WorkspaceTreeModel()
    model.set_views(tree.items)
    assert model.data(model.index(0, 3), Qt.ItemDataRole.DisplayRole) == "CORRUPTED"


def test_experience_dialog_keeps_explicit_revision_selection(qt_app) -> None:
    dialog = ExperienceDialog((("item-1", "revision-1", "Synthetic A", True),
                               ("item-2", "revision-2", "Synthetic B", False)))
    dialog.body.setPlainText("Synthetic judgment\nSynthetic rationale")
    assert ExperienceKind(dialog.kind.currentData()) == ExperienceKind.JUDGMENT
    assert dialog.derived_title == "Synthetic judgment"
    assert [(choice.context_item_id, choice.context_revision_id)
            for choice in dialog.selected_evidence] == [("item-1", "revision-1")]
    dialog.evidence.item(1).setCheckState(dialog.evidence.item(0).checkState())
    assert len(dialog.selected_evidence) == 2
    assert not hasattr(dialog, "events")


def test_experience_record_uses_one_text_field_and_typed_kind(
    qt_app, tmp_path: Path, monkeypatch,
) -> None:
    _silence_dialogs(monkeypatch)
    monkeypatch.setattr(PromotionDialog, "exec", lambda _self: QDialog.DialogCode.Accepted)
    def accept_record(dialog):
        dialog.body.setPlainText("到场人数与场地容量不一致\n简报预计120人，场地核定110人。")
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(ExperienceDialog, "exec", accept_record)
    application = create_local_application(tmp_path / "projects")
    project = application.create_project(CreateProjectRequest(name="Experience UI", actor="tester"))
    source = tmp_path / "brief.txt"
    source.write_text("预计120人", encoding="utf-8")
    window = MainWindow(application, actor="tester")
    failures = []
    window._show_failure = lambda operation, exc: failures.append((operation, exc))
    window._activate_project(project.project_id, project.database_path)
    _wait_idle(qt_app, window)
    window._add_inputs((source,), None)
    _wait_idle(qt_app, window)
    window.context_view.promote_workspace_item(
        window.tree.topLevelItem(0).data(0, ITEM_ID_ROLE), "brief.txt"
    )
    _wait_idle(qt_app, window)
    window.mode_tabs.setCurrentWidget(window.context_view)
    _wait_idle(qt_app, window)
    window.context_view.item_view.selectRow(0)
    _wait_idle(qt_app, window)
    window.context_view._create_experience()
    _wait_idle(qt_app, window)
    assert not failures
    summaries = application.list_experience_summaries(
        project_id=project.project_id, database_path=project.database_path, limit=10
    )
    assert len(summaries) == 1
    assert summaries[0].record.kind == ExperienceKind.JUDGMENT
    assert summaries[0].title == "到场人数与场地容量不一致"
    window.close()


def test_ai_draft_citation_opens_fixed_revision_target(qt_app) -> None:
    result = AnalysisRunResult(
        id="run", project_id="project", action=AnalysisAction.SUMMARY,
        provider="openai", model="gpt-6-luna", status=AnalysisStatus.SUCCEEDED,
        coverage="PARTIAL_INPUT",
        claims=(ModelClaim("SUMMARY", "Synthetic claim", ("element",)),),
        inputs=(("element", "revision", "LINE", "2"),),
        error_code=None, input_tokens=50, output_tokens=15, possibly_stale=False,
    )
    dialog = AIResultDialog(result)
    dialog.citations.setCurrentRow(0)
    assert dialog.selected_revision_id == "revision"
    assert "LINE: 2" in dialog.citations.item(0).text()


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
    failures = []
    window._show_failure = lambda operation, exc: failures.append((operation, exc))
    window._activate_project(project.project_id, project.database_path)
    _wait_idle(qt_app, window)
    window._add_inputs((source,), None)
    _wait_idle(qt_app, window)
    assert not failures

    container_item = window.tree.topLevelItem(0)
    window.tree.setCurrentItem(container_item)
    container_item.setSelected(True)
    menu = window._active_context_menu(container_item.data(0, ITEM_ID_ROLE))
    assert "加入 Project Context" not in {action.text() for action in menu.actions()}
    window.close()


def test_v23_context_extract_and_search_stay_in_background(
    qt_app, tmp_path: Path, monkeypatch
) -> None:
    _silence_dialogs(monkeypatch)
    monkeypatch.setattr(PromotionDialog, "exec", lambda _self: QDialog.DialogCode.Accepted)
    app = create_local_application(tmp_path / "projects")
    project = app.create_project(CreateProjectRequest(name="Content UI", actor="tester"))
    source = tmp_path / "notes.txt"
    source.write_text("first line\nneedle result\n", encoding="utf-8")
    window = MainWindow(app, actor="tester")
    failures = []
    window._show_failure = lambda operation, exc: failures.append((operation, exc))
    window._activate_project(project.project_id, project.database_path)
    _wait_idle(qt_app, window)
    window._add_inputs((source,), None)
    _wait_idle(qt_app, window)
    assert not failures
    item = window.tree.topLevelItem(0)
    assert item is not None
    window.context_view.promote_workspace_item(item.data(0, ITEM_ID_ROLE), "notes.txt")
    _wait_idle(qt_app, window)
    window.mode_tabs.setCurrentWidget(window.context_view)
    _wait_idle(qt_app, window)
    context = window.context_view
    context.item_view.selectRow(0)
    _wait_idle(qt_app, window)
    qt_app.processEvents()
    assert len(context.revision_table.selectionModel().selectedRows()) == 1
    assert context.extract_button.isEnabled()
    context.extract_button.click()
    _wait_idle(qt_app, window)
    assert "SUCCEEDED" in context.extract_status.text()
    context.content_query.setText("needle")
    context.content_search_button.click()
    _wait_idle(qt_app, window)
    assert context.content_results.rowCount() == 1
    assert "LINE: 2" in context.content_results.item(0, 1).text()
    window.close()


def test_v23_extraction_keeps_ui_heartbeat(qt_app, tmp_path: Path, monkeypatch) -> None:
    _silence_dialogs(monkeypatch)
    monkeypatch.setattr(PromotionDialog, "exec", lambda _self: QDialog.DialogCode.Accepted)
    app = create_local_application(tmp_path / "projects")
    project = app.create_project(CreateProjectRequest(name="Heartbeat", actor="tester"))
    source = tmp_path / "large.txt"
    source.write_text((("record alpha synthetic " * 7) + "\n") * 8_000 + "needle\n",
                      encoding="utf-8")
    window = MainWindow(app, actor="tester")
    window._activate_project(project.project_id, project.database_path)
    _wait_idle(qt_app, window)
    window._add_inputs((source,), None)
    _wait_idle(qt_app, window)
    item = window.tree.topLevelItem(0)
    window.context_view.promote_workspace_item(item.data(0, ITEM_ID_ROLE), "large.txt")
    _wait_idle(qt_app, window)
    window.mode_tabs.setCurrentWidget(window.context_view)
    _wait_idle(qt_app, window)
    context = window.context_view
    context.item_view.selectRow(0)
    _wait_idle(qt_app, window)
    context.revision_table.selectRow(0)
    qt_app.processEvents()
    ticks: list[int] = []
    timer = QTimer()
    timer.setInterval(25)
    timer.timeout.connect(lambda: ticks.append(1))
    timer.start()
    context.extract_button.click()
    _wait_idle(qt_app, window)
    timer.stop()
    assert len(ticks) >= 5
    assert "SUCCEEDED" in context.extract_status.text()
    window.close()
