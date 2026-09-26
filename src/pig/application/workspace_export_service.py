from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Callable
from uuid import uuid4

from pig.application.contracts import (
    ExportWorkspaceItemsRequest,
    ExportWorkspaceItemsResult,
    MaterializeWorkspaceItemRequest,
    RefreshWorkingArtifactRequest,
)
from pig.application.errors import ApplicationError
from pig.application.operation_control import (
    OperationControl,
    OperationStage,
    ensure_operation_control,
)
from pig.application.ports import (
    OriginalSnapshotStore,
    ProjectDatabaseProvider,
    WorkingArtifactStore,
    WorkspaceExportDirectory,
    WorkspaceExportEntry,
    WorkspaceExportStore,
)
from pig.domain.entities import ProcessingEvent
from pig.domain.enums import (
    ErrorCode,
    EventSeverity,
    EventType,
    NodeProcessingStatus,
    WorkingContentStatus,
    WorkingRefreshReason,
    WorkspaceItemKind,
    WorkspaceExportKind,
)
from pig.domain.exceptions import EntityNotFoundError, InvariantViolationError
from pig.domain.model_version import WORKBENCH_MODEL_VERSION
from pig.domain.paths import safe_filesystem_segment


Clock = Callable[[], datetime]
IdGenerator = Callable[[], str]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid4())


