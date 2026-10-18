import pytest

from src.db import DEFAULT_CRITERIA
from src.models import ScorecardValidationError, validate_scorecard


def active_criteria():
    return [
        {
            "criterion_id": criterion_id,
            "name": name,
            "description": description,
            "weight": weight,
            "max_score": maximum,
            "is_active": 1,
            "version": 1,
        }
        for criterion_id, name, description, weight, maximum in DEFAULT_CRITERIA
    ]


def criterion_result(criterion_id: str, score: float = 7):
    criterion = next(
        row for row in active_criteria() if row["criterion_id"] == criterion_id
    )
    return {
        "criterion_id": criterion_id,
        "score": score,
        "max_score": criterion["max_score"],
        "justification": "evidence-based",
        "evidence": "Proposal page 1",
        "evidence_page": 1,
        "missing_evidence": [],
    }


def test_valid_json_is_normalized_to_exact_active_criteria():
    criteria = active_criteria()
    payload = {
        "criteria": [criterion_result(row["criterion_id"]) for row in criteria],
        "risks": [],
        "overall_summary": "Review summary",
    }
    scorecard, warnings = validate_scorecard(payload, criteria)
    assert len(scorecard["criteria"]) == len(criteria)
    assert not warnings
    assert scorecard["criteria_by_id"]["quality_system"]["score"] == 7


def test_missing_criterion_defaults_to_zero_with_warning():
    criteria = active_criteria()
    payload = {"criteria": [], "risks": [], "overall_summary": ""}
    scorecard, warnings = validate_scorecard(payload, criteria)
    assert scorecard["criteria"][0]["score"] == 0
    assert len(warnings) == len(criteria)
    assert warnings[0].startswith("MISSING_CRITERION_SCORE_DEFAULTED_TO_ZERO:")


def test_positive_score_without_evidence_is_conservatively_zeroed():
    criteria = active_criteria()
    payload = {
        "criteria": [
            {
                **criterion_result("quality_system"),
                "evidence": "",
            }
        ]
    }
    scorecard, warnings = validate_scorecard(payload, criteria)
    assert scorecard["criteria_by_id"]["quality_system"]["score"] == 0
    assert "POSITIVE_SCORE_WITHOUT_DOCUMENTARY_EVIDENCE_DEFAULTED_TO_ZERO:quality_system" in warnings


@pytest.mark.parametrize(
    "items, message",
    [
        (
            [
                {
                    **criterion_result("quality_system"),
                    "criterion_id": "not_a_criterion",
                }
            ],
            "Unknown criterion",
        ),
        (
            [
                criterion_result("quality_system"),
                criterion_result("quality_system"),
            ],
            "Duplicate criterion",
        ),
        ([criterion_result("quality_system", 11)], "outside 0..10"),
        ([criterion_result("quality_system", float("inf"))], "outside 0..10"),
    ],
)
def test_invalid_scores_or_criteria_are_rejected(items, message):
    with pytest.raises(ScorecardValidationError, match=message):
        validate_scorecard({"criteria": items}, active_criteria())


def test_malformed_json_is_reported_not_silently_normalized():
    with pytest.raises(ScorecardValidationError, match="Invalid JSON"):
        validate_scorecard("{not json", active_criteria())


def test_boolean_is_not_accepted_as_numeric_score():
    with pytest.raises(ScorecardValidationError, match="must be numeric"):
        validate_scorecard(
            {"criteria": [criterion_result("quality_system", True)]},
            active_criteria(),
        )
