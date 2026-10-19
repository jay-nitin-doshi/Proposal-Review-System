"""Structured output contract for LLM-generated tender scorecards."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CriterionAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion_id: str = Field(min_length=1)
    score: float = Field(ge=0)
    max_score: float = Field(gt=0)
    justification: str
    evidence: str
    evidence_page: int | None = Field(default=None, ge=1)
    confidence: str
    missing_evidence: list[str] = Field(default_factory=list)


class TenderScorecard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supplier_name: str
    criteria: list[CriterionAssessment]
    risks: list[str] = Field(default_factory=list)
    overall_summary: str


class ValidationFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion_id: str = Field(min_length=1)
    severity: Literal["low", "medium", "high", "critical"]
    explanation: str = Field(min_length=1)


def normalize_provider_review_shape(value: object) -> object:
    """Accept common provider JSON wrappers and map them to our contract."""
    if not isinstance(value, Mapping):
        return value

    payload: Mapping[str, object] = value
    nested = payload.get("validation_result")
    if isinstance(nested, Mapping):
        payload = nested

    raw_findings = payload.get("findings", [])
    if not isinstance(raw_findings, list):
        return value
    findings: list[dict[str, object]] = []
    unmapped_findings: list[str] = []
    for finding in raw_findings:
        if isinstance(finding, str) and finding.strip():
            unmapped_findings.append(finding.strip())
            continue
        if not isinstance(finding, Mapping):
            return value
        explanation = finding.get(
            "explanation",
            finding.get("issue", finding.get("finding")),
        )
        if not isinstance(explanation, str):
            return value
        criterion_id = finding.get("criterion_id")
        if not isinstance(criterion_id, str):
            unmapped_findings.append(explanation)
            continue
        severity = finding.get("severity")
        if severity not in {"low", "medium", "high", "critical"}:
            material = finding.get(
                "material",
                finding.get("material_issue"),
            )
            severity = "high" if material is True else "low"
        findings.append(
            {
                "criterion_id": criterion_id,
                "severity": severity,
                "explanation": explanation,
            }
        )

    passed = payload.get("passed")
    if not isinstance(passed, bool):
        validation = payload.get(
            "overall_validation",
            value.get("validation_result") if isinstance(value, Mapping) else None,
        )
        if isinstance(validation, str):
            normalized_validation = validation.strip().casefold()
            if normalized_validation in {
                "pass",
                "passed",
                "approved",
                "true",
            }:
                passed = True
            elif normalized_validation in {
                "fail",
                "failed",
                "rejected",
                "false",
            }:
                passed = False
            else:
                return value
        else:
            return value
    risks = payload.get("risks", [])
    if not isinstance(risks, list) or not all(
        isinstance(risk, str) for risk in risks
    ):
        return value
    risks = [
        *risks,
        *[
            f"Unmapped evidence finding: {finding}"
            for finding in unmapped_findings
        ],
    ]
    return {
        "passed": passed and not unmapped_findings,
        "findings": findings,
        "risks": risks,
    }


class ScorecardReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool
    findings: list[ValidationFinding] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_provider_review_shape(cls, value: object) -> object:
        return normalize_provider_review_shape(value)
