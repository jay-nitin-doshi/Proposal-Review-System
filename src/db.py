"""SQLite persistence for tender runs, criteria, documents, and reviews."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.scoring import validate_criteria


DEFAULT_CRITERIA = [
    ("manufacturing_capability", "Manufacturing capability & process control", "Facility/process fit, equipment, batch controls, contamination prevention, validation, cleaning, and traceability.", 20.0, 10.0),
    ("quality_system", "GMP, quality system & product quality", "GMP evidence, quality systems, deviations/CAPA, change control, data integrity, batch release, complaints, and recalls.", 20.0, 10.0),
    ("regulatory_readiness", "Regulatory readiness & documentation", "Site-specific licences, inspection evidence, target-market readiness, dossier support, and document completeness.", 15.0, 10.0),
    ("supply_continuity", "Supply capacity & business continuity", "Demonstrated/uncommitted capacity, lead times, critical sourcing, continuity, and shortage plans.", 10.0, 10.0),
    ("technology_transfer", "Implementation & technology transfer", "Milestones, ownership, transfer/qualification/validation, staffing, risks, and acceptance criteria.", 10.0, 10.0),
    ("commercial_value", "Commercial value & price transparency", "Comparable total cost, line-item pricing, MOQ, testing, packaging, freight, taxes, currency, and payment terms.", 15.0, 10.0),
    ("ehs_security", "EHS, security & risk controls", "Safety/environmental controls, waste handling, access controls, record integrity, and risk mitigation.", 5.0, 10.0),
    ("support_experience", "Support, experience & references", "Relevant experience, reference quality, complaint/recall support, escalation coverage, and service targets.", 5.0, 10.0),
]

DEFAULT_GATES = [
    ("site_licence", "Current site-specific manufacturing licence verified"),
    ("gmp_status", "Applicable GMP status and inspection disposition verified"),
    ("product_scope", "Exact product scope and target-market requirements confirmed"),
    ("critical_findings", "No unresolved critical quality or data-integrity finding"),
    ("quality_agreement", "Required quality agreement and audit rights accepted"),
]


def connect(database_path: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(database_path: str | Path) -> None:
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(connect(path)) as connection, connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS evaluation_criteria (
                criterion_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                weight REAL NOT NULL CHECK(weight >= 0),
                max_score REAL NOT NULL CHECK(max_score > 0),
                is_active INTEGER NOT NULL DEFAULT 1,
                version INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS rfp_runs (
                rfp_run_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL,
                criteria_snapshot_json TEXT NOT NULL,
                model_provider TEXT NOT NULL,
                minimum_score REAL NOT NULL,
                notes TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS supplier_results (
                result_id INTEGER PRIMARY KEY AUTOINCREMENT,
                rfp_run_id TEXT NOT NULL REFERENCES rfp_runs(rfp_run_id),
                supplier_name TEXT NOT NULL,
                submission_date TEXT NOT NULL,
                experience_rating REAL NOT NULL,
                evaluation_status TEXT NOT NULL,
                absolute_score REAL,
                ppi REAL,
                technical_rank INTEGER,
                eligibility_status TEXT NOT NULL,
                shortlist_status TEXT NOT NULL,
                result_json TEXT NOT NULL,
                raw_model_output TEXT,
                failure_reason TEXT NOT NULL DEFAULT '',
                warnings_json TEXT NOT NULL DEFAULT '[]',
                UNIQUE(rfp_run_id, supplier_name)
            );
            CREATE TABLE IF NOT EXISTS criterion_results (
                result_id INTEGER NOT NULL REFERENCES supplier_results(result_id),
                criterion_id TEXT NOT NULL,
                score REAL NOT NULL,
                max_score REAL NOT NULL,
                weight REAL NOT NULL,
                benchmark REAL,
                gap REAL,
                relative_pct REAL,
                weighted_contribution REAL,
                justification TEXT NOT NULL,
                evidence TEXT NOT NULL,
                evidence_page INTEGER,
                confidence TEXT NOT NULL,
                missing_evidence_json TEXT NOT NULL DEFAULT '[]',
                PRIMARY KEY(result_id, criterion_id)
            );
            CREATE TABLE IF NOT EXISTS supplier_documents (
                document_id INTEGER PRIMARY KEY AUTOINCREMENT,
                rfp_run_id TEXT NOT NULL REFERENCES rfp_runs(rfp_run_id),
                supplier_name TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                page_count INTEGER,
                extraction_status TEXT NOT NULL,
                extraction_warnings_json TEXT NOT NULL DEFAULT '[]'
            );
            CREATE TABLE IF NOT EXISTS eligibility_gates (
                result_id INTEGER NOT NULL REFERENCES supplier_results(result_id),
                gate_id TEXT NOT NULL,
                gate_name TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('PASS','FAIL','PENDING_VERIFICATION')),
                rationale TEXT NOT NULL DEFAULT '',
                reviewer TEXT NOT NULL DEFAULT '',
                reviewed_at TEXT,
                PRIMARY KEY(result_id, gate_id)
            );
            CREATE TABLE IF NOT EXISTS criteria_audit (
                audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                changed_at TEXT NOT NULL,
                actor TEXT NOT NULL,
                before_json TEXT NOT NULL,
                after_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS gate_audit (
                audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                result_id INTEGER NOT NULL REFERENCES supplier_results(result_id),
                gate_id TEXT NOT NULL,
                changed_at TEXT NOT NULL,
                reviewer TEXT NOT NULL,
                previous_status TEXT NOT NULL,
                new_status TEXT NOT NULL,
                previous_rationale TEXT NOT NULL,
                new_rationale TEXT NOT NULL
            );
            """
        )
        existing = connection.execute(
            "SELECT COUNT(*) FROM evaluation_criteria"
        ).fetchone()[0]
        if existing == 0:
            connection.executemany(
                """INSERT INTO evaluation_criteria
                   (criterion_id,name,description,weight,max_score,is_active,version)
                   VALUES (?,?,?,?,?,1,1)""",
                DEFAULT_CRITERIA,
            )


