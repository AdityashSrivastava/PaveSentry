"""
Defect Liability Period (DLP) Warranty Watchdog Engine.
Enforces 3-Year & 2-Year PWD Contractor Warranty Clauses conforming to:
- CPWD General Conditions of Contract (GCC) Clause 17 (Rectification of Defects during DLP)
- CPWD GCC Clause 2 (Compensation for Delay and Non-Rectification)
- Delhi PWD Maintenance Manual & CSIR-CRRI Quality Guidelines
"""
import uuid
from datetime import datetime, timedelta
from typing import Any

from database.db_manager import DB_PATH, get_connection

RECTIFICATION_WINDOW_HOURS = 48  # Mandatory 48-hour notice window under CPWD Clause 17
BASE_DEFECT_PENALTY_INR = 25000.0  # Base penalty per verified recurring pothole during DLP
ADMIN_SURCHARGE_PCT = 0.25  # 25% administrative & departmental supervision surcharge

def inspect_pothole_for_dlp_breach(
    pothole_report: dict[str, Any],
    db_path=DB_PATH
) -> dict[str, Any] | None:
    """
    Checks if a newly reported or AI-verified pothole falls within a corridor
    under an active Contractor Defect Liability Period (DLP) warranty.
    If true, automatically registers a DLP breach incident and generates a Show Cause Notice.
    """
    segment_id = pothole_report.get("segment_id")
    road_name = pothole_report.get("road_name") or ""
    lat = pothole_report.get("latitude")
    lon = pothole_report.get("longitude")

    conn = get_connection(db_path)
    cursor = conn.cursor()

    # Find active DLP work order for this segment or road corridor
    cursor.execute("""
        SELECT * FROM work_orders 
        WHERE (segment_id = ? OR road_name = ? OR (length(?) > 5 AND road_name LIKE ?)) 
          AND stage = 'Audited & Closed' 
          AND dlp_status IN ('Active Warranty', 'Breach Flagged (Penalty Pending)')
        ORDER BY completion_date DESC LIMIT 1
    """, (segment_id, road_name, road_name, f"%{road_name[:18]}%"))
    wo = cursor.fetchone()

    if not wo:
        conn.close()
        return None

    wo = dict(wo)

    # Check if current date is within DLP window
    now = datetime.utcnow()
    dlp_end_dt = None
    if wo.get("dlp_end_date"):
        try:
            dlp_end_dt = datetime.fromisoformat(wo["dlp_end_date"])
        except Exception:
            pass

    if dlp_end_dt and now > dlp_end_dt:
        # Warranty already expired
        conn.close()
        return None

    # DLP Breach Confirmed!
    severity = pothole_report.get("severity") or "Severe"
    area_cm2 = pothole_report.get("cv_area_cm2") or 2500.0
    
    # Calculate penalty according to severity and area
    scale_factor = 1.5 if "severe" in severity.lower() or area_cm2 > 3000 else 1.0
    direct_penalty = BASE_DEFECT_PENALTY_INR * scale_factor
    admin_surcharge = direct_penalty * ADMIN_SURCHARGE_PCT
    total_penalty = round(direct_penalty + admin_surcharge, 2)

    incident_id = f"DLP-INC-{uuid.uuid4().hex[:8].upper()}"
    pothole_id = pothole_report.get("report_id") or "UNKNOWN-POT"
    defect_date = pothole_report.get("created_at") or now.isoformat()
    rectification_deadline = (now + timedelta(hours=RECTIFICATION_WINDOW_HOURS)).isoformat()
    clause_applied = "CPWD GCC Clause 17 (DLP Rectification Failure) & Clause 2 (Liquidated Damages)"

    show_cause_notice = (
        f"OFFICIAL SHOW CAUSE NOTICE UNDER CPWD GCC CLAUSE 17\n"
        f"To: {wo['contractor_name']} (Contractor)\n"
        f"Work Order Reference: {wo['work_order_id']} | Tender Code: {wo['tender_code']}\n"
        f"Corridor: {wo['road_name']} ({wo['pwd_division']})\n"
        f"Defect Liability Period: {wo.get('dlp_months', 36)} Months Mandatory Warranty\n\n"
        f"SUBJECT: RECURRENCE OF ROAD DEFECT / POTHOLE DURING ACTIVE DLP WARRANTY\n"
        f"Notice is hereby served that an automated field survey / verified distress report has identified a "
        f"defect ({severity}, area ~{area_cm2:.1f} cm2) on the subject corridor executed under your contract.\n\n"
        f"In accordance with CPWD GCC Clause 17, you are directed to mobilize repair crews and rectify the "
        f"defect within {RECTIFICATION_WINDOW_HOURS} hours (Deadline: {rectification_deadline[:16]}).\n"
        f"Failure to rectify within the stipulated window shall result in an immediate departmental penalty of "
        f"₹{total_penalty:,.2f} being deducted from your Security Deposit / Performance Bank Guarantee (PBG), "
        f"with departmental execution at your risk and cost."
    )

    # Insert DLP Incident
    cursor.execute("""
        INSERT INTO dlp_warranty_incidents (
            incident_id, work_order_id, segment_id, pothole_report_id, contractor_name,
            defect_date, severity, rectification_deadline, penalty_amount_inr,
            clause_applied, status, show_cause_notice_text, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Notice Issued', ?, ?)
    """, (
        incident_id,
        wo["work_order_id"],
        segment_id,
        pothole_id,
        wo["contractor_name"],
        defect_date,
        severity,
        rectification_deadline,
        total_penalty,
        clause_applied,
        show_cause_notice,
        now.isoformat()
    ))

    # Update work order dlp_status
    cursor.execute("""
        UPDATE work_orders 
        SET dlp_status = 'Breach Flagged (Penalty Pending)', updated_at = ?
        WHERE work_order_id = ?
    """, (now.isoformat(), wo["work_order_id"]))

    conn.commit()
    conn.close()

    return {
        "incident_id": incident_id,
        "work_order_id": wo["work_order_id"],
        "segment_id": segment_id,
        "road_name": wo["road_name"],
        "contractor_name": wo["contractor_name"],
        "penalty_amount_inr": total_penalty,
        "penalty_amount_formatted": f"₹{(total_penalty / 100000):.2f} L" if total_penalty >= 100000 else f"₹{total_penalty:,.2f}",
        "rectification_deadline": rectification_deadline,
        "clause_applied": clause_applied,
        "show_cause_notice": show_cause_notice
    }


