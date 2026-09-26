from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from pig.application.contracts import (
    CreateProjectRequest,
    ImportProjectItemsRequest,
    InspectImportSessionRequest,
)
from pig.bootstrap import create_local_application
from pig.domain.enums import ImportSessionStatus, NodeProcessingStatus
from pig.infrastructure.database.provider import SqlAlchemyProjectDatabase
from pig.infrastructure.database.repositories import SqlAlchemyProcessingRepository


def _imported_zip(tmp_path: Path):
    source = tmp_path / "batch.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("folder/one.txt", b"one")
        archive.writestr("folder/two.txt", b"two")
    application = create_local_application(tmp_path / "projects")
    project = application.create_project(
        CreateProjectRequest(name="W10 Batch", actor="tester")
    )
    imported = application.import_project_items(
        ImportProjectItemsRequest(
            project_id=project.project_id,
            database_path=project.database_path,
            input_paths=(source,),
            actor="tester",
            idempotency_key="w10-batch",
        )
    )
    return application, project, imported


def test_structure_batch_persists_equivalent_tree_lineage_workspace_and_events(
    tmp_path: Path,
) -> None:
    application, project, imported = _imported_zip(tmp_path)

    inspected = application.inspect_import_session(
        InspectImportSessionRequest(
            project_id=project.project_id,
            database_path=project.database_path,
            import_session_id=imported.import_session_id,
            actor="tester",
        )
    )

    database = SqlAlchemyProjectDatabase()
    with database.unit_of_work(project.database_path) as uow:
        nodes = tuple(uow.catalog.nodes_for_project(project.project_id))
        relationships = tuple(
            uow.catalog.relationships_for_project(project.project_id)
        )
        lineage = tuple(uow.catalog.lineage_for_project(project.project_id))
        items = tuple(uow.workspace.items_for_project(project.project_id))
        events = tuple(uow.processing.events_for_project(project.project_id))

    assert inspected.node_count == 4
    assert len(nodes) == len(items) == 4
    assert len(relationships) == 3
    lineage_by_descendant = {
        node.id: sorted(
            record.distance
            for record in lineage
            if record.descendant_node_id == node.id
        )
        for node in nodes
    }
    assert all(
        lineage_by_descendant[node.id] == list(range(node.depth + 1))
        for node in nodes
    )
    assert {
        event.node_id
        for event in events
        if event.event_type.value == "NODE_PROCESSING_FINISHED"
    } == {node.id for node in nodes}


def test_structure_batch_failure_rolls_back_all_source_projection_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    application, project, imported = _imported_zip(tmp_path)

    def fail_bulk_events(self, events):
        raise RuntimeError("injected batch persistence failure")

    monkeypatch.setattr(
        SqlAlchemyProcessingRepository, "append_events", fail_bulk_events
    )
    with pytest.raises(RuntimeError, match="injected batch persistence failure"):
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
        session = uow.imports.get_session(imported.import_session_id)
        nodes = tuple(uow.catalog.nodes_for_project(project.project_id))
        relationships = tuple(
            uow.catalog.relationships_for_project(project.project_id)
        )
        items = tuple(uow.workspace.items_for_project(project.project_id))
        job = uow.processing.job_for_import_session(imported.import_session_id)

    assert session is not None
    assert session.status == ImportSessionStatus.INSPECTING
    assert len(nodes) == 1
    assert nodes[0].status == NodeProcessingStatus.DISCOVERED
    assert relationships == ()
    assert items == ()
    assert job is None
