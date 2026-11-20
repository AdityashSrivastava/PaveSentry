"""
Comprehensive Automated Test Suite for Phase B:
Multi-Year Capital Planning & Deterioration Decay (3-Year & 5-Year Horizons)
Conforming to IRC:37:2018, IRC:82:2023, CPWD Cost Escalation & Delhi PWD Specifications.
"""
import io
import openpyxl
from fastapi.testclient import TestClient
from backend.main import app
from optimization.decay import calculate_remaining_service_life
from optimization.multi_year_optimizer import (
    optimize_multi_year_capital_plan,
    simulate_multi_year_scenarios
)
from database.db_manager import get_all_segments

client = TestClient(app)

def test_1_irc37_remaining_service_life():
    print("\n--- Test 1: Conformance to IRC:37:2018 Remaining Service Life (RSL) ---")
    segments = get_all_segments()
    assert len(segments) > 0, "Network corridors must be populated"
    sample = segments[0]
    
    rsl = calculate_remaining_service_life(sample)
    print(f"Sample Corridor: {sample.get('name')}")
    print(f"Annual Design Traffic: {rsl['annual_msa']} msa, Cumulative Consumed: {rsl['cumulative_msa_consumed']} msa")
    print(f"Fatigue Consumption: {rsl['fatigue_consumed_pct']}%, RSL: {rsl['rsl_years']} years ({rsl['rsl_category']})")
    
    assert "rsl_years" in rsl
    assert rsl["rsl_years"] >= 0.0
    assert rsl["cumulative_msa_consumed"] >= 0
    assert rsl["fatigue_consumed_pct"] >= 0.0
    assert "irc37_compliance" in rsl

    # Test API endpoint
    res = client.get(f"/api/decay/corridor/{sample['segment_id']}/rsl")
    assert res.status_code == 200, f"RSL endpoint failed: {res.text}"
    data = res.json()
    assert data["status"] == "success"
    assert data["rsl"]["segment_id"] == sample["segment_id"]
    print("PASS: IRC:37 RSL calculation verified.")

def test_2_multi_year_capital_plan_5year():
    print("\n--- Test 2: 5-Year Capital Improvement Plan (CIP) with Inflation & Spatial Clusters ---")
    res = client.post("/api/optimization/multi-year", json={
        "annual_budget": 100000000.0,
        "horizon_years": 5,
        "max_km_per_year": 160.0,
        "zone": "all",
        "discount_rate": 0.06,
        "inflation_rate": 0.055
    })
    assert res.status_code == 200, f"Multi-Year optimization failed: {res.text}"
    body = res.json()
    assert body["status"] == "success"
    plan = body["plan"]
    
    fin = plan["financial_summary"]
    print(f"Nominal 5-Year Outlay: {fin['total_invested_nominal_formatted']}")
    print(f"Discounted NPV Outlay: {fin['total_invested_npv_formatted']}")
    print(f"Total Corridors Treated: {fin['total_corridors_treated']} ({fin['total_km_treated']} km)")
    print(f"Final Managed Network PCI: {fin['final_managed_pci']} vs Do-Nothing PCI: {fin['final_do_nothing_pci']}")
    print(f"Total Spatial Mobilization Savings: {fin.get('total_mobilization_savings_formatted')}")

    assert fin["horizon_years"] == 5
    assert fin["final_managed_pci"] > fin["final_do_nothing_pci"]
    assert len(plan["yearly_plans"]) == 5
    assert len(plan["master_schedule"]) > 0
    
    # Check spatial clustering presence
    clusters = set(s.get("spatial_cluster_id") for s in plan["master_schedule"] if s.get("spatial_cluster_id"))
    print(f"Identified Spatial Mobilization Route Clusters: {clusters}")
    assert len(clusters) > 0, "Spatial route clusters should be formed for contiguous corridors"
    print("PASS: 5-Year CIP optimization and spatial clustering verified.")

def test_3_what_if_scenarios_simulation():
    print("\n--- Test 3: Multi-Scenario 'What-If' Sensitivity Simulator ---")
    res = client.post("/api/optimization/multi-year/scenarios", json={
        "annual_budget": 100000000.0,
        "horizon_years": 5,
        "max_km_per_year": 160.0,
        "discount_rate": 0.06,
        "inflation_rate": 0.055
    })
    assert res.status_code == 200, f"Scenario simulation failed: {res.text}"
    data = res.json()["scenarios_comparison"]
    
    print(f"Executive Verdict: {data['scenario_verdict']}")
    print(f"Austerity Deferred Penalty: {data['deferred_penalty_austerity_formatted']}")
    print(f"Preservation Quality Gap: +{data['pci_gap']} PCI points")

    scenarios = data["scenarios"]
    assert len(scenarios) == 3
    sc_map = {s["id"]: s for s in scenarios}
    
    assert "austerity" in sc_map
    assert "baseline" in sc_map
    assert "preservation" in sc_map

    # Preservation must achieve highest PCI, Austerity lowest
    assert sc_map["preservation"]["final_pci"] >= sc_map["baseline"]["final_pci"]
    assert sc_map["baseline"]["final_pci"] > sc_map["austerity"]["final_pci"]
    print("PASS: Multi-Scenario Sensitivity Simulator verified.")

def test_4_excel_cip_workbook_export():
    print("\n--- Test 4: Official 3-Sheet 5-Year CIP Excel (.xlsx) Export ---")
    res = client.get("/api/export/multi-year-excel?annual_budget=100000000.0&horizon_years=5&max_km_per_year=160.0")
    assert res.status_code == 200, f"Excel export failed: {res.text}"
    assert res.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    
    # Parse returned bytes with openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(res.content))
    sheet_names = wb.sheetnames
    print(f"Generated Excel Sheets: {sheet_names}")
    
    assert "Executive CIP Summary" in sheet_names
    assert "Master Work Schedule" in sheet_names
    assert "Decay & Asset Trajectory" in sheet_names
    
    ws_exec = wb["Executive CIP Summary"]
    assert ws_exec["A1"].value is not None
    
    ws_sched = wb["Master Work Schedule"]
    assert ws_sched.max_row > 5, "Schedule sheet must contain project rows"
    
    ws_decay = wb["Decay & Asset Trajectory"]
    assert ws_decay.max_row >= 7, "Decay sheet must contain trajectory progression"
    print("PASS: 3-Sheet Excel CIP Workbook validated.")

if __name__ == "__main__":
    test_1_irc37_remaining_service_life()
    test_2_multi_year_capital_plan_5year()
    test_3_what_if_scenarios_simulation()
    test_4_excel_cip_workbook_export()
    print("\n=======================================================")
    print("ALL PHASE B VERIFICATION TESTS COMPLETED SUCCESSFULLY!")
    print("=======================================================\n")
