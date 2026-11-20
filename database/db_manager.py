import os
import sqlite3
import json
import uuid
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

DB_DIR = Path(__file__).resolve().parent
DB_PATH = DB_DIR / "road_maintenance.db"
SCHEMA_PATH = DB_DIR / "schema.sql"

def get_connection(db_path=DB_PATH):
    """Establishes and returns a connection to the SQLite database."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path=DB_PATH, schema_path=SCHEMA_PATH):
    """Initializes the database schema if tables do not exist and applies migrations."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    with open(schema_path, "r", encoding="utf-8") as f:
        schema_sql = f.read()
    cursor.executescript(schema_sql)

    # Dynamic migrations for Phase A CV columns & Citizen 311 Crowdsourcing
    columns_to_add = [
        ("cv_verified", "INTEGER DEFAULT 0"),
        ("cv_confidence", "REAL"),
        ("cv_area_cm2", "REAL"),
        ("cv_depth_category", "TEXT"),
        ("annotated_photo_filename", "TEXT"),
        ("boundary_coords", "TEXT"),
        ("citizen_ticket_id", "TEXT"),
        ("citizen_name", "TEXT"),
        ("citizen_mobile", "TEXT"),
        ("source_channel", "TEXT"),
        ("assigned_division", "TEXT"),
        ("assigned_engineer", "TEXT")
    ]
    for col_name, col_type in columns_to_add:
        try:
            cursor.execute(f"ALTER TABLE pothole_reports ADD COLUMN {col_name} {col_type}")
        except Exception:
            pass
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_potholes_ticket ON pothole_reports(citizen_ticket_id);")

    # Phase C: Seed initial work orders across Kanban stages if empty
    seed_kanban_work_orders(cursor)

    conn.commit()
    conn.close()

ZONE_TO_PWD_DIVISION = {
    "South Delhi": "PWD South Division (M-11)",
    "South East Delhi": "PWD South-East Division (M-12)",
    "South West Delhi": "PWD South-West Division (M-13)",
    "Central Delhi": "PWD Central Division (M-21)",
    "New Delhi (NDMC)": "NDMC Road Maintenance Division / PWD Special",
    "North Delhi": "PWD North Division (M-31)",
    "North West Delhi": "PWD North-West Division (M-32)",
    "East Delhi": "PWD East Division (M-41)",
    "North East Delhi": "PWD Shahdara & North-East Division (M-42)",
    "West Delhi": "PWD West Division (M-22)"
}

def get_pwd_division(city_zone: str) -> str:
    """Returns official Delhi PWD or NDMC division name for an administrative zone."""
    if not city_zone:
        return "PWD Delhi NCT Central Division"
    return ZONE_TO_PWD_DIVISION.get(city_zone, f"PWD Division ({city_zone})")

def resolve_zone_filter(zone: str):
    """
    Normalizes human-friendly administrative division names to corresponding list of city_zones.
    Handles 'East Delhi & Shahdara', 'NDMC', 'North West', etc.
    """
    if not zone or zone.strip().lower() in ["all", "all delhi zones", "all delhi"]:
        return None
    z = zone.strip()
    if z in ["East Delhi & Shahdara", "East Delhi and Shahdara", "East Delhi"]:
        return ["East Delhi", "North East Delhi"]
    if "NDMC" in z or "New Delhi" in z:
        return ["New Delhi (NDMC)"]
    if z in ["North West", "North West Delhi", "North-West"]:
        return ["North West Delhi"]
    if z in ["South Delhi"]:
        return ["South Delhi"]
    if z in ["South East Delhi", "South-East"]:
        return ["South East Delhi"]
    if z in ["South West Delhi", "South-West"]:
        return ["South West Delhi"]
    if z in ["Central Delhi"]:
        return ["Central Delhi"]
    if z in ["North Delhi"]:
        return ["North Delhi"]
    if z in ["West Delhi"]:
        return ["West Delhi"]
    return [z]

