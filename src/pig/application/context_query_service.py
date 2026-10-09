from __future__ import annotations

from pathlib import Path

from pig.application.contracts import (
    ContextItemView,
    GetContextItemDetailsRequest,
    GetContextItemDetailsResult,
    GetProjectContextRequest,
    GetProjectContextResult,
)
from pig.application.errors import ApplicationError
from pig.application.ports import ProjectDatabaseProvider
from pig.domain.enums import (
    ContextFreshnessStatus,
    ContextLifecycleStatus,
    ContextRevisionCaptureStatus,
    WorkingContentStatus,
    WorkspaceItemLifecycleStatus,
)
from pig.domain.exceptions import EntityNotFoundError
from pig.domain.model_version import CURRENT_PROJECT_MODEL_VERSION


class ContextQueryService:
    """Read-only Context projections and deterministic freshness classification."""

    def __init__(self, *, database: ProjectDatabaseProvider) -> None:
        self._database = database

    def project_context(self, request: GetProjectContextRequest) -> GetProjectContextResult:
        project_id = self._required(request.project_id, "project_id")
        database_path = Path(request.database_path).resolve(strict=True)
        with self._database.unit_of_work(database_path) as uow:
            project = self._project(uow, project_id)
            all_sections = tuple(uow.context.sections_for_project(project_id))
            sections = tuple(
                value for value in all_sections
                if value.lifecycle_status == ContextLifecycleStatus.ACTIVE
            )
            removed_sections = tuple(
                value for value in all_sections
                if value.lifecycle_status == ContextLifecycleStatus.REMOVED
            )
            active_section_ids = {value.id for value in sections}
            placements = tuple(
                value for value in uow.context.placements_for_project(project_id)
                if value.lifecycle_status == ContextLifecycleStatus.ACTIVE
                and value.context_section_id in active_section_ids
            )
            placements_by_item = {}
            for placement in placements:
                placements_by_item.setdefault(placement.context_item_id, []).append(placement)
            views = []
            removed_views = []
            for item in uow.context.items_for_project(project_id):
                view = self._view(
                    uow, item, tuple(placements_by_item.get(item.id, ()))
                )
                if item.lifecycle_status == ContextLifecycleStatus.ACTIVE:
                    views.append(view)
                else:
                    removed_views.append(view)
        return GetProjectContextResult(
            project=project,
            sections=sections,
            items=tuple(views),
            placements=placements,
            unsectioned_item_ids=tuple(
                value.item.id for value in views if not value.effective_placements
            ),
            removed_sections=removed_sections,
            removed_items=tuple(removed_views),
        )

    def item_details(
        self, request: GetContextItemDetailsRequest
    ) -> GetContextItemDetailsResult:
        project_id = self._required(request.project_id, "project_id")
        database_path = Path(request.database_path).resolve(strict=True)
        with self._database.unit_of_work(database_path) as uow:
            project = self._project(uow, project_id)
            item = uow.context.get_item(request.context_item_id)
            if item is None or item.project_id != project_id:
                raise EntityNotFoundError(f"context item not found: {request.context_item_id}")
            sections = {
                value.id: value for value in uow.context.sections_for_project(project_id)
            }
            placements = tuple(
                value for value in uow.context.placements_for_item(item.id)
                if value.lifecycle_status == ContextLifecycleStatus.ACTIVE
                and sections.get(value.context_section_id) is not None
                and sections[value.context_section_id].lifecycle_status
                == ContextLifecycleStatus.ACTIVE
            )
            view = self._view(uow, item, placements)
            revisions = tuple(uow.context.revisions_for_item(item.id))
            annotations = tuple(uow.context.annotations_for_item(item.id))
        return GetContextItemDetailsResult(
            project=project,
            view=view,
            revisions=revisions,
            annotations=annotations,
        )

    def _view(self, uow, item, placements):
        workspace_item = uow.workspace.get_item(item.workspace_item_id)
        if workspace_item is None:
            raise EntityNotFoundError(f"workspace item not found: {item.workspace_item_id}")
        revision = (
            None
            if item.current_context_revision_id is None
            else uow.context.get_revision(item.current_context_revision_id)
        )
        return ContextItemView(
            item=item,
            workspace_item=workspace_item,
            current_revision=revision,
            freshness=self.freshness(uow, workspace_item, revision),
            effective_placements=placements,
        )

    @staticmethod
    def freshness(uow, workspace_item, revision):
        if (
            workspace_item.lifecycle_status != WorkspaceItemLifecycleStatus.ACTIVE
            or not uow.workspace.is_effectively_active(workspace_item.id)
        ):
            return ContextFreshnessStatus.WORKSPACE_MISSING
        if revision is None or revision.capture_status != ContextRevisionCaptureStatus.READY:
            return ContextFreshnessStatus.WORKSPACE_UNREADABLE
        working = uow.workspace.working_artifact_for_item(workspace_item.id)
        if working is None:
            return ContextFreshnessStatus.CURRENT
        if working.content_status == WorkingContentStatus.MISSING:
            return ContextFreshnessStatus.WORKSPACE_MISSING
        if working.content_status == WorkingContentStatus.UNREADABLE:
            return ContextFreshnessStatus.WORKSPACE_UNREADABLE
        if working.current_sha256 != revision.source_observed_sha256:
            return ContextFreshnessStatus.WORKSPACE_UPDATED
        return ContextFreshnessStatus.CURRENT

    @staticmethod
    def _project(uow, project_id):
        project = uow.projects.get(project_id)
        if project is None:
            raise EntityNotFoundError(f"project not found: {project_id}")
        if project.model_version != CURRENT_PROJECT_MODEL_VERSION:
            raise ApplicationError("PROJECT_CONTEXT_UPGRADE_REQUIRED", "Project must be upgraded")
        return project

    @staticmethod
    def _required(value: str, field: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ApplicationError("INVALID_REQUEST", f"{field} must not be empty")
        return normalized
