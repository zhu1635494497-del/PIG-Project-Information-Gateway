"""Persistent human-authored experience facts, separate from observed Events and AI drafts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from pig.domain.experience_policy import (
    ExperienceEvidenceRole, ExperienceKind, ExperienceStatus,
)


@dataclass(frozen=True, slots=True)
class ProjectExperienceRecord:
    id: str
    project_id: str
    kind: ExperienceKind
    status: ExperienceStatus
    current_version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ExperienceVersion:
    record_id: str
    project_id: str
    version: int
    title: str
    body: str
    author: str
    recorded_at: datetime


@dataclass(frozen=True, slots=True)
class ExperienceStateChange:
    id: str
    project_id: str
    record_id: str
    version: int
    from_status: ExperienceStatus | None
    to_status: ExperienceStatus
    actor: str
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class ExperienceRevisionLink:
    record_id: str
    project_id: str
    version: int
    context_item_id: str
    context_revision_id: str
    role: ExperienceEvidenceRole


@dataclass(frozen=True, slots=True)
class ExperienceEventLink:
    record_id: str
    project_id: str
    version: int
    event_id: str
