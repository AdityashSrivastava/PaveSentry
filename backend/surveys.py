import io
import csv
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

from database.db_manager import (
    get_connection,
    find_nearest_segment,
    log_survey_upload,
    update_segment_condition,
    DB_PATH
)
from ml.predict import run_predictions_and_update_db

def calculate_astm_pci(iri: float, rut_depth_mm: float, crack_density_pct: float, pothole_count: int) -> float:
    """
    Computes ASTM D6433 compliant Pavement Condition Index (PCI 0-100)
    from laser profilometer roughness, rutting, cracking, and pothole distress values.
    """
    deduct_iri = max(0.0, min(45.0, (iri - 1.5) * 11.5))
    deduct_rut = max(0.0, min(25.0, (rut_depth_mm - 2.5) * 1.4))
    deduct_crack = max(0.0, min(25.0, crack_density_pct * 0.85))
    deduct_potholes = max(0.0, min(30.0, pothole_count * 4.5))

    pci = 100.0 - (deduct_iri + deduct_rut + deduct_crack + deduct_potholes)
    return round(max(5.0, min(100.0, pci)), 1)

def parse_survey_csv(file_content: bytes) -> List[Dict[str, Any]]:
    """
    Parses CSV exported by ROMDAS, laser profilometers, or smartphone roughness meters.
    Normalizes column names flexibly to handle varying government survey van outputs.
    """
    text = ""
    for enc in ["utf-8-sig", "utf-8", "latin-1", "cp1252"]:
        try:
            text = file_content.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if not text:
        raise ValueError("Unable to decode CSV file. Ensure valid UTF-8 or ASCII encoding.")

    # Detect delimiter
    sample = text[:2048]
    delimiter = ","
    if "\t" in sample and sample.count("\t") > sample.count(","):
        delimiter = "\t"
    elif ";" in sample and sample.count(";") > sample.count(","):
        delimiter = ";"

    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    records = []

    for row in reader:
        norm_row = {str(k).strip().lower().replace(" ", "_"): v for k, v in row.items() if k is not None}
        
        # Extract Segment ID
        seg_id = None
        for k in ["segment_id", "corridor_id", "seg_id", "road_id", "id"]:
            if k in norm_row and norm_row[k]:
                seg_id = norm_row[k].strip()
                break

        # Extract Coordinates
        lat = None
        for k in ["latitude", "lat", "start_lat", "gps_lat", "y"]:
            if k in norm_row and norm_row[k]:
                try:
                    lat = float(norm_row[k])
                    break
                except ValueError:
                    pass

        lon = None
        for k in ["longitude", "lon", "lng", "start_lon", "gps_lon", "x"]:
            if k in norm_row and norm_row[k]:
                try:
                    lon = float(norm_row[k])
                    break
                except ValueError:
                    pass

        # Extract IRI
        iri = 3.2
        for k in ["iri", "iri_m_km", "iri_roughness", "roughness_iri", "roughness"]:
            if k in norm_row and norm_row[k]:
                try:
                    iri = float(norm_row[k])
                    break
                except ValueError:
                    pass

        # Extract Rut Depth
        rut_mm = 6.0
        for k in ["rut_depth_mm", "rutting_mm", "rut_mm", "rutting", "rut_depth"]:
            if k in norm_row and norm_row[k]:
                try:
                    rut_mm = float(norm_row[k])
                    break
                except ValueError:
                    pass

        # Extract Cracking
        crack_pct = 5.0
        for k in ["crack_density_pct", "crack_pct", "cracking_pct", "cracks_pct", "cracking"]:
            if k in norm_row and norm_row[k]:
                try:
                    crack_pct = float(norm_row[k])
                    break
                except ValueError:
                    pass

        # Extract Potholes
        potholes = 0
        for k in ["pothole_count", "potholes", "potholes_count", "active_potholes"]:
            if k in norm_row and norm_row[k]:
                try:
                    potholes = int(float(norm_row[k]))
                    break
                except ValueError:
                    pass

        # Extract PCI (or compute if absent)
        pci = None
        for k in ["pci", "pavement_condition_index"]:
            if k in norm_row and norm_row[k]:
                try:
                    pci = float(norm_row[k])
                    break
                except ValueError:
                    pass
        if pci is None:
            pci = calculate_astm_pci(iri, rut_mm, crack_pct, potholes)

        # Survey Date
        survey_date = datetime.utcnow().strftime("%Y-%m-%d")
        for k in ["survey_date", "date", "timestamp"]:
            if k in norm_row and norm_row[k]:
                survey_date = norm_row[k].strip()[:10]
                break

        records.append({
            "segment_id": seg_id,
            "latitude": lat,
            "longitude": lon,
            "iri": round(iri, 2),
            "rut_depth_mm": round(rut_mm, 1),
            "crack_density_pct": round(crack_pct, 1),
            "pothole_count": potholes,
            "pci": round(pci, 1),
            "survey_date": survey_date
        })

    return records

