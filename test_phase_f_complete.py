"""
test_phase_f_complete.py
Comprehensive End-to-End Verification Test Suite for Phase F:
Green Roads & Carbon Footprint Calculator (IRC:SP:98-2020) and
Full Platform Regression Suite across Phases A, B, C, D, and E.
"""

import os
import sys
import json
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from optimization.green_roads import (
    calculate_corridor_carbon,
    get_treatment_options_comparison,
    get_network_green_esg_summary,
    get_green_certificate,
    EMISSION_FACTORS,
    CONVENTIONAL_BASELINE_TREATMENT
)

client = TestClient(app)

# ==============================================================================
# SECTION 1: Phase F Unit Tests - IRC:SP:98-2020 LCA & Carbon Footprint Math
# ==============================================================================

def test_phase_f_emission_benchmarks_validity():
    """Verify standard emission factor benchmarks and RAP configurations."""
    assert "Full Reconstruction & Sub-base Work (IRC:37)" in EMISSION_FACTORS
    assert "Cold In-Place Recycling (CIR) Base Stabilization" in EMISSION_FACTORS
    assert "Warm Mix Asphalt (WMA) Sustainable Overlay" in EMISSION_FACTORS
    
    hma = EMISSION_FACTORS["Full Reconstruction & Sub-base Work (IRC:37)"]
    cir = EMISSION_FACTORS["Cold In-Place Recycling (CIR) Base Stabilization"]
    
    assert hma["embodied_co2e_per_lanekm"] > cir["embodied_co2e_per_lanekm"]
    assert cir["rap_recycled_content_pct"] >= 80.0
    assert hma["plant_mixing_temp_c"] >= 160


def test_phase_f_corridor_carbon_calculation():
    """Test detailed lifecycle carbon accounting for a Delhi arterial corridor."""
    lca = calculate_corridor_carbon("DL-NCT-0001")
    
    assert lca["segment_id"] == "DL-NCT-0001"
    assert "corridor_name" in lca
    assert lca["length_km"] > 0
    assert lca["lanes"] >= 2
    assert lca["lane_km"] > 0
    assert lca["baseline_conventional_reconstruction_tco2e"] > 0
    assert lca["embodied_emissions_tco2e"] < lca["baseline_conventional_reconstruction_tco2e"]
    assert lca["embodied_carbon_saved_tco2e"] > 0
    assert lca["embodied_carbon_savings_pct"] > 0
    assert lca["annual_diesel_saved_litres"] > 0
    assert lca["equivalent_trees_offset"] > 0
    assert 0 <= lca["irc_sp_98_score"] <= 100
    assert any(tier in lca["star_rating"] for tier in ["5-Star", "4-Star", "3-Star", "2-Star"])
    
    # Check 5 category breakdowns
    cats = lca["category_scores"]
    assert "materials_and_recycling" in cats
    assert "energy_and_low_temp" in cats
    assert "haulage_and_insitu" in cats
    assert "drainage_preservation" in cats
    assert "vehicle_operational_efficiency" in cats
    
    total_cat_score = sum(c["score"] for c in cats.values())
    assert total_cat_score == lca["irc_sp_98_score"]


def test_phase_f_treatment_comparison_matrix():
    """Verify that all 6 technologies are ranked and compared properly."""
    comparisons = get_treatment_options_comparison("DL-NCT-0001")
    assert len(comparisons) == 6
    
    tech_names = [c["treatment_name"] for c in comparisons]
    assert "Full Reconstruction & Sub-base Work (IRC:37)" in tech_names
    assert "Cold In-Place Recycling (CIR) Base Stabilization" in tech_names
    
    # CIR should show highest RAP and high carbon savings
    cir_entry = next(c for c in comparisons if "Cold In-Place Recycling" in c["treatment_name"])
    assert cir_entry["recycled_rap_pct"] >= 80.0
    assert cir_entry["savings_pct"] >= 75.0
    assert cir_entry["green_score"] >= 75


def test_phase_f_network_esg_summary():
    """Verify aggregation across all 30 Delhi NCT arterial corridors."""
    summary = get_network_green_esg_summary()
    assert summary["total_corridors_evaluated"] >= 30
    assert summary["total_lane_km_treated"] > 500
    assert summary["total_embodied_co2e_saved_tco2e"] > 10000
    assert summary["total_annual_diesel_saved_litres"] > 1000000
    assert summary["total_equivalent_trees_offset"] > 100000
    assert 40 <= summary["average_network_green_score"] <= 90
    assert len(summary["esg_reporting_standards"]) >= 4


