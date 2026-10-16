"""V2.4.1 synthetic consumer for the in-memory Context Bundle contract."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from pig.application.experience_contracts import (
    BundleExperienceRecord,
    BundleObservedEvent,
    extend_context_manifest_v2,
)
from pig.domain.enums import ContextRevisionCaptureStatus
from pig.domain.exceptions import InvariantViolationError
from pig.domain.experience_policy import (
    ExperienceEvidenceRef,
    ExperienceEvidenceRole,
    ExperienceEventRef,
    ExperienceKind,
    ExperienceStatus,
)


NOW = datetime(2026, 10, 11, 9, tzinfo=timezone.utc)


def _base(*, include_r2: bool = True):
    entries = [{"context_item_id": "I1", "context_revision_id": "R1"}]
    if include_r2:
        entries.append({"context_item_id": "I2", "context_revision_id": "R2"})
    return {
        "schema_version": "1.0", "export_id": "P1",
        "project": {"id": "launch", "name": "新品发布"},
        "context_revision": 7, "sections": [], "entries": entries,
    }


def _record(*, event_links: tuple[ExperienceEventRef, ...] = (ExperienceEventRef("launch", "E1"),)):
    return BundleExperienceRecord(
        id="J1", version=2, kind=ExperienceKind.JUDGMENT,
        status=ExperienceStatus.CONFIRMED, title="选择供应商 B",
        body="虽非最低价，但可在发布日期前交付。", author="owner",
        recorded_at=NOW,
        revision_links=(
            ExperienceEvidenceRef("launch", "I1", "R1",
                                  ContextRevisionCaptureStatus.READY,
                                  ExperienceEvidenceRole.SUPPORTS),
            ExperienceEvidenceRef("launch", "I2", "R2",
                                  ContextRevisionCaptureStatus.READY,
                                  ExperienceEvidenceRole.SUPPORTS),
        ),
        event_links=event_links,
    )


def _event(*, project_id: str = "launch"):
    return BundleObservedEvent(
        project_id=project_id, id="E1", type="CONTEXT_REVISION_CAPTURED",
        occurred_at=NOW, actor="owner",
    )


def test_synthetic_consumer_reconstructs_judgment_and_exact_evidence() -> None:
    base = _base()
    result = extend_context_manifest_v2(
        base_manifest=base, records=(_record(),), observed_events=(_event(),),
    )
    decoded = json.loads(json.dumps(result, ensure_ascii=False))
    assert base["schema_version"] == "1.0"
    assert "experience_records" not in base
    assert decoded["schema_version"] == "2.0"
    record = decoded["experience_records"][0]
    assert record["title"] == "选择供应商 B"
    assert record["status"] == "CONFIRMED"
    assert record["version"] == 2
    assert {(link["context_item_id"], link["context_revision_id"])
            for link in record["revision_links"]} == {("I1", "R1"), ("I2", "R2")}
    assert record["event_ids"] == ["E1"]
    assert decoded["observed_events"][0]["type"] == "CONTEXT_REVISION_CAPTURED"
    assert "body" not in decoded["observed_events"][0]


def test_bundle_cannot_silently_expand_to_missing_revision() -> None:
    with pytest.raises(InvariantViolationError, match="missing evidence"):
        extend_context_manifest_v2(
            base_manifest=_base(include_r2=False),
            records=(_record(),), observed_events=(_event(),),
        )


def test_event_snapshot_must_be_linked_and_same_project() -> None:
    with pytest.raises(InvariantViolationError, match="Event identity"):
        extend_context_manifest_v2(
            base_manifest=_base(), records=(_record(),),
            observed_events=(_event(project_id="other"),),
        )
    with pytest.raises(InvariantViolationError, match="unreferenced"):
        extend_context_manifest_v2(
            base_manifest=_base(), records=(_record(event_links=()),),
            observed_events=(_event(),),
        )


def test_rejects_wrong_base_version_and_naive_timestamp() -> None:
    base = _base()
    base["schema_version"] = "3.0"
    with pytest.raises(InvariantViolationError, match="base schema"):
        extend_context_manifest_v2(
            base_manifest=base, records=(_record(),), observed_events=(_event(),),
        )
    invalid_record = replace(_record(), recorded_at=NOW.replace(tzinfo=None))
    with pytest.raises(InvariantViolationError, match="timezone"):
        extend_context_manifest_v2(
            base_manifest=_base(), records=(invalid_record,), observed_events=(_event(),),
        )
