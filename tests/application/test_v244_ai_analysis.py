"""Synthetic-only provider and project persistence acceptance."""

from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from pig.application.ai_analysis_service import (
    AIAnalysisService, AllowedLivePlan, AnalysisPlanRequest, ModelProfile,
)
from pig.application.content_contracts import ExtractContextRevisionsRequest
from pig.application.contracts import (
    CreateProjectRequest, GetWorkspaceTreeRequest, ImportProjectItemsRequest,
    InspectImportSessionRequest, PromoteWorkspaceItemToContextRequest,
)
from pig.application.errors import ApplicationError
from pig.bootstrap import create_local_application
from pig.domain.ai_policy import AnalysisAction, AnalysisStatus
from pig.infrastructure.ai.responses import ProviderFailure, ProviderResult
from pig.infrastructure.database.provider import SqlAlchemyProjectDatabase
from pig.infrastructure.database import models


class _FakeCredentials:
    def get(self, provider):
        return "synthetic-key"

    def put(self, provider, secret):
        pass


class _FakeProvider:
    def __init__(self, invalid=False, error=False):
        self.calls = 0
        self.invalid = invalid
        self.error = error

    def invoke(self, *, model, key, action, elements):
        self.calls += 1
        if self.error:
            raise ProviderFailure("PROVIDER_UNAVAILABLE")
        return ProviderResult({"claims": [{
            "kind": "SUMMARY", "text": "Synthetic claim",
            "element_ids": ["wrong" if self.invalid else elements[0].id],
            "subject": None, "time": None,
        }]}, 100, 30)


def _ready(tmp_path: Path, *, text="Synthetic project fact\nSecond line"):
    source = tmp_path / "synthetic.txt"
    source.write_text(text, encoding="utf-8")
    app = create_local_application(tmp_path / "projects")
    project = app.create_project(CreateProjectRequest(name="Synthetic AI", actor="tester"))
    imported = app.import_project_items(ImportProjectItemsRequest(
        project_id=project.project_id, database_path=project.database_path,
        input_paths=(source,), actor="tester"))
    app.inspect_import_session(InspectImportSessionRequest(
        project_id=project.project_id, database_path=project.database_path,
        import_session_id=imported.import_session_id, actor="tester"))
    tree = app.get_workspace_tree(GetWorkspaceTreeRequest(
        project_id=project.project_id, database_path=project.database_path))
    promoted = app.promote_workspace_item_to_context(PromoteWorkspaceItemToContextRequest(
        project_id=project.project_id, database_path=project.database_path,
        workspace_item_id=tree.items[0].item.id, actor="tester",
        expected_workspace_revision=tree.workspace_revision, expected_context_revision=0))
    revision = promoted.capture.context_revision_id
    app.extract_context_revisions(ExtractContextRevisionsRequest(
        project.project_id, project.database_path, (revision,), "tester"))
    return project, revision


def _service(adapter, *, enabled=True, budget=Decimal("5.00")):
    return AIAnalysisService(database=SqlAlchemyProjectDatabase(),
                             adapters={"openai": adapter},
                             credential_store=_FakeCredentials(),
                             live_enabled=enabled, qualification_budget_usd=budget)


def _request(project, revision):
    return AnalysisPlanRequest(project.project_id, project.database_path,
                               AnalysisAction.SUMMARY, (revision,),
                               "openai", "gpt-6-luna")


def test_synthetic_provider_result_is_cited_persisted_and_one_shot(tmp_path):
    project, revision = _ready(tmp_path)
    provider = _FakeProvider()
    service = _service(provider)
    plan = service.plan(_request(project, revision))
    assert plan.coverage == "COMPLETE_INPUT"
    result = service.execute(plan, actor="tester", confirmed_token=plan.consent_token)
    assert result.status == AnalysisStatus.SUCCEEDED
    assert result.claims[0].element_ids == (plan.elements[0].id,)
    assert service.get(project.project_id, project.database_path, result.id).claims == result.claims
    assert provider.calls == 1
    with SqlAlchemyProjectDatabase().unit_of_work(project.database_path) as uow:
        with pytest.raises(IntegrityError):
            uow.session.execute(delete(models.ContentElementModel).where(
                models.ContentElementModel.id == plan.elements[0].id))
    with pytest.raises(ApplicationError, match="confirmation expired"):
        service.execute(plan, actor="tester", confirmed_token=plan.consent_token)
    assert provider.calls == 1


@pytest.mark.parametrize("invalid,error", [(True, False), (False, True)])
def test_invalid_citation_and_offline_failure_remain_non_successful(tmp_path, invalid, error):
    project, revision = _ready(tmp_path)
    service = _service(_FakeProvider(invalid=invalid, error=error))
    plan = service.plan(_request(project, revision))
    result = service.execute(plan, actor="tester", confirmed_token=plan.consent_token)
    assert result.status == AnalysisStatus.FAILED
    assert result.claims == ()
    assert result.error_code == ("ANALYSIS_OUTPUT_INVALID" if invalid else "PROVIDER_UNAVAILABLE")


