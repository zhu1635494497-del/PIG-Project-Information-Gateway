from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile

import pytest

from pig.application.contracts import (
    CaptureContextRevisionRequest,
    CreateProjectRequest,
    ImportProjectItemsRequest,
    InspectContextObjectStoreRequest,
    InspectImportSessionRequest,
    OpenWorkspaceItemRequest,
)
from pig.application.errors import ApplicationError
from pig.bootstrap import create_local_application
from pig.domain.entities import ContextItem
from pig.domain.enums import (
    ContextContentObjectStatus,
    ContextLifecycleStatus,
    ContextRevisionCaptureStatus,
    ContextRevisionSourceKind,
    EventType,
)
from pig.infrastructure.database.provider import SqlAlchemyProjectDatabase
from pig.infrastructure.database import models


NOW = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)


class NoopOpener:
    def open(self, path: Path) -> None:
        pass


def _context_ready_file(tmp_path: Path, *, materialize: bool):
    source = tmp_path / "source.txt"
    source.write_bytes(b"original context")
    app = create_local_application(tmp_path / "projects", file_opener=NoopOpener())
    project = app.create_project(CreateProjectRequest(name="Capture", actor="tester"))
    imported = app.import_project_items(ImportProjectItemsRequest(
        project_id=project.project_id, database_path=project.database_path,
        input_paths=(source,), actor="tester",
    ))
    app.inspect_import_session(InspectImportSessionRequest(
        project_id=project.project_id, database_path=project.database_path,
        import_session_id=imported.import_session_id, actor="tester",
    ))
    database = SqlAlchemyProjectDatabase()
    with database.unit_of_work(project.database_path) as uow:
        workspace_item = uow.workspace.items_for_project(project.project_id)[0]
    opened = None
    if materialize:
        opened = app.open_workspace_item(OpenWorkspaceItemRequest(
            project_id=project.project_id, database_path=project.database_path,
            workspace_item_id=workspace_item.id, actor="tester",
        ))
    item = ContextItem(
        id=str(uuid4()), project_id=project.project_id,
        workspace_item_id=workspace_item.id,
        lifecycle_status=ContextLifecycleStatus.ACTIVE,
        created_at=NOW, updated_at=NOW,
    )
    with database.unit_of_work(project.database_path) as uow:
        uow.context.add_item(item)
        uow.commit()
    return app, project, workspace_item, item, opened


def _capture(app, project, item, *, expected_context_revision: int):
    return app.capture_context_revision(CaptureContextRevisionRequest(
        project_id=project.project_id,
        database_path=project.database_path,
        context_item_id=item.id,
        actor="tester",
        expected_workspace_revision=1,
        expected_context_revision=expected_context_revision,
    ))


def test_virtual_item_captures_source_without_creating_working_artifact(tmp_path: Path) -> None:
    app, project, workspace_item, item, _ = _context_ready_file(tmp_path, materialize=False)

    result = _capture(app, project, item, expected_context_revision=0)

    assert result.source_kind == ContextRevisionSourceKind.SOURCE
    assert result.capture_status == ContextRevisionCaptureStatus.READY
    assert (project.workspace_path / result.object_key).read_bytes() == b"original context"
    database = SqlAlchemyProjectDatabase()
    with database.unit_of_work(project.database_path) as uow:
        assert uow.workspace.working_artifact_for_item(workspace_item.id) is None
        revision = uow.context.get_revision(result.context_revision_id)
        assert revision.source_node_id == workspace_item.origin_source_node_id
        assert uow.context.get_item(item.id).current_context_revision_id == revision.id


def test_materialized_item_captures_current_working_bytes_and_deduplicates(tmp_path: Path) -> None:
    app, project, _workspace_item, item, opened = _context_ready_file(tmp_path, materialize=True)
    opened.path.write_bytes(b"edited working bytes")

    first = _capture(app, project, item, expected_context_revision=0)
    second = _capture(app, project, item, expected_context_revision=1)

    assert first.source_kind == ContextRevisionSourceKind.WORKING
    assert (project.workspace_path / first.object_key).read_bytes() == b"edited working bytes"
    assert second.object_reused is True
    assert second.content_object_id == first.content_object_id
    database = SqlAlchemyProjectDatabase()
    with database.unit_of_work(project.database_path) as uow:
        assert len(uow.context.content_objects_for_project(project.project_id)) == 1
        assert len(uow.context.revisions_for_item(item.id)) == 2
        assert EventType.CONTEXT_CONTENT_OBJECT_REUSED in {
            event.event_type for event in uow.processing.events_for_project(project.project_id)
        }


