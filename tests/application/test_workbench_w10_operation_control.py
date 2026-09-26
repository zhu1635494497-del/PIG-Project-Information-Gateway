from __future__ import annotations

from pathlib import Path

import pytest

from pig.application import (
    AddWorkspaceInputsRequest,
    CancellationToken,
    CreateProjectRequest,
    ExportWorkspaceItemsRequest,
    GetWorkspaceTreeRequest,
    InspectProjectRecoveryRequest,
    LoadProjectRequest,
    OperationCancelled,
    OperationControl,
    OperationStage,
)
from pig.application.contracts import (
    ImportProjectItemsRequest,
    InspectImportSessionRequest,
)
from pig.application.errors import ApplicationError
from pig.bootstrap import create_local_application
from pig.domain.enums import (
    ErrorCode,
    EventType,
    ImportItemStatus,
    ImportSessionStatus,
    OriginalSnapshotStatus,
    ProjectStatus,
    WorkspaceItemKind,
)
from pig.domain.snapshot_policy import SnapshotImportPolicy
from pig.domain.processing_policy import ProcessingPolicy
from pig.infrastructure.database.provider import SqlAlchemyProjectDatabase


def _project(tmp_path: Path):
    application = create_local_application(tmp_path / "projects")
    project = application.create_project(
        CreateProjectRequest(name="W10 Operation", actor="tester")
    )
    return application, project


def test_operation_progress_is_monotonic_and_cancellation_is_cooperative() -> None:
    snapshots = []
    token = CancellationToken()
    control = OperationControl(callback=snapshots.append, token=token)

    control.start_stage(OperationStage.PREFLIGHT, total_count=2)
    control.advance(count=1, current_item="first")
    control.start_stage(
        OperationStage.SNAPSHOT_COPY,
        total_count=1,
        total_bytes=4,
    )
    control.advance(byte_count=2, current_item="file.txt")
    control.cancel()

    assert [value.sequence for value in snapshots] == sorted(
        value.sequence for value in snapshots
    )
    assert snapshots[-1].cancellation_requested
    assert snapshots[-2].ratio == 0.5
    with pytest.raises(OperationCancelled):
        control.checkpoint()
    with pytest.raises(ValueError):
        control.start_stage(OperationStage.PREFLIGHT)


def test_import_disk_preflight_rejects_before_snapshot_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"resource")
    application, project = _project(tmp_path)
    monkeypatch.setattr(
        application._snapshot_import_service._store,
        "available_space",
        lambda _path: 0,
    )

    with pytest.raises(ApplicationError) as failure:
        application.import_project_items(
            ImportProjectItemsRequest(
                project_id=project.project_id,
                database_path=project.database_path,
                input_paths=(source,),
                actor="tester",
                idempotency_key="disk-preflight",
                policy=SnapshotImportPolicy(minimum_free_space_bytes=1),
            )
        )

    assert failure.value.code == "INSUFFICIENT_DISK_SPACE"
    database = SqlAlchemyProjectDatabase()
    with database.unit_of_work(project.database_path) as uow:
        assert uow.imports.sessions_for_project(project.project_id) == []
        assert uow.projects.get(project.project_id).status == ProjectStatus.CREATED
        events = tuple(uow.processing.events_for_project(project.project_id))
    assert events[-1].event_type == EventType.IMPORT_FAILED
    assert events[-1].error_code == ErrorCode.INTERNAL_ERROR
    assert events[-1].details["failure_code"] == "INSUFFICIENT_DISK_SPACE"
    assert not (project.workspace_path / "originals").exists()


def test_large_input_threshold_emits_a_nonblocking_progress_warning(
    tmp_path: Path,
) -> None:
    source = tmp_path / "warning.txt"
    source.write_bytes(b"warning")
    application, project = _project(tmp_path)
    snapshots = []
    control = OperationControl(callback=snapshots.append)

    result = application.import_project_items(
        ImportProjectItemsRequest(
            project_id=project.project_id,
            database_path=project.database_path,
            input_paths=(source,),
            actor="tester",
            idempotency_key="soft-warning",
            policy=SnapshotImportPolicy(
                minimum_free_space_bytes=0,
                soft_warning_entry_count=1,
                soft_warning_total_size=1,
            ),
        ),
        control=control,
    )

    assert result.accepted_item_count == 1
    assert any(
        value.stage == OperationStage.SNAPSHOT_COPY and value.warning
        for value in snapshots
    )