def get_all_segments(db_path=DB_PATH, zone=None):
    """
    Returns full details for all Delhi road segments including latest condition,
    traffic/weather metrics, prediction results, and official PWD divisions.
    Optionally filters by administrative zone/division.
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()
    
    resolved_zones = resolve_zone_filter(zone)
    where_clause = ""
    params = []
    if resolved_zones:
        placeholders = ",".join(["?"] * len(resolved_zones))
        where_clause = f"WHERE rs.city_zone IN ({placeholders})"
        params = resolved_zones

    query = f"""
    SELECT 
        rs.segment_id,
        rs.name,
        rs.road_type,
        rs.city_zone,
        rs.length_km,
        rs.surface_type,
        rs.lanes,
        rs.start_lat,
        rs.start_lon,
        rs.end_lat,
        rs.end_lon,
        rs.construction_year,
        rs.last_major_maintenance_year,
        rs.geometry_coords,
        cs.pci,
        cs.iri,
        cs.crack_density_pct,
        cs.rut_depth_mm,
        cs.pothole_count,
        cs.survey_date,
        tw.aadt,
        tw.heavy_vehicle_pct,
        tw.annual_rainfall_mm,
        tw.freeze_thaw_cycles,
        tw.avg_temperature_c,
        p.predicted_risk_level,
        p.pothole_probability,
        p.est_time_to_failure_months,
        p.est_preventive_cost_inr,
        p.est_reactive_cost_inr,
        p.priority_score,
        p.recommended_action,
        p.updated_at
    FROM road_segments rs
    LEFT JOIN (
        SELECT * FROM condition_surveys 
        WHERE survey_id IN (
            SELECT MAX(survey_id) FROM condition_surveys GROUP BY segment_id
        )
    ) cs ON rs.segment_id = cs.segment_id
    LEFT JOIN traffic_weather tw ON rs.segment_id = tw.segment_id
    LEFT JOIN predictions p ON rs.segment_id = p.segment_id
    {where_clause}
    ORDER BY rs.segment_id ASC
    """
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    results = []
    for row in rows:
        d = dict(row)
        d["pwd_division"] = get_pwd_division(d.get("city_zone"))
        results.append(d)
        
    return results

def get_segment_by_id(segment_id: str, db_path=DB_PATH):
    """Returns single road segment details by segment_id."""
    segs = get_all_segments(db_path=db_path)
    for s in segs:
        if s["segment_id"] == segment_id:
            return s
    return None

def get_segments_geojson(db_path=DB_PATH, zone=None):
    """
    Returns GeoJSON FeatureCollection representation of Delhi road segments for Leaflet.js maps.
    Uses authentic multi-point road curvature geometry_coords when available, falling back
    to 2-point coordinates otherwise.
    """
    segments = get_all_segments(db_path, zone=zone)
    features = []
    
    for seg in segments:
        coords = None
        if seg.get("geometry_coords"):
            try:
                coords = json.loads(seg["geometry_coords"])
            except Exception:
                pass
                
        if not coords or len(coords) < 2:
            coords = [
                [seg["start_lon"], seg["start_lat"]],
                [seg["end_lon"], seg["end_lat"]]
            ]
            
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": coords
            },
            "properties": seg
        }
        features.append(feature)
        
    return {
        "type": "FeatureCollection",
        "features": features
    }

def get_network_stats(db_path=DB_PATH, zone=None):
    """
    Returns aggregated summary metrics for the Delhi NCT road network or a specific
    administrative division/zone.
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()
    
    resolved_zones = resolve_zone_filter(zone)
    stats = {}
    stats["selected_zone"] = zone if zone else "all"
    
    if resolved_zones:
        placeholders = ",".join(["?"] * len(resolved_zones))
        
        cursor.execute(f"SELECT COUNT(*), SUM(length_km) FROM road_segments WHERE city_zone IN ({placeholders})", resolved_zones)
        row = cursor.fetchone()
        stats["total_segments"] = row[0] or 0
        stats["total_length_km"] = round(row[1] or 0, 2)
        
        cursor.execute(f"""
        SELECT 
            AVG(cs.pci),
            AVG(cs.iri),
            SUM(cs.pothole_count)
        FROM condition_surveys cs
        JOIN road_segments rs ON cs.segment_id = rs.segment_id
        WHERE cs.survey_id IN (
            SELECT MAX(survey_id) FROM condition_surveys GROUP BY segment_id
        )
        AND rs.city_zone IN ({placeholders})
        """, resolved_zones)
        row = cursor.fetchone()
        stats["avg_pci"] = round(row[0] or 0, 1)
        stats["avg_iri"] = round(row[1] or 0, 2)
        stats["total_active_potholes"] = row[2] or 0
        
        cursor.execute(f"""
        SELECT p.predicted_risk_level, COUNT(*) 
        FROM predictions p
        JOIN road_segments rs ON p.segment_id = rs.segment_id
        WHERE rs.city_zone IN ({placeholders})
        GROUP BY p.predicted_risk_level
        """, resolved_zones)
        risk_counts = {r[0]: r[1] for r in cursor.fetchall()}
        stats["risk_distribution"] = {
            "High": risk_counts.get("High", 0),
            "Medium": risk_counts.get("Medium", 0),
            "Low": risk_counts.get("Low", 0)
        }
        
        cursor.execute(f"""
        SELECT 
            SUM(p.est_preventive_cost_inr),
            SUM(p.est_reactive_cost_inr)
        FROM predictions p
        JOIN road_segments rs ON p.segment_id = rs.segment_id
        WHERE rs.city_zone IN ({placeholders})
        """, resolved_zones)
        row = cursor.fetchone()
        preventive_total = row[0] or 0
        reactive_total = row[1] or 0
    else:
        cursor.execute("SELECT COUNT(*), SUM(length_km) FROM road_segments")
        row = cursor.fetchone()
        stats["total_segments"] = row[0] or 0
        stats["total_length_km"] = round(row[1] or 0, 2)
        
        cursor.execute("""
        SELECT 
            AVG(cs.pci),
            AVG(cs.iri),
            SUM(cs.pothole_count)
        FROM condition_surveys cs
        WHERE cs.survey_id IN (
            SELECT MAX(survey_id) FROM condition_surveys GROUP BY segment_id
        )
        """)
        row = cursor.fetchone()
        stats["avg_pci"] = round(row[0] or 0, 1)
        stats["avg_iri"] = round(row[1] or 0, 2)
        stats["total_active_potholes"] = row[2] or 0
        
        cursor.execute("""
        SELECT predicted_risk_level, COUNT(*) 
        FROM predictions 
        GROUP BY predicted_risk_level
        """)
        risk_counts = {r[0]: r[1] for r in cursor.fetchall()}
        stats["risk_distribution"] = {
            "High": risk_counts.get("High", 0),
            "Medium": risk_counts.get("Medium", 0),
            "Low": risk_counts.get("Low", 0)
        }
        
        cursor.execute("""
        SELECT 
            SUM(est_preventive_cost_inr),
            SUM(est_reactive_cost_inr)
        FROM predictions
        """)
        row = cursor.fetchone()
        preventive_total = row[0] or 0
        reactive_total = row[1] or 0
    
    stats["total_preventive_backlog_inr"] = round(preventive_total, 2)
    stats["total_reactive_backlog_inr"] = round(reactive_total, 2)
    stats["potential_savings_inr"] = round(reactive_total - preventive_total, 2)
    
    # Format savings string in Lakhs or Crores
    savings = stats["potential_savings_inr"]
    if savings >= 10000000:
        stats["potential_savings_formatted"] = f"₹{(savings / 10000000):.2f} Crores"
    else:
        stats["potential_savings_formatted"] = f"₹{(savings / 100000):.2f} Lakhs"
        
    conn.close()
    return stats

