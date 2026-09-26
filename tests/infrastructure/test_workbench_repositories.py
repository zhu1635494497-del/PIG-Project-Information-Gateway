from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from pig.domain.entities import (
    ImportSession,
    OriginalArtifact,
    OriginalSnapshot,
    OriginalSnapshotEntry,
    ProcessingEvent,
    Project,
    WorkingArtifact,
    WorkspaceItem,
    WorkspacePlacement,
)
from pig.domain.enums import (
    ArtifactIntegrityStatus,
    EventSeverity,
    EventType,
    ImportSessionStatus,
    OriginalSnapshotStatus,
    OriginalSnapshotEntryKind,
    ProjectStatus,
    SourceKind,
    WorkingContentStatus,
    WorkspaceItemKind,
    WorkspaceItemLifecycleStatus,
    WorkspaceMaterializationStatus,
)
from pig.domain.exceptions import InvariantViolationError
from pig.domain.model_version import WORKBENCH_MODEL_VERSION


NOW = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
SHA_A = "a" * 64
SHA_B = "b" * 64


def _project() -> Project:
    return Project(
        id="project-1",
        name="Workbench Project",
        description=None,
        status=ProjectStatus.CREATED,
        workspace_locator="file:///D:/PIG/projects/project-1",
        model_version=WORKBENCH_MODEL_VERSION,
        created_at=NOW,
        updated_at=NOW,
    )


def _folder(item_id: str, name: str) -> WorkspaceItem:
    return WorkspaceItem(
        id=item_id,
        project_id="project-1",
        item_kind=WorkspaceItemKind.FOLDER,
        display_name=name,
        lifecycle_status=WorkspaceItemLifecycleStatus.ACTIVE,
        materialization_status=WorkspaceMaterializationStatus.VIRTUAL,
        created_at=NOW,
        updated_at=NOW,
    )


def test_workbench_repository_round_trip_preserves_core_objects(uow_factory) -> None:
    session = ImportSession(
        id="import-1",
        project_id="project-1",
        status=ImportSessionStatus.QUEUED,
        requested_item_count=1,
        accepted_item_count=0,
        failed_item_count=0,
        requested_at=NOW,
        actor="tester",
        correlation_id="correlation-1",
    )
    snapshot = OriginalSnapshot(
        id="snapshot-1",
        project_id="project-1",
        import_session_id=session.id,
        input_kind=SourceKind.FILE,
        original_display_name="报价.zip",
        external_locator_at_import="file:///D:/input/quote.zip",
        status=OriginalSnapshotStatus.COPYING,
        created_at=NOW,
    )
    original = OriginalArtifact(
        id="original-1",
        project_id="project-1",
        snapshot_id=snapshot.id,
        storage_key="originals/original-1/content",
        size=128,
        sha256=SHA_A,
        integrity_status=ArtifactIntegrityStatus.VERIFIED,
        created_at=NOW,
    )
    root = _folder("workspace-root", "项目资料")
    file_item = WorkspaceItem(
        id="workspace-file",
        project_id="project-1",
        item_kind=WorkspaceItemKind.FILE,
        display_name="报价.xlsx",
        lifecycle_status=WorkspaceItemLifecycleStatus.ACTIVE,
        materialization_status=WorkspaceMaterializationStatus.MATERIALIZED,
        created_at=NOW,
        updated_at=NOW,
    )
    working = WorkingArtifact(
        id="working-1",
        project_id="project-1",
        workspace_item_id=file_item.id,
        storage_key="working/workspace-file/quote.xlsx",
        baseline_size=256,
        baseline_sha256=SHA_B,
        current_size=256,
        current_sha256=SHA_B,
        content_status=WorkingContentStatus.CLEAN,
        materialized_at=NOW,
        updated_at=NOW,
    )
    event = ProcessingEvent(
        id="event-1",
        event_type=EventType.WORKSPACE_ITEM_ADDED,
        project_id="project-1",
        import_session_id=session.id,
        snapshot_id=snapshot.id,
        workspace_item_id=file_item.id,
        working_artifact_id=working.id,
        actor="tester",
        occurred_at=NOW,
        severity=EventSeverity.INFO,
        correlation_id="correlation-1",
    )

    with uow_factory() as uow:
        uow.projects.add(_project())
        uow.imports.add_session(session)
        uow.imports.add_snapshot(snapshot)
        uow.imports.add_original_artifact(original)
        uow.workspace.add_item(
            root,
            WorkspacePlacement(
                workspace_item_id=root.id,
                project_id=root.project_id,
                parent_workspace_item_id=None,
                ordinal=0,
                updated_at=NOW,
            ),
        )
        uow.workspace.add_item(
            file_item,
            WorkspacePlacement(
                workspace_item_id=file_item.id,
                project_id=file_item.project_id,
                parent_workspace_item_id=root.id,
                ordinal=0,
                updated_at=NOW,
            ),
        )
        uow.workspace.add_working_artifact(working)
        uow.processing.append_event(event)
        uow.commit()

    with uow_factory() as uow:
        assert uow.projects.get("project-1") == _project()
        assert uow.imports.get_session(session.id) == session
        assert uow.imports.get_snapshot(snapshot.id) == snapshot
        assert uow.imports.get_original_artifact(original.id) == original
        assert uow.workspace.get_item(root.id) == root
        assert uow.workspace.get_placement(file_item.id).parent_workspace_item_id == root.id
        assert uow.workspace.working_artifact_for_item(file_item.id) == working
        assert uow.processing.events_for_project("project-1") == [event]


