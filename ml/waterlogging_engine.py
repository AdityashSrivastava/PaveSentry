"""
ml/waterlogging_engine.py
Monsoon Waterlogging & Hydroplaning Vulnerability Index Engine for Delhi NCR
Conforms to IRC:37:2018 (Pavement Subgrade Moisture Saturation & Soaked CBR Loss),
IRC:SP:42 (Guidelines on Road Drainage), and Delhi PWD Monsoon Flood Action Plan.
"""

import math
import time
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from database.db_manager import get_segment_by_id, get_all_segments

# ==============================================================================
# Delhi NCT Historical Waterlogging Underpasses & Low-Lying Vulnerability Hotspots
# Calibrated against Delhi Traffic Police Monsoon Advisories & Delhi PWD Flood Control
# ==============================================================================
DELHI_WATERLOGGING_HOTSPOTS = [
    {
        "hotspot_id": "DEL-WL-01",
        "name": "Minto Bridge Railway Underpass",
        "city_zone": "Central Delhi",
        "latitude": 28.6342,
        "longitude": 77.2248,
        "depression_depth_m": 4.5,
        "outfall_drain": "Barapullah Nallah via Deen Dayal Upadhyay Drain",
        "sump_pump_capacity_cusecs": 120.0,
        "historical_max_inundation_cm": 140.0,
        "historical_failure_severity": "Critical (Complete Submersion / Traffic Diverted)",
        "vulnerability_tier": "Critical",
        "nearest_segment_hint": "DL-NCT-0002"
    },
    {
        "hotspot_id": "DEL-WL-02",
        "name": "Pul Prahladpur Railway Underpass (MB Road)",
        "city_zone": "South East Delhi",
        "latitude": 28.5085,
        "longitude": 77.2882,
        "depression_depth_m": 3.8,
        "outfall_drain": "Agra Canal Stormwater Outfall",
        "sump_pump_capacity_cusecs": 85.0,
        "historical_max_inundation_cm": 115.0,
        "historical_failure_severity": "Severe (Subgrade Saturated Cavitation)",
        "vulnerability_tier": "Critical",
        "nearest_segment_hint": "DL-NCT-0003"
    },
    {
        "hotspot_id": "DEL-WL-03",
        "name": "ITO Junction & Vikas Marg Underpass",
        "city_zone": "Central Delhi",
        "latitude": 28.6294,
        "longitude": 77.2435,
        "depression_depth_m": 2.9,
        "outfall_drain": "Yamuna River Outfall Drain No. 12",
        "sump_pump_capacity_cusecs": 90.0,
        "historical_max_inundation_cm": 85.0,
        "historical_failure_severity": "Severe (Yamuna Backflow Risk)",
        "vulnerability_tier": "High",
        "nearest_segment_hint": "DL-NCT-0002"
    },
    {
        "hotspot_id": "DEL-WL-04",
        "name": "Zakhira Flyover Underpass (Rohtak Road)",
        "city_zone": "West Delhi",
        "latitude": 28.6675,
        "longitude": 77.1583,
        "depression_depth_m": 3.2,
        "outfall_drain": "Najafgarh Drain Tributary",
        "sump_pump_capacity_cusecs": 70.0,
        "historical_max_inundation_cm": 95.0,
        "historical_failure_severity": "Severe (Commercial Multi-Axle Rutting)",
        "vulnerability_tier": "High",
        "nearest_segment_hint": "DL-NCT-0004"
    },
    {
        "hotspot_id": "DEL-WL-05",
        "name": "Azadpur Subzi Mandi Underpass (GT Karnal Road)",
        "city_zone": "North Delhi",
        "latitude": 28.7088,
        "longitude": 77.1782,
        "depression_depth_m": 3.0,
        "outfall_drain": "Supplementary Drain to Yamuna",
        "sump_pump_capacity_cusecs": 75.0,
        "historical_max_inundation_cm": 80.0,
        "historical_failure_severity": "Moderate to Severe",
        "vulnerability_tier": "High",
        "nearest_segment_hint": "DL-NCT-0005"
    },
    {
        "hotspot_id": "DEL-WL-06",
        "name": "Bhairon Marg / Pragati Maidan Underpass",
        "city_zone": "New Delhi (NDMC)",
        "latitude": 28.6180,
        "longitude": 77.2480,
        "depression_depth_m": 4.1,
        "outfall_drain": "Purana Qila Stormwater Line",
        "sump_pump_capacity_cusecs": 110.0,
        "historical_max_inundation_cm": 70.0,
        "historical_failure_severity": "Moderate (Automated Sump Pump Redundancy)",
        "vulnerability_tier": "Moderate",
        "nearest_segment_hint": "DL-NCT-0001"
    },
    {
        "hotspot_id": "DEL-WL-07",
        "name": "Tilak Bridge Railway Underpass",
        "city_zone": "Central Delhi",
        "latitude": 28.6256,
        "longitude": 77.2389,
        "depression_depth_m": 3.5,
        "outfall_drain": "Barapullah Drain Connection",
        "sump_pump_capacity_cusecs": 80.0,
        "historical_max_inundation_cm": 75.0,
        "historical_failure_severity": "Moderate to High",
        "vulnerability_tier": "High",
        "nearest_segment_hint": "DL-NCT-0002"
    },
    {
        "hotspot_id": "DEL-WL-08",
        "name": "Lawrence Road Industrial Underpass",
        "city_zone": "North West Delhi",
        "latitude": 28.6834,
        "longitude": 77.1492,
        "depression_depth_m": 2.8,
        "outfall_drain": "Najafgarh Supplementary Drain",
        "sump_pump_capacity_cusecs": 60.0,
        "historical_max_inundation_cm": 65.0,
        "historical_failure_severity": "Moderate (Industrial Effluent Intrusion)",
        "vulnerability_tier": "Moderate",
        "nearest_segment_hint": "DL-NCT-0006"
    },
    {
        "hotspot_id": "DEL-WL-09",
        "name": "Badarpur Border Underpass (Mathura Road)",
        "city_zone": "South Delhi",
        "latitude": 28.4982,
        "longitude": 77.3015,
        "depression_depth_m": 3.4,
        "outfall_drain": "Agra Canal Feeder",
        "sump_pump_capacity_cusecs": 90.0,
        "historical_max_inundation_cm": 90.0,
        "historical_failure_severity": "High (Haryana Interstate Traffic Stalled)",
        "vulnerability_tier": "High",
        "nearest_segment_hint": "DL-NCT-0003"
    },
    {
        "hotspot_id": "DEL-WL-10",
        "name": "Mahipalpur Airport Approach Underpass",
        "city_zone": "South West Delhi",
        "latitude": 28.5471,
        "longitude": 77.1264,
        "depression_depth_m": 3.1,
        "outfall_drain": "Palam Drain to Najafgarh",
        "sump_pump_capacity_cusecs": 105.0,
        "historical_max_inundation_cm": 60.0,
        "historical_failure_severity": "Moderate (IGI Airport Corridor Priority)",
        "vulnerability_tier": "Moderate",
        "nearest_segment_hint": "DL-NCT-0001"
    }
]

