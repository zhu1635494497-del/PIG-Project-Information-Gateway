from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

import pytest

from pig.application.contracts import (
    AdvanceContextRevisionRequest,
    ContextItemLifecycleRequest,
    ContextSectionLifecycleRequest,
    CreateContextSectionRequest,
    ExecuteContextRevisionCleanupRequest,
    GetContextItemDetailsRequest,
    GetProjectContextRequest,
    ImportProjectItemsRequest,
    InspectImportSessionRequest,
    OpenWorkspaceItemRequest,
    PlaceContextItemRequest,
    PreflightContextPromotionRequest,
    PreviewContextRevisionCleanupRequest,
    PromoteWorkspaceItemToContextRequest,
    RefreshWorkingArtifactRequest,
    SetContextRevisionProtectionRequest,
    UpsertContextAnnotationRequest,
    CreateProjectRequest,
)
from pig.application.errors import ApplicationError
from pig.bootstrap import create_local_application
from pig.domain.enums import ContextFreshnessStatus, ContextLifecycleStatus, EventType
from pig.infrastructure.database.provider import SqlAlchemyProjectDatabase


class NoopOpener:
    def open(self, path: Path) -> None:
        pass


def _ready(tmp_path: Path, *, materialized: bool = False):
    source = tmp_path / "core.txt"
    source.write_bytes(b"version zero")
    app = create_local_application(tmp_path / "projects", file_opener=NoopOpener())
    project = app.create_project(CreateProjectRequest(name="Context Actions", actor="tester"))
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
    if materialized:
        opened = app.open_workspace_item(OpenWorkspaceItemRequest(
            project_id=project.project_id, database_path=project.database_path,
            workspace_item_id=workspace_item.id, actor="tester",
        ))
    promoted = app.promote_workspace_item_to_context(PromoteWorkspaceItemToContextRequest(
        project_id=project.project_id, database_path=project.database_path,
        workspace_item_id=workspace_item.id, actor="tester",
        expected_workspace_revision=1, expected_context_revision=0,
        purpose="Decision source",
    ))
    return app, project, workspace_item, promoted.item, opened


def test_promote_is_idempotent_and_item_starts_unsectioned(tmp_path: Path) -> None:
    app, project, workspace_item, item, _ = _ready(tmp_path)

    repeated = app.promote_workspace_item_to_context(PromoteWorkspaceItemToContextRequest(
        project_id=project.project_id, database_path=project.database_path,
        workspace_item_id=workspace_item.id, actor="tester",
        expected_workspace_revision=1, expected_context_revision=1,
    ))
    context = app.get_project_context(GetProjectContextRequest(
        project_id=project.project_id, database_path=project.database_path
    ))

    assert repeated.item.id == item.id
    assert repeated.capture is None
    assert context.project.context_revision == 1
    assert context.unsectioned_item_ids == (item.id,)
    assert context.items[0].freshness == ContextFreshnessStatus.CURRENT


def test_promotion_preflight_is_read_only_and_describes_source(tmp_path: Path) -> None:
    source = tmp_path / "preflight.txt"
    source.write_bytes(b"preflight")
    app = create_local_application(tmp_path / "projects", file_opener=NoopOpener())
    project = app.create_project(CreateProjectRequest(name="Preflight", actor="tester"))
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
        item = uow.workspace.items_for_project(project.project_id)[0]

    result = app.preflight_context_promotion(PreflightContextPromotionRequest(
        project_id=project.project_id,
        database_path=project.database_path,
        workspace_item_id=item.id,
        expected_workspace_revision=1,
    ))

    assert result.capture_allowed
    assert result.estimated_size_bytes == len(b"preflight")
    assert result.source_kind.value == "SOURCE"
    assert result.context_revision == 0
    with database.unit_of_work(project.database_path) as uow:
        assert uow.context.items_for_project(project.project_id) == ()
        assert uow.context.revisions_for_project(project.project_id) == ()


def test_promotion_preflight_rejects_a_container_node(tmp_path: Path) -> None:
    source = tmp_path / "container.zip"
    with ZipFile(source, "w") as archive:
        archive.writestr("inside.txt", b"inside")
    app = create_local_application(tmp_path / "projects", file_opener=NoopOpener())
    project = app.create_project(CreateProjectRequest(name="Container Guard", actor="tester"))
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
        container = next(
            value for value in uow.workspace.items_for_project(project.project_id)
            if value.display_name == "container.zip"
        )

    with pytest.raises(ApplicationError) as error:
        app.preflight_context_promotion(PreflightContextPromotionRequest(
            project_id=project.project_id,
            database_path=project.database_path,
            workspace_item_id=container.id,
            expected_workspace_revision=1,
        ))

    assert error.value.code == "CONTEXT_ACTION_INVALID"


