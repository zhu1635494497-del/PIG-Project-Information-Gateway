from __future__ import annotations

from pathlib import Path

from pig.application.contracts import (
    GetWorkspaceItemRequest,
    GetWorkspaceItemResult,
    GetWorkspaceTreeRequest,
    GetWorkspaceTreeResult,
    SearchWorkspaceItemsRequest,
    SearchWorkspaceItemsResult,
    WorkspaceItemView,
)
from pig.application.errors import ApplicationError
from pig.application.ports import ProjectDatabaseProvider
from pig.domain.enums import (
    NodeFormat,
    WorkingContentStatus,
    WorkspaceItemLifecycleStatus,
)
from pig.domain.exceptions import EntityNotFoundError
from pig.domain.model_version import WORKBENCH_MODEL_VERSION


class WorkspaceQueryService:
    """Read-only Workspace projection for UI and future Tool callers."""

    def __init__(self, *, database: ProjectDatabaseProvider) -> None:
        self._database = database

    def tree(self, request: GetWorkspaceTreeRequest) -> GetWorkspaceTreeResult:
        project_id, database_path = self._identity(
            request.project_id, request.database_path
        )
        project, views = self._project_views(project_id, database_path)
        active = tuple(
            view
            for view in views
            if view.item.lifecycle_status == WorkspaceItemLifecycleStatus.ACTIVE
            and view.effectively_active
        )
        deleted = tuple(
            view
            for view in views
            if view.item.lifecycle_status == WorkspaceItemLifecycleStatus.DELETED
        )
        return GetWorkspaceTreeResult(
            project=project,
            workspace_revision=project.workspace_revision,
            items=active,
            deleted_items=deleted,
        )

    def item(self, request: GetWorkspaceItemRequest) -> GetWorkspaceItemResult:
        project_id, database_path = self._identity(
            request.project_id, request.database_path
        )
        with self._database.unit_of_work(database_path) as uow:
            project = uow.projects.get(project_id)
            if project is None:
                raise EntityNotFoundError(f"project not found: {project_id}")
            self._project(project, database_path)
            record = uow.workspace.read_record_for_item(
                project_id, request.workspace_item_id
            )
            if record is None:
                raise EntityNotFoundError(
                    f"workspace item not found: {request.workspace_item_id}"
                )
            view = self._view(record)
        return GetWorkspaceItemResult(project=project, view=view)

    def search(
        self, request: SearchWorkspaceItemsRequest
    ) -> SearchWorkspaceItemsResult:
        project_id, database_path = self._identity(
            request.project_id, request.database_path
        )
        if not isinstance(request.limit, int) or isinstance(request.limit, bool) or not 1 <= request.limit <= 500:
            raise ApplicationError("INVALID_REQUEST", "limit must be between 1 and 500")
        if not isinstance(request.offset, int) or isinstance(request.offset, bool) or request.offset < 0:
            raise ApplicationError("INVALID_REQUEST", "offset must be nonnegative")
        formats = self._enum_values(request.formats, NodeFormat, "formats")
        content = self._enum_values(
            request.content_statuses, WorkingContentStatus, "content_statuses"
        )
        lifecycle = self._enum_values(
            request.lifecycle_statuses,
            WorkspaceItemLifecycleStatus,
            "lifecycle_statuses",
        )
        query = "" if request.query is None else request.query.strip().casefold()
        with self._database.unit_of_work(database_path) as uow:
            project = uow.projects.get(project_id)
            if project is None:
                raise EntityNotFoundError(f"project not found: {project_id}")
            self._project(project, database_path)
            records, total = uow.workspace.search_read_records(
                project_id,
                query=query,
                formats=formats,
                content_statuses=content,
                lifecycle_statuses=lifecycle,
                limit=request.limit,
                offset=request.offset,
            )
            page = tuple(self._view(record) for record in records)
        return SearchWorkspaceItemsResult(
            project_id=project_id,
            items=page,
            total=total,
            limit=request.limit,
            offset=request.offset,
            has_more=request.offset + len(page) < total,
        )

    def _project_views(self, project_id: str, database_path: Path):
        with self._database.unit_of_work(database_path) as uow:
            project = uow.projects.get(project_id)
            if project is None:
                raise EntityNotFoundError(f"project not found: {project_id}")
            self._project(project, database_path)
            records = uow.workspace.read_records_for_project(project_id)
            views = tuple(self._view(record) for record in records)
        return project, tuple(views)

    @staticmethod
    def _view(record) -> WorkspaceItemView:
        return WorkspaceItemView(
            item=record.item,
            placement=record.placement,
            workspace_path=record.workspace_path,
            effectively_active=record.effectively_active,
            source_node=record.source_node,
            source=record.source,
            working_artifact=record.working_artifact,
            current_revision=record.current_revision,
            previous_revision=record.previous_revision,
        )

    @staticmethod
    def _enum_values(values, enum_type, field):
        if any(not isinstance(value, enum_type) for value in values):
            raise ApplicationError("INVALID_REQUEST", f"{field} contains an invalid value")
        return tuple(dict.fromkeys(values))

    @staticmethod
    def _identity(project_id: str, database_path: Path) -> tuple[str, Path]:
        project = project_id.strip()
        path = Path(database_path).expanduser().resolve(strict=False)
        if not project or not path.is_absolute():
            raise ApplicationError(
                "INVALID_REQUEST", "project_id and absolute database_path are required"
            )
        return project, path

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
