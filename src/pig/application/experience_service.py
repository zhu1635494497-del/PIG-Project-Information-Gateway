"""Controlled human-experience Actions and bounded read-only Queries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional
from uuid import uuid4

from pig.application.errors import ApplicationError
from pig.application.ports import ProjectDatabaseProvider
from pig.domain.entities import ProcessingEvent
from pig.domain.enums import EventSeverity, EventType
from pig.domain.exceptions import EntityNotFoundError, InvariantViolationError
from pig.domain.experience_entities import (
    ExperienceEventLink, ExperienceRevisionLink, ExperienceStateChange,
    ExperienceVersion, ProjectExperienceRecord,
)
from pig.domain.experience_policy import (
    ExperienceAction, ExperienceEvidenceRef, ExperienceEvidenceRole,
    ExperienceEventRef, ExperienceKind, ExperiencePolicy, ExperienceStatus,
    next_experience_status, validate_experience_content, validate_experience_links,
)
from pig.domain.model_version import CURRENT_PROJECT_MODEL_VERSION


@dataclass(frozen=True, slots=True)
class ExperienceEvidenceChoice:
    context_item_id: str
    context_revision_id: str
    role: ExperienceEvidenceRole = ExperienceEvidenceRole.SUPPORTS


@dataclass(frozen=True, slots=True)
class ExperienceMutationRequest:
    project_id: str
    database_path: Path
    actor: str
    expected_context_revision: int
    kind: ExperienceKind
    title: str
    body: str
    evidence: tuple[ExperienceEvidenceChoice, ...]
    event_ids: tuple[str, ...] = ()
    record_id: Optional[str] = None
    expected_record_version: Optional[int] = None


@dataclass(frozen=True, slots=True)
class ExperienceTransitionRequest:
    project_id: str
    database_path: Path
    actor: str
    expected_context_revision: int
    record_id: str
    expected_record_version: int


@dataclass(frozen=True, slots=True)
class ExperienceDetail:
    record: ProjectExperienceRecord
    versions: tuple[ExperienceVersion, ...]
    state_changes: tuple[ExperienceStateChange, ...]
    revision_links: tuple[ExperienceRevisionLink, ...]
    event_links: tuple[ExperienceEventLink, ...]


@dataclass(frozen=True, slots=True)
class ExperienceSummary:
    record: ProjectExperienceRecord
    title: str
    author: str


class ExperienceService:
    def __init__(self, *, database: ProjectDatabaseProvider,
                 policy: ExperiencePolicy = ExperiencePolicy(),
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                 id_generator: Callable[[], str] = lambda: str(uuid4())) -> None:
        self._database = database
        self._policy = policy
        self._clock = clock
        self._id = id_generator

    def create(self, request: ExperienceMutationRequest) -> ExperienceDetail:
        if request.record_id is not None or request.expected_record_version is not None:
            raise ApplicationError("INVALID_REQUEST", "creation cannot specify an existing record")
        with self._database.unit_of_work(self._db(request.database_path)) as uow:
            self._project(uow, request.project_id, request.expected_context_revision)
            self._validate_request(uow, request)
            now = self._clock()
            record_id = self._id()
            record = ProjectExperienceRecord(
                id=record_id, project_id=request.project_id, kind=request.kind,
                status=ExperienceStatus.DRAFT, current_version=1,
                created_at=now, updated_at=now)
            uow.experience.add_record(record)
            self._add_version(uow, request, record_id, 1, now)
            self._state(uow, record, None, ExperienceStatus.DRAFT, request.actor, now)
            self._advance_and_event(uow, request.project_id, request.expected_context_revision,
                                    request.actor, EventType.EXPERIENCE_CREATED,
                                    record_id, 1, None, ExperienceStatus.DRAFT, now)
            uow.commit()
            return self._detail(uow, record)

    def correct(self, request: ExperienceMutationRequest) -> ExperienceDetail:
        if not request.record_id or request.expected_record_version is None:
            raise ApplicationError("INVALID_REQUEST", "correction requires record and expected version")
        with self._database.unit_of_work(self._db(request.database_path)) as uow:
            self._project(uow, request.project_id, request.expected_context_revision)
            old = self._owned_record(uow, request.project_id, request.record_id)
            if old.current_version != request.expected_record_version or old.kind != request.kind:
                raise ApplicationError("EXPERIENCE_STALE", "experience version or kind changed")
            new_status = next_experience_status(old.status, ExperienceAction.EDIT)
            self._validate_request(uow, request)
            now = self._clock()
            version = old.current_version + 1
            updated = uow.experience.update_record(
                old.id, expected_version=old.current_version, expected_status=old.status,
                new_version=version, new_status=new_status, updated_at=now)
            self._add_version(uow, request, old.id, version, now)
            self._state(uow, updated, old.status, new_status, request.actor, now)
            self._advance_and_event(uow, request.project_id, request.expected_context_revision,
                                    request.actor, EventType.EXPERIENCE_CORRECTED,
                                    old.id, version, old.status, new_status, now)
            uow.commit()
            return self._detail(uow, updated)

    def confirm(self, request: ExperienceTransitionRequest) -> ExperienceDetail:
        return self._transition(request, ExperienceAction.CONFIRM, EventType.EXPERIENCE_CONFIRMED)

    def supersede(self, request: ExperienceTransitionRequest) -> ExperienceDetail:
        return self._transition(request, ExperienceAction.SUPERSEDE, EventType.EXPERIENCE_SUPERSEDED)

    def _transition(self, request: ExperienceTransitionRequest,
                    action: ExperienceAction, event_type: EventType) -> ExperienceDetail:
        with self._database.unit_of_work(self._db(request.database_path)) as uow:
            self._project(uow, request.project_id, request.expected_context_revision)
            old = self._owned_record(uow, request.project_id, request.record_id)
            if old.current_version != request.expected_record_version:
                raise ApplicationError("EXPERIENCE_STALE", "experience version changed")
            new_status = next_experience_status(old.status, action)
            if action == ExperienceAction.CONFIRM:
                links = uow.experience.revision_links_for_version(old.id, old.current_version)
                if not any(link.role == ExperienceEvidenceRole.SUPPORTS for link in links):
                    raise InvariantViolationError("confirmed experience requires supporting evidence")
                for link in links:
                    revision = uow.context.get_revision(link.context_revision_id)
                    if (revision is None or revision.project_id != request.project_id
                            or revision.context_item_id != link.context_item_id
                            or revision.capture_status.value != "READY"):
                        raise ApplicationError("EXPERIENCE_EVIDENCE_INVALID",
                                               "fixed supporting Revision is not READY")
            now = self._clock()
            updated = uow.experience.update_record(
                old.id, expected_version=old.current_version, expected_status=old.status,
                new_version=old.current_version, new_status=new_status, updated_at=now)
            self._state(uow, updated, old.status, new_status, request.actor, now)
            self._advance_and_event(uow, request.project_id, request.expected_context_revision,
                                    request.actor, event_type, old.id, old.current_version,
                                    old.status, new_status, now)
            uow.commit()
            return self._detail(uow, updated)

    def get(self, *, project_id: str, database_path: Path, record_id: str) -> ExperienceDetail:
        with self._database.unit_of_work(self._db(database_path)) as uow:
            self._project(uow, project_id)
            record = self._owned_record(uow, project_id, record_id)
            return self._detail(uow, record)

    def list(self, *, project_id: str, database_path: Path,
             status: Optional[ExperienceStatus] = None, limit: int = 50,
             offset: int = 0) -> tuple[ProjectExperienceRecord, ...]:
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
            raise ApplicationError("INVALID_REQUEST", "experience page limit must be 1-100")
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            raise ApplicationError("INVALID_REQUEST", "experience offset must be nonnegative")
        with self._database.unit_of_work(self._db(database_path)) as uow:
            self._project(uow, project_id)
            return tuple(uow.experience.list_records(project_id, status=status,
                                                     limit=limit, offset=offset))

    def list_summaries(self, *, project_id: str, database_path: Path,
                       limit: int = 50, offset: int = 0) -> tuple[ExperienceSummary, ...]:
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
            raise ApplicationError("INVALID_REQUEST", "experience page limit must be 1-100")
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            raise ApplicationError("INVALID_REQUEST", "experience offset must be nonnegative")
        with self._database.unit_of_work(self._db(database_path)) as uow:
            self._project(uow, project_id)
            records = uow.experience.list_records(project_id, status=None,
                                                  limit=limit, offset=offset)
            summaries = []
            for record in records:
                version = uow.experience.get_version(record.id, record.current_version)
                if version is None:
                    raise InvariantViolationError("experience current version is missing")
                summaries.append(ExperienceSummary(record, version.title, version.author))
            return tuple(summaries)

    def list_observed_events(self, *, project_id: str, database_path: Path,
                             limit: int = 50) -> tuple[ProcessingEvent, ...]:
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
            raise ApplicationError("INVALID_REQUEST", "event page limit must be 1-100")
        with self._database.unit_of_work(self._db(database_path)) as uow:
            self._project(uow, project_id)
            return tuple(uow.processing.recent_events_for_project(project_id, limit=limit))

    @staticmethod
    def _db(path: Path) -> Path:
        return Path(path).resolve(strict=True)

    @staticmethod
    def _project(uow, project_id: str, expected_revision: Optional[int] = None):
        project = uow.projects.get(project_id)
        if project is None:
            raise EntityNotFoundError(f"project not found: {project_id}")
        if project.model_version != CURRENT_PROJECT_MODEL_VERSION:
            raise ApplicationError("PROJECT_CONTEXT_UPGRADE_REQUIRED", "Project must be upgraded")
        if expected_revision is not None and project.context_revision != expected_revision:
            raise ApplicationError("CONTEXT_WRITE_CONFLICT", "Project Context changed")
        return project

    @staticmethod
    def _owned_record(uow, project_id: str, record_id: str) -> ProjectExperienceRecord:
        record = uow.experience.get_record(record_id)
        if record is None or record.project_id != project_id:
            raise EntityNotFoundError(f"experience record not found: {record_id}")
        return record

    def _validate_request(self, uow, request: ExperienceMutationRequest) -> None:
        if not isinstance(request.kind, ExperienceKind):
            raise ApplicationError("INVALID_REQUEST", "invalid experience kind")
        if not request.evidence:
            raise InvariantViolationError("experience requires at least one fixed Revision")
        validate_experience_content(title=request.title, body=request.body,
                                    author=request.actor, policy=self._policy)
        if len(request.actor) > 255:
            raise ApplicationError("INVALID_REQUEST", "experience author is too long")
        if any(ord(char) < 32 for char in request.actor):
            raise ApplicationError("INVALID_REQUEST", "experience author contains control characters")
        references = []
        for choice in request.evidence:
            revision = uow.context.get_revision(choice.context_revision_id)
            if revision is None or revision.project_id != request.project_id:
                raise ApplicationError("EXPERIENCE_EVIDENCE_INVALID", "Revision is outside project")
            if revision.context_item_id != choice.context_item_id:
                raise ApplicationError("EXPERIENCE_EVIDENCE_INVALID", "Revision does not belong to Item")
            references.append(ExperienceEvidenceRef(
                project_id=revision.project_id, context_item_id=revision.context_item_id,
                context_revision_id=revision.id, capture_status=revision.capture_status,
                role=choice.role))
        events = []
        for event_id in request.event_ids:
            event = uow.processing.get_event(event_id)
            if event is None or event.project_id != request.project_id:
                raise ApplicationError("EXPERIENCE_EVENT_INVALID", "Event is outside project")
            events.append(ExperienceEventRef(project_id=event.project_id, event_id=event.id))
        validate_experience_links(project_id=request.project_id, evidence=tuple(references),
                                  events=tuple(events), policy=self._policy)

    @staticmethod
    def _detail(uow, record: ProjectExperienceRecord) -> ExperienceDetail:
        return ExperienceDetail(
            record=record,
            versions=tuple(uow.experience.versions_for_record(record.id)),
            state_changes=tuple(uow.experience.state_changes_for_record(record.id)),
            revision_links=tuple(uow.experience.revision_links_for_version(
                record.id, record.current_version)),
            event_links=tuple(uow.experience.event_links_for_version(
                record.id, record.current_version)),
        )

    def _add_version(self, uow, request: ExperienceMutationRequest,
                     record_id: str, version: int, now: datetime) -> None:
        uow.experience.add_version(ExperienceVersion(
            record_id=record_id, project_id=request.project_id, version=version,
            title=request.title, body=request.body, author=request.actor, recorded_at=now))
        uow.experience.add_revision_links(tuple(ExperienceRevisionLink(
            record_id=record_id, project_id=request.project_id, version=version,
            context_item_id=choice.context_item_id, context_revision_id=choice.context_revision_id,
            role=choice.role) for choice in request.evidence))
        uow.experience.add_event_links(tuple(ExperienceEventLink(
            record_id=record_id, project_id=request.project_id, version=version,
            event_id=event_id) for event_id in request.event_ids))

    def _state(self, uow, record: ProjectExperienceRecord,
               old: Optional[ExperienceStatus], new: ExperienceStatus,
               actor: str, now: datetime) -> None:
        uow.experience.add_state_change(ExperienceStateChange(
            id=self._id(), project_id=record.project_id, record_id=record.id,
            version=record.current_version, from_status=old, to_status=new,
            actor=actor, occurred_at=now))

    def _advance_and_event(self, uow, project_id: str, expected_revision: int,
                           actor: str, event_type: EventType, record_id: str,
                           version: int, old: Optional[ExperienceStatus],
                           new: ExperienceStatus, now: datetime) -> None:
        uow.projects.advance_context_revision(project_id, expected_revision, updated_at=now)
        uow.processing.append_event(ProcessingEvent(
            id=self._id(), event_type=event_type, project_id=project_id,
            actor=actor, occurred_at=now, severity=EventSeverity.INFO,
            correlation_id=self._id(), previous_status=old.value if old else None,
            new_status=new.value, details={"record_id": record_id, "version": version},
        ))
