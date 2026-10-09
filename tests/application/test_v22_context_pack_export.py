"""Synthetic Context Pack publication, safety, and history acceptance."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from pig.application.contracts import (
    AdvanceContextRevisionRequest, CancelContextPackPreflightRequest, ContextPackRevisionChoice,
    CreateContextSectionRequest, CreateProjectRequest, ExecuteContextPackExportRequest,
    GetContextPackExportsRequest, GetWorkspaceTreeRequest, ImportProjectItemsRequest,
    InspectImportSessionRequest, PlaceContextItemRequest,
    MaterializeWorkspaceItemRequest, RecoverInterruptedContextPackExportsRequest,
    PreflightContextPackExportRequest, PromoteWorkspaceItemToContextRequest,
    PreviewContextRevisionCleanupRequest,
    UpsertContextAnnotationRequest,
)
from pig.application.errors import ApplicationError
from pig.application.operation_control import OperationControl
from pig.bootstrap import create_local_application
from pig.domain.enums import ContextPackExportStatus, ContextPackFormat, EventType
from pig.infrastructure.database.provider import SqlAlchemyProjectDatabase


def _project(tmp_path: Path, payload: bytes = b"approved project brief"):
    source = tmp_path / "brief.txt"
    source.write_bytes(payload)
    app = create_local_application(tmp_path / "projects")
    project = app.create_project(CreateProjectRequest(name="Pack Project", actor="tester"))
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
        expected_context_revision=0, purpose="Decision material",
    ))
    section = app.create_context_section(CreateContextSectionRequest(
        project_id=project.project_id, database_path=project.database_path,
        name="Decision", description="Read this first", actor="tester",
        expected_context_revision=1,
    ))
    app.create_context_section(CreateContextSectionRequest(
        project_id=project.project_id, database_path=project.database_path,
        name="Empty", actor="tester", expected_context_revision=2,
    ))
    app.place_context_item(PlaceContextItemRequest(
        project_id=project.project_id, database_path=project.database_path,
        context_item_id=promoted.item.id, context_section_id=section.section.id,
        actor="tester", expected_context_revision=3,
    ))
    app.upsert_context_annotation(UpsertContextAnnotationRequest(
        project_id=project.project_id, database_path=project.database_path,
        context_item_id=promoted.item.id, body="Human reading guide",
        actor="tester", expected_context_revision=4,
    ))
    return app, project, promoted


def _preflight(app, project, target, format):
    return app.preflight_context_pack_export(PreflightContextPackExportRequest(
        project_id=project.project_id, database_path=project.database_path,
        destination_path=target, format=format, actor="tester",
    ))


def _execute(app, project, preflight, *, control=None):
    return app.execute_context_pack_export(ExecuteContextPackExportRequest(
        project_id=project.project_id, database_path=project.database_path,
        export_id=preflight.export_id, plan_token=preflight.plan_token,
        actor="tester",
    ), control=control)


@pytest.mark.parametrize("format", (ContextPackFormat.DIRECTORY, ContextPackFormat.ZIP))
def test_offline_pack_contains_exact_revision_and_restart_safe_history(tmp_path: Path, format) -> None:
    app, project, promoted = _project(tmp_path)
    target = tmp_path / ("handoff" if format == ContextPackFormat.DIRECTORY else "handoff.zip")
    preflight = _preflight(app, project, target, format)
    result = _execute(app, project, preflight)
    assert result.export.status == ContextPackExportStatus.SUCCEEDED
    if format == ContextPackFormat.DIRECTORY:
        manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
        readme = (target / "README.md").read_text(encoding="utf-8")
        payload = (target / manifest["entries"][0]["relative_path"]).read_bytes()
    else:
        with zipfile.ZipFile(target) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            readme = archive.read("README.md").decode("utf-8")
            payload = archive.read(manifest["entries"][0]["relative_path"])
            recipient = tmp_path / "independent-recipient"
            archive.extractall(recipient)
        detached_manifest = json.loads((recipient / "manifest.json").read_text(encoding="utf-8"))
        for packaged in detached_manifest["entries"]:
            received = (recipient / packaged["relative_path"]).read_bytes()
            assert hashlib.sha256(received).hexdigest() == packaged["sha256"]
    assert manifest["export_id"] == preflight.export_id
    assert [section["name"] for section in manifest["sections"]] == ["Decision", "Empty"]
    assert manifest["entries"][0]["context_revision_id"] == promoted.capture.context_revision_id
    assert hashlib.sha256(payload).hexdigest() == manifest["entries"][0]["sha256"]
    assert b"approved project brief" == payload
    assert "Human reading guide" in readme
    assert "No selected files" in readme
    reopened = create_local_application(tmp_path / "projects")
    history = reopened.get_context_pack_exports(GetContextPackExportsRequest(
        project_id=project.project_id, database_path=project.database_path,
    ))
    assert len(history.exports) == 1 and history.exports[0].status == ContextPackExportStatus.SUCCEEDED
    with SqlAlchemyProjectDatabase().unit_of_work(project.database_path) as uow:
        assert len(uow.context_packs.entries_for_export(preflight.export_id)) == 1
        assert len(uow.context_packs.sections_for_export(preflight.export_id)) == 2
        assert uow.context_packs.successful_revision_ids(project.project_id) == frozenset({
            promoted.capture.context_revision_id,
        })
        events = {value.event_type for value in uow.processing.events_for_project(project.project_id)}
        assert {EventType.CONTEXT_PACK_EXPORT_REQUESTED, EventType.CONTEXT_PACK_EXPORT_PREFLIGHTED,
                EventType.CONTEXT_PACK_EXPORT_STARTED, EventType.CONTEXT_PACK_EXPORT_COMPLETED} <= events


def test_pack_conflict_and_one_use_token(tmp_path: Path) -> None:
    app, project, _ = _project(tmp_path)
    target = tmp_path / "handoff"
    preflight = _preflight(app, project, target, ContextPackFormat.DIRECTORY)
    target.mkdir()
    with pytest.raises(ApplicationError) as failed:
        _execute(app, project, preflight)
    assert failed.value.code == "CONTEXT_PACK_DESTINATION_EXISTS"
    assert app.get_context_pack_exports(GetContextPackExportsRequest(
        project_id=project.project_id, database_path=project.database_path,
    )).exports[0].status == ContextPackExportStatus.FAILED
    with pytest.raises(ApplicationError) as used:
        _execute(app, project, preflight)
    assert used.value.code == "CONTEXT_PACK_TOKEN_USED"


def test_pack_cancel_and_corrupt_object_never_publish_or_protect(tmp_path: Path) -> None:
    app, project, promoted = _project(tmp_path)
    cancelled_target = tmp_path / "cancelled"
    preflight = _preflight(app, project, cancelled_target, ContextPackFormat.DIRECTORY)
    control = OperationControl()
    control.cancel()
    with pytest.raises(ApplicationError) as cancelled:
        _execute(app, project, preflight, control=control)
    assert cancelled.value.code == "OPERATION_CANCELLED"
    assert not cancelled_target.exists()
    assert not tuple(tmp_path.glob("*.pig-pack.tmp"))
    with SqlAlchemyProjectDatabase().unit_of_work(project.database_path) as uow:
        assert uow.context_packs.get_export(preflight.export_id).status == ContextPackExportStatus.CANCELLED_AT_SAFE_POINT
        assert uow.context_packs.entries_for_export(preflight.export_id) == ()
        object_id = promoted.capture.content_object_id
        content = uow.context.get_content_object(object_id)
    object_path = project.database_path.parent.joinpath(*content.object_key.split("/"))
    object_path.write_bytes(b"tampered")
    with pytest.raises(ApplicationError) as bad_preflight:
        _preflight(app, project, tmp_path / "corrupt", ContextPackFormat.ZIP)
    assert bad_preflight.value.code == "CONTEXT_PACK_CONTENT_INVALID"
    assert not (tmp_path / "corrupt").exists()
    history = app.get_context_pack_exports(GetContextPackExportsRequest(
        project_id=project.project_id, database_path=project.database_path,
    ))
    assert history.exports[-1].status == ContextPackExportStatus.FAILED


def test_pack_destination_inside_project_is_denied(tmp_path: Path) -> None:
    app, project, _ = _project(tmp_path)
    with pytest.raises(ApplicationError) as denied:
        _preflight(app, project, project.database_path.parent / "internal", ContextPackFormat.DIRECTORY)
    assert denied.value.code == "CONTEXT_PACK_DESTINATION_INVALID"


def test_historical_revision_requires_confirmation_and_remains_exact(tmp_path: Path) -> None:
    app, project, promoted = _project(tmp_path)
    with SqlAlchemyProjectDatabase().unit_of_work(project.database_path) as uow:
        workspace_item_id = uow.context.get_item(promoted.item.id).workspace_item_id
        workspace_revision = uow.projects.get(project.project_id).workspace_revision
    working = app.materialize_workspace_item(MaterializeWorkspaceItemRequest(
        project_id=project.project_id, database_path=project.database_path,
        workspace_item_id=workspace_item_id, actor="tester",
    ))
    working.path.write_bytes(b"new working material")
    app.advance_context_revision(AdvanceContextRevisionRequest(
        project_id=project.project_id, database_path=project.database_path,
        context_item_id=promoted.item.id, actor="tester",
        expected_workspace_revision=workspace_revision, expected_context_revision=5,
    ))
    choice = (ContextPackRevisionChoice(
        context_item_id=promoted.item.id,
        context_revision_id=promoted.capture.context_revision_id,
    ),)
    target = tmp_path / "historical"
    first = app.preflight_context_pack_export(PreflightContextPackExportRequest(
        project_id=project.project_id, database_path=project.database_path,
        destination_path=target, format=ContextPackFormat.DIRECTORY,
        actor="tester", revision_choices=choice,
    ))
    assert first.plan.warning_item_ids == (promoted.item.id,)
    with pytest.raises(ApplicationError) as needs_confirmation:
        app.execute_context_pack_export(ExecuteContextPackExportRequest(
            project_id=project.project_id, database_path=project.database_path,
            export_id=first.export_id, plan_token=first.plan_token,
            actor="tester", revision_choices=choice,
        ))
    assert needs_confirmation.value.code == "CONTEXT_PACK_CONFIRMATION_REQUIRED"
    second = app.preflight_context_pack_export(PreflightContextPackExportRequest(
        project_id=project.project_id, database_path=project.database_path,
        destination_path=target, format=ContextPackFormat.DIRECTORY,
        actor="tester", revision_choices=choice,
    ))
    app.execute_context_pack_export(ExecuteContextPackExportRequest(
        project_id=project.project_id, database_path=project.database_path,
        export_id=second.export_id, plan_token=second.plan_token,
        actor="tester", revision_choices=choice, confirm_outdated=True,
    ))
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    assert (target / manifest["entries"][0]["relative_path"]).read_bytes() == b"approved project brief"
    working.path.write_bytes(b"third version")
    app.advance_context_revision(AdvanceContextRevisionRequest(
        project_id=project.project_id, database_path=project.database_path,
        context_item_id=promoted.item.id, actor="tester",
        expected_workspace_revision=workspace_revision, expected_context_revision=6,
    ))
    cleanup = app.preview_context_revision_cleanup(PreviewContextRevisionCleanupRequest(
        project_id=project.project_id, database_path=project.database_path,
        actor="tester",
    ))
    assert promoted.capture.context_revision_id not in {value.revision_id for value in cleanup.candidates}


def test_preflight_is_invalidated_by_context_change_and_corrupt_bytes(tmp_path: Path) -> None:
    app, project, promoted = _project(tmp_path)
    target = tmp_path / "stale"
    preflight = _preflight(app, project, target, ContextPackFormat.DIRECTORY)
    app.create_context_section(CreateContextSectionRequest(
        project_id=project.project_id, database_path=project.database_path,
        name="Later", actor="tester", expected_context_revision=5,
    ))
    with pytest.raises(ApplicationError) as stale:
        _execute(app, project, preflight)
    assert stale.value.code == "CONTEXT_PACK_PLAN_STALE"
    assert not target.exists()

    clean = _preflight(app, project, target, ContextPackFormat.DIRECTORY)
    with SqlAlchemyProjectDatabase().unit_of_work(project.database_path) as uow:
        content = uow.context.get_content_object(promoted.capture.content_object_id)
    project.database_path.parent.joinpath(*content.object_key.split("/")).write_bytes(b"tampered")
    with pytest.raises(ApplicationError) as corrupt:
        _execute(app, project, clean)
    assert corrupt.value.code == "CONTEXT_PACK_CONTENT_INVALID"
    assert not target.exists()


def test_interrupted_run_is_visible_and_explicitly_recovered(tmp_path: Path) -> None:
    app, project, _ = _project(tmp_path)
    preflight = _preflight(app, project, tmp_path / "interrupted", ContextPackFormat.DIRECTORY)
    with SqlAlchemyProjectDatabase().unit_of_work(project.database_path) as uow:
        uow.context_packs.update_export_status(
            preflight.export_id, ContextPackExportStatus.PREFLIGHTED,
            ContextPackExportStatus.RUNNING, updated_at=uow.context_packs.get_export(preflight.export_id).updated_at,
            started_at=uow.context_packs.get_export(preflight.export_id).updated_at,
        )
        uow.commit()
    recovered = app.recover_interrupted_context_pack_exports(RecoverInterruptedContextPackExportsRequest(
        project_id=project.project_id, database_path=project.database_path,
        actor="tester", confirmed=True,
    ))
    assert recovered.recovered_export_ids == (preflight.export_id,)
    assert recovered.external_paths_to_review == ()
    with SqlAlchemyProjectDatabase().unit_of_work(project.database_path) as uow:
        assert uow.context_packs.get_export(preflight.export_id).status == ContextPackExportStatus.FAILED
        assert uow.context_packs.entries_for_export(preflight.export_id) == ()


def test_user_can_cancel_preflight_without_publishing(tmp_path: Path) -> None:
    app, project, _ = _project(tmp_path)
    target = tmp_path / "not-delivered"
    preflight = _preflight(app, project, target, ContextPackFormat.DIRECTORY)
    cancelled = app.cancel_context_pack_preflight(CancelContextPackPreflightRequest(
        project_id=project.project_id, database_path=project.database_path,
        export_id=preflight.export_id, plan_token=preflight.plan_token,
        actor="tester",
    ))
    assert cancelled.status == ContextPackExportStatus.CANCELLED_AT_SAFE_POINT
    assert not target.exists()
    with pytest.raises(ApplicationError) as used:
        _execute(app, project, preflight)
    assert used.value.code == "CONTEXT_PACK_TOKEN_USED"


def test_same_named_files_remain_distinct_and_pack_once_each(tmp_path: Path) -> None:
    app, project, original = _project(tmp_path)
    other_folder = tmp_path / "other"
    other_folder.mkdir()
    other = other_folder / "brief.txt"
    other.write_bytes(b"a different approved brief")
    imported = app.import_project_items(ImportProjectItemsRequest(
        project_id=project.project_id, database_path=project.database_path,
        input_paths=(other,), actor="tester",
    ))
    app.inspect_import_session(InspectImportSessionRequest(
        project_id=project.project_id, database_path=project.database_path,
        import_session_id=imported.import_session_id, actor="tester",
    ))
    tree = app.get_workspace_tree(GetWorkspaceTreeRequest(
        project_id=project.project_id, database_path=project.database_path,
    ))
    second = next(value.item for value in tree.items if value.item.id != original.item.workspace_item_id)
    app.promote_workspace_item_to_context(PromoteWorkspaceItemToContextRequest(
        project_id=project.project_id, database_path=project.database_path,
        workspace_item_id=second.id, actor="tester",
        expected_workspace_revision=tree.workspace_revision, expected_context_revision=5,
    ))
    target = tmp_path / "same-name.zip"
    preflight = _preflight(app, project, target, ContextPackFormat.ZIP)
    assert len(preflight.plan.entries) == 2
    result = _execute(app, project, preflight)
    assert result.export.status == ContextPackExportStatus.SUCCEEDED
    with zipfile.ZipFile(target) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert len({value["relative_path"] for value in manifest["entries"]}) == 2
        payloads = {archive.read(value["relative_path"]) for value in manifest["entries"]}
        assert payloads == {b"approved project brief", b"a different approved brief"}


def test_large_file_streams_with_progress(tmp_path: Path) -> None:
    payload = b"x" * (12 * 1024 * 1024)
    app, project, _ = _project(tmp_path, payload)
    target = tmp_path / "large.zip"
    preflight = _preflight(app, project, target, ContextPackFormat.ZIP)
    snapshots = []
    control = OperationControl(callback=snapshots.append)
    _execute(app, project, preflight, control=control)
    assert any(value.completed_bytes >= len(payload) for value in snapshots)
    with zipfile.ZipFile(target) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert archive.read(manifest["entries"][0]["relative_path"]) == payload


def test_preflight_hash_is_cancellable_and_records_outcome(tmp_path: Path) -> None:
    app, project, _ = _project(tmp_path, b"v" * (3 * 1024 * 1024))
    progress = []
    cancelled_once = False

    def cancel_after_first_chunk(snapshot):
        nonlocal cancelled_once
        progress.append(snapshot)
        if snapshot.completed_bytes > 0 and not cancelled_once:
            cancelled_once = True
            control.cancel()

    control = OperationControl(callback=cancel_after_first_chunk)
    with pytest.raises(ApplicationError) as cancelled:
        app.preflight_context_pack_export(PreflightContextPackExportRequest(
            project_id=project.project_id, database_path=project.database_path,
            destination_path=tmp_path / "not-published",
            format=ContextPackFormat.DIRECTORY, actor="tester",
        ), control=control)
    assert cancelled.value.code == "OPERATION_CANCELLED"
    assert progress and any(value.completed_bytes > 0 for value in progress)
    history = app.get_context_pack_exports(GetContextPackExportsRequest(
        project_id=project.project_id, database_path=project.database_path,
    ))
    assert history.exports[-1].status == ContextPackExportStatus.CANCELLED_AT_SAFE_POINT
