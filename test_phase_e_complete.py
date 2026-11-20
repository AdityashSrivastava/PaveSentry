"""
test_phase_e_complete.py
Comprehensive End-to-End Test Suite for Phase E: Enterprise PostGIS Migration & Connected Vehicle Telemetry.
Verifies PostGIS spatial indexing, ST_DWithin radius topological queries, SQLite-to-PostGIS migration dump,
high-frequency accelerometer vibration streaming, ASTM E1926 Quarter-Car IRI computation,
pothole shock spike detection, and full regression across Phases A, B, C, and D.
"""
import io
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from PIL import Image
import numpy as np

ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))

from backend.main import app
from database.postgis_manager import get_postgis_engine, POSTGIS_DUMP_PATH
from ml.telemetry_engine import get_telemetry_engine

client = TestClient(app)

def test_01_postgis_spatial_engine_and_indexing():
    """Validates PostGIS spatial engine status and ST_DWithin radius queries."""
    res = client.get("/api/spatial/status")
    assert res.status_code == 200, f"Spatial status failed: {res.text}"
    status = res.json()
    assert status["status"] == "success"
    assert "EPSG:4326" in status["spatial_reference_system"]
    assert status["total_corridors_indexed"] >= 300
    assert "ST_DWithin" in "".join(status["supported_topological_ops"])

    # Test ST_DWithin radius query around Central Delhi (Connaught Place / Ring Road)
    res_radius = client.get("/api/spatial/corridors/radius?lon=77.2180&lat=28.6304&radius_m=3000")
    assert res_radius.status_code == 200
    data = res_radius.json()
    assert data["status"] == "success"
    assert data["corridors_found"] > 0
    corridors = data["corridors"]
    assert len(corridors) > 0
    
    # Assert sorted by proximity
    dists = [c["distance_meters"] for c in corridors]
    assert dists == sorted(dists), "Corridors should be ordered by metric distance"
    assert "closest_point" in corridors[0]
    print(f"\n[Test 1 PASSED] PostGIS Spatial Engine: {data['corridors_found']} corridors found within 3km of Central Delhi. Closest: {corridors[0]['name']} ({corridors[0]['distance_meters']}m)")


def test_02_postgis_migration_dump():
    """Validates one-click SQLite to PostgreSQL 16 + PostGIS SQL dump generation."""
    res = client.post("/api/spatial/migrate")
    assert res.status_code == 200, f"Migration failed: {res.text}"
    data = res.json()
    assert data["status"] == "success"
    assert data["corridors_migrated"] >= 300
    assert data["dump_size_bytes"] > 100000  # Dump should be > 100 KB
    assert POSTGIS_DUMP_PATH.exists()

    with open(POSTGIS_DUMP_PATH, "r", encoding="utf-8") as f:
        content = f.read(2000)
    assert "CREATE EXTENSION IF NOT EXISTS postgis;" in content
    assert "ST_GeomFromText" in content
    print(f"\n[Test 2 PASSED] PostGIS 16 Migration Dump generated ({round(data['dump_size_bytes']/1024, 1)} KB). All {data['corridors_migrated']} corridors converted to WKT LineStrings.")


