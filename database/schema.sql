-- Database Schema for PaveSentry (SQLite — Delhi NCT Network)

CREATE TABLE IF NOT EXISTS road_segments (
    segment_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    road_type TEXT NOT NULL,          -- Highway, Arterial, Collector, Local
    city_zone TEXT NOT NULL,          -- Central Delhi, South Delhi, North Delhi, East Delhi, West Delhi, New Delhi (NDMC), Shahdara, etc.
    length_km REAL NOT NULL,
    surface_type TEXT NOT NULL,       -- Bituminous Concrete, Mastic Asphalt, Flexible, Rigid Concrete
    lanes INTEGER NOT NULL,
    start_lat REAL NOT NULL,
    start_lon REAL NOT NULL,
    end_lat REAL NOT NULL,
    end_lon REAL NOT NULL,
    construction_year INTEGER NOT NULL,
    last_major_maintenance_year INTEGER NOT NULL,
    geometry_coords TEXT              -- JSON array of [[lon, lat], ...] for authentic road curvature
);

CREATE TABLE IF NOT EXISTS condition_surveys (
    survey_id INTEGER PRIMARY KEY AUTOINCREMENT,
    segment_id TEXT NOT NULL,
    survey_date TEXT NOT NULL,
    pci REAL NOT NULL,                -- Pavement Condition Index (0-100)
    iri REAL NOT NULL,                -- International Roughness Index (m/km)
    crack_density_pct REAL NOT NULL,  -- Crack area percentage
    rut_depth_mm REAL NOT NULL,       -- Rut depth in mm
    pothole_count INTEGER NOT NULL,   -- Active potholes observed
    FOREIGN KEY (segment_id) REFERENCES road_segments(segment_id)
);

CREATE TABLE IF NOT EXISTS traffic_weather (
    segment_id TEXT PRIMARY KEY,
    aadt INTEGER NOT NULL,             -- Average Annual Daily Traffic (PCU/day)
    heavy_vehicle_pct REAL NOT NULL,   -- Percentage of commercial multi-axle trucks
    annual_rainfall_mm REAL NOT NULL,  -- Annual rainfall in mm (Monsoon load)
    freeze_thaw_cycles INTEGER NOT NULL, -- Thermal expansion cycles (Summer 46C / Winter 4C)
    avg_temperature_c REAL NOT NULL,  -- Peak summer average temperature
    FOREIGN KEY (segment_id) REFERENCES road_segments(segment_id)
);

CREATE TABLE IF NOT EXISTS repair_history (
    repair_id INTEGER PRIMARY KEY AUTOINCREMENT,
    segment_id TEXT NOT NULL,
    repair_date TEXT NOT NULL,
    repair_type TEXT NOT NULL,         -- Crack Sealing, Micro-surfacing, BC Mill & Overlay, Reconstruction
    cost_inr REAL NOT NULL,
    FOREIGN KEY (segment_id) REFERENCES road_segments(segment_id)
);

CREATE TABLE IF NOT EXISTS predictions (
    segment_id TEXT PRIMARY KEY,
    predicted_risk_level TEXT NOT NULL, -- High, Medium, Low
    pothole_probability REAL NOT NULL,
    est_time_to_failure_months REAL NOT NULL,
    est_preventive_cost_inr REAL NOT NULL,
    est_reactive_cost_inr REAL NOT NULL,
    priority_score REAL NOT NULL,
    recommended_action TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (segment_id) REFERENCES road_segments(segment_id)
);

-- ==========================================================================
-- PHASE 3: AUTHENTICATION, MULTI-TENANCY & FIELD SURVEY INGESTION TABLES
-- ==========================================================================

CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL,               -- pwd_engineer, mcd_planner, crri_auditor
    division TEXT NOT NULL,           -- e.g. PWD South Division (M-11), NDMC, CSIR-CRRI Pavement Division
    created_at TEXT NOT NULL,
    last_login TEXT
);

CREATE TABLE IF NOT EXISTS pothole_reports (
    report_id TEXT PRIMARY KEY,
    segment_id TEXT,
    road_name TEXT,
    city_zone TEXT,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    severity TEXT NOT NULL,           -- High / Severe (>50mm), Medium / Moderate (25-50mm), Low / Minor (<25mm)
    depth_mm REAL,
    width_cm REAL,
    photo_filename TEXT,              -- path relative to uploads/potholes/
    reported_by TEXT NOT NULL,        -- user email
    reporter_role TEXT NOT NULL,
    reporter_division TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'Reported', -- Reported, Verified, Scheduled, Repaired
    notes TEXT,
    created_at TEXT NOT NULL,
    cv_verified INTEGER DEFAULT 0,
    cv_confidence REAL,
    cv_area_cm2 REAL,
    cv_depth_category TEXT,
    annotated_photo_filename TEXT,
    boundary_coords TEXT,
    FOREIGN KEY (segment_id) REFERENCES road_segments(segment_id)
);

