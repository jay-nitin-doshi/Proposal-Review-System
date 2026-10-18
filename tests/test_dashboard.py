import json
from pathlib import Path
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest

from src.dashboard import (
    build_criterion_rows,
    build_detailed_result_rows,
    build_leaderboard_rows,
    build_output_matrix_rows,
    build_score_contribution_rows,
)
from src.db import (
    DEFAULT_GATES,
    DEFAULT_CRITERIA,
    connect,
    get_criteria,
    initialize_database,
    save_run,
)
from src.models import validate_scorecard
from src.scoring import score_and_rank


def make_scored_supplier(connection):
    criteria = get_criteria(connection, active_only=True)
    scorecard, warnings = validate_scorecard(
        {
            "criteria": [
                {
                    "criterion_id": criterion["criterion_id"],
                    "score": 7,
                    "max_score": criterion["max_score"],
                    "justification": "Reviewer found supporting information.",
                    "evidence": f"Page 1 excerpt for {criterion['criterion_id']}.",
                    "evidence_page": 1,
                    "confidence": "reviewer-entered",
                    "missing_evidence": [],
                }
                for criterion in criteria
            ],
            "risks": [],
            "overall_summary": "Complete example assessment.",
        },
        criteria,
    )
    result = {
        "supplier_name": "Dashboard Supplier",
        "submission_date": "2026-10-01",
        "experience_rating": 4.2,
        "evaluation_status": "MANUAL_REVIEW_COMPLETE",
        "eligibility_status": "PENDING_VERIFICATION",
        "shortlist_status": "PENDING_MANDATORY_REVIEW",
        "warnings": warnings,
        "scorecard": scorecard,
        "result_json": {
            **scorecard,
            "commercial_review": {
                "status": "NOT_REVIEWED",
                "rationale": "",
            },
        },
        "raw_model_output": json.dumps(scorecard),
        "gates": [
            {
                "gate_id": gate_id,
                "gate_name": gate_name,
                "status": "PENDING_VERIFICATION",
                "rationale": "Awaiting verification.",
                "reviewer": "",
            }
            for gate_id, gate_name in DEFAULT_GATES
        ],
    }
    for row in result["scorecard"]["criteria"]:
        row["weight"] = next(
            criterion["weight"]
            for criterion in criteria
            if criterion["criterion_id"] == row["criterion_id"]
        )
    score_and_rank([result], criteria)
    result["result_json"]["industry_index"] = result["industry_index"]
    return result, criteria


def test_dashboard_rows_expose_final_scores_and_normalized_criterion_values(tmp_path):
    database_path = tmp_path / "dashboard.db"
    initialize_database(database_path)
    connection = connect(database_path)
    try:
        supplier, criteria = make_scored_supplier(connection)
        leaderboard = build_leaderboard_rows([supplier])
        criterion_rows = build_criterion_rows(
            [
                {
                    **supplier,
                    "criterion_results": [
                        {
                            "criterion_id": row["criterion_id"],
                            "score": row["score"],
                            "max_score": row["max_score"],
                            "weight": row["weight"],
                            "weighted_contribution": supplier["criterion_metrics"][
                                row["criterion_id"]
                            ]["weighted_contribution"],
                            "benchmark": supplier["criterion_metrics"][
                                row["criterion_id"]
                            ]["benchmark"],
                            "gap": supplier["criterion_metrics"][row["criterion_id"]]["gap"],
                            "relative_pct": supplier["criterion_metrics"][
                                row["criterion_id"]
                            ]["relative_pct"],
                            "evidence_page": row["evidence_page"],
                        }
                        for row in supplier["scorecard"]["criteria"]
                    ],
                }
            ],
            criteria,
        )
    finally:
        connection.close()

    assert leaderboard[0]["Final score"] == pytest.approx(70)
    assert leaderboard[0]["Eligibility"] == "PENDING_VERIFICATION"
    assert len(criterion_rows) == len(DEFAULT_CRITERIA)
    assert criterion_rows[0]["Score (%)"] == pytest.approx(70)
    assert criterion_rows[0]["Weighted points"] == pytest.approx(14)
    assert criterion_rows[0]["Criterion"] == "Manufacturing capability & process control"
    matrix = build_output_matrix_rows(
        [
            {
                **supplier,
                "criterion_results": [
                    {
                        "criterion_id": row["criterion_id"],
                        "score": row["score"],
                        "max_score": row["max_score"],
                    }
                    for row in supplier["scorecard"]["criteria"]
                ],
            }
        ],
        criteria,
    )
    assert matrix[0]["Rank"] == 1
    assert matrix[0]["Final score / 100"] == pytest.approx(70)
    assert matrix[0][
        "Manufacturing capability & process control (score / max)"
    ] == "7 / 10"
    assert matrix[0]["Industry index (cohort proxy)"] == pytest.approx(100)

    pie_rows = build_score_contribution_rows(
        [
            {
                "criterion_id": row["criterion_id"],
                "weighted_contribution": supplier["criterion_metrics"][
                    row["criterion_id"]
                ]["weighted_contribution"],
            }
            for row in supplier["scorecard"]["criteria"]
        ],
        criteria,
        leaderboard[0]["Final score"],
    )
    assert sum(row["Weighted points"] for row in pie_rows) == pytest.approx(100)
    assert sum(
        row["Weighted points"]
        for row in pie_rows
        if row["Criterion"] != "Points below template maximum"
    ) == pytest.approx(leaderboard[0]["Final score"])