def get_criteria(
    connection: sqlite3.Connection, *, active_only: bool = False
) -> list[dict[str, Any]]:
    query = "SELECT * FROM evaluation_criteria"
    if active_only:
        query += " WHERE is_active = 1"
    query += " ORDER BY rowid"
    return [dict(row) for row in connection.execute(query).fetchall()]


def save_criteria(
    connection: sqlite3.Connection, rows: list[dict[str, Any]], actor: str
) -> None:
    criteria = [
        {
            **row,
            "weight": float(row["weight"]),
            "max_score": float(row["max_score"]),
            "is_active": bool(row["is_active"]),
        }
        for row in rows
    ]
    validate_criteria(criteria)
    before = get_criteria(connection)
    before_by_id = {row["criterion_id"]: row for row in before}
    with connection:
        for row in criteria:
            criterion_id = str(row["criterion_id"]).strip()
            if not criterion_id.replace("_", "").isalnum():
                raise ValueError(f"Invalid criterion ID: {criterion_id!r}.")
            prior = before_by_id.get(criterion_id)
            version = int(prior["version"]) + 1 if prior else 1
            connection.execute(
                """INSERT INTO evaluation_criteria
                   (criterion_id,name,description,weight,max_score,is_active,version)
                   VALUES (?,?,?,?,?,?,?)
                   ON CONFLICT(criterion_id) DO UPDATE SET
                     name=excluded.name, description=excluded.description,
                     weight=excluded.weight, max_score=excluded.max_score,
                     is_active=excluded.is_active, version=excluded.version""",
                (
                    criterion_id,
                    str(row["name"]).strip(),
                    str(row["description"]).strip(),
                    float(row["weight"]),
                    float(row["max_score"]),
                    int(bool(row["is_active"])),
                    version,
                ),
            )
        submitted = {str(row["criterion_id"]).strip() for row in criteria}
        for old in before:
            if old["criterion_id"] not in submitted:
                connection.execute(
                    "UPDATE evaluation_criteria SET is_active=0, version=version+1 WHERE criterion_id=?",
                    (old["criterion_id"],),
                )
        after = get_criteria(connection)
        connection.execute(
            """INSERT INTO criteria_audit(changed_at,actor,before_json,after_json)
               VALUES(?,?,?,?)""",
            (
                datetime.now(timezone.utc).isoformat(),
                actor,
                json.dumps(before),
                json.dumps(after),
            ),
        )


