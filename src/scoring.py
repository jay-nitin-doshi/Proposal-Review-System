"""Deterministic score, peer benchmark, rank, and eligibility calculations."""

from __future__ import annotations

import math
from datetime import date
from typing import Any


def validate_criteria(criteria: list[dict[str, Any]]) -> None:
    active = [row for row in criteria if row["is_active"]]
    if not active:
        raise ValueError("At least one criterion must be active.")
    ids = [row["criterion_id"] for row in criteria]
    if len(ids) != len(set(ids)) or any(not value.strip() for value in ids):
        raise ValueError("Criterion IDs must be non-empty and unique.")
    for row in active:
        weight = float(row["weight"])
        maximum = float(row["max_score"])
        if not math.isfinite(weight) or weight < 0:
            raise ValueError(f"Invalid weight for {row['criterion_id']}.")
        if not math.isfinite(maximum) or maximum <= 0:
            raise ValueError(f"Invalid maximum score for {row['criterion_id']}.")
    total = sum(float(row["weight"]) for row in active)
    if not math.isclose(total, 100.0, abs_tol=1e-6):
        raise ValueError(f"Active criterion weights must total 100; currently {total:g}.")


def score_and_rank(
    suppliers: list[dict[str, Any]], criteria: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Add absolute score, criterion benchmarks, PPI, and deterministic rank."""
    validate_criteria(criteria)
    active = [row for row in criteria if row["is_active"]]
    if not suppliers:
        return []
    benchmarks = {
        criterion["criterion_id"]: max(
            float(supplier["scorecard"]["criteria_by_id"][criterion["criterion_id"]]["score"])
            for supplier in suppliers
        )
        for criterion in active
    }

    for supplier in suppliers:
        points = 0.0
        ppi_points = 0.0
        criterion_metrics: dict[str, dict[str, float | None]] = {}
        for criterion in active:
            criterion_id = criterion["criterion_id"]
            score = float(supplier["scorecard"]["criteria_by_id"][criterion_id]["score"])
            maximum = float(criterion["max_score"])
            weight = float(criterion["weight"])
            benchmark = benchmarks[criterion_id]
            relative = (100.0 * score / benchmark) if benchmark > 0 else 0.0
            points += score / maximum * weight
            ppi_points += relative * weight
            criterion_metrics[criterion_id] = {
                "benchmark": benchmark,
                "gap": score - benchmark,
                "relative_pct": relative,
                "weighted_contribution": score / maximum * weight,
            }
            if benchmark == 0:
                supplier.setdefault("warnings", []).append(
                    f"ZERO_BENCHMARK_RELATIVE_PERCENT_SET_TO_ZERO:{criterion_id}"
                )
        supplier["absolute_score"] = points
        supplier["ppi"] = ppi_points / sum(float(row["weight"]) for row in active)
        supplier["criterion_metrics"] = criterion_metrics

    cohort_average = sum(
        float(supplier["absolute_score"]) for supplier in suppliers
    ) / len(suppliers)
    for supplier in suppliers:
        supplier["industry_index"] = (
            100.0 * float(supplier["absolute_score"]) / cohort_average
            if cohort_average > 0
            else 0.0
        )
        if cohort_average == 0:
            supplier.setdefault("warnings", []).append(
                "ZERO_COHORT_AVERAGE_INDUSTRY_INDEX_SET_TO_ZERO"
            )

    def rank_key(supplier: dict[str, Any]) -> tuple[Any, ...]:
        return (
            -float(supplier["ppi"]),
            date.fromisoformat(supplier["submission_date"]),
            -float(supplier["experience_rating"]),
            supplier["supplier_name"].casefold(),
            supplier["supplier_name"],
        )

    ranked = sorted(suppliers, key=rank_key)
    for rank, supplier in enumerate(ranked, start=1):
        supplier["technical_rank"] = rank
    return ranked


def assess_shortlist(
    gates: list[dict[str, Any]], absolute_score: float, minimum_score: float
) -> tuple[str, str]:
    """Return a non-award eligibility label and threshold-based shortlist status."""
    statuses = {gate["status"] for gate in gates}
    if "FAIL" in statuses:
        return "NOT_ELIGIBLE", "EXCLUDED_BY_MANDATORY_GATE"
    if "PENDING_VERIFICATION" in statuses:
        return "PENDING_VERIFICATION", "PENDING_MANDATORY_REVIEW"
    if absolute_score < minimum_score:
        return "ELIGIBLE_FOR_REVIEW", "BELOW_SCORE_THRESHOLD"
    return "ELIGIBLE_FOR_REVIEW", "SHORTLIST_CANDIDATE"