def scan_all_open_potholes_for_dlp(db_path=DB_PATH) -> list[dict[str, Any]]:
    """
    Scans all open reported/verified potholes in the system against active DLP contracts.
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM pothole_reports 
        WHERE status IN ('Reported', 'Verified', 'Scheduled')
        ORDER BY created_at DESC
    """)
    reports = [dict(r) for r in cursor.fetchall()]
    conn.close()

    breaches = []
    for rep in reports:
        breach = inspect_pothole_for_dlp_breach(rep, db_path=db_path)
        if breach:
            breaches.append(breach)
    return breaches


def get_active_dlp_contracts(db_path=DB_PATH) -> list[dict[str, Any]]:
    """
    Retrieves all contractors and corridors currently covered under active Defect Liability Period warranties.
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            wo.work_order_id,
            wo.segment_id,
            wo.road_name,
            wo.city_zone,
            wo.pwd_division,
            wo.tender_code,
            wo.contractor_name,
            wo.contract_value_inr,
            wo.treatment_type,
            wo.dlp_months,
            wo.dlp_start_date,
            wo.dlp_end_date,
            wo.dlp_status,
            COUNT(inc.incident_id) as breach_count,
            COALESCE(SUM(inc.penalty_amount_inr), 0) as total_penalties_inr
        FROM work_orders wo
        LEFT JOIN dlp_warranty_incidents inc ON wo.work_order_id = inc.work_order_id
        WHERE wo.stage = 'Audited & Closed'
        GROUP BY wo.work_order_id
        ORDER BY wo.dlp_end_date ASC
    """)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    now = datetime.utcnow()
    contracts = []
    for r in rows:
        dlp_end = r.get("dlp_end_date")
        days_remaining = 0
        if dlp_end:
            try:
                dt_end = datetime.fromisoformat(dlp_end)
                days_remaining = max(0, (dt_end - now).days)
            except Exception:
                pass

        contracts.append({
            **r,
            "days_remaining": days_remaining,
            "contract_value_formatted": f"₹{(r['contract_value_inr'] / 10000000):.2f} Cr" if r['contract_value_inr'] >= 10000000 else f"₹{(r['contract_value_inr'] / 100000):.2f} L",
            "total_penalties_formatted": f"₹{(r['total_penalties_inr'] / 100000):.2f} L" if r['total_penalties_inr'] > 0 else "₹0.00"
        })
    return contracts
