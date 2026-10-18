"""Dashboard-friendly tables derived from persisted evaluation runs."""

from __future__ import annotations

from typing import Any


def build_leaderboard_rows(suppliers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten persisted supplier results into executive dashboard records."""
    rows = []
    for supplier in suppliers:
        commercial = supplier.get("result_json", {}).get("commercial_review", {})
        industry_index = supplier.get(
            "industry_index",
            supplier.get("result_json", {}).get("industry_index", 0.0),
        )
        gates = supplier.get("gates", [])
        rows.append(
            {
                "Technical rank": supplier.get("technical_rank"),
                "Supplier": supplier["supplier_name"],
                "Final score": float(supplier["absolute_score"]),
                "PPI": float(supplier["ppi"]),
                "Industry index (cohort proxy)": float(industry_index),
                "Submission date": supplier["submission_date"],
                "Experience / 5": float(supplier["experience_rating"]),
                "Evaluation": supplier["evaluation_status"],
                "Commercial review": commercial.get("status", "NOT_REVIEWED"),
                "Eligibility": supplier["eligibility_status"],
                "Shortlist status": supplier["shortlist_status"],
                "Gate checks open": sum(gate["status"] != "PASS" for gate in gates),
                "Warnings": len(supplier.get("warnings", [])),
            }
        )
    return rows


def build_output_matrix_rows(
    suppliers: list[dict[str, Any]], criteria: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Build a ranked supplier-by-criterion matrix with final output scores."""
    criterion_names = {
        row["criterion_id"]: row["name"]
        for row in criteria
    }
    rows = []
    for supplier in sorted(
        suppliers,
        key=lambda item: (
            item.get("technical_rank") is None,
            item.get("technical_rank") or float("inf"),
        ),
    ):
        row: dict[str, Any] = {
            "Rank": supplier.get("technical_rank"),
            "Supplier": supplier["supplier_name"],
        }
        for result in supplier.get("criterion_results", []):
            criterion_id = result["criterion_id"]
            criterion_name = criterion_names.get(criterion_id, criterion_id)
            row[f"{criterion_name} (score / max)"] = (
                f"{float(result['score']):g} / {float(result['max_score']):g}"
            )
        row["Final score / 100"] = float(supplier["absolute_score"])
        row["PPI (%)"] = float(supplier["ppi"])
        row["Industry index (cohort proxy)"] = float(
            supplier.get(
                "industry_index",
                supplier.get("result_json", {}).get("industry_index", 0.0),
            )
        )
        row["Eligibility"] = supplier["eligibility_status"]
        row["Shortlist status"] = supplier["shortlist_status"]
        rows.append(row)
    return rows


def build_criterion_rows(
    suppliers: list[dict[str, Any]], criteria: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Flatten criterion scores and weighted contributions for comparison charts."""
    criterion_names = {
        row["criterion_id"]: row["name"]
        for row in criteria
    }
    rows = []
    for supplier in suppliers:
        for criterion in supplier.get("criterion_results", []):
            maximum = float(criterion["max_score"])
            score = float(criterion["score"])
            rows.append(
                {
                    "Supplier": supplier["supplier_name"],
                    "Criterion ID": criterion["criterion_id"],
                    "Criterion": criterion_names.get(
                        criterion["criterion_id"], criterion["criterion_id"]
                    ),
                    "Score": score,
                    "Maximum": maximum,
                    "Score (%)": 100.0 * score / maximum if maximum else 0.0,
                    "Weight (%)": float(criterion["weight"]),
                    "Weighted points": float(criterion["weighted_contribution"]),
                    "Peer benchmark": float(criterion["benchmark"] or 0),
                    "Gap": float(criterion["gap"] or 0),
                    "Relative performance (%)": float(criterion["relative_pct"] or 0),
                    "Evidence page": criterion.get("evidence_page"),
                }
            )
    return rows


def build_score_contribution_rows(
    criterion_results: list[dict[str, Any]],
    criteria: list[dict[str, Any]],
    final_score: float,
) -> list[dict[str, Any]]:
    """Return weighted criterion points plus remaining possible template points."""
    criterion_names = {
        row["criterion_id"]: row["name"]
        for row in criteria
    }
    rows = [
        {
            "Criterion": criterion_names.get(
                result["criterion_id"], result["criterion_id"]
            ),
            "Weighted points": float(result["weighted_contribution"]),
        }
        for result in criterion_results
    ]
    remaining_points = max(0.0, 100.0 - final_score)
    if remaining_points:
        rows.append(
            {
                "Criterion": "Points below template maximum",
                "Weighted points": remaining_points,
            }
        )
    return rows


def build_detailed_result_rows(
    suppliers: list[dict[str, Any]], criteria: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Create auditable per-supplier, per-criterion result rows."""
    criterion_names = {
        row["criterion_id"]: row["name"]
        for row in criteria
    }
    detailed = []
    for supplier in suppliers:
        gate_statuses = [gate["status"] for gate in supplier.get("gates", [])]
        gate_summary = (
            "FAIL"
            if "FAIL" in gate_statuses
            else "PENDING_VERIFICATION"
            if "PENDING_VERIFICATION" in gate_statuses
            else "PASS"
        )
        for result in supplier.get("criterion_results", []):
            detailed.append(
                {
                    "Rank": supplier.get("technical_rank"),
                    "Supplier": supplier["supplier_name"],
                    "Final score / 100": float(supplier["absolute_score"]),
                    "PPI (%)": float(supplier["ppi"]),
                    "Eligibility": supplier["eligibility_status"],
                    "Shortlist status": supplier["shortlist_status"],
                    "Gate status": gate_summary,
                    "Criterion ID": result["criterion_id"],
                    "Criterion": criterion_names.get(
                        result["criterion_id"], result["criterion_id"]
                    ),
                    "Score": float(result["score"]),
                    "Maximum score": float(result["max_score"]),
                    "Weight (%)": float(result["weight"]),
                    "Weighted contribution": float(
                        result["weighted_contribution"]
                    ),
                    "Peer benchmark": (
                        float(result["benchmark"])
                        if result["benchmark"] is not None
                        else None
                    ),
                    "Gap to benchmark": (
                        float(result["gap"]) if result["gap"] is not None else None
                    ),
                    "Relative performance (%)": (
                        float(result["relative_pct"])
                        if result["relative_pct"] is not None
                        else None
                    ),
                    "Rationale": result["justification"],
                    "Evidence excerpt": result["evidence"],
                    "Evidence page": result["evidence_page"],
                    "Missing evidence": "; ".join(result["missing_evidence"]),
                    "Confidence": result["confidence"],
                    "Warnings": "; ".join(supplier.get("warnings", [])),
                }
            )
    return detailed
