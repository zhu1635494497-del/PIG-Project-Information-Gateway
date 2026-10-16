"""Deterministic safety boundaries for opt-in, cited model drafts.

The model is never an authority for project state or evidence identity.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from typing import Mapping, Sequence

from pig.domain.exceptions import InvariantViolationError


class AnalysisAction(str, Enum):
    SUMMARY = "SUMMARY"
    COMPARE = "COMPARE"
    KEY_FACTS = "KEY_FACTS"


class AnalysisStatus(str, Enum):
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    INTERRUPTED = "INTERRUPTED"


@dataclass(frozen=True, slots=True)
class AnalysisElement:
    id: str
    revision_id: str
    locator_kind: str
    locator_value: str
    text: str


@dataclass(frozen=True, slots=True)
class ModelClaim:
    kind: str
    text: str
    element_ids: tuple[str, ...]
    subject: str | None = None
    time: str | None = None


def validate_model_output(raw: object, *, action: AnalysisAction,
                          elements: Sequence[AnalysisElement]) -> tuple[ModelClaim, ...]:
    """Reject malformed, unsupported, uncited, or out-of-plan model claims."""
    if not isinstance(raw, dict) or set(raw) != {"claims"}:
        raise InvariantViolationError("model result schema is invalid")
    rows = raw["claims"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= 20:
        raise InvariantViolationError("model result claim count is invalid")
    allowed = {element.id for element in elements}
    revision_by_element = {element.id: element.revision_id for element in elements}
    required_kind = {
        AnalysisAction.SUMMARY: "SUMMARY",
        AnalysisAction.COMPARE: "CHANGE",
        AnalysisAction.KEY_FACTS: "FACT",
    }[action]
    result: list[ModelClaim] = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {
            "kind", "text", "element_ids", "subject", "time"
        }:
            raise InvariantViolationError("model claim schema is invalid")
        kind, content, links = row["kind"], row["text"], row["element_ids"]
        if kind != required_kind or not isinstance(content, str) or not 1 <= len(content.strip()) <= 2000:
            raise InvariantViolationError("model claim content is invalid")
        if (not isinstance(links, list) or not 1 <= len(links) <= 8
                or any(not isinstance(value, str) or value not in allowed for value in links)
                or len(set(links)) != len(links)):
            raise InvariantViolationError("model citation is outside selected input")
        if (action == AnalysisAction.COMPARE
                and len({revision_by_element[value] for value in links}) < 2):
            raise InvariantViolationError("comparison claim must cite both Revisions")
        for name in ("subject", "time"):
            value = row[name]
            if value is not None and (not isinstance(value, str) or len(value) > 200):
                raise InvariantViolationError("model fact-card field is invalid")
        result.append(ModelClaim(kind, content.strip(), tuple(links),
                                 row["subject"], row["time"]))
    return tuple(result)


def input_fingerprint(*, action: AnalysisAction, provider: str, model: str,
                      elements: Sequence[AnalysisElement], prompt_version: str) -> str:
    payload = {
        "action": action.value, "provider": provider, "model": model,
        "prompt_version": prompt_version,
        "elements": [{"id": e.id, "revision_id": e.revision_id,
                      "locator_kind": e.locator_kind, "locator_value": e.locator_value,
                      "sha256": sha256(e.text.encode("utf-8")).hexdigest()}
                     for e in elements],
    }
    return sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":")).encode("utf-8")).hexdigest()
