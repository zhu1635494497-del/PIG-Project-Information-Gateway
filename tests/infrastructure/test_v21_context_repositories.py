from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from pig.domain import entities, enums
from pig.domain.exceptions import ConcurrentStateError
from pig.domain.model_version import PROJECT_CONTEXT_MODEL_VERSION


NOW = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)


def _id() -> str:
    return str(uuid4())


def test_context_schema_round_trips_foundation_entities(uow_factory) -> None:
    project_id = _id()
    workspace_item_id = _id()
    working_artifact_id = _id()
    section_id = _id()
    item_id = _id()
    object_id = _id()
    revision_id = _id()
    annotation_id = _id()

    with uow_factory() as uow:
        uow.projects.add(
            entities.Project(
                id=project_id,
                name="Context Project",
                status=enums.ProjectStatus.READY,
                workspace_locator="file:///context-project",
                model_version=PROJECT_CONTEXT_MODEL_VERSION,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        uow.workspace.add_item(
            entities.WorkspaceItem(
                id=workspace_item_id,
                project_id=project_id,
                item_kind=enums.WorkspaceItemKind.FILE,
                display_name="core.xlsx",
                lifecycle_status=enums.WorkspaceItemLifecycleStatus.ACTIVE,
                materialization_status=enums.WorkspaceMaterializationStatus.MATERIALIZED,
                created_at=NOW,
                updated_at=NOW,
            ),
            entities.WorkspacePlacement(
                workspace_item_id=workspace_item_id,
                project_id=project_id,
                parent_workspace_item_id=None,
                ordinal=0,
                updated_at=NOW,
            ),
        )
        uow.workspace.add_working_artifact(
            entities.WorkingArtifact(
                id=working_artifact_id,
                project_id=project_id,
                workspace_item_id=workspace_item_id,
                storage_key=f"working/{workspace_item_id}/core.xlsx",
                baseline_size=10,
                baseline_sha256="a" * 64,
                current_size=10,
                current_sha256="a" * 64,
                content_status=enums.WorkingContentStatus.CLEAN,
                materialized_at=NOW,
                updated_at=NOW,
            )
        )
        uow.context.add_settings(
            entities.ContextSettings(
                project_id=project_id,
                soft_quota_bytes=10 * 1024**3,
                minimum_free_bytes=2 * 1024**3,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        uow.context.add_section(
            entities.ContextSection(
                id=section_id,
                project_id=project_id,
                name="Core",
                ordinal=0,
                lifecycle_status=enums.ContextLifecycleStatus.ACTIVE,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        uow.context.add_item(
            entities.ContextItem(
                id=item_id,
                project_id=project_id,
                workspace_item_id=workspace_item_id,
                lifecycle_status=enums.ContextLifecycleStatus.ACTIVE,
                purpose="Primary workbook",
                created_at=NOW,
                updated_at=NOW,
            )
        )
        uow.context.add_placement(
            entities.ContextPlacement(
                id=_id(),
                project_id=project_id,
                context_item_id=item_id,
                context_section_id=section_id,
                ordinal=0,
                lifecycle_status=enums.ContextLifecycleStatus.ACTIVE,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        uow.context.add_content_object(
            entities.ContextContentObject(
                id=object_id,
                project_id=project_id,
                sha256="b" * 64,
                size_bytes=10,
                object_key=f"context/objects/bb/{'b' * 64}",
                availability_status=enums.ContextContentObjectStatus.AVAILABLE,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        uow.context.add_revision(
            entities.ContextRevision(
                id=revision_id,
                project_id=project_id,
                context_item_id=item_id,
                content_object_id=object_id,
                source_kind=enums.ContextRevisionSourceKind.WORKING,
                source_working_artifact_id=working_artifact_id,
                captured_workspace_revision=0,
                source_observed_sha256="a" * 64,
                capture_status=enums.ContextRevisionCaptureStatus.READY,
                is_manually_protected=False,
                created_by="tester",
                ready_at=NOW,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        uow.context.add_annotation(
            entities.ContextAnnotation(
                id=annotation_id,
                project_id=project_id,
                context_item_id=item_id,
                context_revision_id=revision_id,
                kind=enums.ContextAnnotationKind.GUIDANCE,
                body="Read the assumptions sheet first.",
                author="tester",
                created_at=NOW,
                updated_at=NOW,
            )
        )
        advanced = uow.projects.advance_context_revision(
            project_id, 0, updated_at=NOW
        )
        uow.commit()

    assert advanced.context_revision == 1
    with uow_factory() as uow:
        assert uow.context.get_settings(project_id).soft_quota_bytes == 10 * 1024**3
        assert [value.id for value in uow.context.sections_for_project(project_id)] == [
            section_id
        ]
        assert uow.context.item_for_workspace_item(workspace_item_id).id == item_id
        assert uow.context.content_object_by_sha256(project_id, "b" * 64).id == object_id
        assert [value.id for value in uow.context.revisions_for_item(item_id)] == [
            revision_id
        ]
        assert [value.id for value in uow.context.annotations_for_item(item_id)] == [
            annotation_id
        ]


def test_context_revision_optimistic_concurrency_rejects_stale_write(uow_factory) -> None:
    project_id = _id()
    with uow_factory() as uow:
        uow.projects.add(
            entities.Project(
                id=project_id,
                name="Concurrency",
                status=enums.ProjectStatus.READY,
                workspace_locator="file:///concurrency",
                model_version=PROJECT_CONTEXT_MODEL_VERSION,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        uow.commit()

    with uow_factory() as uow:
        uow.projects.advance_context_revision(project_id, 0, updated_at=NOW)
        uow.commit()

    with pytest.raises(ConcurrentStateError, match="context revision changed"):
        with uow_factory() as uow:
            uow.projects.advance_context_revision(project_id, 0, updated_at=NOW)


def test_context_section_lifecycle_requires_matching_removed_time(uow_factory) -> None:
    project_id = _id()
    with uow_factory() as uow:
        uow.projects.add(
            entities.Project(
                id=project_id,
                name="Constraints",
                status=enums.ProjectStatus.READY,
                workspace_locator="file:///constraints",
                model_version=PROJECT_CONTEXT_MODEL_VERSION,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        uow.commit()

    with pytest.raises(IntegrityError):
        with uow_factory() as uow:
            uow.context.add_section(
                entities.ContextSection(
                    id=_id(),
                    project_id=project_id,
                    name="Invalid",
                    ordinal=0,
                    lifecycle_status=enums.ContextLifecycleStatus.ACTIVE,
                    removed_at=NOW,
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