def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates great-circle distance between two GPS coordinates in kilometers."""
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (math.sin(delta_phi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2))
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c


def find_nearest_waterlogging_hotspot(lat: float, lon: float) -> Tuple[Dict[str, Any], float]:
    """Finds the closest waterlogging underpass hotspot and distance in km."""
    best_hotspot = DELHI_WATERLOGGING_HOTSPOTS[0]
    min_dist = float("inf")

    for h in DELHI_WATERLOGGING_HOTSPOTS:
        dist = haversine_distance_km(lat, lon, h["latitude"], h["longitude"])
        if dist < min_dist:
            min_dist = dist
            best_hotspot = h

    return best_hotspot, round(min_dist, 2)


def calculate_waterlogging_risk(segment_id: str) -> Dict[str, Any]:
    """
    Computes comprehensive Monsoon Waterlogging & Hydroplaning Vulnerability Index
    for a specific Delhi arterial corridor based on topography, drainage, and soaked CBR.
    """
    seg = get_segment_by_id(segment_id)
    if not seg:
        raise ValueError(f"Segment ID '{segment_id}' not found in Delhi pavement database.")

    lat = float(seg.get("start_lat") or 28.6139)
    lon = float(seg.get("start_lon") or 77.2090)
    pci = float(seg.get("pci") or 70.0)
    rut_depth_mm = float(seg.get("rut_depth_mm") or 6.5)
    aadt = int(seg.get("aadt") or 45000)
    heavy_pct = float(seg.get("heavy_vehicle_pct") or 0.14)
    speed_limit = 70.0 if seg.get("road_type") == "Highway" else 50.0

    nearest_hotspot, dist_km = find_nearest_waterlogging_hotspot(lat, lon)

    # 1. Proximity Vulnerability Component (Closer to underpass depression = higher score)
    # Range 0 to 35 pts
    if dist_km <= 1.0:
        proximity_score = 35.0
    elif dist_km <= 3.0:
        proximity_score = 35.0 - (dist_km - 1.0) * 8.0
    elif dist_km <= 7.0:
        proximity_score = max(5.0, 19.0 - (dist_km - 3.0) * 3.5)
    else:
        proximity_score = 5.0

    # 2. Rutting / Water Film Trapping Component (Ruts > 10mm trap water film > 2.5mm)
    # Range 0 to 25 pts
    rut_score = min(25.0, (rut_depth_mm / 18.0) * 25.0)

    # 3. Pavement Permeability & Crack Infiltration Component (Cracks allow subgrade saturation)
    # Range 0 to 20 pts
    crack_density = float(seg.get("crack_density_pct") or 5.0)
    crack_score = min(20.0, (crack_density / 15.0) * 20.0)

    # 4. Heavy Traffic Dynamic Sump Action Component (Trucks force water into pores under high pore pressure)
    # Range 0 to 20 pts
    traffic_score = min(20.0, (aadt * heavy_pct / 12000.0) * 20.0)

    # Total Waterlogging Pavement Risk Factor (WPRF) (0-100)
    wprf = round(min(100.0, proximity_score + rut_score + crack_score + traffic_score), 1)

    # Risk Tier Classification
    if wprf >= 75.0:
        risk_tier = "Critical Vulnerability (Immediate Pre-Monsoon Intervention)"
        risk_color = "#dc2626"
    elif wprf >= 55.0:
        risk_tier = "High Vulnerability (Drainage Clearing & Polymer Seal)"
        risk_color = "#ea580c"
    elif wprf >= 35.0:
        risk_tier = "Moderate Vulnerability (Routine Sump Desilting)"
        risk_color = "#f59e0b"
    else:
        risk_tier = "Low Vulnerability (Adequate Gravity Outfall)"
        risk_color = "#10b981"

    # IRC:37:2018 Soaked Subgrade Resilient Modulus Loss
    # Baseline Dry CBR (8.5%), Soaked CBR drops significantly in waterlogged soil
    dry_cbr = 8.5
    cbr_loss_pct = round(min(60.0, 20.0 + (wprf / 100.0) * 40.0), 1)
    soaked_cbr = round(dry_cbr * (1.0 - cbr_loss_pct / 100.0), 2)
    mr_dry_mpa = round(10.0 * dry_cbr, 1)          # IRC:37 MR = 10 * CBR (MPa)
    mr_soaked_mpa = round(10.0 * soaked_cbr, 1)
    fatigue_life_reduction_pct = round(min(80.0, (1.0 - (mr_soaked_mpa / mr_dry_mpa)**1.5) * 100.0), 1)

    # Hydroplaning Risk Index (HRI) (0-100)
    # Water film depth estimated from rut depth and crossfall slope
    estimated_water_film_mm = round(max(0.5, rut_depth_mm * 0.45), 2)
    hri = round(min(100.0, (estimated_water_film_mm / 6.0) * 50.0 + (speed_limit / 80.0) * 50.0), 1)
    if hri >= 70.0:
        hydro_verdict = "Severe Hydroplaning Hazard (Skid Resistance Loss at Speed)"
    elif hri >= 45.0:
        hydro_verdict = "Moderate Hydroplaning Risk (Wet Weather Speed Advisory Required)"
    else:
        hydro_verdict = "Safe Wet Pavement Friction (Standard Tire Microtexture Adhesion)"

    # Pre-Monsoon Maintenance Priority Boost
    # June 15 is Delhi monsoon onset date
    today = datetime.now()
    is_pre_monsoon = (today.month in [3, 4, 5, 6])
    pre_monsoon_boost_pct = round((wprf / 100.0) * (45.0 if is_pre_monsoon else 20.0), 1)
    effective_priority_score = round(min(100.0, (100.0 - pci) * 0.6 + wprf * 0.4), 1)

    return {
        "segment_id": segment_id,
        "corridor_name": seg.get("name", "Delhi Arterial Corridor"),
        "city_zone": seg.get("city_zone", "Delhi NCT"),
        "length_km": seg.get("length_km", 5.0),
        "lanes": seg.get("lanes", 4),
        "waterlogging_risk_score": wprf,
        "risk_tier": risk_tier,
        "risk_color": risk_color,
        "nearest_hotspot": {
            "name": nearest_hotspot["name"],
            "distance_km": dist_km,
            "depression_depth_m": nearest_hotspot["depression_depth_m"],
            "outfall_drain": nearest_hotspot["outfall_drain"],
            "historical_max_inundation_cm": nearest_hotspot["historical_max_inundation_cm"],
            "historical_severity": nearest_hotspot["historical_failure_severity"]
        },
        "soaked_subgrade_mechanics": {
            "standard_specification": "IRC:37:2018 Moisture Sensitivity Matrix",
            "dry_cbr_pct": dry_cbr,
            "soaked_cbr_pct": soaked_cbr,
            "cbr_loss_pct": cbr_loss_pct,
            "dry_resilient_modulus_mpa": mr_dry_mpa,
            "soaked_resilient_modulus_mpa": mr_soaked_mpa,
            "fatigue_life_reduction_pct": fatigue_life_reduction_pct
        },
        "hydroplaning_assessment": {
            "hydroplaning_risk_index": hri,
            "estimated_water_film_depth_mm": estimated_water_film_mm,
            "critical_hydroplaning_speed_kmh": round(6.35 * (speed_limit ** 0.5) * 1.8, 1),
            "verdict": hydro_verdict
        },
        "pre_monsoon_preparedness": {
            "active_pre_monsoon_window": is_pre_monsoon,
            "pre_monsoon_priority_multiplier": pre_monsoon_boost_pct,
            "effective_priority_score": effective_priority_score,
            "recommended_drainage_intervention": (
                "Desilt stormwater catch-pits, install polymer-modified asphalt crack seal, and position high-head standby dewatering pumps"
                if wprf >= 55.0 else
                "Routine road shoulder grading and culvert trash screen clearance"
            ),
            "statutory_deadline": "15 June (Mandatory Delhi PWD Pre-Monsoon Preparedness Protocol)"
        }
    }


def get_network_waterlogging_summary() -> Dict[str, Any]:
    """
    Returns network-wide waterlogging vulnerability statistics and top hotspots across Delhi NCT.
    """
    segments = get_all_segments()
    total_segments = len(segments)

    critical_count = 0
    high_count = 0
    moderate_count = 0
    low_count = 0
    total_wprf = 0.0

    ranked_corridors = []

    for s in segments:
        seg_id = s.get("segment_id")
        try:
            wl = calculate_waterlogging_risk(seg_id)
            score = wl["waterlogging_risk_score"]
            total_wprf += score

            if score >= 75.0:
                critical_count += 1
            elif score >= 55.0:
                high_count += 1
            elif score >= 35.0:
                moderate_count += 1
            else:
                low_count += 1

            ranked_corridors.append({
                "segment_id": seg_id,
                "name": wl["corridor_name"],
                "zone": wl["city_zone"],
                "score": score,
                "tier": wl["risk_tier"].split(" ")[0],
                "color": wl["risk_color"],
                "hotspot": wl["nearest_hotspot"]["name"],
                "distance_km": wl["nearest_hotspot"]["distance_km"],
                "cbr_loss_pct": wl["soaked_subgrade_mechanics"]["cbr_loss_pct"],
                "hydroplaning_index": wl["hydroplaning_assessment"]["hydroplaning_risk_index"]
            })
        except Exception:
            continue

    avg_wprf = round(total_wprf / max(1, total_segments), 1)
    ranked_corridors.sort(key=lambda x: x["score"], reverse=True)

    return {
        "status": "success",
        "total_corridors_analyzed": total_segments,
        "network_average_wprf": avg_wprf,
        "vulnerability_distribution": {
            "critical": critical_count,
            "high": high_count,
            "moderate": moderate_count,
            "low": low_count
        },
        "top_waterlogging_vulnerable_corridors": ranked_corridors[:8],
        "delhi_underpass_hotspots": DELHI_WATERLOGGING_HOTSPOTS,
        "flood_control_agencies": [
            "Public Works Department (Delhi PWD) Flood Control Unit",
            "Irrigation & Flood Control Department (I&FC), GNCTD",
            "Municipal Corporation of Delhi (MCD) Stormwater Division",
            "New Delhi Municipal Council (NDMC) Civil Engineering"
        ]
    }
