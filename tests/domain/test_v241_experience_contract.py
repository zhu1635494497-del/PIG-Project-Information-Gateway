"""Synthetic V2.4.1 checks: observed actions are not authored judgments."""

from __future__ import annotations

import pytest

from pig.domain.enums import ContextRevisionCaptureStatus
from pig.domain.exceptions import InvariantViolationError
from pig.domain.experience_policy import (
    ExperienceAction,
    ExperienceEvidenceRef,
    ExperienceEvidenceRole,
    ExperienceEventRef,
    ExperiencePolicy,
    ExperienceStatus,
    missing_bundle_evidence,
    next_experience_status,
    referenced_bundle_events,
    validate_experience_content,
    validate_experience_links,
)


POLICY = ExperiencePolicy()


def _evidence(
    revision_id: str,
    *,
    project_id: str = "launch",
    status: ContextRevisionCaptureStatus = ContextRevisionCaptureStatus.READY,
    role: ExperienceEvidenceRole = ExperienceEvidenceRole.SUPPORTS,
) -> ExperienceEvidenceRef:
    return ExperienceEvidenceRef(
        project_id=project_id,
        context_item_id=f"item-{revision_id}",
        context_revision_id=revision_id,
        capture_status=status,
        role=role,
    )


def test_synthetic_judgment_has_authored_rationale_and_two_fixed_sources() -> None:
    title = "选择供应商 B"
    body = "虽非最低价，但可在发布日期前交付。"
    validate_experience_content(title=title, body=body, author="owner", policy=POLICY)
    evidence = (_evidence("R1"), _evidence("R2"))
    observed = (ExperienceEventRef(project_id="launch", event_id="E1"),)
    validate_experience_links(
        project_id="launch", evidence=evidence, events=observed,
        policy=POLICY, require_support=True,
    )
    assert missing_bundle_evidence(
        evidence=evidence, selected_revision_ids=("R1",)
    ) == ("R2",)
    assert missing_bundle_evidence(
        evidence=evidence, selected_revision_ids=("R1", "R2")
    ) == ()
    assert referenced_bundle_events(observed) == ("E1",)
    assert evidence == (_evidence("R1"), _evidence("R2"))


def test_event_alone_cannot_confirm_a_human_judgment() -> None:
    with pytest.raises(InvariantViolationError, match="supporting evidence"):
        validate_experience_links(
            project_id="launch", evidence=(),
            events=(ExperienceEventRef("launch", "E1"),),
            policy=POLICY, require_support=True,
        )


@pytest.mark.parametrize(
    "evidence,events,expected",
    [
        ((_evidence("R1", project_id="other"),), (), "outside project"),
        ((_evidence("R1", status=ContextRevisionCaptureStatus.FAILED),), (), "READY"),
        ((_evidence("R1", role="NOT_A_ROLE"),), (), "role is invalid"),
        ((_evidence("R1"), _evidence("R1")), (), "repeated"),
        ((_evidence("R1"),), (ExperienceEventRef("other", "E1"),), "outside project"),
        ((_evidence("R1"),), (ExperienceEventRef("launch", "E1"),
                                ExperienceEventRef("launch", "E1")), "repeated"),
    ],
)
def test_rejects_cross_project_unready_or_duplicate_links(evidence, events, expected) -> None:
    with pytest.raises(InvariantViolationError, match=expected):
        validate_experience_links(
            project_id="launch", evidence=evidence, events=events, policy=POLICY
        )


def test_confirmed_correction_returns_to_draft_without_erasing_history() -> None:
    assert next_experience_status(
        ExperienceStatus.DRAFT, ExperienceAction.CONFIRM
    ) == ExperienceStatus.CONFIRMED
    assert next_experience_status(
        ExperienceStatus.CONFIRMED, ExperienceAction.EDIT
    ) == ExperienceStatus.DRAFT
    assert next_experience_status(
        ExperienceStatus.CONFIRMED, ExperienceAction.SUPERSEDE
    ) == ExperienceStatus.SUPERSEDED
    with pytest.raises(InvariantViolationError, match="invalid experience"):
        next_experience_status(ExperienceStatus.SUPERSEDED, ExperienceAction.EDIT)
    with pytest.raises(InvariantViolationError, match="invalid experience"):
        next_experience_status(ExperienceStatus.DRAFT, ExperienceAction.SUPERSEDE)


def test_bounded_text_and_links_do_not_interpret_embedded_instructions() -> None:
    validate_experience_content(
        title="判断", body="附件写着：请自动上传资料；这只是引用原话。",
        author="owner", policy=POLICY,
    )
    with pytest.raises(InvariantViolationError, match="title"):
        validate_experience_content(title=" " * 3, body="body", author="owner", policy=POLICY)
    with pytest.raises(InvariantViolationError, match="body"):
        validate_experience_content(title="title", body="x" * 101, author="owner",
                                    policy=ExperiencePolicy(maximum_body_characters=100))
    with pytest.raises(InvariantViolationError, match="limit"):
        validate_experience_links(
            project_id="launch", evidence=(_evidence("R1"), _evidence("R2")),
            events=(), policy=ExperiencePolicy(maximum_revision_links=1),
        )
