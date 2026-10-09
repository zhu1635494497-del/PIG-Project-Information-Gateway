from __future__ import annotations

from typing import Optional, Sequence

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from pig.domain import entities
from pig.infrastructure.database import models
from pig.domain.exceptions import ConcurrentStateError, EntityNotFoundError


def _settings(row: models.ContextSettingsModel) -> entities.ContextSettings:
    return entities.ContextSettings(
        project_id=row.project_id,
        soft_quota_bytes=row.soft_quota_bytes,
        minimum_free_bytes=row.minimum_free_bytes,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _section(row: models.ContextSectionModel) -> entities.ContextSection:
    return entities.ContextSection(
        id=row.id,
        project_id=row.project_id,
        name=row.name,
        description=row.description,
        ordinal=row.ordinal,
        lifecycle_status=row.lifecycle_status,
        removed_at=row.removed_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _item(row: models.ContextItemModel) -> entities.ContextItem:
    return entities.ContextItem(
        id=row.id,
        project_id=row.project_id,
        workspace_item_id=row.workspace_item_id,
        title_override=row.title_override,
        purpose=row.purpose,
        lifecycle_status=row.lifecycle_status,
        current_context_revision_id=row.current_context_revision_id,
        removed_at=row.removed_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _placement(row: models.ContextPlacementModel) -> entities.ContextPlacement:
    return entities.ContextPlacement(
        id=row.id,
        project_id=row.project_id,
        context_item_id=row.context_item_id,
        context_section_id=row.context_section_id,
        ordinal=row.ordinal,
        lifecycle_status=row.lifecycle_status,
        removed_at=row.removed_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _content_object(
    row: models.ContextContentObjectModel,
) -> entities.ContextContentObject:
    return entities.ContextContentObject(
        id=row.id,
        project_id=row.project_id,
        sha256=row.sha256,
        size_bytes=row.size_bytes,
        object_key=row.object_key,
        availability_status=row.availability_status,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _revision(row: models.ContextRevisionModel) -> entities.ContextRevision:
    return entities.ContextRevision(
        id=row.id,
        project_id=row.project_id,
        context_item_id=row.context_item_id,
        content_object_id=row.content_object_id,
        source_kind=row.source_kind,
        source_working_artifact_id=row.source_working_artifact_id,
        source_node_id=row.source_node_id,
        captured_workspace_revision=row.captured_workspace_revision,
        source_observed_sha256=row.source_observed_sha256,
        capture_status=row.capture_status,
        is_manually_protected=row.is_manually_protected,
        protection_reason=row.protection_reason,
        created_by=row.created_by,
        ready_at=row.ready_at,
        error_code=row.error_code,
        error_message=row.error_message,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _annotation(row: models.ContextAnnotationModel) -> entities.ContextAnnotation:
    return entities.ContextAnnotation(
        id=row.id,
        project_id=row.project_id,
        context_item_id=row.context_item_id,
        context_revision_id=row.context_revision_id,
        kind=row.kind,
        body=row.body,
        author=row.author,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlAlchemyContextRepository:
    """Persistence boundary for V2.1 Context facts; no workflow policy lives here."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add_settings(self, settings: entities.ContextSettings) -> None:
        row = models.ContextSettingsModel(
            project_id=settings.project_id,
            soft_quota_bytes=settings.soft_quota_bytes,
            minimum_free_bytes=settings.minimum_free_bytes,
            created_at=settings.created_at,
            updated_at=settings.updated_at,
        )
        self._session.add(row)
        self._session.flush([row])

    def get_settings(self, project_id: str) -> Optional[entities.ContextSettings]:
        row = self._session.get(models.ContextSettingsModel, project_id)
        return None if row is None else _settings(row)

    def add_section(self, section: entities.ContextSection) -> None:
        row = models.ContextSectionModel(
            id=section.id,
            project_id=section.project_id,
            name=section.name,
            description=section.description,
            ordinal=section.ordinal,
            lifecycle_status=section.lifecycle_status,
            removed_at=section.removed_at,
            created_at=section.created_at,
            updated_at=section.updated_at,
        )
        self._session.add(row)
        self._session.flush([row])

    def get_section(self, section_id: str) -> Optional[entities.ContextSection]:
        row = self._session.get(models.ContextSectionModel, section_id)
        return None if row is None else _section(row)

    def sections_for_project(self, project_id: str) -> Sequence[entities.ContextSection]:
        rows = self._session.scalars(
            select(models.ContextSectionModel)
            .where(models.ContextSectionModel.project_id == project_id)
            .order_by(models.ContextSectionModel.ordinal, models.ContextSectionModel.id)
        ).all()
        return tuple(_section(row) for row in rows)

    def update_section(
        self, section_id: str, *, name=None, description=None, ordinal=None,
        expected_status=None, new_status=None, removed_at=None, updated_at,
    ) -> entities.ContextSection:
        row = self._session.get(models.ContextSectionModel, section_id)
        if row is None:
            raise EntityNotFoundError(f"context section not found: {section_id}")
        if expected_status is not None and row.lifecycle_status != expected_status:
            raise ConcurrentStateError("context section lifecycle changed concurrently")
        if name is not None:
            row.name = name
        row.description = description
        if ordinal is not None:
            row.ordinal = ordinal
        if new_status is not None:
            row.lifecycle_status = new_status
            row.removed_at = removed_at
        row.updated_at = updated_at
        self._session.flush([row])
        return _section(row)

    def add_item(self, item: entities.ContextItem) -> None:
        row = models.ContextItemModel(
            id=item.id,
            project_id=item.project_id,
            workspace_item_id=item.workspace_item_id,
            title_override=item.title_override,
            purpose=item.purpose,
            lifecycle_status=item.lifecycle_status,
            current_context_revision_id=item.current_context_revision_id,
            removed_at=item.removed_at,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )
        self._session.add(row)
        self._session.flush([row])

    def get_item(self, item_id: str) -> Optional[entities.ContextItem]:
        row = self._session.get(models.ContextItemModel, item_id)
        return None if row is None else _item(row)

    def item_for_workspace_item(self, workspace_item_id: str) -> Optional[entities.ContextItem]:
        row = self._session.scalar(
            select(models.ContextItemModel).where(
                models.ContextItemModel.workspace_item_id == workspace_item_id
            )
        )
        return None if row is None else _item(row)

    def items_for_project(self, project_id: str) -> Sequence[entities.ContextItem]:
        rows = self._session.scalars(
            select(models.ContextItemModel)
            .where(models.ContextItemModel.project_id == project_id)
            .order_by(models.ContextItemModel.created_at, models.ContextItemModel.id)
        ).all()
        return tuple(_item(row) for row in rows)

    def update_item(
        self, item_id: str, *, title_override=None, purpose=None,
        expected_status=None, new_status=None, removed_at=None, updated_at,
    ) -> entities.ContextItem:
        row = self._session.get(models.ContextItemModel, item_id)
        if row is None:
            raise EntityNotFoundError(f"context item not found: {item_id}")
        if expected_status is not None and row.lifecycle_status != expected_status:
            raise ConcurrentStateError("context item lifecycle changed concurrently")
        row.title_override = title_override
        row.purpose = purpose
        if new_status is not None:
            row.lifecycle_status = new_status
            row.removed_at = removed_at
        row.updated_at = updated_at
        self._session.flush([row])
        return _item(row)

    def add_placement(self, placement: entities.ContextPlacement) -> None:
        row = models.ContextPlacementModel(
            id=placement.id,
            project_id=placement.project_id,
            context_item_id=placement.context_item_id,
            context_section_id=placement.context_section_id,
            ordinal=placement.ordinal,
            lifecycle_status=placement.lifecycle_status,
            removed_at=placement.removed_at,
            created_at=placement.created_at,
            updated_at=placement.updated_at,
        )
        self._session.add(row)
        self._session.flush([row])

    def placements_for_item(
        self, context_item_id: str
    ) -> Sequence[entities.ContextPlacement]:
        rows = self._session.scalars(
            select(models.ContextPlacementModel)
            .where(models.ContextPlacementModel.context_item_id == context_item_id)
            .order_by(
                models.ContextPlacementModel.context_section_id,
                models.ContextPlacementModel.ordinal,
                models.ContextPlacementModel.id,
            )
        ).all()
        return tuple(_placement(row) for row in rows)

    def placements_for_project(
        self, project_id: str
    ) -> Sequence[entities.ContextPlacement]:
        rows = self._session.scalars(
            select(models.ContextPlacementModel)
            .where(models.ContextPlacementModel.project_id == project_id)
            .order_by(
                models.ContextPlacementModel.context_section_id,
                models.ContextPlacementModel.ordinal,
                models.ContextPlacementModel.id,
            )
        ).all()
        return tuple(_placement(row) for row in rows)

    def get_placement(
        self, context_item_id: str, context_section_id: str
    ) -> Optional[entities.ContextPlacement]:
        row = self._session.scalar(
            select(models.ContextPlacementModel).where(
                models.ContextPlacementModel.context_item_id == context_item_id,
                models.ContextPlacementModel.context_section_id == context_section_id,
            )
        )
        return None if row is None else _placement(row)

    def update_placement(
        self, placement_id: str, *, ordinal=None, expected_status=None,
        new_status=None, removed_at=None, updated_at,
    ) -> entities.ContextPlacement:
        row = self._session.get(models.ContextPlacementModel, placement_id)
        if row is None:
            raise EntityNotFoundError(f"context placement not found: {placement_id}")
        if expected_status is not None and row.lifecycle_status != expected_status:
            raise ConcurrentStateError("context placement lifecycle changed concurrently")
        if ordinal is not None:
            row.ordinal = ordinal
        if new_status is not None:
            row.lifecycle_status = new_status
            row.removed_at = removed_at
        row.updated_at = updated_at
        self._session.flush([row])
        return _placement(row)

    def add_content_object(self, value: entities.ContextContentObject) -> None:
        row = models.ContextContentObjectModel(
            id=value.id,
            project_id=value.project_id,
            sha256=value.sha256,
            size_bytes=value.size_bytes,
            object_key=value.object_key,
            availability_status=value.availability_status,
            created_at=value.created_at,
            updated_at=value.updated_at,
        )
        self._session.add(row)
        self._session.flush([row])

    def get_content_object(
        self, object_id: str
    ) -> Optional[entities.ContextContentObject]:
        row = self._session.get(models.ContextContentObjectModel, object_id)
        return None if row is None else _content_object(row)

    def content_object_by_sha256(
        self, project_id: str, sha256: str
    ) -> Optional[entities.ContextContentObject]:
        row = self._session.scalar(
            select(models.ContextContentObjectModel).where(
                models.ContextContentObjectModel.project_id == project_id,
                models.ContextContentObjectModel.sha256 == sha256,
            )
        )
        return None if row is None else _content_object(row)

    def content_objects_for_project(
        self, project_id: str
    ) -> Sequence[entities.ContextContentObject]:
        rows = self._session.scalars(
            select(models.ContextContentObjectModel)
            .where(models.ContextContentObjectModel.project_id == project_id)
            .order_by(models.ContextContentObjectModel.created_at, models.ContextContentObjectModel.id)
        ).all()
        return tuple(_content_object(row) for row in rows)

    def update_content_object_status(
        self,
        object_id: str,
        expected_status,
        new_status,
        *,
        updated_at,
    ) -> entities.ContextContentObject:
        result = self._session.execute(
            update(models.ContextContentObjectModel)
            .where(
                models.ContextContentObjectModel.id == object_id,
                models.ContextContentObjectModel.availability_status == expected_status,
            )
            .values(availability_status=new_status, updated_at=updated_at)
        )
        if result.rowcount != 1:
            if self._session.get(models.ContextContentObjectModel, object_id) is None:
                raise EntityNotFoundError(f"context content object not found: {object_id}")
            raise ConcurrentStateError("context content object status changed concurrently")
        row = self._session.get(models.ContextContentObjectModel, object_id)
        return _content_object(row)

    def add_revision(self, revision: entities.ContextRevision) -> None:
        row = models.ContextRevisionModel(
            id=revision.id,
            project_id=revision.project_id,
            context_item_id=revision.context_item_id,
            content_object_id=revision.content_object_id,
            source_kind=revision.source_kind,
            source_working_artifact_id=revision.source_working_artifact_id,
            source_node_id=revision.source_node_id,
            captured_workspace_revision=revision.captured_workspace_revision,
            source_observed_sha256=revision.source_observed_sha256,
            capture_status=revision.capture_status,
            is_manually_protected=revision.is_manually_protected,
            protection_reason=revision.protection_reason,
            created_by=revision.created_by,
            ready_at=revision.ready_at,
            error_code=revision.error_code,
            error_message=revision.error_message,
            created_at=revision.created_at,
            updated_at=revision.updated_at,
        )
        self._session.add(row)
        self._session.flush([row])

    def get_revision(self, revision_id: str) -> Optional[entities.ContextRevision]:
        row = self._session.get(models.ContextRevisionModel, revision_id)
        return None if row is None else _revision(row)

    def revisions_for_item(
        self, context_item_id: str
    ) -> Sequence[entities.ContextRevision]:
        rows = self._session.scalars(
            select(models.ContextRevisionModel)
            .where(models.ContextRevisionModel.context_item_id == context_item_id)
            .order_by(models.ContextRevisionModel.created_at, models.ContextRevisionModel.id)
        ).all()
        return tuple(_revision(row) for row in rows)

    def revisions_for_project(
        self, project_id: str
    ) -> Sequence[entities.ContextRevision]:
        rows = self._session.scalars(
            select(models.ContextRevisionModel)
            .where(models.ContextRevisionModel.project_id == project_id)
            .order_by(models.ContextRevisionModel.created_at, models.ContextRevisionModel.id)
        ).all()
        return tuple(_revision(row) for row in rows)

    def update_revision_capture(
        self,
        revision_id: str,
        expected_status,
        new_status,
        *,
        updated_at,
        content_object_id=None,
        source_observed_sha256=None,
        ready_at=None,
        error_code=None,
        error_message=None,
    ) -> entities.ContextRevision:
        values = {
            "capture_status": new_status,
            "updated_at": updated_at,
            "content_object_id": content_object_id,
            "source_observed_sha256": source_observed_sha256,
            "ready_at": ready_at,
            "error_code": error_code,
            "error_message": error_message,
        }
        result = self._session.execute(
            update(models.ContextRevisionModel)
            .where(
                models.ContextRevisionModel.id == revision_id,
                models.ContextRevisionModel.capture_status == expected_status,
            )
            .values(**values)
        )
        if result.rowcount != 1:
            if self._session.get(models.ContextRevisionModel, revision_id) is None:
                raise EntityNotFoundError(f"context revision not found: {revision_id}")
            raise ConcurrentStateError("context revision capture status changed concurrently")
        row = self._session.get(models.ContextRevisionModel, revision_id)
        return _revision(row)

    def set_item_current_revision(
        self,
        item_id: str,
        expected_revision_id,
        revision_id: str,
        *,
        updated_at,
    ) -> entities.ContextItem:
        predicate = (
            models.ContextItemModel.current_context_revision_id.is_(None)
            if expected_revision_id is None
            else models.ContextItemModel.current_context_revision_id == expected_revision_id
        )
        result = self._session.execute(
            update(models.ContextItemModel)
            .where(models.ContextItemModel.id == item_id, predicate)
            .values(current_context_revision_id=revision_id, updated_at=updated_at)
        )
        if result.rowcount != 1:
            if self._session.get(models.ContextItemModel, item_id) is None:
                raise EntityNotFoundError(f"context item not found: {item_id}")
            raise ConcurrentStateError("context item current revision changed concurrently")
        row = self._session.get(models.ContextItemModel, item_id)
        return _item(row)

    def update_revision_protection(
        self, revision_id: str, expected_protected: bool, new_protected: bool,
        *, protection_reason, updated_at,
    ) -> entities.ContextRevision:
        result = self._session.execute(
            update(models.ContextRevisionModel)
            .where(
                models.ContextRevisionModel.id == revision_id,
                models.ContextRevisionModel.is_manually_protected == expected_protected,
            )
            .values(
                is_manually_protected=new_protected,
                protection_reason=protection_reason,
                updated_at=updated_at,
            )
        )
        if result.rowcount != 1:
            if self._session.get(models.ContextRevisionModel, revision_id) is None:
                raise EntityNotFoundError(f"context revision not found: {revision_id}")
            raise ConcurrentStateError("context revision protection changed concurrently")
        row = self._session.get(models.ContextRevisionModel, revision_id)
        return _revision(row)

    def delete_revisions(self, revision_ids: Sequence[str]) -> None:
        if not revision_ids:
            return
        self._session.execute(
            delete(models.ContextRevisionModel).where(
                models.ContextRevisionModel.id.in_(tuple(revision_ids))
            )
        )
        self._session.flush()

    def delete_content_objects(self, object_ids: Sequence[str]) -> None:
        if not object_ids:
            return
        self._session.execute(
            delete(models.ContextContentObjectModel).where(
                models.ContextContentObjectModel.id.in_(tuple(object_ids))
            )
        )
        self._session.flush()

    def add_annotation(self, annotation: entities.ContextAnnotation) -> None:
        row = models.ContextAnnotationModel(
            id=annotation.id,
            project_id=annotation.project_id,
            context_item_id=annotation.context_item_id,
            context_revision_id=annotation.context_revision_id,
            kind=annotation.kind,
            body=annotation.body,
            author=annotation.author,
            created_at=annotation.created_at,
            updated_at=annotation.updated_at,
        )
        self._session.add(row)
        self._session.flush([row])

    def annotations_for_item(
        self, context_item_id: str
    ) -> Sequence[entities.ContextAnnotation]:
        rows = self._session.scalars(
            select(models.ContextAnnotationModel)
            .where(models.ContextAnnotationModel.context_item_id == context_item_id)
            .order_by(models.ContextAnnotationModel.created_at, models.ContextAnnotationModel.id)
        ).all()
        return tuple(_annotation(row) for row in rows)

    def update_annotation(
        self, annotation_id: str, *, body: str, author: str,
        context_revision_id, updated_at,
    ) -> entities.ContextAnnotation:
        row = self._session.get(models.ContextAnnotationModel, annotation_id)
        if row is None:
            raise EntityNotFoundError(f"context annotation not found: {annotation_id}")
        row.body = body
        row.author = author
        row.context_revision_id = context_revision_id
        row.updated_at = updated_at
        self._session.flush([row])
        return _annotation(row)