# ==========================================================================
# PHASE 3: AUTHENTICATION, MULTI-TENANCY & FIELD SURVEY INGESTION HELPERS
# ==========================================================================

import math
import uuid
from datetime import datetime

def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Computes great-circle distance between two GPS coordinates in kilometers."""
    R = 6371.0 # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def find_nearest_segment(lat: float, lon: float, max_distance_km: float = 5.0, db_path=DB_PATH):
    """
    Finds the closest Delhi NCT road corridor to a given GPS coordinate.
    Calculates distance to both start/end coordinates and intermediate geometry points.
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT segment_id, name, road_type, city_zone, start_lat, start_lon, end_lat, end_lon, geometry_coords
        FROM road_segments
    """)
    rows = cursor.fetchall()
    conn.close()

    closest_segment = None
    min_dist = float("inf")

    for row in rows:
        seg_id = row["segment_id"]
        # Distance to start and end
        d_start = haversine_distance_km(lat, lon, row["start_lat"], row["start_lon"])
        d_end = haversine_distance_km(lat, lon, row["end_lat"], row["end_lon"])
        local_min = min(d_start, d_end)

        # If geometry coords exist, check points along the corridor
        if row["geometry_coords"]:
            try:
                coords = json.loads(row["geometry_coords"])
                for pt in coords:
                    if len(pt) >= 2:
                        # GeoJSON is [lon, lat]
                        d_pt = haversine_distance_km(lat, lon, pt[1], pt[0])
                        if d_pt < local_min:
                            local_min = d_pt
            except Exception:
                pass

        if local_min < min_dist:
            min_dist = local_min
            closest_segment = {
                "segment_id": seg_id,
                "name": row["name"],
                "road_type": row["road_type"],
                "city_zone": row["city_zone"],
                "distance_km": round(min_dist, 3),
                "distance_m": round(min_dist * 1000, 1)
            }

    if min_dist <= max_distance_km:
        return closest_segment
    return None

def get_user_by_email(email: str, db_path=DB_PATH):
    """Retrieves user record by email address (case-insensitive)."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE LOWER(email) = LOWER(?)", (email.strip(),))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_user_by_id(user_id: str, db_path=DB_PATH):
    """Retrieves user record by user_id."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def create_user(user_id: str, email: str, hashed_password: str, full_name: str, role: str, division: str, db_path=DB_PATH):
    """Creates a new user record in the users table."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    now_str = datetime.utcnow().isoformat()
    cursor.execute("""
        INSERT INTO users (user_id, email, hashed_password, full_name, role, division, created_at, last_login)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, email.strip().lower(), hashed_password, full_name.strip(), role.strip(), division.strip(), now_str, now_str))
    conn.commit()
    conn.close()
    return get_user_by_id(user_id, db_path=db_path)

def update_user_last_login(user_id: str, db_path=DB_PATH):
    """Updates the last_login timestamp for a user."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET last_login = ? WHERE user_id = ?", (datetime.utcnow().isoformat(), user_id))
    conn.commit()
    conn.close()

