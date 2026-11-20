-- ============================================================================
-- PaveSentry Enterprise PostGIS 16 Spatial Schema
-- Conforms to OpenGIS Simple Features Specification & EPSG:4326 (WGS 84)
-- ============================================================================

-- Enable PostGIS Spatial Extensions
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;

-- 1. Road Segments with True Spatial LineString Geometry
CREATE TABLE IF NOT EXISTS road_segments (
    segment_id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    road_type VARCHAR(50) NOT NULL,          -- Highway, Arterial, Collector, Local
    city_zone VARCHAR(100) NOT NULL,         -- Central Delhi, South Delhi, North Delhi, East Delhi, etc.
    length_km DOUBLE PRECISION NOT NULL,
    surface_type VARCHAR(100) NOT NULL,      -- Bituminous Concrete, Mastic Asphalt, Rigid Concrete
    lanes INTEGER NOT NULL DEFAULT 4,
    start_lat DOUBLE PRECISION NOT NULL,
    start_lon DOUBLE PRECISION NOT NULL,
    end_lat DOUBLE PRECISION NOT NULL,
    end_lon DOUBLE PRECISION NOT NULL,
    construction_year INTEGER NOT NULL,
    last_major_maintenance_year INTEGER NOT NULL,
    -- PostGIS Native Spatial Column (LineString geometry in WGS 84)
    geometry GEOMETRY(LineString, 4326) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Spatial GIST Index for Sub-Millisecond Topological Queries
CREATE INDEX IF NOT EXISTS idx_road_segments_gist ON road_segments USING GIST(geometry);
CREATE INDEX IF NOT EXISTS idx_road_segments_zone ON road_segments(city_zone);
CREATE INDEX IF NOT EXISTS idx_road_segments_type ON road_segments(road_type);

-- 2. Condition Surveys
CREATE TABLE IF NOT EXISTS condition_surveys (
    survey_id SERIAL PRIMARY KEY,
    segment_id VARCHAR(50) NOT NULL REFERENCES road_segments(segment_id) ON DELETE CASCADE,
    survey_date DATE NOT NULL,
    pci DOUBLE PRECISION NOT NULL,                -- Pavement Condition Index (0-100)
    iri DOUBLE PRECISION NOT NULL,                -- International Roughness Index (m/km)
    crack_density_pct DOUBLE PRECISION NOT NULL,  -- Crack area percentage
    rut_depth_mm DOUBLE PRECISION NOT NULL,       -- Rut depth in mm
    pothole_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_surveys_segment ON condition_surveys(segment_id);

-- 3. Traffic and Environmental Weather
CREATE TABLE IF NOT EXISTS traffic_weather (
    segment_id VARCHAR(50) PRIMARY KEY REFERENCES road_segments(segment_id) ON DELETE CASCADE,
    aadt INTEGER NOT NULL,                         -- Average Annual Daily Traffic
    heavy_vehicle_pct DOUBLE PRECISION NOT NULL,   -- Commercial freight percentage
    annual_rainfall_mm DOUBLE PRECISION NOT NULL,  -- Annual rainfall in mm (Monsoon)
    freeze_thaw_cycles INTEGER NOT NULL,           -- Thermal cycling (Summer 46°C / Winter 4°C)
    avg_temperature_c DOUBLE PRECISION NOT NULL    -- Peak summer temperature
);

-- 4. Machine Learning Predictive Output Matrix
CREATE TABLE IF NOT EXISTS predictions (
    segment_id VARCHAR(50) PRIMARY KEY REFERENCES road_segments(segment_id) ON DELETE CASCADE,
    predicted_risk_level VARCHAR(20) NOT NULL,    -- High, Medium, Low
    pothole_probability DOUBLE PRECISION NOT NULL,
    est_time_to_failure_months DOUBLE PRECISION NOT NULL,
    est_preventive_cost_inr DOUBLE PRECISION NOT NULL,
    est_reactive_cost_inr DOUBLE PRECISION NOT NULL,
    priority_score DOUBLE PRECISION NOT NULL,
    recommended_action VARCHAR(255) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);

-- 5. Pothole Reports with True Spatial Point Geometry
CREATE TABLE IF NOT EXISTS pothole_reports (
    report_id VARCHAR(50) PRIMARY KEY,
    segment_id VARCHAR(50) REFERENCES road_segments(segment_id) ON DELETE SET NULL,
    road_name VARCHAR(255),
    city_zone VARCHAR(100),
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    severity VARCHAR(50) NOT NULL,
    depth_mm DOUBLE PRECISION,
    width_cm DOUBLE PRECISION,
    photo_filename VARCHAR(255),
    reported_by VARCHAR(100) NOT NULL,
    reporter_role VARCHAR(50) NOT NULL,
    reporter_division VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'Reported',
    notes TEXT,
    cv_verified BOOLEAN DEFAULT FALSE,
    cv_confidence DOUBLE PRECISION,
    cv_area_cm2 DOUBLE PRECISION,
    cv_depth_category VARCHAR(50),
    annotated_photo_filename VARCHAR(255),
    -- PostGIS Native Spatial Point Geometry
    location GEOMETRY(Point, 4326) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_potholes_gist ON pothole_reports USING GIST(location);
CREATE INDEX IF NOT EXISTS idx_potholes_segment ON pothole_reports(segment_id);
CREATE INDEX IF NOT EXISTS idx_potholes_status ON pothole_reports(status);

-- 6. Connected Fleet / Bus Continuous Vibration Telemetry Stream
CREATE TABLE IF NOT EXISTS telemetry_stream (
    telemetry_id BIGSERIAL PRIMARY KEY,
    vehicle_id VARCHAR(50) NOT NULL,               -- e.g. 'DTC-DL1PC-4021', 'PWD-INSP-07'
    fleet_type VARCHAR(50) NOT NULL DEFAULT 'DTC Bus', -- DTC Electric Bus, PWD Inspection Van, Sanitation Fleet
    recorded_at TIMESTAMP WITH TIME ZONE NOT NULL,
    speed_kmh DOUBLE PRECISION NOT NULL,
    -- 3-Axis Accelerometer (m/s^2 or g)
    accel_x DOUBLE PRECISION NOT NULL,
    accel_y DOUBLE PRECISION NOT NULL,
    accel_z DOUBLE PRECISION NOT NULL,             -- Vertical axle acceleration
    -- 3-Axis Gyroscope (rad/s)
    gyro_pitch DOUBLE PRECISION NOT NULL,
    gyro_roll DOUBLE PRECISION NOT NULL,
    gyro_yaw DOUBLE PRECISION NOT NULL,
    -- Computed Dynamics
    vertical_rms DOUBLE PRECISION NOT NULL,        -- Root Mean Square vertical acceleration
    computed_iri DOUBLE PRECISION NOT NULL,        -- Live ASTM E1926 Quarter-Car Roughness (m/km)
    is_pothole_spike BOOLEAN DEFAULT FALSE,        -- True if vertical acceleration > 2.2g
    spike_magnitude_g DOUBLE PRECISION DEFAULT 0.0,
    -- PostGIS Spatial Snapping
    location GEOMETRY(Point, 4326) NOT NULL,
    snapped_segment_id VARCHAR(50) REFERENCES road_segments(segment_id) ON DELETE SET NULL,
    distance_to_segment_m DOUBLE PRECISION
);

-- High-Performance Spatial & Time-Series Indexes
CREATE INDEX IF NOT EXISTS idx_telemetry_gist ON telemetry_stream USING GIST(location);
CREATE INDEX IF NOT EXISTS idx_telemetry_vehicle_time ON telemetry_stream(vehicle_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_telemetry_snapped ON telemetry_stream(snapped_segment_id);
CREATE INDEX IF NOT EXISTS idx_telemetry_spikes ON telemetry_stream(is_pothole_spike) WHERE is_pothole_spike = TRUE;

-- 7. Municipal Work Orders & Contract SLAs (Phase C)
CREATE TABLE IF NOT EXISTS work_orders (
    work_order_id VARCHAR(50) PRIMARY KEY,
    segment_id VARCHAR(50) NOT NULL REFERENCES road_segments(segment_id) ON DELETE CASCADE,
    road_name VARCHAR(255) NOT NULL,
    city_zone VARCHAR(100) NOT NULL,
    contractor_name VARCHAR(255) NOT NULL,
    contractor_contact VARCHAR(100),
    contract_value_inr DOUBLE PRECISION NOT NULL,
    stage VARCHAR(50) NOT NULL DEFAULT 'Reported',
    treatment_type VARCHAR(255) NOT NULL,
    priority_level VARCHAR(20) NOT NULL,
    sla_target_days INTEGER NOT NULL,
    sla_deadline TIMESTAMP WITH TIME ZONE NOT NULL,
    sla_status VARCHAR(50) NOT NULL DEFAULT 'On Track',
    completion_date TIMESTAMP WITH TIME ZONE,
    dlp_months INTEGER DEFAULT 36,
    dlp_start_date TIMESTAMP WITH TIME ZONE,
    dlp_end_date TIMESTAMP WITH TIME ZONE,
    dlp_status VARCHAR(50) DEFAULT 'Active Warranty',
    boq_items_json JSONB,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_postgis_wo_stage ON work_orders(stage);
CREATE INDEX IF NOT EXISTS idx_postgis_wo_segment ON work_orders(segment_id);

-- 8. Defect Liability Period (DLP) Warranty Incidents (Phase C)
CREATE TABLE IF NOT EXISTS dlp_warranty_incidents (
    incident_id VARCHAR(50) PRIMARY KEY,
    work_order_id VARCHAR(50) NOT NULL REFERENCES work_orders(work_order_id) ON DELETE CASCADE,
    segment_id VARCHAR(50) NOT NULL REFERENCES road_segments(segment_id) ON DELETE CASCADE,
    pothole_report_id VARCHAR(50) REFERENCES pothole_reports(report_id) ON DELETE SET NULL,
    contractor_name VARCHAR(255) NOT NULL,
    defect_date TIMESTAMP WITH TIME ZONE NOT NULL,
    severity VARCHAR(50) NOT NULL,
    rectification_deadline TIMESTAMP WITH TIME ZONE NOT NULL,
    penalty_amount_inr DOUBLE PRECISION NOT NULL,
    clause_applied VARCHAR(255) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'Notice Issued',
    show_cause_notice_text TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_postgis_dlp_wo ON dlp_warranty_incidents(work_order_id);
CREATE INDEX IF NOT EXISTS idx_postgis_dlp_seg ON dlp_warranty_incidents(segment_id);
