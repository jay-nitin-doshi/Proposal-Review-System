"""Streamlit interface for evidence-grounded tender proposal evaluation."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st

from src.db import (
    DEFAULT_GATES,
    connect,
    get_criteria,
    initialize_database,
    list_runs,
    load_run,
    save_criteria,
    save_run,
    update_gate,
)
from src.dashboard import (
    build_criterion_rows,
    build_detailed_result_rows,
    build_leaderboard_rows,
    build_output_matrix_rows,
    build_score_contribution_rows,
)
from src.evaluator import EvaluatorError, evaluate_proposal
from src.models import ScorecardValidationError, validate_scorecard
from src.pdf_reader import extract_pdf
from src.providers import PROVIDERS, ProviderValidationError, list_available_models
from src.scoring import assess_shortlist, score_and_rank, validate_criteria


ROOT = Path(__file__).resolve().parent
DATABASE_PATH = Path(os.getenv("RFP_DB_PATH", ROOT / "data" / "rfp_evaluation.db"))
MAX_UPLOADS = 20

st.set_page_config(
    page_title="Paracetamol Tender Review",
    page_icon="📋",
    layout="wide",
)


def _safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", Path(value).name)


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, indent=2, ensure_ascii=False, default=str).encode("utf-8")


def _provider_key_fingerprint(provider: str, api_key: str) -> str:
    return hashlib.sha256(f"{provider}\0{api_key}".encode("utf-8")).hexdigest()


def _clear_provider_validation() -> None:
    st.session_state.pop("validated_provider_fingerprint", None)
    st.session_state.pop("validated_provider_models", None)
    st.session_state.pop("selected_provider_model", None)


@st.cache_resource
def _initialize_database(database_path: str) -> bool:
    initialize_database(database_path)
    return True


_initialize_database(str(DATABASE_PATH))
connection = connect(DATABASE_PATH)

with st.sidebar:
    st.header("1 · AI provider")
    selected_provider = st.selectbox(
        "Provider",
        options=PROVIDERS,
        key="ai_provider",
        on_change=_clear_provider_validation,
    )
    provider_api_key = st.text_input(
        f"{selected_provider} API key",
        type="password",
        key="provider_api_key",
        on_change=_clear_provider_validation,
        help="Used only for this session; not read from .env or saved to the database.",
    )
    if st.button("Validate key and load models", key="validate_provider_key"):
        try:
            with st.spinner(f"Validating {selected_provider} API key..."):
                available_models = list_available_models(
                    selected_provider, provider_api_key
                )
        except ProviderValidationError as exc:
            _clear_provider_validation()
            st.error(str(exc))
        else:
            st.session_state["validated_provider_fingerprint"] = (
                _provider_key_fingerprint(selected_provider, provider_api_key)
            )
            st.session_state["validated_provider_models"] = available_models
            st.success(
                f"API key validated. {len(available_models)} chat model(s) available."
            )

    current_fingerprint = _provider_key_fingerprint(
        selected_provider, provider_api_key
    )
    provider_validated = (
        bool(provider_api_key.strip())
        and st.session_state.get("validated_provider_fingerprint")
        == current_fingerprint
    )
    provider_models = (
        st.session_state.get("validated_provider_models", [])
        if provider_validated
        else []
    )
    selected_model = ""
    if provider_models:
        selected_model = st.selectbox(
            "2. Select an available model",
            options=provider_models,
            key="selected_provider_model",
        )
    else:
        st.info("Validate your provider key to load available models.")

    st.divider()
    st.header("Optional · LangSmith traces")
    langsmith_key = st.text_input(
        "LangSmith API key",
        type="password",
        key="langsmith_api_key",
        help="Leave blank to disable tracing. Traces may contain proposal text and evidence.",
    )
    langsmith_project = st.text_input(
        "LangSmith project",
        value="paracetamol-tender-review",
        key="langsmith_project",
    )
    st.caption(
        "AI evaluation sends proposal text to the selected model provider. "
        "Use only providers approved for your tender data."
    )
    ai_data_approved = st.checkbox(
        "I approve sending proposal data to the selected provider"
        + (" and LangSmith" if langsmith_key.strip() else ""),
        key="ai_data_approved",
    )

    ai_provider_ready = provider_validated and bool(selected_model)

st.markdown(
    """
    <style>
    section.main > div.block-container {
        padding-top: 1.25rem;
        padding-bottom: 2rem;
    }
    [data-testid="stHeading"] h1 {
        font-size: 2rem !important;
        line-height: 1.15 !important;
        margin-bottom: .25rem !important;
    }
    .stApp {
        background:
            radial-gradient(ellipse at 92% 2%, rgba(14, 165, 233, .10), transparent 28%),
            radial-gradient(ellipse at 4% 16%, rgba(139, 92, 246, .08), transparent 27%);
    }
    [data-testid="stHeader"] { background: rgba(0, 0, 0, 0); }
    [data-testid="stTabs"] button[aria-selected="true"] {
        color: #2563eb;
        border-bottom-color: #2563eb;
        font-weight: 700;
    }
    [data-testid="stFileUploaderDropzone"] {
        background: linear-gradient(135deg, rgba(59, 130, 246, .08), rgba(16, 185, 129, .08));
        border: 1.5px dashed rgba(37, 99, 235, .48);
        border-radius: 16px;
    }
    [data-testid="stMetric"] {
        border-radius: 14px;
        border: 1px solid rgba(100, 116, 139, .2);
        box-shadow: 0 5px 18px rgba(30, 64, 175, .06);
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    '<p style="font-size: 2rem; font-weight: 700; margin: 0 0 .75rem;">'
    "Proposal Review System</p>",
    unsafe_allow_html=True,
)

new_tab, results_tab, detailed_results_tab, criteria_tab = st.tabs(
    [
        "New evaluation",
        "Output matrix & leader dashboard",
        "Detailed results",
        "Criteria & settings",
    ]
)

