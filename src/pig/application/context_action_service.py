from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional
from uuid import uuid4

from pig.application.contracts import (
    AdvanceContextRevisionRequest,
    CaptureContextRevisionRequest,
    ContextAnnotationMutationResult,
    ContextItemLifecycleRequest,
    ContextItemMutationResult,
    ContextPlacementMutationResult,
    ContextRevisionCleanupCandidate,
    ContextRevisionProtectionResult,
    ContextSectionLifecycleRequest,
    ContextSectionMutationResult,
    CreateContextSectionRequest,
    ExecuteContextRevisionCleanupRequest,
    ExecuteContextRevisionCleanupResult,
    PlaceContextItemRequest,
    PreflightContextPromotionRequest,
    PreflightContextPromotionResult,
    PreviewContextRevisionCleanupRequest,
    PreviewContextRevisionCleanupResult,
    PromoteWorkspaceItemToContextRequest,
    PromoteWorkspaceItemToContextResult,
    SetContextRevisionProtectionRequest,
    UpdateContextSectionRequest,
    UpsertContextAnnotationRequest,
)
from pig.application.errors import ApplicationError
from pig.application.operation_control import OperationControl
from pig.application.ports import ContextObjectStore, ProjectDatabaseProvider
from pig.domain.entities import (
    ContextAnnotation,
    ContextItem,
    ContextPlacement,
    ContextSection,
    ProcessingEvent,
)
from pig.domain.enums import (
    ContextAnnotationKind,
    ContextContentObjectStatus,
    ContextLifecycleStatus,
    ContextRevisionCaptureStatus,
    ContextRevisionSourceKind,
    ErrorCode,
    EventSeverity,
    EventType,
    NodeKind,
    NodeFormat,
    WorkspaceItemKind,
)
from pig.domain.exceptions import EntityNotFoundError
from pig.domain.model_version import CURRENT_PROJECT_MODEL_VERSION


Clock = Callable[[], datetime]
IdGenerator = Callable[[], str]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid4())


