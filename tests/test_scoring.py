from copy import deepcopy

import pytest

from src.db import DEFAULT_CRITERIA
from src.scoring import assess_shortlist, score_and_rank, validate_criteria


def criteria():
    return [
        {
            "criterion_id": criterion_id,
            "name": name,
            "description": description,
            "weight": weight,
            "max_score": maximum,
            "is_active": True,
            "version": 1,
        }
        for criterion_id, name, description, weight, maximum in DEFAULT_CRITERIA
    ]


def supplier(name, scores, submitted="2026-10-01", experience=3.0):
    rows = [
        {
            "criterion_id": criterion["criterion_id"],
            "score": score,
            "max_score": criterion["max_score"],
            "weight": criterion["weight"],
            "justification": "documented",
            "evidence": "proposal excerpt",
            "evidence_page": 1,
            "confidence": "medium",
            "missing_evidence": [],
        }
        for criterion, score in zip(criteria(), scores, strict=True)
    ]
    return {
        "supplier_name": name,
        "submission_date": submitted,
        "experience_rating": experience,
        "scorecard": {
            "criteria": rows,
            "criteria_by_id": {row["criterion_id"]: row for row in rows},
            "risks": [],
            "overall_summary": "summary",
        },
        "warnings": [],
    }


def test_seed_weights_total_100_and_99_is_rejected():
    rows = criteria()
    validate_criteria(rows)
    rows[0]["weight"] -= 1
    with pytest.raises(ValueError, match="must total 100"):
        validate_criteria(rows)


def test_weighted_score_and_peer_metrics_are_calculated_deterministically():
    rows = criteria()
    suppliers = [
        supplier("Supplier B", [8] * 8, submitted="2026-10-02"),
        supplier("Supplier A", [8] * 8, submitted="2026-10-01"),
    ]
    ranked = score_and_rank(suppliers, rows)
    assert ranked[0]["supplier_name"] == "Supplier A"
    assert ranked[0]["technical_rank"] == 1
    assert ranked[0]["absolute_score"] == pytest.approx(80)
    assert ranked[0]["ppi"] == pytest.approx(100)
    metric = ranked[1]["criterion_metrics"]["manufacturing_capability"]
    assert metric["benchmark"] == 8
    assert metric["gap"] == 0
    assert metric["relative_pct"] == 100


def test_industry_index_is_cohort_relative_and_mean_is_100():
    ranked = score_and_rank(
        [
            supplier("Lower score", [4] * 8),
            supplier("Higher score", [8] * 8),
        ],
        criteria(),
    )
    lower = next(row for row in ranked if row["supplier_name"] == "Lower score")
    higher = next(row for row in ranked if row["supplier_name"] == "Higher score")

    assert lower["industry_index"] == pytest.approx(66.6667)
    assert higher["industry_index"] == pytest.approx(133.3333)
    assert sum(row["industry_index"] for row in ranked) / len(ranked) == pytest.approx(100)


def test_rank_tie_breaks_by_experience_then_name():
    rows = criteria()
    equal = [8] * 8
    suppliers = [
        supplier("zeta", equal, experience=4.5),
        supplier("Beta", equal, experience=4.5),
        supplier("Alpha", equal, experience=4.0),
    ]
    ranked = score_and_rank(suppliers, rows)
    assert [row["supplier_name"] for row in ranked] == ["Beta", "zeta", "Alpha"]


def test_zero_benchmark_is_safe_and_warned():
    rows = criteria()
    scores = [0] * 8
    result = score_and_rank([supplier("No evidence", scores)], rows)[0]
    assert result["ppi"] == 0
    assert "ZERO_BENCHMARK_RELATIVE_PERCENT_SET_TO_ZERO:manufacturing_capability" in result["warnings"]


def test_pending_or_failed_gate_never_becomes_shortlist_candidate():
    pending = [{"status": "PENDING_VERIFICATION"}]
    assert assess_shortlist(pending, 99, 70) == (
        "PENDING_VERIFICATION",
        "PENDING_MANDATORY_REVIEW",
    )
    failed = [{"status": "FAIL"}]
    assert assess_shortlist(failed, 99, 70) == (
        "NOT_ELIGIBLE",
        "EXCLUDED_BY_MANDATORY_GATE",
    )
    assert assess_shortlist([{"status": "PASS"}], 60, 70)[1] == "BELOW_SCORE_THRESHOLD"


def test_seed_criteria_are_not_mutated_by_fixture_creation():
    original = deepcopy(DEFAULT_CRITERIA)
    criteria()
    assert DEFAULT_CRITERIA == original
