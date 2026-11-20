"""
test_phase_d_complete.py
Comprehensive End-to-End Test Suite for Phase D: Explainable AI (XAI) & TreeSHAP Feature Attribution.
Includes local attribution, global importance, counterfactual simulation, audit memo generation,
and regression verification of Phases A, B, and C.
"""
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))

from backend.main import app
from ml.xai_engine import (
    explain_corridor_risk,
    get_global_shap_importance,
    simulate_intervention_counterfactual,
    ExplainableAIEngine
)

client = TestClient(app)

def test_01_local_shap_attribution():
    """Validates local TreeSHAP attribution and percentage influence calculation for a Delhi corridor."""
    corridor_id = "DL-NCT-0001"
    res = client.get(f"/api/xai/corridor/{corridor_id}")
    assert res.status_code == 200, f"Failed local SHAP endpoint: {res.text}"
    data = res.json()
    assert data["status"] == "success"
    
    exp = data["explanation"]
    assert exp["segment_id"] == corridor_id
    assert "road_name" in exp
    assert "pothole_probability" in exp
    assert 0.0 <= exp["pothole_probability"] <= 1.0
    assert "base_expected_value" in exp
    assert exp["total_features_analyzed"] == 17
    
    # Check waterfall items
    waterfall = exp["waterfall_attribution"]
    assert len(waterfall) == 17
    total_influence = sum(f["influence_pct"] for f in waterfall)
    # Sum of normalized relative percentages should be ~100%
    assert 98.0 <= total_influence <= 102.0, f"Expected total influence ~100%, got {total_influence}"
    
    # Validate top risk drivers
    drivers = exp["top_risk_drivers"]
    assert len(drivers) > 0
    for d in drivers:
        assert d["shap_value"] > 0
        assert d["is_risk_driver"] is True
        assert len(d["engineering_rationale"]) > 10
        assert "display_name" in d
        assert "category" in d

    # Validate audit justification narrative
    narrative = exp["audit_justification"]
    assert "CSIR-CRRI" in narrative
    assert "IRC:37:2018" in narrative
    assert corridor_id in narrative or exp["road_name"] in narrative
    print(f"\n[Test 1 PASSED] Corridor {corridor_id} TreeSHAP explanation verified. Top driver: {drivers[0]['display_name']} (+{drivers[0]['influence_pct']}%)")


def test_02_global_shap_importance():
    """Validates network-wide global feature importance ranking across all 350 Delhi NCT corridors."""
    res = client.get("/api/xai/global-importance")
    assert res.status_code == 200, f"Failed global importance endpoint: {res.text}"
    data = res.json()
    assert data["status"] == "success"
    assert data["total_corridors_analyzed"] >= 300
    
    ranked = data["ranked_global_features"]
    assert len(ranked) == 17
    total_pct = sum(f["global_importance_pct"] for f in ranked)
    assert 98.0 <= total_pct <= 102.0, f"Expected total global importance ~100%, got {total_pct}"
    
    # Top driver must be legitimate
    top_driver = data["top_macro_driver"]
    assert top_driver is not None and len(top_driver) > 0
    print(f"\n[Test 2 PASSED] Global TreeSHAP analyzed {data['total_corridors_analyzed']} corridors. Top macro driver: {top_driver} ({data['top_macro_driver_pct']}%)")


def test_03_counterfactual_sensitivity_simulation():
    """Validates What-If counterfactual simulation reducing risk via commercial traffic diversion and drainage."""
    # Find a high or medium risk corridor
    corridor_id = "DL-NCT-0001"
    
    # Apply engineering interventions
    payload = {
        "segment_id": corridor_id,
        "overrides": {
            "heavy_vehicle_pct": 5.0,
            "annual_rainfall_mm": 500.0,
            "pothole_count": 0,
            "crack_density_pct": 2.0
        }
    }
    res = client.post("/api/xai/counterfactual", json=payload)
    assert res.status_code == 200, f"Counterfactual failed: {res.text}"
    data = res.json()
    assert data["status"] == "success"
    
    cf = data["counterfactual"]
    assert cf["segment_id"] == corridor_id
    assert cf["baseline_probability"] >= cf["counterfactual_probability"]
    assert cf["percentage_risk_drop"] >= 0.0
    assert "verdict" in cf
    print(f"\n[Test 3 PASSED] Counterfactual simulation: failure probability dropped from {cf['baseline_probability']:.1%} to {cf['counterfactual_probability']:.1%} (-{cf['percentage_risk_drop']}%)")