def test_live_gate_blocks_before_outbound_or_run_write(tmp_path):
    project, revision = _ready(tmp_path)
    provider = _FakeProvider()
    service = _service(provider, enabled=False)
    plan = service.plan(_request(project, revision))
    with pytest.raises(ApplicationError, match="live provider gate"):
        service.execute(plan, actor="tester", confirmed_token=plan.consent_token)
    assert provider.calls == 0
    assert service.list(project.project_id, project.database_path) == ()


def test_exact_synthetic_scope_allows_only_one_deepseek_plan(tmp_path):
    project, revision = _ready(tmp_path)
    provider = _FakeProvider()
    request = AnalysisPlanRequest(project.project_id, project.database_path,
                                  AnalysisAction.SUMMARY, (revision,),
                                  "deepseek", "deepseek-flash")
    preview = AIAnalysisService(
        database=SqlAlchemyProjectDatabase(), adapters={"deepseek": provider},
        credential_store=_FakeCredentials(),
    ).plan(request)
    service = AIAnalysisService(
        database=SqlAlchemyProjectDatabase(), adapters={"deepseek": provider},
        credential_store=_FakeCredentials(), live_enabled=True,
        allowed_live_plans=(AllowedLivePlan(
            project.project_id, project.database_path.resolve(),
            preview.fingerprint),),
    )
    plan = service.plan(request)
    assert service.can_execute(plan)
    assert [(value.provider, value.model) for value in service.profiles()] == [
        ("deepseek", "deepseek-flash")]
    result = service.execute(plan, actor="tester", confirmed_token=plan.consent_token)
    assert result.status == AnalysisStatus.SUCCEEDED
    assert provider.calls == 1


@pytest.mark.parametrize("scope_change", ["project", "database", "fingerprint"])
def test_synthetic_scope_rejects_other_inputs_before_run_write(tmp_path, scope_change):
    project, revision = _ready(tmp_path)
    provider = _FakeProvider()
    request = AnalysisPlanRequest(project.project_id, project.database_path,
                                  AnalysisAction.SUMMARY, (revision,),
                                  "deepseek", "deepseek-flash")
    preview = AIAnalysisService(
        database=SqlAlchemyProjectDatabase(), adapters={"deepseek": provider},
        credential_store=_FakeCredentials(),
    ).plan(request)
    scope = AllowedLivePlan(
        "other-project" if scope_change == "project" else project.project_id,
        tmp_path / "other.sqlite" if scope_change == "database"
        else project.database_path.resolve(),
        "wrong-fingerprint" if scope_change == "fingerprint" else preview.fingerprint,
    )
    service = AIAnalysisService(
        database=SqlAlchemyProjectDatabase(), adapters={"deepseek": provider},
        credential_store=_FakeCredentials(), live_enabled=True,
        allowed_live_plans=(scope,),
    )
    plan = service.plan(request)
    assert not service.can_execute(plan)
    with pytest.raises(ApplicationError, match="authorized outbound scope"):
        service.execute(plan, actor="tester", confirmed_token=plan.consent_token)
    assert provider.calls == 0
    assert service.list(project.project_id, project.database_path) == ()


def test_source_qualification_flag_cannot_enable_packaged_runtime(tmp_path, monkeypatch):
    import pig.bootstrap as bootstrap
    monkeypatch.setattr(bootstrap.sys, "frozen", True, raising=False)
    app = bootstrap.create_local_application(
        tmp_path / "projects", synthetic_deepseek_qualification=True)
    assert not app.ai_live_enabled()


def test_workspace_change_invalidates_preview_before_outbound(tmp_path):
    project, revision = _ready(tmp_path)
    provider = _FakeProvider()
    service = _service(provider)
    plan = service.plan(_request(project, revision))
    with SqlAlchemyProjectDatabase().unit_of_work(project.database_path) as uow:
        current = uow.projects.get(project.project_id)
        uow.projects.advance_workspace_revision(project.project_id,
                                                current.workspace_revision,
                                                updated_at=datetime.now(timezone.utc))
        uow.commit()
    with pytest.raises(ApplicationError, match="analysis input changed"):
        service.execute(plan, actor="tester", confirmed_token=plan.consent_token)
    assert provider.calls == 0