def create_pothole_report(report_data: dict, db_path=DB_PATH):
    """Inserts a new pothole report with optional photo attachment."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    report_id = report_data.get("report_id") or f"POT-2026-{uuid.uuid4().hex[:8].upper()}"
    now_str = datetime.utcnow().isoformat()
    
    cursor.execute("""
        INSERT INTO pothole_reports (
            report_id, segment_id, road_name, city_zone, latitude, longitude,
            severity, depth_mm, width_cm, photo_filename, reported_by,
            reporter_role, reporter_division, status, notes, created_at,
            cv_verified, cv_confidence, cv_area_cm2, cv_depth_category,
            annotated_photo_filename, boundary_coords
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        report_id,
        report_data.get("segment_id"),
        report_data.get("road_name", "Delhi NCT Corridor"),
        report_data.get("city_zone", "Central Delhi"),
        report_data["latitude"],
        report_data["longitude"],
        report_data.get("severity", "Medium"),
        report_data.get("depth_mm", 35.0),
        report_data.get("width_cm", 40.0),
        report_data.get("photo_filename"),
        report_data.get("reported_by", "engineer@pwd.delhi.gov.in"),
        report_data.get("reporter_role", "pwd_engineer"),
        report_data.get("reporter_division", "Delhi PWD"),
        report_data.get("status", "Reported"),
        report_data.get("notes", ""),
        now_str,
        report_data.get("cv_verified", 0),
        report_data.get("cv_confidence"),
        report_data.get("cv_area_cm2"),
        report_data.get("cv_depth_category"),
        report_data.get("annotated_photo_filename"),
        report_data.get("boundary_coords")
    ))

    # If associated with a segment, increment pothole count in condition_surveys
    seg_id = report_data.get("segment_id")
    if seg_id:
        cursor.execute("""
            UPDATE condition_surveys 
            SET pothole_count = pothole_count + 1
            WHERE survey_id = (
                SELECT MAX(survey_id) FROM condition_surveys WHERE segment_id = ?
            )
        """, (seg_id,))

    conn.commit()
    cursor.execute("SELECT * FROM pothole_reports WHERE report_id = ?", (report_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_pothole_reports(status: str = None, zone: str = None, limit: int = 100, db_path=DB_PATH):
    """Retrieves reported potholes with optional filtering."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    query = "SELECT * FROM pothole_reports WHERE 1=1"
    params = []

    if status and status.lower() != "all":
        query += " AND status = ?"
        params.append(status)
    if zone and zone.lower() != "all":
        query += " AND city_zone = ?"
        params.append(zone)

    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def update_pothole_status(report_id: str, new_status: str, db_path=DB_PATH):
    """Updates lifecycle status of a reported pothole."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("UPDATE pothole_reports SET status = ? WHERE report_id = ?", (new_status, report_id))
    conn.commit()
    cursor.execute("SELECT * FROM pothole_reports WHERE report_id = ?", (report_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def create_citizen_pothole_report(report_data: dict, db_path=DB_PATH):
    """Inserts crowdsourced pothole report with citizen tracking ticket and division routing."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    report_id = report_data.get("report_id") or f"POT-311-{uuid.uuid4().hex[:8].upper()}"
    ticket_id = report_data.get("citizen_ticket_id") or f"DEL-311-2026-{uuid.uuid4().hex[:6].upper()}"
    now_str = datetime.utcnow().isoformat()
    
    cursor.execute("""
        INSERT INTO pothole_reports (
            report_id, segment_id, road_name, city_zone, latitude, longitude,
            severity, depth_mm, width_cm, photo_filename, reported_by,
            reporter_role, reporter_division, status, notes, created_at,
            cv_verified, cv_confidence, cv_area_cm2, cv_depth_category,
            annotated_photo_filename, boundary_coords,
            citizen_ticket_id, citizen_name, citizen_mobile, source_channel,
            assigned_division, assigned_engineer
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        report_id,
        report_data.get("segment_id"),
        report_data.get("road_name", "Delhi NCR Road"),
        report_data.get("city_zone", "Central Delhi"),
        report_data["latitude"],
        report_data["longitude"],
        report_data.get("severity", "Medium"),
        report_data.get("depth_mm", 30.0),
        report_data.get("width_cm", 35.0),
        report_data.get("photo_filename"),
        report_data.get("citizen_mobile", "citizen_crowdsource"),
        "citizen",
        report_data.get("assigned_division", "Delhi PWD"),
        report_data.get("status", "Reported"),
        report_data.get("notes", "Crowdsourced report via Delhi 311 / WhatsApp PWA"),
        now_str,
        report_data.get("cv_verified", 0),
        report_data.get("cv_confidence"),
        report_data.get("cv_area_cm2"),
        report_data.get("cv_depth_category"),
        report_data.get("annotated_photo_filename"),
        report_data.get("boundary_coords"),
        ticket_id,
        report_data.get("citizen_name", "Delhi Resident"),
        report_data.get("citizen_mobile"),
        report_data.get("source_channel", "delhi_311"),
        report_data.get("assigned_division"),
        report_data.get("assigned_engineer")
    ))

    conn.commit()
    cursor.execute("SELECT * FROM pothole_reports WHERE report_id = ?", (report_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_pothole_by_ticket_id(ticket_id: str, db_path=DB_PATH):
    """Retrieves pothole report by citizen tracking ticket ID."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM pothole_reports 
        WHERE citizen_ticket_id = ? OR report_id = ?
        ORDER BY created_at DESC LIMIT 1
    """, (ticket_id, ticket_id))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def log_survey_upload(upload_info: dict, db_path=DB_PATH):
    """Logs an ingested survey file (ROMDAS CSV or ARRB GeoJSON)."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    upload_id = upload_info.get("upload_id") or f"SRV-2026-{uuid.uuid4().hex[:8].upper()}"
    now_str = datetime.utcnow().isoformat()
    cursor.execute("""
        INSERT INTO survey_uploads (
            upload_id, filename, file_format, uploaded_by, division,
            records_count, segments_affected, avg_iri, avg_pci, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        upload_id,
        upload_info.get("filename", "survey_data.csv"),
        upload_info.get("file_format", "CSV/ROMDAS"),
        upload_info.get("uploaded_by", "engineer@pwd.delhi.gov.in"),
        upload_info.get("division", "PWD Delhi"),
        upload_info.get("records_count", 0),
        upload_info.get("segments_affected", 0),
        upload_info.get("avg_iri", 0.0),
        upload_info.get("avg_pci", 0.0),
        now_str
    ))
    conn.commit()
    cursor.execute("SELECT * FROM survey_uploads WHERE upload_id = ?", (upload_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_survey_uploads(limit: int = 50, db_path=DB_PATH):
    """Retrieves log of recent field survey ingestion batches."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM survey_uploads ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def update_segment_condition(segment_id: str, survey_date: str, pci: float, iri: float, rut_depth_mm: float, crack_density_pct: float, pothole_count: int, db_path=DB_PATH):
    """Inserts a new official condition survey record for a segment."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO condition_surveys (segment_id, survey_date, pci, iri, crack_density_pct, rut_depth_mm, pothole_count)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (segment_id, survey_date, pci, iri, crack_density_pct, rut_depth_mm, pothole_count))
    conn.commit()
    conn.close()

def create_audit_validation(audit_info: dict, db_path=DB_PATH):
    """Creates a new CSIR-CRRI audit validation record for a road segment."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    audit_id = audit_info.get("audit_id") or f"AUD-2026-{uuid.uuid4().hex[:8].upper()}"
    now_str = datetime.utcnow().isoformat()
    cursor.execute("""
        INSERT INTO audit_validations (
            audit_id, segment_id, auditor_name, auditor_email, compliance_status,
            measured_iri, measured_pci, certificate_code, audit_notes, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        audit_id,
        audit_info["segment_id"],
        audit_info.get("auditor_name", "Dr. CSIR-CRRI Auditor"),
        audit_info.get("auditor_email", "auditor@crri.delhi.res.in"),
        audit_info.get("compliance_status", "Compliant with IRC:82"),
        audit_info["measured_iri"],
        audit_info["measured_pci"],
        audit_info.get("certificate_code", f"CRRI-NCT-2026-{uuid.uuid4().hex[:6].upper()}"),
        audit_info.get("audit_notes", ""),
        now_str
    ))
    conn.commit()
    cursor.execute("SELECT * FROM audit_validations WHERE audit_id = ?", (audit_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_audit_validations(segment_id: str = None, limit: int = 50, db_path=DB_PATH):
    """Retrieves recent CSIR-CRRI audit validation records."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    if segment_id:
        cursor.execute("SELECT * FROM audit_validations WHERE segment_id = ? ORDER BY created_at DESC LIMIT ?", (segment_id, limit))
    else:
        cursor.execute("SELECT * FROM audit_validations ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

# ==========================================================================
# PHASE C: CONTRACTOR SLA & WORK ORDER LIFECYCLE KANBAN & DLP WARRANTY ENGINE
# ==========================================================================

def seed_kanban_work_orders(cursor):
    """Seeds authentic Delhi PWD contractor work orders across all 5 Kanban stages if table is empty."""
    try:
        cursor.execute("SELECT COUNT(*) FROM work_orders")
        row = cursor.fetchone()
        if row and row[0] > 0:
            return  # Already populated
    except Exception:
        return

    now = datetime.utcnow()
    seeds = [
        {
            "work_order_id": "WO-2026-NCT-1001",
            "segment_id": "DL-PW-0001",
            "road_name": "Mahatma Gandhi Ring Road (Inner Ring Road)",
            "city_zone": "Central Delhi",
            "pwd_division": "PWD Central Division (M-21)",
            "tender_code": "NIT-PWD-2026-M21-088",
            "contractor_name": "Larsen & Toubro Ltd (Infrastructure Div)",
            "contractor_contact": "infra.delhi@lntecc.com",
            "contract_value_inr": 42000000.0,
            "stage": "Under Repair",
            "treatment_type": "Full Reconstruction & Sub-base Work (IRC:37)",
            "priority_level": "Critical",
            "sla_target_days": 60,
            "sla_deadline": (now + timedelta(days=22)).isoformat(),
            "sla_status": "On Track",
            "completion_date": None,
            "dlp_months": 36,
            "dlp_start_date": None,
            "dlp_end_date": None,
            "dlp_status": "Pending Completion",
            "notes": "Sensor paver mobilization complete. DBM 75mm base compaction underway at Ch. 2.4km."
        },
        {
            "work_order_id": "WO-2026-NCT-1002",
            "segment_id": "DL-PW-0002",
            "road_name": "Outer Ring Road (NH-44 Stretch)",
            "city_zone": "South Delhi",
            "pwd_division": "PWD South Division (M-11)",
            "tender_code": "NIT-PWD-2026-M11-042",
            "contractor_name": "Dilip Buildcon Ltd",
            "contractor_contact": "delhi.projects@dilipbuildcon.com",
            "contract_value_inr": 29000000.0,
            "stage": "Tender Issued",
            "treatment_type": "Bituminous Concrete (BC) Mill & Overlay (IRC:82)",
            "priority_level": "High",
            "sla_target_days": 30,
            "sla_deadline": (now + timedelta(days=12)).isoformat(),
            "sla_status": "On Track",
            "completion_date": None,
            "dlp_months": 36,
            "dlp_start_date": None,
            "dlp_end_date": None,
            "dlp_status": "Pending Completion",
            "notes": "e-Tender technical bids evaluated; LOA issued to contractor. Traffic diversion NOC pending."
        },
        {
            "work_order_id": "WO-2026-NCT-1003",
            "segment_id": "DL-PW-0004",
            "road_name": "Vikas Marg (ITO to Preet Vihar)",
            "city_zone": "East Delhi",
            "pwd_division": "PWD East Division (M-41)",
            "tender_code": "NIT-PWD-2026-M41-019",
            "contractor_name": "NKC Projects Pvt Ltd",
            "contractor_contact": "works@nkcprojects.com",
            "contract_value_inr": 31000000.0,
            "stage": "Inspected",
            "treatment_type": "Full Reconstruction & Sub-base Work (IRC:37)",
            "priority_level": "High",
            "sla_target_days": 14,
            "sla_deadline": (now + timedelta(days=2)).isoformat(),
            "sla_status": "Approaching Breach",
            "completion_date": None,
            "dlp_months": 36,
            "dlp_start_date": None,
            "dlp_end_date": None,
            "dlp_status": "Pending Completion",
            "notes": "Field engineer inspection logged severe base saturation. Detailed estimate sent for Chief Engineer approval."
        },
        {
            "work_order_id": "WO-2026-NCT-1004",
            "segment_id": "DL-PW-0005",
            "road_name": "Mathura Road (Ashram to Badarpur)",
            "city_zone": "South East Delhi",
            "pwd_division": "PWD South-East Division (M-12)",
            "tender_code": "NIT-PWD-2026-M12-076",
            "contractor_name": "Gawar Construction Ltd",
            "contractor_contact": "tenders@gawar.in",
            "contract_value_inr": 35000000.0,
            "stage": "Reported",
            "treatment_type": "Preventive Micro-Surfacing & Slurry Seal (IRC:SP:81)",
            "priority_level": "Medium",
            "sla_target_days": 7,
            "sla_deadline": (now + timedelta(days=4)).isoformat(),
            "sla_status": "On Track",
            "completion_date": None,
            "dlp_months": 24,
            "dlp_start_date": None,
            "dlp_end_date": None,
            "dlp_status": "Pending Completion",
            "notes": "AI camera detection flagged initial ravelling and friction loss. Site verification scheduled."
        },
        {
            "work_order_id": "WO-2026-NCT-1005",
            "segment_id": "DL-PW-0003",
            "road_name": "Barapullah Elevated Corridor",
            "city_zone": "South East Delhi",
            "pwd_division": "PWD South-East Division (M-12)",
            "tender_code": "NIT-PWD-2025-M12-031",
            "contractor_name": "HCC Delhi Paving Ltd",
            "contractor_contact": "projects.delhi@hccindia.com",
            "contract_value_inr": 8500000.0,
            "stage": "Audited & Closed",
            "treatment_type": "Routine Inspection & Monsoon Drain Clearance",
            "priority_level": "Low",
            "sla_target_days": 30,
            "sla_deadline": (now - timedelta(days=150)).isoformat(),
            "sla_status": "Completed On Time",
            "completion_date": (now - timedelta(days=165)).isoformat(),
            "dlp_months": 36,
            "dlp_start_date": (now - timedelta(days=165)).isoformat(),
            "dlp_end_date": (now + timedelta(days=930)).isoformat(),
            "dlp_status": "Active Warranty",
            "notes": "Handover accepted following CSIR-CRRI laser profilometer validation (IRI 2.05 m/km). 3-Year DLP in force."
        },
        {
            "work_order_id": "WO-2026-NCT-1006",
            "segment_id": "DL-PW-0006",
            "road_name": "Sardar Patel Marg (Dhaula Kuan)",
            "city_zone": "New Delhi (NDMC)",
            "pwd_division": "NDMC Road Maintenance Division / PWD Special",
            "tender_code": "NIT-NDMC-2025-R-014",
            "contractor_name": "Apex Infratech Delhi",
            "contractor_contact": "contracts@apexinfratech.in",
            "contract_value_inr": 12000000.0,
            "stage": "Audited & Closed",
            "treatment_type": "Preventive Micro-Surfacing & Slurry Seal (IRC:SP:81)",
            "priority_level": "Low",
            "sla_target_days": 21,
            "sla_deadline": (now - timedelta(days=260)).isoformat(),
            "sla_status": "Completed On Time",
            "completion_date": (now - timedelta(days=275)).isoformat(),
            "dlp_months": 24,
            "dlp_start_date": (now - timedelta(days=275)).isoformat(),
            "dlp_end_date": (now + timedelta(days=455)).isoformat(),
            "dlp_status": "Active Warranty",
            "notes": "VIP arterial corridor micro-surfacing complete with high-friction aggregate. 24-Month warranty active."
        },
        {
            "work_order_id": "WO-2026-NCT-1007",
            "segment_id": "DL-PW-0007",
            "road_name": "Najafgarh Road (Uttam Nagar to Tilak Nagar)",
            "city_zone": "West Delhi",
            "pwd_division": "PWD West Division (M-22)",
            "tender_code": "NIT-PWD-2026-M22-005",
            "contractor_name": "Continental Paving Corp",
            "contractor_contact": "info@continentalpaving.com",
            "contract_value_inr": 18000000.0,
            "stage": "Reported",
            "treatment_type": "Preventive Micro-Surfacing & Slurry Seal (IRC:SP:81)",
            "priority_level": "High",
            "sla_target_days": 7,
            "sla_deadline": (now - timedelta(days=3)).isoformat(),
            "sla_status": "SLA Breached",
            "completion_date": None,
            "dlp_months": 24,
            "dlp_start_date": None,
            "dlp_end_date": None,
            "dlp_status": "Pending Completion",
            "notes": "Citizen reports of multiple rutted potholes. Response past 7-day SLA window; escalation notice generated."
        }
    ]

    for s in seeds:
        cursor.execute("""
            INSERT INTO work_orders (
                work_order_id, segment_id, road_name, city_zone, pwd_division, tender_code,
                contractor_name, contractor_contact, contract_value_inr, stage, treatment_type,
                priority_level, sla_target_days, sla_deadline, sla_status, completion_date,
                dlp_months, dlp_start_date, dlp_end_date, dlp_status, boq_items_json, notes,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            s["work_order_id"], s["segment_id"], s["road_name"], s["city_zone"], s["pwd_division"],
            s["tender_code"], s["contractor_name"], s["contractor_contact"], s["contract_value_inr"],
            s["stage"], s["treatment_type"], s["priority_level"], s["sla_target_days"], s["sla_deadline"],
            s["sla_status"], s["completion_date"], s["dlp_months"], s["dlp_start_date"], s["dlp_end_date"],
            s["dlp_status"], json.dumps([]), s["notes"], (now - timedelta(days=15)).isoformat(), now.isoformat()
        ))


def get_work_orders(stage: str = None, zone: str = None, sla_status: str = None, limit: int = 100, db_path=DB_PATH):
    """Retrieves work orders matching optional stage, administrative zone, and SLA filters."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    conditions = []
    params = []

    if stage and stage.lower() != "all":
        conditions.append("stage = ?")
        params.append(stage)
    if zone and zone.lower() != "all":
        resolved = resolve_zone_filter(zone)
        if resolved:
            placeholders = ",".join(["?"] * len(resolved))
            conditions.append(f"city_zone IN ({placeholders})")
            params.extend(resolved)
    if sla_status and sla_status.lower() != "all":
        conditions.append("sla_status = ?")
        params.append(sla_status)

    where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"""
        SELECT * FROM work_orders 
        {where_sql}
        ORDER BY 
            CASE stage 
                WHEN 'Reported' THEN 1 
                WHEN 'Inspected' THEN 2 
                WHEN 'Tender Issued' THEN 3 
                WHEN 'Under Repair' THEN 4 
                WHEN 'Audited & Closed' THEN 5 
                ELSE 6 
            END,
            sla_deadline ASC
        LIMIT ?
    """
    params.append(limit)
    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    now = datetime.utcnow()
    processed = []
    for r in rows:
        val = r.get("contract_value_inr") or 0.0
        val_fmt = f"₹{(val / 10000000):.2f} Cr" if val >= 10000000 else f"₹{(val / 100000):.2f} L"
        
        # Calculate SLA days remaining
        deadline_str = r.get("sla_deadline")
        sla_days_rem = 0
        if deadline_str:
            try:
                dl = datetime.fromisoformat(deadline_str)
                sla_days_rem = (dl - now).days
            except Exception:
                pass

        # Calculate DLP warranty days remaining
        dlp_end_str = r.get("dlp_end_date")
        dlp_days_rem = 0
        if dlp_end_str:
            try:
                dlp_end = datetime.fromisoformat(dlp_end_str)
                dlp_days_rem = max(0, (dlp_end - now).days)
            except Exception:
                pass

        processed.append({
            **r,
            "contract_value_formatted": val_fmt,
            "sla_days_remaining": sla_days_rem,
            "dlp_days_remaining": dlp_days_rem
        })
    return processed


def get_work_order_by_id(wo_id: str, db_path=DB_PATH):
    """Retrieves full details of a specific work order by ID."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM work_orders WHERE work_order_id = ?", (wo_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    r = dict(row)
    val = r.get("contract_value_inr") or 0.0
    r["contract_value_formatted"] = f"₹{(val / 10000000):.2f} Cr" if val >= 10000000 else f"₹{(val / 100000):.2f} L"
    return r


def create_work_order(wo_data: Dict[str, Any], db_path=DB_PATH):
    """Creates a new municipal work order and stores it in the database."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    now = datetime.utcnow()
    wo_id = wo_data.get("work_order_id") or f"WO-2026-NCT-{uuid.uuid4().hex[:6].upper()}"
    sla_target = int(wo_data.get("sla_target_days") or 14)
    deadline = (now + timedelta(days=sla_target)).isoformat()
    dlp_months = int(wo_data.get("dlp_months") or 36)

    tender_code = wo_data.get("tender_code") or f"NIT-PWD-2026-{uuid.uuid4().hex[:4].upper()}"

    cursor.execute("""
        INSERT INTO work_orders (
            work_order_id, segment_id, road_name, city_zone, pwd_division, tender_code,
            contractor_name, contractor_contact, contract_value_inr, stage, treatment_type,
            priority_level, sla_target_days, sla_deadline, sla_status, completion_date,
            dlp_months, dlp_start_date, dlp_end_date, dlp_status, boq_items_json, notes,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        wo_id,
        wo_data["segment_id"],
        wo_data.get("road_name") or "Corridor",
        wo_data.get("city_zone") or "Central Delhi",
        wo_data.get("pwd_division") or get_pwd_division(wo_data.get("city_zone")),
        tender_code,
        wo_data.get("contractor_name") or "To Be Assigned via e-Tender",
        wo_data.get("contractor_contact", ""),
        float(wo_data.get("contract_value_inr") or 1000000.0),
        wo_data.get("stage") or "Reported",
        wo_data.get("treatment_type") or "Preventive Micro-Surfacing (IRC:SP:81)",
        wo_data.get("priority_level") or "Medium",
        sla_target,
        deadline,
        "On Track",
        None,
        dlp_months,
        None,
        None,
        "Pending Completion",
        json.dumps(wo_data.get("boq_items") or []),
        wo_data.get("notes") or "Created from PaveSentry Pavement Management System",
        now.isoformat(),
        now.isoformat()
    ))
    conn.commit()
    conn.close()
    return get_work_order_by_id(wo_id, db_path=db_path)


def update_work_order_stage(wo_id: str, new_stage: str, updated_by: str = None, notes: str = None, db_path=DB_PATH):
    """
    Updates the lifecycle stage of a work order (e.g. advance to Under Repair or Audited & Closed).
    Automatically calculates DLP warranty dates if moving to Audited & Closed.
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM work_orders WHERE work_order_id = ?", (wo_id,))
    wo = cursor.fetchone()
    if not wo:
        conn.close()
        return None
    wo = dict(wo)

    now = datetime.utcnow()
    extra_updates = []
    params = [new_stage]

    if new_stage == "Audited & Closed":
        dlp_m = wo.get("dlp_months") or 36
        dlp_start = now.isoformat()
        dlp_end = (now + timedelta(days=30 * dlp_m)).isoformat()
        extra_updates.append("completion_date = ?")
        params.append(now.isoformat())
        extra_updates.append("dlp_start_date = ?")
        params.append(dlp_start)
        extra_updates.append("dlp_end_date = ?")
        params.append(dlp_end)
        extra_updates.append("dlp_status = 'Active Warranty'")
        
        # Check if completed on time
        deadline_str = wo.get("sla_deadline")
        sla_res = "Completed On Time"
        if deadline_str:
            try:
                dl = datetime.fromisoformat(deadline_str)
                if now > dl:
                    sla_res = "Completed Late"
            except Exception:
                pass
        extra_updates.append("sla_status = ?")
        params.append(sla_res)

    if notes:
        existing_notes = wo.get("notes") or ""
        new_note_entry = f"[{now.strftime('%d-%b %H:%M')}] Stage -> {new_stage}: {notes}. "
        extra_updates.append("notes = ?")
        params.append(new_note_entry + existing_notes)

    extra_updates.append("updated_at = ?")
    params.append(now.isoformat())

    params.append(wo_id)
    update_sql = f"UPDATE work_orders SET stage = ?, {', '.join(extra_updates)} WHERE work_order_id = ?"
    cursor.execute(update_sql, params)
    conn.commit()
    conn.close()
    return get_work_order_by_id(wo_id, db_path=db_path)


def get_kanban_summary_stats(zone: str = None, db_path=DB_PATH) -> Dict[str, Any]:
    """Computes real-time KPI metrics for the Contractor Kanban & SLA Dashboard."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    resolved = resolve_zone_filter(zone)
    zone_filter_sql = ""
    params = []
    if resolved:
        placeholders = ",".join(["?"] * len(resolved))
        zone_filter_sql = f"WHERE city_zone IN ({placeholders})"
        params = list(resolved)

    cursor.execute(f"""
        SELECT 
            COUNT(*) as total_orders,
            SUM(CASE WHEN stage = 'Reported' THEN 1 ELSE 0 END) as count_reported,
            SUM(CASE WHEN stage = 'Inspected' THEN 1 ELSE 0 END) as count_inspected,
            SUM(CASE WHEN stage = 'Tender Issued' THEN 1 ELSE 0 END) as count_tender_issued,
            SUM(CASE WHEN stage = 'Under Repair' THEN 1 ELSE 0 END) as count_under_repair,
            SUM(CASE WHEN stage = 'Audited & Closed' THEN 1 ELSE 0 END) as count_audited_closed,
            SUM(CASE WHEN sla_status = 'On Track' THEN 1 ELSE 0 END) as sla_on_track,
            SUM(CASE WHEN sla_status = 'Approaching Breach' THEN 1 ELSE 0 END) as sla_approaching_breach,
            SUM(CASE WHEN sla_status = 'SLA Breached' THEN 1 ELSE 0 END) as sla_breached,
            SUM(CASE WHEN dlp_status = 'Active Warranty' THEN 1 ELSE 0 END) as active_dlp_contracts,
            SUM(CASE WHEN dlp_status = 'Breach Flagged (Penalty Pending)' THEN 1 ELSE 0 END) as dlp_breached_contracts,
            COALESCE(SUM(contract_value_inr), 0) as total_contract_value_inr
        FROM work_orders
        {zone_filter_sql}
    """, params)
    stats_row = dict(cursor.fetchone())

    # Get total penalties from dlp_warranty_incidents
    cursor.execute("SELECT COALESCE(SUM(penalty_amount_inr), 0) FROM dlp_warranty_incidents")
    total_penalties = cursor.fetchone()[0] or 0.0

    conn.close()

    total_orders = stats_row["total_orders"] or 0
    on_track = stats_row["sla_on_track"] or 0
    sla_compliance_pct = round((on_track / max(1, total_orders)) * 100.0, 1)

    val = stats_row["total_contract_value_inr"] or 0.0

    return {
        "total_work_orders": total_orders,
        "stages": {
            "reported": stats_row["count_reported"] or 0,
            "inspected": stats_row["count_inspected"] or 0,
            "tender_issued": stats_row["count_tender_issued"] or 0,
            "under_repair": stats_row["count_under_repair"] or 0,
            "audited_closed": stats_row["count_audited_closed"] or 0
        },
        "sla": {
            "on_track": on_track,
            "approaching_breach": stats_row["sla_approaching_breach"] or 0,
            "breached": stats_row["sla_breached"] or 0,
            "compliance_pct": sla_compliance_pct
        },
        "dlp": {
            "active_warranty_contracts": stats_row["active_dlp_contracts"] or 0,
            "breach_flagged_contracts": stats_row["dlp_breached_contracts"] or 0,
            "total_penalties_inr": total_penalties,
            "total_penalties_formatted": f"₹{(total_penalties / 100000):.2f} L" if total_penalties >= 100000 else f"₹{total_penalties:,.2f}"
        },
        "total_contract_value_inr": val,
        "total_contract_value_formatted": f"₹{(val / 10000000):.2f} Cr" if val >= 10000000 else f"₹{(val / 100000):.2f} L"
    }


def get_dlp_incidents(status: str = None, limit: int = 50, db_path=DB_PATH):
    """Retrieves Defect Liability Period breach incidents and contractor notices."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    if status and status.lower() != "all":
        cursor.execute("""
            SELECT inc.*, wo.road_name, wo.pwd_division, wo.city_zone 
            FROM dlp_warranty_incidents inc
            JOIN work_orders wo ON inc.work_order_id = wo.work_order_id
            WHERE inc.status = ?
            ORDER BY inc.created_at DESC LIMIT ?
        """, (status, limit))
    else:
        cursor.execute("""
            SELECT inc.*, wo.road_name, wo.pwd_division, wo.city_zone 
            FROM dlp_warranty_incidents inc
            JOIN work_orders wo ON inc.work_order_id = wo.work_order_id
            ORDER BY inc.created_at DESC LIMIT ?
        """, (limit,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    for r in rows:
        p = r.get("penalty_amount_inr") or 0.0
        r["penalty_amount_formatted"] = f"₹{(p / 100000):.2f} L" if p >= 100000 else f"₹{p:,.2f}"
    return rows


def update_dlp_incident_status(incident_id: str, new_status: str, notes: str = None, db_path=DB_PATH):
    """Updates the resolution status of a DLP breach incident (e.g. Rectified by Contractor or Bank Guarantee Deducted)."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE dlp_warranty_incidents
        SET status = ?
        WHERE incident_id = ?
    """, (new_status, incident_id))
    conn.commit()
    conn.close()
    return True

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully at:", DB_PATH)

