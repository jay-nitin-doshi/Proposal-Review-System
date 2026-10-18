"""Validation and normalization for evaluator-produced scorecards."""

from __future__ import annotations

import json
import math
from typing import Any


class ScorecardValidationError(ValueError):
    """Raised when a scorecard cannot be safely normalized."""


def validate_scorecard(
    payload: str | dict[str, Any], criteria: list[dict[str, Any]]
) -> tuple[dict[str, Any], list[str]]:
    """Validate a scorecard and default omitted criteria to zero with warnings."""
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ScorecardValidationError(f"Invalid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ScorecardValidationError("Scorecard JSON must be an object.")

    criteria_rows = payload.get("criteria")
    if not isinstance(criteria_rows, list):
        raise ScorecardValidationError("'criteria' must be a list.")

    active = {row["criterion_id"]: row for row in criteria}
    normalized: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    for item in criteria_rows:
        if not isinstance(item, dict):
            raise ScorecardValidationError("Each criterion result must be an object.")
        criterion_id = item.get("criterion_id")
        if not isinstance(criterion_id, str) or not criterion_id:
            raise ScorecardValidationError("Each result needs a non-empty criterion_id.")
        if criterion_id not in active:
            raise ScorecardValidationError(
                f"Unknown criterion_id: {criterion_id!r}."
            )
        if criterion_id in normalized:
            raise ScorecardValidationError(
                f"Duplicate criterion_id: {criterion_id!r}."
            )

        criterion = active[criterion_id]
        score = item.get("score")
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise ScorecardValidationError(
                f"Score for {criterion_id!r} must be numeric."
            )
        score = float(score)
        if not math.isfinite(score) or not 0 <= score <= float(criterion["max_score"]):
            raise ScorecardValidationError(
                f"Score for {criterion_id!r} is outside 0..{criterion['max_score']}."
            )

        reported_max = item.get("max_score", criterion["max_score"])
        if (
            isinstance(reported_max, bool)
            or not isinstance(reported_max, (int, float))
            or not math.isclose(float(reported_max), float(criterion["max_score"]))
        ):
            raise ScorecardValidationError(
                f"Maximum score for {criterion_id!r} does not match active criteria."
            )

        justification = item.get("justification", "")
        evidence = item.get("evidence", "")
        if not isinstance(justification, str) or not isinstance(evidence, str):
            raise ScorecardValidationError(
                f"Justification and evidence for {criterion_id!r} must be strings."
            )
        if score > 0 and not evidence.strip():
            score = 0.0
            warnings.append(
                f"POSITIVE_SCORE_WITHOUT_DOCUMENTARY_EVIDENCE_DEFAULTED_TO_ZERO:{criterion_id}"
            )
        page = item.get("evidence_page")
        if page is not None and (
            isinstance(page, bool) or not isinstance(page, int) or page < 1
        ):
            raise ScorecardValidationError(
                f"Evidence page for {criterion_id!r} must be a positive integer or null."
            )
        missing = item.get("missing_evidence", [])
        if not isinstance(missing, list) or not all(
            isinstance(entry, str) for entry in missing
        ):
            raise ScorecardValidationError(
                f"Missing evidence for {criterion_id!r} must be a list of strings."
            )

        normalized[criterion_id] = {
            "criterion_id": criterion_id,
            "score": score,
            "max_score": float(criterion["max_score"]),
            "weight": float(criterion["weight"]),
            "justification": justification.strip(),
            "evidence": evidence.strip(),
            "evidence_page": page,
            "confidence": item.get("confidence", "not stated"),
            "missing_evidence": missing,
        }

    for criterion in criteria:
        criterion_id = criterion["criterion_id"]
        if criterion_id not in normalized:
            normalized[criterion_id] = {
                "criterion_id": criterion_id,
                "score": 0.0,
                "max_score": float(criterion["max_score"]),
                "weight": float(criterion["weight"]),
                "justification": "No valid score was supplied; conservatively defaulted to zero.",
                "evidence": "",
                "evidence_page": None,
                "confidence": "low",
                "missing_evidence": ["Criterion score was not provided."],
            }
            warnings.append(f"MISSING_CRITERION_SCORE_DEFAULTED_TO_ZERO:{criterion_id}")

    risks = payload.get("risks", [])
    if not isinstance(risks, list) or not all(isinstance(item, str) for item in risks):
        raise ScorecardValidationError("'risks' must be a list of strings.")
    summary = payload.get("overall_summary", "")
    if not isinstance(summary, str):
        raise ScorecardValidationError("'overall_summary' must be a string.")

    normalized_scorecard = {
        "criteria": [normalized[row["criterion_id"]] for row in criteria],
        "criteria_by_id": normalized,
        "risks": risks,
        "overall_summary": summary.strip(),
    }
    return normalized_scorecard, warnings