class WorkspaceExportService:
    """Export current Workspace file bytes without rewriting source Containers."""

    def __init__(
        self,
        *,
        database: ProjectDatabaseProvider,
        originals: OriginalSnapshotStore,
        structure_service,
        working_file_service,
        working_store: WorkingArtifactStore,
        store: WorkspaceExportStore,
        clock: Clock = _utc_now,
        id_generator: IdGenerator = _new_id,
    ) -> None:
        self._database = database
        self._originals = originals
        self._structure = structure_service
        self._working_files = working_file_service
        self._working_store = working_store
        self._store = store
        self._clock = clock
        self._new_id = id_generator

    def export(
        self,
        request: ExportWorkspaceItemsRequest,
        *,
        control: OperationControl | None = None,
    ) -> ExportWorkspaceItemsResult:
        operation = ensure_operation_control(control)
        operation.start_stage(OperationStage.EXPORT_PREPARATION)
        operation.checkpoint()
        project_id = request.project_id.strip()
        actor = request.actor.strip()
        database_path = Path(request.database_path).expanduser().resolve(strict=False)
        destination = Path(request.destination_path).expanduser().resolve(strict=False)
        item_ids = tuple(dict.fromkeys(request.workspace_item_ids))
        if (
            not project_id
            or not actor
            or not database_path.is_absolute()
            or not destination.is_absolute()
            or not item_ids
            or any(not value.strip() for value in item_ids)
        ):
            raise ApplicationError("INVALID_REQUEST", "complete export identity is required")
        operation_id = self._new_id()
        project_path = database_path.parent.resolve(strict=False)
        try:
            destination.relative_to(project_path)
        except ValueError:
            pass
        else:
            raise ApplicationError(
                ErrorCode.EXPORT_DESTINATION_INVALID.value,
                "exports must be written outside the managed Project directory",
            )

        with self._database.unit_of_work(database_path) as uow:
            project = uow.projects.get(project_id)
            if project is None:
                raise EntityNotFoundError(f"project not found: {project_id}")
            self._project(project, database_path)
            records = tuple(uow.workspace.read_records_for_project(project_id))
            by_id = {record.item.id: record for record in records}
            selected = []
            for item_id in item_ids:
                record = by_id.get(item_id)
                if record is None:
                    raise EntityNotFoundError(f"workspace item not found: {item_id}")
                if not record.effectively_active:
                    raise ApplicationError(
                        "EXPORT_ITEM_DENIED",
                        "only effectively active Workspace items can be exported",
                        {"workspace_item_id": record.item.id},
                    )
                selected.append(record)
            if (
                len(selected) == 1
                and selected[0].item.item_kind == WorkspaceItemKind.FILE
            ):
                export_kind = WorkspaceExportKind.FILE
                export_items = tuple(selected)
                export_directories = ()
            elif (
                len(selected) == 1
                and selected[0].item.item_kind == WorkspaceItemKind.FOLDER
            ):
                export_kind = WorkspaceExportKind.DIRECTORY
                directory_root_id = selected[0].item.id
                subtree = self._active_subtree(directory_root_id, by_id)
                export_items = tuple(
                    value
                    for value in subtree
                    if value.item.item_kind == WorkspaceItemKind.FILE
                )
                export_directories = tuple(
                    value
                    for value in subtree
                    if value.item.item_kind != WorkspaceItemKind.FILE
                    and value.item.id != directory_root_id
                )
            else:
                export_kind = WorkspaceExportKind.ZIP
                expanded = []
                seen: set[str] = set()
                for value in selected:
                    if value.item.item_kind == WorkspaceItemKind.CONTAINER_VIEW:
                        raise ApplicationError(
                            "EXPORT_ITEM_DENIED",
                            "select an ordinary folder or terminal files for export",
                        )
                    candidates = (
                        (value,)
                        if value.item.item_kind == WorkspaceItemKind.FILE
                        else self._active_subtree(value.item.id, by_id)
                    )
                    for candidate in candidates:
                        if candidate.item.id not in seen:
                            seen.add(candidate.item.id)
                            expanded.append(candidate)
                export_items = tuple(
                    value
                    for value in expanded
                    if value.item.item_kind == WorkspaceItemKind.FILE
                )
                export_directories = tuple(
                    value
                    for value in expanded
                    if value.item.item_kind != WorkspaceItemKind.FILE
                )
            if any(
                value.item.origin_source_node_id is None
                for value in export_items
            ):
                raise ApplicationError(
                    "EXPORT_ITEM_DENIED",
                    "every exported file must be source-backed",
                )
            if export_kind == WorkspaceExportKind.DIRECTORY:
                relative_paths = {
                    record.item.id: self._relative_from_root(
                        record, by_id[directory_root_id]
                    )
                    for record in (*export_items, *export_directories)
                }
            else:
                relative_paths = {
                    record.item.id: self._safe_workspace_path(
                        record.workspace_path
                    )
                    for record in (*export_items, *export_directories)
                }
            source_node_ids = tuple(
                record.item.origin_source_node_id
                for record in export_items
                if record.working_artifact is None
                and record.item.origin_source_node_id is not None
            )
            direct_originals = uow.workspace.original_artifacts_for_source_nodes(
                source_node_ids
            )
            self._event(
                uow,
                EventType.WORKSPACE_EXPORT_REQUESTED,
                project_id,
                actor,
                operation_id,
                details={
                    "item_count": len(item_ids),
                    "export_kind": export_kind.value,
                    "destination": str(destination),
                },
            )
            uow.commit()

        operation.start_stage(
            OperationStage.EXPORT_PREPARATION,
            total_count=len(export_items),
            current_item=(
                None if not export_items else export_items[0].item.display_name
            ),
        )

        folded: dict[str, str] = {}
        for item_id, value in relative_paths.items():
            key = value.casefold()
            if key in folded:
                failure = ApplicationError(
                    ErrorCode.EXPORT_PATH_COLLISION.value,
                    "selected Workspace files collide in the export package",
                    {"first": folded[key], "second": item_id, "path": value},
                )
                self._failed(database_path, project_id, actor, operation_id, failure)
                raise failure
            folded[key] = item_id

        if export_kind == WorkspaceExportKind.ZIP and destination.suffix.lower() != ".zip":
            failure = ApplicationError(
                ErrorCode.EXPORT_DESTINATION_INVALID.value,
                "multi-file exports require a .zip destination",
            )
            self._failed(database_path, project_id, actor, operation_id, failure)
            raise failure
        try:
            entries = []
            for record in export_items:
                operation.checkpoint()
                item = record.item
                operation.update(current_item=item.display_name)
                artifact = record.working_artifact
                original = direct_originals.get(
                    item.origin_source_node_id or ""
                )
                if artifact is None and original is not None:
                    if (
                        record.source_node is None
                        or record.source_node.status != NodeProcessingStatus.SUCCESS
                    ):
                        raise ApplicationError(
                            "SOURCE_NODE_NOT_MATERIALIZABLE",
                            "source node is not a successful terminal file",
                        )
                    path = self._originals.artifact_path(project_path, original)
                    size = original.size
                    sha256 = original.sha256
                elif artifact is None:
                    materialized = self._structure.materialize(
                        MaterializeWorkspaceItemRequest(
                            project_id=project_id,
                            database_path=database_path,
                            workspace_item_id=item.id,
                            actor=actor,
                            policy=request.policy,
                        )
                    )
                    artifact = materialized.working_artifact
                    path = materialized.path
                    size = artifact.current_size
                    sha256 = artifact.current_sha256
                else:
                    path = None
                    checkpoint = record.current_revision
                    if (
                        checkpoint is not None
                        and checkpoint.size == artifact.current_size
                        and checkpoint.sha256 == artifact.current_sha256
                        and artifact.content_status
                        not in {
                            WorkingContentStatus.MISSING,
                            WorkingContentStatus.UNREADABLE,
                        }
                    ):
                        path = self._working_store.unchanged_path(
                            project_path,
                            artifact.storage_key,
                            expected_size=artifact.current_size,
                            expected_modified_at=checkpoint.file_modified_at,
                        )
                    if path is None:
                        refreshed = self._working_files.refresh(
                            RefreshWorkingArtifactRequest(
                                project_id=project_id,
                                database_path=database_path,
                                workspace_item_id=item.id,
                                actor=actor,
                                reason=WorkingRefreshReason.EXPLICIT,
                            )
                        )
                        artifact = refreshed.working_artifact
                        path = refreshed.path
                    if artifact.content_status in {
                        WorkingContentStatus.MISSING,
                        WorkingContentStatus.UNREADABLE,
                    }:
                        raise ApplicationError(
                            ErrorCode.EXPORT_FAILED.value,
                            "a selected Working File is unavailable",
                            {"workspace_item_id": item.id},
                        )
                    size = artifact.current_size
                    sha256 = artifact.current_sha256
                entries.append(
                    WorkspaceExportEntry(
                        workspace_item_id=item.id,
                        relative_path=relative_paths[item.id],
                        source_path=path,
                        size=size,
                        sha256=sha256,
                    )
                )
                operation.advance(count=1, current_item=item.display_name)
            total_bytes = sum(entry.size for entry in entries)
            warning = self._resource_warning(
                len(entries),
                total_bytes,
                request.policy.soft_warning_entry_count,
                request.policy.soft_warning_total_size,
            )
            if warning is not None:
                operation.update(warning=warning)
            free_bytes = self._store.available_space(destination)
            required_bytes = total_bytes + request.policy.minimum_free_space_bytes
            if free_bytes < required_bytes:
                raise ApplicationError(
                    "INSUFFICIENT_DISK_SPACE",
                    "Export destination does not have enough free space",
                    {
                        "required_bytes": required_bytes,
                        "available_bytes": free_bytes,
                        "export_bytes": total_bytes,
                    },
                )
            operation.checkpoint()
            stored = self._store.write(
                destination,
                operation_id,
                tuple(entries),
                tuple(
                    WorkspaceExportDirectory(
                        relative_path=relative_paths[value.item.id]
                    )
                    for value in export_directories
                ),
                export_kind=export_kind,
                allow_replace=request.confirmed_replace,
                maximum_total_size=request.policy.max_total_expanded_size,
                chunk_size=request.policy.io_chunk_size,
                control=operation,
            )
        except BaseException as exc:
            self._failed(database_path, project_id, actor, operation_id, exc)
            raise

        with self._database.unit_of_work(database_path) as uow:
            self._event(
                uow,
                EventType.WORKSPACE_EXPORT_COMPLETED,
                project_id,
                actor,
                operation_id,
                details={
                    "destination": str(stored.path),
                    "export_kind": export_kind.value,
                    "entry_count": stored.entry_count,
                    "size": stored.size,
                    "sha256": stored.sha256,
                },
            )
            uow.commit()
        return ExportWorkspaceItemsResult(
            project_id=project_id,
            workspace_item_ids=item_ids,
            destination_path=stored.path,
            export_kind=export_kind,
            entry_count=stored.entry_count,
            size=stored.size,
            sha256=stored.sha256,
        )

    @staticmethod
    def _active_subtree(root_id, by_id):
        children: dict[str | None, list] = {}
        for item_id, record in by_id.items():
            children.setdefault(
                record.placement.parent_workspace_item_id, []
            ).append(item_id)
        result = []
        queue = deque([root_id])
        while queue:
            current = queue.popleft()
            record = by_id.get(current)
            if record is None or not record.effectively_active:
                continue
            result.append(record)
            queue.extend(children.get(current, ()))
        return tuple(result)

    @staticmethod
    def _safe_workspace_path(workspace_path: str) -> str:
        parts = workspace_path.split("/")
        if not parts or any(not part for part in parts):
            raise InvariantViolationError("workspace path is invalid")
        return str(
            PurePosixPath(
                *(safe_filesystem_segment(part) for part in parts)
            )
        )

    @classmethod
    def _relative_from_root(cls, record, root) -> str:
        prefix = f"{root.workspace_path}/"
        if not record.workspace_path.startswith(prefix):
            raise InvariantViolationError(
                "item is outside the selected export folder"
            )
        relative = record.workspace_path[len(prefix) :]
        if not relative:
            raise InvariantViolationError("folder export root is not a content entry")
        return cls._safe_workspace_path(relative)

    def _failed(self, database_path, project_id, actor, operation_id, failure) -> None:
        try:
            code = (
                ErrorCode(failure.code)
                if isinstance(failure, ApplicationError)
                and failure.code in ErrorCode._value2member_map_
                else ErrorCode.EXPORT_FAILED
            )
            with self._database.unit_of_work(database_path) as uow:
                self._event(
                    uow,
                    EventType.WORKSPACE_EXPORT_FAILED,
                    project_id,
                    actor,
                    operation_id,
                    severity=(
                        EventSeverity.WARNING
                        if getattr(failure, "code", None)
                        == "OPERATION_CANCELLED"
                        else EventSeverity.ERROR
                    ),
                    error_code=code,
                    details={
                        "failure_code": getattr(
                            failure, "code", type(failure).__name__
                        )
                    },
                )
                uow.commit()
        except BaseException:
            return

    def _event(
        self,
        uow,
        event_type,
        project_id,
        actor,
        correlation_id,
        *,
        severity=EventSeverity.INFO,
        error_code=None,
        details=None,
    ) -> None:
        uow.processing.append_event(
            ProcessingEvent(
                id=self._new_id(),
                event_type=event_type,
                project_id=project_id,
                actor=actor,
                occurred_at=self._clock(),
                severity=severity,
                correlation_id=correlation_id,
                error_code=error_code,
                details={} if details is None else details,
            )
        )

    @staticmethod
    def _resource_warning(
        entry_count: int,
        total_size: int,
        entry_threshold: int,
        size_threshold: int,
    ) -> str | None:
        reasons = []
        if entry_count >= entry_threshold:
            reasons.append(f"{entry_count} entries")
        if total_size >= size_threshold:
            reasons.append(f"{total_size} bytes")
        if not reasons:
            return None
        return "Large export: " + ", ".join(reasons)

    @staticmethod
    def _project(project, database_path: Path) -> None:
        if project.model_version != WORKBENCH_MODEL_VERSION:
            raise ApplicationError(
                "UNSUPPORTED_PROJECT_MODEL_VERSION", "unsupported Project data model"
            )
        if database_path.parent.as_uri() != project.workspace_locator:
            raise ApplicationError(
                "PROJECT_DATABASE_MISMATCH", "database path is outside the Project workspace"
            )
