"""V2.4.1 domain rules for human-authored project experience.

This module defines a bounded contract. Persistence and UI actions arrive in V2.4.2.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from pig.domain.enums import ContextRevisionCaptureStatus
from pig.domain.exceptions import InvariantViolationError


class ExperienceKind(str, Enum):
    JUDGMENT = "JUDGMENT"
    DECISION = "DECISION"
    LESSON = "LESSON"


class ExperienceStatus(str, Enum):
    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"
    SUPERSEDED = "SUPERSEDED"


class ExperienceAction(str, Enum):
    EDIT = "EDIT"
    CONFIRM = "CONFIRM"
    SUPERSEDE = "SUPERSEDE"


class ExperienceEvidenceRole(str, Enum):
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    BACKGROUND = "BACKGROUND"


@dataclass(frozen=True, slots=True)
class ExperienceEvidenceRef:
    project_id: str
    context_item_id: str
    context_revision_id: str
    capture_status: ContextRevisionCaptureStatus
    role: ExperienceEvidenceRole


@dataclass(frozen=True, slots=True)
class ExperienceEventRef:
    project_id: str
    event_id: str


@dataclass(frozen=True, slots=True)
class ExperiencePolicy:
    maximum_title_characters: int = 200
    maximum_body_characters: int = 10_000
    maximum_revision_links: int = 50
    maximum_event_links: int = 50

    def __post_init__(self) -> None:
        if min(
            self.maximum_title_characters,
            self.maximum_body_characters,
            self.maximum_revision_links,
            self.maximum_event_links,
        ) <= 0:
            raise ValueError("experience limits must be positive")


def validate_experience_content(
    *, title: str, body: str, author: str, policy: ExperiencePolicy
) -> None:
    """Validate authored text without rewriting the user's wording."""
    if not title.strip() or len(title) > policy.maximum_title_characters:
        raise InvariantViolationError("experience title is empty or too long")
    if not body.strip() or len(body) > policy.maximum_body_characters:
        raise InvariantViolationError("experience body is empty or too long")
    if not author.strip():
        raise InvariantViolationError("experience author is empty")


def validate_experience_links(
    *,
    project_id: str,
    evidence: tuple[ExperienceEvidenceRef, ...],
    events: tuple[ExperienceEventRef, ...],
    policy: ExperiencePolicy,
    require_support: bool = False,
) -> None:
    """Check scope and uniqueness before Application persistence.

    The repository must still verify that each referenced Item, Revision, and
    Event exists and belongs to this project when the transaction commits.
    """
    if not project_id.strip():
        raise InvariantViolationError("experience project is empty")
    if len(evidence) > policy.maximum_revision_links or len(events) > policy.maximum_event_links:
        raise InvariantViolationError("experience link limit exceeded")
    revision_ids: set[str] = set()
    for link in evidence:
        if not isinstance(link.role, ExperienceEvidenceRole):
            raise InvariantViolationError("experience evidence role is invalid")
        if not isinstance(link.capture_status, ContextRevisionCaptureStatus):
            raise InvariantViolationError("experience evidence status is invalid")
        if link.project_id != project_id or not link.context_item_id.strip():
            raise InvariantViolationError("experience evidence is outside project or Item")
        if not link.context_revision_id.strip() or link.context_revision_id in revision_ids:
            raise InvariantViolationError("experience evidence Revision is empty or repeated")
        if link.capture_status != ContextRevisionCaptureStatus.READY:
            raise InvariantViolationError("experience evidence Revision must be READY")
        revision_ids.add(link.context_revision_id)
    event_ids: set[str] = set()
    for link in events:
        if link.project_id != project_id or not link.event_id.strip() or link.event_id in event_ids:
            raise InvariantViolationError("experience Event is outside project, empty, or repeated")
        event_ids.add(link.event_id)
    if require_support and not any(
        link.role == ExperienceEvidenceRole.SUPPORTS for link in evidence
    ):
        raise InvariantViolationError("confirmed experience requires supporting evidence")


def next_experience_status(
    current: ExperienceStatus, action: ExperienceAction
) -> ExperienceStatus:
    """A confirmed edit creates a new draft version; superseded is terminal."""
    transitions = {
        (ExperienceStatus.DRAFT, ExperienceAction.EDIT): ExperienceStatus.DRAFT,
        (ExperienceStatus.DRAFT, ExperienceAction.CONFIRM): ExperienceStatus.CONFIRMED,
        (ExperienceStatus.CONFIRMED, ExperienceAction.EDIT): ExperienceStatus.DRAFT,
        (ExperienceStatus.CONFIRMED, ExperienceAction.SUPERSEDE): ExperienceStatus.SUPERSEDED,
    }
    try:
        return transitions[(current, action)]
    except KeyError as exc:
        raise InvariantViolationError("invalid experience state transition") from exc


def missing_bundle_evidence(
    *, evidence: tuple[ExperienceEvidenceRef, ...], selected_revision_ids: tuple[str, ...]
) -> tuple[str, ...]:
    """Return linked Revisions absent from the explicit export selection.

    The Pack planner must block publication if this result is non-empty. This
    function never expands the export selection on the user's behalf.
    """
    selected = set(selected_revision_ids)
    return tuple(sorted({
        link.context_revision_id for link in evidence
        if link.context_revision_id not in selected
    }))


def referenced_bundle_events(events: tuple[ExperienceEventRef, ...]) -> tuple[str, ...]:
    """Derive only the safe Event snapshots linked by selected records."""
    return tuple(sorted({link.event_id for link in events}))
