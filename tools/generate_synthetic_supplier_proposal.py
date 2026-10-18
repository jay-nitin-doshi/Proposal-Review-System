"""Generate a clearly fictional supplier proposal for tender-app testing."""

from __future__ import annotations

from pathlib import Path

import pymupdf


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "synthetic_calyxora_pharmaworks_proposal.pdf"
PAGE_WIDTH = 612
PAGE_HEIGHT = 792
NAVY = (0.055, 0.12, 0.22)
BLUE = (0.12, 0.36, 0.62)
TEAL = (0.0, 0.53, 0.53)
PALE = (0.93, 0.96, 0.98)
INK = (0.15, 0.20, 0.26)
MUTED = (0.38, 0.45, 0.52)
AMBER = (0.96, 0.72, 0.25)
WHITE = (1, 1, 1)


def add_page(
    document: pymupdf.Document,
    number: int,
    title: str,
    subtitle: str,
    sections: list[tuple[str, str]],
) -> pymupdf.Page:
    page = document.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    page.draw_rect(page.rect, color=WHITE, fill=WHITE)
    page.draw_rect(pymupdf.Rect(0, 0, PAGE_WIDTH, 12), color=NAVY, fill=NAVY)
    page.draw_circle((43, 42), 14, color=TEAL, fill=TEAL)
    page.draw_line((37, 42), (43, 36), color=WHITE, width=1.8)
    page.draw_line((43, 36), (49, 42), color=WHITE, width=1.8)
    page.draw_line((49, 42), (43, 48), color=WHITE, width=1.8)
    page.draw_line((43, 48), (37, 42), color=WHITE, width=1.8)
    page.insert_text((68, 39), "CALYXORA  /  PHARMAWORKS", fontsize=9, fontname="hebo", color=NAVY)
    page.insert_text((425, 39), "SYNTHETIC TENDER RESPONSE", fontsize=7, fontname="hebo", color=TEAL)
    page.draw_line((42, 60), (570, 60), color=(0.83, 0.87, 0.91), width=0.7)

    page.insert_text((48, 98), title, fontsize=23, fontname="hebo", color=NAVY)
    page.insert_textbox(
        pymupdf.Rect(49, 108, 561, 133),
        subtitle,
        fontsize=9.2,
        fontname="helv",
        color=MUTED,
        lineheight=1.18,
    )

    y = 151
    for heading, paragraph in sections:
        page.insert_text((50, y), heading.upper(), fontsize=9.4, fontname="hebo", color=BLUE)
        y += 11
        body = page.insert_textbox(
            pymupdf.Rect(51, y, 560, 740),
            paragraph,
            fontsize=9.15,
            fontname="helv",
            color=INK,
            lineheight=1.22,
        )
        if body < 0:
            raise ValueError(
                f"Text overflow on page {number}, section {heading}: {body:.1f} points"
            )
        used_height = pymupdf.Rect(51, y, 560, 740).height - body
        y += used_height + 13
    if y > 738:
        raise ValueError(f"Page {number} body exceeds footer: y={y:.1f}")

    page.draw_rect(pymupdf.Rect(0, 754, PAGE_WIDTH, PAGE_HEIGHT), color=NAVY, fill=NAVY)
    page.insert_text(
        (45, 774),
        "FICTIONAL TRAINING ARTIFACT — NOT A REAL SUPPLIER, OFFER, LICENSE, OR CERTIFICATE",
        fontsize=6.7,
        fontname="hebo",
        color=WHITE,
    )
    page.insert_text((557, 774), f"{number:02d}", fontsize=8, fontname="hebo", color=WHITE)
    return page


