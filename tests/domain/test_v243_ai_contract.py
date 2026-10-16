from dataclasses import replace

import pytest

from pig.domain.ai_policy import (
    AnalysisAction, AnalysisElement, input_fingerprint, validate_model_output,
)
from pig.domain.exceptions import InvariantViolationError


ELEMENT = AnalysisElement("element-1", "revision-1", "PAGE", "1", "Synthetic text")


def test_cited_summary_is_accepted_and_fingerprint_binds_content_and_model():
    claim = {"kind": "SUMMARY", "text": "A fact", "element_ids": [ELEMENT.id],
             "subject": None, "time": None}
    assert validate_model_output({"claims": [claim]}, action=AnalysisAction.SUMMARY,
                                 elements=(ELEMENT,))[0].element_ids == (ELEMENT.id,)
    original = input_fingerprint(action=AnalysisAction.SUMMARY, provider="fake",
                                 model="fake-1", elements=(ELEMENT,), prompt_version="1")
    changed = input_fingerprint(action=AnalysisAction.SUMMARY, provider="fake",
                                model="fake-1", elements=(replace(ELEMENT, text="Changed"),),
                                prompt_version="1")
    assert original != changed


@pytest.mark.parametrize("element_ids", [[], ["unknown"], [ELEMENT.id, ELEMENT.id]])
def test_invalid_citations_are_rejected(element_ids):
    with pytest.raises(InvariantViolationError):
        validate_model_output({"claims": [{"kind": "SUMMARY", "text": "A fact",
                                           "element_ids": element_ids,
                                           "subject": None, "time": None}]},
                              action=AnalysisAction.SUMMARY, elements=(ELEMENT,))


@pytest.mark.parametrize("action,kind", [
    (AnalysisAction.COMPARE, "CHANGE"),
    (AnalysisAction.KEY_FACTS, "FACT"),
])
def test_compare_and_fact_cards_require_typed_cited_claims(action, kind):
    elements = (ELEMENT, AnalysisElement("element-2", "revision-2", "PAGE", "2",
                                          "Other synthetic text")) if action == AnalysisAction.COMPARE else (ELEMENT,)
    citations = [element.id for element in elements]
    values = validate_model_output({"claims": [{
        "kind": kind, "text": "Synthetic finding", "element_ids": citations,
        "subject": "Synthetic subject" if kind == "FACT" else None,
        "time": None,
    }]}, action=action, elements=elements)
    assert values[0].kind == kind
    with pytest.raises(InvariantViolationError):
        validate_model_output({"claims": [{
            "kind": "SUMMARY", "text": "Wrong action", "element_ids": [ELEMENT.id],
            "subject": None, "time": None,
        }]}, action=action, elements=elements)
