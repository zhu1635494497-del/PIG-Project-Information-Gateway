"""V2.1.5 synthetic acceptance across large Working and nested Virtual sources."""

from __future__ import annotations

import hashlib
from pathlib import Path
from zipfile import ZipFile

import pytest

from pig.application.contracts import (
    AdvanceContextRevisionRequest,
    CreateContextSectionRequest,
    CreateProjectRequest,
    GetContextItemDetailsRequest,
    GetProjectContextRequest,
    GetWorkspaceTreeRequest,
    ImportProjectItemsRequest,
    InspectImportSessionRequest,
    MaterializeWorkspaceItemRequest,
    PreflightContextPromotionRequest,
    PromoteWorkspaceItemToContextRequest,
    RefreshWorkingArtifactRequest,
    UpsertContextAnnotationRequest,
)
from pig.application.errors import ApplicationError
from pig.application.operation_control import (
    CancellationToken,
    OperationCancelled,
    OperationControl,
    OperationStage,
)
from pig.bootstrap import create_local_application
from pig.domain.enums import (
    ContextFreshnessStatus,
    ContextRevisionCaptureStatus,
    ContextRevisionSourceKind,
    EventType,
)
from pig.infrastructure.database import models
from pig.infrastructure.database.provider import SqlAlchemyProjectDatabase


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def test_large_working_and_nested_virtual_context_survive_restart(tmp_path: Path) -> None:
    source = tmp_path / "large-report.txt"
    block = bytes(range(256)) * 4096
    with source.open("wb") as stream:
        for _ in range(80):
            stream.write(block)
    original_sha256 = _sha256(source)
    archive = tmp_path / "nested.zip"
    with ZipFile(archive, "w") as output:
        output.writestr("mail/attachment/core.txt", b"nested context bytes")

    application = create_local_application(tmp_path / "projects")
    project = application.create_project(
        CreateProjectRequest(name="V215 synthetic", actor="acceptance")
    )
    imported = application.import_project_items(ImportProjectItemsRequest(
        project_id=project.project_id, database_path=project.database_path,
        input_paths=(source, archive), actor="acceptance",
    ))
    assert imported.accepted_item_count == 2
    inspected = application.inspect_import_session(InspectImportSessionRequest(
        project_id=project.project_id, database_path=project.database_path,
        import_session_id=imported.import_session_id, actor="acceptance",
    ))
    assert inspected.error_count == 0
    tree = application.get_workspace_tree(GetWorkspaceTreeRequest(
        project_id=project.project_id, database_path=project.database_path
    ))
    large = next(value for value in tree.items if value.item.display_name == source.name)
    nested = next(value for value in tree.items if value.item.display_name == "core.txt")
    assert nested.working_artifact is None
    assert large.source_node is not None and nested.source_node is not None

    working = application.materialize_workspace_item(MaterializeWorkspaceItemRequest(
        project_id=project.project_id, database_path=project.database_path,
        workspace_item_id=large.item.id, actor="acceptance",
    ))
    with working.path.open("r+b") as stream:
        stream.write(b"X")
    captured = application.promote_workspace_item_to_context(
        PromoteWorkspaceItemToContextRequest(
            project_id=project.project_id, database_path=project.database_path,
            workspace_item_id=large.item.id, actor="acceptance",
            expected_workspace_revision=tree.workspace_revision,
            expected_context_revision=0,
        )
    )
    assert captured.capture.source_kind == ContextRevisionSourceKind.WORKING
    assert captured.capture.size_bytes == 80 * 1024 * 1024
    with source.open("rb") as stream:
        assert stream.read(1) != b"X"
    assert _sha256(source) == original_sha256
    virtual = application.promote_workspace_item_to_context(
        PromoteWorkspaceItemToContextRequest(
            project_id=project.project_id, database_path=project.database_path,
            workspace_item_id=nested.item.id, actor="acceptance",
            expected_workspace_revision=tree.workspace_revision,
            expected_context_revision=1,
        )
    )
    assert virtual.capture.source_kind == ContextRevisionSourceKind.SOURCE
    assert (project.workspace_path / virtual.capture.object_key).read_bytes() == b"nested context bytes"
    with SqlAlchemyProjectDatabase().unit_of_work(project.database_path) as uow:
        assert uow.workspace.working_artifact_for_item(nested.item.id) is None
        assert uow.context.get_revision(virtual.capture.context_revision_id).source_node_id == nested.source_node.id

    section = application.create_context_section(CreateContextSectionRequest(
        project_id=project.project_id, database_path=project.database_path,
        name="Decisions", actor="acceptance", expected_context_revision=2,
    ))
    with pytest.raises(ApplicationError) as conflict:
        application.create_context_section(CreateContextSectionRequest(
            project_id=project.project_id, database_path=project.database_path,
            name="Stale", actor="acceptance", expected_context_revision=2,
        ))
    assert conflict.value.code == "CONTEXT_WRITE_CONFLICT"
    application.upsert_context_annotation(UpsertContextAnnotationRequest(
        project_id=project.project_id, database_path=project.database_path,
        context_item_id=captured.item.id,
        body="Read the approved version first.", actor="acceptance",
        expected_context_revision=3,
    ))
    with working.path.open("r+b") as stream:
        stream.write(b"Y")
    application.refresh_working_artifact(RefreshWorkingArtifactRequest(
        project_id=project.project_id, database_path=project.database_path,
        workspace_item_id=large.item.id, actor="acceptance",
    ))
    details = application.get_context_item_details(GetContextItemDetailsRequest(
        project_id=project.project_id, database_path=project.database_path,
        context_item_id=captured.item.id,
    ))
    assert details.view.freshness == ContextFreshnessStatus.WORKSPACE_UPDATED
    assert details.view.current_revision.id == captured.capture.context_revision_id
    advanced = application.advance_context_revision(AdvanceContextRevisionRequest(
        project_id=project.project_id, database_path=project.database_path,
        context_item_id=captured.item.id, actor="acceptance",
        expected_workspace_revision=tree.workspace_revision,
        expected_context_revision=4,
    ))
    assert advanced.context_revision_id != captured.capture.context_revision_id

    reopened = create_local_application(tmp_path / "projects")
    context = reopened.get_project_context(GetProjectContextRequest(
        project_id=project.project_id, database_path=project.database_path
    ))
    assert context.project.context_revision == 5
    assert [value.name for value in context.sections] == [section.section.name]
    assert len(context.items) == 2
    reopened_details = reopened.get_context_item_details(GetContextItemDetailsRequest(
        project_id=project.project_id, database_path=project.database_path,
        context_item_id=captured.item.id,
    ))
    assert reopened_details.annotations[0].body == "Read the approved version first."
    assert reopened_details.view.freshness == ContextFreshnessStatus.CURRENT
    assert reopened_details.view.current_revision.id == advanced.context_revision_id
    assert len(reopened_details.revisions) == 2
    assert _sha256(source) == original_sha256


