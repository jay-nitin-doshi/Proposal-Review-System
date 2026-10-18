# Paracetamol Manufacturing Tender Review

A local Streamlit decision-support app for reviewing multiple supplier proposal
PDFs. It provides page-aware evidence extraction, optional LLM-assisted criterion
scorecards, reviewer-entered scoring, deterministic weighted scoring and peer
benchmarking, human-reviewed eligibility gates, SQLite audit history, and JSON/CSV
exports. Its interactive proposal dashboard includes final-score ranking,
eligibility-aware comparisons, a criteria heatmap, supplier strengths radar,
weighted-contribution breakdown, filters, and scorecard-level evidence detail.
The default first tab is a colorful **New evaluation** workspace with the PDF
uploader, evaluation steps, and a chart of active tender-template weights.
After a run completes, the **Output matrix & leader dashboard** tab shows a
supplier-by-criterion matrix followed by the ranked leader dashboard, ordered
by the final weighted score.
A separate **Detailed results** tab provides a filterable, exportable table with
one row per supplier and criterion, including final score, criterion score,
weight, weighted contribution, peer benchmark, rationale, cited excerpt/page,
missing evidence, confidence, and verification status.

> **Synthetic training/demo only.** The supplied supplier names, proposal contents,
> dates, hints, and criteria are fictional and are not official Pfizer policy or a
> real procurement standard. Do not use this prototype to qualify a real supplier
> or make an award decision. Obtain authorized procurement, Quality, Regulatory,
> Legal, EHS, information-security, and privacy approval first.

## Run locally on Windows

From the project directory in PowerShell:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

Open the local URL printed by Streamlit. Upload the included synthetic PDFs to
exercise the workflow. A local SQLite database is created at
`data\rfp_evaluation.db` by default. Set `RFP_DB_PATH` to use a different path.
Database files and secrets are excluded from Git.

For an evidence-rich single-supplier test, upload
`synthetic_calyxora_pharmaworks_proposal.pdf`, enter the supplier name shown in
the proposal, use submission date `2026-10-18`, and enter any experience rating
only as a reviewer-supplied test value. Regenerate the PDF with:

```powershell
python tools\generate_synthetic_supplier_proposal.py
```

This 12-page file is intentionally fictional, including its company, licence
references, claimed audit results, pricing, capacity, exhibits, and references.
It contains no authentic supporting certificates and cannot establish gate
eligibility or guarantee a specific AI score. The five mandatory verification
gates should remain pending until a human checks genuine evidence.

## Evaluation workflow

1. Upload one or more PDFs and enter each supplier's legal name, submission date,
   and historical experience rating.
2. Choose manual review or AI-assisted evidence extraction.
3. The app extracts PDF text while retaining page labels, reports OCR-needed
   documents, computes SHA-256 document hashes, and creates a unique evaluation run.
4. AI evaluation requests one criterion-wise JSON scorecard per supplier. Manual
   evaluation permits reviewers to enter scores, rationale, and cited evidence.
5. Python validates criterion IDs and score ranges, defaults omitted model scores
   to zero with a warning, conservatively defaults positive scores with no cited
   documentary evidence to zero, computes weighted absolute scores and peer PPI,
   and applies deterministic tie-breaks.
6. Human reviewers record the separate mandatory-gate decisions. A pending or
   failed gate prevents shortlist candidacy; no result is marked approved.
7. Inspect evidence and missing items; export the full run as JSON or its leaderboard
   as CSV.

The default rubric has eight configurable criteria (20/20/15/10/10/15/5/5 percent)
with 0–10 scores. Active weights must total 100%. Criteria changes are versioned,
audited, and snapshotted per run; changing criteria does not change past results.

## AI providers and evaluation

The sidebar supports **OpenAI**, **Google Gemini**, and **Anthropic**. Enter a
provider API key and select **Validate key and load models**. The app calls the
provider's model-list endpoint; only after successful validation does it show
the available chat-model selector. In AI mode, proposal upload is disabled
until a model is selected. Changing the provider or key invalidates the prior
validation and requires validation again.

Provider keys are password inputs held only in Streamlit session state; the app
does not read them from `.env` or write them to the application database.
LangSmith tracing is optional; enter a LangSmith API key in the sidebar to
enable it. Traces can contain full proposal text, scorecards, and evidence.
Manual reviewer mode does not require a provider key.

The evaluator uses the selected provider's LangChain adapter and a LangGraph
to generate a structured Pydantic scorecard, validate it against active
criteria in Python, and run a second LLM evidence-critique pass. Validation
issues trigger one bounded repair attempt; cited pages beyond the extracted
document page count are rejected. Persistent issues become an evaluation error
and are not ranked. The critique uses the same configured model, so it is an
additional check—not independent verification. Python remains authoritative
for evidence rules, scoring, ranking, and eligibility gates.

The critique parser also accepts provider JSON-mode responses wrapped under
`validation_result` with `issue`, `material` or `material_issue`, and
`overall_validation` fields.
Synthetic/demo labeling or lack of independent verification is recorded as a
review risk, not by itself as a score-evidence mismatch; substantive evidence
contradictions still trigger repair and can fail closed.

AI-assisted evaluation requires explicit confirmation in the sidebar that the
selected provider is approved to process the proposal data. If tracing is
enabled, the same confirmation also covers LangSmith.

Each proposal's basic profile includes prior experience rating, historical
performance score, years manufacturing the product/category, proposed annual
capacity, site/country, and product scope. Historical performance is retained
for reviewer context; it does not change the tender score or ranking.

The model extracts and assesses evidence only. It cannot calculate scores, rank
suppliers, verify GMP/licences, set gates, or choose an awardee. The criteria,
gate definitions, minimum shortlist score, and all supplier metadata must be
authorized for the actual tender before use.

## Scoring and decision controls

- Absolute weighted score: `sum((criterion score / criterion maximum) * weight %)`.
- Criterion benchmark: maximum score among valid scorecards in the same run.
- PPI: weighted average of each criterion's score divided by its peer benchmark.
  A zero benchmark produces relative performance 0 and an explicit warning.
- Industry index (proposal-cohort proxy): `supplier final score / mean final score
  in this run * 100`; 100 is the run average. This is not an externally sourced
  industry benchmark.
- Ranking: higher PPI, earlier submission, higher historical experience rating,
  then case-insensitive supplier name. Errors are not ranked.
- Gates: `PASS`, `FAIL`, or `PENDING_VERIFICATION`; unknown is never a pass.
- Commercial score comparisons are not definitive until product scope, volume,
  packaging, testing/release, delivery basis, currency, tax basis, and contract
  period are comparable. Reviewers record comparability status and its rationale
  for each supplier; unreviewed/incomparable bids are visibly flagged.
- Selecting an individual proposal displays its final score and PPI, the
  proposal-cohort industry-index proxy, a template-weighted contribution pie
  chart, and criterion-level rationale/evidence excerpts and page references.

## Tests

```powershell
python -m pytest -q
```

The test suite covers provider-key validation and model discovery, staged
upload gating, provider adapter configuration, weight validation, score
formulas, PPI and cohort index, deterministic tie-breaking, scorecard
validation, contribution pie totals, gate behavior, and PDF extraction/OCR
detection.

## Production limitations

This prototype has no authentication, authorization, encryption-at-rest policy,
enterprise audit-log immutability, shared database, retention controls, or
production-grade deployment hardening. Local SQLite is not appropriate for
multi-user or ephemeral-host production. Before processing real tenders, add
approved identity/access management, secure persistent storage, backups,
retention/deletion controls, provider data-processing approval, dependency/security
reviews, and human quality/regulatory review.