def add_cover(document: pymupdf.Document) -> None:
    page = document.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    page.draw_rect(page.rect, color=NAVY, fill=NAVY)
    page.draw_rect(pymupdf.Rect(0, 0, PAGE_WIDTH, 16), color=TEAL, fill=TEAL)
    page.draw_circle((88, 92), 25, color=TEAL, fill=TEAL)
    for start, end in [
        ((77, 92), (88, 81)),
        ((88, 81), (99, 92)),
        ((99, 92), (88, 103)),
        ((88, 103), (77, 92)),
    ]:
        page.draw_line(start, end, color=WHITE, width=3)

    page.insert_text((128, 84), "CALYXORA", fontsize=18, fontname="hebo", color=WHITE)
    page.insert_text((128, 105), "PHARMAWORKS  |  SYNTHETIC SUPPLIER", fontsize=8.5, fontname="hebo", color=(0.65, 0.83, 0.88))
    page.draw_line((64, 151), (548, 151), color=(0.3, 0.45, 0.59), width=1)
    page.insert_text((66, 222), "PARACETAMOL", fontsize=31, fontname="hebo", color=WHITE)
    page.insert_text((66, 263), "MANUFACTURING TENDER", fontsize=18, fontname="hebo", color=WHITE)
    page.insert_textbox(
        pymupdf.Rect(68, 286, 510, 343),
        "Illustrative proposal for contract manufacture and supply of immediate-release "
        "paracetamol 500 mg tablets",
        fontsize=12,
        fontname="helv",
        color=(0.83, 0.89, 0.94),
        lineheight=1.3,
    )
    page.draw_rect(
        pymupdf.Rect(66, 382, 546, 494),
        color=(0.12, 0.22, 0.34),
        fill=(0.12, 0.22, 0.34),
        radius=0.08,
    )
    cover_fields = [
        ("Submitted to", "Tender Evaluation Committee"),
        ("Tender scope", "Paracetamol 500 mg immediate-release tablets"),
        ("Synthetic submission date", "18 October 2026"),
        ("Offer validity", "90 days from synthetic submission date"),
    ]
    y = 407
    for label, value in cover_fields:
        page.insert_text((84, y), label.upper(), fontsize=7, fontname="hebo", color=(0.62, 0.75, 0.85))
        page.insert_text((246, y), value, fontsize=9, fontname="helv", color=WHITE)
        y += 23
    page.draw_rect(
        pymupdf.Rect(66, 535, 546, 661),
        color=(1.0, 0.88, 0.62),
        fill=(1.0, 0.88, 0.62),
        radius=0.08,
    )
    page.insert_text((84, 560), "DEMO DATA — NOT FOR PROCUREMENT USE", fontsize=11, fontname="hebo", color=NAVY)
    disclaimer = (
        "Calyxora PharmaWorks Ltd. and every site, person, number, quality record, "
        "license reference, audit, reference customer, price, and performance statement "
        "in this PDF are invented solely to test a software prototype. No real company, "
        "facility, authorization, certificate, or supporting record is represented. "
        "This PDF is not a real bid and must never be submitted to a real tender."
    )
    page.insert_textbox(
        pymupdf.Rect(84, 575, 527, 647),
        disclaimer,
        fontsize=9,
        fontname="helv",
        color=NAVY,
        lineheight=1.25,
    )
    page.insert_text((66, 716), "CONFIDENTIALITY SIMULATION  |  VERSION 1.0  |  12-PAGE DEMO DOSSIER", fontsize=7, fontname="hebo", color=(0.69, 0.79, 0.86))
    page.insert_text((66, 774), "SYNTHETIC TRAINING ARTIFACT — NOT A REAL SUPPLIER OFFER", fontsize=7, fontname="hebo", color=WHITE)
    page.insert_text((557, 774), "01", fontsize=8, fontname="hebo", color=WHITE)