def test_detailed_result_rows_trace_score_to_evidence_and_gate_status():
    supplier = {
        "supplier_name": "Example Supplier",
        "technical_rank": 1,
        "absolute_score": 82.5,
        "ppi": 96.2,
        "eligibility_status": "PENDING_VERIFICATION",
        "shortlist_status": "PENDING_MANDATORY_REVIEW",
        "gates": [{"status": "PENDING_VERIFICATION"}],
        "warnings": ["MODEL_EVIDENCE_REQUIRES_REVIEW"],
        "criterion_results": [
            {
                "criterion_id": "quality_system",
                "score": 8,
                "max_score": 10,
                "weight": 20,
                "weighted_contribution": 16,
                "benchmark": 9,
                "gap": -1,
                "relative_pct": 88.89,
                "justification": "CAPA and batch release are described.",
                "evidence": "Page 4: controlled CAPA procedure.",
                "evidence_page": 4,
                "missing_evidence": ["Independent audit closeout"],
                "confidence": "medium",
            }
        ],
    }

    rows = build_detailed_result_rows(
        [supplier],
        [{"criterion_id": "quality_system", "name": "GMP quality system"}],
    )

    assert len(rows) == 1
    assert rows[0]["Final score / 100"] == pytest.approx(82.5)
    assert rows[0]["Gate status"] == "PENDING_VERIFICATION"
    assert rows[0]["Weighted contribution"] == pytest.approx(16)
    assert rows[0]["Rationale"] == "CAPA and batch release are described."
    assert rows[0]["Evidence excerpt"] == "Page 4: controlled CAPA procedure."
    assert rows[0]["Evidence page"] == 4
    assert rows[0]["Missing evidence"] == "Independent audit closeout"


def test_streamlit_renders_dashboard_with_persisted_proposals(tmp_path, monkeypatch):
    database_path = tmp_path / "streamlit-dashboard.db"
    initialize_database(database_path)
    connection = connect(database_path)
    try:
        supplier, criteria = make_scored_supplier(connection)
        supplier["result_json"] = {
            **supplier["scorecard"],
            "commercial_review": {"status": "NOT_REVIEWED", "rationale": ""},
        }
        save_run(
            connection,
            {
                "rfp_run_id": "dashboard-ui-test",
                "created_at": "2026-10-18T00:00:00+00:00",
                "status": "completed",
                "criteria_snapshot": criteria,
                "model_provider": "Manual reviewer",
                "minimum_score": 70,
                "notes": "",
            },
            [supplier],
            [],
        )
    finally:
        connection.close()

    monkeypatch.setenv("RFP_DB_PATH", str(database_path))
    with patch(
        "src.providers.list_available_models", return_value=["gpt-4o-mini"]
    ):
        app = AppTest.from_file(
            str(Path(__file__).resolve().parents[1] / "app.py"),
            default_timeout=30,
        ).run()
        assert not app.exception
        assert [tab.label for tab in app.tabs] == [
            "New evaluation",
            "Output matrix & leader dashboard",
            "Detailed results",
            "Criteria & settings",
        ]
        assert len(app.get("plotly_chart")) >= 7
        assert any(metric.label == "Top final score" for metric in app.metric)
        assert any(
            heading.value == "Start a new evaluation"
            for heading in app.subheader
        )
        assert app.file_uploader[0].label == "Choose proposal PDFs"
        assert any(
            heading.value == "Evaluation output matrix"
            for heading in app.subheader
        )

        app.radio[0].set_value("AI-assisted evidence extraction").run()
        ai_fields = {field.label: field.value for field in app.text_input}
        assert ai_fields["OpenAI API key"] == ""
        assert ai_fields["LangSmith API key"] == ""
        assert not any(
            selectbox.label == "2. Select an available model"
            for selectbox in app.selectbox
        )
        assert app.file_uploader[0].disabled is True
        next(
            field for field in app.text_input if field.label == "OpenAI API key"
        ).set_value("test-key").run()
        app.button("validate_provider_key").click().run()
        assert any(
            selectbox.label == "2. Select an available model"
            for selectbox in app.selectbox
        )
        assert app.file_uploader[0].disabled is False
        next(
            field for field in app.text_input if field.label == "OpenAI API key"
        ).set_value("changed-key").run()
        assert app.file_uploader[0].disabled is True
