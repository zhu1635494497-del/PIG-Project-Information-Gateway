"""Project-local AI draft persistence; no credentials or outbound payloads."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from pig.domain.ai_policy import AnalysisElement, AnalysisStatus, ModelClaim
from pig.infrastructure.database import models


class SqlAlchemyAIRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_run(self, **fields) -> None:
        self._session.add(models.AIAnalysisRunModel(**fields))
        self._session.flush()

    def add_inputs(self, run_id: str, project_id: str,
                   elements: tuple[AnalysisElement, ...]) -> None:
        self._session.add_all(models.AIAnalysisInputModel(
            run_id=run_id, project_id=project_id, element_id=element.id,
            context_revision_id=element.revision_id,
            locator_kind=element.locator_kind, locator_value=element.locator_value,
            ordinal=ordinal,
        ) for ordinal, element in enumerate(elements))
        self._session.flush()

    def finish(self, run_id: str, *, status: AnalysisStatus, finished_at,
               input_tokens: int | None = None, output_tokens: int | None = None,
               error_code: str | None = None) -> None:
        result = self._session.execute(update(models.AIAnalysisRunModel).where(
            models.AIAnalysisRunModel.id == run_id,
            models.AIAnalysisRunModel.status == AnalysisStatus.RUNNING,
        ).values(status=status, finished_at=finished_at,
                 input_tokens=input_tokens, output_tokens=output_tokens,
                 error_code=error_code))
        if result.rowcount != 1:
            raise RuntimeError("AI run is no longer RUNNING")

    def add_claims(self, run_id: str, claims: tuple[ModelClaim, ...]) -> None:
        for ordinal, claim in enumerate(claims):
            self._session.add(models.AIAnalysisClaimModel(
                run_id=run_id, ordinal=ordinal, kind=claim.kind, text=claim.text,
                subject=claim.subject, time=claim.time,
            ))
        self._session.flush()
        self._session.add_all(models.AIAnalysisCitationModel(
            run_id=run_id, claim_ordinal=ordinal, element_id=element_id,
        ) for ordinal, claim in enumerate(claims) for element_id in claim.element_ids)
        self._session.flush()

    def get_run(self, project_id: str, run_id: str):
        return self._session.scalar(select(models.AIAnalysisRunModel).where(
            models.AIAnalysisRunModel.project_id == project_id,
            models.AIAnalysisRunModel.id == run_id,
        ))

    def list_runs(self, project_id: str, *, limit: int = 50):
        return tuple(self._session.scalars(select(models.AIAnalysisRunModel).where(
            models.AIAnalysisRunModel.project_id == project_id,
        ).order_by(models.AIAnalysisRunModel.started_at.desc()).limit(limit)).all())

    def claims_for_run(self, run_id: str) -> tuple[ModelClaim, ...]:
        rows = self._session.scalars(select(models.AIAnalysisClaimModel).where(
            models.AIAnalysisClaimModel.run_id == run_id,
        ).order_by(models.AIAnalysisClaimModel.ordinal)).all()
        result = []
        for row in rows:
            links = self._session.scalars(select(models.AIAnalysisCitationModel.element_id).where(
                models.AIAnalysisCitationModel.run_id == run_id,
                models.AIAnalysisCitationModel.claim_ordinal == row.ordinal,
            ).order_by(models.AIAnalysisCitationModel.element_id)).all()
            result.append(ModelClaim(row.kind, row.text, tuple(links), row.subject, row.time))
        return tuple(result)

    def inputs_for_run(self, run_id: str):
        return tuple(self._session.scalars(select(models.AIAnalysisInputModel).where(
            models.AIAnalysisInputModel.run_id == run_id,
        ).order_by(models.AIAnalysisInputModel.ordinal)).all())

    def running(self, project_id: str):
        return tuple(self._session.scalars(select(models.AIAnalysisRunModel).where(
            models.AIAnalysisRunModel.project_id == project_id,
            models.AIAnalysisRunModel.status == AnalysisStatus.RUNNING,
        )).all())

    def estimated_spend_usd(self, project_id: str) -> Decimal:
        value = self._session.scalar(select(func.sum(models.AIAnalysisRunModel.estimated_max_usd))
                                     .where(models.AIAnalysisRunModel.project_id == project_id))
        return Decimal(value or 0)
