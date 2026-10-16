"""Explicit-plan, one-shot-consent AI Actions over fixed Context elements only."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from threading import Lock
from typing import Callable, Mapping
from uuid import uuid4

from pig.application.ai_prompts import PROMPT_VERSION
from pig.application.ai_ports import AIProvider, CredentialStore, ProviderFailure
from pig.application.errors import ApplicationError
from pig.application.ports import ProjectDatabaseProvider
from pig.domain.ai_policy import (
    AnalysisAction, AnalysisElement, AnalysisStatus, ModelClaim, input_fingerprint,
    validate_model_output,
)
from pig.domain.entities import ProcessingEvent
from pig.domain.enums import (
    ContextLifecycleStatus, ContextRevisionCaptureStatus, EventSeverity, EventType,
)
from pig.domain.model_version import CURRENT_PROJECT_MODEL_VERSION


@dataclass(frozen=True, slots=True)
class ModelProfile:
    provider: str
    model: str
    input_usd_per_million: Decimal
    output_usd_per_million: Decimal


# Conservative peak, uncached rates; refresh at provider qualification.
MODEL_PROFILES = (
    ModelProfile("openai", "gpt-6-luna", Decimal("0.10"), Decimal("0.50")),
    ModelProfile("deepseek", "deepseek-flash", Decimal("0.30"), Decimal("1.20")),
)


@dataclass(frozen=True, slots=True)
class AnalysisPlanRequest:
    project_id: str
    database_path: Path
    action: AnalysisAction
    revision_ids: tuple[str, ...]
    provider: str
    model: str


@dataclass(frozen=True, slots=True)
class AnalysisPlan:
    request: AnalysisPlanRequest
    elements: tuple[AnalysisElement, ...]
    coverage: str
    omitted_elements: int
    fingerprint: str
    consent_token: str
    estimated_max_usd: Decimal
    estimated_input_tokens: int
    max_output_tokens: int
    workspace_revision: int
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class AllowedLivePlan:
    """Narrow, explicit permission for one synthetic qualification input."""

    project_id: str
    database_path: Path
    fingerprint: str


@dataclass(frozen=True, slots=True)
class AnalysisRunResult:
    id: str
    project_id: str
    action: AnalysisAction
    provider: str
    model: str
    status: AnalysisStatus
    coverage: str
    claims: tuple[ModelClaim, ...]
    inputs: tuple[tuple[str, str, str, str], ...]
    error_code: str | None
    input_tokens: int | None
    output_tokens: int | None
    possibly_stale: bool


class AIAnalysisService:
    MAX_ELEMENTS_PER_REVISION = 40
    MAX_CHARS_PER_ELEMENT = 1500
    MAX_TOTAL_CHARS = 48_000
    MAX_OUTPUT_TOKENS = 4000
    MAX_REQUEST_USD = Decimal("0.50")

    def __init__(self, *, database: ProjectDatabaseProvider,
                 adapters: Mapping[str, AIProvider], credential_store: CredentialStore,
                 live_enabled: bool = False,
                 allowed_live_plans: tuple[AllowedLivePlan, ...] | None = None,
                 qualification_budget_usd: Decimal = Decimal("5.00"),
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                 id_generator: Callable[[], str] = lambda: str(uuid4())) -> None:
        self._database = database
        self._adapters = dict(adapters)
        self._credential_store = credential_store
        self._live_enabled = live_enabled
        self._allowed_live_plans = allowed_live_plans
        self._qualification_budget_usd = qualification_budget_usd
        self._clock = clock
        self._id = id_generator
        self._pending: dict[str, tuple[str, datetime]] = {}
        self._lock = Lock()

    def profiles(self) -> tuple[ModelProfile, ...]:
        return tuple(profile for profile in MODEL_PROFILES
                     if profile.provider in self._adapters)

    @property
    def live_enabled(self) -> bool:
        return self._live_enabled

    def can_execute(self, plan: AnalysisPlan) -> bool:
        if not self._live_enabled or plan.request.provider not in self._adapters:
            return False
        if self._allowed_live_plans is None:
            return True
        return any(
            scope.project_id == plan.request.project_id
            and scope.database_path.resolve()
            == Path(plan.request.database_path).resolve()
            and scope.fingerprint == plan.fingerprint
            for scope in self._allowed_live_plans
        )

    def plan(self, request: AnalysisPlanRequest) -> AnalysisPlan:
        plan = self._build_plan(request)
        with self._lock:
            now = self._clock()
            self._pending = {token: value for token, value in self._pending.items()
                             if value[1] >= now}
            self._pending[plan.consent_token] = (plan.fingerprint, plan.expires_at)
        return plan

    def _build_plan(self, request: AnalysisPlanRequest) -> AnalysisPlan:
        if not isinstance(request.action, AnalysisAction):
            raise ApplicationError("INVALID_REQUEST", "analysis action is invalid")
        count = {AnalysisAction.SUMMARY: 1, AnalysisAction.KEY_FACTS: 1,
                 AnalysisAction.COMPARE: 2}[request.action]
        if (len(request.revision_ids) != count
                or len(set(request.revision_ids)) != count):
            raise ApplicationError("INVALID_REQUEST", "action requires fixed Revision selection")
        profile = next((p for p in MODEL_PROFILES if
                        (p.provider, p.model) == (request.provider, request.model)), None)
        if profile is None:
            raise ApplicationError("MODEL_UNAVAILABLE", "provider/model is not supported")
        elements: list[AnalysisElement] = []
        omitted = 0
        partial = False
        total_chars = 0
        with self._database.unit_of_work(Path(request.database_path).resolve(strict=True)) as uow:
            project = uow.projects.get(request.project_id)
            if project is None or project.model_version != CURRENT_PROJECT_MODEL_VERSION:
                raise ApplicationError("PROJECT_CONTEXT_UPGRADE_REQUIRED", "Project must be upgraded")
            workspace_revision = project.workspace_revision
            for revision_id in request.revision_ids:
                revision_chars = 0
                revision_quota = self.MAX_TOTAL_CHARS // count
                revision = uow.context.get_revision(revision_id)
                if (revision is None or revision.project_id != request.project_id
                        or revision.capture_status != ContextRevisionCaptureStatus.READY):
                    raise ApplicationError("ANALYSIS_REVISION_INVALID", "selected Revision is not READY")
                item = uow.context.get_item(revision.context_item_id)
                if (item is None or item.project_id != request.project_id
                        or item.lifecycle_status != ContextLifecycleStatus.ACTIVE):
                    raise ApplicationError("ANALYSIS_REVISION_INVALID", "selected Item is inactive")
                run, rows, row_total = uow.content.latest_document_elements(
                    request.project_id, revision_id,
                    limit=self.MAX_ELEMENTS_PER_REVISION + 1,
                    max_chars_per_element=self.MAX_CHARS_PER_ELEMENT,
                )
                if (run is None or not rows or
                        run.input_sha256 != revision.source_observed_sha256):
                    raise ApplicationError("ANALYSIS_CONTENT_MISSING",
                                           "extract this fixed Revision before analysis")
                if run.status.value == "PARTIAL":
                    partial = True
                for row in rows[:self.MAX_ELEMENTS_PER_REVISION]:
                    content = row.text[:self.MAX_CHARS_PER_ELEMENT]
                    if row.text_length > len(content):
                        partial = True
                    if (total_chars + len(content) > self.MAX_TOTAL_CHARS
                            or revision_chars + len(content) > revision_quota):
                        partial = True
                        omitted += 1
                        continue
                    total_chars += len(content)
                    revision_chars += len(content)
                    elements.append(AnalysisElement(
                        id=row.id, revision_id=revision_id,
                        locator_kind=row.locator_kind.value,
                        locator_value=row.locator_value, text=content,
                    ))
                omitted += max(0, row_total - min(len(rows), self.MAX_ELEMENTS_PER_REVISION))
                if row_total > self.MAX_ELEMENTS_PER_REVISION:
                    partial = True
                if not any(element.revision_id == revision_id for element in elements):
                    raise ApplicationError("ANALYSIS_CONTENT_MISSING",
                                           "selected Revision has no bounded content")
        if not elements:
            raise ApplicationError("ANALYSIS_CONTENT_MISSING", "no bounded content elements")
        # UTF-8 bytes are a deliberately high-side token proxy for multilingual text.
        estimated_input_tokens = 2000 + sum(len(e.text.encode("utf-8")) + 100 for e in elements)
        estimate = (
            Decimal(estimated_input_tokens) * profile.input_usd_per_million
            + Decimal(self.MAX_OUTPUT_TOKENS) * profile.output_usd_per_million
        ) / Decimal(1_000_000)
        if estimate > self.MAX_REQUEST_USD:
            raise ApplicationError("ANALYSIS_BUDGET_EXCEEDED", "estimated request exceeds $0.50")
        return AnalysisPlan(
            request=request, elements=tuple(elements),
            coverage="PARTIAL_INPUT" if partial else "COMPLETE_INPUT",
            omitted_elements=omitted,
            fingerprint=input_fingerprint(action=request.action, provider=request.provider,
                                          model=request.model, elements=elements,
                                          prompt_version=PROMPT_VERSION),
            consent_token=self._id(), estimated_max_usd=estimate,
            estimated_input_tokens=estimated_input_tokens,
            max_output_tokens=self.MAX_OUTPUT_TOKENS,
            workspace_revision=workspace_revision,
            expires_at=self._clock() + timedelta(minutes=5),
        )

    def execute(self, plan: AnalysisPlan, *, actor: str,
                confirmed_token: str) -> AnalysisRunResult:
        if not actor.strip() or len(actor) > 255 or any(ord(c) < 32 for c in actor):
            raise ApplicationError("INVALID_REQUEST", "analysis actor is invalid")
        with self._lock:
            pending = self._pending.pop(confirmed_token, None)
        if (confirmed_token != plan.consent_token or pending is None
                or pending[0] != plan.fingerprint or pending[1] < self._clock()):
            raise ApplicationError("ANALYSIS_CONSENT_INVALID", "plan confirmation expired or changed")
        refreshed = self._build_plan(plan.request)
        if (refreshed.fingerprint != plan.fingerprint
                or refreshed.workspace_revision != plan.workspace_revision
                or refreshed.coverage != plan.coverage
                or refreshed.estimated_max_usd != plan.estimated_max_usd):
            raise ApplicationError("ANALYSIS_PLAN_STALE", "analysis input changed; preview again")
        if not self._live_enabled:
            raise ApplicationError("PROVIDER_NOT_QUALIFIED",
                                   "live provider gate has not been accepted")
        if not self.can_execute(plan):
            raise ApplicationError("PROVIDER_NOT_QUALIFIED",
                                   "this plan is outside the authorized outbound scope")
        adapter = self._adapters.get(plan.request.provider)
        if adapter is None:
            raise ApplicationError("MODEL_UNAVAILABLE", "provider adapter is missing")
        key = self._credential_store.get(plan.request.provider)
        if not key:
            raise ApplicationError("CREDENTIAL_MISSING", "configure API key in Windows Credential Manager")
        run_id = self._id()
        now = self._clock()
        with self._database.unit_of_work(Path(plan.request.database_path).resolve(strict=True)) as uow:
            if (uow.ai.estimated_spend_usd(plan.request.project_id)
                    + plan.estimated_max_usd > self._qualification_budget_usd):
                raise ApplicationError("ANALYSIS_BUDGET_EXCEEDED",
                                       "synthetic qualification budget would be exceeded")
            uow.ai.add_run(
                id=run_id, project_id=plan.request.project_id, action=plan.request.action,
                provider=plan.request.provider, model=plan.request.model,
                prompt_version=PROMPT_VERSION, input_fingerprint=plan.fingerprint,
                workspace_revision_at_plan=plan.workspace_revision,
                coverage=plan.coverage, status=AnalysisStatus.RUNNING,
                actor=actor, consented_at=now, started_at=now,
                estimated_max_usd=plan.estimated_max_usd,
            )
            uow.ai.add_inputs(run_id, plan.request.project_id, plan.elements)
            self._event(uow, plan.request.project_id, run_id, actor,
                        EventType.AI_RUN_STARTED, AnalysisStatus.RUNNING, now)
            uow.commit()
        try:
            response = adapter.invoke(model=plan.request.model, key=key,
                                      action=plan.request.action, elements=plan.elements)
            claims = validate_model_output(response.output, action=plan.request.action,
                                           elements=plan.elements)
            status, error_code = AnalysisStatus.SUCCEEDED, None
            input_tokens, output_tokens = response.input_tokens, response.output_tokens
        except ProviderFailure as exc:
            claims, status, error_code = (), AnalysisStatus.FAILED, exc.code
            input_tokens = output_tokens = None
        except Exception:
            claims, status, error_code = (), AnalysisStatus.FAILED, "ANALYSIS_OUTPUT_INVALID"
            input_tokens = output_tokens = None
        finished = self._clock()
        with self._database.unit_of_work(Path(plan.request.database_path).resolve(strict=True)) as uow:
            if claims:
                uow.ai.add_claims(run_id, claims)
            uow.ai.finish(run_id, status=status, finished_at=finished,
                          input_tokens=input_tokens, output_tokens=output_tokens,
                          error_code=error_code)
            self._event(uow, plan.request.project_id, run_id, actor,
                        EventType.AI_RUN_SUCCEEDED if status == AnalysisStatus.SUCCEEDED
                        else EventType.AI_RUN_FAILED, status, finished, error_code)
            uow.commit()
        return self.get(plan.request.project_id, plan.request.database_path, run_id)

    def get(self, project_id: str, database_path: Path, run_id: str) -> AnalysisRunResult:
        with self._database.unit_of_work(Path(database_path).resolve(strict=True)) as uow:
            run = uow.ai.get_run(project_id, run_id)
            if run is None:
                raise ApplicationError("ANALYSIS_NOT_FOUND", "AI draft was not found")
            project = uow.projects.get(project_id)
            inputs = uow.ai.inputs_for_run(run_id)
            stale = project.workspace_revision != run.workspace_revision_at_plan or any(
                (item := uow.context.get_item(
                    uow.context.get_revision(value.context_revision_id).context_item_id
                )) is None or item.current_context_revision_id != value.context_revision_id
                for value in inputs
            )
            return AnalysisRunResult(
                id=run.id, project_id=project_id, action=run.action,
                provider=run.provider, model=run.model, status=run.status,
                coverage=run.coverage, claims=uow.ai.claims_for_run(run_id),
                inputs=tuple((value.element_id, value.context_revision_id,
                              value.locator_kind, value.locator_value) for value in inputs),
                error_code=run.error_code, input_tokens=run.input_tokens,
                output_tokens=run.output_tokens,
                possibly_stale=stale,
            )

    def list(self, project_id: str, database_path: Path):
        with self._database.unit_of_work(Path(database_path).resolve(strict=True)) as uow:
            return tuple((row.id, row.action, row.provider, row.model, row.status,
                          row.started_at) for row in uow.ai.list_runs(project_id))

    def recover_interrupted(self, project_id: str, database_path: Path, *, actor: str) -> int:
        with self._database.unit_of_work(Path(database_path).resolve(strict=True)) as uow:
            rows = uow.ai.running(project_id)
            for row in rows:
                now = self._clock()
                uow.ai.finish(row.id, status=AnalysisStatus.INTERRUPTED, finished_at=now,
                              error_code="PROCESS_INTERRUPTED")
                self._event(uow, project_id, row.id, actor,
                            EventType.AI_RUN_INTERRUPTED, AnalysisStatus.INTERRUPTED,
                            now, "PROCESS_INTERRUPTED")
            uow.commit()
            return len(rows)

    def save_credential(self, provider: str, secret: str) -> None:
        self._credential_store.put(provider, secret)

    def remove_credential(self, provider: str) -> None:
        self._credential_store.delete(provider)

    @staticmethod
    def _event(uow, project_id: str, run_id: str, actor: str,
               event_type: EventType, status: AnalysisStatus, at: datetime,
               error_code: str | None = None) -> None:
        uow.processing.append_event(ProcessingEvent(
            id=str(uuid4()), event_type=event_type, project_id=project_id,
            actor=actor, occurred_at=at,
            severity=EventSeverity.ERROR if status == AnalysisStatus.FAILED else EventSeverity.INFO,
            correlation_id=run_id, new_status=status.value,
            details={"ai_run_id": run_id, "error_code": error_code or ""},
        ))