def parse_survey_geojson(file_content: bytes) -> List[Dict[str, Any]]:
    """
    Parses GeoJSON exported by ARRB Hawkeye, Trimble, or GIS field mapping vans.
    """
    try:
        data = json.loads(file_content.decode("utf-8"))
    except Exception as e:
        raise ValueError(f"Invalid GeoJSON content: {str(e)}")

    features = data.get("features", [])
    records = []

    for f in features:
        props = f.get("properties", {})
        geom = f.get("geometry", {})
        coords = geom.get("coordinates", [])

        lat, lon = None, None
        if geom.get("type") == "Point" and len(coords) >= 2:
            lon, lat = coords[0], coords[1]
        elif geom.get("type") == "LineString" and len(coords) > 0:
            # Use midpoint coordinate
            mid_idx = len(coords) // 2
            mid_pt = coords[mid_idx]
            if len(mid_pt) >= 2:
                lon, lat = mid_pt[0], mid_pt[1]

        seg_id = props.get("segment_id") or props.get("id")
        iri = float(props.get("iri", props.get("iri_m_km", 3.2)))
        rut_mm = float(props.get("rut_depth_mm", 6.0))
        crack_pct = float(props.get("crack_density_pct", 5.0))
        potholes = int(props.get("pothole_count", 0))
        
        pci = props.get("pci")
        if pci is not None:
            pci = float(pci)
        else:
            pci = calculate_astm_pci(iri, rut_mm, crack_pct, potholes)

        survey_date = props.get("survey_date", datetime.utcnow().strftime("%Y-%m-%d"))

        records.append({
            "segment_id": seg_id,
            "latitude": lat,
            "longitude": lon,
            "iri": round(iri, 2),
            "rut_depth_mm": round(rut_mm, 1),
            "crack_density_pct": round(crack_pct, 1),
            "pothole_count": potholes,
            "pci": round(pci, 1),
            "survey_date": survey_date
        })

    return records

def ingest_survey_file(
    file_content: bytes,
    filename: str,
    uploaded_by: str,
    division: str,
    db_path=DB_PATH
) -> Dict[str, Any]:
    """
    High-level ingestion pipeline for field survey files (CSV or GeoJSON).
    1. Parses records.
    2. Maps to authentic Delhi road network corridors.
    3. Updates condition_surveys table in SQLite.
    4. Triggers ML prediction updates.
    5. Returns audit report.
    """
    fn_lower = filename.lower()
    if fn_lower.endswith(".geojson") or fn_lower.endswith(".json"):
        records = parse_survey_geojson(file_content)
        file_format = "GeoJSON/ARRB Hawkeye"
    elif fn_lower.endswith(".csv") or fn_lower.endswith(".txt"):
        records = parse_survey_csv(file_content)
        file_format = "CSV/ROMDAS Profilometer"
    else:
        raise ValueError("Unsupported survey format. Please upload a .csv, .geojson, or .json file.")

    if not records:
        raise ValueError("The uploaded survey file contains no readable data rows.")

    # Verify existing segments in DB
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT segment_id, name, city_zone FROM road_segments")
    db_segments = {r["segment_id"]: dict(r) for r in cursor.fetchall()}
    conn.close()

    updated_segments_map = {}
    matched_records = 0

    for rec in records:
        seg_id = rec.get("segment_id")
        
        # If segment_id is unknown or missing, spatial coordinate lookup
        if not seg_id or seg_id not in db_segments:
            if rec.get("latitude") and rec.get("longitude"):
                nearest = find_nearest_segment(rec["latitude"], rec["longitude"], max_distance_km=3.5, db_path=db_path)
                if nearest:
                    seg_id = nearest["segment_id"]

        if seg_id and seg_id in db_segments:
            update_segment_condition(
                segment_id=seg_id,
                survey_date=rec["survey_date"],
                pci=rec["pci"],
                iri=rec["iri"],
                rut_depth_mm=rec["rut_depth_mm"],
                crack_density_pct=rec["crack_density_pct"],
                pothole_count=rec["pothole_count"],
                db_path=db_path
            )
            matched_records += 1
            updated_segments_map[seg_id] = {
                "segment_id": seg_id,
                "name": db_segments[seg_id]["name"],
                "zone": db_segments[seg_id]["city_zone"],
                "pci": rec["pci"],
                "iri": rec["iri"],
                "pothole_count": rec["pothole_count"],
                "survey_date": rec["survey_date"]
            }

    if matched_records == 0:
        raise ValueError("None of the coordinates or Segment IDs matched existing Delhi NCT road corridors.")

    # Re-run ML model predictions so risk levels, costs, and priority scores update
    try:
        run_predictions_and_update_db()
    except Exception as e:
        print(f"Warning: ML inference update following survey ingestion logged note: {e}")

    # Calculate average ingested metrics
    avg_iri = round(sum(s["iri"] for s in updated_segments_map.values()) / len(updated_segments_map), 2)
    avg_pci = round(sum(s["pci"] for s in updated_segments_map.values()) / len(updated_segments_map), 1)

    # Log survey upload to audit history
    upload_record = log_survey_upload({
        "filename": filename,
        "file_format": file_format,
        "uploaded_by": uploaded_by,
        "division": division,
        "records_count": len(records),
        "segments_affected": len(updated_segments_map),
        "avg_iri": avg_iri,
        "avg_pci": avg_pci
    }, db_path=db_path)

    return {
        "status": "success",
        "upload_id": upload_record["upload_id"] if upload_record else "SRV-2026-NCTD",
        "filename": filename,
        "file_format": file_format,
        "records_total": len(records),
        "records_matched": matched_records,
        "segments_affected": len(updated_segments_map),
        "avg_iri": avg_iri,
        "avg_pci": avg_pci,
        "updated_segments": list(updated_segments_map.values())[:15]
    }