class ContextActionService:
    """V2.1.3 deterministic Context writes and retention workflow."""

    def __init__(
        self, *, database: ProjectDatabaseProvider, capture_service,
        object_store: ContextObjectStore, clock: Clock = _utc_now,
        id_generator: IdGenerator = _new_id,
    ) -> None:
        self._database = database
        self._capture = capture_service
        self._objects = object_store
        self._clock = clock
        self._new_id = id_generator

    def preflight_promotion(
        self, request: PreflightContextPromotionRequest
    ) -> PreflightContextPromotionResult:
        project_id = self._text(request.project_id, "project_id", 255)
        database_path = Path(request.database_path).resolve(strict=True)
        with self._database.unit_of_work(database_path) as uow:
            project = self._project(uow, project_id)
            if project.workspace_revision != request.expected_workspace_revision:
                raise ApplicationError(
                    ErrorCode.WORKSPACE_CHANGED_DURING_CAPTURE.value,
                    "Workspace changed before promotion preflight",
                    {"expected": request.expected_workspace_revision,
                     "actual": project.workspace_revision},
                )
            workspace_item = uow.workspace.get_item(request.workspace_item_id)
            if (
                workspace_item is None
                or workspace_item.project_id != project_id
                or workspace_item.item_kind not in (WorkspaceItemKind.FILE, WorkspaceItemKind.CONTAINER_VIEW)
                or not uow.workspace.is_effectively_active(workspace_item.id)
                or workspace_item.origin_source_node_id is None
            ):
                raise ApplicationError(
                    ErrorCode.CONTEXT_ACTION_INVALID.value,
                    "only an active source-backed terminal file can enter Context",
                )
            working = uow.workspace.working_artifact_for_item(workspace_item.id)
            node = uow.catalog.get_node(workspace_item.origin_source_node_id)
            if node is None:
                raise ApplicationError(
                    ErrorCode.CONTEXT_CAPTURE_SOURCE_MISSING.value,
                    "source node is missing",
                )
            if not (node.kind == NodeKind.FILE or
                    (workspace_item.item_kind == WorkspaceItemKind.CONTAINER_VIEW and node.format == NodeFormat.EML)):
                raise ApplicationError(
                    ErrorCode.CONTEXT_ACTION_INVALID.value,
                    "container nodes cannot enter Context",
                )
            settings = uow.context.get_settings(project_id)
            if settings is None:
                raise ApplicationError(
                    ErrorCode.INTERNAL_ERROR.value, "Context settings are missing"
                )
            source_kind = (
                ContextRevisionSourceKind.WORKING
                if working is not None else ContextRevisionSourceKind.SOURCE
            )
            estimated_size = (
                working.current_size
                if working is not None and working.current_size is not None
                else node.declared_size or 0
            )
            used_bytes = sum(
                value.size_bytes
                for value in uow.context.content_objects_for_project(project_id)
                if value.availability_status
                == ContextContentObjectStatus.AVAILABLE
            )
            existing = uow.context.item_for_workspace_item(workspace_item.id)
            context_revision = project.context_revision
            workspace_revision = project.workspace_revision
        available = self._objects.available_space(database_path.parent)
        quota_warning = used_bytes + estimated_size > settings.soft_quota_bytes
        blocking_code = None
        if estimated_size > request.policy.max_single_file_size:
            blocking_code = ErrorCode.LIMIT_EXCEEDED.value
        elif available - estimated_size < settings.minimum_free_bytes:
            blocking_code = ErrorCode.CONTEXT_CAPTURE_CAPACITY_BLOCKED.value
        return PreflightContextPromotionResult(
            project_id=project_id,
            workspace_item_id=workspace_item.id,
            workspace_revision=workspace_revision,
            context_revision=context_revision,
            source_kind=source_kind,
            estimated_size_bytes=estimated_size,
            context_store_bytes=used_bytes,
            available_bytes=available,
            soft_quota_bytes=settings.soft_quota_bytes,
            minimum_free_bytes=settings.minimum_free_bytes,
            quota_warning=quota_warning,
            capture_allowed=blocking_code is None,
            blocking_code=blocking_code,
            existing_context_item_id=None if existing is None else existing.id,
            already_active=(
                existing is not None
                and existing.lifecycle_status == ContextLifecycleStatus.ACTIVE
                and existing.current_context_revision_id is not None
            ),
        )

    def promote(
        self, request: PromoteWorkspaceItemToContextRequest,
        *, control: OperationControl | None = None,
    ) -> PromoteWorkspaceItemToContextResult:
        project_id, actor, database_path = self._write_request(
            request.project_id, request.actor, request.database_path,
            request.expected_context_revision,
        )
        title = self._optional_text(request.title_override, "title_override", 512)
        purpose = self._optional_text(request.purpose, "purpose", 20_000)
        correlation_id = request.correlation_id or self._new_id()
        restored = False
        with self._database.unit_of_work(database_path) as uow:
            project = self._project(uow, project_id)
            if project.workspace_revision != request.expected_workspace_revision:
                raise ApplicationError(
                    ErrorCode.WORKSPACE_CHANGED_DURING_CAPTURE.value,
                    "Workspace changed before promotion",
                )
            workspace_item = uow.workspace.get_item(request.workspace_item_id)
            if (
                workspace_item is None or workspace_item.project_id != project_id
                or workspace_item.item_kind not in (WorkspaceItemKind.FILE, WorkspaceItemKind.CONTAINER_VIEW)
                or not uow.workspace.is_effectively_active(workspace_item.id)
                or workspace_item.origin_source_node_id is None
            ):
                raise ApplicationError(
                    ErrorCode.CONTEXT_ACTION_INVALID.value,
                    "only an active source-backed terminal file can enter Context",
                )
            source_node = uow.catalog.get_node(workspace_item.origin_source_node_id)
            if source_node is None:
                raise ApplicationError(
                    ErrorCode.CONTEXT_CAPTURE_SOURCE_MISSING.value,
                    "source node is missing",
                )
            if not (source_node.kind == NodeKind.FILE or
                    (workspace_item.item_kind == WorkspaceItemKind.CONTAINER_VIEW and source_node.format == NodeFormat.EML)):
                raise ApplicationError(
                    ErrorCode.CONTEXT_ACTION_INVALID.value,
                    "container nodes cannot enter Context",
                )
            item = uow.context.item_for_workspace_item(workspace_item.id)
            if item is None:
                now = self._clock()
                item = ContextItem(
                    id=self._new_id(), project_id=project_id,
                    workspace_item_id=workspace_item.id,
                    lifecycle_status=ContextLifecycleStatus.ACTIVE,
                    title_override=title, purpose=purpose,
                    created_at=now, updated_at=now,
                )
                uow.context.add_item(item)
                uow.commit()
            elif item.lifecycle_status == ContextLifecycleStatus.REMOVED:
                restored = True
                item = uow.context.update_item(
                    item.id, title_override=title, purpose=purpose,
                    expected_status=ContextLifecycleStatus.REMOVED,
                    new_status=ContextLifecycleStatus.ACTIVE,
                    removed_at=None, updated_at=self._clock(),
                )
                uow.commit()
            elif item.current_context_revision_id is not None:
                return PromoteWorkspaceItemToContextResult(
                    item=item, capture=None, restored=False
                )

        capture = self._capture.capture(
            CaptureContextRevisionRequest(
                project_id=project_id, database_path=database_path,
                context_item_id=item.id, actor=actor,
                expected_workspace_revision=request.expected_workspace_revision,
                expected_context_revision=request.expected_context_revision,
                correlation_id=correlation_id, policy=request.policy,
            ),
            control=control,
        )
        with self._database.unit_of_work(database_path) as uow:
            current = uow.context.get_item(item.id)
            uow.processing.append_event(self._event(
                EventType.CONTEXT_ITEM_RESTORED if restored else EventType.CONTEXT_ITEM_PROMOTED,
                project_id, actor, correlation_id,
                context_item_id=item.id, workspace_item_id=item.workspace_item_id,
                context_revision_id=capture.context_revision_id,
                new_status=ContextLifecycleStatus.ACTIVE.value,
            ))
            uow.commit()
        return PromoteWorkspaceItemToContextResult(
            item=current, capture=capture, restored=restored
        )

    def advance_revision(
        self, request: AdvanceContextRevisionRequest,
        *, control: OperationControl | None = None,
    ):
        correlation_id = request.correlation_id or self._new_id()
        result = self._capture.capture(
            CaptureContextRevisionRequest(
                project_id=request.project_id, database_path=request.database_path,
                context_item_id=request.context_item_id, actor=request.actor,
                expected_workspace_revision=request.expected_workspace_revision,
                expected_context_revision=request.expected_context_revision,
                correlation_id=correlation_id, policy=request.policy,
            ), control=control,
        )
        with self._database.unit_of_work(request.database_path) as uow:
            uow.processing.append_event(self._event(
                EventType.CONTEXT_REVISION_ADVANCED, result.project_id,
                request.actor.strip(), correlation_id,
                context_item_id=result.context_item_id,
                context_revision_id=result.context_revision_id,
                context_content_object_id=result.content_object_id,
                details={"sha256": result.sha256, "size": result.size_bytes},
            ))
            uow.commit()
        return result

    def remove_item(self, request: ContextItemLifecycleRequest) -> ContextItemMutationResult:
        return self._item_lifecycle(request, ContextLifecycleStatus.ACTIVE,
                                    ContextLifecycleStatus.REMOVED,
                                    EventType.CONTEXT_ITEM_REMOVED)

    def restore_item(self, request: ContextItemLifecycleRequest) -> ContextItemMutationResult:
        return self._item_lifecycle(request, ContextLifecycleStatus.REMOVED,
                                    ContextLifecycleStatus.ACTIVE,
                                    EventType.CONTEXT_ITEM_RESTORED)

    def _item_lifecycle(self, request, expected, new, event_type):
        project_id, actor, database_path = self._write_request(
            request.project_id, request.actor, request.database_path,
            request.expected_context_revision,
        )
        correlation_id = request.correlation_id or self._new_id()
        now = self._clock()
        with self._database.unit_of_work(database_path) as uow:
            item = self._owned_item(uow, project_id, request.context_item_id)
            updated = uow.context.update_item(
                item.id, title_override=item.title_override, purpose=item.purpose,
                expected_status=expected, new_status=new,
                removed_at=now if new == ContextLifecycleStatus.REMOVED else None,
                updated_at=now,
            )
            project = uow.projects.advance_context_revision(
                project_id, request.expected_context_revision, updated_at=now
            )
            uow.processing.append_event(self._event(
                event_type, project_id, actor, correlation_id,
                context_item_id=item.id, workspace_item_id=item.workspace_item_id,
                previous_status=expected.value, new_status=new.value,
            ))
            uow.commit()
        return ContextItemMutationResult(
            project_id=project_id, context_revision=project.context_revision, item=updated
        )

    def create_section(self, request: CreateContextSectionRequest) -> ContextSectionMutationResult:
        project_id, actor, database_path = self._write_request(
            request.project_id, request.actor, request.database_path,
            request.expected_context_revision,
        )
        name = self._text(request.name, "name", 255)
        description = self._optional_text(request.description, "description", 20_000)
        correlation_id = request.correlation_id or self._new_id()
        now = self._clock()
        with self._database.unit_of_work(database_path) as uow:
            sections = tuple(uow.context.sections_for_project(project_id))
            ordinal = request.ordinal if request.ordinal is not None else (
                max((value.ordinal for value in sections), default=-1) + 1
            )
            self._ordinal(ordinal)
            section = ContextSection(
                id=self._new_id(), project_id=project_id, name=name,
                description=description, ordinal=ordinal,
                lifecycle_status=ContextLifecycleStatus.ACTIVE,
                created_at=now, updated_at=now,
            )
            uow.context.add_section(section)
            project = uow.projects.advance_context_revision(
                project_id, request.expected_context_revision, updated_at=now
            )
            uow.processing.append_event(self._event(
                EventType.CONTEXT_SECTION_CREATED, project_id, actor, correlation_id,
                context_section_id=section.id, new_status=ContextLifecycleStatus.ACTIVE.value,
                details={"name": name, "ordinal": ordinal},
            ))
            uow.commit()
        return ContextSectionMutationResult(project_id=project_id,
            context_revision=project.context_revision, section=section)

    def update_section(self, request: UpdateContextSectionRequest) -> ContextSectionMutationResult:
        project_id, actor, database_path = self._write_request(
            request.project_id, request.actor, request.database_path,
            request.expected_context_revision,
        )
        correlation_id = request.correlation_id or self._new_id()
        with self._database.unit_of_work(database_path) as uow:
            current = self._owned_section(uow, project_id, request.context_section_id)
            name = current.name if request.name is None else self._text(request.name, "name", 255)
            description = (
                current.description if request.description is None
                else self._optional_text(request.description, "description", 20_000)
            )
            ordinal = current.ordinal if request.ordinal is None else self._ordinal(request.ordinal)
            updated = uow.context.update_section(
                current.id, name=name, description=description, ordinal=ordinal,
                updated_at=self._clock(),
            )
            project = uow.projects.advance_context_revision(
                project_id, request.expected_context_revision, updated_at=self._clock()
            )
            event_type = (
                EventType.CONTEXT_SECTION_REORDERED
                if ordinal != current.ordinal and name == current.name
                else EventType.CONTEXT_SECTION_RENAMED
            )
            uow.processing.append_event(self._event(
                event_type, project_id, actor, correlation_id,
                context_section_id=current.id,
                details={"name": name, "ordinal": ordinal},
            ))
            uow.commit()
        return ContextSectionMutationResult(project_id=project_id,
            context_revision=project.context_revision, section=updated)

    def remove_section(self, request: ContextSectionLifecycleRequest) -> ContextSectionMutationResult:
        return self._section_lifecycle(request, ContextLifecycleStatus.ACTIVE,
            ContextLifecycleStatus.REMOVED, EventType.CONTEXT_SECTION_REMOVED)

    def restore_section(self, request: ContextSectionLifecycleRequest) -> ContextSectionMutationResult:
        return self._section_lifecycle(request, ContextLifecycleStatus.REMOVED,
            ContextLifecycleStatus.ACTIVE, EventType.CONTEXT_SECTION_RESTORED)

    def _section_lifecycle(self, request, expected, new, event_type):
        project_id, actor, database_path = self._write_request(
            request.project_id, request.actor, request.database_path,
            request.expected_context_revision,
        )
        correlation_id = request.correlation_id or self._new_id()
        now = self._clock()
        with self._database.unit_of_work(database_path) as uow:
            section = self._owned_section(uow, project_id, request.context_section_id)
            updated = uow.context.update_section(
                section.id, name=section.name, description=section.description,
                ordinal=section.ordinal, expected_status=expected, new_status=new,
                removed_at=now if new == ContextLifecycleStatus.REMOVED else None,
                updated_at=now,
            )
            project = uow.projects.advance_context_revision(
                project_id, request.expected_context_revision, updated_at=now
            )
            uow.processing.append_event(self._event(
                event_type, project_id, actor, correlation_id,
                context_section_id=section.id, previous_status=expected.value,
                new_status=new.value,
            ))
            uow.commit()
        return ContextSectionMutationResult(project_id=project_id,
            context_revision=project.context_revision, section=updated)

    def place_item(self, request: PlaceContextItemRequest) -> ContextPlacementMutationResult:
        return self._placement(request, "PLACE")

    def remove_placement(self, request: PlaceContextItemRequest) -> ContextPlacementMutationResult:
        return self._placement(request, "REMOVE")

    def reorder_placement(self, request: PlaceContextItemRequest) -> ContextPlacementMutationResult:
        return self._placement(request, "REORDER")

    def _placement(self, request, action):
        project_id, actor, database_path = self._write_request(
            request.project_id, request.actor, request.database_path,
            request.expected_context_revision,
        )
        correlation_id = request.correlation_id or self._new_id()
        now = self._clock()
        with self._database.unit_of_work(database_path) as uow:
            item = self._owned_item(uow, project_id, request.context_item_id)
            section = self._owned_section(uow, project_id, request.context_section_id)
            if item.lifecycle_status != ContextLifecycleStatus.ACTIVE or section.lifecycle_status != ContextLifecycleStatus.ACTIVE:
                raise ApplicationError(ErrorCode.CONTEXT_ACTION_INVALID.value,
                                       "placement requires active Item and Section")
            existing = uow.context.get_placement(item.id, section.id)
            ordinal = request.ordinal
            if ordinal is None:
                peers = [value.ordinal for value in uow.context.placements_for_project(project_id)
                         if value.context_section_id == section.id]
                ordinal = max(peers, default=-1) + 1
            self._ordinal(ordinal)
            if action == "PLACE":
                if existing is None:
                    placement = ContextPlacement(
                        id=self._new_id(), project_id=project_id,
                        context_item_id=item.id, context_section_id=section.id,
                        ordinal=ordinal, lifecycle_status=ContextLifecycleStatus.ACTIVE,
                        created_at=now, updated_at=now,
                    )
                    uow.context.add_placement(placement)
                elif existing.lifecycle_status == ContextLifecycleStatus.REMOVED:
                    placement = uow.context.update_placement(
                        existing.id, ordinal=ordinal,
                        expected_status=ContextLifecycleStatus.REMOVED,
                        new_status=ContextLifecycleStatus.ACTIVE,
                        removed_at=None, updated_at=now,
                    )
                else:
                    placement = existing
                event_type = EventType.CONTEXT_PLACEMENT_CREATED
            else:
                if existing is None:
                    raise EntityNotFoundError("context placement not found")
                if action == "REMOVE":
                    placement = uow.context.update_placement(
                        existing.id, ordinal=existing.ordinal,
                        expected_status=ContextLifecycleStatus.ACTIVE,
                        new_status=ContextLifecycleStatus.REMOVED,
                        removed_at=now, updated_at=now,
                    )
                    event_type = EventType.CONTEXT_PLACEMENT_REMOVED
                else:
                    if existing.lifecycle_status != ContextLifecycleStatus.ACTIVE:
                        raise ApplicationError(ErrorCode.CONTEXT_ACTION_INVALID.value,
                                               "removed placement cannot be reordered")
                    placement = uow.context.update_placement(
                        existing.id, ordinal=ordinal, updated_at=now
                    )
                    event_type = EventType.CONTEXT_PLACEMENT_REORDERED
            if action == "PLACE" and existing is not None and existing.lifecycle_status == ContextLifecycleStatus.ACTIVE:
                return ContextPlacementMutationResult(
                    project_id=project_id,
                    context_revision=request.expected_context_revision,
                    placement=placement,
                )
            project = uow.projects.advance_context_revision(
                project_id, request.expected_context_revision, updated_at=now
            )
            uow.processing.append_event(self._event(
                event_type, project_id, actor, correlation_id,
                context_item_id=item.id, context_section_id=section.id,
                details={"placement_id": placement.id, "ordinal": placement.ordinal},
            ))
            uow.commit()
        return ContextPlacementMutationResult(project_id=project_id,
            context_revision=project.context_revision, placement=placement)

    def upsert_annotation(
        self, request: UpsertContextAnnotationRequest
    ) -> ContextAnnotationMutationResult:
        project_id, actor, database_path = self._write_request(
            request.project_id, request.actor, request.database_path,
            request.expected_context_revision,
        )
        body = self._text(request.body, "body", 50_000)
        correlation_id = request.correlation_id or self._new_id()
        now = self._clock()
        with self._database.unit_of_work(database_path) as uow:
            item = self._owned_item(uow, project_id, request.context_item_id)
            if request.context_revision_id is not None:
                revision = uow.context.get_revision(request.context_revision_id)
                if revision is None or revision.context_item_id != item.id:
                    raise ApplicationError(ErrorCode.CONTEXT_ACTION_INVALID.value,
                                           "annotation Revision must belong to its Item")
            existing = next(iter(uow.context.annotations_for_item(item.id)), None)
            if existing is None:
                annotation = ContextAnnotation(
                    id=self._new_id(), project_id=project_id,
                    context_item_id=item.id,
                    context_revision_id=request.context_revision_id,
                    kind=ContextAnnotationKind.GUIDANCE,
                    body=body, author=actor, created_at=now, updated_at=now,
                )
                uow.context.add_annotation(annotation)
                created = True
                event_type = EventType.CONTEXT_ANNOTATION_CREATED
            else:
                annotation = uow.context.update_annotation(
                    existing.id, body=body, author=actor,
                    context_revision_id=request.context_revision_id, updated_at=now,
                )
                created = False
                event_type = EventType.CONTEXT_ANNOTATION_UPDATED
            project = uow.projects.advance_context_revision(
                project_id, request.expected_context_revision, updated_at=now
            )
            uow.processing.append_event(self._event(
                event_type, project_id, actor, correlation_id,
                context_item_id=item.id, context_annotation_id=annotation.id,
                context_revision_id=request.context_revision_id,
            ))
            uow.commit()
        return ContextAnnotationMutationResult(project_id=project_id,
            context_revision=project.context_revision, annotation=annotation,
            created=created)

    def set_revision_protection(
        self, request: SetContextRevisionProtectionRequest
    ) -> ContextRevisionProtectionResult:
        project_id, actor, database_path = self._write_request(
            request.project_id, request.actor, request.database_path,
            request.expected_context_revision,
        )
        reason = self._optional_text(request.reason, "reason", 2_000)
        if request.protected and reason is None:
            raise ApplicationError(ErrorCode.CONTEXT_ACTION_INVALID.value,
                                   "protecting a Revision requires a reason")
        correlation_id = request.correlation_id or self._new_id()
        now = self._clock()
        with self._database.unit_of_work(database_path) as uow:
            revision = uow.context.get_revision(request.context_revision_id)
            if revision is None or revision.project_id != project_id:
                raise EntityNotFoundError(f"context revision not found: {request.context_revision_id}")
            updated = uow.context.update_revision_protection(
                revision.id, revision.is_manually_protected, request.protected,
                protection_reason=reason if request.protected else None,
                updated_at=now,
            )
            project = uow.projects.advance_context_revision(
                project_id, request.expected_context_revision, updated_at=now
            )
            uow.processing.append_event(self._event(
                EventType.CONTEXT_REVISION_PROTECTED if request.protected else
                EventType.CONTEXT_REVISION_UNPROTECTED,
                project_id, actor, correlation_id,
                context_item_id=revision.context_item_id,
                context_revision_id=revision.id,
                details={"reason": reason} if request.protected else {},
            ))
            uow.commit()
        return ContextRevisionProtectionResult(project_id=project_id,
            context_revision=project.context_revision, revision=updated)

    def preview_cleanup(
        self, request: PreviewContextRevisionCleanupRequest
    ) -> PreviewContextRevisionCleanupResult:
        project_id = self._text(request.project_id, "project_id", 255)
        actor = self._text(request.actor, "actor", 255)
        database_path = Path(request.database_path).resolve(strict=True)
        with self._database.unit_of_work(database_path) as uow:
            project = self._project(uow, project_id)
            candidates = self._cleanup_candidates(uow, project_id)
            token = self._cleanup_token(project_id, project.context_revision, candidates)
            uow.processing.append_event(self._event(
                EventType.CONTEXT_REVISION_CLEANUP_PREVIEWED,
                project_id, actor, self._new_id(),
                details={"preview_token": token, "candidate_count": len(candidates),
                         "reclaimable_bytes": self._reclaimable(candidates)},
            ))
            uow.commit()
        return PreviewContextRevisionCleanupResult(
            project_id=project_id, context_revision=project.context_revision,
            preview_token=token, candidates=candidates,
            reclaimable_bytes=self._reclaimable(candidates),
        )

    def execute_cleanup(
        self, request: ExecuteContextRevisionCleanupRequest
    ) -> ExecuteContextRevisionCleanupResult:
        if not request.confirmed:
            raise ApplicationError(ErrorCode.CONTEXT_ACTION_INVALID.value,
                                   "Context cleanup requires explicit confirmation")
        project_id, actor, database_path = self._write_request(
            request.project_id, request.actor, request.database_path,
            request.expected_context_revision,
        )
        correlation_id = request.correlation_id or self._new_id()
        with self._database.unit_of_work(database_path) as uow:
            candidates = self._cleanup_candidates(uow, project_id)
            token = self._cleanup_token(project_id, request.expected_context_revision, candidates)
            if token != request.preview_token:
                raise ApplicationError(
                    ErrorCode.CONTEXT_CLEANUP_PREVIEW_STALE.value,
                    "cleanup preview is stale; preview again before deleting",
                )
            revision_ids = tuple(value.revision_id for value in candidates)
            object_ids = {
                value.content_object_id for value in candidates if not value.object_shared
            }
            object_rows = tuple(
                value for value in uow.context.content_objects_for_project(project_id)
                if value.id in object_ids
            )
            uow.context.delete_revisions(revision_ids)
            uow.context.delete_content_objects(tuple(object_ids))
            project = uow.projects.advance_context_revision(
                project_id, request.expected_context_revision, updated_at=self._clock()
            )
            uow.processing.append_event(self._event(
                EventType.CONTEXT_REVISION_CLEANUP_COMPLETED,
                project_id, actor, correlation_id,
                details={"deleted_revision_ids": revision_ids,
                         "deleted_content_object_ids": tuple(object_ids),
                         "preview_token": token},
            ))
            uow.commit()
        reclaimed = 0
        orphaned = []
        for value in object_rows:
            try:
                removed = self._objects.remove(
                    database_path.parent, value.object_key,
                    expected_size=value.size_bytes, expected_sha256=value.sha256,
                )
            except (ApplicationError, OSError):
                orphaned.append(value.object_key)
            else:
                if removed:
                    reclaimed += value.size_bytes
        if orphaned:
            with self._database.unit_of_work(database_path) as uow:
                uow.processing.append_event(self._event(
                    EventType.CONTEXT_REVISION_CLEANUP_FAILED,
                    project_id, actor, correlation_id,
                    severity=EventSeverity.WARNING,
                    error_code=ErrorCode.CONTEXT_ACTION_INVALID,
                    details={
                        "message": "database cleanup completed but object removal failed",
                        "orphaned_object_keys": tuple(orphaned),
                    },
                ))
                uow.commit()
        return ExecuteContextRevisionCleanupResult(
            project_id=project_id, context_revision=project.context_revision,
            deleted_revision_ids=revision_ids,
            deleted_content_object_ids=tuple(object_ids),
            reclaimed_bytes=reclaimed,
            orphaned_object_keys=tuple(orphaned),
        )

    def _cleanup_candidates(self, uow, project_id):
        exported_revisions = uow.context_packs.successful_revision_ids(project_id)
        experience_revisions = uow.experience.referenced_revision_ids(project_id)
        annotations = {
            value.context_revision_id
            for item in uow.context.items_for_project(project_id)
            for value in uow.context.annotations_for_item(item.id)
            if value.context_revision_id is not None
        }
        all_revisions = tuple(uow.context.revisions_for_project(project_id))
        references_by_object = {}
        for revision in all_revisions:
            if revision.content_object_id is not None:
                references_by_object.setdefault(revision.content_object_id, set()).add(revision.id)
        objects = {value.id: value for value in uow.context.content_objects_for_project(project_id)}
        eligible = []
        for item in uow.context.items_for_project(project_id):
            ready = sorted(
                (value for value in all_revisions
                 if value.context_item_id == item.id
                 and value.capture_status == ContextRevisionCaptureStatus.READY),
                key=lambda value: (value.created_at, value.id), reverse=True,
            )
            protected_ids = set()
            if item.current_context_revision_id is not None:
                protected_ids.add(item.current_context_revision_id)
            previous = next((value for value in ready if value.id not in protected_ids), None)
            if previous is not None:
                protected_ids.add(previous.id)
            for revision in ready:
                if (
                    revision.id in protected_ids
                    or revision.is_manually_protected
                    or revision.id in annotations
                    or revision.id in exported_revisions
                    or revision.id in experience_revisions
                    or revision.content_object_id is None
                ):
                    continue
                content = objects.get(revision.content_object_id)
                if content is None or content.availability_status != ContextContentObjectStatus.AVAILABLE:
                    continue
                eligible.append((revision, content))
        candidate_ids = {revision.id for revision, _content in eligible}
        candidates = [
            ContextRevisionCleanupCandidate(
                revision_id=revision.id,
                context_item_id=revision.context_item_id,
                content_object_id=content.id,
                size_bytes=content.size_bytes,
                object_shared=bool(references_by_object[content.id] - candidate_ids),
            )
            for revision, content in eligible
        ]
        return tuple(sorted(candidates, key=lambda value: value.revision_id))

    @staticmethod
    def _cleanup_token(project_id, context_revision, candidates):
        material = "|".join((project_id, str(context_revision), *(
            f"{value.revision_id}:{value.content_object_id}:{int(value.object_shared)}"
            for value in candidates
        )))
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    @staticmethod
    def _reclaimable(candidates):
        seen = set()
        total = 0
        for value in candidates:
            if not value.object_shared and value.content_object_id not in seen:
                seen.add(value.content_object_id)
                total += value.size_bytes
        return total

    def _write_request(self, project_id, actor, database_path, expected_revision):
        project_id = self._text(project_id, "project_id", 255)
        actor = self._text(actor, "actor", 255)
        path = Path(database_path).resolve(strict=True)
        with self._database.unit_of_work(path) as uow:
            project = self._project(uow, project_id)
            if project.context_revision != expected_revision:
                self._conflict(uow, project_id, actor, project.context_revision,
                               expected_revision)
                uow.commit()
                raise ApplicationError(
                    ErrorCode.CONTEXT_WRITE_CONFLICT.value,
                    "Project Context changed concurrently",
                    {"expected": expected_revision, "actual": project.context_revision},
                )
        return project_id, actor, path

    def _conflict(self, uow, project_id, actor, actual, expected):
        uow.processing.append_event(self._event(
            EventType.CONTEXT_WRITE_CONFLICT, project_id, actor, self._new_id(),
            severity=EventSeverity.WARNING,
            error_code=ErrorCode.CONTEXT_WRITE_CONFLICT,
            details={"expected": expected, "actual": actual},
        ))

    def _event(self, event_type, project_id, actor, correlation_id, **kwargs):
        return ProcessingEvent(
            id=self._new_id(), event_type=event_type, project_id=project_id,
            actor=actor, occurred_at=self._clock(),
            severity=kwargs.pop("severity", EventSeverity.INFO),
            correlation_id=correlation_id, **kwargs,
        )

    def _project(self, uow, project_id):
        project = uow.projects.get(project_id)
        if project is None:
            raise EntityNotFoundError(f"project not found: {project_id}")
        if project.model_version != CURRENT_PROJECT_MODEL_VERSION:
            raise ApplicationError("PROJECT_CONTEXT_UPGRADE_REQUIRED", "Project must be upgraded")
        return project

    @staticmethod
    def _owned_item(uow, project_id, item_id):
        item = uow.context.get_item(item_id)
        if item is None or item.project_id != project_id:
            raise EntityNotFoundError(f"context item not found: {item_id}")
        return item

    @staticmethod
    def _owned_section(uow, project_id, section_id):
        section = uow.context.get_section(section_id)
        if section is None or section.project_id != project_id:
            raise EntityNotFoundError(f"context section not found: {section_id}")
        return section

    @staticmethod
    def _text(value: str, field: str, maximum: int) -> str:
        normalized = value.strip()
        if not normalized or len(normalized) > maximum:
            raise ApplicationError("INVALID_REQUEST", f"{field} is empty or too long")
        if any(ord(character) < 32 or ord(character) == 127 for character in normalized):
            raise ApplicationError("INVALID_REQUEST", f"{field} contains control characters")
        return normalized

    @classmethod
    def _optional_text(cls, value: Optional[str], field: str, maximum: int):
        if value is None:
            return None
        normalized = value.strip()
        return None if not normalized else cls._text(normalized, field, maximum)

    @staticmethod
    def _ordinal(value: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ApplicationError("INVALID_REQUEST", "ordinal must be a nonnegative integer")
        return value
