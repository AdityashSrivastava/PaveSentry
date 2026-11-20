"""
Comprehensive Verification Test Suite for Phase C:
Contractor SLA & Work Order Lifecycle Kanban Board,
CPWD DSR 2023-24 Bill of Quantities (BOQ),
and Defect Liability Period (DLP) 3-Year Warranty Watchdog.
"""
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from database.db_manager import get_work_orders, get_work_order_by_id, get_connection
from backend.auth import create_access_token, seed_default_users

# Ensure default users exist
seed_default_users()

client = TestClient(app)

def get_auth_token():
    return create_access_token({"sub": "usr-pwd-001", "role": "pwd_engineer", "division": "PWD Central Division (M-21)"})

def test_1_kanban_work_orders_lifecycle():
    print("\n--- Test 1: Kanban Work Order Lifecycle & 5-Stage Progression ---")
    res = client.get("/api/kanban/work-orders")
    assert res.status_code == 200, f"Failed to get work orders: {res.text}"
    data = res.json()
    assert data["status"] == "success"
    
    orders = data["work_orders"]
    assert len(orders) >= 7, "Initial seed work orders must be present"
    
    stages_present = set(o["stage"] for o in orders)
    expected_stages = {"Reported", "Inspected", "Tender Issued", "Under Repair", "Audited & Closed"}
    assert expected_stages.issubset(stages_present), f"All 5 Kanban stages must be populated. Found: {stages_present}"
    
    stats = data["stats"]
    print(f"Total Work Orders: {stats['total_work_orders']}")
    print(f"Stage Breakdown: {stats['stages']}")
    print(f"SLA Compliance Rate: {stats['sla']['compliance_pct']}% (On Track: {stats['sla']['on_track']})")
    
    # Create a new test work order
    create_res = client.post("/api/kanban/work-orders", json={
        "segment_id": "DL-PW-0001",
        "road_name": "Ring Road Phase C Test Stretch",
        "city_zone": "Central Delhi",
        "contractor_name": "Larsen & Toubro Ltd",
        "contract_value_inr": 15000000.0,
        "stage": "Reported",
        "treatment_type": "Bituminous Concrete (BC) Mill & Overlay (IRC:82)",
        "priority_level": "High",
        "sla_target_days": 14,
        "dlp_months": 36,
        "notes": "Automated verification test work order"
    })
    assert create_res.status_code == 200, f"Create work order failed: {create_res.text}"
    new_wo = create_res.json()["work_order"]
    wo_id = new_wo["work_order_id"]
    assert new_wo["stage"] == "Reported"
    print(f"Created Work Order: {wo_id} ({new_wo['road_name']})")

    # Progress through stages: Reported -> Inspected -> Tender Issued -> Under Repair -> Audited & Closed
    stages_to_test = ["Inspected", "Tender Issued", "Under Repair", "Audited & Closed"]
    for next_st in stages_to_test:
        step_res = client.put(f"/api/kanban/work-orders/{wo_id}/stage", json={
            "stage": next_st,
            "notes": f"Advanced to {next_st} via test suite",
            "updated_by": "Test Engineer"
        })
        assert step_res.status_code == 200, f"Failed advancing to {next_st}: {step_res.text}"
        updated = step_res.json()["work_order"]
        assert updated["stage"] == next_st
        print(f"  [➔] Advanced {wo_id} to: {next_st}")

    # Check that Audited & Closed automatically activated 3-Year DLP Warranty
    closed_wo = get_work_order_by_id(wo_id)
    assert closed_wo["dlp_status"] == "Active Warranty"
    assert closed_wo["dlp_start_date"] is not None
    assert closed_wo["dlp_end_date"] is not None
    assert closed_wo["dlp_months"] == 36
    print(f"PASS: Work order lifecycle from Reported to Audited & Closed with 36-Month DLP verified.")

def test_2_cpwd_dsr_catalog_and_boq():
    print("\n--- Test 2: CPWD DSR 2023-24 Road Work Sub-Head 16 & BOQ Generator ---")
    # 1. Catalog
    res = client.get("/api/dsr/catalog")
    assert res.status_code == 200
    catalog = res.json()
    assert catalog["delhi_cost_index"] == 1.085
    items = catalog["items"]
    assert len(items) >= 10
    
    item_codes = [i["item_code"] for i in items]
    assert "16.45" in item_codes   # Subgrade
    assert "16.48" in item_codes   # WMM
    assert "16.71.1" in item_codes # DBM
    assert "16.73.1" in item_codes # BC
    assert "16.89.1" in item_codes # Micro-Surfacing
    assert "16.92" in item_codes   # Crack Sealing
    print(f"Available CPWD DSR Sub-Head 16 Items: {len(items)} items (+8.5% Delhi Index calibrated)")

    # 2. BOQ Generation
    boq_res = client.post("/api/dsr/generate-boq", json={
        "road_name": "Outer Ring Road Heavy Arterial",
        "length_km": 3.0,
        "lanes": 6,
        "treatment_type": "Full Reconstruction & Sub-base Work (IRC:37)",
        "city_zone": "South Delhi"
    })
    assert boq_res.status_code == 200, f"BOQ generation failed: {boq_res.text}"
    boq = boq_res.json()["boq"]
    
    fin = boq["financial_breakdown"]
    print(f"Corridor Pavement Area: {boq['pavement_area_sqm']:,.2f} sqm")
    print(f"Base DSR Subtotal: ₹{fin['base_dsr_subtotal_inr']:,.2f}")
    print(f"Delhi Cost Index Addition (+8.5%): ₹{fin['delhi_index_addition_inr']:,.2f}")
    print(f"Gross Tender Value (incl 10% Contractor Profit & 18% GST): {fin['gross_tender_value_formatted']}")
    print(f"DLP Warranty Clause: {boq['dlp_warranty_label']}")

    assert fin["gross_tender_value_inr"] > fin["base_dsr_subtotal_inr"]
    assert boq["dlp_warranty_months"] == 36
    assert len(boq["items"]) >= 5
    print("PASS: CPWD DSR Rate Analysis & BOQ Generator verified.")

