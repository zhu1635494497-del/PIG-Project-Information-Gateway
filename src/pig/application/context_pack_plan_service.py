"""Read-only selection of immutable Context bytes for a future Pack export."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pig.application.context_query_service import ContextQueryService
from pig.application.experience_contracts import (
    CONTEXT_BUNDLE_SCHEMA_VERSION, BundleExperienceRecord, BundleObservedEvent,
)
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
from pig.domain.experience_policy import ExperienceEvidenceRef, ExperienceEventRef
from pig.domain.model_version import CURRENT_PROJECT_MODEL_VERSION
from pig.domain.paths import safe_filesystem_segment


CONTEXT_PACK_MANIFEST_SCHEMA_VERSION = "1.0"


def _pack_filename(display_name: str, used: set[str]) -> str:
    """Choose a readable, Windows-safe filename without hiding duplicate items."""
    filename = safe_filesystem_segment(display_name)
    stem, suffix = Path(filename).stem, Path(filename).suffix
    candidate = filename
    number = 2
    while candidate.casefold() in used:
        marker = f" ({number})"
        candidate = f"{stem[:180 - len(suffix) - len(marker)].rstrip(' .') or 'file'}{marker}{suffix}"
        number += 1
    used.add(candidate.casefold())
    return candidate


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
        record_ids = tuple(request.selected_record_ids)
        if len(record_ids) > 100 or len(set(record_ids)) != len(record_ids):
            raise ApplicationError("INVALID_REQUEST", "selected experience records must be unique and bounded")
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
            used_filenames: set[str] = set()
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
                    relative_path=f"files/{_pack_filename(workspace_item.display_name, used_filenames)}",
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

            included_revisions = {entry.context_revision_id for entry in entries}
            experience_records = []
            observed_events_by_id = {}
            for record_id in record_ids:
                record = uow.experience.get_record(record_id)
                if record is None or record.project_id != project_id:
                    raise ApplicationError("CONTEXT_BUNDLE_RECORD_INVALID", "record is outside project")
                versions = uow.experience.versions_for_record(record_id)
                version = next((value for value in versions
                                if value.version == record.current_version), None)
                if version is None:
                    raise ApplicationError("CONTEXT_BUNDLE_RECORD_INVALID", "record text version is missing")
                links = uow.experience.revision_links_for_version(record_id, version.version)
                if any(link.context_revision_id not in included_revisions for link in links):
                    raise ApplicationError("CONTEXT_BUNDLE_EVIDENCE_MISSING",
                                           "selected files omit a linked fixed Revision")
                evidence = []
                for link in links:
                    revision = uow.context.get_revision(link.context_revision_id)
                    if revision is None or revision.project_id != project_id:
                        raise ApplicationError("CONTEXT_BUNDLE_EVIDENCE_MISSING", "linked Revision is missing")
                    evidence.append(ExperienceEvidenceRef(
                        project_id=project_id, context_item_id=link.context_item_id,
                        context_revision_id=link.context_revision_id,
                        capture_status=revision.capture_status, role=link.role))
                event_links = []
                for link in uow.experience.event_links_for_version(record_id, version.version):
                    event = uow.processing.get_event(link.event_id)
                    if event is None or event.project_id != project_id:
                        raise ApplicationError("CONTEXT_BUNDLE_EVENT_MISSING", "linked Event is missing")
                    event_links.append(ExperienceEventRef(project_id=project_id, event_id=event.id))
                    observed_events_by_id[event.id] = BundleObservedEvent(
                        project_id=project_id, id=event.id, type=event.event_type.value,
                        occurred_at=event.occurred_at, actor=event.actor)
                experience_records.append(BundleExperienceRecord(
                    id=record.id, version=version.version, kind=record.kind,
                    status=record.status, title=version.title, body=version.body,
                    author=version.author, recorded_at=version.recorded_at,
                    revision_links=tuple(evidence), event_links=tuple(event_links)))

        fingerprint_input = {
            "project_id": project_id,
            "context_revision": project.context_revision,
            "item_revisions": [(value.context_item_id, value.context_revision_id) for value in entries],
            "experience_records": [(value.id, value.version) for value in experience_records],
        }
        fingerprint = hashlib.sha256(json.dumps(
            fingerprint_input, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")).hexdigest()
        return GetContextPackPlanResult(
            project_id=project_id, project_name=project.name,
            context_revision=project.context_revision,
            manifest_schema_version=(CONTEXT_BUNDLE_SCHEMA_VERSION if experience_records
                                     else CONTEXT_PACK_MANIFEST_SCHEMA_VERSION),
            plan_fingerprint=fingerprint,
            total_bytes=sum(value.size_bytes for value in entries),
            sections=section_plan, entries=tuple(entries),
            warning_item_ids=tuple(warnings),
            experience_records=tuple(experience_records),
            observed_events=tuple(observed_events_by_id[key] for key in sorted(observed_events_by_id)),
        )