def test_recent_project_events_are_bounded_and_chronological(uow_factory) -> None:
    events = [
        ProcessingEvent(
            id=f"event-{index}",
            event_type=EventType.WORKSPACE_ITEM_ADDED,
            project_id="project-1",
            actor="tester",
            occurred_at=NOW + timedelta(seconds=index),
            severity=EventSeverity.INFO,
            correlation_id=f"correlation-{index}",
        )
        for index in range(4)
    ]
    with uow_factory() as uow:
        uow.projects.add(_project())
        for value in events:
            uow.processing.append_event(value)
        uow.commit()

    with uow_factory() as uow:
        assert uow.processing.recent_events_for_project(
            "project-1", limit=2
        ) == events[-2:]


def test_bounded_bulk_writes_match_single_row_repository_results(uow_factory) -> None:
    session = ImportSession(
        id="import-1",
        project_id="project-1",
        status=ImportSessionStatus.QUEUED,
        requested_item_count=2,
        accepted_item_count=0,
        failed_item_count=0,
        requested_at=NOW,
        actor="tester",
        correlation_id="correlation-1",
    )
    snapshots = [
        OriginalSnapshot(
            id=f"snapshot-{mode}",
            project_id="project-1",
            import_session_id=session.id,
            input_kind=SourceKind.FOLDER,
            original_display_name=mode,
            external_locator_at_import=f"file:///D:/{mode}",
            status=OriginalSnapshotStatus.COPYING,
            created_at=NOW,
        )
        for mode in ("single", "bulk")
    ]

    def values(mode: str):
        artifact = OriginalArtifact(
            id=f"artifact-{mode}",
            project_id="project-1",
            snapshot_id=f"snapshot-{mode}",
            storage_key=f"originals/artifact-{mode}/content",
            size=4,
            sha256=SHA_A,
            integrity_status=ArtifactIntegrityStatus.VERIFIED,
            created_at=NOW,
        )
        entries = [
            OriginalSnapshotEntry(
                id=f"root-{mode}",
                project_id="project-1",
                snapshot_id=f"snapshot-{mode}",
                kind=OriginalSnapshotEntryKind.FOLDER,
                original_name="root",
                ordinal=0,
                created_at=NOW,
            ),
            OriginalSnapshotEntry(
                id=f"file-{mode}",
                project_id="project-1",
                snapshot_id=f"snapshot-{mode}",
                parent_entry_id=f"root-{mode}",
                artifact_id=artifact.id,
                kind=OriginalSnapshotEntryKind.FILE,
                original_name="file.txt",
                ordinal=0,
                created_at=NOW,
            ),
        ]
        return artifact, entries

    with uow_factory() as uow:
        uow.projects.add(_project())
        uow.imports.add_session(session)
        for snapshot in snapshots:
            uow.imports.add_snapshot(snapshot)
        single_artifact, single_entries = values("single")
        uow.imports.add_original_artifact(single_artifact)
        for entry in single_entries:
            uow.imports.add_snapshot_entry(entry)
        bulk_artifact, bulk_entries = values("bulk")
        uow.imports.add_original_artifacts([bulk_artifact])
        uow.imports.add_snapshot_entries(bulk_entries)
        single_events = [
            ProcessingEvent(
                id=f"single-event-{index}",
                event_type=EventType.SNAPSHOT_READY,
                project_id="project-1",
                actor="tester",
                occurred_at=NOW + timedelta(seconds=index),
                severity=EventSeverity.INFO,
                correlation_id="single",
            )
            for index in range(2)
        ]
        bulk_events = [
            ProcessingEvent(
                id=f"bulk-event-{index}",
                event_type=EventType.SNAPSHOT_READY,
                project_id="project-1",
                actor="tester",
                occurred_at=NOW + timedelta(seconds=index + 2),
                severity=EventSeverity.INFO,
                correlation_id="bulk",
            )
            for index in range(2)
        ]
        for event in single_events:
            uow.processing.append_event(event)
        uow.processing.append_events(bulk_events)
        uow.commit()

    with uow_factory() as uow:
        single = uow.imports.entries_for_snapshot("snapshot-single")
        bulk = uow.imports.entries_for_snapshot("snapshot-bulk")
        normalize = lambda values: [
            (value.kind, value.original_name, value.ordinal, value.parent_entry_id is None)
            for value in values
        ]
        assert normalize(single) == normalize(bulk)
        assert len(uow.processing.events_for_project("project-1")) == 4