def test_interrupted_run_reopens_as_interrupted_not_success(tmp_path):
    project, revision = _ready(tmp_path)

    class _CrashProvider:
        def invoke(self, **_kwargs):
            raise KeyboardInterrupt("synthetic interruption")

    service = _service(_CrashProvider())
    plan = service.plan(_request(project, revision))
    with pytest.raises(KeyboardInterrupt):
        service.execute(plan, actor="tester", confirmed_token=plan.consent_token)
    assert service.list(project.project_id, project.database_path)[0][4] == AnalysisStatus.RUNNING
    assert service.recover_interrupted(project.project_id, project.database_path,
                                       actor="tester") == 1
    assert service.list(project.project_id, project.database_path)[0][4] == AnalysisStatus.INTERRUPTED


def test_qualification_budget_stops_before_outbound(tmp_path):
    project, revision = _ready(tmp_path)
    provider = _FakeProvider()
    service = _service(provider, budget=Decimal("0"))
    plan = service.plan(_request(project, revision))
    with pytest.raises(ApplicationError, match="qualification budget"):
        service.execute(plan, actor="tester", confirmed_token=plan.consent_token)
    assert provider.calls == 0


def test_per_request_estimate_cap_blocks_plan(tmp_path, monkeypatch):
    project, revision = _ready(tmp_path)
    import pig.application.ai_analysis_service as module
    monkeypatch.setattr(module, "MODEL_PROFILES", (
        ModelProfile("openai", "gpt-6-luna", Decimal("1000"), Decimal("1000")),
    ))
    with pytest.raises(ApplicationError, match="exceeds \\$0.50"):
        _service(_FakeProvider()).plan(_request(project, revision))


def test_long_element_is_previewed_as_partial_input(tmp_path):
    project, revision = _ready(tmp_path, text="Synthetic " + "x" * 2500)
    plan = _service(_FakeProvider()).plan(_request(project, revision))
    assert plan.coverage == "PARTIAL_INPUT"
    assert len(plan.elements[0].text) == 1500


def test_compare_requires_two_fixed_revisions_and_cites_both(tmp_path):
    project, first = _ready(tmp_path)
    second_source = tmp_path / "second.txt"
    second_source.write_text("Other synthetic fact", encoding="utf-8")
    app = create_local_application(tmp_path / "projects")
    imported = app.import_project_items(ImportProjectItemsRequest(
        project_id=project.project_id, database_path=project.database_path,
        input_paths=(second_source,), actor="tester"))
    app.inspect_import_session(InspectImportSessionRequest(
        project_id=project.project_id, database_path=project.database_path,
        import_session_id=imported.import_session_id, actor="tester"))
    tree = app.get_workspace_tree(GetWorkspaceTreeRequest(
        project_id=project.project_id, database_path=project.database_path))
    item = next(value.item for value in tree.items if value.item.display_name == "second.txt")
    promoted = app.promote_workspace_item_to_context(PromoteWorkspaceItemToContextRequest(
        project_id=project.project_id, database_path=project.database_path,
        workspace_item_id=item.id, actor="tester",
        expected_workspace_revision=tree.workspace_revision, expected_context_revision=1))
    second = promoted.capture.context_revision_id
    app.extract_context_revisions(ExtractContextRevisionsRequest(
        project.project_id, project.database_path, (second,), "tester"))

    class _CompareProvider:
        def invoke(self, *, model, key, action, elements):
            return ProviderResult({"claims": [{
                "kind": "CHANGE", "text": "Synthetic difference",
                "element_ids": [elements[0].id, elements[-1].id],
                "subject": None, "time": None,
            }]}, 120, 40)

    service = _service(_CompareProvider())
    plan = service.plan(AnalysisPlanRequest(
        project.project_id, project.database_path, AnalysisAction.COMPARE,
        (first, second), "openai", "gpt-6-luna"))
    assert {value.revision_id for value in plan.elements} == {first, second}
    result = service.execute(plan, actor="tester", confirmed_token=plan.consent_token)
    assert result.status == AnalysisStatus.SUCCEEDED
    assert len(result.claims[0].element_ids) == 2


def test_key_fact_card_remains_a_cited_draft(tmp_path):
    project, revision = _ready(tmp_path)

    class _FactProvider:
        def invoke(self, *, model, key, action, elements):
            return ProviderResult({"claims": [{
                "kind": "FACT", "text": "Synthetic project fact",
                "element_ids": [elements[0].id], "subject": "Project",
                "time": None,
            }]}, 90, 25)

    service = _service(_FactProvider())
    plan = service.plan(AnalysisPlanRequest(
        project.project_id, project.database_path, AnalysisAction.KEY_FACTS,
        (revision,), "openai", "gpt-6-luna"))
    result = service.execute(plan, actor="tester", confirmed_token=plan.consent_token)
    assert result.status == AnalysisStatus.SUCCEEDED
    assert result.claims[0].subject == "Project"
    assert result.claims[0].kind == "FACT"
