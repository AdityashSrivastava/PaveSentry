import sys
import io
import requests
import numpy as np
from PIL import Image

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

BASE = "http://127.0.0.1:9005"

print("=" * 70)
print("TESTING PHASE A: COMPUTER VISION POTHOLE CHARACTERIZATION")
print("=" * 70)

# 1. Non-road rejection
blank_img = Image.fromarray(np.full((300, 300, 3), 245, dtype=np.uint8))
buf1 = io.BytesIO()
blank_img.save(buf1, format="JPEG")
buf1.seek(0)
res_blank = requests.post(f"{BASE}/api/vision/analyze", files={"file": ("blank.jpg", buf1, "image/jpeg")})
assert res_blank.status_code == 200, f"Blank failed: {res_blank.text}"
d_blank = res_blank.json()
assert d_blank["is_defect"] is False, "Should reject non-road image"
print("  [PASS] Non-road rejection verified:", d_blank["verification_status"])

# 2. Road defect detection & depth characterization
w, h = 640, 480
road = np.random.normal(110, 10, (h, w, 3)).clip(0, 255).astype(np.uint8)
yy, xx = np.ogrid[:h, :w]
mask = ((xx - 320)**2 / (80**2) + (yy - 240)**2 / (55**2)) <= 1.0
road[mask] = (road[mask] * 0.40).astype(np.uint8)
img = Image.fromarray(road)
buf2 = io.BytesIO()
img.save(buf2, format="JPEG")
buf2.seek(0)
res_defect = requests.post(f"{BASE}/api/vision/analyze", files={"file": ("pothole.jpg", buf2, "image/jpeg")})
assert res_defect.status_code == 200, f"Defect failed: {res_defect.text}"
d_defect = res_defect.json()
assert d_defect["is_defect"] is True, "Should verify defect"
assert d_defect["surface_area_cm2"] > 0, "Should calculate surface area"
assert d_defect["estimated_depth_mm"] > 0, "Should calculate depth"
assert d_defect["depth_category"] in ["Shallow (<25mm)", "Medium (25-50mm)", "Severe (>50mm)"], "Invalid depth category"
assert d_defect["annotated_image_url"] is not None, "Should provide annotated overlay"
print(f"  [PASS] Defect verified: {d_defect['verification_status']}")
print(f"         Confidence: {d_defect['confidence']*100:.1f}%")
print(f"         Surface Area: {d_defect['surface_area_cm2']} cm2")
print(f"         Depth: {d_defect['estimated_depth_mm']} mm [{d_defect['depth_category']}]")
print(f"         Annotated Overlay URL: {d_defect['annotated_image_url']}")

# 3. Pothole reporting with automated AI grading
login_res = requests.post(f"{BASE}/api/auth/login", json={"email": "engineer@pwd.delhi.gov.in", "password": "delhi2026pwd"})
login_data = login_res.json()
token = login_data.get("access_token") or login_data.get("token")
headers = {"Authorization": f"Bearer {token}"}

buf2.seek(0)
res_rep = requests.post(
    f"{BASE}/api/potholes/report",
    headers=headers,
    data={"latitude": 28.5672, "longitude": 77.2100, "road_name": "Ring Road AIIMS Test"},
    files={"photo": ("field_pothole.jpg", buf2, "image/jpeg")}
)
assert res_rep.status_code == 200, f"Report failed: {res_rep.text}"
d_rep = res_rep.json()
assert d_rep["report"]["cv_verified"] == 1, "Report should record cv_verified = 1"
assert d_rep["report"]["cv_area_cm2"] > 0, "Report should record cv_area_cm2"
print(f"  [PASS] Pothole report registered with AI auto-grading: {d_rep['report']['report_id']}")
print(f"         CV Area: {d_rep['report']['cv_area_cm2']} cm2 | Category: {d_rep['report']['cv_depth_category']}")

print("\n" + "=" * 70)
print("TESTING PHASE B: MULTI-YEAR CAPITAL PLANNING & DETERIORATION DECAY")
print("=" * 70)

# 4. Corridor Weibull decay & Cost of Inaction
res_decay = requests.get(f"{BASE}/api/decay/corridor/DL-NCT-0001")
assert res_decay.status_code == 200, f"Corridor decay failed: {res_decay.text}"
d_dec = res_decay.json()
assert len(d_dec["weibull_curve"]) == 6, "Should have 6 years in Weibull trajectory"
assert len(d_dec["cost_of_inaction"]["yearly_cost_trajectory"]) == 5, "Should have 5 years inaction trajectory"
print(f"  [PASS] Corridor decay retrieved for: {d_dec['road_name']}")
print(f"         Year 3 Penalty %: {d_dec['cost_of_inaction']['year_3_penalty_pct']}%")
print(f"         Decision Headline: {d_dec['cost_of_inaction']['decision_headline']}")

# 5. Network-wide Cost of Inaction simulation
res_inact = requests.post(f"{BASE}/api/decay/simulate-inaction", json={"horizon_years": 5, "zone": "all"})
assert res_inact.status_code == 200, f"Network inaction failed: {res_inact.text}"
d_inact = res_inact.json()
assert len(d_inact["simulation"]["yearly_network_costs"]) == 5, "Should have 5 yearly costs"
print(f"  [PASS] Network Cost of Inaction simulated:")
print(f"         Year 3 Penalty: {d_inact['simulation']['year_3_penalty_pct']}% ({d_inact['simulation']['year_3_penalty_formatted']})")
print(f"         Executive Summary: {d_inact['simulation']['executive_summary']}")

# 6. Multi-year Capital Optimization (3-Year and 5-Year Master Plans)
res_cip3 = requests.post(f"{BASE}/api/optimization/multi-year", json={"annual_budget": 100000000.0, "horizon_years": 3, "max_km_per_year": 140.0})
assert res_cip3.status_code == 200, f"3-Year CIP failed: {res_cip3.text}"
d_cip3 = res_cip3.json()["plan"]
assert len(d_cip3["yearly_plans"]) == 3, "Should produce 3 yearly plans"
print(f"  [PASS] 3-Year CIP Master Plan optimized. Total projects: {d_cip3['financial_summary']['total_corridors_treated']}")

res_cip5 = requests.post(f"{BASE}/api/optimization/multi-year", json={"annual_budget": 100000000.0, "horizon_years": 5, "max_km_per_year": 140.0})
assert res_cip5.status_code == 200, f"5-Year CIP failed: {res_cip5.text}"
d_cip5 = res_cip5.json()["plan"]
assert len(d_cip5["yearly_plans"]) == 5, "Should produce 5 yearly plans"
print(f"  [PASS] 5-Year CIP Master Plan optimized.")
print(f"         Initial avg PCI: {d_cip5['financial_summary']['initial_avg_pci']}")
print(f"         Managed Final PCI: {d_cip5['financial_summary']['final_managed_pci']} vs Do-Nothing: {d_cip5['financial_summary']['final_do_nothing_pci']}")
print(f"         Net Capital Savings: {d_cip5['financial_summary']['total_net_savings_formatted']} ({d_cip5['financial_summary']['roi_percentage']}% ROI)")
print(f"         Executive Verdict: {d_cip5['financial_summary']['executive_verdict']}")

print("\n" + "=" * 70)
print("SUCCESS: ALL PHASE A AND PHASE B CAPABILITIES VERIFIED 100% OPERATIONAL")
print("=" * 70)
