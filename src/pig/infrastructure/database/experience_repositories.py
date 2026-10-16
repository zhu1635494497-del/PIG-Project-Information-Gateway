"""Relational V2.4 human-experience repository; no AI-generated facts live here."""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Sequence

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from pig.domain.experience_entities import (
    ProjectExperienceRecord, ExperienceVersion, ExperienceStateChange,
    ExperienceRevisionLink, ExperienceEventLink,
)
from pig.domain.experience_policy import ExperienceStatus
from pig.domain.exceptions import ConcurrentStateError
from pig.infrastructure.database import models


def _record(row: models.ExperienceRecordModel) -> ProjectExperienceRecord:
    return ProjectExperienceRecord(**{
        key: getattr(row, key) for key in (
            "id", "project_id", "kind", "status", "current_version", "created_at", "updated_at")
    })


def _version(row: models.ExperienceVersionModel) -> ExperienceVersion:
    return ExperienceVersion(**{
        key: getattr(row, key) for key in (
            "record_id", "project_id", "version", "title", "body", "author", "recorded_at")
    })


def _state(row: models.ExperienceStateChangeModel) -> ExperienceStateChange:
    return ExperienceStateChange(
        id=row.id, project_id=row.project_id, record_id=row.record_id,
        version=row.version,
        from_status=ExperienceStatus(row.from_status) if row.from_status else None,
        to_status=row.to_status, actor=row.actor, occurred_at=row.occurred_at,
    )


def _revision_link(row: models.ExperienceRevisionLinkModel) -> ExperienceRevisionLink:
    return ExperienceRevisionLink(**{
        key: getattr(row, key) for key in (
            "record_id", "project_id", "version", "context_item_id", "context_revision_id", "role")
    })


def _event_link(row: models.ExperienceEventLinkModel) -> ExperienceEventLink:
    return ExperienceEventLink(**{
        key: getattr(row, key) for key in (
            "record_id", "project_id", "version", "event_id")
    })


class SqlAlchemyExperienceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_record(self, value: ProjectExperienceRecord) -> None:
        self._session.add(models.ExperienceRecordModel(**{
            key: getattr(value, key) for key in (
                "id", "project_id", "kind", "status", "current_version", "created_at", "updated_at")
        }))
        self._session.flush()

    def get_record(self, record_id: str) -> Optional[ProjectExperienceRecord]:
        row = self._session.get(models.ExperienceRecordModel, record_id)
        return _record(row) if row else None

    def list_records(self, project_id: str, *, status: Optional[ExperienceStatus],
                     limit: int, offset: int) -> Sequence[ProjectExperienceRecord]:
        statement = select(models.ExperienceRecordModel).where(
            models.ExperienceRecordModel.project_id == project_id)
        if status is not None:
            statement = statement.where(models.ExperienceRecordModel.status == status)
        rows = self._session.scalars(statement.order_by(
            models.ExperienceRecordModel.updated_at.desc(), models.ExperienceRecordModel.id.desc()
        ).limit(limit).offset(offset)).all()
        return tuple(_record(row) for row in rows)

    def update_record(self, record_id: str, *, expected_version: int,
                      expected_status: ExperienceStatus, new_version: int,
                      new_status: ExperienceStatus, updated_at: datetime) -> ProjectExperienceRecord:
        result = self._session.execute(update(models.ExperienceRecordModel).where(
            models.ExperienceRecordModel.id == record_id,
            models.ExperienceRecordModel.current_version == expected_version,
            models.ExperienceRecordModel.status == expected_status,
        ).values(current_version=new_version, status=new_status, updated_at=updated_at))
        if result.rowcount != 1:
            raise ConcurrentStateError("experience record changed before update")
        self._session.flush()
        return self.get_record(record_id)

    def add_version(self, value: ExperienceVersion) -> None:
        self._session.add(models.ExperienceVersionModel(**{
            key: getattr(value, key) for key in (
                "record_id", "project_id", "version", "title", "body", "author", "recorded_at")
        }))
        self._session.flush()

    def versions_for_record(self, record_id: str) -> Sequence[ExperienceVersion]:
        rows = self._session.scalars(select(models.ExperienceVersionModel).where(
            models.ExperienceVersionModel.record_id == record_id
        ).order_by(models.ExperienceVersionModel.version)).all()
        return tuple(_version(row) for row in rows)

    def get_version(self, record_id: str, version: int) -> Optional[ExperienceVersion]:
        row = self._session.get(models.ExperienceVersionModel, (record_id, version))
        return _version(row) if row else None

    def add_state_change(self, value: ExperienceStateChange) -> None:
        self._session.add(models.ExperienceStateChangeModel(
            id=value.id, project_id=value.project_id, record_id=value.record_id,
            version=value.version,
            from_status=value.from_status.value if value.from_status else None,
            to_status=value.to_status, actor=value.actor, occurred_at=value.occurred_at))
        self._session.flush()

    def state_changes_for_record(self, record_id: str) -> Sequence[ExperienceStateChange]:
        rows = self._session.scalars(select(models.ExperienceStateChangeModel).where(
            models.ExperienceStateChangeModel.record_id == record_id
        ).order_by(models.ExperienceStateChangeModel.occurred_at,
                   models.ExperienceStateChangeModel.id)).all()
        return tuple(_state(row) for row in rows)

    def add_revision_links(self, values: Sequence[ExperienceRevisionLink]) -> None:
        self._session.add_all(models.ExperienceRevisionLinkModel(**{
            key: getattr(value, key) for key in (
                "record_id", "project_id", "version", "context_item_id", "context_revision_id", "role")
        }) for value in values)
        self._session.flush()

    def revision_links_for_version(self, record_id: str, version: int) -> Sequence[ExperienceRevisionLink]:
        rows = self._session.scalars(select(models.ExperienceRevisionLinkModel).where(
            models.ExperienceRevisionLinkModel.record_id == record_id,
            models.ExperienceRevisionLinkModel.version == version,
        ).order_by(models.ExperienceRevisionLinkModel.context_revision_id)).all()
        return tuple(_revision_link(row) for row in rows)

    def referenced_revision_ids(self, project_id: str) -> frozenset[str]:
        return frozenset(self._session.scalars(select(
            models.ExperienceRevisionLinkModel.context_revision_id
        ).where(models.ExperienceRevisionLinkModel.project_id == project_id)).all())

    def add_event_links(self, values: Sequence[ExperienceEventLink]) -> None:
        self._session.add_all(models.ExperienceEventLinkModel(**{
            key: getattr(value, key) for key in (
                "record_id", "project_id", "version", "event_id")
        }) for value in values)
        self._session.flush()

    def event_links_for_version(self, record_id: str, version: int) -> Sequence[ExperienceEventLink]:
        rows = self._session.scalars(select(models.ExperienceEventLinkModel).where(
            models.ExperienceEventLinkModel.record_id == record_id,
            models.ExperienceEventLinkModel.version == version,
        ).order_by(models.ExperienceEventLinkModel.event_id)).all()
        return tuple(_event_link(row) for row in rows)