with new_tab:
    st.subheader("Start a new evaluation")
    criteria = get_criteria(connection, active_only=True)
    try:
        validate_criteria(criteria)
    except ValueError as exc:
        st.error(f"Evaluation is disabled until criteria are corrected: {exc}")
        criteria_ready = False
    else:
        criteria_ready = True

    upload_mode = st.radio(
        "Scoring approach",
        ["Manual reviewer scorecard", "AI-assisted evidence extraction"],
        help=(
            "Manual mode keeps proposal text in this application. AI mode sends extracted "
            "text to the selected provider."
        ),
        horizontal=True,
        key="scoring_mode",
    )
    upload_enabled = (
        upload_mode == "Manual reviewer scorecard" or ai_provider_ready
    )
    if upload_mode == "AI-assisted evidence extraction" and not ai_provider_ready:
        st.info(
            "Complete provider setup in the left sidebar: validate the API key, "
            "then select an available model to enable proposal uploads."
        )
    upload_col, rubric_col = st.columns([1.25, 1], gap="large")
    with upload_col:
        with st.container(border=True):
            st.markdown("#### Upload supplier proposals")
            st.caption(
                "PDF only · up to 20 files · 20 MiB and 200 pages per file."
            )
            uploads = st.file_uploader(
                "Choose proposal PDFs",
                type=["pdf"],
                accept_multiple_files=True,
                disabled=not upload_enabled,
                key="proposal_uploads",
                help="Upload one PDF per supplier. Duplicate documents are rejected.",
            )
            if uploads:
                st.success(f"{len(uploads)} proposal(s) ready for supplier details.")
            elif upload_enabled:
                st.caption("Select or drag-and-drop files to begin.")
            else:
                st.caption("Complete provider validation in the sidebar to upload in AI mode.")
    with rubric_col:
        with st.container(border=True):
            st.markdown("#### Tender template at a glance")
            if criteria:
                weight_chart = px.pie(
                    pd.DataFrame(
                        [
                            {
                                "Criterion": row["name"],
                                "Weight (%)": float(row["weight"]),
                            }
                            for row in criteria
                        ]
                    ),
                    names="Criterion",
                    values="Weight (%)",
                    hole=0.58,
                    color_discrete_sequence=px.colors.qualitative.Bold,
                )
                weight_chart.update_traces(
                    textposition="inside",
                    texttemplate="%{percent}",
                    hovertemplate="%{label}<br>Weight: %{value:g}%<extra></extra>",
                    marker=dict(line=dict(color="rgba(255,255,255,.7)", width=2)),
                )
                weight_chart.add_annotation(
                    text=f"{len(criteria)}<br><sup>criteria</sup>",
                    x=0.5,
                    y=0.5,
                    showarrow=False,
                    font_size=18,
                )
                weight_chart.update_layout(
                    height=330,
                    margin=dict(l=5, r=5, t=10, b=5),
                    legend=dict(orientation="h", y=-0.05, x=0.5, xanchor="center"),
                    paper_bgcolor="rgba(0,0,0,0)",
                )
                st.plotly_chart(
                    weight_chart,
                    width="stretch",
                    key="new_evaluation_rubric_weights",
                )
                st.caption(
                    "The chart reflects active criterion weights; the weighted final score is out of 100."
                )
            else:
                st.info("Add active criteria to display the template weight chart.")
    st.markdown(
        """
        <div style="
            padding: .9rem 1.2rem; border-radius: 16px; margin: .3rem 0 .8rem;
            background: linear-gradient(115deg, #1d4ed8 0%, #4f46e5 54%, #7c3aed 100%);
            color: white; box-shadow: 0 10px 24px rgba(79, 70, 229, .16);">
            <div style="font-size: .78rem; font-weight: 700; letter-spacing: .08em;
                        text-transform: uppercase; opacity: .85;">
                Tender workspace · evidence-led supplier review
            </div>
            <div style="font-size: .95rem; margin-top: .25rem; opacity: .9;">
                Capture supplier context and compare evidence-backed scores.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.container(border=True):
        st.markdown("#### Your evaluation in three steps")
        step_one, step_two, step_three = st.columns(3)
        with step_one:
            st.markdown("**:blue[1 · Add proposals]**")
            st.caption("Upload supplier PDFs and enter each supplier's basic profile.")
        with step_two:
            st.markdown("**:violet[2 · Review evidence]**")
            st.caption("Extract scores against the active tender template.")
        with step_three:
            st.markdown("**:green[3 · Compare results]**")
            st.caption("Inspect weighted scores, PPI, evidence, and verification gates.")
    if uploads and len(uploads) > MAX_UPLOADS:
        st.error(f"Upload no more than {MAX_UPLOADS} proposal PDFs per run.")
        uploads = []

    if uploads:
        st.caption(f"{len(uploads)} proposal(s) selected.")
        minimum_score = st.number_input(
            "Minimum absolute score for shortlist candidacy",
            min_value=0.0,
            max_value=100.0,
            value=70.0,
            step=1.0,
        )
        with st.form("proposal_metadata_and_scorecards"):
            st.markdown("#### Supplier details")
            proposal_rows: list[dict[str, Any]] = []
            for index, uploaded in enumerate(uploads):
                default_name = Path(uploaded.name).stem.replace("_", " ").title()
                with st.expander(_safe_filename(uploaded.name), expanded=index == 0):
                    name = st.text_input(
                        "Supplier legal name",
                        value=default_name,
                        key=f"supplier_name_{index}",
                    )
                    submission_date = st.date_input(
                        "Submission date",
                        value=date.today(),
                        key=f"submission_date_{index}",
                    )
                    experience = st.slider(
                        "Historical experience rating (reviewer-entered, 0–5)",
                        min_value=0.0,
                        max_value=5.0,
                        value=3.0,
                        step=0.1,
                        key=f"experience_{index}",
                    )
                    history_performance = st.slider(
                        "Historical supplier performance score (reference only, 0–100)",
                        min_value=0.0,
                        max_value=100.0,
                        value=70.0,
                        step=1.0,
                        key=f"history_performance_{index}",
                        help="Recorded for reviewer context; it does not change the tender score or rank.",
                    )
                    experience_years = st.number_input(
                        "Years manufacturing this product / category",
                        min_value=0,
                        max_value=100,
                        value=0,
                        step=1,
                        key=f"manufacturing_years_{index}",
                    )
                    annual_capacity = st.number_input(
                        "Proposed annual capacity (metric tonnes)",
                        min_value=0.0,
                        max_value=1_000_000.0,
                        value=0.0,
                        step=100.0,
                        key=f"annual_capacity_{index}",
                    )
                    manufacturing_site = st.text_input(
                        "Manufacturing site / country",
                        key=f"manufacturing_site_{index}",
                    )
                    product_scope = st.text_input(
                        "Product strength, dosage form, and proposed scope",
                        value="Paracetamol",
                        key=f"product_scope_{index}",
                    )
                    commercial_status = st.selectbox(
                        "Commercial bid comparability",
                        ["NOT_REVIEWED", "COMPARABLE", "NOT_COMPARABLE"],
                        help=(
                            "Mark comparable only after confirming product scope, volume, "
                            "packaging, testing/release, delivery, currency, tax, and contract period."
                        ),
                        key=f"commercial_status_{index}",
                    )
                    commercial_rationale = st.text_input(
                        "Commercial normalization basis / reason",
                        key=f"commercial_rationale_{index}",
                    )
                    manual_scores: dict[str, dict[str, Any]] = {}
                    if upload_mode == "Manual reviewer scorecard":
                        st.markdown("##### Criterion scores")
                        for criterion in criteria:
                            criterion_id = criterion["criterion_id"]
                            st.markdown(
                                f"**{criterion['name']}** — {criterion['weight']:g}%"
                            )
                            score = st.slider(
                                f"Score / {criterion['max_score']:g}",
                                min_value=0.0,
                                max_value=float(criterion["max_score"]),
                                value=0.0,
                                step=0.5,
                                key=f"manual_score_{index}_{criterion_id}",
                            )
                            justification = st.text_area(
                                "Reviewer rationale",
                                key=f"manual_justification_{index}_{criterion_id}",
                                height=72,
                            )
                            evidence = st.text_area(
                                "Evidence excerpt / page reference",
                                key=f"manual_evidence_{index}_{criterion_id}",
                                height=72,
                            )
                            evidence_page = st.number_input(
                                "Proposal page (leave 0 if unknown)",
                                min_value=0,
                                max_value=200,
                                value=0,
                                step=1,
                                key=f"manual_page_{index}_{criterion_id}",
                            )
                            manual_scores[criterion_id] = {
                                "criterion_id": criterion_id,
                                "score": score,
                                "max_score": criterion["max_score"],
                                "justification": justification,
                                "evidence": evidence,
                                "evidence_page": evidence_page or None,
                                "confidence": "reviewer-entered",
                                "missing_evidence": [],
                            }
                    proposal_rows.append(
                        {
                            "upload": uploaded,
                            "supplier_name": name.strip(),
                            "submission_date": submission_date.isoformat(),
                            "experience_rating": experience,
                            "supplier_profile": {
                                "historical_performance_score": history_performance,
                                "manufacturing_experience_years": experience_years,
                                "proposed_annual_capacity_mt": annual_capacity,
                                "manufacturing_site": manufacturing_site.strip(),
                                "product_scope": product_scope.strip(),
                            },
                            "commercial_status": commercial_status,
                            "commercial_rationale": commercial_rationale.strip(),
                            "manual_scores": manual_scores,
                        }
                    )

            notes = st.text_area(
                "Run notes (scope, assumptions, contract period, etc.)", height=75
            )
            submit = st.form_submit_button(
                "Evaluate proposals and save audit run",
                type="primary",
                disabled=not criteria_ready,
            )

        if submit:
            names = [row["supplier_name"].casefold() for row in proposal_rows]
            if any(not name for name in names):
                st.error("Every supplier must have a non-empty legal name.")
            elif len(names) != len(set(names)):
                st.error("Duplicate supplier names detected; each supplier must be unique.")
            elif upload_mode == "AI-assisted evidence extraction" and not ai_provider_ready:
                st.error("Validate the provider key and select a model in the sidebar.")
            elif upload_mode == "AI-assisted evidence extraction" and (
                langsmith_key.strip() and not langsmith_project.strip()
            ):
                st.error("Enter a LangSmith project or leave tracing disabled.")
            elif upload_mode == "AI-assisted evidence extraction" and not ai_data_approved:
                st.error("Confirm provider data approval before sending proposal text.")
            else:
                extracted_rows: list[dict[str, Any]] = []
                seen_hashes: set[str] = set()
                duplicate_file = False
                for row in proposal_rows:
                    content = row["upload"].getvalue()
                    digest = hashlib.sha256(content).hexdigest()
                    if digest in seen_hashes:
                        st.error("Duplicate PDF content detected; remove duplicate uploads.")
                        duplicate_file = True
                        break
                    seen_hashes.add(digest)
                    try:
                        extracted = extract_pdf(content)
                        error = (
                            "Scanned/empty PDF requires OCR or manual review."
                            if extracted.extraction_status == "scanned_or_empty"
                            else ""
                        )
                    except ValueError as exc:
                        extracted = None
                        error = str(exc)
                    extracted_rows.append(
                        {
                            **row,
                            "sha256": digest,
                            "extracted": extracted,
                            "extraction_error": error,
                        }
                    )

                if not duplicate_file:
                    run_id = str(uuid.uuid4())
                    result_rows: list[dict[str, Any]] = []
                    document_rows: list[dict[str, Any]] = []
                    model_provider = (
                        f"{selected_provider}: {selected_model}; LangSmith tracing "
                        f"{'enabled' if langsmith_key.strip() else 'disabled'}"
                        if upload_mode == "AI-assisted evidence extraction"
                        else "Manual reviewer"
                    )
                    progress = st.progress(0.0, text="Preparing supplier evaluations")

                    for index, item in enumerate(extracted_rows):
                        extracted = item["extracted"]
                        document_rows.append(
                            {
                                "supplier_name": item["supplier_name"],
                                "original_filename": _safe_filename(item["upload"].name),
                                "sha256": item["sha256"],
                                "page_count": extracted.page_count if extracted else None,
                                "extraction_status": (
                                    extracted.extraction_status if extracted else "extraction_error"
                                ),
                                "warnings": extracted.warnings if extracted else [],
                            }
                        )
                        supplier_result: dict[str, Any] = {
                            "supplier_name": item["supplier_name"],
                            "submission_date": item["submission_date"],
                            "experience_rating": item["experience_rating"],
                            "supplier_profile": item["supplier_profile"],
                            "evaluation_status": "EVALUATION_ERROR",
                            "eligibility_status": "NOT_RANKED",
                            "shortlist_status": "NOT_RANKED",
                            "warnings": [],
                            "commercial_status": item["commercial_status"],
                            "commercial_rationale": item["commercial_rationale"],
                            "gates": [
                                {
                                    "gate_id": gate_id,
                                    "gate_name": gate_name,
                                    "status": "PENDING_VERIFICATION",
                                    "rationale": "Awaiting authorized human verification.",
                                    "reviewer": "",
                                }
                                for gate_id, gate_name in DEFAULT_GATES
                            ],
                            "failure_reason": item["extraction_error"],
                            "result_json": {
                                "supplier_profile": item["supplier_profile"],
                                "commercial_review": {
                                    "status": item["commercial_status"],
                                    "rationale": item["commercial_rationale"],
                                }
                            },
                        }
                        if extracted and extracted.warnings:
                            supplier_result["warnings"].extend(extracted.warnings)

                        raw_output = None
                        can_evaluate = extracted is not None and (
                            not item["extraction_error"]
                            or upload_mode == "Manual reviewer scorecard"
                        )
                        if can_evaluate and extracted is not None:
                            try:
                                if upload_mode == "Manual reviewer scorecard":
                                    model_payload = {
                                        "criteria": list(item["manual_scores"].values()),
                                        "risks": [],
                                        "overall_summary": "Manually assessed by the reviewer.",
                                    }
                                    scorecard, warnings = validate_scorecard(
                                        model_payload, criteria
                                    )
                                else:
                                    model_payload, raw_output = evaluate_proposal(
                                        item["supplier_name"],
                                        extracted.text,
                                        criteria,
                                        provider=selected_provider,
                                        api_key=provider_api_key,
                                        model=selected_model,
                                        langsmith_api_key=langsmith_key,
                                        langsmith_project=langsmith_project,
                                        run_id=run_id,
                                        page_count=extracted.page_count,
                                    )
                                    scorecard = model_payload
                                    warnings = scorecard.pop("validation_warnings", [])
                                for score in scorecard["criteria"]:
                                    if not score["evidence"]:
                                        supplier_result["warnings"].append(
                                            f"NO_EVIDENCE_TEXT:{score['criterion_id']}"
                                        )
                                supplier_result["warnings"].extend(warnings)
                                supplier_result["scorecard"] = scorecard
                                supplier_result["raw_model_output"] = (
                                    raw_output
                                    if raw_output is not None
                                    else json.dumps(model_payload, ensure_ascii=False)
                                )
                                supplier_result["result_json"] = {
                                    **scorecard,
                                    "supplier_profile": item["supplier_profile"],
                                    "commercial_review": {
                                        "status": item["commercial_status"],
                                        "rationale": item["commercial_rationale"],
                                    },
                                }
                                supplier_result["evaluation_status"] = (
                                    "MANUAL_REVIEW_COMPLETE"
                                    if upload_mode == "Manual reviewer scorecard"
                                    else "AI_REVIEW_COMPLETE"
                                )
                                supplier_result["failure_reason"] = ""
                            except (EvaluatorError, ScorecardValidationError) as exc:
                                supplier_result["failure_reason"] = str(exc)
                                supplier_result["raw_model_output"] = raw_output
                        result_rows.append(supplier_result)
                        progress.progress(
                            (index + 1) / len(extracted_rows),
                            text=f"Processed {index + 1} of {len(extracted_rows)} proposals",
                        )

                    ranked = [
                        row for row in result_rows if row["evaluation_status"] != "EVALUATION_ERROR"
                    ]
                    try:
                        if ranked:
                            score_and_rank(ranked, criteria)
                            for supplier in ranked:
                                supplier["result_json"]["industry_index"] = supplier[
                                    "industry_index"
                                ]
                                for score in supplier["scorecard"]["criteria"]:
                                    score["weight"] = next(
                                        criterion["weight"]
                                        for criterion in criteria
                                        if criterion["criterion_id"] == score["criterion_id"]
                                    )
                                eligibility, shortlist = assess_shortlist(
                                    supplier["gates"],
                                    supplier["absolute_score"],
                                    float(minimum_score),
                                )
                                supplier["eligibility_status"] = eligibility
                                supplier["shortlist_status"] = shortlist
                        for supplier in result_rows:
                            if supplier["evaluation_status"] == "EVALUATION_ERROR":
                                supplier["warnings"].append("SUPPLIER_NOT_INCLUDED_IN_RANKING")
                    except ValueError as exc:
                        st.error(f"Run was not saved because scoring failed: {exc}")
                        st.stop()

                    statuses = {row["evaluation_status"] for row in result_rows}
                    run_status = (
                        "completed"
                        if len(statuses) == 1 and "EVALUATION_ERROR" not in statuses
                        else "partial"
                        if ranked
                        else "failed"
                    )
                    run_record = {
                        "rfp_run_id": run_id,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "status": run_status,
                        "criteria_snapshot": criteria,
                        "model_provider": model_provider,
                        "minimum_score": float(minimum_score),
                        "notes": notes.strip(),
                    }
                    try:
                        save_run(connection, run_record, result_rows, document_rows)
                    except sqlite3.Error as exc:
                        st.error(f"Could not persist evaluation run: {exc}")
                    else:
                        st.session_state["selected_run"] = run_id
                        st.success(
                            f"Run {run_id} saved ({run_status}). The output matrix and "
                            "leader dashboard now show the results; open Detailed results "
                            "for evidence and criterion-level information."
                        )
                        st.rerun()
    else:
        st.info("Upload one or more proposal PDFs to start a run.")

with results_tab:
    st.subheader("Proposal comparison dashboard")
    runs = list_runs(connection)
    if not runs:
        st.info("No evaluation runs have been saved yet.")
    else:
        run_ids = [row["rfp_run_id"] for row in runs]
        default_run = st.session_state.get("selected_run")
        index = run_ids.index(default_run) if default_run in run_ids else 0
        selected_run_id = st.selectbox(
            "Select an evaluation run",
            options=run_ids,
            index=index,
            format_func=lambda value: next(
                f"{value[:8]}… | {next(row['created_at'] for row in runs if row['rfp_run_id'] == value)}"
                for row in runs
                if row["rfp_run_id"] == value
            ),
        )
        if not isinstance(selected_run_id, str):
            st.error("Select an evaluation run to continue.")
            st.stop()
        run = load_run(connection, selected_run_id)
        st.caption(
            f"Run ID: `{run['rfp_run_id']}` · {run['status']} · "
            f"{run['model_provider']} · Created {run['created_at']}"
        )
        if run["notes"]:
            st.write(f"**Run notes:** {run['notes']}")
        st.caption(
            f"Criteria snapshot version(s): "
            + ", ".join(
                f"{row['criterion_id']} v{row['version']}"
                for row in run["criteria_snapshot"]
            )
        )

        successful = [
            row for row in run["suppliers"] if row["evaluation_status"] != "EVALUATION_ERROR"
        ]
        if successful:
            st.subheader("Evaluation output matrix")
            st.caption(
                "Criterion cells show reviewer/AI score over maximum. Final score is "
                "the weighted score out of 100; rank and shortlist status are separate "
                "from mandatory-gate verification."
            )
            output_matrix = pd.DataFrame(
                build_output_matrix_rows(successful, run["criteria_snapshot"])
            )
            st.dataframe(
                output_matrix,
                hide_index=True,
                width="stretch",
                key=f"output_matrix_{selected_run_id}",
            )

            leaderboard = pd.DataFrame(build_leaderboard_rows(successful))
            criterion_table = pd.DataFrame(
                build_criterion_rows(successful, run["criteria_snapshot"])
            )

            st.markdown(
                """
                <style>
                .dashboard-title {font-size: 1.55rem; font-weight: 700; margin: .35rem 0 0;}
                .dashboard-subtitle {color: #91a4bd; font-size: .9rem; margin-bottom: 1.1rem;}
                [data-testid="stMetric"] {
                    background: linear-gradient(145deg, rgba(25,41,67,.88), rgba(15,26,44,.92));
                    border: 1px solid rgba(118,153,197,.18);
                    padding: 1rem 1.1rem; border-radius: 14px;
                    box-shadow: 0 8px 22px rgba(2,12,27,.16);
                }
                </style>
                <div class="dashboard-title">Leader dashboard — ranked by final output score</div>
                <div class="dashboard-subtitle">
                Compare evidence-based final scores, peer performance, and criteria strengths
                across proposals in this run.
                </div>
                """,
                unsafe_allow_html=True,
            )

            filter_left, filter_middle, filter_right = st.columns(3)
            eligibility_values = ["All"] + sorted(
                leaderboard["Eligibility"].dropna().unique().tolist()
            )
            eligibility_filter = filter_left.selectbox(
                "Eligibility filter", eligibility_values
            )
            minimum_filter = filter_middle.number_input(
                "Minimum displayed score",
                min_value=0.0,
                max_value=100.0,
                value=0.0,
                step=1.0,
            )
            evidence_only = filter_right.checkbox("Only evidence/verification issues")
            filtered_leaderboard = leaderboard[
                leaderboard["Final score"] >= minimum_filter
            ]
            if eligibility_filter != "All":
                filtered_leaderboard = filtered_leaderboard[
                    filtered_leaderboard["Eligibility"] == eligibility_filter
                ]
            if evidence_only:
                issue_names = {
                    row["supplier_name"]
                    for row in successful
                    if row["warnings"]
                    or any(
                        gate["status"] != "PASS" for gate in row["gates"]
                    )
                }
                filtered_leaderboard = filtered_leaderboard[
                    filtered_leaderboard["Supplier"].isin(issue_names)
                ]

            display_names = filtered_leaderboard["Supplier"].tolist()
            visible_suppliers = [
                supplier
                for supplier in successful
                if supplier["supplier_name"] in display_names
            ]
            displayed_criteria = criterion_table[
                criterion_table["Supplier"].isin(display_names)
            ]

            proposal_count = len(visible_suppliers)
            average_score = (
                float(filtered_leaderboard["Final score"].mean())
                if proposal_count
                else 0.0
            )
            top_supplier = (
                filtered_leaderboard.sort_values(
                    ["Final score", "Technical rank"],
                    ascending=[False, True],
                ).iloc[0]
                if proposal_count
                else None
            )
            candidates = int(
                (filtered_leaderboard["Shortlist status"] == "SHORTLIST_CANDIDATE").sum()
            )
            kpi_one, kpi_two, kpi_three, kpi_four = st.columns(4)
            kpi_one.metric("Proposals in view", proposal_count)
            kpi_two.metric(
                "Top final score",
                f"{top_supplier['Final score']:.1f} / 100"
                if top_supplier is not None
                else "—",
                help=top_supplier["Supplier"] if top_supplier is not None else "",
            )
            kpi_three.metric("Average final score", f"{average_score:.1f} / 100")
            kpi_four.metric("Shortlist candidates", candidates)

            compare_names: list[str] = []
            if not proposal_count:
                st.info("No proposals match the selected dashboard filters.")
            else:
                status_colors = {
                    "ELIGIBLE_FOR_REVIEW": "#22c55e",
                    "PENDING_VERIFICATION": "#f59e0b",
                    "NOT_ELIGIBLE": "#ef4444",
                }
                display_order = (
                    filtered_leaderboard.sort_values("Technical rank")["Supplier"].tolist()
                )
                score_chart = px.bar(
                    filtered_leaderboard,
                    x="Final score",
                    y="Supplier",
                    color="Eligibility",
                    color_discrete_map=status_colors,
                    text=filtered_leaderboard["Final score"].map(lambda score: f"{score:.1f}"),
                    category_orders={"Supplier": display_order},
                    orientation="h",
                    hover_data={
                        "Technical rank": True,
                        "PPI": ":.2f",
                        "Shortlist status": True,
                        "Gate checks open": True,
                        "Warnings": True,
                        "Final score": False,
                    },
                    title="Final weighted score by proposal",
                    labels={"Final score": "Final score (0–100)"},
                )
                score_chart.update_traces(textposition="outside", cliponaxis=False)
                score_chart.update_layout(
                    xaxis=dict(range=[0, 108], title="Final weighted score (0–100)"),
                    yaxis_title="",
                    legend_title="Verification eligibility",
                    height=max(360, 68 * proposal_count),
                    margin=dict(l=20, r=35, t=65, b=25),
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                )
                if float(run["minimum_score"]) > 0:
                    score_chart.add_vline(
                        x=float(run["minimum_score"]),
                        line_dash="dash",
                        line_color="#cbd5e1",
                        annotation_text=f"Threshold {run['minimum_score']:g}",
                        annotation_position="top",
                    )
                st.plotly_chart(score_chart, width="stretch")

                view_left, view_right = st.columns(2)
                with view_left:
                    scatter = px.scatter(
                        filtered_leaderboard,
                        x="Final score",
                        y="PPI",
                        color="Eligibility",
                        color_discrete_map=status_colors,
                        size="Experience / 5",
                        size_max=28,
                        hover_name="Supplier",
                        hover_data=[
                            "Technical rank",
                            "Shortlist status",
                            "Gate checks open",
                            "Warnings",
                        ],
                        title="Absolute score vs peer performance",
                        labels={
                            "Final score": "Final weighted score (0–100)",
                            "PPI": "Peer Performance Index (%)",
                        },
                    )
                    scatter.update_layout(
                        height=390,
                        margin=dict(l=20, r=20, t=60, b=25),
                        plot_bgcolor="rgba(0,0,0,0)",
                        paper_bgcolor="rgba(0,0,0,0)",
                    )
                    st.plotly_chart(scatter, width="stretch")
                with view_right:
                    heat = displayed_criteria.pivot(
                        index="Supplier", columns="Criterion", values="Score (%)"
                    )
                    heat = heat.reindex(display_order)
                    heat = heat.reindex(
                        columns=[
                            criterion["name"]
                            for criterion in run["criteria_snapshot"]
                            if criterion["criterion_id"]
                            in set(displayed_criteria["Criterion ID"])
                        ]
                    )
                    heatmap = px.imshow(
                        heat,
                        color_continuous_scale=[
                            [0.0, "#ef4444"],
                            [0.5, "#f59e0b"],
                            [1.0, "#22c55e"],
                        ],
                        zmin=0,
                        zmax=100,
                        aspect="auto",
                        text_auto=True,
                        labels={
                            "x": "Evaluation criterion",
                            "y": "Supplier proposal",
                            "color": "Score %",
                        },
                        title="Criterion scorecard heatmap (% of maximum)",
                    )
                    heatmap.update_layout(
                        height=max(390, 65 * proposal_count),
                        margin=dict(l=20, r=20, t=60, b=100),
                        paper_bgcolor="rgba(0,0,0,0)",
                        xaxis_tickangle=-32,
                    )
                    st.plotly_chart(heatmap, width="stretch")

                compare_names = st.multiselect(
                    "Choose proposals for criteria profile comparison",
                    options=display_order,
                    default=display_order[: min(3, len(display_order))],
                    key=f"dashboard_compare_{selected_run_id}",
                )
                if compare_names:
                    radar_data = displayed_criteria[
                        displayed_criteria["Supplier"].isin(compare_names)
                    ]
                    radar = px.line_polar(
                        radar_data,
                        r="Score (%)",
                        theta="Criterion",
                        color="Supplier",
                        line_close=True,
                        range_r=[0, 100],
                        title="Supplier strengths profile (% of criterion maximum)",
                        hover_data=["Score", "Maximum", "Weight (%)"],
                    )
                    radar.update_traces(fill="toself", opacity=0.72)
                    radar.update_layout(
                        height=520,
                        margin=dict(l=40, r=40, t=65, b=35),
                        paper_bgcolor="rgba(0,0,0,0)",
                        polar=dict(
                            bgcolor="rgba(0,0,0,0)",
                            radialaxis=dict(range=[0, 100], ticksuffix="%"),
                        ),
                    )
                    st.plotly_chart(radar, width="stretch")

                st.markdown("#### Weighted contribution by criterion")
                contribution = px.bar(
                    displayed_criteria,
                    x="Supplier",
                    y="Weighted points",
                    color="Criterion",
                    barmode="stack",
                    hover_data={
                        "Score": True,
                        "Maximum": True,
                        "Weight (%)": True,
                        "Weighted points": ":.2f",
                    },
                    title="How each criterion contributes to the final score",
                    labels={"Weighted points": "Contribution to final score"},
                )
                contribution.update_layout(
                    height=430,
                    margin=dict(l=20, r=20, t=60, b=110),
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    xaxis_tickangle=-20,
                )
                st.plotly_chart(contribution, width="stretch")

                st.markdown("#### Final scores and review status")
                st.dataframe(
                    filtered_leaderboard,
                    hide_index=True,
                    width="stretch",
                    column_config={
                        "Final score": st.column_config.ProgressColumn(
                            "Final score / 100",
                            min_value=0,
                            max_value=100,
                            format="%.2f",
                        ),
                        "PPI": st.column_config.NumberColumn(
                            "Peer performance (%)", format="%.2f%%"
                        ),
                    },
                )

            st.caption(
                "Technical rank is diagnostic only. Pending or failed mandatory gates prevent "
                "shortlist candidacy; no AI score constitutes approval."
            )
            left, right = st.columns(2)
            with left:
                st.download_button(
                    "Download full audit JSON",
                    data=_json_bytes(run),
                    file_name=f"tender_evaluation_{run['rfp_run_id'][:8]}.json",
                    mime="application/json",
                )
            with right:
                st.download_button(
                    "Download leaderboard CSV",
                    data=filtered_leaderboard.to_csv(index=False).encode("utf-8"),
                    file_name=f"tender_leaderboard_{run['rfp_run_id'][:8]}.csv",
                    mime="text/csv",
                )

            supplier_names = [row["supplier_name"] for row in successful]
            selected_names = compare_names if proposal_count else []
            if selected_names:
                comparison = displayed_criteria[
                    displayed_criteria["Supplier"].isin(selected_names)
                ]
                st.markdown("#### Selected proposal score breakdown")
                st.dataframe(
                    comparison[
                        [
                            "Supplier",
                            "Criterion",
                            "Score",
                            "Maximum",
                            "Weight (%)",
                            "Weighted points",
                            "Peer benchmark",
                            "Gap",
                            "Relative performance (%)",
                            "Evidence page",
                        ]
                    ],
                    hide_index=True,
                    width="stretch",
                )

            supplier_by_name = {row["supplier_name"]: row for row in run["suppliers"]}
            selected_supplier = st.selectbox(
                "Individual proposal analysis",
                options=supplier_names,
                key=f"detail_supplier_{selected_run_id}",
            )
            detail = supplier_by_name[selected_supplier]
            profile = detail["result_json"].get("supplier_profile", {})
            with st.expander("Supplier history and proposal profile", expanded=False):
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "Supplier": detail["supplier_name"],
                                "Submission date": detail["submission_date"],
                                "Historical experience / 5": detail["experience_rating"],
                                "Historical performance / 100": profile.get(
                                    "historical_performance_score"
                                ),
                                "Manufacturing experience (years)": profile.get(
                                    "manufacturing_experience_years"
                                ),
                                "Proposed annual capacity (MT)": profile.get(
                                    "proposed_annual_capacity_mt"
                                ),
                                "Manufacturing site": profile.get("manufacturing_site"),
                                "Product scope": profile.get("product_scope"),
                            }
                        ]
                    ),
                    hide_index=True,
                    width="stretch",
                )
            dleft, dmid, dright = st.columns(3)
            dleft.metric("Final weighted score", f"{detail['absolute_score']:.2f} / 100")
            dmid.metric("Peer Performance Index", f"{detail['ppi']:.2f}")
            industry_index = float(
                detail.get(
                    "industry_index",
                    detail["result_json"].get("industry_index", 0.0),
                )
            )
            dright.metric("Industry index¹", f"{industry_index:.2f}")
            st.caption(
                "¹ Cohort-relative proxy: 100 equals the average final score in this "
                "evaluation run; this is not an external industry benchmark."
            )
            st.progress(
                min(max(float(detail["absolute_score"]) / 100.0, 0.0), 1.0),
                text="Final weighted score",
            )
            contribution_rows = build_score_contribution_rows(
                detail["criterion_results"],
                run["criteria_snapshot"],
                float(detail["absolute_score"]),
            )
            pie = px.pie(
                pd.DataFrame(contribution_rows),
                names="Criterion",
                values="Weighted points",
                hole=0.48,
                title="Individual proposal — weighted contribution by template criterion",
            )
            pie.update_traces(
                textposition="inside",
                texttemplate="%{label}<br>%{value:.1f}",
                hovertemplate="%{label}: %{value:.2f} points<extra></extra>",
            )
            pie.add_annotation(
                text=f"{float(detail['absolute_score']):.1f}<br><sup>out of 100</sup>",
                x=0.5,
                y=0.5,
                showarrow=False,
                font_size=18,
            )
            pie.update_layout(
                height=510,
                margin=dict(l=15, r=15, t=75, b=15),
                showlegend=True,
            )
            st.plotly_chart(pie, width="stretch")
            st.markdown("#### Evidence supporting each criterion score")
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Criterion": next(
                                (
                                    item["name"]
                                    for item in run["criteria_snapshot"]
                                    if item["criterion_id"] == criterion["criterion_id"]
                                ),
                                criterion["criterion_id"],
                            ),
                            "Score / max": (
                                f"{criterion['score']:g} / {criterion['max_score']:g}"
                            ),
                            "Weight (%)": criterion["weight"],
                            "Weighted points": criterion["weighted_contribution"],
                            "Evidence excerpt": criterion["evidence"],
                            "Page": criterion["evidence_page"],
                            "Rationale": criterion["justification"],
                        }
                        for criterion in detail["criterion_results"]
                    ]
                ),
                hide_index=True,
                width="stretch",
            )
            st.markdown(f"**Summary:** {detail['result_json'].get('overall_summary', '')}")
            llm_validation = detail["result_json"].get("llm_validation")
            if llm_validation:
                if llm_validation.get("passed"):
                    st.success(
                        "Second-pass LLM evidence critique found no material evidence-support issue. "
                        "This is not independent verification."
                    )
                else:
                    st.warning("Second-pass LLM evidence critique flagged concerns.")
                for finding in llm_validation.get("findings", []):
                    st.warning(
                        f"{finding.get('criterion_id', 'criterion')}: "
                        f"{finding.get('explanation', '')}"
                    )
            commercial_review = detail["result_json"].get("commercial_review", {})
            if commercial_review.get("status") != "COMPARABLE":
                st.warning(
                    f"Commercial comparison: {commercial_review.get('status', 'NOT_REVIEWED')}. "
                    "Do not treat commercial criterion scores as a definitive price ranking."
                )
            if commercial_review.get("rationale"):
                st.caption(f"Commercial review basis: {commercial_review['rationale']}")
            if detail["result_json"].get("risks"):
                st.markdown("**Risks and open concerns**")
                for risk in detail["result_json"]["risks"]:
                    st.warning(risk)

            for criterion_result in detail["criterion_results"]:
                criterion = next(
                    (
                        row
                        for row in run["criteria_snapshot"]
                        if row["criterion_id"] == criterion_result["criterion_id"]
                    ),
                    {"name": criterion_result["criterion_id"]},
                )
                with st.expander(
                    f"{criterion['name']}: {criterion_result['score']:g}/"
                    f"{criterion_result['max_score']:g} · "
                    f"{criterion_result['weight']:g}% weight"
                ):
                    st.write(criterion_result["justification"] or "No justification provided.")
                    st.write(
                        f"**Evidence:** {criterion_result['evidence'] or 'No evidence excerpt supplied.'}"
                    )
                    if criterion_result["evidence_page"]:
                        st.caption(f"Proposal page {criterion_result['evidence_page']}")
                    st.caption(
                        f"Peer benchmark {criterion_result['benchmark']:g} · "
                        f"Gap {criterion_result['gap']:g} · "
                        f"Relative performance {criterion_result['relative_pct']:.2f}% · "
                        f"Weighted contribution {criterion_result['weighted_contribution']:.2f}"
                    )
                    if criterion_result["missing_evidence"]:
                        st.write("Missing evidence: " + "; ".join(criterion_result["missing_evidence"]))

            st.markdown("#### Mandatory verification gates")
            with st.form(f"gate_review_{detail['result_id']}"):
                gate_values: list[dict[str, Any]] = []
                for gate in detail["gates"]:
                    st.markdown(f"**{gate['gate_name']}**")
                    gate_status = st.selectbox(
                        "Review status",
                        ["PENDING_VERIFICATION", "PASS", "FAIL"],
                        index=[
                            "PENDING_VERIFICATION",
                            "PASS",
                            "FAIL",
                        ].index(gate["status"]),
                        key=f"gate_status_{detail['result_id']}_{gate['gate_id']}",
                    )
                    rationale = st.text_input(
                        "Verification rationale",
                        value=gate["rationale"],
                        key=f"gate_reason_{detail['result_id']}_{gate['gate_id']}",
                    )
                    gate_values.append(
                        {"gate_id": gate["gate_id"], "status": gate_status, "rationale": rationale}
                    )
                reviewer = st.text_input(
                    "Reviewer name / identifier",
                    key=f"gate_reviewer_{detail['result_id']}",
                )
                gate_submit = st.form_submit_button("Save human gate review")
            if gate_submit:
                if not reviewer.strip():
                    st.error("Enter the authorized reviewer's name or identifier.")
                else:
                    for gate in gate_values:
                        update_gate(
                            connection,
                            detail["result_id"],
                            gate["gate_id"],
                            gate["status"],
                            gate["rationale"],
                            reviewer,
                        )
                    st.success("Gate decisions saved. They do not change the technical score.")
                    st.rerun()
            if detail["gate_history"]:
                with st.expander("Gate decision audit history"):
                    st.dataframe(
                        pd.DataFrame(detail["gate_history"]),
                        hide_index=True,
                        width="stretch",
                    )
        else:
            st.warning("No supplier in this run has a valid scorecard; all are excluded from ranking.")

        failed_suppliers = [
            row for row in run["suppliers"] if row["evaluation_status"] == "EVALUATION_ERROR"
        ]
        if failed_suppliers:
            st.markdown("#### Evaluation errors requiring retry or manual review")
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Supplier": row["supplier_name"],
                            "Failure": row["failure_reason"],
                            "Warnings": "; ".join(row["warnings"]),
                        }
                        for row in failed_suppliers
                    ]
                ),
                hide_index=True,
                width="stretch",
            )
        if run["documents"]:
            with st.expander("Document extraction audit"):
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "Supplier": row["supplier_name"],
                                "Filename": row["original_filename"],
                                "Pages": row["page_count"],
                                "Extraction": row["extraction_status"],
                                "SHA-256": row["sha256"],
                                "Warnings": "; ".join(row["warnings"]),
                            }
                            for row in run["documents"]
                        ]
                    ),
                    hide_index=True,
                    width="stretch",
                )

with detailed_results_tab:
    st.subheader("Detailed evaluation results")
    st.caption(
        "One row per supplier and criterion. Scores are calculated deterministically; "
        "citations and rationale should be checked by the tender reviewers."
    )
    detailed_runs = list_runs(connection)
    if not detailed_runs:
        st.info("Complete an evaluation run to see detailed results here.")
    else:
        detailed_run_ids = [row["rfp_run_id"] for row in detailed_runs]
        preferred_run = st.session_state.get("selected_run")
        detailed_default_index = (
            detailed_run_ids.index(preferred_run)
            if preferred_run in detailed_run_ids
            else 0
        )
        detailed_run_id = st.selectbox(
            "Evaluation run for detailed results",
            options=detailed_run_ids,
            index=detailed_default_index,
            key="detailed_results_run_selector",
            format_func=lambda value: next(
                f"{value[:8]}… | {next(row['created_at'] for row in detailed_runs if row['rfp_run_id'] == value)}"
                for row in detailed_runs
                if row["rfp_run_id"] == value
            ),
        )
        if not isinstance(detailed_run_id, str):
            st.error("Select an evaluation run to see detailed results.")
            st.stop()
        detailed_run = load_run(connection, detailed_run_id)
        st.caption(
            f"Run `{detailed_run['rfp_run_id']}` · {detailed_run['status']} · "
            f"{detailed_run['model_provider']} · "
            f"{len(detailed_run['suppliers'])} supplier(s)"
        )
        detailed_successful = [
            supplier
            for supplier in detailed_run["suppliers"]
            if supplier["evaluation_status"] != "EVALUATION_ERROR"
        ]
        detailed_failed = [
            supplier
            for supplier in detailed_run["suppliers"]
            if supplier["evaluation_status"] == "EVALUATION_ERROR"
        ]
        if detailed_successful:
            summary_rows = build_leaderboard_rows(detailed_successful)
            detailed_rows = build_detailed_result_rows(
                detailed_successful, detailed_run["criteria_snapshot"]
            )
            summary_frame = pd.DataFrame(summary_rows)
            detailed_frame = pd.DataFrame(detailed_rows)

            st.markdown("#### Supplier final-score summary")
            st.dataframe(
                summary_frame,
                hide_index=True,
                width="stretch",
                column_config={
                    "Final score": st.column_config.ProgressColumn(
                        "Final score / 100",
                        min_value=0,
                        max_value=100,
                        format="%.2f",
                    ),
                    "PPI": st.column_config.NumberColumn(
                        "PPI (%)", format="%.2f%%"
                    ),
                },
            )

            detail_filter_left, detail_filter_right = st.columns(2)
            available_suppliers = [
                row["supplier_name"] for row in detailed_successful
            ]
            selected_detail_suppliers = detail_filter_left.multiselect(
                "Filter suppliers",
                options=available_suppliers,
                default=available_suppliers,
                key=f"detailed_suppliers_{detailed_run_id}",
            )
            criterion_options = [
                row["name"] for row in detailed_run["criteria_snapshot"]
            ]
            selected_detail_criteria = detail_filter_right.multiselect(
                "Filter criteria",
                options=criterion_options,
                default=criterion_options,
                key=f"detailed_criteria_{detailed_run_id}",
            )
            filtered_details = detailed_frame[
                detailed_frame["Supplier"].isin(selected_detail_suppliers)
                & detailed_frame["Criterion"].isin(selected_detail_criteria)
            ]

            st.markdown("#### Criterion-level evidence and scoring")
            st.dataframe(
                filtered_details,
                hide_index=True,
                width="stretch",
                height=min(720, max(260, 38 * (len(filtered_details) + 1))),
                column_config={
                    "Final score / 100": st.column_config.ProgressColumn(
                        "Final score / 100",
                        min_value=0,
                        max_value=100,
                        format="%.2f",
                    ),
                    "Evidence excerpt": st.column_config.TextColumn(
                        "Evidence excerpt", width="large"
                    ),
                    "Rationale": st.column_config.TextColumn(
                        "Rationale", width="large"
                    ),
                    "Missing evidence": st.column_config.TextColumn(
                        "Missing evidence", width="large"
                    ),
                },
            )
            csv_data = filtered_details.to_csv(index=False).encode("utf-8-sig")
            download_left, download_right = st.columns(2)
            download_left.download_button(
                "Download detailed results (CSV)",
                data=csv_data,
                file_name=f"detailed_tender_results_{detailed_run_id[:8]}.csv",
                mime="text/csv",
                key=f"detailed_results_csv_{detailed_run_id}",
            )
            download_right.download_button(
                "Download full run and audit (JSON)",
                data=_json_bytes(detailed_run),
                file_name=f"tender_audit_{detailed_run_id[:8]}.json",
                mime="application/json",
                key=f"detailed_results_json_{detailed_run_id}",
            )
        else:
            st.info("This run does not contain a valid scorecard to display.")

        if detailed_failed:
            st.markdown("#### Supplier evaluation errors")
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Supplier": supplier["supplier_name"],
                            "Status": supplier["evaluation_status"],
                            "Failure": supplier["failure_reason"],
                            "Warnings": "; ".join(supplier["warnings"]),
                        }
                        for supplier in detailed_failed
                    ]
                ),
                hide_index=True,
                width="stretch",
            )

with criteria_tab:
    st.subheader("Configurable evaluation criteria")
    st.caption(
        "Changes affect future runs only. Existing runs preserve their criteria snapshot. "
        "This prototype has no user authentication; restrict access before real use."
    )
    criteria_rows = get_criteria(connection)
    editor_frame = pd.DataFrame(
        [
            {
                "criterion_id": row["criterion_id"],
                "name": row["name"],
                "description": row["description"],
                "weight": row["weight"],
                "max_score": row["max_score"],
                "is_active": bool(row["is_active"]),
            }
            for row in criteria_rows
        ]
    )
    with st.form("criteria_editor_form"):
        edited = st.data_editor(
            editor_frame,
            num_rows="dynamic",
            hide_index=True,
            width="stretch",
            column_config={
                "criterion_id": st.column_config.TextColumn("Stable ID", required=True),
                "name": st.column_config.TextColumn("Criterion", required=True),
                "description": st.column_config.TextColumn("Assessment scope", required=True),
                "weight": st.column_config.NumberColumn("Weight (%)", min_value=0.0, step=1.0),
                "max_score": st.column_config.NumberColumn("Maximum score", min_value=0.1),
                "is_active": st.column_config.CheckboxColumn("Active"),
            },
        )
        actor = st.text_input("Criteria editor / authorized owner identifier")
        criteria_submit = st.form_submit_button("Save criteria for future runs")
    if criteria_submit:
        try:
            rows = [
                {str(key): value for key, value in record.items()}
                for record in edited.to_dict(orient="records")
            ]
            if not actor.strip():
                raise ValueError("Enter the authorized criteria editor's identifier.")
            if any(not str(row.get("name", "")).strip() for row in rows):
                raise ValueError("Criterion names cannot be empty.")
            if any(not str(row.get("description", "")).strip() for row in rows):
                raise ValueError("Criterion descriptions cannot be empty.")
            save_criteria(connection, rows, actor.strip())
        except (ValueError, TypeError) as exc:
            st.error(f"Criteria not saved: {exc}")
        else:
            st.success("Criteria saved and audit logged.")
            st.rerun()

    st.markdown("#### Mandatory gates")
    st.write(
        "Gate outcomes are separate from numerical scores. Every gate starts as "
        "**PENDING_VERIFICATION**; pending or failed gates prevent shortlist candidacy."
    )
    st.dataframe(
        pd.DataFrame(
            [{"Gate ID": gate_id, "Human verification requirement": name} for gate_id, name in DEFAULT_GATES]
        ),
        hide_index=True,
        width="stretch",
    )
    st.caption(
        "Commercial scores are not a definitive price ranking unless all bids share "
        "product scope, volume, packaging, testing/release, delivery, currency, tax basis, "
        "and contract period. Mark incomparable bids for human normalization in run notes."
    )

connection.close()