def test_04_cvc_csir_crri_defensible_audit_memo():
    """Validates the official CVC / CSIR-CRRI Defensible AI Justification Memorandum generation."""
    corridor_id = "DL-NCT-0001"
    res = client.get(f"/api/xai/audit-report/{corridor_id}")
    assert res.status_code == 200, f"Audit memo failed: {res.text}"
    data = res.json()
    assert data["status"] == "success"
    
    memo = data["audit_memo"]
    assert "GOVERNMENT OF NCT OF DELHI" in memo["document_title"]
    assert memo["corridor_id"] == corridor_id
    assert "PWD/XAI-AUDIT" in memo["memo_ref"]
    assert len(memo["top_drivers"]) > 0
    assert len(memo["governance_compliance"]) >= 3
    assert "signoff_block" in memo
    assert memo["signoff_block"]["status"] == "APPROVED FOR CAPITAL REPAIR ALLOCATION"
    print(f"\n[Test 4 PASSED] Official CVC Defensible Audit Memo verified. Ref: {memo['memo_ref']}")


def test_05_regression_phases_a_b_c():
    """Validates that Phase A (Vision), Phase B (Multi-Year CIP), and Phase C (Kanban & DSR) remain 100% operational."""
    # Phase A: Vision Calibration Presets & Analyzer
    res_presets = client.get("/api/vision/calibration-presets")
    assert res_presets.status_code == 200
    assert len(res_presets.json()["presets"]) >= 4
    
    import io
    from PIL import Image
    import numpy as np
    blank_img = Image.fromarray(np.full((320, 320, 3), 245, dtype=np.uint8))
    buf_blank = io.BytesIO()
    blank_img.save(buf_blank, format="JPEG")
    buf_blank.seek(0)
    res_a = client.post("/api/vision/analyze", files={"file": ("blank.jpg", buf_blank, "image/jpeg")})
    assert res_a.status_code == 200
    assert res_a.json()["is_defect"] is False
    print("\n[Regression A PASSED] YOLOv8 Edge Vision Detector operational.")

    # Phase B: Multi-Year Capital Planning
    res_b = client.post("/api/optimization/multi-year", json={
        "annual_budget": 100000000.0,
        "horizon_years": 3,
        "max_km_per_year": 150.0,
        "discount_rate": 0.06
    })
    assert res_b.status_code == 200
    plan = res_b.json()["plan"]
    assert len(plan["master_schedule"]) > 0
    print(f"[Regression B PASSED] Multi-Year CIP 3-Year Plan generated {len(plan['master_schedule'])} scheduled projects.")

    # Phase C: CPWD DSR Catalog & BOQ
    res_c_boq = client.post("/api/dsr/generate-boq", json={
        "road_name": "Ring Road Phase C Test",
        "length_km": 3.0,
        "lanes": 4,
        "treatment_type": "Preventive Micro-Surfacing & Slurry Seal (IRC:SP:81)"
    })
    assert res_c_boq.status_code == 200
    boq = res_c_boq.json()["boq"]
    assert len(boq["items"]) > 0
    assert boq["financial_breakdown"]["gross_tender_value_inr"] > 0
    print(f"[Regression C PASSED] CPWD DSR BOQ generated: Grand Total ₹{boq['financial_breakdown']['gross_tender_value_inr']:,.2f}.")

if __name__ == "__main__":
    pytest.main(["-v", "test_phase_d_complete.py"])