def save_run(
    connection: sqlite3.Connection,
    run: dict[str, Any],
    suppliers: list[dict[str, Any]],
    documents: list[dict[str, Any]],
) -> None:
    with connection:
        connection.execute(
            """INSERT INTO rfp_runs
               (rfp_run_id,created_at,status,criteria_snapshot_json,model_provider,minimum_score,notes)
               VALUES(?,?,?,?,?,?,?)""",
            (
                run["rfp_run_id"],
                run["created_at"],
                run["status"],
                json.dumps(run["criteria_snapshot"], ensure_ascii=False),
                run["model_provider"],
                run["minimum_score"],
                run.get("notes", ""),
            ),
        )
        for supplier in suppliers:
            cursor = connection.execute(
                """INSERT INTO supplier_results
                   (rfp_run_id,supplier_name,submission_date,experience_rating,
                    evaluation_status,absolute_score,ppi,technical_rank,
                    eligibility_status,shortlist_status,result_json,raw_model_output,
                    failure_reason,warnings_json)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    run["rfp_run_id"],
                    supplier["supplier_name"],
                    supplier["submission_date"],
                    supplier["experience_rating"],
                    supplier["evaluation_status"],
                    supplier.get("absolute_score"),
                    supplier.get("ppi"),
                    supplier.get("technical_rank"),
                    supplier["eligibility_status"],
                    supplier["shortlist_status"],
                    json.dumps(supplier.get("result_json", {}), ensure_ascii=False),
                    supplier.get("raw_model_output"),
                    supplier.get("failure_reason", ""),
                    json.dumps(supplier.get("warnings", []), ensure_ascii=False),
                ),
            )
            result_id = cursor.lastrowid
            for gate in supplier["gates"]:
                connection.execute(
                    """INSERT INTO eligibility_gates
                       (result_id,gate_id,gate_name,status,rationale,reviewer,reviewed_at)
                       VALUES(?,?,?,?,?,?,?)""",
                    (
                        result_id,
                        gate["gate_id"],
                        gate["gate_name"],
                        gate["status"],
                        gate.get("rationale", ""),
                        gate.get("reviewer", ""),
                        gate.get("reviewed_at"),
                    ),
                )
            scorecard = supplier.get("scorecard")
            if scorecard:
                for score in scorecard["criteria"]:
                    metric = supplier["criterion_metrics"][score["criterion_id"]]
                    connection.execute(
                        """INSERT INTO criterion_results
                           (result_id,criterion_id,score,max_score,weight,benchmark,gap,
                            relative_pct,weighted_contribution,justification,evidence,
                            evidence_page,confidence,missing_evidence_json)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            result_id,
                            score["criterion_id"],
                            score["score"],
                            score["max_score"],
                            score["weight"],
                            metric["benchmark"],
                            metric["gap"],
                            metric["relative_pct"],
                            metric["weighted_contribution"],
                            score["justification"],
                            score["evidence"],
                            score["evidence_page"],
                            score["confidence"],
                            json.dumps(score["missing_evidence"], ensure_ascii=False),
                        ),
                    )
        connection.executemany(
            """INSERT INTO supplier_documents
               (rfp_run_id,supplier_name,original_filename,sha256,page_count,
                extraction_status,extraction_warnings_json)
               VALUES(?,?,?,?,?,?,?)""",
            [
                (
                    run["rfp_run_id"],
                    item["supplier_name"],
                    item["original_filename"],
                    item["sha256"],
                    item.get("page_count"),
                    item["extraction_status"],
                    json.dumps(item.get("warnings", []), ensure_ascii=False),
                )
                for item in documents
            ],
        )


def list_runs(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in connection.execute(
            "SELECT * FROM rfp_runs ORDER BY created_at DESC"
        ).fetchall()
    ]