def test_bulk_snapshot_failure_rolls_back_the_whole_unit_of_work(uow_factory) -> None:
    session = ImportSession(
        id="import-1",
        project_id="project-1",
        status=ImportSessionStatus.QUEUED,
        requested_item_count=1,
        accepted_item_count=0,
        failed_item_count=0,
        requested_at=NOW,
        actor="tester",
        correlation_id="correlation-1",
    )
    snapshot = OriginalSnapshot(
        id="snapshot-1",
        project_id="project-1",
        import_session_id=session.id,
        input_kind=SourceKind.FOLDER,
        original_display_name="rollback",
        external_locator_at_import="file:///D:/rollback",
        status=OriginalSnapshotStatus.COPYING,
        created_at=NOW,
    )
    with uow_factory() as uow:
        uow.projects.add(_project())
        uow.imports.add_session(session)
        uow.imports.add_snapshot(snapshot)
        uow.commit()

    artifact = OriginalArtifact(
        id="artifact-rollback",
        project_id="project-1",
        snapshot_id=snapshot.id,
        storage_key="originals/artifact-rollback/content",
        size=4,
        sha256=SHA_A,
        integrity_status=ArtifactIntegrityStatus.VERIFIED,
        created_at=NOW,
    )
    duplicate_entries = [
        OriginalSnapshotEntry(
            id="root-rollback",
            project_id="project-1",
            snapshot_id=snapshot.id,
            kind=OriginalSnapshotEntryKind.FOLDER,
            original_name="root",
            ordinal=0,
            created_at=NOW,
        ),
        *[
            OriginalSnapshotEntry(
                id=f"duplicate-{index}",
                project_id="project-1",
                snapshot_id=snapshot.id,
                parent_entry_id="root-rollback",
                artifact_id=artifact.id,
                kind=OriginalSnapshotEntryKind.FILE,
                original_name=f"duplicate-{index}.txt",
                ordinal=0,
                created_at=NOW,
            )
            for index in range(2)
        ],
    ]
    with pytest.raises(IntegrityError):
        with uow_factory() as uow:
            uow.imports.add_original_artifacts([artifact])
            uow.imports.add_snapshot_entries(duplicate_entries)
            uow.commit()

    with uow_factory() as uow:
        assert uow.imports.original_artifacts_for_snapshot(snapshot.id) == []
        assert uow.imports.entries_for_snapshot(snapshot.id) == []