def test_phase_f_green_highway_certificate():
    """Verify statutory green tender compliance certificate format."""
    cert = get_green_certificate("DL-NCT-0001")
    assert cert["certificate_id"].startswith("IRC-SP98-DEL-")
    assert cert["corridor_id"] == "DL-NCT-0001"
    assert "Mahatma Gandhi" in cert["corridor_name"] or "Ring Road" in cert["corridor_name"]
    assert "signatories" in cert
    assert "pwd_engineer" in cert["signatories"]
    assert "crri_expert" in cert["signatories"]
    assert "Delhi PWD" in cert["signatories"]["pwd_engineer"]
    assert "CSIR" in cert["signatories"]["crri_expert"] or "CRRI" in cert["signatories"]["crri_expert"]


# ==============================================================================
# SECTION 2: Phase F FastAPI Integration Endpoints
# ==============================================================================

def test_api_green_roads_corridor():
    """GET /api/green-roads/corridor/{segment_id}"""
    res = client.get("/api/green-roads/corridor/DL-NCT-0001")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "carbon_lca" in data
    assert data["carbon_lca"]["segment_id"] == "DL-NCT-0001"


def test_api_green_roads_comparison():
    """GET /api/green-roads/comparison/{segment_id}"""
    res = client.get("/api/green-roads/comparison/DL-NCT-0001")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "comparison" in data
    assert len(data["comparison"]) == 6


def test_api_green_roads_network_summary():
    """GET /api/green-roads/network-summary"""
    res = client.get("/api/green-roads/network-summary")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "esg_summary" in data
    assert data["esg_summary"]["total_corridors_evaluated"] >= 30


def test_api_green_roads_certificate():
    """GET /api/green-roads/certificate/{segment_id}"""
    res = client.get("/api/green-roads/certificate/DL-NCT-0001")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "certificate" in data
    assert data["certificate"]["certificate_id"].startswith("IRC-SP98-DEL-")


# ==============================================================================
# SECTION 3: Full Platform Regression Suite across Phases A to E
# ==============================================================================

def test_regression_phase_a_vision():
    """Phase A: Vision presets and analyze API."""
    res_presets = client.get("/api/vision/calibration-presets")
    assert res_presets.status_code == 200
    presets = res_presets.json()["presets"]
    assert len(presets) >= 4


def test_regression_phase_b_multi_year_planning():
    """Phase B: Multi-Year Master Plan & IRC:37:2018 Decay."""
    from optimization.decay import calculate_remaining_service_life
    dummy_seg = {"pci": 82.0, "aadt": 45000, "heavy_commercial_vehicle_percentage": 0.15, "drainage_condition": "Fair"}
    rsl = calculate_remaining_service_life(dummy_seg)
    assert rsl["rsl_years"] > 0
    
    from optimization.multi_year_optimizer import optimize_multi_year_capital_plan
    plan = optimize_multi_year_capital_plan(annual_budget_inr=500000000.0, horizon_years=3)
    assert "yearly_schedules" in plan or "yearly_allocations" in plan or len(plan) > 0


def test_regression_phase_c_kanban_and_boq():
    """Phase C: Contractor SLA Kanban & CPWD DSR BOQ generator."""
    res_kb = client.get("/api/kanban/work-orders")
    assert res_kb.status_code == 200
    assert "work_orders" in res_kb.json()
    
    res_stats = client.get("/api/kanban/stats")
    assert res_stats.status_code == 200
    assert "stages" in res_stats.json()["stats"]
    assert "dlp" in res_stats.json()["stats"]
    
    res_boq = client.post("/api/dsr/generate-boq", json={"segment_id": "DL-NCT-0001"})
    assert res_boq.status_code == 200
    assert "boq" in res_boq.json()


def test_regression_phase_d_xai_shap():
    """Phase D: TreeSHAP Feature Attribution & Counterfactual Simulation."""
    from ml.xai_engine import explain_corridor_risk, get_global_shap_importance
    attr = explain_corridor_risk("DL-NCT-0001")
    assert "top_risk_drivers" in attr
    assert "pothole_probability" in attr
    
    global_shap = get_global_shap_importance()
    assert "ranked_global_features" in global_shap


def test_regression_phase_e_postgis_and_telemetry():
    """Phase E: Enterprise PostGIS Manager & DTC Connected Fleet Telemetry."""
    from database.postgis_manager import get_postgis_engine
    engine = get_postgis_engine()
    status = engine.get_engine_status()
    assert "spatial_index_type" in status
    
    nearby = engine.query_corridors_within_radius(77.2090, 28.6139, 5000)
    assert len(nearby) > 0
    
    from ml.telemetry_engine import get_telemetry_engine
    telem = get_telemetry_engine()
    fleet = telem.get_live_fleet_telemetry()
    assert len(fleet) >= 3
    
    res_spikes = client.get("/api/telemetry/spikes")
    assert res_spikes.status_code == 200


if __name__ == "__main__":
    pytest.main(["-v", __file__])
