from __future__ import annotations

from pathlib import Path
import json

import pytest

from pig.application.contracts import (
    CreateProjectRequest, ImportProjectItemsRequest, InspectImportSessionRequest,
    PromoteWorkspaceItemToContextRequest,
    GetContextPackPlanRequest,
    PreflightContextPackExportRequest, ExecuteContextPackExportRequest,
)
from pig.application.errors import ApplicationError
from pig.application.experience_service import (
    ExperienceEvidenceChoice, ExperienceMutationRequest, ExperienceService,
    ExperienceTransitionRequest,
)
from pig.application.context_pack_plan_service import ContextPackPlanService
from pig.application.context_pack_export_service import ContextPackExportService
from pig.bootstrap import create_local_application
from pig.domain.enums import EventType, ContextPackFormat
from pig.domain.experience_policy import ExperienceKind, ExperienceStatus
from pig.infrastructure.database.provider import SqlAlchemyProjectDatabase


def _ready(tmp_path: Path):
    source = tmp_path / "decision.txt"
    source.write_text("Synthetic decision evidence", encoding="utf-8")
    app = create_local_application(tmp_path / "projects")
    project = app.create_project(CreateProjectRequest(name="Experience", actor="tester"))
    imported = app.import_project_items(ImportProjectItemsRequest(
        project_id=project.project_id, database_path=project.database_path,
        input_paths=(source,), actor="tester"))
    app.inspect_import_session(InspectImportSessionRequest(
        project_id=project.project_id, database_path=project.database_path,
        import_session_id=imported.import_session_id, actor="tester"))
    database = SqlAlchemyProjectDatabase()
    with database.unit_of_work(project.database_path) as uow:
        item = uow.workspace.items_for_project(project.project_id)[0]
    promoted = app.promote_workspace_item_to_context(PromoteWorkspaceItemToContextRequest(
        project_id=project.project_id, database_path=project.database_path,
        workspace_item_id=item.id, actor="tester", expected_workspace_revision=1,
        expected_context_revision=0))
    service = ExperienceService(database=database)
    return project, promoted.item, promoted.capture, service, database


def _create(project, item, capture):
    return ExperienceMutationRequest(
        project_id=project.project_id, database_path=project.database_path,
        actor="tester", expected_context_revision=1, kind=ExperienceKind.JUDGMENT,
        title="Choose supplier B", body="Delivery date is reliable",
        evidence=(ExperienceEvidenceChoice(item.id, capture.context_revision_id),),
    )


def test_human_experience_reopens_and_preserves_correction_history(tmp_path: Path) -> None:
    project, item, capture, service, database = _ready(tmp_path)
    draft = service.create(_create(project, item, capture))
    assert draft.record.status == ExperienceStatus.DRAFT
    assert draft.revision_links[0].context_revision_id == capture.context_revision_id
    with database.unit_of_work(project.database_path) as uow:
        assert uow.projects.get(project.project_id).context_revision == 2
        assert EventType.EXPERIENCE_CREATED in {
            event.event_type for event in uow.processing.events_for_project(project.project_id)}

    confirmed = service.confirm(ExperienceTransitionRequest(
        project.project_id, project.database_path, "tester", 2,
        draft.record.id, 1))
    assert confirmed.record.status == ExperienceStatus.CONFIRMED
    corrected = service.correct(ExperienceMutationRequest(
        project_id=project.project_id, database_path=project.database_path,
        actor="tester", expected_context_revision=3, kind=ExperienceKind.JUDGMENT,
        title="Choose supplier B", body="Corrected delivery date",
        evidence=(ExperienceEvidenceChoice(item.id, capture.context_revision_id),),
        record_id=draft.record.id, expected_record_version=1))
    assert corrected.record.current_version == 2
    assert corrected.record.status == ExperienceStatus.DRAFT
    reopened = service.get(project_id=project.project_id,
                           database_path=project.database_path, record_id=draft.record.id)
    assert [version.body for version in reopened.versions] == [
        "Delivery date is reliable", "Corrected delivery date"]
    assert [change.to_status for change in reopened.state_changes] == [
        ExperienceStatus.DRAFT, ExperienceStatus.CONFIRMED, ExperienceStatus.DRAFT]