def test_multiple_placements_and_section_soft_delete_restore(tmp_path: Path) -> None:
    app, project, _workspace_item, item, _ = _ready(tmp_path)
    first = app.create_context_section(CreateContextSectionRequest(
        project_id=project.project_id, database_path=project.database_path,
        name="Decisions", actor="tester", expected_context_revision=1,
    ))
    second = app.create_context_section(CreateContextSectionRequest(
        project_id=project.project_id, database_path=project.database_path,
        name="Inputs", actor="tester", expected_context_revision=2,
    ))
    app.place_context_item(PlaceContextItemRequest(
        project_id=project.project_id, database_path=project.database_path,
        context_item_id=item.id, context_section_id=first.section.id,
        actor="tester", expected_context_revision=3,
    ))
    app.place_context_item(PlaceContextItemRequest(
        project_id=project.project_id, database_path=project.database_path,
        context_item_id=item.id, context_section_id=second.section.id,
        actor="tester", expected_context_revision=4,
    ))

    app.remove_context_section(ContextSectionLifecycleRequest(
        project_id=project.project_id, database_path=project.database_path,
        context_section_id=first.section.id, actor="tester",
        expected_context_revision=5,
    ))
    one_visible = app.get_project_context(GetProjectContextRequest(
        project_id=project.project_id, database_path=project.database_path
    ))
    assert len(one_visible.items[0].effective_placements) == 1
    app.remove_context_section(ContextSectionLifecycleRequest(
        project_id=project.project_id, database_path=project.database_path,
        context_section_id=second.section.id, actor="tester",
        expected_context_revision=6,
    ))
    unsectioned = app.get_project_context(GetProjectContextRequest(
        project_id=project.project_id, database_path=project.database_path
    ))
    assert unsectioned.unsectioned_item_ids == (item.id,)

    app.restore_context_section(ContextSectionLifecycleRequest(
        project_id=project.project_id, database_path=project.database_path,
        context_section_id=first.section.id, actor="tester",
        expected_context_revision=7,
    ))
    restored = app.get_project_context(GetProjectContextRequest(
        project_id=project.project_id, database_path=project.database_path
    ))
    assert [value.context_section_id for value in restored.items[0].effective_placements] == [first.section.id]


def test_guidance_persists_and_freshness_detects_working_update(tmp_path: Path) -> None:
    app, project, workspace_item, item, _ = _ready(tmp_path)
    annotation = app.upsert_context_annotation(UpsertContextAnnotationRequest(
        project_id=project.project_id, database_path=project.database_path,
        context_item_id=item.id, body="Read the final paragraph first.",
        actor="tester", expected_context_revision=1,
    ))
    opened = app.open_workspace_item(OpenWorkspaceItemRequest(
        project_id=project.project_id, database_path=project.database_path,
        workspace_item_id=workspace_item.id, actor="tester",
    ))
    opened.path.write_bytes(b"workspace changed")
    refreshed = app.refresh_working_artifact(RefreshWorkingArtifactRequest(
        project_id=project.project_id, database_path=project.database_path,
        workspace_item_id=workspace_item.id, actor="tester",
    ))

    details = app.get_context_item_details(GetContextItemDetailsRequest(
        project_id=project.project_id, database_path=project.database_path,
        context_item_id=item.id,
    ))

    assert annotation.created
    assert details.annotations[0].body == "Read the final paragraph first."
    assert details.view.freshness == ContextFreshnessStatus.WORKSPACE_UPDATED
    assert details.view.current_revision.source_observed_sha256 != refreshed.working_artifact.current_sha256


def test_item_remove_and_restore_preserve_revision(tmp_path: Path) -> None:
    app, project, _workspace_item, item, _ = _ready(tmp_path)
    current_revision_id = item.current_context_revision_id
    removed = app.remove_context_item(ContextItemLifecycleRequest(
        project_id=project.project_id, database_path=project.database_path,
        context_item_id=item.id, actor="tester", expected_context_revision=1,
    ))
    assert removed.item.lifecycle_status == ContextLifecycleStatus.REMOVED
    assert app.get_project_context(GetProjectContextRequest(
        project_id=project.project_id, database_path=project.database_path
    )).items == ()

    restored = app.restore_context_item(ContextItemLifecycleRequest(
        project_id=project.project_id, database_path=project.database_path,
        context_item_id=item.id, actor="tester", expected_context_revision=2,
    ))
    assert restored.item.current_context_revision_id == current_revision_id


