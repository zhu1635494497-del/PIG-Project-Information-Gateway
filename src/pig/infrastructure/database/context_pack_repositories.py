from __future__ import annotations

from typing import Optional, Sequence

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from pig.domain import entities
from pig.domain.enums import ContextPackExportStatus
from pig.domain.context_pack_state import require_export_transition
from pig.domain.exceptions import ConcurrentStateError, EntityNotFoundError, InvariantViolationError
from pig.infrastructure.database import models


def _export(row: models.ContextPackExportModel) -> entities.ContextPackExport:
    return entities.ContextPackExport(**{
        name: getattr(row, name) for name in (
            "id", "project_id", "format", "status", "destination_locator",
            "actor", "correlation_id", "captured_context_revision",
            "manifest_schema_version", "plan_fingerprint", "entry_count",
            "total_bytes", "created_at", "updated_at", "started_at",
            "finished_at", "published_sha256", "error_code", "error_message",
        )
    })


def _entry(row: models.ContextPackEntryModel) -> entities.ContextPackEntry:
    return entities.ContextPackEntry(**{
        name: getattr(row, name) for name in (
            "id", "project_id", "export_id", "context_item_id",
            "context_revision_id", "ordinal", "relative_path", "display_name",
            "size_bytes", "sha256", "created_at", "purpose_snapshot",
            "guidance_body_snapshot", "guidance_author_snapshot",
        )
    })


def _section(row: models.ContextPackSectionModel) -> entities.ContextPackSection:
    return entities.ContextPackSection(**{
        name: getattr(row, name) for name in (
            "id", "project_id", "export_id", "source_section_id",
            "name_snapshot", "description_snapshot", "ordinal",
            "is_unsectioned", "created_at",
        )
    })


def _placement(row: models.ContextPackPlacementModel) -> entities.ContextPackPlacement:
    return entities.ContextPackPlacement(**{
        name: getattr(row, name) for name in (
            "id", "project_id", "export_id", "entry_id", "section_id",
            "ordinal", "created_at",
        )
    })