def test_cancel_during_snapshot_copy_persists_interrupted_state_and_reopens(
    tmp_path: Path,
) -> None:
    source = tmp_path / "large.bin"
    source.write_bytes(b"x" * (2 * 1024 * 1024))
    application, project = _project(tmp_path)
    token = CancellationToken()

    def cancel_after_first_chunk(snapshot) -> None:
        if (
            snapshot.stage == OperationStage.SNAPSHOT_COPY
            and snapshot.completed_bytes >= 64 * 1024
        ):
            token.cancel()

    control = OperationControl(callback=cancel_after_first_chunk, token=token)
    with pytest.raises(OperationCancelled):
        application.import_project_items(
            ImportProjectItemsRequest(
                project_id=project.project_id,
                database_path=project.database_path,
                input_paths=(source,),
                actor="tester",
                idempotency_key="cancel-copy",
                policy=SnapshotImportPolicy(
                    io_chunk_size=64 * 1024,
                    minimum_free_space_bytes=0,
                ),
            ),
            control=control,
        )

    database = SqlAlchemyProjectDatabase()
    with database.unit_of_work(project.database_path) as uow:
        session = uow.imports.sessions_for_project(project.project_id)[0]
        item = uow.imports.items_for_session(session.id)[0]
        snapshot = uow.imports.get_snapshot(item.snapshot_id)
        current_project = uow.projects.get(project.project_id)
        events = tuple(uow.processing.events_for_project(project.project_id))
    assert session.status == ImportSessionStatus.INTERRUPTED
    assert item.status == ImportItemStatus.INTERRUPTED
    assert snapshot.status == OriginalSnapshotStatus.INTERRUPTED
    assert current_project.status == ProjectStatus.FAILED
    assert events[-2].event_type == EventType.IMPORT_INTERRUPTED
    assert not tuple((project.workspace_path / ".staging").rglob("content"))

    reopened = create_local_application(tmp_path / "unused")
    loaded = reopened.load_project(LoadProjectRequest(database_path=project.database_path))
    assert loaded.project.id == project.project_id
    recovery = reopened.inspect_project_recovery(
        InspectProjectRecoveryRequest(
            project_id=project.project_id,
            database_path=project.database_path,
        )
    )
    assert not recovery.recovery_required


