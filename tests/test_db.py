import json

from src.db import (
    DEFAULT_GATES,
    connect,
    get_criteria,
    initialize_database,
    load_run,
    save_run,
    update_gate,
)
from src.models import validate_scorecard
from src.scoring import score_and_rank


def test_run_persists_criteria_evidence_and_gate_decisions(tmp_path):
    database_path = tmp_path / "tender.db"
    initialize_database(database_path)
    connection = connect(database_path)
    try:
        criteria = get_criteria(connection, active_only=True)
        scorecard, warnings = validate_scorecard(
            {
                "criteria": [
                    {
                        "criterion_id": row["criterion_id"],
                        "score": 8,
                        "max_score": row["max_score"],
                        "justification": "Reviewed evidence.",
                        "evidence": "Proposal excerpt.",
                        "evidence_page": 1,
                        "missing_evidence": [],
                    }
                    for row in criteria
                ],
                "risks": ["Confirm site audit."],
                "overall_summary": "Strong documentation; verification pending.",
            },
            criteria,
        )
        supplier = {
            "supplier_name": "Example Supplier",
            "submission_date": "2026-10-01",
            "experience_rating": 4.0,
            "evaluation_status": "AI_REVIEW_COMPLETE",
            "eligibility_status": "PENDING_VERIFICATION",
            "shortlist_status": "PENDING_MANDATORY_REVIEW",
            "warnings": warnings,
            "scorecard": scorecard,
            "result_json": scorecard,
            "raw_model_output": json.dumps(scorecard),
            "gates": [
                {
                    "gate_id": gate_id,
                    "gate_name": gate_name,
                    "status": "PENDING_VERIFICATION",
                    "rationale": "Awaiting verification",
                    "reviewer": "",
                }
                for gate_id, gate_name in DEFAULT_GATES
            ],
        }
        supplier["scorecard"]["criteria"] = [
            {
                **row,
                "weight": next(
                    criterion["weight"]
                    for criterion in criteria
                    if criterion["criterion_id"] == row["criterion_id"]
                ),
            }
            for row in supplier["scorecard"]["criteria"]
        ]
        ranked = score_and_rank([supplier], criteria)
        supplier = ranked[0]
        supplier["evaluation_status"] = "AI_REVIEW_COMPLETE"
        supplier["eligibility_status"] = "PENDING_VERIFICATION"
        supplier["shortlist_status"] = "PENDING_MANDATORY_REVIEW"
        supplier["gates"] = [
            {
                "gate_id": gate_id,
                "gate_name": gate_name,
                "status": "PENDING_VERIFICATION",
                "rationale": "Awaiting verification",
                "reviewer": "",
            }
            for gate_id, gate_name in DEFAULT_GATES
        ]
        save_run(
            connection,
            {
                "rfp_run_id": "run-test",
                "created_at": "2026-10-18T00:00:00+00:00",
                "status": "completed",
                "criteria_snapshot": criteria,
                "model_provider": "Manual test",
                "minimum_score": 70,
                "notes": "Test notes",
            },
            [supplier],
            [
                {
                    "supplier_name": "Example Supplier",
                    "original_filename": "proposal.pdf",
                    "sha256": "abc123",
                    "page_count": 1,
                    "extraction_status": "text_extracted",
                    "warnings": [],
                }
            ],
        )
        loaded = load_run(connection, "run-test")
        assert loaded["criteria_snapshot"][0]["criterion_id"] == "manufacturing_capability"
        assert loaded["suppliers"][0]["criterion_results"][0]["evidence"] == "Proposal excerpt."
        assert loaded["suppliers"][0]["gates"][0]["status"] == "PENDING_VERIFICATION"
        result_id = loaded["suppliers"][0]["result_id"]

        update_gate(
            connection,
            result_id,
            DEFAULT_GATES[0][0],
            "FAIL",
            "Verification failed.",
            "reviewer-1",
        )
        after_failure = load_run(connection, "run-test")["suppliers"][0]
        assert after_failure["eligibility_status"] == "NOT_ELIGIBLE"
        assert after_failure["shortlist_status"] == "EXCLUDED_BY_MANDATORY_GATE"
        assert after_failure["gate_history"][0]["previous_status"] == "PENDING_VERIFICATION"
        assert after_failure["gate_history"][0]["new_status"] == "FAIL"

        for gate_id, _ in DEFAULT_GATES:
            update_gate(
                connection,
                result_id,
                gate_id,
                "PASS",
                "Verified by reviewer.",
                "reviewer-1",
            )
        after_review = load_run(connection, "run-test")["suppliers"][0]
        assert after_review["eligibility_status"] == "ELIGIBLE_FOR_REVIEW"
        assert after_review["shortlist_status"] == "SHORTLIST_CANDIDATE"
    finally:
        connection.close()