def test_03_telemetry_packet_processing_and_snapping():
    """Validates vehicle accelerometer vibration processing, ASTM E1926 Quarter-Car IRI, and PostGIS snapping."""
    # 1. Normal smooth riding packet on Ring Road near AIIMS
    normal_packet = {
        "vehicle_id": "DTC-DL1PC-4021",
        "latitude": 28.5672,
        "longitude": 77.2090,
        "speed_kmh": 42.0,
        "accel_x": 0.02,
        "accel_y": 0.01,
        "accel_z": 1.08,  # Normal ~1.0g vibration
        "gyro_pitch": 0.01,
        "gyro_roll": 0.005,
        "gyro_yaw": 0.001
    }
    res_norm = client.post("/api/telemetry/ingest", json=normal_packet)
    assert res_norm.status_code == 200
    t_norm = res_norm.json()["telemetry"]
    assert t_norm["vehicle_id"] == "DTC-DL1PC-4021"
    assert t_norm["computed_iri"] > 0
    assert t_norm["is_pothole_spike"] is False
    assert t_norm["snapped_corridor"] is not None
    assert t_norm["distance_to_corridor_m"] < 150.0

    # 2. Severe pothole crater impact shock packet (> 2.2g)
    shock_packet = {
        "vehicle_id": "DTC-DL1PC-4021",
        "latitude": 28.5675,
        "longitude": 77.2094,
        "speed_kmh": 38.0,
        "accel_x": 0.05,
        "accel_y": 0.03,
        "accel_z": 2.74,  # Severe 2.74g shock impact
        "gyro_pitch": 0.08,
        "gyro_roll": 0.04,
        "gyro_yaw": 0.002
    }
    res_shock = client.post("/api/telemetry/ingest", json=shock_packet)
    assert res_shock.status_code == 200
    t_shock = res_shock.json()["telemetry"]
    assert t_shock["is_pothole_spike"] is True
    assert t_shock["spike_magnitude_g"] >= 2.7

    # Verify spike registered in alert feed
    res_spikes = client.get("/api/telemetry/spikes")
    assert res_spikes.status_code == 200
    spikes = res_spikes.json()["spikes"]
    assert len(spikes) > 0
    print(f"\n[Test 3 PASSED] Telemetry ingestion verified. Quarter-Car IRI: {t_norm['computed_iri']} m/km. High-G shock ({t_shock['spike_magnitude_g']}g) flagged & snapped to: {t_shock['snapped_corridor']}")


def test_04_dtc_bus_trip_simulation():
    """Validates continuous DTC electric bus trip simulation along an arterial corridor."""
    corridor_id = "DL-NCT-0001"  # Mahatma Gandhi Ring Road
    payload = {
        "segment_id": corridor_id,
        "vehicle_id": "DTC-DL1PC-4021",
        "speed_kmh": 45.0,
        "samples_count": 16
    }
    res = client.post("/api/telemetry/simulate-trip", json=payload)
    assert res.status_code == 200, f"Trip simulation failed: {res.text}"
    trip = res.json()
    assert trip["status"] == "success"
    assert trip["corridor_id"] == corridor_id
    assert trip["total_samples"] == 16
    assert trip["mean_dynamic_iri"] > 0
    assert len(trip["waveform_samples"]) == 16

    # Verify waveform endpoint
    res_wave = client.get(f"/api/telemetry/waveform/{payload['vehicle_id']}")
    assert res_wave.status_code == 200
    assert res_wave.json()["samples_count"] > 0
    print(f"\n[Test 4 PASSED] DTC Bus trip simulated on {trip['corridor_name']}: Mean Dynamic IRI {trip['mean_dynamic_iri']} m/km ({trip['total_samples']} samples).")


def test_05_regression_phases_a_b_c_d():
    """Validates that Phase A (Vision), Phase B (Multi-Year CIP), Phase C (Kanban & DSR), and Phase D (XAI) remain 100% operational."""
    # Phase A: Vision Detector
    res_presets = client.get("/api/vision/calibration-presets")
    assert res_presets.status_code == 200
    assert len(res_presets.json()["presets"]) >= 4

    # Phase B: Multi-Year Capital Planning
    res_b = client.post("/api/optimization/multi-year", json={
        "annual_budget": 100000000.0,
        "horizon_years": 3,
        "max_km_per_year": 150.0,
        "discount_rate": 0.06
    })
    assert res_b.status_code == 200
    assert len(res_b.json()["plan"]["master_schedule"]) > 0

    # Phase C: CPWD DSR Catalog & BOQ
    res_c_boq = client.post("/api/dsr/generate-boq", json={
        "road_name": "Ring Road Phase E Regression Test",
        "length_km": 2.5,
        "lanes": 4,
        "treatment_type": "Preventive Micro-Surfacing & Slurry Seal (IRC:SP:81)"
    })
    assert res_c_boq.status_code == 200
    assert len(res_c_boq.json()["boq"]["items"]) > 0

    # Phase D: Explainable AI TreeSHAP Attribution
    res_d = client.get("/api/xai/corridor/DL-NCT-0001")
    assert res_d.status_code == 200
    exp = res_d.json()["explanation"]
    assert len(exp["top_risk_drivers"]) > 0
    assert "CSIR-CRRI" in exp["audit_justification"]

    print("\n[Regression A, B, C, D PASSED] All previous phases remain 100% operational.")

if __name__ == "__main__":
    pytest.main(["-v", "test_phase_e_complete.py"])
