"""In-memory V2.4.1 Context Bundle extension contract.

No database read, filesystem publication, model call, or external transmission occurs here.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from pig.domain.exceptions import InvariantViolationError
from pig.domain.experience_policy import (
    ExperienceEvidenceRef,
    ExperienceEventRef,
    ExperienceKind,
    ExperiencePolicy,
    ExperienceStatus,
    missing_bundle_evidence,
    validate_experience_content,
    validate_experience_links,
)


CONTEXT_BUNDLE_SCHEMA_VERSION = "2.0"


@dataclass(frozen=True, slots=True)
class BundleExperienceRecord:
    id: str
    version: int
    kind: ExperienceKind
    status: ExperienceStatus
    title: str
    body: str
    author: str
    recorded_at: datetime
    revision_links: tuple[ExperienceEvidenceRef, ...]
    event_links: tuple[ExperienceEventRef, ...] = ()


@dataclass(frozen=True, slots=True)
class BundleObservedEvent:
    project_id: str
    id: str
    type: str
    occurred_at: datetime
    actor: str


def extend_context_manifest_v2(
    *,
    base_manifest: Mapping[str, Any],
    records: Sequence[BundleExperienceRecord],
    observed_events: Sequence[BundleObservedEvent],
    policy: ExperiencePolicy = ExperiencePolicy(),
) -> dict[str, Any]:
    """Return a new 2.0 manifest without broadening the selected file set.

    V2.4.2 will call this only after a read-only plan and physical preflight.
    The producer remains responsible for resolving IDs against the same Project
    transaction and for exposing the exact Bundle selection to the user.
    """
    if base_manifest.get("schema_version") != "1.0":
        raise InvariantViolationError("Bundle base schema must be 1.0")
    project = base_manifest.get("project")
    if not isinstance(project, dict) or not isinstance(project.get("id"), str):
        raise InvariantViolationError("Bundle project identity is missing")
    project_id = project["id"]
    entries = base_manifest.get("entries")
    if not isinstance(entries, list):
        raise InvariantViolationError("Bundle entries are missing")
    included = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise InvariantViolationError("Bundle entry is invalid")
        item_id = entry.get("context_item_id")
        revision_id = entry.get("context_revision_id")
        if not isinstance(item_id, str) or not isinstance(revision_id, str):
            raise InvariantViolationError("Bundle entry identity is invalid")
        included.add((item_id, revision_id))

    event_by_id: dict[str, BundleObservedEvent] = {}
    for event in observed_events:
        if (event.project_id != project_id or not event.id.strip()
                or not event.type.strip() or not event.actor.strip()):
            raise InvariantViolationError("Bundle Event identity is invalid")
        if event.id in event_by_id:
            raise InvariantViolationError("Bundle Event is repeated")
        event_by_id[event.id] = event

    seen_records: set[str] = set()
    used_events: set[str] = set()
    rendered_records = []
    for record in records:
        if not record.id.strip() or record.id in seen_records or record.version < 1:
            raise InvariantViolationError("Bundle experience identity is invalid or repeated")
        if not isinstance(record.kind, ExperienceKind) or not isinstance(record.status, ExperienceStatus):
            raise InvariantViolationError("Bundle experience kind or status is invalid")
        seen_records.add(record.id)
        validate_experience_content(
            title=record.title, body=record.body, author=record.author, policy=policy,
        )
        validate_experience_links(
            project_id=project_id, evidence=record.revision_links,
            events=record.event_links, policy=policy,
            require_support=record.status == ExperienceStatus.CONFIRMED,
        )
        if missing_bundle_evidence(
            evidence=record.revision_links,
            selected_revision_ids=tuple(revision for _item, revision in included),
        ) or any(
            (link.context_item_id, link.context_revision_id) not in included
            for link in record.revision_links
        ):
            raise InvariantViolationError("Bundle experience has missing evidence")
        event_ids = {link.event_id for link in record.event_links}
        if event_ids - event_by_id.keys():
            raise InvariantViolationError("Bundle experience has missing observed Event")
        used_events.update(event_ids)
        rendered_records.append({
            "id": record.id,
            "version": record.version,
            "kind": record.kind.value,
            "status": record.status.value,
            "title": record.title,
            "body": record.body,
            "author": record.author,
            "recorded_at": _utc_timestamp(record.recorded_at),
            "revision_links": [{
                "context_item_id": link.context_item_id,
                "context_revision_id": link.context_revision_id,
                "role": link.role.value,
            } for link in record.revision_links],
            "event_ids": sorted(event_ids),
        })
    if set(event_by_id) != used_events:
        raise InvariantViolationError("Bundle contains unreferenced observed Event")

    extended = deepcopy(dict(base_manifest))
    extended["schema_version"] = CONTEXT_BUNDLE_SCHEMA_VERSION
    extended["experience_records"] = rendered_records
    extended["observed_events"] = [{
        "id": event_by_id[event_id].id,
        "type": event_by_id[event_id].type,
        "occurred_at": _utc_timestamp(event_by_id[event_id].occurred_at),
        "actor": event_by_id[event_id].actor,
    } for event_id in sorted(used_events)]
    return extended


def _utc_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise InvariantViolationError("Bundle timestamp must include timezone")
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")