class SqlAlchemyContextPackRepository:
    """Relational export history; business preflight belongs to Application."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add_export(self, value: entities.ContextPackExport) -> None:
        row = models.ContextPackExportModel(**{
            name: getattr(value, name) for name in (
                "id", "project_id", "format", "status", "destination_locator",
                "actor", "correlation_id", "captured_context_revision",
                "manifest_schema_version", "plan_fingerprint", "entry_count",
                "total_bytes", "created_at", "updated_at", "started_at",
                "finished_at", "published_sha256", "error_code", "error_message",
            )
        })
        self._session.add(row)
        self._session.flush([row])

    def get_export(self, export_id: str) -> Optional[entities.ContextPackExport]:
        row = self._session.get(models.ContextPackExportModel, export_id)
        return None if row is None else _export(row)

    def exports_for_project(self, project_id: str) -> Sequence[entities.ContextPackExport]:
        rows = self._session.scalars(
            select(models.ContextPackExportModel)
            .where(models.ContextPackExportModel.project_id == project_id)
            .order_by(models.ContextPackExportModel.created_at, models.ContextPackExportModel.id)
        ).all()
        return tuple(_export(row) for row in rows)

    def update_export_status(
        self, export_id: str, expected: ContextPackExportStatus,
        new: ContextPackExportStatus, *, updated_at, started_at=None,
        finished_at=None, published_sha256=None, error_code=None,
        error_message=None,
    ) -> entities.ContextPackExport:
        require_export_transition(expected, new)
        if new == ContextPackExportStatus.RUNNING and started_at is None:
            raise ValueError("RUNNING requires started_at")
        if new in (ContextPackExportStatus.SUCCEEDED, ContextPackExportStatus.FAILED,
                   ContextPackExportStatus.CANCELLED_AT_SAFE_POINT) and finished_at is None:
            raise ValueError("terminal Context Pack state requires finished_at")
        if new == ContextPackExportStatus.SUCCEEDED and published_sha256 is None:
            raise ValueError("SUCCEEDED requires published_sha256")
        result = self._session.execute(
            update(models.ContextPackExportModel)
            .where(models.ContextPackExportModel.id == export_id,
                   models.ContextPackExportModel.status == expected)
            .values(status=new, updated_at=updated_at, started_at=started_at,
                    finished_at=finished_at, published_sha256=published_sha256,
                    error_code=error_code, error_message=error_message)
        )
        if result.rowcount != 1:
            if self._session.get(models.ContextPackExportModel, export_id) is None:
                raise EntityNotFoundError(f"Context Pack export not found: {export_id}")
            raise ConcurrentStateError("Context Pack export state changed concurrently")
        return _export(self._session.get(models.ContextPackExportModel, export_id))

    def add_entry(self, value: entities.ContextPackEntry) -> None:
        export = self._session.get(models.ContextPackExportModel, value.export_id)
        if export is None or export.project_id != value.project_id or export.status != ContextPackExportStatus.SUCCEEDED:
            raise InvariantViolationError("Context Pack Entries may only belong to a successful Export")
        row = models.ContextPackEntryModel(**{
            name: getattr(value, name) for name in (
                "id", "project_id", "export_id", "context_item_id",
                "context_revision_id", "ordinal", "relative_path", "display_name",
                "size_bytes", "sha256", "created_at", "purpose_snapshot",
                "guidance_body_snapshot", "guidance_author_snapshot",
            )
        })
        self._session.add(row)
        self._session.flush([row])

    def entries_for_export(self, export_id: str) -> Sequence[entities.ContextPackEntry]:
        rows = self._session.scalars(
            select(models.ContextPackEntryModel)
            .where(models.ContextPackEntryModel.export_id == export_id)
            .order_by(models.ContextPackEntryModel.ordinal)
        ).all()
        return tuple(_entry(row) for row in rows)

    def add_section(self, value: entities.ContextPackSection) -> None:
        row = models.ContextPackSectionModel(**{
            name: getattr(value, name) for name in (
                "id", "project_id", "export_id", "source_section_id",
                "name_snapshot", "description_snapshot", "ordinal",
                "is_unsectioned", "created_at",
            )
        })
        self._session.add(row)
        self._session.flush([row])

    def sections_for_export(self, export_id: str) -> Sequence[entities.ContextPackSection]:
        rows = self._session.scalars(
            select(models.ContextPackSectionModel)
            .where(models.ContextPackSectionModel.export_id == export_id)
            .order_by(models.ContextPackSectionModel.ordinal)
        ).all()
        return tuple(_section(row) for row in rows)

    def add_placement(self, value: entities.ContextPackPlacement) -> None:
        row = models.ContextPackPlacementModel(**{
            name: getattr(value, name) for name in (
                "id", "project_id", "export_id", "entry_id", "section_id",
                "ordinal", "created_at",
            )
        })
        self._session.add(row)
        self._session.flush([row])

    def placements_for_export(self, export_id: str) -> Sequence[entities.ContextPackPlacement]:
        rows = self._session.scalars(
            select(models.ContextPackPlacementModel)
            .where(models.ContextPackPlacementModel.export_id == export_id)
            .order_by(models.ContextPackPlacementModel.section_id,
                      models.ContextPackPlacementModel.ordinal)
        ).all()
        return tuple(_placement(row) for row in rows)

    def successful_revision_ids(self, project_id: str) -> frozenset[str]:
        rows = self._session.scalars(
            select(models.ContextPackEntryModel.context_revision_id)
            .join(models.ContextPackExportModel,
                  models.ContextPackEntryModel.export_id == models.ContextPackExportModel.id)
            .where(models.ContextPackExportModel.project_id == project_id,
                   models.ContextPackExportModel.status == ContextPackExportStatus.SUCCEEDED)
        ).all()
        return frozenset(rows)