CREATE TABLE IF NOT EXISTS survey_uploads (
    upload_id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    file_format TEXT NOT NULL,        -- CSV/ROMDAS, GeoJSON/ARRB
    uploaded_by TEXT NOT NULL,
    division TEXT NOT NULL,
    records_count INTEGER NOT NULL,
    segments_affected INTEGER NOT NULL,
    avg_iri REAL,
    avg_pci REAL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_validations (
    audit_id TEXT PRIMARY KEY,
    segment_id TEXT NOT NULL,
    auditor_name TEXT NOT NULL,
    auditor_email TEXT NOT NULL,
    compliance_status TEXT NOT NULL,  -- Compliant with IRC:82, Conditional Pass, Non-Compliant - Urgent Tender
    measured_iri REAL NOT NULL,
    measured_pci REAL NOT NULL,
    certificate_code TEXT NOT NULL,
    audit_notes TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (segment_id) REFERENCES road_segments(segment_id)
);

-- Indexes for high-performance spatial & relational lookup
CREATE INDEX IF NOT EXISTS idx_condition_segment ON condition_surveys(segment_id);
CREATE INDEX IF NOT EXISTS idx_potholes_segment ON pothole_reports(segment_id);
CREATE INDEX IF NOT EXISTS idx_potholes_status ON pothole_reports(status);
CREATE INDEX IF NOT EXISTS idx_audits_segment ON audit_validations(segment_id);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- ==========================================================================
-- PHASE C: CONTRACTOR SLA & WORK ORDER LIFECYCLE KANBAN & DLP WARRANTY TABLES
-- ==========================================================================

CREATE TABLE IF NOT EXISTS work_orders (
    work_order_id TEXT PRIMARY KEY,
    segment_id TEXT NOT NULL,
    road_name TEXT NOT NULL,
    city_zone TEXT NOT NULL,
    pwd_division TEXT NOT NULL,
    tender_code TEXT NOT NULL,
    contractor_name TEXT NOT NULL,
    contractor_contact TEXT,
    contract_value_inr REAL NOT NULL,
    stage TEXT NOT NULL DEFAULT 'Reported', -- Reported, Inspected, Tender Issued, Under Repair, Audited & Closed
    treatment_type TEXT NOT NULL,          -- Full Reconstruction, BC Mill & Overlay, Preventive Micro-Surfacing, Crack Sealing
    priority_level TEXT NOT NULL,          -- Critical, High, Medium, Low
    sla_target_days INTEGER NOT NULL,      -- e.g. 7, 14, 30, 60
    sla_deadline TEXT NOT NULL,            -- ISO datetime
    sla_status TEXT NOT NULL DEFAULT 'On Track', -- On Track, Approaching Breach, SLA Breached, Completed On Time, Completed Late
    completion_date TEXT,
    dlp_months INTEGER DEFAULT 36,         -- 36 months for BC/DBM, 24 for Micro-surfacing, 12 for Patching
    dlp_start_date TEXT,
    dlp_end_date TEXT,
    dlp_status TEXT DEFAULT 'Active Warranty', -- Active Warranty, Expired Warranty, Breach Flagged (Penalty Pending)
    boq_items_json TEXT,                   -- JSON list of CPWD DSR items and quantities
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (segment_id) REFERENCES road_segments(segment_id)
);

CREATE TABLE IF NOT EXISTS dlp_warranty_incidents (
    incident_id TEXT PRIMARY KEY,
    work_order_id TEXT NOT NULL,
    segment_id TEXT NOT NULL,
    pothole_report_id TEXT,
    contractor_name TEXT NOT NULL,
    defect_date TEXT NOT NULL,
    severity TEXT NOT NULL,
    rectification_deadline TEXT NOT NULL,
    penalty_amount_inr REAL NOT NULL,
    clause_applied TEXT NOT NULL,          -- CPWD GCC Clause 17 (Rectification of Defects during DLP)
    status TEXT NOT NULL DEFAULT 'Notice Issued', -- Notice Issued, Rectified by Contractor, Bank Guarantee Deducted
    show_cause_notice_text TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (work_order_id) REFERENCES work_orders(work_order_id),
    FOREIGN KEY (segment_id) REFERENCES road_segments(segment_id)
);

CREATE INDEX IF NOT EXISTS idx_wo_stage ON work_orders(stage);
CREATE INDEX IF NOT EXISTS idx_wo_segment ON work_orders(segment_id);
CREATE INDEX IF NOT EXISTS idx_wo_sla_status ON work_orders(sla_status);
CREATE INDEX IF NOT EXISTS idx_wo_dlp_status ON work_orders(dlp_status);
CREATE INDEX IF NOT EXISTS idx_dlp_wo ON dlp_warranty_incidents(work_order_id);
CREATE INDEX IF NOT EXISTS idx_dlp_segment ON dlp_warranty_incidents(segment_id);


