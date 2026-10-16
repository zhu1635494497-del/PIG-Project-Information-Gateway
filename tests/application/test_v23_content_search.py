"""Synthetic fixed-Revision extraction and derived-index acceptance."""

from __future__ import annotations

from email.message import EmailMessage
from io import BytesIO
from pathlib import Path
import sqlite3
from datetime import datetime, timezone
from zipfile import ZipFile

import pytest

from pig.application.content_contracts import (
    ExtractContextRevisionsRequest, RebuildContextIndexRequest, SearchContextContentRequest,
    RecoverInterruptedContentRequest,
    OpenContextRevisionRequest,
)
from pig.application.errors import ApplicationError
from pig.application.operation_control import OperationCancelled
from pig.application.contracts import (
    CreateProjectRequest, GetWorkspaceTreeRequest, ImportProjectItemsRequest,
    InspectImportSessionRequest, PromoteWorkspaceItemToContextRequest,
)
from pig.bootstrap import create_local_application
from pig.domain.enums import ContentExtractionStatus
from pig.domain.entities import ExtractionRun
from pig.infrastructure.database.provider import SqlAlchemyProjectDatabase
from pig.infrastructure.database.migrations import upgrade_database


def _xlsx() -> bytes:
    stream = BytesIO()
    with ZipFile(stream, "w") as archive:
        archive.writestr("xl/workbook.xml", '''<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Budget" sheetId="1" r:id="rId1"/></sheets></workbook>''')
        archive.writestr("xl/_rels/workbook.xml.rels", '''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>''')
        archive.writestr("xl/worksheets/sheet1.xml", '''<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="B1" t="inlineStr"><is><t>needle</t></is></c></row></sheetData></worksheet>''')
    return stream.getvalue()


def _eml() -> bytes:
    message = EmailMessage()
    message["Subject"] = "needle update"
    message["From"] = "sender@example.invalid"
    message["To"] = "reader@example.invalid"
    message.set_content("body line")
    return message.as_bytes()


@pytest.mark.parametrize(("name", "payload", "locator"), [
    ("brief.txt", b"first line\nneedle update\n", "LINE: 2"),
    ("data.csv", b"label,value\nitem,needle\n", "CSV_ROW: 2"),
    ("mail.eml", _eml(), "EMAIL_FIELD: Subject"),
    ("data.xlsx", _xlsx(), "SHEET_CELL: Budget!B1"),
])
def test_fixed_revision_extract_search_reuse_rebuild(tmp_path: Path, name: str,
                                                       payload: bytes, locator: str) -> None:
    source = tmp_path / name
    source.write_bytes(payload)
    app = create_local_application(tmp_path / "projects")
    project = app.create_project(CreateProjectRequest(name="Content", actor="tester"))
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
    promoted = app.promote_workspace_item_to_context(PromoteWorkspaceItemToContextRequest(
        project_id=project.project_id, database_path=project.database_path,
        workspace_item_id=tree.items[0].item.id, actor="tester",
        expected_workspace_revision=tree.workspace_revision,
        expected_context_revision=0,
    ))
    revision_id = promoted.capture.context_revision_id
    request = ExtractContextRevisionsRequest(project.project_id, project.database_path,
                                             (revision_id,), "tester")
    run = app.extract_context_revisions(request).runs[0]
    assert run.status == ContentExtractionStatus.SUCCEEDED
    assert app.extract_context_revisions(request).runs[0].id == run.id
    source.write_bytes(b"external file changed")
    query = SearchContextContentRequest(project.project_id, project.database_path, "needle")
    result = app.search_context_content(query)
    assert result.total >= 1
    assert result.hits[0].context_revision_id == revision_id
    assert f"{result.hits[0].locator_kind}: {result.hits[0].locator_value}" == locator

    with sqlite3.connect(project.database_path) as connection:
        connection.execute("INSERT INTO content_fts(content_fts) VALUES ('delete-all')")
    assert app.search_context_content(query).total == 0
    rebuilt = app.rebuild_context_index(RebuildContextIndexRequest(
        project.project_id, project.database_path, "tester"))
    assert rebuilt.element_count == run.element_count
    assert app.search_context_content(query).total >= 1
    with sqlite3.connect(project.database_path) as connection:
        connection.execute("DROP TABLE content_fts")
    assert app.rebuild_context_index(RebuildContextIndexRequest(
        project.project_id, project.database_path, "tester")).element_count == run.element_count
    assert app.search_context_content(query).total >= 1
    reopened = create_local_application(tmp_path / "projects")
    assert reopened.search_context_content(query).total >= 1


def _ready_revision(tmp_path: Path, name: str, payload: bytes, *, opener=None):
    source = tmp_path / name
    source.write_bytes(payload)
    app = create_local_application(tmp_path / "projects", file_opener=opener)
    project = app.create_project(CreateProjectRequest(name="Content", actor="tester"))
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
    promoted = app.promote_workspace_item_to_context(PromoteWorkspaceItemToContextRequest(
        project_id=project.project_id, database_path=project.database_path,
        workspace_item_id=tree.items[0].item.id, actor="tester",
        expected_workspace_revision=tree.workspace_revision, expected_context_revision=0,
    ))
    return app, project, promoted.capture.context_revision_id


