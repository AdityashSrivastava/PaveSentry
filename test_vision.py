import sys
import numpy as np
from PIL import Image
from ml.vision_detector import get_vision_detector

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

d = get_vision_detector()

print("=" * 65)
print("TESTING PAVESENTRY COMPUTER VISION ENGINE (PHASE A)")
print("=" * 65)

# 1. Non-road rejection
blank = Image.fromarray(np.full((300, 300, 3), 245, dtype=np.uint8))
res1 = d.analyze_image(blank)
print(f"1. Non-road Rejection: is_defect={res1['is_defect']} | Status={res1['verification_status']}")
assert res1['is_defect'] is False, "Should reject blank non-road image"

# Helper function
def make_pothole_img(mult):
    w, h = 640, 480
    road = np.random.normal(110, 8, (h, w, 3)).clip(0, 255).astype(np.uint8)
    yy, xx = np.ogrid[:h, :w]
    mask = ((xx - 320)**2 / (75**2) + (yy - 240)**2 / (50**2)) <= 1.0
    road[mask] = (road[mask] * mult).astype(np.uint8)
    return Image.fromarray(road)

# 2. Shallow pothole (<25 mm)
res2 = d.analyze_image(make_pothole_img(0.80))
print(f"2. Shallow Defect: is_defect={res2['is_defect']} | Area={res2['surface_area_cm2']} cm2 | Depth={res2['estimated_depth_mm']} mm | Cat={res2['depth_category']}")
assert res2['is_defect'] is True
assert res2['depth_category'] == 'Shallow (<25mm)'
assert res2['estimated_depth_mm'] < 25.0

# 3. Medium pothole (25-50 mm)
res3 = d.analyze_image(make_pothole_img(0.55))
print(f"3. Medium Defect:  is_defect={res3['is_defect']} | Area={res3['surface_area_cm2']} cm2 | Depth={res3['estimated_depth_mm']} mm | Cat={res3['depth_category']}")
assert res3['is_defect'] is True
assert res3['depth_category'] == 'Medium (25-50mm)'
assert 25.0 <= res3['estimated_depth_mm'] <= 50.0

# 4. Severe crater (>50 mm)
res4 = d.analyze_image(make_pothole_img(0.20))
print(f"4. Severe Crater:  is_defect={res4['is_defect']} | Area={res4['surface_area_cm2']} cm2 | Depth={res4['estimated_depth_mm']} mm | Cat={res4['depth_category']}")
assert res4['is_defect'] is True
assert res4['depth_category'] == 'Severe (>50mm)'
assert res4['estimated_depth_mm'] > 50.0

# 5. Clean road (smooth without cavities)
clean_road = Image.fromarray(np.random.normal(110, 8, (480, 640, 3)).clip(0, 255).astype(np.uint8))
res5 = d.analyze_image(clean_road)
print(f"5. Smooth Road:    is_defect={res5['is_defect']} | Status={res5['verification_status']}")
assert res5['is_defect'] is False, "Should identify clean pavement without defects"

print("=" * 65)
print("SUCCESS: ALL PHASE A COMPUTER VISION SPECIFICATIONS FULLY VERIFIED!")
print("=" * 65)
