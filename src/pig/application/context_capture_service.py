from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, Callable
from uuid import uuid4

from pig.application.contracts import (
    CaptureContextRevisionRequest,
    CaptureContextRevisionResult,
    ContextObjectStoreIssue,
    InspectContextObjectStoreRequest,
    InspectContextObjectStoreResult,
    RefreshWorkingArtifactRequest,
)
from pig.application.errors import ApplicationError
from pig.application.operation_control import (
    OperationCancelled,
    OperationControl,
    OperationStage,
    ensure_operation_control,
)
from pig.application.ports import ContextObjectStore, ProjectDatabaseProvider, WorkingArtifactStore
from pig.domain.entities import ContextContentObject, ContextRevision, ProcessingEvent
from pig.domain.enums import (
    ContextContentObjectStatus,
    ContextLifecycleStatus,
    ContextRevisionCaptureStatus,
    ContextRevisionSourceKind,
    ErrorCode,
    EventSeverity,
    EventType,
    WorkingContentStatus,
    WorkingRefreshReason,
    WorkspaceItemKind,
)
from pig.domain.exceptions import ConcurrentStateError, EntityNotFoundError
from pig.domain.model_version import CURRENT_PROJECT_MODEL_VERSION


Clock = Callable[[], datetime]
IdGenerator = Callable[[], str]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid4())