def test_3_dlp_warranty_watchdog_and_penalties():
    print("\n--- Test 3: Defect Liability Period (DLP) Warranty Watchdog & Penalty Enforcement ---")
    # Retrieve active DLP contracts
    res = client.get("/api/dlp/contracts")
    assert res.status_code == 200
    contracts = res.json()["contracts"]
    assert len(contracts) >= 2, "Active DLP contracts must be tracked"
    print(f"Tracked Active DLP Warranty Contracts: {len(contracts)}")
    for c in contracts:
        print(f"  - {c['road_name']} | Contractor: {c['contractor_name']} | Days Left: {c['days_remaining']}d ({c['dlp_status']})")

    # Report a severe defect on active DLP corridor (DL-PW-0003 Barapullah Elevated Corridor)
    token = get_auth_token()
    rep_res = client.post(
        "/api/potholes/report",
        data={
            "latitude": 28.588,
            "longitude": 77.255,
            "road_name": "Barapullah Elevated Corridor",
            "severity": "Severe",
            "depth_mm": 58.0,
            "width_cm": 65.0,
            "notes": "Severe cavitation recurrence on Barapullah corridor"
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    assert rep_res.status_code == 200, f"Pothole report failed: {rep_res.text}"
    rep_data = rep_res.json()
    
    # Watchdog should automatically detect warranty breach
    alert = rep_data.get("dlp_breach_alert")
    assert alert is not None, "DLP breach alert must be triggered on active warranty corridor"
    print(f"ALERT TRIGGERED: {alert['incident_id']}")
    print(f"Target Contractor: {alert['contractor_name']}")
    print(f"Levied Penalty: {alert['penalty_amount_formatted']}")
    print(f"Clause Applied: {alert['clause_applied']}")
    print(f"Rectification Deadline (48h): {alert['rectification_deadline']}")
    
    assert "CPWD GCC Clause 17" in alert["clause_applied"]
    assert alert["penalty_amount_inr"] > 0
    assert "SHOW CAUSE NOTICE" in alert["show_cause_notice"]

    # Verify incident recorded in DLP incidents registry
    inc_res = client.get("/api/dlp/incidents")
    assert inc_res.status_code == 200
    incidents = inc_res.json()["incidents"]
    assert len(incidents) > 0
    test_incident = next((i for i in incidents if i["incident_id"] == alert["incident_id"]), None)
    assert test_incident is not None

    # Resolve incident: contractor rectifies within 48h
    resolv_res = client.put(f"/api/dlp/incidents/{alert['incident_id']}/status", json={
        "status": "Rectified by Contractor",
        "notes": "Verified by CSIR-CRRI field auditor"
    })
    assert resolv_res.status_code == 200
    print("PASS: DLP Watchdog Clause 17 penalty notice and resolution verified.")

def test_4_kanban_stats_and_filters():
    print("\n--- Test 4: Real-Time Kanban KPIs & Division Filtering ---")
    res_all = client.get("/api/kanban/stats")
    assert res_all.status_code == 200
    stats_all = res_all.json()["stats"]
    assert stats_all["total_work_orders"] >= 7
    print(f"Total Work Orders (All Delhi): {stats_all['total_work_orders']}")
    print(f"Total Committed Value: {stats_all['total_contract_value_formatted']}")

    # Filter by specific division (South Delhi)
    res_south = client.get("/api/kanban/work-orders?zone=South Delhi")
    assert res_south.status_code == 200
    south_orders = res_south.json()["work_orders"]
    for o in south_orders:
        assert o["city_zone"] == "South Delhi"
    print(f"South Delhi Division Work Orders Filter: {len(south_orders)} orders")

    # SLA filter
    res_breached = client.get("/api/kanban/work-orders?sla_status=SLA Breached")
    assert res_breached.status_code == 200
    breached_orders = res_breached.json()["work_orders"]
    for o in breached_orders:
        assert o["sla_status"] == "SLA Breached"
    print(f"SLA Breached Filter: {len(breached_orders)} orders flagged for executive escalation")
    print("PASS: Real-Time Kanban KPIs & Division Filtering verified.")

if __name__ == "__main__":
    test_1_kanban_work_orders_lifecycle()
    test_2_cpwd_dsr_catalog_and_boq()
    test_3_dlp_warranty_watchdog_and_penalties()
    test_4_kanban_stats_and_filters()
    print("\n=======================================================")
    print("ALL PHASE C VERIFICATION TESTS COMPLETED SUCCESSFULLY!")
    print("=======================================================\n")