def test_unsupported_format_has_explicit_state_not_false_zero_hits(tmp_path: Path) -> None:
    app, project, revision = _ready_revision(tmp_path, "report.pdf", b"%PDF-1.4\nsynthetic")
    run = app.extract_context_revisions(ExtractContextRevisionsRequest(
        project.project_id, project.database_path, (revision,), "tester")).runs[0]
    assert run.status == ContentExtractionStatus.UNSUPPORTED
    assert run.error_code == "CONTENT_FORMAT_UNSUPPORTED"
    assert app.search_context_content(SearchContextContentRequest(
        project.project_id, project.database_path, "synthetic")).total == 0


def test_cancel_persists_result_and_allows_retry(tmp_path: Path, monkeypatch) -> None:
    app, project, revision = _ready_revision(tmp_path, "brief.txt", b"needle")
    service = app._content_service
    original = service._run_worker
    monkeypatch.setattr(service, "_run_worker", lambda *_: (_ for _ in ()).throw(OperationCancelled()))
    request = ExtractContextRevisionsRequest(project.project_id, project.database_path,
                                             (revision,), "tester")
    with pytest.raises(OperationCancelled):
        app.extract_context_revisions(request)
    runs = app.get_content_extraction_runs(project.project_id, project.database_path, revision)
    assert runs[0].status == ContentExtractionStatus.CANCELLED_AT_SAFE_POINT
    monkeypatch.setattr(service, "_run_worker", original)
    assert app.extract_context_revisions(request).runs[0].status == ContentExtractionStatus.SUCCEEDED


def test_explicit_recovery_requires_confirmation(tmp_path: Path) -> None:
    app, project, revision = _ready_revision(tmp_path, "brief.txt", b"needle")
    request = RecoverInterruptedContentRequest(project.project_id, project.database_path,
                                                "tester", False)
    with pytest.raises(ApplicationError) as failure:
        app.recover_interrupted_content(request)
    assert failure.value.code == "CONTENT_RECOVERY_CONFIRMATION_REQUIRED"
    confirmed = RecoverInterruptedContentRequest(project.project_id, project.database_path,
                                                  "tester", True)
    assert app.recover_interrupted_content(confirmed).recovered_run_ids == ()


def test_chinese_two_character_substring_is_searchable(tmp_path: Path) -> None:
    app, project, revision = _ready_revision(tmp_path, "brief.txt", "项目核心判断".encode("utf-8"))
    app.extract_context_revisions(ExtractContextRevisionsRequest(
        project.project_id, project.database_path, (revision,), "tester"))
    result = app.search_context_content(SearchContextContentRequest(
        project.project_id, project.database_path, "核心"))
    assert result.total == 1
    assert result.hits[0].locator_value == "1"


def test_interrupted_run_recovery_does_not_touch_fixed_bytes(tmp_path: Path) -> None:
    app, project, revision = _ready_revision(tmp_path, "brief.txt", b"needle")
    database = SqlAlchemyProjectDatabase()
    with database.unit_of_work(project.database_path) as uow:
        fixed = uow.context.get_revision(revision)
        content = uow.context.get_content_object(fixed.content_object_id)
        uow.content.add_run(ExtractionRun(
            id="interrupted-run", project_id=project.project_id,
            context_revision_id=revision, input_sha256=content.sha256,
            extractor_name="txt", extractor_version="basic-1",
            config_sha256="0" * 64, status=ContentExtractionStatus.RUNNING,
            actor="tester", correlation_id="interrupted", started_at=datetime.now(timezone.utc),
        ))
        uow.commit()
    before = (project.database_path.parent / content.object_key).read_bytes()
    recovered = app.recover_interrupted_content(RecoverInterruptedContentRequest(
        project.project_id, project.database_path, "tester", True))
    assert recovered.recovered_run_ids == ("interrupted-run",)
    assert app.get_content_extraction_runs(project.project_id, project.database_path,
                                           revision)[0].status == ContentExtractionStatus.FAILED
    assert (project.database_path.parent / content.object_key).read_bytes() == before


def test_open_fixed_preview_uses_original_name_and_refuses_changed_copy(tmp_path: Path) -> None:
    class Opener:
        def __init__(self):
            self.paths = []

        def open(self, path):
            self.paths.append(path)

    opener = Opener()
    app, project, revision = _ready_revision(tmp_path, "brief.txt", b"fixed needle", opener=opener)
    request = OpenContextRevisionRequest(project.project_id, project.database_path, revision)
    result = app.open_context_revision(request)
    assert result.preview_path.name == "brief.txt"
    assert result.preview_path.read_bytes() == b"fixed needle"
    assert opener.paths == [result.preview_path]
    result.preview_path.chmod(0o666)
    result.preview_path.write_bytes(b"edited preview")
    with pytest.raises(ApplicationError) as failure:
        app.open_context_revision(request)
    assert failure.value.code == "CONTENT_PREVIEW_CHANGED"


def test_pre_v23_project_requires_confirmed_upgrade(tmp_path: Path) -> None:
    database_path = tmp_path / "project.sqlite"
    upgrade_database(database_path, "0013_context_pack_events")
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "INSERT INTO projects (id, singleton_key, name, status, workspace_locator, "
            "model_version, created_at, updated_at, workspace_revision, context_revision) "
            "VALUES (?, 1, 'Old', 'READY', ?, 'project-context-v2.1', ?, ?, 0, 0)",
            ("old-project", tmp_path.resolve().as_uri(), now, now),
        )
    app = create_local_application(tmp_path)
    with pytest.raises(ApplicationError) as failure:
        app.search_context_content(SearchContextContentRequest(
            "old-project", database_path, "needle"))
    assert failure.value.code == "PROJECT_UPGRADE_REQUIRED"