class ContextCaptureService:
    """Capture immutable Context revisions without changing Source or Working bytes."""

    def __init__(
        self,
        *,
        database: ProjectDatabaseProvider,
        store: ContextObjectStore,
        working_store: WorkingArtifactStore,
        working_file_service,
        structure_service,
        clock: Clock = _utc_now,
        id_generator: IdGenerator = _new_id,
    ) -> None:
        self._database = database
        self._store = store
        self._working_store = working_store
        self._working_files = working_file_service
        self._structure = structure_service
        self._clock = clock
        self._new_id = id_generator

    def capture(
        self,
        request: CaptureContextRevisionRequest,
        *,
        control: OperationControl | None = None,
    ) -> CaptureContextRevisionResult:
        operation = ensure_operation_control(control)
        correlation_id = request.correlation_id or operation.operation_id
        project_id = self._required(request.project_id, "project_id")
        actor = self._required(request.actor, "actor")
        database_path = Path(request.database_path).resolve(strict=True)
        project_path = database_path.parent
        revision_id = self._new_id()

        with self._database.unit_of_work(database_path) as uow:
            project = self._project(uow, project_id)
            if project.workspace_revision != request.expected_workspace_revision:
                raise ApplicationError(
                    ErrorCode.WORKSPACE_CHANGED_DURING_CAPTURE.value,
                    "Workspace changed before Context capture started",
                    {"expected": request.expected_workspace_revision, "actual": project.workspace_revision},
                )
            if project.context_revision != request.expected_context_revision:
                raise ApplicationError(
                    ErrorCode.CONTEXT_WRITE_CONFLICT.value,
                    "Project Context changed before capture started",
                    {"expected": request.expected_context_revision, "actual": project.context_revision},
                )
            context_item = uow.context.get_item(request.context_item_id)
            if (
                context_item is None
                or context_item.project_id != project_id
                or context_item.lifecycle_status != ContextLifecycleStatus.ACTIVE
            ):
                raise EntityNotFoundError(f"active context item not found: {request.context_item_id}")
            workspace_item = uow.workspace.get_item(context_item.workspace_item_id)
            if (
                workspace_item is None
                or workspace_item.project_id != project_id
                or workspace_item.item_kind != WorkspaceItemKind.FILE
                or not uow.workspace.is_effectively_active(workspace_item.id)
                or workspace_item.origin_source_node_id is None
            ):
                raise ApplicationError(
                    ErrorCode.CONTEXT_CAPTURE_SOURCE_MISSING.value,
                    "Context Item no longer references an active source-backed file",
                )
            settings = uow.context.get_settings(project_id)
            if settings is None:
                raise ApplicationError(ErrorCode.INTERNAL_ERROR.value, "Context settings are missing")
            working = uow.workspace.working_artifact_for_item(workspace_item.id)
            node = uow.catalog.get_node(workspace_item.origin_source_node_id)
            if node is None:
                raise ApplicationError(ErrorCode.CONTEXT_CAPTURE_SOURCE_MISSING.value, "source node is missing")
            source_kind = (
                ContextRevisionSourceKind.WORKING
                if working is not None
                else ContextRevisionSourceKind.SOURCE
            )
            estimated_size = (
                working.current_size
                if working is not None and working.current_size is not None
                else node.declared_size or 0
            )
            used_bytes = sum(
                value.size_bytes
                for value in uow.context.content_objects_for_project(project_id)
                if value.availability_status == ContextContentObjectStatus.AVAILABLE
            )
            current_item_revision = context_item.current_context_revision_id

        available = self._store.available_space(project_path)
        quota_warning = used_bytes + estimated_size > settings.soft_quota_bytes
        if available - estimated_size < settings.minimum_free_bytes:
            self._record_capacity_block(
                database_path, project_id, actor, correlation_id,
                context_item.id, workspace_item.id, available, estimated_size,
                settings.minimum_free_bytes,
            )
            raise ApplicationError(
                ErrorCode.CONTEXT_CAPTURE_CAPACITY_BLOCKED.value,
                "Context capture would violate the minimum free-space reserve",
                {
                    "available_bytes": available,
                    "estimated_bytes": estimated_size,
                    "minimum_free_bytes": settings.minimum_free_bytes,
                },
            )

        now = self._clock()
        pending = ContextRevision(
            id=revision_id,
            project_id=project_id,
            context_item_id=context_item.id,
            source_kind=source_kind,
            source_working_artifact_id=None if working is None else working.id,
            source_node_id=node.id if working is None else None,
            captured_workspace_revision=request.expected_workspace_revision,
            capture_status=ContextRevisionCaptureStatus.PENDING,
            is_manually_protected=False,
            created_by=actor,
            created_at=now,
            updated_at=now,
        )
        with self._database.unit_of_work(database_path) as uow:
            uow.context.add_revision(pending)
            uow.processing.append_event(self._event(
                EventType.CONTEXT_CAPTURE_PREFLIGHTED, project_id, actor,
                correlation_id, context_item_id=context_item.id,
                context_revision_id=revision_id, workspace_item_id=workspace_item.id,
                details={
                    "source_kind": source_kind.value,
                    "estimated_size": estimated_size,
                    "available_bytes": available,
                    "quota_warning": quota_warning,
                },
            ))
            uow.context.update_revision_capture(
                revision_id,
                ContextRevisionCaptureStatus.PENDING,
                ContextRevisionCaptureStatus.CAPTURING,
                updated_at=self._clock(),
            )
            uow.processing.append_event(self._event(
                EventType.CONTEXT_CAPTURE_STARTED, project_id, actor,
                correlation_id, context_item_id=context_item.id,
                context_revision_id=revision_id, workspace_item_id=workspace_item.id,
                previous_status=ContextRevisionCaptureStatus.PENDING.value,
                new_status=ContextRevisionCaptureStatus.CAPTURING.value,
                details={"source_kind": source_kind.value},
            ))
            uow.commit()

        operation.start_stage(
            OperationStage.CONTEXT_CAPTURE,
            total_bytes=estimated_size if source_kind == ContextRevisionSourceKind.WORKING else 0,
            current_item=workspace_item.display_name,
        )
        try:
            if source_kind == ContextRevisionSourceKind.WORKING:
                refreshed = self._working_files.refresh(
                    RefreshWorkingArtifactRequest(
                        project_id=project_id,
                        database_path=database_path,
                        workspace_item_id=workspace_item.id,
                        actor=actor,
                        reason=WorkingRefreshReason.EXPLICIT,
                    )
                )
                if refreshed.working_artifact.content_status in {
                    WorkingContentStatus.MISSING,
                    WorkingContentStatus.UNREADABLE,
                }:
                    raise ApplicationError(
                        ErrorCode.CONTEXT_CAPTURE_SOURCE_MISSING.value
                        if refreshed.working_artifact.content_status == WorkingContentStatus.MISSING
                        else ErrorCode.CONTEXT_CAPTURE_SOURCE_UNREADABLE.value,
                        "Working Artifact cannot be captured",
                    )
                expected_source_hash = refreshed.working_artifact.current_sha256
                expected_source_size = refreshed.working_artifact.current_size
                operation.start_stage(
                    OperationStage.CONTEXT_CAPTURE,
                    total_bytes=expected_source_size or 0,
                    current_item=workspace_item.display_name,
                )
                producer = self._file_producer(refreshed.path, request.policy.io_chunk_size)
            else:
                expected_source_hash = None
                expected_source_size = None

                def producer(output: BinaryIO) -> None:
                    self._structure.produce_source_content(
                        project_id=project_id,
                        database_path=database_path,
                        workspace_item_id=workspace_item.id,
                        operation_id=f"{operation.operation_id}-source",
                        policy=request.policy,
                        output=output,
                    )

            stored = self._store.capture(
                project_path,
                operation.operation_id,
                producer,
                maximum=request.policy.max_single_file_size,
                control=operation,
            )
            if (
                expected_source_hash is not None
                and (stored.sha256 != expected_source_hash or stored.size != expected_source_size)
            ):
                raise ApplicationError(
                    ErrorCode.WORKSPACE_CHANGED_DURING_CAPTURE.value,
                    "Working Artifact changed during Context capture",
                )

            ready_at = self._clock()
            with self._database.unit_of_work(database_path) as uow:
                current_project = self._project(uow, project_id)
                if current_project.workspace_revision != request.expected_workspace_revision:
                    raise ApplicationError(
                        ErrorCode.WORKSPACE_CHANGED_DURING_CAPTURE.value,
                        "Workspace changed during Context capture",
                    )
                if current_project.context_revision != request.expected_context_revision:
                    raise ApplicationError(
                        ErrorCode.CONTEXT_WRITE_CONFLICT.value,
                        "Project Context changed during capture",
                    )
                content_object = uow.context.content_object_by_sha256(project_id, stored.sha256)
                object_reused = content_object is not None
                if content_object is None:
                    content_object = ContextContentObject(
                        id=self._new_id(), project_id=project_id,
                        sha256=stored.sha256, size_bytes=stored.size,
                        object_key=stored.object_key,
                        availability_status=ContextContentObjectStatus.AVAILABLE,
                        created_at=ready_at, updated_at=ready_at,
                    )
                    uow.context.add_content_object(content_object)
                elif (
                    content_object.object_key != stored.object_key
                    or content_object.size_bytes != stored.size
                ):
                    raise ApplicationError(
                        ErrorCode.ARTIFACT_HASH_MISMATCH.value,
                        "Context object metadata does not match captured bytes",
                    )
                elif content_object.availability_status != ContextContentObjectStatus.AVAILABLE:
                    content_object = uow.context.update_content_object_status(
                        content_object.id,
                        content_object.availability_status,
                        ContextContentObjectStatus.AVAILABLE,
                        updated_at=ready_at,
                    )
                uow.context.update_revision_capture(
                    revision_id,
                    ContextRevisionCaptureStatus.CAPTURING,
                    ContextRevisionCaptureStatus.READY,
                    updated_at=ready_at,
                    content_object_id=content_object.id,
                    source_observed_sha256=stored.sha256,
                    ready_at=ready_at,
                )
                uow.context.set_item_current_revision(
                    context_item.id,
                    current_item_revision,
                    revision_id,
                    updated_at=ready_at,
                )
                advanced = uow.projects.advance_context_revision(
                    project_id,
                    request.expected_context_revision,
                    updated_at=ready_at,
                )
                uow.processing.append_event(self._event(
                    EventType.CONTEXT_CONTENT_OBJECT_REUSED
                    if object_reused else EventType.CONTEXT_CONTENT_OBJECT_PUBLISHED,
                    project_id, actor, correlation_id,
                    context_item_id=context_item.id,
                    context_revision_id=revision_id,
                    context_content_object_id=content_object.id,
                    details={"size": stored.size, "sha256": stored.sha256},
                ))
                uow.processing.append_event(self._event(
                    EventType.CONTEXT_CAPTURE_COMPLETED, project_id, actor,
                    correlation_id, context_item_id=context_item.id,
                    context_revision_id=revision_id,
                    context_content_object_id=content_object.id,
                    workspace_item_id=workspace_item.id,
                    previous_status=ContextRevisionCaptureStatus.CAPTURING.value,
                    new_status=ContextRevisionCaptureStatus.READY.value,
                    details={"source_kind": source_kind.value, "size": stored.size, "sha256": stored.sha256},
                ))
                uow.commit()
            operation.complete()
            return CaptureContextRevisionResult(
                project_id=project_id,
                context_item_id=context_item.id,
                context_revision_id=revision_id,
                content_object_id=content_object.id,
                source_kind=source_kind,
                capture_status=ContextRevisionCaptureStatus.READY,
                workspace_revision=request.expected_workspace_revision,
                context_revision=advanced.context_revision,
                size_bytes=stored.size,
                sha256=stored.sha256,
                object_key=stored.object_key,
                object_reused=object_reused,
                quota_warning=quota_warning,
            )
        except BaseException as exc:
            self._record_failure(
                database_path, project_id, actor, correlation_id,
                context_item.id, workspace_item.id, revision_id, exc,
            )
            raise

    def inspect_store(
        self, request: InspectContextObjectStoreRequest
    ) -> InspectContextObjectStoreResult:
        project_id = self._required(request.project_id, "project_id")
        actor = self._required(request.actor, "actor")
        database_path = Path(request.database_path).resolve(strict=True)
        project_path = database_path.parent
        with self._database.unit_of_work(database_path) as uow:
            self._project(uow, project_id)
            objects = tuple(uow.context.content_objects_for_project(project_id))
        by_key = {value.object_key: value for value in objects}
        orphan_keys, missing_keys = self._store.inspect(
            project_path, known_object_keys=frozenset(by_key)
        )
        issues: list[ContextObjectStoreIssue] = []
        correlation_id = self._new_id()
        with self._database.unit_of_work(database_path) as uow:
            for key in orphan_keys:
                issues.append(ContextObjectStoreIssue(object_key=key, issue="ORPHAN_CANDIDATE"))
                uow.processing.append_event(self._event(
                    EventType.CONTEXT_CONTENT_OBJECT_ORPHAN_DETECTED,
                    project_id, actor, correlation_id,
                    severity=EventSeverity.WARNING,
                    details={"object_key": key},
                ))
            for key in missing_keys:
                value = by_key[key]
                issues.append(ContextObjectStoreIssue(
                    object_key=key, issue="MISSING", content_object_id=value.id
                ))
                if value.availability_status == ContextContentObjectStatus.AVAILABLE:
                    uow.context.update_content_object_status(
                        value.id,
                        ContextContentObjectStatus.AVAILABLE,
                        ContextContentObjectStatus.MISSING,
                        updated_at=self._clock(),
                    )
                uow.processing.append_event(self._event(
                    EventType.CONTEXT_CONTENT_OBJECT_MISSING_DETECTED,
                    project_id, actor, correlation_id,
                    context_content_object_id=value.id,
                    severity=EventSeverity.ERROR,
                    details={"object_key": key},
                ))
            uow.commit()
        return InspectContextObjectStoreResult(
            project_id=project_id,
            orphan_keys=orphan_keys,
            missing_object_ids=tuple(by_key[key].id for key in missing_keys),
            issues=tuple(issues),
        )

    def _record_capacity_block(self, database_path, project_id, actor, correlation_id,
                               context_item_id, workspace_item_id, available, estimated,
                               minimum_free) -> None:
        with self._database.unit_of_work(database_path) as uow:
            uow.processing.append_event(self._event(
                EventType.CONTEXT_CAPTURE_BLOCKED_BY_CAPACITY,
                project_id, actor, correlation_id,
                context_item_id=context_item_id,
                workspace_item_id=workspace_item_id,
                severity=EventSeverity.WARNING,
                error_code=ErrorCode.CONTEXT_CAPTURE_CAPACITY_BLOCKED,
                details={"available_bytes": available, "estimated_bytes": estimated,
                         "minimum_free_bytes": minimum_free},
            ))
            uow.commit()

    def _record_failure(self, database_path, project_id, actor, correlation_id,
                        context_item_id, workspace_item_id, revision_id, exc) -> None:
        cancelled = isinstance(exc, OperationCancelled)
        new_status = (
            ContextRevisionCaptureStatus.CANCELLED_AT_SAFE_POINT
            if cancelled else ContextRevisionCaptureStatus.FAILED
        )
        code = self._error_code(exc)
        with self._database.unit_of_work(database_path) as uow:
            revision = uow.context.get_revision(revision_id)
            if revision is not None and revision.capture_status == ContextRevisionCaptureStatus.CAPTURING:
                uow.context.update_revision_capture(
                    revision_id,
                    ContextRevisionCaptureStatus.CAPTURING,
                    new_status,
                    updated_at=self._clock(),
                    error_code=None if cancelled else code.value,
                    error_message=(
                        None
                        if cancelled
                        else exc.message
                        if isinstance(exc, ApplicationError)
                        else "unexpected Context capture failure"
                    ),
                )
                uow.processing.append_event(self._event(
                    EventType.CONTEXT_CAPTURE_CANCELLED if cancelled else
                    EventType.WORKSPACE_CHANGED_DURING_CAPTURE
                    if code == ErrorCode.WORKSPACE_CHANGED_DURING_CAPTURE else
                    EventType.CONTEXT_CAPTURE_FAILED,
                    project_id, actor, correlation_id,
                    context_item_id=context_item_id,
                    context_revision_id=revision_id,
                    workspace_item_id=workspace_item_id,
                    severity=EventSeverity.WARNING if cancelled else EventSeverity.ERROR,
                    previous_status=ContextRevisionCaptureStatus.CAPTURING.value,
                    new_status=new_status.value,
                    error_code=None if cancelled else code,
                    details={"exception_type": type(exc).__name__},
                ))
                uow.commit()

    @staticmethod
    def _file_producer(path: Path, chunk_size: int):
        def produce(output: BinaryIO) -> None:
            try:
                with path.open("rb") as stream:
                    while True:
                        chunk = stream.read(chunk_size)
                        if not chunk:
                            break
                        output.write(chunk)
            except FileNotFoundError as exc:
                raise ApplicationError(
                    ErrorCode.CONTEXT_CAPTURE_SOURCE_MISSING.value,
                    "Working Artifact disappeared during capture",
                ) from exc
            except OSError as exc:
                raise ApplicationError(
                    ErrorCode.CONTEXT_CAPTURE_SOURCE_UNREADABLE.value,
                    "Working Artifact could not be read during capture",
                ) from exc
        return produce

    def _project(self, uow, project_id):
        project = uow.projects.get(project_id)
        if project is None:
            raise EntityNotFoundError(f"project not found: {project_id}")
        if project.model_version != CURRENT_PROJECT_MODEL_VERSION:
            raise ApplicationError(
                "PROJECT_CONTEXT_UPGRADE_REQUIRED",
                "Project must be upgraded before Context capture",
            )
        return project

    def _event(self, event_type, project_id, actor, correlation_id, **kwargs):
        return ProcessingEvent(
            id=self._new_id(), event_type=event_type, project_id=project_id,
            actor=actor, occurred_at=self._clock(), severity=kwargs.pop("severity", EventSeverity.INFO),
            correlation_id=correlation_id, **kwargs,
        )

    @staticmethod
    def _required(value: str, name: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ApplicationError("INVALID_REQUEST", f"{name} must not be empty")
        return normalized

    @staticmethod
    def _error_code(exc: BaseException) -> ErrorCode:
        if isinstance(exc, ApplicationError):
            try:
                return ErrorCode(exc.code)
            except ValueError:
                return ErrorCode.CONTEXT_CAPTURE_FAILED
        if isinstance(exc, ConcurrentStateError):
            return ErrorCode.CONTEXT_WRITE_CONFLICT
        return ErrorCode.CONTEXT_CAPTURE_FAILED
