import io
import sys
import numpy as np
from PIL import Image
import cv2
from fastapi.testclient import TestClient
from backend.main import app

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

client = TestClient(app)

print("=" * 75)
print("COMPREHENSIVE VERIFICATION: PHASE A ADVANCED COMPUTER VISION ENGINE")
print("=" * 75)

# 1. Test calibration presets endpoint
res_presets = client.get("/api/vision/calibration-presets")
assert res_presets.status_code == 200, f"Presets failed: {res_presets.text}"
d_presets = res_presets.json()
assert len(d_presets["presets"]) >= 4, "Should have at least 4 calibration presets"
print(f"  [PASS] Calibration presets available: {[p['name'] for p in d_presets['presets']]}")

# 2. Test non-road rejection
blank_img = Image.fromarray(np.full((320, 320, 3), 245, dtype=np.uint8))
buf_blank = io.BytesIO()
blank_img.save(buf_blank, format="JPEG")
buf_blank.seek(0)

res_blank = client.post(
    "/api/vision/analyze",
    files={"file": ("blank.jpg", buf_blank, "image/jpeg")}
)
assert res_blank.status_code == 200, f"Blank failed: {res_blank.text}"
d_blank = res_blank.json()
assert d_blank["is_defect"] is False, "Should reject non-road image"
print(f"  [PASS] False-positive rejection: {d_blank['verification_status']}")
print(f"         Reason: {d_blank['rejection_reason']}")

# 3. Test genuine defect with photogrammetric perspective calibration
w, h = 640, 480
road = np.random.normal(110, 10, (h, w, 3)).clip(0, 255).astype(np.uint8)
yy, xx = np.ogrid[:h, :w]
mask = ((xx - 320)**2 / (80**2) + (yy - 250)**2 / (50**2)) <= 1.0
road[mask] = (road[mask] * 0.38).astype(np.uint8)
img = Image.fromarray(road)

buf_defect = io.BytesIO()
img.save(buf_defect, format="JPEG")
buf_defect.seek(0)

res_defect = client.post(
    "/api/vision/analyze",
    data={
        "calibration_mode": "camera_geometry",
        "camera_height_m": 1.35,
        "camera_tilt_deg": 18.0
    },
    files={"file": ("road_pothole.jpg", buf_defect, "image/jpeg")}
)
assert res_defect.status_code == 200, f"Defect failed: {res_defect.text}"
d_defect = res_defect.json()
assert d_defect["is_defect"] is True, "Should verify road defect"
assert d_defect["surface_area_cm2"] > 0, "Should compute metric surface area"
assert d_defect["estimated_depth_mm"] > 0, "Should estimate photometric depth"
assert "astm_total_deduct_points" in d_defect, "Should calculate ASTM deduct score"
assert d_defect["annotated_image_url"] is not None, "Should generate HUD overlay"

print(f"  [PASS] Genuine Defect Characterized:")
print(f"         Primary Distress Type: {d_defect['primary_distress_type']}")
print(f"         Surface Area: {d_defect['surface_area_cm2']} cm2 | Depth: {d_defect['estimated_depth_mm']} mm [{d_defect['depth_category']}]")
print(f"         ASTM D6433 Deduct Score: -{d_defect['astm_total_deduct_points']} points")
print(f"         Calibration Preset: {d_defect['calibration_info']['preset']}")
print(f"         Annotated Overlay: {d_defect['annotated_image_url']}")

# 4. Test Dashcam Video Stream Processing & Deduplication
fourcc = cv2.VideoWriter_fourcc(*'mp4v')
buf_vid = io.BytesIO()
temp_vid_path = "temp_test_stream.mp4"
out = cv2.VideoWriter(temp_vid_path, fourcc, 10.0, (w, h))

for f_i in range(20):  # 2.0 seconds
    f_arr = np.random.normal(110, 8, (h, w, 3)).clip(0, 255).astype(np.uint8)
    y_c = int(190 + f_i * 7)
    if y_c < h - 40:
        yy, xx = np.ogrid[:h, :w]
        m = ((xx - 320)**2 / (60**2) + (yy - y_c)**2 / (40**2)) <= 1.0
        f_arr[m] = (f_arr[m] * 0.40).astype(np.uint8)
    out.write(f_arr)
out.release()

with open(temp_vid_path, "rb") as vf:
    vid_bytes = vf.read()

import os
if os.path.exists(temp_vid_path):
    os.remove(temp_vid_path)

res_vid = client.post(
    "/api/vision/analyze-video",
    data={
        "sample_fps": 2.0,
        "max_duration_sec": 10.0,
        "camera_height_m": 1.20,
        "camera_tilt_deg": 14.0
    },
    files={"file": ("dashcam_inspection.mp4", io.BytesIO(vid_bytes), "video/mp4")}
)
assert res_vid.status_code == 200, f"Video analyze failed: {res_vid.text}"
d_vid = res_vid.json()
assert d_vid["frames_analyzed"] >= 2, "Should sample multiple frames"
assert d_vid["unique_defects_count"] == 1, f"Should deduplicate single moving pothole into 1 defect, got {d_vid['unique_defects_count']}"
assert len(d_vid["unique_defects"]) == 1, "Should have 1 unique defect record"
assert d_vid["unique_defects"][0]["hero_image_url"] is not None, "Should extract hero keyframe"

print(f"  [PASS] Dashcam Moving Survey Video Processing & Deduplication:")
print(f"         Video Duration: {d_vid['video_duration_sec']}s | Frames Sampled: {d_vid['frames_analyzed']}")
print(f"         Unique Defects Count: {d_vid['unique_defects_count']} (Deduplication 100% Verified)")
print(f"         Survey Condition Rating: {d_vid['survey_rating']}")
print(f"         Recommended Action: {d_vid['recommended_action']}")
print(f"         Hero Snapshot Keyframe: {d_vid['unique_defects'][0]['hero_image_url']}")

print("\n" + "=" * 75)
print("SUCCESS: PHASE A FINISHED WITH FULL ASTM D6433 & VIDEO CAPABILITIES")
print("=" * 75)