def test_workspace_move_rejects_cycle_and_preserves_old_placement(uow_factory) -> None:
    root = _folder("root", "Root")
    child = _folder("child", "Child")
    with uow_factory() as uow:
        uow.projects.add(_project())
        uow.workspace.add_item(
            root,
            WorkspacePlacement(
                workspace_item_id=root.id,
                project_id=root.project_id,
                parent_workspace_item_id=None,
                ordinal=0,
                updated_at=NOW,
            ),
        )
        uow.workspace.add_item(
            child,
            WorkspacePlacement(
                workspace_item_id=child.id,
                project_id=child.project_id,
                parent_workspace_item_id=root.id,
                ordinal=0,
                updated_at=NOW,
            ),
        )
        uow.commit()

    with pytest.raises(InvariantViolationError):
        with uow_factory() as uow:
            uow.workspace.move_item(
                root.id,
                new_parent_id=child.id,
                new_ordinal=0,
                updated_at=NOW,
            )

    with uow_factory() as uow:
        assert uow.workspace.get_placement(root.id).parent_workspace_item_id is None


def test_database_trigger_rejects_workspace_cycle(uow_factory) -> None:
    root = _folder("root", "Root")
    child = _folder("child", "Child")
    with uow_factory() as uow:
        uow.projects.add(_project())
        uow.workspace.add_item(
            root,
            WorkspacePlacement(
                workspace_item_id=root.id,
                project_id=root.project_id,
                parent_workspace_item_id=None,
                ordinal=0,
                updated_at=NOW,
            ),
        )
        uow.workspace.add_item(
            child,
            WorkspacePlacement(
                workspace_item_id=child.id,
                project_id=child.project_id,
                parent_workspace_item_id=root.id,
                ordinal=0,
                updated_at=NOW,
            ),
        )
        uow.commit()

    with pytest.raises(IntegrityError):
        with uow_factory() as uow:
            uow.session.execute(
                text(
                    "UPDATE workspace_placements "
                    "SET parent_workspace_item_id = 'child' "
                    "WHERE workspace_item_id = 'root'"
                )
            )
            uow.commit()


def test_workbench_unit_of_work_rolls_back_without_commit(uow_factory) -> None:
    with uow_factory() as uow:
        uow.projects.add(_project())

    with uow_factory() as uow:
        assert uow.projects.get("project-1") is None


def test_database_rejects_original_artifact_identity_rewrite(
    uow_factory,
) -> None:
    with uow_factory() as uow:
        uow.projects.add(_project())
        uow.imports.add_session(
            ImportSession(
                id="import-1",
                project_id="project-1",
                status=ImportSessionStatus.QUEUED,
                requested_item_count=1,
                accepted_item_count=0,
                failed_item_count=0,
                requested_at=NOW,
                actor="tester",
                correlation_id="correlation-1",
            )
        )
        uow.imports.add_snapshot(
            OriginalSnapshot(
                id="snapshot-1",
                project_id="project-1",
                import_session_id="import-1",
                input_kind=SourceKind.FILE,
                original_display_name="input.txt",
                external_locator_at_import="file:///D:/input.txt",
                status=OriginalSnapshotStatus.COPYING,
                created_at=NOW,
            )
        )
        uow.imports.add_original_artifact(
            OriginalArtifact(
                id="original-1",
                project_id="project-1",
                snapshot_id="snapshot-1",
                storage_key="originals/original-1/content",
                size=1,
                sha256=SHA_A,
                integrity_status=ArtifactIntegrityStatus.VERIFIED,
                created_at=NOW,
            )
        )
        uow.commit()

    with pytest.raises(IntegrityError):
        with uow_factory() as uow:
            uow.session.execute(
                text(
                    "UPDATE original_artifacts SET sha256 = :sha256 "
                    "WHERE id = 'original-1'"
                ),
                {"sha256": SHA_B},
            )
            uow.commit()
