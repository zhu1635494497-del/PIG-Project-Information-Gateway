from __future__ import annotations

import os
from pathlib import Path

import pytest

from pig.application import CreateProjectRequest, ExportWorkspaceItemsRequest
from pig.application.contracts import (
    ImportProjectItemsRequest,
    InspectImportSessionRequest,
    MaterializeWorkspaceItemRequest,
)
from pig.application.errors import ApplicationError
from pig.application.working_file_service import WorkingFileService
from pig.bootstrap import create_local_application
from pig.domain.enums import (
    EventType,
    WorkingContentStatus,
    WorkspaceItemKind,
    WorkspaceMaterializationStatus,
)
from pig.infrastructure.database.provider import SqlAlchemyProjectDatabase


def _import_project(tmp_path: Path, source: Path):
    application = create_local_application(tmp_path / "projects")
    project = application.create_project(
        CreateProjectRequest(name="W10 Export", actor="tester")
    )
    imported = application.import_project_items(
        ImportProjectItemsRequest(
            project_id=project.project_id,
            database_path=project.database_path,
            input_paths=(source,),
            actor="tester",
            idempotency_key="w10-export",
        )
    )
    application.inspect_import_session(
        InspectImportSessionRequest(
            project_id=project.project_id,
            database_path=project.database_path,
            import_session_id=imported.import_session_id,
            actor="tester",
        )
    )
    database = SqlAlchemyProjectDatabase()
    with database.unit_of_work(project.database_path) as uow:
        records = tuple(uow.workspace.read_records_for_project(project.project_id))
    return application, project, records


def test_virtual_folder_export_streams_originals_without_materializing_working_files(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    (source / "nested" / "empty").mkdir(parents=True)
    for index in range(20):
        (source / "nested" / f"file-{index:02d}.txt").write_text(
            f"value-{index}", encoding="utf-8"
        )
    application, project, records = _import_project(tmp_path, source)
    root = next(
        record
        for record in records
        if record.item.item_kind == WorkspaceItemKind.FOLDER
        and record.placement.parent_workspace_item_id is None
    )

    destination = tmp_path / "deliverables" / "source"
    destination.parent.mkdir()
    result = application.export_workspace_items(
        ExportWorkspaceItemsRequest(
            project_id=project.project_id,
            database_path=project.database_path,
            workspace_item_ids=(root.item.id,),
            destination_path=destination,
            actor="tester",
        )
    )

    assert result.entry_count == 20
    assert (destination / "nested" / "empty").is_dir()
    assert (destination / "nested" / "file-19.txt").read_text(
        encoding="utf-8"
    ) == "value-19"
    database = SqlAlchemyProjectDatabase()
    with database.unit_of_work(project.database_path) as uow:
        items = tuple(uow.workspace.items_for_project(project.project_id))
        assert all(
            uow.workspace.working_artifact_for_item(item.id) is None
            for item in items
            if item.item_kind == WorkspaceItemKind.FILE
        )
        assert all(
            item.materialization_status
            == WorkspaceMaterializationStatus.VIRTUAL
            for item in items
            if item.item_kind == WorkspaceItemKind.FILE
        )


def test_unchanged_working_file_export_uses_stat_hint_without_refresh_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.txt"
    source.write_bytes(b"stable")
    application, project, records = _import_project(tmp_path, source)
    item = records[0].item
    application.materialize_workspace_item(
        MaterializeWorkspaceItemRequest(
            project_id=project.project_id,
            database_path=project.database_path,
            workspace_item_id=item.id,
            actor="tester",
        )
    )

    def unexpected_refresh(self, request):
        raise AssertionError("unchanged Working File should not be pre-hashed")

    monkeypatch.setattr(WorkingFileService, "refresh", unexpected_refresh)
    destination = tmp_path / "stable-export.txt"
    application.export_workspace_items(
        ExportWorkspaceItemsRequest(
            project_id=project.project_id,
            database_path=project.database_path,
            workspace_item_ids=(item.id,),
            destination_path=destination,
            actor="tester",
        )
    )
    assert destination.read_bytes() == b"stable"


def test_same_stat_content_change_is_rejected_and_staging_is_cleaned(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.txt"
    source.write_bytes(b"aaaa")
    application, project, records = _import_project(tmp_path, source)
    item = records[0].item
    materialized = application.materialize_workspace_item(
        MaterializeWorkspaceItemRequest(
            project_id=project.project_id,
            database_path=project.database_path,
            workspace_item_id=item.id,
            actor="tester",
        )
    )
    before = materialized.path.stat()
    materialized.path.write_bytes(b"bbbb")
    os.utime(
        materialized.path,
        ns=(before.st_atime_ns, before.st_mtime_ns),
    )
    destination = tmp_path / "stealth-export.txt"

    with pytest.raises(ApplicationError) as failure:
        application.export_workspace_items(
            ExportWorkspaceItemsRequest(
                project_id=project.project_id,
                database_path=project.database_path,
                workspace_item_ids=(item.id,),
                destination_path=destination,
                actor="tester",
            )
        )

    assert failure.value.code == "EXPORT_FAILED"
    assert not destination.exists()
    assert not tuple(tmp_path.glob(".stealth-export.txt.*.pig-export.tmp"))
    database = SqlAlchemyProjectDatabase()
    with database.unit_of_work(project.database_path) as uow:
        events = tuple(uow.processing.events_for_project(project.project_id))
    assert events[-1].event_type == EventType.WORKSPACE_EXPORT_FAILED


@pytest.mark.parametrize("replacement", ["missing", "directory"])
def test_missing_or_unreadable_working_file_is_persisted_and_export_fails(
    tmp_path: Path, replacement: str
) -> None:
    source = tmp_path / "source.txt"
    source.write_bytes(b"content")
    application, project, records = _import_project(tmp_path, source)
    item = records[0].item
    materialized = application.materialize_workspace_item(
        MaterializeWorkspaceItemRequest(
            project_id=project.project_id,
            database_path=project.database_path,
            workspace_item_id=item.id,
            actor="tester",
        )
    )
    materialized.path.unlink()
    if replacement == "directory":
        materialized.path.mkdir()

    with pytest.raises(ApplicationError) as failure:
        application.export_workspace_items(
            ExportWorkspaceItemsRequest(
                project_id=project.project_id,
                database_path=project.database_path,
                workspace_item_ids=(item.id,),
                destination_path=tmp_path / f"{replacement}.txt",
                actor="tester",
            )
        )

    assert failure.value.code == "EXPORT_FAILED"
    database = SqlAlchemyProjectDatabase()
    with database.unit_of_work(project.database_path) as uow:
        artifact = uow.workspace.working_artifact_for_item(item.id)
    assert artifact is not None
    assert artifact.content_status == (
        WorkingContentStatus.MISSING
        if replacement == "missing"
        else WorkingContentStatus.UNREADABLE
    )
