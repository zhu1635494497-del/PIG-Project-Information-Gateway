from __future__ import annotations

from typing import Sequence

from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from pig.domain import entities
from pig.domain.enums import ContentExtractionStatus
from pig.infrastructure.database import models


def _run(row: models.ExtractionRunModel) -> entities.ExtractionRun:
    return entities.ExtractionRun(
        id=row.id, project_id=row.project_id, context_revision_id=row.context_revision_id,
        input_sha256=row.input_sha256, extractor_name=row.extractor_name,
        extractor_version=row.extractor_version, config_sha256=row.config_sha256,
        status=row.status, actor=row.actor, correlation_id=row.correlation_id,
        started_at=row.started_at, finished_at=row.finished_at,
        element_count=row.element_count, error_code=row.error_code,
        error_message=row.error_message,
    )


class SqlAlchemyContentRepository:
    """Canonical elements and rebuildable FTS are committed in one Project transaction."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def schema_revision(self) -> str:
        return str(self._session.execute(text("SELECT version_num FROM alembic_version")).scalar_one())

    def add_run(self, run: entities.ExtractionRun) -> None:
        self._session.add(models.ExtractionRunModel(**{
            name: getattr(run, name) for name in run.__dataclass_fields__
        }))
        self._session.flush()

    def get_run(self, run_id: str) -> entities.ExtractionRun | None:
        row = self._session.get(models.ExtractionRunModel, run_id)
        return None if row is None else _run(row)

    def runs_for_revision(self, project_id: str, revision_id: str) -> Sequence[entities.ExtractionRun]:
        rows = self._session.scalars(
            select(models.ExtractionRunModel).where(
                models.ExtractionRunModel.project_id == project_id,
                models.ExtractionRunModel.context_revision_id == revision_id,
            ).order_by(models.ExtractionRunModel.started_at.desc())
        ).all()
        return tuple(_run(row) for row in rows)

    def latest_document_elements(self, project_id: str, revision_id: str, *, limit: int,
                                 max_chars_per_element: int):
        """A bounded canonical snapshot; never reads Workspace or searches by query text."""
        run = self._session.scalar(select(models.ExtractionRunModel).where(
            models.ExtractionRunModel.project_id == project_id,
            models.ExtractionRunModel.context_revision_id == revision_id,
            models.ExtractionRunModel.status.in_((ContentExtractionStatus.SUCCEEDED,
                                                 ContentExtractionStatus.PARTIAL)),
        ).order_by(models.ExtractionRunModel.started_at.desc(),
                   models.ExtractionRunModel.id.desc()).limit(1))
        if run is None:
            return None, (), 0
        document = self._session.scalar(select(models.ContentDocumentModel).where(
            models.ContentDocumentModel.project_id == project_id,
            models.ContentDocumentModel.extraction_run_id == run.id,
        ))
        if document is None:
            return _run(run), (), 0
        total = int(self._session.scalar(select(func.count()).select_from(
            models.ContentElementModel).where(
                models.ContentElementModel.project_id == project_id,
                models.ContentElementModel.document_id == document.id,
            )) or 0)
        rows = self._session.execute(select(
            models.ContentElementModel.id,
            models.ContentElementModel.locator_kind,
            models.ContentElementModel.locator_value,
            func.substr(models.ContentElementModel.text, 1, max_chars_per_element + 1).label("text"),
            func.length(models.ContentElementModel.text).label("text_length"),
        ).where(
            models.ContentElementModel.project_id == project_id,
            models.ContentElementModel.document_id == document.id,
        ).order_by(models.ContentElementModel.ordinal).limit(limit)).all()
        return _run(run), tuple(rows), total

    def running_runs(self, project_id: str) -> Sequence[entities.ExtractionRun]:
        rows = self._session.scalars(select(models.ExtractionRunModel).where(
            models.ExtractionRunModel.project_id == project_id,
            models.ExtractionRunModel.status == ContentExtractionStatus.RUNNING,
        )).all()
        return tuple(_run(row) for row in rows)

    def runs_for_item(self, project_id: str, context_item_id: str) -> Sequence[entities.ExtractionRun]:
        rows = self._session.scalars(
            select(models.ExtractionRunModel).join(
                models.ContextRevisionModel,
                models.ContextRevisionModel.id == models.ExtractionRunModel.context_revision_id,
            ).where(
                models.ExtractionRunModel.project_id == project_id,
                models.ContextRevisionModel.context_item_id == context_item_id,
            ).order_by(models.ExtractionRunModel.started_at.desc())
        ).all()
        return tuple(_run(row) for row in rows)

    def latest_equivalent(self, project_id: str, revision_id: str,
                          input_sha256: str, extractor_name: str,
                          extractor_version: str, config_sha256: str) -> entities.ExtractionRun | None:
        row = self._session.scalar(
            select(models.ExtractionRunModel).where(
                models.ExtractionRunModel.project_id == project_id,
                models.ExtractionRunModel.context_revision_id == revision_id,
                models.ExtractionRunModel.input_sha256 == input_sha256,
                models.ExtractionRunModel.extractor_name == extractor_name,
                models.ExtractionRunModel.extractor_version == extractor_version,
                models.ExtractionRunModel.config_sha256 == config_sha256,
                models.ExtractionRunModel.status.in_((ContentExtractionStatus.SUCCEEDED,
                                                      ContentExtractionStatus.PARTIAL)),
            ).order_by(models.ExtractionRunModel.started_at.desc()).limit(1)
        )
        return None if row is None else _run(row)

    def finish_run(self, run_id: str, status: ContentExtractionStatus, *, finished_at,
                   element_count: int = 0, error_code: str | None = None,
                   error_message: str | None = None) -> None:
        result = self._session.execute(
            update(models.ExtractionRunModel).where(
                models.ExtractionRunModel.id == run_id,
                models.ExtractionRunModel.status == ContentExtractionStatus.RUNNING,
            ).values(status=status, finished_at=finished_at, element_count=element_count,
                     error_code=error_code, error_message=error_message)
        )
        if result.rowcount != 1:
            raise RuntimeError("extraction run is no longer RUNNING")

    def add_document(self, document: entities.ContentDocument,
                     elements: Sequence[entities.ContentElement]) -> None:
        self._session.add(models.ContentDocumentModel(**{
            name: getattr(document, name) for name in document.__dataclass_fields__
        }))
        self._session.flush()
        for element in elements:
            self._session.add(models.ContentElementModel(**{
                name: getattr(element, name) for name in element.__dataclass_fields__
            }))
        self._session.flush()

    def rebuild_index(self) -> int:
        self._session.execute(text(
            "CREATE VIRTUAL TABLE IF NOT EXISTS content_fts USING fts5("
            "text, content='content_elements', content_rowid='rowid')"
        ))
        self._session.execute(text("""CREATE TRIGGER IF NOT EXISTS content_elements_ai
            AFTER INSERT ON content_elements BEGIN
            INSERT INTO content_fts(rowid, text) VALUES (new.rowid, new.text); END"""))
        self._session.execute(text("""CREATE TRIGGER IF NOT EXISTS content_elements_ad
            AFTER DELETE ON content_elements BEGIN
            INSERT INTO content_fts(content_fts, rowid, text) VALUES ('delete', old.rowid, old.text); END"""))
        self._session.execute(text("INSERT INTO content_fts(content_fts) VALUES ('rebuild')"))
        return int(self._session.execute(text("SELECT count(*) FROM content_elements")).scalar_one())

    def search(self, project_id: str, expression: str, *, limit: int, offset: int,
               revision_id: str | None = None) -> tuple[tuple[dict, ...], int]:
        predicate = " AND d.context_revision_id = :revision_id" if revision_id else ""
        where = (
            "FROM content_fts f JOIN content_elements e ON e.rowid = f.rowid "
            "JOIN content_documents d ON d.id = e.document_id "
            "JOIN extraction_runs r ON r.id = d.extraction_run_id "
            "JOIN context_revisions v ON v.id = d.context_revision_id "
            "JOIN context_items i ON i.id = v.context_item_id "
            "JOIN workspace_items w ON w.id = i.workspace_item_id "
            "WHERE content_fts MATCH :expression AND e.project_id = :project_id "
            "AND r.status IN ('SUCCEEDED','PARTIAL') AND v.capture_status = 'READY' "
            "AND i.lifecycle_status = 'ACTIVE'" + predicate
        )
        params = {"expression": expression, "project_id": project_id,
                  "revision_id": revision_id, "limit": limit, "offset": offset}
        total = int(self._session.execute(text("SELECT count(*) " + where), params).scalar_one())
        query = (
            "SELECT e.id AS element_id, d.context_revision_id, i.id AS context_item_id, "
            "COALESCE(i.title_override, w.display_name) AS title, e.locator_kind, "
            "e.locator_value, snippet(content_fts, 0, '[', ']', '…', 16) AS snippet "
            + where + " ORDER BY bm25(content_fts), e.ordinal LIMIT :limit OFFSET :offset"
        )
        rows = self._session.execute(text(query), params).mappings().all()
        return tuple(dict(row) for row in rows), total

    def search_cjk_substring(self, project_id: str, query: str, *, limit: int,
                             offset: int, revision_id: str | None = None) -> tuple[tuple[dict, ...], int]:
        # SQLite unicode61 tokenizes a continuous Han phrase as one token. This
        # bounded-page fallback retains useful two-character Chinese searches.
        predicate = " AND d.context_revision_id = :revision_id" if revision_id else ""
        where = (
            "FROM content_elements e JOIN content_documents d ON d.id = e.document_id "
            "JOIN extraction_runs r ON r.id = d.extraction_run_id "
            "JOIN context_revisions v ON v.id = d.context_revision_id "
            "JOIN context_items i ON i.id = v.context_item_id "
            "JOIN workspace_items w ON w.id = i.workspace_item_id "
            "WHERE e.project_id = :project_id AND instr(e.text, :query) > 0 "
            "AND r.status IN ('SUCCEEDED','PARTIAL') AND v.capture_status = 'READY' "
            "AND i.lifecycle_status = 'ACTIVE'" + predicate
        )
        params = {"project_id": project_id, "query": query, "revision_id": revision_id,
                  "limit": limit, "offset": offset}
        total = int(self._session.execute(text("SELECT count(*) " + where), params).scalar_one())
        rows = self._session.execute(text(
            "SELECT e.id AS element_id, d.context_revision_id, i.id AS context_item_id, "
            "COALESCE(i.title_override, w.display_name) AS title, e.locator_kind, "
            "e.locator_value, substr(e.text, max(1, instr(e.text, :query)-24), 96) AS snippet "
            + where + " ORDER BY d.created_at DESC, e.ordinal LIMIT :limit OFFSET :offset"
        ), params).mappings().all()
        return tuple(dict(row) for row in rows), total
