"""V2.2.1 read-only plan and relational export-history contract."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from pig.application.contracts import (
    AdvanceContextRevisionRequest,
    ContextPackRevisionChoice,
    CreateContextSectionRequest,
    CreateProjectRequest,
    GetContextPackPlanRequest,
    GetProjectContextRequest,
    GetWorkspaceTreeRequest,
    ImportProjectItemsRequest,
    InspectImportSessionRequest,
    MaterializeWorkspaceItemRequest,
    PlaceContextItemRequest,
    PromoteWorkspaceItemToContextRequest,
    UpsertContextAnnotationRequest,
)
from pig.application.errors import ApplicationError
from pig.bootstrap import create_local_application
from pig.domain import entities, enums
from pig.domain.exceptions import InvariantViolationError
from pig.infrastructure.database.provider import SqlAlchemyProjectDatabase


NOW = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)


def _id() -> str:
    return str(uuid4())


def _ready_project(tmp_path: Path):
    source = tmp_path / "brief.txt"
    source.write_bytes(b"first version")
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
    item = tree.items[0].item
    promoted = app.promote_workspace_item_to_context(PromoteWorkspaceItemToContextRequest(
        project_id=project.project_id, database_path=project.database_path,
        workspace_item_id=item.id, actor="tester",
        expected_workspace_revision=tree.workspace_revision,
        expected_context_revision=0, purpose="Approved brief",
    ))
    return app, project, tree, item, promoted


def test_plan_reads_exact_revision_sections_and_guidance_without_writes(tmp_path: Path) -> None:
    app, project, tree, workspace_item, promoted = _ready_project(tmp_path)
    section = app.create_context_section(CreateContextSectionRequest(
        project_id=project.project_id, database_path=project.database_path,
        name="Decision", description="Key material", actor="tester",
        expected_context_revision=1,
    ))
    empty_section = app.create_context_section(CreateContextSectionRequest(
        project_id=project.project_id, database_path=project.database_path,
        name="Background", description="No selected material", actor="tester",
        expected_context_revision=2,
    ))
    app.place_context_item(PlaceContextItemRequest(
        project_id=project.project_id, database_path=project.database_path,
        context_item_id=promoted.item.id, context_section_id=section.section.id,
        actor="tester", expected_context_revision=3,
    ))
    app.upsert_context_annotation(UpsertContextAnnotationRequest(
        project_id=project.project_id, database_path=project.database_path,
        context_item_id=promoted.item.id, body="Read before delivery",
        actor="tester", expected_context_revision=4,
    ))
    working = app.materialize_workspace_item(MaterializeWorkspaceItemRequest(
        project_id=project.project_id, database_path=project.database_path,
        workspace_item_id=workspace_item.id, actor="tester",
    ))
    working.path.write_bytes(b"second version")
    advanced = app.advance_context_revision(AdvanceContextRevisionRequest(
        project_id=project.project_id, database_path=project.database_path,
        context_item_id=promoted.item.id, actor="tester",
        expected_workspace_revision=tree.workspace_revision,
        expected_context_revision=5,
    ))
    request = GetContextPackPlanRequest(
        project_id=project.project_id, database_path=project.database_path,
        revision_choices=(ContextPackRevisionChoice(
            context_item_id=promoted.item.id,
            context_revision_id=promoted.capture.context_revision_id,
        ),),
    )
    plan = app.get_context_pack_plan(request)
    assert plan.context_revision == 6
    assert plan.manifest_schema_version == "1.0"
    assert tuple(value.name for value in plan.sections) == ("Decision", "Background")
    assert plan.sections[1].source_section_id == empty_section.section.id
    assert len(plan.entries) == 1
    entry = plan.entries[0]
    assert entry.context_revision_id == promoted.capture.context_revision_id
    assert entry.context_revision_id != advanced.context_revision_id
    assert entry.section_ids == (section.section.id,)
    assert entry.guidance_body == "Read before delivery"
    assert entry.purpose == "Approved brief"
    assert entry.relative_path.startswith(f"files/{promoted.item.id}/")
    assert len(plan.plan_fingerprint) == 64
    assert app.get_context_pack_plan(request).plan_fingerprint == plan.plan_fingerprint
    assert app.get_project_context(GetProjectContextRequest(
        project_id=project.project_id, database_path=project.database_path,
    )).project.context_revision == 6
    with SqlAlchemyProjectDatabase().unit_of_work(project.database_path) as uow:
        assert uow.context_packs.exports_for_project(project.project_id) == ()
    with pytest.raises(ApplicationError):
        app.get_context_pack_plan(GetContextPackPlanRequest(
            project_id=project.project_id, database_path=project.database_path,
            revision_choices=(ContextPackRevisionChoice(
                context_item_id=promoted.item.id, context_revision_id=_id()
            ),),
        ))


def test_pack_history_round_trip_and_same_item_revision_fk(tmp_path: Path) -> None:
    app, project, _tree, _workspace_item, promoted = _ready_project(tmp_path)
    plan = app.get_context_pack_plan(GetContextPackPlanRequest(
        project_id=project.project_id, database_path=project.database_path,
    ))
    export_id, entry_id, section_id = _id(), _id(), _id()
    with SqlAlchemyProjectDatabase().unit_of_work(project.database_path) as uow:
        uow.context_packs.add_export(entities.ContextPackExport(
            id=export_id, project_id=project.project_id,
            format=enums.ContextPackFormat.DIRECTORY,
            status=enums.ContextPackExportStatus.PENDING,
            destination_locator=str(tmp_path / "handoff"), actor="tester",
            correlation_id=_id(), captured_context_revision=plan.context_revision,
            manifest_schema_version=plan.manifest_schema_version,
            plan_fingerprint=plan.plan_fingerprint, entry_count=1,
            total_bytes=plan.total_bytes, created_at=NOW, updated_at=NOW,
        ))
        assert not uow.context_packs.successful_revision_ids(project.project_id)
        with pytest.raises(InvariantViolationError):
            uow.context_packs.add_entry(entities.ContextPackEntry(
                id=entry_id, project_id=project.project_id, export_id=export_id,
                context_item_id=promoted.item.id,
                context_revision_id=promoted.capture.context_revision_id,
                ordinal=0, relative_path=plan.entries[0].relative_path,
                display_name="brief.txt", size_bytes=plan.entries[0].size_bytes,
                sha256=plan.entries[0].sha256, created_at=NOW,
            ))
        uow.context_packs.update_export_status(
            export_id, enums.ContextPackExportStatus.PENDING,
            enums.ContextPackExportStatus.PREFLIGHTED, updated_at=NOW,
        )
        uow.context_packs.update_export_status(
            export_id, enums.ContextPackExportStatus.PREFLIGHTED,
            enums.ContextPackExportStatus.RUNNING, updated_at=NOW, started_at=NOW,
        )
        uow.context_packs.update_export_status(
            export_id, enums.ContextPackExportStatus.RUNNING,
            enums.ContextPackExportStatus.SUCCEEDED, updated_at=NOW,
            finished_at=NOW, published_sha256="a" * 64,
        )
        uow.context_packs.add_entry(entities.ContextPackEntry(
            id=entry_id, project_id=project.project_id, export_id=export_id,
            context_item_id=promoted.item.id,
            context_revision_id=promoted.capture.context_revision_id,
            ordinal=0, relative_path=plan.entries[0].relative_path,
            display_name="brief.txt", size_bytes=plan.entries[0].size_bytes,
            sha256=plan.entries[0].sha256, created_at=NOW,
            guidance_body_snapshot="Frozen guidance",
        ))
        uow.context_packs.add_section(entities.ContextPackSection(
            id=section_id, project_id=project.project_id, export_id=export_id,
            source_section_id=None, name_snapshot="Unsectioned", ordinal=0,
            is_unsectioned=True, created_at=NOW,
        ))
        uow.context_packs.add_placement(entities.ContextPackPlacement(
            id=_id(), project_id=project.project_id, export_id=export_id,
            entry_id=entry_id, section_id=section_id, ordinal=0,
            created_at=NOW,
        ))
        uow.commit()
    with SqlAlchemyProjectDatabase().unit_of_work(project.database_path) as uow:
        assert uow.context_packs.get_export(export_id).status == enums.ContextPackExportStatus.SUCCEEDED
        assert uow.context_packs.entries_for_export(export_id)[0].guidance_body_snapshot == "Frozen guidance"
        assert len(uow.context_packs.sections_for_export(export_id)) == 1
        assert len(uow.context_packs.placements_for_export(export_id)) == 1
    with SqlAlchemyProjectDatabase().unit_of_work(project.database_path) as uow:
        assert uow.context_packs.successful_revision_ids(project.project_id) == frozenset({
            promoted.capture.context_revision_id
        })
        with pytest.raises(IntegrityError):
            uow.context_packs.add_entry(entities.ContextPackEntry(
                id=_id(), project_id=project.project_id, export_id=export_id,
                context_item_id=_id(), context_revision_id=promoted.capture.context_revision_id,
                ordinal=1, relative_path="files/other/file.txt",
                display_name="file.txt", size_bytes=1, sha256="a" * 64,
                created_at=NOW,
            ))