def test_capacity_preflight_and_execution_block_without_revision(tmp_path: Path) -> None:
    source = tmp_path / "small.txt"
    source.write_bytes(b"capacity check")
    application = create_local_application(tmp_path / "projects")
    project = application.create_project(
        CreateProjectRequest(name="Capacity acceptance", actor="acceptance")
    )
    imported = application.import_project_items(ImportProjectItemsRequest(
        project_id=project.project_id, database_path=project.database_path,
        input_paths=(source,), actor="acceptance",
    ))
    application.inspect_import_session(InspectImportSessionRequest(
        project_id=project.project_id, database_path=project.database_path,
        import_session_id=imported.import_session_id, actor="acceptance",
    ))
    tree = application.get_workspace_tree(GetWorkspaceTreeRequest(
        project_id=project.project_id, database_path=project.database_path
    ))
    with SqlAlchemyProjectDatabase().unit_of_work(project.database_path) as uow:
        settings = uow.session.get(models.ContextSettingsModel, project.project_id)
        settings.minimum_free_bytes = 10**18
        uow.commit()
    item_id = tree.items[0].item.id
    preflight = application.preflight_context_promotion(PreflightContextPromotionRequest(
        project_id=project.project_id, database_path=project.database_path,
        workspace_item_id=item_id,
        expected_workspace_revision=tree.workspace_revision,
    ))
    assert not preflight.capture_allowed
    assert preflight.blocking_code == "CONTEXT_CAPTURE_CAPACITY_BLOCKED"
    with pytest.raises(ApplicationError) as blocked:
        application.promote_workspace_item_to_context(PromoteWorkspaceItemToContextRequest(
            project_id=project.project_id, database_path=project.database_path,
            workspace_item_id=item_id, actor="acceptance",
            expected_workspace_revision=tree.workspace_revision,
            expected_context_revision=0,
        ))
    assert blocked.value.code == "CONTEXT_CAPTURE_CAPACITY_BLOCKED"
    with SqlAlchemyProjectDatabase().unit_of_work(project.database_path) as uow:
        assert uow.context.revisions_for_project(project.project_id) == ()
        assert uow.projects.get(project.project_id).context_revision == 0


def test_cancel_at_capture_safe_point_leaves_no_published_revision(tmp_path: Path) -> None:
    source = tmp_path / "cancel.txt"
    source.write_bytes(b"keep original bytes")
    application = create_local_application(tmp_path / "projects")
    project = application.create_project(
        CreateProjectRequest(name="Cancel acceptance", actor="acceptance")
    )
    imported = application.import_project_items(ImportProjectItemsRequest(
        project_id=project.project_id, database_path=project.database_path,
        input_paths=(source,), actor="acceptance",
    ))
    application.inspect_import_session(InspectImportSessionRequest(
        project_id=project.project_id, database_path=project.database_path,
        import_session_id=imported.import_session_id, actor="acceptance",
    ))
    tree = application.get_workspace_tree(GetWorkspaceTreeRequest(
        project_id=project.project_id, database_path=project.database_path
    ))
    token = CancellationToken()

    def request_cancel_at_capture_start(snapshot) -> None:
        if snapshot.stage == OperationStage.CONTEXT_CAPTURE:
            token.cancel()

    control = OperationControl(callback=request_cancel_at_capture_start, token=token)
    with pytest.raises(OperationCancelled):
        application.promote_workspace_item_to_context(
            PromoteWorkspaceItemToContextRequest(
                project_id=project.project_id, database_path=project.database_path,
                workspace_item_id=tree.items[0].item.id, actor="acceptance",
                expected_workspace_revision=tree.workspace_revision,
                expected_context_revision=0,
            ),
            control=control,
        )
    with SqlAlchemyProjectDatabase().unit_of_work(project.database_path) as uow:
        revisions = uow.context.revisions_for_project(project.project_id)
        assert len(revisions) == 1
        assert revisions[0].capture_status == ContextRevisionCaptureStatus.CANCELLED_AT_SAFE_POINT
        assert uow.context.get_item(revisions[0].context_item_id).current_context_revision_id is None
        assert uow.projects.get(project.project_id).context_revision == 0
        assert any(
            event.event_type == EventType.CONTEXT_CAPTURE_CANCELLED
            for event in uow.processing.events_for_project(project.project_id)
        )
    assert source.read_bytes() == b"keep original bytes"