def test_stale_action_does_not_write_or_remove_evidence(tmp_path: Path) -> None:
    project, item, capture, service, database = _ready(tmp_path)
    draft = service.create(_create(project, item, capture))
    with pytest.raises(ApplicationError, match="Project Context changed"):
        service.confirm(ExperienceTransitionRequest(
            project.project_id, project.database_path, "tester", 1,
            draft.record.id, 1))
    with database.unit_of_work(project.database_path) as uow:
        assert capture.context_revision_id in uow.experience.referenced_revision_ids(project.project_id)
        assert uow.projects.get(project.project_id).context_revision == 2


def test_selected_experience_extends_bundle_without_changing_legacy_pack(tmp_path: Path) -> None:
    project, item, capture, service, database = _ready(tmp_path)
    draft = service.create(_create(project, item, capture))
    planner = ContextPackPlanService(database=database)
    legacy = planner.get_plan(GetContextPackPlanRequest(
        project_id=project.project_id, database_path=project.database_path))
    assert legacy.manifest_schema_version == "1.0"
    selected = planner.get_plan(GetContextPackPlanRequest(
        project_id=project.project_id, database_path=project.database_path,
        selected_record_ids=(draft.record.id,)))
    assert selected.manifest_schema_version == "2.0"
    value = json.loads(ContextPackExportService._manifest(selected, "synthetic-export"))
    assert value["experience_records"][0]["revision_links"][0]["context_revision_id"] == capture.context_revision_id
    assert value["observed_events"] == []


def test_selected_experience_is_exported_as_reopenable_bundle(tmp_path: Path) -> None:
    project, item, capture, service, _database = _ready(tmp_path)
    draft = service.create(_create(project, item, capture))
    app = create_local_application(tmp_path / "projects")
    target = tmp_path / "bundle"
    preflight = app.preflight_context_pack_export(PreflightContextPackExportRequest(
        project_id=project.project_id, database_path=project.database_path,
        destination_path=target, format=ContextPackFormat.DIRECTORY,
        actor="tester", selected_record_ids=(draft.record.id,),
    ))
    app.execute_context_pack_export(ExecuteContextPackExportRequest(
        project_id=project.project_id, database_path=project.database_path,
        export_id=preflight.export_id, plan_token=preflight.plan_token,
        actor="tester", selected_record_ids=(draft.record.id,),
    ))
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    record = manifest["experience_records"][0]
    assert manifest["schema_version"] == "2.0"
    assert record["id"] == draft.record.id
    assert record["body"] == "Delivery date is reliable"
    assert record["revision_links"][0]["context_revision_id"] == capture.context_revision_id
    assert manifest["entries"][0]["context_revision_id"] == capture.context_revision_id


def test_observed_event_is_linked_without_becoming_human_rationale(tmp_path: Path) -> None:
    project, item, capture, service, database = _ready(tmp_path)
    event = service.list_observed_events(project_id=project.project_id,
                                         database_path=project.database_path)[-1]
    base = _create(project, item, capture)
    request = ExperienceMutationRequest(
        project_id=base.project_id, database_path=base.database_path,
        actor=base.actor, expected_context_revision=base.expected_context_revision,
        kind=base.kind, title=base.title, body=base.body,
        evidence=base.evidence, event_ids=(event.id,),
    )
    detail = service.create(request)
    assert detail.event_links[0].event_id == event.id
    planner = ContextPackPlanService(database=database)
    plan = planner.get_plan(GetContextPackPlanRequest(
        project_id=project.project_id, database_path=project.database_path,
        selected_record_ids=(detail.record.id,)))
    manifest = json.loads(ContextPackExportService._manifest(plan, "synthetic-export"))
    assert manifest["experience_records"][0]["event_ids"] == [event.id]
    assert manifest["observed_events"][0]["id"] == event.id
    assert "details" not in manifest["observed_events"][0]