def test_capture_rejects_stale_workspace_revision_without_revision(tmp_path: Path) -> None:
    app, project, _workspace_item, item, _ = _context_ready_file(tmp_path, materialize=False)

    with pytest.raises(ApplicationError) as raised:
        app.capture_context_revision(CaptureContextRevisionRequest(
            project_id=project.project_id, database_path=project.database_path,
            context_item_id=item.id, actor="tester",
            expected_workspace_revision=0, expected_context_revision=0,
        ))
    assert raised.value.code == "WORKSPACE_CHANGED_DURING_CAPTURE"


def test_object_store_scan_marks_missing_and_reports_orphan(tmp_path: Path) -> None:
    app, project, _workspace_item, item, _ = _context_ready_file(tmp_path, materialize=False)
    captured = _capture(app, project, item, expected_context_revision=0)
    object_path = project.workspace_path / captured.object_key
    object_path.unlink()
    orphan = project.workspace_path / "context" / "objects" / "ff" / ("f" * 64)
    orphan.parent.mkdir(parents=True, exist_ok=True)
    orphan.write_bytes(b"orphan")

    result = app.inspect_context_object_store(InspectContextObjectStoreRequest(
        project_id=project.project_id, database_path=project.database_path, actor="tester"
    ))

    assert result.orphan_keys == (orphan.relative_to(project.workspace_path).as_posix(),)
    assert result.missing_object_ids == (captured.content_object_id,)
    database = SqlAlchemyProjectDatabase()
    with database.unit_of_work(project.database_path) as uow:
        assert uow.context.get_content_object(captured.content_object_id).availability_status == ContextContentObjectStatus.MISSING


def test_missing_working_file_creates_failed_capture_revision(tmp_path: Path) -> None:
    app, project, _workspace_item, item, opened = _context_ready_file(tmp_path, materialize=True)
    opened.path.unlink()

    with pytest.raises(ApplicationError) as raised:
        _capture(app, project, item, expected_context_revision=0)

    assert raised.value.code == "CONTEXT_CAPTURE_SOURCE_MISSING"
    database = SqlAlchemyProjectDatabase()
    with database.unit_of_work(project.database_path) as uow:
        revision = uow.context.revisions_for_item(item.id)[0]
        assert revision.capture_status == ContextRevisionCaptureStatus.FAILED
        assert revision.error_code == "CONTEXT_CAPTURE_SOURCE_MISSING"
        assert uow.projects.get(project.project_id).context_revision == 0


def test_capacity_gate_blocks_before_revision_creation(tmp_path: Path) -> None:
    app, project, _workspace_item, item, _ = _context_ready_file(tmp_path, materialize=False)
    database = SqlAlchemyProjectDatabase()
    with database.unit_of_work(project.database_path) as uow:
        row = uow.session.get(models.ContextSettingsModel, project.project_id)
        row.minimum_free_bytes = 10**18
        uow.commit()

    with pytest.raises(ApplicationError) as raised:
        _capture(app, project, item, expected_context_revision=0)

    assert raised.value.code == "CONTEXT_CAPTURE_CAPACITY_BLOCKED"
    with database.unit_of_work(project.database_path) as uow:
        assert uow.context.revisions_for_item(item.id) == ()
        assert uow.processing.events_for_project(project.project_id)[-1].event_type == EventType.CONTEXT_CAPTURE_BLOCKED_BY_CAPACITY


def test_virtual_archive_child_streams_directly_from_source(tmp_path: Path) -> None:
    archive = tmp_path / "nested.zip"
    with ZipFile(archive, "w") as output:
        output.writestr("folder/core.txt", b"nested core bytes")
    app = create_local_application(tmp_path / "projects", file_opener=NoopOpener())
    project = app.create_project(CreateProjectRequest(name="Nested", actor="tester"))
    imported = app.import_project_items(ImportProjectItemsRequest(
        project_id=project.project_id, database_path=project.database_path,
        input_paths=(archive,), actor="tester",
    ))
    app.inspect_import_session(InspectImportSessionRequest(
        project_id=project.project_id, database_path=project.database_path,
        import_session_id=imported.import_session_id, actor="tester",
    ))
    database = SqlAlchemyProjectDatabase()
    with database.unit_of_work(project.database_path) as uow:
        workspace_item = next(
            value for value in uow.workspace.items_for_project(project.project_id)
            if value.display_name == "core.txt"
        )
        item = ContextItem(
            id=str(uuid4()), project_id=project.project_id,
            workspace_item_id=workspace_item.id,
            lifecycle_status=ContextLifecycleStatus.ACTIVE,
            created_at=NOW, updated_at=NOW,
        )
        uow.context.add_item(item)
        uow.commit()

    result = _capture(app, project, item, expected_context_revision=0)

    assert result.source_kind == ContextRevisionSourceKind.SOURCE
    assert (project.workspace_path / result.object_key).read_bytes() == b"nested core bytes"
    with database.unit_of_work(project.database_path) as uow:
        assert uow.workspace.working_artifact_for_item(workspace_item.id) is None
