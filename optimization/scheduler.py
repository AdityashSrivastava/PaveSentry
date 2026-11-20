import sys
from pathlib import Path

import pandas as pd

# Ensure UTF-8 output on Windows terminals
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

from database.db_manager import get_all_segments


def optimize_maintenance_schedule(annual_budget_inr=100000000, max_km_per_month=15.0, max_months=12, zone=None):
    """
    Optimizes segment selection and monthly schedule under budget (₹ INR) and crew constraints.
    Uses Priority-to-Cost Efficiency Ratio Ranking (Greedy Knapsack Optimization) for Delhi NCT network.
    Default annual budget: ₹10 Crores (₹100,000,000).
    Optionally filters by administrative zone/division (e.g. South Delhi, NDMC, East Delhi & Shahdara, North West).
    """
    segments = get_all_segments(zone=zone)
    if not segments:
        return {"scheduled_segments": [], "summary": {"message": "No road segments found for the selected zone/criteria."}}
        
    df = pd.DataFrame(segments)
    
    # Filter segments needing intervention (High & Medium risk, or low PCI)
    candidate_df = df[(df["predicted_risk_level"].isin(["High", "Medium"])) | (df["pci"] < 75)].copy()
    
    if candidate_df.empty:
        return {"scheduled_segments": [], "summary": {"message": "No road segments currently require urgent maintenance."}}
        
    # Cost effectiveness ratio: Priority Score / Cost (₹ in Lakhs)
    candidate_df["cost_efficiency"] = candidate_df["priority_score"] / (candidate_df["est_preventive_cost_inr"] / 100000.0 + 0.1)
    
    # Sort by priority score descending & cost efficiency
    candidate_df.sort_values(by=["priority_score", "cost_efficiency"], ascending=[False, False], inplace=True)
    
    scheduled_list = []
    current_month = 1
    monthly_km_used = 0.0
    total_spent = 0.0
    total_reactive_cost_avoided = 0.0
    
    for _, row in candidate_df.iterrows():
        cost = row["est_preventive_cost_inr"]
        length = row["length_km"]
        reactive_cost = row["est_reactive_cost_inr"]
        
        # Check budget
        if total_spent + cost > annual_budget_inr:
            continue # Skip if exceeds total budget
            
        # Check monthly crew capacity
        if monthly_km_used + length > max_km_per_month:
            current_month += 1
            monthly_km_used = 0.0
            
        if current_month > max_months:
            break # Exceeded 12-month scheduling horizon
            
        total_spent += cost
        total_reactive_cost_avoided += reactive_cost
        monthly_km_used += length
        
        scheduled_item = dict(row)
        scheduled_item["scheduled_month"] = f"Month {current_month}"
        scheduled_item["month_number"] = current_month
        scheduled_item["allocated_cost_inr"] = cost
        scheduled_item["reactive_avoided_inr"] = reactive_cost
        scheduled_item["net_savings_inr"] = round(reactive_cost - cost, 2)
        
        # Contractor bidding & CSIR-CRRI audit metadata
        timeline_days = max(30, min(120, int(round(length * 16.0))))
        scheduled_item["tender_timeline_days"] = timeline_days
        seg_suffix = str(scheduled_item.get("segment_id", "0000"))[-4:]
        pci_val = int(scheduled_item.get("pci", 50))
        scheduled_item["crri_compliance_code"] = f"CRRI-NCT-2026-PCI{pci_val}-{seg_suffix}"
        
        scheduled_list.append(scheduled_item)
        
    total_savings = round(total_reactive_cost_avoided - total_spent, 2)
    roi_pct = round((total_savings / (total_spent + 1.0)) * 100.0, 1)
    
    fmt_spent = f"₹{(total_spent / 10000000):.2f} Cr" if total_spent >= 10000000 else f"₹{(total_spent / 100000):.2f} L"
    fmt_savings = f"₹{(total_savings / 10000000):.2f} Cr" if total_savings >= 10000000 else f"₹{(total_savings / 100000):.2f} L"
    
    summary = {
        "annual_budget_inr": annual_budget_inr,
        "selected_zone": zone or "all",
        "total_spent_inr": round(total_spent, 2),
        "total_spent_formatted": fmt_spent,
        "remaining_budget_inr": round(annual_budget_inr - total_spent, 2),
        "total_reactive_cost_avoided_inr": round(total_reactive_cost_avoided, 2),
        "total_net_savings_inr": total_savings,
        "total_savings_formatted": fmt_savings,
        "roi_percentage": roi_pct,
        "scheduled_count": len(scheduled_list),
        "total_km_repaired": round(sum(s["length_km"] for s in scheduled_list), 2)
    }
    
    return {
        "scheduled_segments": scheduled_list,
        "summary": summary
    }

if __name__ == "__main__":
    res = optimize_maintenance_schedule(annual_budget_inr=100000000)
    print("Optimization Summary:", res["summary"])
    print(f"Scheduled {len(res['scheduled_segments'])} segments.")