PAGES = [
    (
        "Executive proposal",
        "A concise, traceable offer designed around the eight illustrative evaluation criteria.",
        [
            (
                "Company profile and scope",
                "Calyxora PharmaWorks Ltd. is an invented, fictional contract-manufacturing company created for tender-app testing. This synthetic response offers development transfer, manufacture, testing, packaging, release documentation, and shipment planning for paracetamol 500 mg immediate-release tablets at the fictional Meridian Works site. All quantities, controls, authorizations, performance figures, references, and exhibits below are invented and do not describe a real company.",
            ),
            (
                "Offer at a glance",
                "Proposed annual allocation: 48 million saleable tablets, with a demonstrated-in-this-fictional-case line capability of 60 million tablets per year and 12 million tablets reserved as uncommitted contingency capacity. Standard lead time is 8 weeks after approved forecast and artwork; emergency recovery plan targets 4 weeks for an agreed partial quantity. Proposed commercial price is INR 0.78 per tablet for the precise scope on page 8, with no unlisted mandatory tooling or release-test fee.",
            ),
            (
                "Decision-ready evidence approach",
                "The dossier maps each criterion to named sections, page-cited evidence, an accountable owner, measurable operating targets, and open assumptions. The fictional company asserts that copies of its site authorization, inspection summary, quality-system index, validation summary, insurance summary, and reference letters are in the synthetic dossier register on page 11. These are descriptions in a training artifact—not authentic documents or independent proof. A real reviewer must obtain and verify original records.",
            ),
            (
                "Commitment and caveats",
                "No production or shipment would start before written scope approval, site and quality due diligence, technical transfer acceptance, an effective quality agreement, and purchase-order authorization. Prices, capacity, dates, customer references, licences, inspection history, quality metrics, and every other business fact in this offer are fictional. The prototype's score and gates are decision-support only; a high score does not establish GMP compliance, legal eligibility, or award readiness.",
            ),
        ],
    ),
    (
        "Manufacturing capability",
        "Criterion: Manufacturing capability & process control  |  Weight in sample rubric: 20%",
        [
            (
                "Site and dedicated process",
                "The fictional Meridian Works site is described as a segregated oral-solid-dose facility with a dedicated paracetamol dispensing and compression campaign, controlled personnel/material flows, room-status controls, qualified dust extraction, and documented line clearance. The proposed process flow is receipt and sampling; dispensing; dry blending; lubrication; compression; in-process control; dedusting and metal detection; blister packing; finished-product testing; quality-unit disposition. A material genealogy links each finished lot to supplier lots, batch records, equipment, operators, in-process results, and packaging components.",
            ),
            (
                "Equipment, control strategy, and capacity",
                "The fictional equipment train comprises two contained dispensing booths, a validated bin blender, rotary press, deduster, calibrated metal detector, and two blister lines. Nominal rated capacity is 60 million tablets per year at the stated product configuration; the 48-million annual offer uses 80% of that capacity, leaving 12 million uncommitted tablets per year. Capacity assumptions include a 250-day schedule, two shifts, planned maintenance, yield allowance, and current product mix. Lot size is 0.5–1.0 million tablets, subject to process validation and approved batch size.",
            ),
            (
                "Process control and contamination prevention",
                "Critical controls include verified dispensing reconciliation; blend uniformity sampling; lubrication-time limits; compression force, tablet weight, thickness, hardness, and friability checks; deduster and metal-detector challenge checks; calibrated instruments; line clearance; status labeling; reconciliation of printed components; and independent batch-record review. Cleaning procedures define worst-case residue limits, swab/rinse locations, dirty/clean hold times, campaign boundaries, and documented release by trained personnel. Any unplanned intervention is recorded with material, equipment, operator, time, reason, and quality assessment.",
            ),
            (
                "Validation, traceability, and evidence",
                "Before commercial manufacture the fictional site commits to approved process-performance qualification, cleaning validation, equipment qualification, computerized-system validation where applicable, and validated analytical methods. A continued-process-verification plan trends critical process parameters and attributes by lot and triggers documented investigation at alert/action limits. Synthetic dossier references: MFG-01 facility and flow diagram; MFG-02 equipment/maintenance register; VAL-01 process-validation summary; CLN-01 cleaning-validation matrix; TRC-01 sample genealogy and batch-record index. These references are fictional and require original-document review.",
            ),
        ],
    ),
    (
        "Quality system and product quality",
        "Criterion: GMP, quality system & product quality  |  Weight in sample rubric: 20%",
        [
            (
                "Independent quality authority",
                "The fictional Quality Unit is organizationally independent of manufacturing scheduling and commercial sales and has authority to stop production, quarantine material, reject a batch, and block shipment. The proposed governance model uses controlled procedures, training qualification, document control, supplier qualification, calibration, preventive maintenance, environmental monitoring where applicable, good documentation practice, and periodic management review. Controlled records are retained under a documented schedule with role-based access and attributable, legible, contemporaneous, original, accurate, complete, consistent, enduring, and available data principles.",
            ),
            (
                "Deviations, CAPA, change control, and OOS",
                "All deviations and out-of-specification results receive a unique record, immediate containment, documented impact assessment, scientifically justified investigation, root-cause evaluation, corrective/preventive actions, effectiveness checks, and closure approval independent of the action owner. Proposed targets are: triage within one business day; critical containment immediately; investigation plan within five business days; and overdue actions escalated weekly. No result may be invalidated solely to obtain a passing retest. Changes affecting formulation, process, site, suppliers, methods, packaging, or computerized systems require prospective risk assessment, approval, qualification/validation, and customer notification or consent where contractually required.",
            ),
            (
                "Batch release, complaints, and recall readiness",
                "Each batch receives review of executed manufacturing and packaging records, deviations, laboratory data, reconciliation, labels, and release specifications by an authorized fictional Quality Unit representative. Product is not released by production staff or by automated score. Complaints are logged on receipt, risk-triaged within one business day, investigated with retained samples and distribution records, and reported to the customer under the proposed quality agreement. The fictional recall exercise target is a complete distribution-accountability report within four hours and a mock-recall reconciliation above 99.5% within one business day.",
            ),
            (
                "Synthetic quality evidence index",
                "Quality exhibits listed for reviewer inspection are QMS-01 controlled-document master index; QMS-02 training matrix; QMS-03 deviation/CAPA and OOS workflow; QMS-04 change-control form; QMS-05 batch-release checklist; QMS-06 data-integrity and audit-trail review procedure; QMS-07 complaint/recall simulation summary; and QMS-08 quality metrics dashboard with numerator, denominator, period, exclusions, and trend definitions. All exhibit identifiers and contents are fictional examples, not real records or independently verified evidence.",
            ),
        ],
    ),
    (
        "Regulatory readiness",
        "Criterion: Regulatory readiness & documentation  |  Weight in sample rubric: 15%",
        [
            (
                "Site-specific scope and authorization claim",
                "For this synthetic scenario, the fictional Meridian Works site dossier asserts an active oral-solid-dose manufacturing authorization identified as DEMO-MFG-2026-041, issued by the fictional Example State Medicines Authority, with a stated expiry of 31 December 2027. The fictional scope is non-sterile tablet manufacture and packaging. A tender reviewer must not treat this statement or identifier as a real licence; the fictional authority and authorization do not exist. The actual original site authorization, premises, legal entity, product scope, validity, conditions, and regulator source would all require direct verification.",
            ),
            (
                "Inspection, product dossier, and markets",
                "The synthetic response describes a fictional regulator inspection dated 14–18 April 2025, a closed-out observation register dated 30 June 2025, and an internal quality audit dated 12 February 2026. It asserts that no critical observation remains open, with closure evidence and effectiveness checks indexed in REG-02. The product dossier index identifies formula and process narrative, proposed finished-product specification, analytical-method summary, stability protocol and current data summary, packaging configuration, impurity-risk assessment, and change-notification route. These are fictional statements and must be checked against authoritative, current records for each target market.",
            ),
            (
                "Document control and submission support",
                "A regulatory coordinator is assigned as owner for controlled document requests, customer questionnaires, deficiency responses, and change notifications. The stated service target is acknowledgement within one business day and a complete standard document pack within five business days, subject to confidentiality and permitted disclosure. A document-transmittal register records document title, identifier, revision, effective date, owner, recipient, secure transfer method, and superseded version. No regulatory approval or market authorization is claimed for a real product or jurisdiction.",
            ),
            (
                "Fictional verification package",
                "Synthetic references: REG-01 site authorization index; REG-02 inspection and observation-closeout index; REG-03 product dossier table of contents; REG-04 target-market requirements matrix; REG-05 change-notification procedure; and REG-06 document-request service log. The references illustrate what a complete response would identify. They do not substitute for original, current certificates, regulator database checks, site audits, or legal advice.",
            ),
        ],
    ),
    (
        "Supply capacity and continuity",
        "Criterion: Supply capacity & business continuity  |  Weight in sample rubric: 10%",
        [
            (
                "Committed and available capacity",
                "The fictional offer reserves 48 million saleable tablets per contract year, scheduled at up to 4.0 million tablets per month after an agreed ramp. Stated qualified practical capacity is 60 million tablets per year at this product configuration; 12 million tablets are identified as uncommitted contingency capacity. These figures are synthetic and conditional on successful qualification, confirmed forecast, approved specifications, and material availability. Capacity planning distinguishes theoretical equipment rate from validated yield, planned maintenance, existing commitments, seasonal peaks, and batch-release time.",
            ),
            (
                "Lead time and service level",
                "Standard replenishment lead time is proposed at eight weeks from frozen forecast, approved artwork, and material availability. The fictional service objectives are at least 98% on-time-in-full delivery per quarter, at least 99.5% order-line documentation completeness, and notification of a foreseeable delay within one business day. A monthly supply review compares forecast, firm orders, available-to-promise quantity, raw/packaging material cover, batch status, release status, and shipment risk.",
            ),
            (
                "Sourcing and shortage response",
                "Each critical input has an approved-source list, incoming specification, supplier change-notification requirement, risk tier, lead-time profile, and alternative-source qualification plan. No alternate source is introduced without customer impact review and required approval. Fictional safety-stock policy is eight weeks for the critical active ingredient and six weeks for primary packaging, subject to expiry, storage, and demand variability. In a disruption, the response team activates within four hours, prioritizes patient/customer allocations under an agreed rule, assesses qualified alternate capacity, and provides a dated recovery plan within two business days.",
            ),
            (
                "Business continuity and evidence",
                "The synthetic continuity plan covers utilities, equipment outage, cyber incident, critical staff absence, transport interruption, supplier failure, and site access restriction. It names primary and deputy owners, call tree, secure document backup, recovery-time objective of 72 hours for order-status systems, recovery-point objective of 24 hours for backed-up planning records, and annual tabletop exercise with tracked corrective actions. Fictional exhibits: SCM-01 capacity model; SCM-02 forecast/capacity reconciliation; SCM-03 critical-material risk register; SCM-04 continuity plan; and SCM-05 on-time-in-full definition and sample dashboard.",
            ),
        ],
    ),
    (
        "Implementation and technology transfer",
        "Criterion: Implementation & technology transfer  |  Weight in sample rubric: 10%",
        [
            (
                "Governance and accountable owners",
                "A fictional cross-functional team includes a named program manager, process-transfer lead, analytical lead, validation lead, Quality Unit approver, regulatory coordinator, supply planner, and customer escalation owner. The customer retains approval of product requirements, specification, analytical transfer acceptance, critical changes, validation protocol, and commercial release conditions. A weekly working meeting, fortnightly risk review, and monthly steering review maintain decision, action, assumption, and dependency logs.",
            ),
            (
                "Milestones and exit criteria",
                "Weeks 0–2: contract scope, confidentiality, document exchange, gap assessment, and quality-agreement alignment. Weeks 3–5: formulation/process package review, analytical method transfer protocol, raw-material and packaging gap closure, and draft control strategy. Weeks 6–8: equipment/process fit confirmation, training, engineering-batch plan, qualification protocols, and approved master documents. Weeks 9–12: engineering or demonstration lots, method transfer, deviation resolution, and readiness review. Weeks 13–16: process-performance qualification subject to approved protocol, cleaning-validation evidence, stability placement, and customer data review. Commercial start follows approved acceptance criteria and explicit written authorization; elapsed time is a planning estimate, not a guaranteed regulatory outcome.",
            ),
            (
                "Risk and change management",
                "The transfer risk register tracks formulation/process knowledge gaps, analytical-method differences, equipment scale, raw-material variability, impurity risks, packaging compatibility, data transfer, supply lead times, and authorization dependencies. Each risk has probability, impact, owner, mitigation, due date, trigger, residual rating, and escalation route. A change-control record is required for scope, site, specification, formula, process, method, supplier, equipment, packaging, or planned production schedule changes. Schedule variance greater than five business days is escalated with recovery options and an impact assessment.",
            ),
            (
                "Acceptance and handover",
                "Transfer completion requires approved protocols and reports, trained personnel, reconciled material genealogy, acceptable process and analytical results against pre-agreed criteria, resolved critical deviations, completed document set, approved stability commitments, and signed Quality Unit/customer readiness record. The customer owns the decision to accept transfer and authorize routine production. Synthetic exhibits: PM-01 integrated schedule; PM-02 RACI; PM-03 risk/dependency log; PM-04 method-transfer protocol outline; and PM-05 transfer acceptance checklist.",
            ),
        ],
    ),
    (
        "Commercial offer and price transparency",
        "Criterion: Commercial value & price transparency  |  Weight in sample rubric: 15%",
        [
            (
                "Normalized comparison basis",
                "All amounts on this page are invented training values, not a real quotation. The comparison basis is one saleable immediate-release paracetamol 500 mg tablet, same agreed specification, 48 million tablets per year, 10-tablet blister with printed carton, routine finished-product testing and quality-unit batch release, delivered to one named buyer warehouse in Mumbai, India, INR, inclusive of assumed applicable indirect tax for this illustration, one-year contract, and standard forecast/order terms. A real tender must replace and validate each basis assumption, tax treatment, freight, and delivery point.",
            ),
            (
                "Illustrative line-item price (INR per saleable tablet)",
                "Manufacturing conversion and routine yield allowance: INR 0.43. Active ingredient and excipients: INR 0.12. Blister, printed carton, and serialization-ready coding allowance: INR 0.10. Routine release testing and batch documentation: INR 0.04. Freight to the stated delivery point: INR 0.03. Tax allowance for this fictional comparison: INR 0.06. Total illustrative delivered price: INR 0.78 per tablet. Annual quantity: 48,000,000 tablets. Illustrative annual total: INR 37,440,000. The arithmetic is 48,000,000 × INR 0.78; figures are not a real market quote or tax opinion.",
            ),
            (
                "Included, excluded, and price controls",
                "Included: standard transfer support, routine testing, release documentation, agreed packaging, standard freight to the named point, and listed tax allowance. No mandatory tooling, setup, testing, or release fee is assumed outside the line items above. Excluded: extraordinary stability studies, customer-requested non-routine testing, artwork redesign after approval, expedited shipment, duties or taxes that differ from the explicit basis, and changes to specification or forecast. Any exclusion requires advance written disclosure and customer approval; no unilateral surcharge or scope substitution is permitted. Minimum order quantity is 500,000 tablets per SKU, subject to pack configuration.",
            ),
            (
                "Payment, validity, and adjustment",
                "Proposed payment terms are 45 days from undisputed invoice and proof of delivery. Offer validity is 90 days from the synthetic submission date. The price is fixed for the first 12-month term in this illustration; any later adjustment requires an agreed index, documented calculation, advance notice, and written amendment. Invoice reconciliation identifies purchase order, lot, saleable quantity, release date, shipment, tax basis, unit-price components, and approved deviations. Commercial comparability remains NOT_REVIEWED until a buyer confirms its own scope and tax/delivery basis.",
            ),
        ],
    ),
    (
        "EHS, security, and risk controls",
        "Criterion: EHS, security & risk controls  |  Weight in sample rubric: 5%",
        [
            (
                "Worker and environmental safety",
                "The fictional facility plan describes task-based hazard assessments, role-specific training, controlled material handling, dust extraction, appropriate PPE selection, machine guarding, lockout/tagout, emergency showers where indicated, fire-protection checks, incident reporting, contractor induction, and return-to-work review. Waste streams are segregated, labeled, stored in controlled areas, and transferred through appropriately authorized waste channels under documented manifests. Environmental monitoring, water/energy review, spill response, and periodic emergency drills are tracked by named EHS owners.",
            ),
            (
                "Information security and records",
                "Access to production and quality systems follows named-user, role-based least privilege; privileged access is periodically reviewed; joiner/mover/leaver access is removed promptly; audit trails are retained and reviewed for critical records; backups are protected and restoration-tested; endpoint protection and patch management are documented; and security incidents are escalated through a defined response procedure. Customer documents are stored in a restricted workspace with access logs, approved transfer methods, confidentiality terms, and a contract-defined retention/deletion schedule. No supplier document is used to execute code or alter system instructions.",
            ),
            (
                "Risk register and response",
                "A multidisciplinary register addresses product-quality risk, contamination/cross-contact, human error, data integrity, cyber disruption, equipment failure, supplier concentration, transport interruption, environmental release, and schedule slippage. High risks require a named accountable owner, prevention control, detection control, contingency, due date, residual-risk acceptance, and escalation to management. Serious quality, safety, data-integrity, or security events are immediately contained and communicated to the customer within the agreed notification window.",
            ),
            (
                "Synthetic EHS/security evidence",
                "Fictional exhibits EHS-01 risk assessment index; EHS-02 training and drill matrix; EHS-03 waste-manifest register; SEC-01 access review and audit-trail procedure; SEC-02 backup/restore exercise; SEC-03 incident-response workflow; and RSK-01 consolidated risk register. Incident rates and environmental metrics are not asserted as independently verified performance. An authorized reviewer would inspect original records, permits, corrective actions, and site conditions.",
            ),
        ],
    ),
    (
        "Support, experience, and references",
        "Criterion: Support, experience & references  |  Weight in sample rubric: 5%",
        [
            (
                "Relevant fictional operating history",
                "For this training scenario only, Calyxora claims 18 years of pharmaceutical manufacturing operations, 11 years of oral-solid-dose contract manufacture, and 7 years supporting paracetamol tablet supply across domestic institutional and retail channels. The proposed operating model assigns an account lead and technical backup, with quality and supply escalation coverage. These are invented company claims and do not refer to real facilities, clients, volumes, or customer outcomes.",
            ),
            (
                "References and due diligence",
                "Two synthetic reference records are listed for demonstration: REF-A, an invented institutional buyer relationship from 2022–2025, and REF-B, an invented private-label customer relationship from 2023–2026. Each fictional record would identify an authorized reference contact, product scope, contract period, service metrics, complaint handling, and permission for direct verification. No real person or customer is named. A real evaluator must obtain consent, contact references through independently verified channels, and check conflicts or exclusions.",
            ),
            (
                "Support service levels",
                "Proposed service targets: critical product-quality or patient-safety concern acknowledged within 30 minutes and escalated immediately to Quality; urgent supply interruption acknowledged within two hours; standard technical or documentation query acknowledged within one business day; standard complete response within five business days; and complaint status update at least weekly while open. Recall and complaint contacts have primary and deputy coverage with after-hours escalation. Service-level clock, severity definitions, stop-clock rules, holidays, and remedies are subject to contract agreement.",
            ),
            (
                "Performance review and improvement",
                "Monthly reviews cover order fulfillment, forecast adherence, deviations, complaints, change notifications, documentation completeness, open CAPA, audit actions, and upcoming supply risks. Quarterly reviews evaluate trends, recurring causes, service-level attainment, and continuous-improvement commitments. Synthetic exhibits SUP-01 account escalation matrix; SUP-02 sample monthly scorecard definition; REF-A and REF-B reference-record templates; and SUP-03 complaint/recall contact tree. All records are fictional placeholders and require authentic evidence and independent reference checks.",
            ),
        ],
    ),
    (
        "Verification gates and commitment",
        "Five mandatory checks are addressed as supplier claims and document requests; reviewer decisions remain pending until independently verified.",
        [
            (
                "Gate 1 — current site-specific manufacturing licence",
                "Supplier statement: the fictional site authorization DEMO-MFG-2026-041 is asserted to cover non-sterile tablet manufacture through 31 December 2027. Requested verification: original authorization, issuing authority confirmation through an independently sourced official channel, legal entity/site address match, current validity, conditions, and product/process scope. This training PDF is not proof of the authorization.",
            ),
            (
                "Gate 2 — applicable GMP status and inspection disposition",
                "Supplier statement: a fictional inspection in April 2025 and closeout in June 2025 are described in REG-02, with no critical observation claimed open. Requested verification: regulator inspection records where available, complete observation and response set, independent audit findings, CAPA effectiveness evidence, and Quality approval. Nothing in this fictional narrative verifies GMP status.",
            ),
            (
                "Gate 3 — exact product scope and target-market requirements confirmed",
                "Supplier statement: proposed scope is 500 mg immediate-release tablets for the buyer-defined market. Requested verification: buyer quality/technical requirements, current target-market rules, formulation and specification fit, dossier needs, labeling, serialization, and any customer/product authorization requirements. Market approval is not claimed for a real product.",
            ),
            (
                "Gate 4 — no unresolved critical quality/data-integrity finding",
                "Supplier statement: the fictional Quality Unit reports no unresolved critical quality or data-integrity finding affecting this proposed scope as of the synthetic submission date. Requested verification: complete recent audit/inspection finding register, severity rationale, closure evidence, effectiveness checks, escalation disclosures, and direct Quality Unit interview. The statement is self-reported and must not be treated as a pass.",
            ),
            (
                "Gate 5 — quality agreement and audit rights",
                "Supplier commitment: execute a mutually agreed quality agreement before commercial manufacture, grant reasonable for-cause and planned audit access, provide records and samples under confidentiality safeguards, notify critical events and changes within agreed windows, support complaints/recalls, and define data retention and destruction. Requested verification: legal/quality review of the executed agreement, audit scope and rights, subcontractor controls, record access, and conflict resolution. No agreement is executed by this synthetic proposal.",
            ),
            (
                "Authorized reviewer disposition",
                "All five app gates should begin as PENDING_VERIFICATION. Only an authorized human reviewer may change each gate to PASS or FAIL after inspecting authentic, current evidence. This proposal is a test fixture designed to exercise the criteria and verification workflow, not to pre-populate gate decisions or guarantee an award.",
            ),
        ],
    ),
    (
        "Dossier index and assumptions",
        "Document map for testing evidence citations, missing-document checks, and proposal review workflow.",
        [
            (
                "Synthetic exhibit register",
                "MFG-01 facility and process-flow description (page 3); MFG-02 equipment and maintenance register (page 3); VAL-01 process-validation summary (page 3); CLN-01 cleaning-validation matrix (page 3); QMS-01 document master index and QMS-02 training matrix (page 4); QMS-03 deviations/CAPA/OOS workflow and QMS-06 data-integrity controls (page 4); REG-01 authorization index and REG-02 inspection-closeout index (page 5); SCM-01 capacity model, SCM-03 materials risk register, and SCM-04 continuity plan (page 6); PM-01 transfer schedule and PM-03 risk log (page 7); EHS-01 risk-assessment index and SEC-01 access/audit-trail procedure (page 9); REF-A/REF-B templates and SUP-01 escalation matrix (page 10).",
            ),
            (
                "What this index is and is not",
                "This index describes fictional evidence categories and locations in this PDF. It does not attach actual certificates, raw batch records, inspection reports, analytical results, insurance binders, customer contracts, or audit reports. All named records, identifiers, entities, metrics, and commitments are invented. For a real tender, obtain permitted original or certified copies, establish authenticity, confirm revision/currentness, protect confidential data, and record reviewer name, date, source, and conclusion.",
            ),
            (
                "Assumptions requiring buyer agreement",
                "The product is assumed to be a 500 mg immediate-release tablet; 48 million saleable units per year; one named delivery point in Mumbai; 10-tablet blister/carton configuration; buyer-approved specification, release limits, and target markets; INR price and stated tax allowance; standard forecast and quality agreement; and successful due diligence, transfer, validation, and written start authorization. Any mismatch may change feasibility, timeline, capacity, price, regulatory obligations, or acceptance criteria. No supplier may silently substitute or claim approval based on these assumptions.",
            ),
            (
                "Illustrative conclusion",
                "The fictional response is intentionally detailed across all eight evaluation criteria: manufacturing capability, quality/GMP, regulatory readiness, supply continuity, technology transfer, commercial transparency, EHS/security, and support/experience. It is designed to produce evidence-rich scorecards in a prototype, not to force a perfect score. The reviewer or configured LLM should score only the claims and evidence actually stated, record missing proof, and keep mandatory gates pending until human verification.",
            ),
        ],
    ),
]


def main() -> None:
    document = pymupdf.open()
    add_cover(document)
    for page_number, (title, subtitle, sections) in enumerate(PAGES, start=2):
        add_page(document, page_number, title, subtitle, sections)
    document.set_metadata(
        {
            "title": "Synthetic Paracetamol Manufacturing Tender Proposal — Calyxora PharmaWorks",
            "author": "Synthetic training artifact generator",
            "subject": "Fictional supplier proposal for tender-evaluation software testing",
            "keywords": "synthetic, fictional, training, paracetamol, proposal, not real",
            "creator": "Tender proposal demo generator",
        }
    )
    document.save(OUTPUT, garbage=4, deflate=True)
    document.close()
    print(f"Created {OUTPUT}")


if __name__ == "__main__":
    main()