def test_cancel_during_structure_inspection_interrupts_pending_add(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    for index in range(20):
        (source / f"file-{index}.txt").write_text(str(index), encoding="utf-8")
    application, project = _project(tmp_path)
    imported = application.import_project_items(
        ImportProjectItemsRequest(
            project_id=project.project_id,
            database_path=project.database_path,
            input_paths=(source,),
            actor="tester",
            idempotency_key="cancel-inspection",
            policy=SnapshotImportPolicy(minimum_free_space_bytes=0),
        )
    )
    token = CancellationToken()

    def cancel_when_inspection_starts(snapshot) -> None:
        if snapshot.stage == OperationStage.STRUCTURE_INSPECTION:
            token.cancel()

    control = OperationControl(callback=cancel_when_inspection_starts, token=token)
    with pytest.raises(OperationCancelled):
        application.inspect_import_session(
            InspectImportSessionRequest(
                project_id=project.project_id,
                database_path=project.database_path,
                import_session_id=imported.import_session_id,
                actor="tester",
            ),
            control=control,
        )

    database = SqlAlchemyProjectDatabase()
    with database.unit_of_work(project.database_path) as uow:
        session = uow.imports.get_session(imported.import_session_id)
        current_project = uow.projects.get(project.project_id)
        workspace = tuple(uow.workspace.items_for_project(project.project_id))
        events = tuple(uow.processing.events_for_project(project.project_id))
    assert session.status == ImportSessionStatus.INTERRUPTED
    assert current_project.status == ProjectStatus.FAILED
    assert workspace == ()
    assert events[-2].event_type == EventType.IMPORT_INTERRUPTED


def _ready_file(tmp_path: Path):
    source = tmp_path / "ready.txt"
    source.write_bytes(b"export-me" * 128 * 1024)
    application, project = _project(tmp_path)
    application.add_workspace_inputs(
        AddWorkspaceInputsRequest(
            project_id=project.project_id,
            database_path=project.database_path,
            input_paths=(source,),
            actor="tester",
            expected_workspace_revision=0,
            snapshot_policy=SnapshotImportPolicy(minimum_free_space_bytes=0),
        )
    )
    tree = application.get_workspace_tree(
        GetWorkspaceTreeRequest(
            project_id=project.project_id,
            database_path=project.database_path,
        )
    )
    item = next(
        value.item
        for value in tree.items
        if value.item.item_kind == WorkspaceItemKind.FILE
    )
    return application, project, item


def test_export_cancel_cleans_staging_and_records_failure(tmp_path: Path) -> None:
    application, project, item = _ready_file(tmp_path)
    destination = tmp_path / "cancelled.txt"
    token = CancellationToken()

    def cancel_during_write(snapshot) -> None:
        if (
            snapshot.stage == OperationStage.EXPORT_WRITE
            and snapshot.completed_bytes > 0
        ):
            token.cancel()

    control = OperationControl(callback=cancel_during_write, token=token)
    with pytest.raises(OperationCancelled):
        application.export_workspace_items(
            ExportWorkspaceItemsRequest(
                project_id=project.project_id,
                database_path=project.database_path,
                workspace_item_ids=(item.id,),
                destination_path=destination,
                actor="tester",
            ),
            control=control,
        )

    assert not destination.exists()
    assert not tuple(tmp_path.glob(".cancelled.txt.*.pig-export.tmp"))
    database = SqlAlchemyProjectDatabase()
    with database.unit_of_work(project.database_path) as uow:
        events = tuple(uow.processing.events_for_project(project.project_id))
    assert events[-1].event_type == EventType.WORKSPACE_EXPORT_FAILED
    assert events[-1].error_code == ErrorCode.EXPORT_FAILED
    assert events[-1].details["failure_code"] == "OPERATION_CANCELLED"


def test_export_disk_preflight_rejects_before_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    application, project, item = _ready_file(tmp_path)
    destination = tmp_path / "no-space.txt"
    monkeypatch.setattr(
        application._workspace_export_service._store,
        "available_space",
        lambda _path: 0,
    )

    with pytest.raises(ApplicationError) as failure:
        application.export_workspace_items(
            ExportWorkspaceItemsRequest(
                project_id=project.project_id,
                database_path=project.database_path,
                workspace_item_ids=(item.id,),
                destination_path=destination,
                actor="tester",
                policy=ProcessingPolicy(minimum_free_space_bytes=1),
            )
        )

    assert failure.value.code == "INSUFFICIENT_DISK_SPACE"
    assert not destination.exists()
    assert not tuple(tmp_path.glob(".no-space.txt.*.pig-export.tmp"))
    database = SqlAlchemyProjectDatabase()
    with database.unit_of_work(project.database_path) as uow:
        events = tuple(uow.processing.events_for_project(project.project_id))
    assert events[-1].event_type == EventType.WORKSPACE_EXPORT_FAILED
    assert events[-1].details["failure_code"] == "INSUFFICIENT_DISK_SPACE"


def test_cancel_requested_during_atomic_publish_is_deferred(tmp_path: Path) -> None:
    application, project, item = _ready_file(tmp_path)
    destination = tmp_path / "published.txt"
    token = CancellationToken()

    def cancel_during_atomic_publish(snapshot) -> None:
        if snapshot.stage == OperationStage.FINALIZING and not snapshot.cancellable:
            token.cancel()

    control = OperationControl(callback=cancel_during_atomic_publish, token=token)
    result = application.export_workspace_items(
        ExportWorkspaceItemsRequest(
            project_id=project.project_id,
            database_path=project.database_path,
            workspace_item_ids=(item.id,),
            destination_path=destination,
            actor="tester",
        ),
        control=control,
    )

    assert token.is_cancellation_requested
    assert result.destination_path == destination
    assert destination.read_bytes() == b"export-me" * 128 * 1024
    database = SqlAlchemyProjectDatabase()
    with database.unit_of_work(project.database_path) as uow:
        events = tuple(uow.processing.events_for_project(project.project_id))
    assert events[-1].event_type == EventType.WORKSPACE_EXPORT_COMPLETED