def test_cleanup_retains_current_and_previous_and_requires_fresh_preview(tmp_path: Path) -> None:
    app, project, workspace_item, item, opened = _ready(tmp_path, materialized=True)
    for expected_revision, payload in ((1, b"version one"), (2, b"version two")):
        opened.path.write_bytes(payload)
        app.advance_context_revision(AdvanceContextRevisionRequest(
            project_id=project.project_id, database_path=project.database_path,
            context_item_id=item.id, actor="tester",
            expected_workspace_revision=1,
            expected_context_revision=expected_revision,
        ))

    preview = app.preview_context_revision_cleanup(PreviewContextRevisionCleanupRequest(
        project_id=project.project_id, database_path=project.database_path, actor="tester"
    ))
    assert len(preview.candidates) == 1
    section = app.create_context_section(CreateContextSectionRequest(
        project_id=project.project_id, database_path=project.database_path,
        name="Changes", actor="tester", expected_context_revision=3,
    ))
    with pytest.raises(ApplicationError) as stale:
        app.execute_context_revision_cleanup(ExecuteContextRevisionCleanupRequest(
            project_id=project.project_id, database_path=project.database_path,
            actor="tester", expected_context_revision=4,
            preview_token=preview.preview_token, confirmed=True,
        ))
    assert stale.value.code == "CONTEXT_CLEANUP_PREVIEW_STALE"

    fresh = app.preview_context_revision_cleanup(PreviewContextRevisionCleanupRequest(
        project_id=project.project_id, database_path=project.database_path, actor="tester"
    ))
    cleaned = app.execute_context_revision_cleanup(ExecuteContextRevisionCleanupRequest(
        project_id=project.project_id, database_path=project.database_path,
        actor="tester", expected_context_revision=section.context_revision,
        preview_token=fresh.preview_token, confirmed=True,
    ))
    assert cleaned.deleted_revision_ids == (fresh.candidates[0].revision_id,)
    details = app.get_context_item_details(GetContextItemDetailsRequest(
        project_id=project.project_id, database_path=project.database_path,
        context_item_id=item.id,
    ))
    assert len([value for value in details.revisions if value.capture_status.value == "READY"]) == 2
    database = SqlAlchemyProjectDatabase()
    with database.unit_of_work(project.database_path) as uow:
        assert EventType.CONTEXT_REVISION_CLEANUP_COMPLETED in {
            value.event_type for value in uow.processing.events_for_project(project.project_id)
        }


def test_manual_protection_excludes_old_revision_from_cleanup(tmp_path: Path) -> None:
    app, project, _workspace_item, item, opened = _ready(tmp_path, materialized=True)
    for expected_revision, payload in ((1, b"one"), (2, b"two")):
        opened.path.write_bytes(payload)
        app.advance_context_revision(AdvanceContextRevisionRequest(
            project_id=project.project_id, database_path=project.database_path,
            context_item_id=item.id, actor="tester", expected_workspace_revision=1,
            expected_context_revision=expected_revision,
        ))
    details = app.get_context_item_details(GetContextItemDetailsRequest(
        project_id=project.project_id, database_path=project.database_path,
        context_item_id=item.id,
    ))
    oldest = details.revisions[0]
    app.set_context_revision_protection(SetContextRevisionProtectionRequest(
        project_id=project.project_id, database_path=project.database_path,
        context_revision_id=oldest.id, protected=True,
        reason="Keep for decision evidence", actor="tester",
        expected_context_revision=3,
    ))
    preview = app.preview_context_revision_cleanup(PreviewContextRevisionCleanupRequest(
        project_id=project.project_id, database_path=project.database_path, actor="tester"
    ))
    assert preview.candidates == ()


def test_context_write_conflict_is_structured_and_logged(tmp_path: Path) -> None:
    app, project, _workspace_item, _item, _ = _ready(tmp_path)

    with pytest.raises(ApplicationError) as conflict:
        app.create_context_section(CreateContextSectionRequest(
            project_id=project.project_id,
            database_path=project.database_path,
            name="Stale write",
            actor="tester",
            expected_context_revision=0,
        ))

    assert conflict.value.code == "CONTEXT_WRITE_CONFLICT"
    database = SqlAlchemyProjectDatabase()
    with database.unit_of_work(project.database_path) as uow:
        events = uow.processing.events_for_project(project.project_id)
    assert EventType.CONTEXT_WRITE_CONFLICT in {value.event_type for value in events}


def test_cleanup_requires_explicit_confirmation(tmp_path: Path) -> None:
    app, project, _workspace_item, _item, _ = _ready(tmp_path)
    preview = app.preview_context_revision_cleanup(
        PreviewContextRevisionCleanupRequest(
            project_id=project.project_id,
            database_path=project.database_path,
            actor="tester",
        )
    )

    with pytest.raises(ApplicationError) as denied:
        app.execute_context_revision_cleanup(ExecuteContextRevisionCleanupRequest(
            project_id=project.project_id,
            database_path=project.database_path,
            actor="tester",
            expected_context_revision=preview.context_revision,
            preview_token=preview.preview_token,
            confirmed=False,
        ))

    assert denied.value.code == "CONTEXT_ACTION_INVALID"
