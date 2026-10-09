"""Read-only selection of immutable Context bytes for a future Pack export."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pig.application.context_query_service import ContextQueryService
from pig.application.contracts import (
    ContextPackPlanEntry,
    ContextPackPlanSection,
    GetContextPackPlanRequest,
    GetContextPackPlanResult,
)
from pig.application.errors import ApplicationError
from pig.application.ports import ProjectDatabaseProvider
from pig.domain.enums import (
    ContextContentObjectStatus,
    ContextFreshnessStatus,
    ContextLifecycleStatus,
    ContextRevisionCaptureStatus,
)
from pig.domain.exceptions import EntityNotFoundError
from pig.domain.model_version import CURRENT_PROJECT_MODEL_VERSION
from pig.domain.paths import safe_filesystem_segment


CONTEXT_PACK_MANIFEST_SCHEMA_VERSION = "1.0"


class ContextPackPlanService:
    def __init__(self, *, database: ProjectDatabaseProvider) -> None:
        self._database = database

    def get_plan(self, request: GetContextPackPlanRequest) -> GetContextPackPlanResult:
        project_id = request.project_id.strip()
        if not project_id:
            raise ApplicationError("INVALID_REQUEST", "project_id must not be empty")
        database_path = Path(request.database_path).resolve(strict=True)
        requested_ids = tuple(request.selected_item_ids)
        if len(set(requested_ids)) != len(requested_ids):
            raise ApplicationError("INVALID_REQUEST", "selected Context Items must be unique")
        choices = {}
        for choice in request.revision_choices:
            if choice.context_item_id in choices:
                raise ApplicationError("INVALID_REQUEST", "Revision choice repeated for Item")
            choices[choice.context_item_id] = choice.context_revision_id

        with self._database.unit_of_work(database_path) as uow:
            project = uow.projects.get(project_id)
            if project is None:
                raise EntityNotFoundError(f"project not found: {project_id}")
            if project.model_version != CURRENT_PROJECT_MODEL_VERSION:
                raise ApplicationError("PROJECT_CONTEXT_UPGRADE_REQUIRED", "Project must be upgraded")
            active_items = {
                item.id: item for item in uow.context.items_for_project(project_id)
                if item.lifecycle_status == ContextLifecycleStatus.ACTIVE
            }
            item_ids = requested_ids or tuple(active_items)
            if not item_ids:
                raise ApplicationError("CONTEXT_PACK_EMPTY", "Project Context has no active Items")
            if any(item_id not in active_items for item_id in item_ids):
                raise ApplicationError("CONTEXT_PACK_ITEM_INVALID", "only active Context Items can be selected")
            if set(choices) - set(item_ids):
                raise ApplicationError("CONTEXT_PACK_REVISION_INVALID", "Revision choice is outside selected Items")

            sections = tuple(
                section for section in uow.context.sections_for_project(project_id)
                if section.lifecycle_status == ContextLifecycleStatus.ACTIVE
            )
            section_ids = {section.id for section in sections}
            placements_by_item: dict[str, list] = {}
            for placement in uow.context.placements_for_project(project_id):
                if (placement.lifecycle_status == ContextLifecycleStatus.ACTIVE
                        and placement.context_section_id in section_ids):
                    placements_by_item.setdefault(placement.context_item_id, []).append(placement)
            entries = []
            warnings = []
            needs_unsectioned = False
            for ordinal, item_id in enumerate(item_ids):
                item = active_items[item_id]
                revision_id = choices.get(item_id, item.current_context_revision_id)
                revision = uow.context.get_revision(revision_id) if revision_id else None
                if (revision is None or revision.project_id != project_id
                        or revision.context_item_id != item_id
                        or revision.capture_status != ContextRevisionCaptureStatus.READY
                        or revision.content_object_id is None):
                    raise ApplicationError("CONTEXT_PACK_REVISION_INVALID", "selected Revision is not READY for its Item")
                content = uow.context.get_content_object(revision.content_object_id)
                if (content is None or content.project_id != project_id
                        or content.availability_status != ContextContentObjectStatus.AVAILABLE):
                    raise ApplicationError("CONTEXT_PACK_CONTENT_MISSING", "selected Context object is unavailable")
                workspace_item = uow.workspace.get_item(item.workspace_item_id)
                if workspace_item is None or workspace_item.project_id != project_id:
                    raise ApplicationError("CONTEXT_PACK_ITEM_INVALID", "Workspace origin is missing")
                freshness = ContextQueryService.freshness(uow, workspace_item, revision)
                if freshness != ContextFreshnessStatus.CURRENT:
                    warnings.append(item_id)
                placements = placements_by_item.get(item_id, ())
                if not placements:
                    needs_unsectioned = True
                annotations = uow.context.annotations_for_item(item_id)
                guidance = annotations[0] if annotations else None
                title = item.title_override or workspace_item.display_name
                entries.append(ContextPackPlanEntry(
                    context_item_id=item_id,
                    context_revision_id=revision.id,
                    content_object_id=content.id,
                    display_name=title,
                    relative_path=f"files/{item.id}/{safe_filesystem_segment(workspace_item.display_name)}",
                    size_bytes=content.size_bytes,
                    sha256=content.sha256,
                    ordinal=ordinal,
                    freshness=freshness,
                    section_ids=tuple(value.context_section_id for value in placements),
                    purpose=item.purpose,
                    guidance_body=None if guidance is None else guidance.body,
                    guidance_author=None if guidance is None else guidance.author,
                ))
            section_plan = tuple(
                ContextPackPlanSection(
                    source_section_id=value.id, name=value.name,
                    description=value.description, ordinal=value.ordinal,
                ) for value in sections
            )
            if needs_unsectioned:
                section_plan += (ContextPackPlanSection(
                    source_section_id=None, name="Unsectioned",
                    ordinal=max((value.ordinal for value in sections), default=-1) + 1,
                    is_unsectioned=True,
                ),)

        fingerprint_input = {
            "project_id": project_id,
            "context_revision": project.context_revision,
            "item_revisions": [(value.context_item_id, value.context_revision_id) for value in entries],
        }
        fingerprint = hashlib.sha256(json.dumps(
            fingerprint_input, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")).hexdigest()
        return GetContextPackPlanResult(
            project_id=project_id, project_name=project.name,
            context_revision=project.context_revision,
            manifest_schema_version=CONTEXT_PACK_MANIFEST_SCHEMA_VERSION,
            plan_fingerprint=fingerprint,
            total_bytes=sum(value.size_bytes for value in entries),
            sections=section_plan, entries=tuple(entries),
            warning_item_ids=tuple(warnings),
        )