def load_run(connection: sqlite3.Connection, run_id: str) -> dict[str, Any]:
    run_row = connection.execute(
        "SELECT * FROM rfp_runs WHERE rfp_run_id=?", (run_id,)
    ).fetchone()
    if run_row is None:
        raise ValueError(f"Run not found: {run_id}")
    run = dict(run_row)
    run["criteria_snapshot"] = json.loads(run.pop("criteria_snapshot_json"))
    run["suppliers"] = []
    rows = connection.execute(
        "SELECT * FROM supplier_results WHERE rfp_run_id=? ORDER BY technical_rank, supplier_name",
        (run_id,),
    ).fetchall()
    for result_row in rows:
        result = dict(result_row)
        result["result_json"] = json.loads(result["result_json"])
        result["warnings"] = json.loads(result.pop("warnings_json"))
        result["gates"] = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM eligibility_gates WHERE result_id=? ORDER BY gate_id",
                (result["result_id"],),
            ).fetchall()
        ]
        result["gate_history"] = [
            dict(row)
            for row in connection.execute(
                """SELECT * FROM gate_audit WHERE result_id=?
                   ORDER BY changed_at, audit_id""",
                (result["result_id"],),
            ).fetchall()
        ]
        result["criterion_results"] = [
            {
                **dict(row),
                "missing_evidence": json.loads(row["missing_evidence_json"]),
            }
            for row in connection.execute(
                "SELECT * FROM criterion_results WHERE result_id=? ORDER BY rowid",
                (result["result_id"],),
            ).fetchall()
        ]
        run["suppliers"].append(result)
    run["documents"] = [
        {
            **dict(row),
            "warnings": json.loads(row["extraction_warnings_json"]),
        }
        for row in connection.execute(
            "SELECT * FROM supplier_documents WHERE rfp_run_id=? ORDER BY supplier_name",
            (run_id,),
        ).fetchall()
    ]
    return run


def update_gate(
    connection: sqlite3.Connection,
    result_id: int,
    gate_id: str,
    status: str,
    rationale: str,
    reviewer: str,
) -> None:
    if status not in {"PASS", "FAIL", "PENDING_VERIFICATION"}:
        raise ValueError("Unsupported gate status.")
    with connection:
        previous = connection.execute(
            """SELECT status,rationale FROM eligibility_gates
               WHERE result_id=? AND gate_id=?""",
            (result_id, gate_id),
        ).fetchone()
        if previous is None:
            raise ValueError("Verification gate was not found.")
        changed_at = datetime.now(timezone.utc).isoformat()
        connection.execute(
            """INSERT INTO gate_audit
               (result_id,gate_id,changed_at,reviewer,previous_status,new_status,
                previous_rationale,new_rationale)
               VALUES(?,?,?,?,?,?,?,?)""",
            (
                result_id,
                gate_id,
                changed_at,
                reviewer.strip(),
                previous["status"],
                status,
                previous["rationale"],
                rationale.strip(),
            ),
        )
        connection.execute(
            """UPDATE eligibility_gates SET status=?,rationale=?,reviewer=?,reviewed_at=?
               WHERE result_id=? AND gate_id=?""",
            (
                status,
                rationale.strip(),
                reviewer.strip(),
                changed_at,
                result_id,
                gate_id,
            ),
        )
        gates = [
            dict(row)
            for row in connection.execute(
                "SELECT status FROM eligibility_gates WHERE result_id=?", (result_id,)
            ).fetchall()
        ]
        result = connection.execute(
            """SELECT absolute_score,rfp_run_id,evaluation_status
               FROM supplier_results WHERE result_id=?""",
            (result_id,),
        ).fetchone()
        if result is None:
            raise ValueError("Supplier result was not found.")
        minimum = connection.execute(
            "SELECT minimum_score FROM rfp_runs WHERE rfp_run_id=?",
            (result["rfp_run_id"],),
        ).fetchone()[0]
        statuses = {row["status"] for row in gates}
        if result["evaluation_status"] == "EVALUATION_ERROR":
            eligibility, shortlist = "NOT_RANKED", "NOT_RANKED"
        elif "FAIL" in statuses:
            eligibility, shortlist = "NOT_ELIGIBLE", "EXCLUDED_BY_MANDATORY_GATE"
        elif "PENDING_VERIFICATION" in statuses:
            eligibility, shortlist = "PENDING_VERIFICATION", "PENDING_MANDATORY_REVIEW"
        elif (result["absolute_score"] or 0) >= minimum:
            eligibility, shortlist = "ELIGIBLE_FOR_REVIEW", "SHORTLIST_CANDIDATE"
        else:
            eligibility, shortlist = "ELIGIBLE_FOR_REVIEW", "BELOW_SCORE_THRESHOLD"
        connection.execute(
            """UPDATE supplier_results SET eligibility_status=?,shortlist_status=?
               WHERE result_id=?""",
            (eligibility, shortlist, result_id),
        )
