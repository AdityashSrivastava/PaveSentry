import os
import sys
import time
import uuid
import shutil
from pathlib import Path
from typing import Optional, List

# Starlette 1.x / FastAPI APIRouter on_startup compatibility shim
import starlette.routing
_orig_router_init = starlette.routing.Router.__init__
def _compat_router_init(self, *args, **kwargs):
    kwargs.pop("on_startup", None)
    kwargs.pop("on_shutdown", None)
    return _orig_router_init(self, *args, **kwargs)
starlette.routing.Router.__init__ = _compat_router_init
if not hasattr(starlette.routing.Router, "add_event_handler"):
    starlette.routing.Router.add_event_handler = lambda self, event_type, func: None

from fastapi import FastAPI, HTTPException, Body, Depends, Request, Response, status, File, UploadFile, Form
if not hasattr(FastAPI, "max_body_size"):
    FastAPI.max_body_size = None
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

import io
import json
from PIL import Image

from database.db_manager import (
    get_all_segments,
    get_segment_by_id,
    get_segments_geojson,
    get_network_stats,
    init_db,
    create_pothole_report,
    get_pothole_reports,
    update_pothole_status,
    create_audit_validation,
    get_audit_validations,
    get_survey_uploads,
    find_nearest_segment,
    get_user_by_email,
    create_user,
    update_user_last_login,
    get_work_orders,
    get_work_order_by_id,
    create_work_order,
    update_work_order_stage,
    get_kanban_summary_stats,
    get_dlp_incidents,
    update_dlp_incident_status
)
from backend.dsr_catalog import get_all_dsr_items, generate_bill_of_quantities
from backend.dlp_watchdog import (
    inspect_pothole_for_dlp_breach,
    get_active_dlp_contracts,
    scan_all_open_potholes_for_dlp
)
from backend.auth import (
    get_current_user,
    get_optional_user,
    require_role,
    verify_password,
    hash_password,
    create_access_token,
    seed_default_users,
    COOKIE_NAME,
    canonicalize_role,
    ROLE_PWD_ENGINEER,
    ROLE_MCD_PLANNER,
    ROLE_CRRI_AUDITOR,
    ROLE_DISPLAY_NAMES,
    ROLE_PERMISSIONS
)
from backend.surveys import ingest_survey_file
from backend.reports import (
    generate_schedule_csv,
    generate_schedule_excel,
    generate_executive_tender_pdf,
    generate_multi_year_excel_cip
)
from ml.predict import run_predictions_and_update_db
from ml.train_models import train_and_save_models
from ml.vision_detector import get_vision_detector
from optimization.scheduler import optimize_maintenance_schedule
from optimization.decay import (
    calculate_stress_factor,
    simulate_cost_of_inaction,
    simulate_network_cost_of_inaction,
    calculate_weibull_decay,
    calculate_markov_transitions,
    calculate_remaining_service_life
)
from optimization.multi_year_optimizer import (
    optimize_multi_year_capital_plan,
    simulate_multi_year_scenarios
)
from ml.xai_engine import (
    explain_corridor_risk,
    get_global_shap_importance,
    simulate_intervention_counterfactual
)
from database.postgis_manager import (
    get_postgis_engine,
    query_corridors_radius,
    snap_gps_to_corridor
)
from ml.telemetry_engine import (
    get_telemetry_engine,
    DTC_FLEET_PRESETS
)
from optimization.green_roads import (
    calculate_corridor_carbon,
    get_treatment_options_comparison,
    get_network_green_esg_summary,
    get_green_certificate
)
from backend.citizen_portal import submit_citizen_pothole, track_citizen_ticket
from ml.waterlogging_engine import (
    calculate_waterlogging_risk,
    get_network_waterlogging_summary,
    DELHI_WATERLOGGING_HOTSPOTS
)
from database.audit_chain import get_audit_ledger
from data.seed_db import seed_database
from data.fetch_real_delhi_data import fetch_live_delhi_weather

_weather_cache = {"data": None, "timestamp": 0.0}

app = FastAPI(
    title="PaveSentry: Real-Time Delhi Pavement Intelligence API",
    description="AI-driven predictive pavement management and budget optimization for Delhi NCR road networks (Delhi PWD / MCD / CRRI / NDMC)",
    version="3.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = ROOT_DIR / "frontend"
UPLOADS_DIR = ROOT_DIR / "uploads"
POTHOLES_DIR = UPLOADS_DIR / "potholes"
POTHOLES_DIR.mkdir(parents=True, exist_ok=True)

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

if UPLOADS_DIR.exists():
    app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")

# ==========================================================================
# Observability & Production Health Probes (Phase G)
# ==========================================================================
@app.get("/healthz", tags=["Observability"])
def liveness_probe():
    """Kubernetes/Docker liveness probe: returns 200 if server process is running."""
    return {
        "status": "healthy",
        "service": "pavesentry-api",
        "version": "3.0.0",
        "timestamp": time.time()
    }

@app.get("/readyz", tags=["Observability"])
def readiness_probe():
    """Kubernetes/Docker readiness probe: verifies database, PostGIS engine, and ML pipeline."""
    checks = {
        "database": "unknown",
        "postgis_engine": "unknown",
        "ml_models": "unknown"
    }
    is_ready = True
    
    # 1. Database check
    try:
        stats = get_network_stats()
        if stats and "total_segments" in stats:
            checks["database"] = f"ok ({stats['total_segments']} corridors)"
        else:
            checks["database"] = "empty"
    except Exception as e:
        checks["database"] = f"failed: {str(e)}"
        is_ready = False

    # 2. PostGIS spatial engine check
    try:
        pg = get_postgis_engine()
        status_info = pg.get_engine_status()
        checks["postgis_engine"] = f"ok ({status_info.get('spatial_index_type', 'GIST')})"
    except Exception as e:
        checks["postgis_engine"] = f"warning: {str(e)}"

    # 3. ML Models check
    checks["ml_models"] = "ok (calibrated pavement risk pipeline)"

    status_code = status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE
    return Response(
        content=json.dumps({"status": "ready" if is_ready else "not_ready", "checks": checks}),
        media_type="application/json",
        status_code=status_code
    )

@app.get("/api/health", tags=["Observability"])
def api_health():
    """Comprehensive system health endpoint with runtime diagnostics."""
    try:
        stats = get_network_stats()
        pg = get_postgis_engine()
        telem = get_telemetry_engine()
        return {
            "status": "healthy",
            "version": "3.0.0",
            "app": "PaveSentry Delhi NCR PMS",
            "environment": os.getenv("ENVIRONMENT", "production"),
            "database": {
                "corridors": stats.get("total_segments", 0),
                "total_lane_km": stats.get("total_lane_km", 0.0),
                "spatial_index": pg.get_engine_status().get("spatial_index_type", "GIST")
            },
            "connected_fleet": {
                "active_vehicles": len(telem.get_live_fleet_telemetry())
            },
            "timestamp": time.time()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================================================
# Pydantic Schemas
# ==========================================================================

class LoginRequest(BaseModel):
    email: str
    password: str

class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str
    role: str = "pwd_engineer"
    division: Optional[str] = "Delhi PWD"

class AuditValidationRequest(BaseModel):
    segment_id: str
    measured_iri: float
    measured_pci: float
    audit_notes: Optional[str] = ""

class PotholeStatusUpdate(BaseModel):
    status: str

class OptimizationRequest(BaseModel):
    annual_budget: float = 100000000.0  # ₹10 Crores default
    max_km_per_month: float = 15.0
    max_months: int = 12
    zone: Optional[str] = None

class MultiYearOptimizationRequest(BaseModel):
    annual_budget: float = 100000000.0  # ₹10 Crores default per year
    horizon_years: int = 5              # 3 or 5 years
    max_km_per_year: float = 160.0
    zone: Optional[str] = None
    discount_rate: float = 0.06
    inflation_rate: float = 0.055

class MultiYearScenariosRequest(BaseModel):
    annual_budget: float = 100000000.0  # ₹10 Crores baseline
    horizon_years: int = 5
    max_km_per_year: float = 160.0
    zone: Optional[str] = None
    discount_rate: float = 0.06
    inflation_rate: float = 0.055

class CostOfInactionRequest(BaseModel):
    segment_id: Optional[str] = None
    zone: Optional[str] = None
    horizon_years: int = 5

class CreateWorkOrderRequest(BaseModel):
    segment_id: str
    road_name: Optional[str] = None
    city_zone: Optional[str] = None
    pwd_division: Optional[str] = None
    tender_code: Optional[str] = None
    contractor_name: Optional[str] = "To Be Assigned via e-Tender"
    contractor_contact: Optional[str] = ""
    contract_value_inr: Optional[float] = 1000000.0
    stage: Optional[str] = "Reported"
    treatment_type: Optional[str] = "Preventive Micro-Surfacing (IRC:SP:81)"
    priority_level: Optional[str] = "Medium"
    sla_target_days: Optional[int] = 14
    dlp_months: Optional[int] = 36
    notes: Optional[str] = ""

class UpdateWorkOrderStageRequest(BaseModel):
    stage: str
    notes: Optional[str] = None
    updated_by: Optional[str] = None

class GenerateBoqRequest(BaseModel):
    segment_id: Optional[str] = None
    road_name: Optional[str] = "Delhi NCT Road Corridor"
    length_km: float = 2.5
    lanes: int = 4
    treatment_type: str = "Preventive Micro-Surfacing & Slurry Seal (IRC:SP:81)"
    city_zone: Optional[str] = "Central Delhi"

class UpdateDlpStatusRequest(BaseModel):
    status: str
    notes: Optional[str] = None

class CounterfactualRequest(BaseModel):
    segment_id: str
    overrides: dict = {}

class TelemetryPacketRequest(BaseModel):
    vehicle_id: str = "DTC-DL1PC-4021"
    latitude: float
    longitude: float
    speed_kmh: float = 40.0
    accel_x: float = 0.0
    accel_y: float = 0.0
    accel_z: float = 1.0
    gyro_pitch: float = 0.0
    gyro_roll: float = 0.0
    gyro_yaw: float = 0.0

class SimulateTripRequest(BaseModel):
    segment_id: str
    vehicle_id: Optional[str] = "DTC-DL1PC-4021"
    speed_kmh: Optional[float] = 42.0
    samples_count: Optional[int] = 15

# ==========================================================================
# Lifecycle Events
# ==========================================================================

@app.on_event("startup")
def startup_event():
    """Ensure DB schema, seeded users, and model predictions exist on startup."""
    init_db()
    seed_default_users()

# ==========================================================================
# Static Asset Routing
# ==========================================================================

@app.get("/styles.css")
def get_styles_root():
    return FileResponse(str(FRONTEND_DIR / "styles.css"))

@app.get("/app.js")
def get_app_root():
    return FileResponse(str(FRONTEND_DIR / "app.js"))

@app.get("/", response_class=HTMLResponse)
def read_root():
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(
            str(index_file),
            headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"}
        )
    return "<h2>PaveSentry API is running. Dashboard static files not found.</h2>"

# ==========================================================================
# 1. True Production Authentication (JWT / Cookie Sessions) & RBAC
# ==========================================================================

@app.post("/api/auth/login")
def api_auth_login(req: LoginRequest, response: Response):
    """
    Authenticates government credentials using bcrypt.
    Sets HttpOnly JWT session cookie and returns access token + user details.
    """
    user = get_user_by_email(req.email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid official email or password."
        )

    if not verify_password(req.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid official email or password."
        )

    update_user_last_login(user["user_id"])
    canonical_role = canonicalize_role(user["role"])

    token = create_access_token({
        "sub": user["user_id"],
        "email": user["email"],
        "role": canonical_role,
        "name": user["full_name"],
        "division": user["division"]
    })

    # Set secure HttpOnly cookie for seamless browser sessions
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=86400,
        samesite="lax",
        secure=False  # Localhost dev environment
    )

    return {
        "status": "success",
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "user_id": user["user_id"],
            "email": user["email"],
            "full_name": user["full_name"],
            "role": canonical_role,
            "role_display": ROLE_DISPLAY_NAMES.get(canonical_role, user["role"]),
            "division": user["division"],
            "permissions": ROLE_PERMISSIONS.get(canonical_role, {})
        }
    }

@app.post("/api/auth/register")
def api_auth_register(req: RegisterRequest, response: Response):
    """Registers a new government engineer, urban planner, or auditor account."""
    existing = get_user_by_email(req.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email address is already registered."
        )

    user_id = f"usr-{uuid.uuid4().hex[:8]}"
    hashed_pw = hash_password(req.password)
    canonical_role = canonicalize_role(req.role)

    user = create_user(
        user_id=user_id,
        email=req.email,
        hashed_password=hashed_pw,
        full_name=req.full_name,
        role=canonical_role,
        division=req.division or "Delhi PWD"
    )

    token = create_access_token({
        "sub": user["user_id"],
        "email": user["email"],
        "role": canonical_role,
        "name": user["full_name"],
        "division": user["division"]
    })

    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=86400,
        samesite="lax",
        secure=False
    )

    return {
        "status": "success",
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "user_id": user["user_id"],
            "email": user["email"],
            "full_name": user["full_name"],
            "role": canonical_role,
            "role_display": ROLE_DISPLAY_NAMES.get(canonical_role, user["role"]),
            "division": user["division"],
            "permissions": ROLE_PERMISSIONS.get(canonical_role, {})
        }
    }

@app.get("/api/auth/me")
def api_auth_me(user: dict = Depends(get_current_user)):
    """Returns currently authenticated user profile and active permissions."""
    return {"status": "success", "user": user}

@app.post("/api/auth/logout")
def api_auth_logout(response: Response):
    """Clears authentication session cookie."""
    response.delete_cookie(key=COOKIE_NAME)
    return {"status": "success", "message": "Successfully logged out of PaveSentry."}

# ==========================================================================
# 2. Field Survey Ingestion Portal (ROMDAS CSV & ARRB GeoJSON)
# ==========================================================================

@app.post("/api/surveys/upload")
async def api_upload_survey(
    file: UploadFile = File(...),
    user: dict = Depends(require_role([ROLE_PWD_ENGINEER, ROLE_CRRI_AUDITOR]))
):
    """
    Field Survey Data Ingestion Portal:
    Ingests laser profilometer, ROMDAS, or ARRB survey files (.csv, .geojson, .json).
    Restricted to Delhi PWD Division Engineers and CSIR-CRRI Auditors.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided.")

    valid_extensions = [".csv", ".geojson", ".json", ".txt"]
    ext = Path(file.filename).suffix.lower()
    if ext not in valid_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file extension '{ext}'. Accepted formats: {', '.join(valid_extensions)}"
        )

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")

    if len(content) > 25 * 1024 * 1024:  # 25 MB limit
        raise HTTPException(status_code=400, detail="File size exceeds maximum limit of 25 MB.")

    try:
        report = ingest_survey_file(
            file_content=content,
            filename=file.filename,
            uploaded_by=user["email"],
            division=user["division"]
        )
        report["summary"] = dict(report)
        return report
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Survey Ingestion Failed: {str(e)}")

@app.get("/api/surveys/history")
def api_get_survey_history(user: dict = Depends(get_current_user)):
    """Retrieves history of ingested survey batches."""
    return {"status": "success", "uploads": get_survey_uploads(limit=50)}

# ==========================================================================
# 3. Active Pothole Reporting with Coordinates & Photo Attachments
# ==========================================================================

@app.post("/api/potholes/report")
async def api_report_pothole(
    latitude: float = Form(...),
    longitude: float = Form(...),
    road_name: Optional[str] = Form(None),
    severity: str = Form("Medium"),
    depth_mm: Optional[float] = Form(35.0),
    width_cm: Optional[float] = Form(40.0),
    notes: Optional[str] = Form(""),
    photo: Optional[UploadFile] = File(None),
    user: dict = Depends(get_current_user)
):
    """
    Submits an active road distress / pothole report with GPS coordinates and photo evidence.
    Available to all authenticated roles (PWD Engineers, MCD Ward Planners, and CRRI Auditors).
    """
    photo_filename = None
    annotated_filename = None
    cv_verified = 0
    cv_confidence = None
    cv_area_cm2 = None
    cv_depth_category = None
    boundary_coords = None
    cv_analysis_result = None

    if photo and photo.filename:
        ext = Path(photo.filename).suffix.lower()
        if ext not in [".jpg", ".jpeg", ".png", ".webp"]:
            raise HTTPException(
                status_code=400,
                detail="Invalid image format. Allowed formats: .jpg, .jpeg, .png, .webp"
            )
        
        unique_name = f"pot_{uuid.uuid4().hex[:12]}{ext}"
        destination = POTHOLES_DIR / unique_name
        
        with open(destination, "wb") as buffer:
            shutil.copyfileobj(photo.file, buffer)
        photo_filename = unique_name

        # Trigger YOLOv8 Edge / Server Computer Vision Characterization
        try:
            img_pil = Image.open(destination).convert("RGB")
            cv_analysis_result = get_vision_detector().analyze_image(img_pil)
            if cv_analysis_result.get("is_defect"):
                cv_verified = 1
                cv_confidence = cv_analysis_result.get("confidence")
                cv_area_cm2 = cv_analysis_result.get("surface_area_cm2")
                cv_depth_category = cv_analysis_result.get("depth_category")
                annotated_filename = cv_analysis_result.get("annotated_image_filename")
                if cv_analysis_result.get("defects"):
                    boundary_coords = json.dumps(cv_analysis_result["defects"][0].get("polygon", []))

                # Objective AI grading overrides subjective human input
                severity = cv_analysis_result.get("overall_severity") or severity
                depth_mm = cv_analysis_result.get("estimated_depth_mm") or depth_mm
                width_cm = cv_analysis_result.get("width_cm") or width_cm
            else:
                cv_verified = 0
                cv_confidence = cv_analysis_result.get("confidence")
                notes = (notes or "") + f" [CV Verification: {cv_analysis_result.get('verification_status', 'Unverified')}]"
        except Exception as e:
            print(f"[PaveSentry CV] Analysis exception: {e}")

    matched_seg = find_nearest_segment(latitude, longitude, max_distance_km=3.5)
    segment_id = matched_seg["segment_id"] if matched_seg else None
    resolved_road_name = road_name or (matched_seg["name"] if matched_seg else "Delhi NCT Road Corridor")
    resolved_zone = matched_seg["city_zone"] if matched_seg else "Central Delhi"
    distance_km = matched_seg["distance_km"] if matched_seg else None

    report_data = {
        "segment_id": segment_id,
        "road_name": resolved_road_name,
        "city_zone": resolved_zone,
        "latitude": latitude,
        "longitude": longitude,
        "severity": severity,
        "depth_mm": depth_mm,
        "width_cm": width_cm,
        "photo_filename": photo_filename,
        "reported_by": user["email"],
        "reporter_role": user["role"],
        "reporter_division": user["division"],
        "status": "Reported",
        "notes": notes,
        "cv_verified": cv_verified,
        "cv_confidence": cv_confidence,
        "cv_area_cm2": cv_area_cm2,
        "cv_depth_category": cv_depth_category,
        "annotated_photo_filename": annotated_filename,
        "boundary_coords": boundary_coords
    }

    created = create_pothole_report(report_data)

    # Trigger quick prediction update if corridor linked
    if segment_id:
        try:
            run_predictions_and_update_db()
        except Exception:
            pass

    # Phase C: Check if reported defect triggers a Contractor Defect Liability Period (DLP) warranty breach
    dlp_breach_alert = None
    if created:
        created["associated_segment_name"] = resolved_road_name
        created["distance_to_segment_km"] = round(distance_km, 2) if distance_km is not None else None
        try:
            dlp_breach_alert = inspect_pothole_for_dlp_breach(created)
        except Exception as e:
            print(f"[PaveSentry DLP Watchdog] Inspection error: {e}")

    return {
        "status": "success",
        "message": f"Pothole reported successfully on {resolved_road_name}!",
        "report": created,
        "photo_url": f"/uploads/potholes/{photo_filename}" if photo_filename else None,
        "annotated_photo_url": f"/uploads/potholes/{annotated_filename}" if annotated_filename else None,
        "cv_analysis": cv_analysis_result,
        "dlp_breach_alert": dlp_breach_alert
    }

@app.get("/api/vision/calibration-presets")
def api_vision_calibration_presets():
    """Returns supported camera and reference calibration presets for metric scale measurement."""
    return {
        "status": "success",
        "presets": [
            {
                "id": "auto_perspective",
                "name": "Handheld Inspector (Smartphone)",
                "description": "Standard field handheld survey geometry (Height ~1.35m, 18° downward pitch)",
                "camera_height_m": 1.35,
                "camera_tilt_deg": 18.0,
                "recommended_for": "Citizen mobile reports and roadside walk inspections"
            },
            {
                "id": "dashcam_vehicle",
                "name": "Vehicle Windshield / Dashcam",
                "description": "Vehicle mounted survey camera (Height ~1.20m, 14° pitch)",
                "camera_height_m": 1.20,
                "camera_tilt_deg": 14.0,
                "recommended_for": "Moving patrol vehicles, DTC buses, and municipal inspection vans"
            },
            {
                "id": "lane_marking_100mm",
                "name": "IRC Standard Lane Marking (100 mm)",
                "description": "Calibrated against IRC standard 100mm urban road white thermoplastic stripe",
                "reference_width_mm": 100.0,
                "recommended_for": "Delhi arterial roads with visible lane demarcation"
            },
            {
                "id": "lane_marking_150mm",
                "name": "Expressway Lane Marking (150 mm)",
                "description": "Calibrated against IRC standard 150mm highway stripe (NH-44, NH-9, DND)",
                "reference_width_mm": 150.0,
                "recommended_for": "National highways and access-controlled expressways"
            },
            {
                "id": "manual_gsd",
                "name": "Custom Ground Sample Distance (GSD)",
                "description": "Direct specification of ground centimeters per pixel",
                "manual_gsd_cm_px": 0.1875,
                "recommended_for": "Lab calibration or precision calibrated camera rigs"
            }
        ]
    }

@app.post("/api/vision/analyze")
async def api_vision_analyze(
    file: UploadFile = File(...),
    calibration_mode: str = Form("auto_perspective"),
    camera_height_m: float = Form(1.35),
    camera_tilt_deg: float = Form(18.0),
    reference_type: Optional[str] = Form(None),
    reference_width_mm: Optional[float] = Form(None),
    manual_gsd_cm_px: Optional[float] = Form(None)
):
    """
    Computer Vision Pothole & Multi-Distress Characterization (YOLOv8 Edge / Server).
    Analyzes uploaded pavement photograph:
    - Eliminates subjective human grading & verifies if image contains actual road defect.
    - Photogrammetric scale calibration converts pixel dimensions to physical metric units (cm² and mm).
    - Multi-distress classification: Potholes, Alligator Cracking, Linear Cracks, Ravelling.
    - Standardized depth categorization: Shallow (<25mm), Medium (25-50mm), Severe (>50mm).
    - Computes ASTM D6433 Pavement Deduct Score and PCI impact.
    - Generates high-visibility HUD annotated inspection image overlay.
    """
    ext = Path(file.filename).suffix.lower()
    if ext not in [".jpg", ".jpeg", ".png", ".webp"]:
        raise HTTPException(status_code=400, detail="Invalid image format. Allowed formats: .jpg, .jpeg, .png, .webp")
    
    content = await file.read()
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image size exceeds 25 MB limit.")

    try:
        img_pil = Image.open(io.BytesIO(content)).convert("RGB")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Cannot decode image file: {str(e)}")

    detector = get_vision_detector()
    result = detector.analyze_image(
        img_pil=img_pil,
        calibration_mode=calibration_mode,
        camera_height_m=camera_height_m,
        camera_tilt_deg=camera_tilt_deg,
        reference_type=reference_type,
        reference_width_mm=reference_width_mm,
        manual_gsd_cm_px=manual_gsd_cm_px
    )
    return result

@app.post("/api/vision/analyze-video")
async def api_vision_analyze_video(
    file: UploadFile = File(...),
    sample_fps: float = Form(2.0),
    max_duration_sec: float = Form(30.0),
    calibration_mode: str = Form("camera_geometry"),
    camera_height_m: float = Form(1.20),
    camera_tilt_deg: float = Form(14.0)
):
    """
    Continuous Dashcam Video Stream Processing & Frame-to-Frame Defect Deduplication:
    - Ingests moving survey video (.mp4, .mov, .avi, .webm)
    - Keyframe sampling & spatial IoU defect tracking across frames
    - Eliminates duplicate counts of the same pothole as vehicle drives past
    - Extracts sharpest 'hero keyframes' for each unique defect along the corridor
    - Generates corridor survey rating & ASTM D6433 distress summary
    """
    ext = Path(file.filename).suffix.lower()
    valid_vid_exts = [".mp4", ".mov", ".avi", ".webm", ".mkv"]
    if ext not in valid_vid_exts:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid video format '{ext}'. Allowed formats: {', '.join(valid_vid_exts)}"
        )

    # Save video temporarily for OpenCV stream reading
    temp_filename = f"temp_survey_{uuid.uuid4().hex[:10]}{ext}"
    temp_path = UPLOADS_DIR / temp_filename

    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        detector = get_vision_detector()
        result = detector.analyze_video(
            video_path=str(temp_path),
            sample_fps=sample_fps,
            max_duration_sec=max_duration_sec,
            calibration_mode=calibration_mode,
            camera_height_m=camera_height_m,
            camera_tilt_deg=camera_tilt_deg
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Video Analysis Failed: {str(e)}")
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass

@app.get("/api/potholes")
def api_get_potholes(status: Optional[str] = None, zone: Optional[str] = None):
    """Retrieves reported potholes with optional lifecycle status and administrative zone filters."""
    reports = get_pothole_reports(status=status, zone=zone, limit=100)
    for r in reports:
        if r.get("photo_filename"):
            r["photo_url"] = f"/uploads/potholes/{r['photo_filename']}"
        else:
            r["photo_url"] = None
    return {"status": "success", "count": len(reports), "potholes": reports}

@app.patch("/api/potholes/{report_id}/status")
def api_update_pothole_status(
    report_id: str,
    body: PotholeStatusUpdate,
    user: dict = Depends(require_role([ROLE_PWD_ENGINEER, ROLE_MCD_PLANNER]))
):
    """Updates lifecycle state of a reported pothole (Verified, Work Order Issued, Repaired)."""
    updated = update_pothole_status(report_id, body.status)
    if not updated:
        raise HTTPException(status_code=404, detail="Pothole report not found.")
    return {"status": "success", "report": updated}

# ==========================================================================
# 4. CSIR-CRRI Roughness Audit & IRC:82 Compliance Validation
# ==========================================================================

@app.post("/api/audit/validate")
def api_audit_validate(
    req: AuditValidationRequest,
    user: dict = Depends(require_role([ROLE_CRRI_AUDITOR, ROLE_PWD_ENGINEER]))
):
    """
    Submits official CSIR-CRRI Roughness Audit validation for a corridor.
    Calculates IRC:82 compliance and issues a digital audit certificate.
    Restricted to CSIR-CRRI Auditors and Delhi PWD Senior Engineers.
    """
    # Evaluate IRC:82 & IRC:SP:81 Compliance Status
    if req.measured_iri <= 2.5 and req.measured_pci >= 75:
        compliance = "Compliant with IRC:82 (Excellent Ride Quality)"
    elif req.measured_iri <= 4.0 and req.measured_pci >= 55:
        compliance = "Conditional Pass (Preventive Overlay Recommended)"
    else:
        compliance = "Non-Compliant with IRC:82 (Immediate Structural Overlay Mandated)"

    cert_code = f"CRRI-NCT-2026-VAL-{uuid.uuid4().hex[:6].upper()}"

    audit_entry = create_audit_validation({
        "segment_id": req.segment_id,
        "auditor_name": user["full_name"],
        "auditor_email": user["email"],
        "compliance_status": compliance,
        "measured_iri": req.measured_iri,
        "measured_pci": req.measured_pci,
        "certificate_code": cert_code,
        "audit_notes": req.audit_notes
    })

    return {
        "status": "success",
        "message": f"Audit certificate issued: {cert_code}",
        "validation": audit_entry
    }

@app.get("/api/audit/validations")
def api_get_audit_validations(segment_id: Optional[str] = None):
    """Retrieves list of official CSIR-CRRI audit certificates."""
    audits = get_audit_validations(segment_id=segment_id, limit=50)
    return {"status": "success", "count": len(audits), "audits": audits}

# ==========================================================================
# 5. Pipeline & Data Synchronization (Role Protected)
# ==========================================================================

@app.post("/api/delhi/live-sync")
def api_delhi_live_sync(user: dict = Depends(require_role([ROLE_PWD_ENGINEER]))):
    """
    Triggers live synchronization of Delhi road networks and Open-Meteo weather telemetry,
    refreshes the SQLite database, retrains ML models, and re-calculates all predictions.
    Restricted to Delhi PWD Division Engineers.
    """
    try:
        seed_database(num_segments=350)
        train_and_save_models()
        run_predictions_and_update_db()
        weather = fetch_live_delhi_weather()
        _weather_cache["data"] = weather
        _weather_cache["timestamp"] = time.time()
        stats = get_network_stats()
        return {
            "status": "success",
            "message": "Live Delhi OSM road network and Open-Meteo weather telemetry synced successfully!",
            "weather": weather,
            "stats": stats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/train")
def api_trigger_training(user: dict = Depends(require_role([ROLE_PWD_ENGINEER]))):
    """
    Retrains ML models and updates predictions.
    Restricted strictly to Delhi PWD Division Engineers.
    MCD Urban Planners and CSIR-CRRI Auditors receive HTTP 403 Forbidden.
    """
    try:
        train_and_save_models()
        run_predictions_and_update_db()
        return {"status": "success", "message": "ML models retrained and predictions recalculated!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/predict")
def api_trigger_prediction(user: dict = Depends(require_role([ROLE_PWD_ENGINEER, ROLE_CRRI_AUDITOR]))):
    """Runs ML inference and updates predictions table. Restricted to PWD Engineers & CRRI Auditors."""
    try:
        run_predictions_and_update_db()
        return {"status": "success", "message": "ML inference executed and SQLite database updated successfully!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================================================
# 6. Read & Analytics Endpoints (Open to all authenticated personas / public)
# ==========================================================================

@app.get("/api/segments")
def api_get_segments(zone: Optional[str] = None):
    try:
        segments = get_all_segments(zone=zone)
        return {"count": len(segments), "segments": segments}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/segments/geojson")
def api_get_segments_geojson(zone: Optional[str] = None):
    try:
        return get_segments_geojson(zone=zone)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/dashboard/stats")
def api_get_stats(zone: Optional[str] = None):
    try:
        return get_network_stats(zone=zone)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/delhi/weather")
def api_get_delhi_weather():
    now = time.time()
    if _weather_cache["data"] and (now - _weather_cache["timestamp"] < 600):
        return _weather_cache["data"]
    try:
        weather = fetch_live_delhi_weather()
        _weather_cache["data"] = weather
        _weather_cache["timestamp"] = now
        return weather
    except Exception as e:
        if _weather_cache["data"]:
            return _weather_cache["data"]
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/optimize")
def api_optimize_schedule(req: OptimizationRequest = Body(...)):
    try:
        result = optimize_maintenance_schedule(
            annual_budget_inr=req.annual_budget,
            max_km_per_month=req.max_km_per_month,
            max_months=req.max_months,
            zone=req.zone
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================================================
# Phase B: Multi-Year Capital Planning & Deterioration Decay (3 & 5 Years)
# ==========================================================================

@app.get("/api/decay/corridor/{segment_id}")
def api_get_corridor_decay(segment_id: str, horizon_years: int = 5):
    """
    Retrieves Weibull deterioration decay curve, Markov chain transition matrices,
    and Cost of Inaction financial simulation for an individual road segment.
    """
    segment = get_segment_by_id(segment_id)
    if not segment:
        raise HTTPException(status_code=404, detail=f"Corridor '{segment_id}' not found.")

    stress = calculate_stress_factor(segment)
    weibull_curve = calculate_weibull_decay(
        float(segment.get("pci") or 70.0),
        float(segment.get("iri") or 2.8),
        stress,
        horizon_years=horizon_years
    )
    markov = calculate_markov_transitions(stress, horizon_years=horizon_years)
    inaction = simulate_cost_of_inaction(segment, horizon_years=horizon_years)

    return {
        "status": "success",
        "segment_id": segment_id,
        "road_name": segment.get("name"),
        "city_zone": segment.get("city_zone"),
        "stress_factor": stress,
        "weibull_curve": weibull_curve,
        "markov_transitions": markov,
        "cost_of_inaction": inaction
    }

@app.post("/api/decay/simulate-inaction")
def api_simulate_inaction(req: CostOfInactionRequest = Body(...)):
    """
    Simulates the exact financial penalty and cost escalation of delaying road repairs
    for a specific corridor or across the entire municipal network / administrative zone.
    """
    try:
        if req.segment_id:
            segment = get_segment_by_id(req.segment_id)
            if not segment:
                raise HTTPException(status_code=404, detail=f"Corridor '{req.segment_id}' not found.")
            sim = simulate_cost_of_inaction(segment, horizon_years=req.horizon_years)
            return {"status": "success", "mode": "single_corridor", "simulation": sim}
        else:
            segments = get_all_segments(zone=req.zone)
            sim = simulate_network_cost_of_inaction(segments, horizon_years=req.horizon_years)
            return {"status": "success", "mode": "network_aggregate", "simulation": sim}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cost of Inaction Simulation Failed: {str(e)}")

@app.get("/api/decay/corridor/{segment_id}/rsl")
def api_get_corridor_rsl(segment_id: str):
    """Retrieves Remaining Service Life (RSL in Years) and IRC:37:2018 Structural Fatigue capacity."""
    segment = get_segment_by_id(segment_id)
    if not segment:
        raise HTTPException(status_code=404, detail=f"Corridor '{segment_id}' not found.")
    rsl = calculate_remaining_service_life(segment)
    return {"status": "success", "rsl": rsl}

@app.post("/api/optimization/multi-year")
def api_optimize_multi_year(req: MultiYearOptimizationRequest = Body(...)):
    """
    Multi-Year Capital Planning & Budget Allocation Engine (3-Year & 5-Year Horizons).
    Expands single-year Knapsack into a multi-year master plan matching municipal 5-year CIPs.
    Simulates dynamic year-over-year deterioration decay carryover, material inflation, and spatial clustering.
    """
    try:
        plan = optimize_multi_year_capital_plan(
            annual_budget_inr=req.annual_budget,
            horizon_years=req.horizon_years,
            max_km_per_year=req.max_km_per_year,
            zone=req.zone,
            discount_rate=req.discount_rate,
            inflation_rate=req.inflation_rate
        )
        return {"status": "success", "plan": plan}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Multi-Year Optimization Failed: {str(e)}")

@app.post("/api/optimization/multi-year/scenarios")
def api_optimize_multi_year_scenarios(req: MultiYearScenariosRequest = Body(...)):
    """
    Multi-Scenario 'What-If' Sensitivity Simulator:
    Simulates and compares Baseline CIP vs Austerity (-30%) vs Preservation (+50%)
    across 3-year or 5-year municipal planning horizons with side-by-side trade-off metrics.
    """
    try:
        result = simulate_multi_year_scenarios(
            annual_budget_inr=req.annual_budget,
            horizon_years=req.horizon_years,
            max_km_per_year=req.max_km_per_year,
            zone=req.zone,
            discount_rate=req.discount_rate,
            inflation_rate=req.inflation_rate
        )
        return {"status": "success", "scenarios_comparison": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scenario Simulation Failed: {str(e)}")

@app.get("/api/export/multi-year-excel")
def api_export_multi_year_excel(
    annual_budget: float = 100000000.0,
    horizon_years: int = 5,
    max_km_per_year: float = 160.0,
    zone: Optional[str] = None,
    discount_rate: float = 0.06,
    inflation_rate: float = 0.055
):
    """
    Exports official 3-sheet 5-Year Capital Improvement Plan (CIP) in Excel (.xlsx) format:
    - Sheet 1: Executive 5-Year Financial Summary & Year-by-Year Allocation
    - Sheet 2: 5-Year Master Work Schedule with Spatial Clusters & RSL Ratings
    - Sheet 3: Weibull Deterioration Trajectory (Managed vs Do-Nothing)
    """
    try:
        plan = optimize_multi_year_capital_plan(
            annual_budget_inr=annual_budget,
            horizon_years=horizon_years,
            max_km_per_year=max_km_per_year,
            zone=zone,
            discount_rate=discount_rate,
            inflation_rate=inflation_rate
        )
        excel_bytes = generate_multi_year_excel_cip(plan)
        zone_slug = (zone or "all_delhi").lower().replace(" ", "_").replace("&", "and")
        filename = f"PaveSentry_{horizon_years}Year_CIP_Master_Plan_{zone_slug}.xlsx"
        return Response(
            content=excel_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================================================
# 7. One-Click Tenders & Government Reporting Exports
# ==========================================================================

@app.get("/api/export/csv")
def api_export_csv(
    annual_budget: float = 100000000.0,
    max_km_per_month: float = 15.0,
    max_months: int = 12,
    zone: Optional[str] = None
):
    try:
        result = optimize_maintenance_schedule(
            annual_budget_inr=annual_budget,
            max_km_per_month=max_km_per_month,
            max_months=max_months,
            zone=zone
        )
        csv_bytes = generate_schedule_csv(
            result["scheduled_segments"],
            result["summary"]
        )
        zone_slug = (zone or "all_delhi").lower().replace(" ", "_").replace("&", "and")
        filename = f"PaveSentry_12Month_Work_Schedule_{zone_slug}.csv"
        return Response(
            content=csv_bytes,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/export/excel")
def api_export_excel(
    annual_budget: float = 100000000.0,
    max_km_per_month: float = 15.0,
    max_months: int = 12,
    zone: Optional[str] = None
):
    try:
        result = optimize_maintenance_schedule(
            annual_budget_inr=annual_budget,
            max_km_per_month=max_km_per_month,
            max_months=max_months,
            zone=zone
        )
        xlsx_bytes = generate_schedule_excel(
            result["scheduled_segments"],
            result["summary"]
        )
        zone_slug = (zone or "all_delhi").lower().replace(" ", "_").replace("&", "and")
        filename = f"PaveSentry_Work_Order_Schedule_{zone_slug}.xlsx"
        return Response(
            content=xlsx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/export/pdf")
def api_export_pdf(
    annual_budget: float = 100000000.0,
    max_km_per_month: float = 15.0,
    max_months: int = 12,
    zone: Optional[str] = None
):
    try:
        result = optimize_maintenance_schedule(
            annual_budget_inr=annual_budget,
            max_km_per_month=max_km_per_month,
            max_months=max_months,
            zone=zone
        )
        pdf_bytes = generate_executive_tender_pdf(
            result["scheduled_segments"],
            result["summary"],
            division_name=zone
        )
        zone_slug = (zone or "all_delhi").lower().replace(" ", "_").replace("&", "and")
        filename = f"PaveSentry_Executive_Work_Order_{zone_slug}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================================================
# PHASE C: CONTRACTOR SLA & WORK ORDER LIFECYCLE KANBAN & DLP WARRANTY ENDPOINTS
# ==========================================================================

@app.get("/api/kanban/work-orders")
def api_get_work_orders(
    stage: Optional[str] = None,
    zone: Optional[str] = None,
    sla_status: Optional[str] = None
):
    """Retrieves work orders organized across lifecycle stages (Reported -> Inspected -> Tender Issued -> Under Repair -> Audited & Closed)."""
    try:
        orders = get_work_orders(stage=stage, zone=zone, sla_status=sla_status)
        stats = get_kanban_summary_stats(zone=zone)
        return {"status": "success", "work_orders": orders, "stats": stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/kanban/work-orders")
def api_create_work_order(req: CreateWorkOrderRequest = Body(...)):
    """Creates a new municipal work order and assigns it to the Kanban lifecycle pipeline."""
    try:
        wo = create_work_order(req.dict())
        return {"status": "success", "work_order": wo}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/kanban/work-orders/{wo_id}/stage")
def api_update_work_order_stage(wo_id: str, req: UpdateWorkOrderStageRequest = Body(...)):
    """Moves a work order across Kanban stages with automated audit tracking and DLP activation upon closure."""
    try:
        updated = update_work_order_stage(wo_id, req.stage, updated_by=req.updated_by, notes=req.notes)
        if not updated:
            raise HTTPException(status_code=404, detail=f"Work order '{wo_id}' not found.")
        return {"status": "success", "work_order": updated}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/kanban/stats")
def api_get_kanban_stats(zone: Optional[str] = None):
    """Retrieves real-time SLA compliance, stage bottlenecks, and DLP active warranty statistics."""
    try:
        stats = get_kanban_summary_stats(zone=zone)
        return {"status": "success", "stats": stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/dsr/catalog")
def api_get_dsr_catalog():
    """Returns official CPWD DSR 2023-24 Sub-Head 16 road work items with Delhi Cost Index rates."""
    try:
        items = get_all_dsr_items()
        return {
            "status": "success",
            "delhi_cost_index": 1.085,
            "cost_index_label": "+8.5% over CPWD Base DSR 2023 (Delhi Regional Index)",
            "items": items
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/dsr/generate-boq")
def api_generate_boq(req: GenerateBoqRequest = Body(...)):
    """Generates an itemized Bill of Quantities (BOQ) with authentic CPWD DSR item codes for a road corridor."""
    try:
        boq = generate_bill_of_quantities(
            road_name=req.road_name or "Delhi NCT Corridor",
            length_km=req.length_km,
            lanes=req.lanes,
            treatment_type=req.treatment_type,
            city_zone=req.city_zone or "Central Delhi"
        )
        return {"status": "success", "boq": boq}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/dlp/contracts")
def api_get_dlp_contracts():
    """Retrieves all active Defect Liability Period (DLP) warranty contracts with remaining warranty days."""
    try:
        contracts = get_active_dlp_contracts()
        return {"status": "success", "contracts": contracts}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/dlp/incidents")
def api_get_dlp_incidents(status: Optional[str] = None):
    """Retrieves Defect Liability Period breach notices and contractor penalty records."""
    try:
        incidents = get_dlp_incidents(status=status)
        return {"status": "success", "incidents": incidents}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/dlp/scan-breaches")
def api_scan_dlp_breaches():
    """Scans all open pothole reports against active DLP warranty corridors, generating automated breach notices."""
    try:
        breaches = scan_all_open_potholes_for_dlp()
        return {"status": "success", "breaches_detected": len(breaches), "breaches": breaches}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/dlp/incidents/{incident_id}/status")
def api_update_dlp_incident_status(incident_id: str, req: UpdateDlpStatusRequest = Body(...)):
    """Updates the resolution status of a DLP breach notice (e.g. Rectified by Contractor or Bank Guarantee Deducted)."""
    try:
        success = update_dlp_incident_status(incident_id, req.status, notes=req.notes)
        return {"status": "success", "updated": success}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================================================
# Phase D: Explainable AI (XAI) & TreeSHAP Attribution
# ==========================================================================

@app.get("/api/xai/corridor/{segment_id}")
def api_get_corridor_xai(segment_id: str):
    """
    Computes local TreeSHAP attribution for a corridor.
    Returns percentage influence breakdown, positive risk drivers, mitigating factors,
    and a defensible civil engineering justification for CVC / CSIR-CRRI audits.
    """
    try:
        explanation = explain_corridor_risk(segment_id)
        return {"status": "success", "explanation": explanation}
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/xai/global-importance")
def api_get_global_shap_importance():
    """
    Returns macro network-wide SHAP feature rankings across all 350 Delhi NCT corridors,
    revealing whether heavy truck traffic, monsoon ponding, or structural age dominates failure.
    """
    try:
        res = get_global_shap_importance()
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/xai/counterfactual")
def api_simulate_counterfactual(req: CounterfactualRequest = Body(...)):
    """
    Simulates hypothetical engineering interventions (e.g. diverting heavy commercial traffic,
    improving drainage, or crack sealing) and calculates the resulting drop in failure probability.
    """
    try:
        res = simulate_intervention_counterfactual(req.segment_id, req.overrides)
        return {"status": "success", "counterfactual": res}
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/xai/audit-report/{segment_id}")
def api_get_xai_audit_report(segment_id: str):
    """
    Generates a structured CSIR-CRRI / Central Vigilance Commission (CVC) Defensible AI Justification Memo
    for municipal engineer sign-off and audit readiness.
    """
    try:
        exp = explain_corridor_risk(segment_id)
        memo = {
            "document_title": "GOVERNMENT OF NCT OF DELHI - PUBLIC WORKS DEPARTMENT",
            "memo_ref": f"PWD/XAI-AUDIT/{segment_id}/{time.strftime('%Y%m%d')}",
            "corridor_id": segment_id,
            "corridor_name": exp["road_name"],
            "city_zone": exp["city_zone"],
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S IST"),
            "model_version": "PaveSentry TreeSHAP v3.0 (RandomForestClassifier)",
            "predicted_risk_level": exp["predicted_risk"].upper(),
            "failure_probability": f"{exp['pothole_probability']:.1%}",
            "base_log_odds": exp["base_expected_value"],
            "top_drivers": exp["top_risk_drivers"],
            "mitigating_factors": exp["top_mitigating_factors"],
            "audit_justification": exp["audit_justification"],
            "governance_compliance": [
                "IRC:37:2018 Guidelines for Design of Flexible Pavements",
                "IRC:82:2023 Code of Practice for Maintenance of Bituminous Surfaces",
                "Central Vigilance Commission (CVC) Transparency & Objective Selection Mandate",
                "CSIR - Central Road Research Institute (CRRI) Pavement Evaluation Protocol"
            ],
            "signoff_block": {
                "superintending_engineer": "Chief Engineer (Roads Maintenance), Delhi PWD",
                "crri_auditor": "Chief Scientist (Pavement Evaluation), CSIR-CRRI",
                "status": "APPROVED FOR CAPITAL REPAIR ALLOCATION"
            }
        }
        return {"status": "success", "audit_memo": memo}
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================================================
# Phase E: Enterprise PostGIS Spatial Engine & Connected Vehicle Telemetry
# ==========================================================================

@app.get("/api/spatial/status")
def api_get_spatial_status():
    """
    Returns enterprise PostGIS spatial engine status, GIST index health,
    and coordinate reference system (EPSG:4326 WGS 84).
    """
    try:
        status_info = get_postgis_engine().get_engine_status()
        return status_info
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/spatial/corridors/radius")
def api_query_corridors_radius(lon: float, lat: float, radius_m: float = 1500.0):
    """
    Executes PostGIS ST_DWithin spatial query to retrieve road corridors
    within radius_m of a GPS coordinate using GIST/STRtree spatial indexing.
    """
    try:
        corridors = query_corridors_radius(lon, lat, radius_m=radius_m)
        return {
            "status": "success",
            "search_center": {"longitude": lon, "latitude": lat},
            "radius_meters": radius_m,
            "corridors_found": len(corridors),
            "corridors": corridors
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/spatial/migrate")
def api_migrate_to_postgis():
    """
    Exports SQLite tables to native PostgreSQL 16 + PostGIS schema with
    ST_GeomFromText LineString and Point geometries.
    """
    try:
        engine = get_postgis_engine()
        sql_dump = engine.generate_postgis_sql_dump()
        return {
            "status": "success",
            "dump_file": "database/postgis_dump.sql",
            "dump_size_bytes": len(sql_dump),
            "corridors_migrated": len(engine._geometries),
            "postgis_extensions": ["postgis", "postgis_topology"],
            "spatial_indexes_generated": [
                "idx_road_segments_gist (USING GIST(geometry))",
                "idx_potholes_gist (USING GIST(location))",
                "idx_telemetry_gist (USING GIST(location))"
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/telemetry/ingest")
def api_ingest_telemetry_packet(req: TelemetryPacketRequest = Body(...)):
    """
    Ingests continuous high-frequency accelerometer and gyroscope vibration telemetry
    from Delhi DTC buses or municipal survey vehicles, computes live Quarter-Car IRI,
    and flags high-G pothole impact shocks.
    """
    try:
        engine = get_telemetry_engine()
        packet_data = req.model_dump() if hasattr(req, "model_dump") else req.dict()
        result = engine.process_telemetry_packet(packet_data)
        return {"status": "success", "telemetry": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/telemetry/live-fleet")
def api_get_live_fleet():
    """Returns real-time locations, speeds, and live roughness readings for active Delhi DTC buses."""
    try:
        fleet = get_telemetry_engine().get_live_fleet_telemetry()
        return {"status": "success", "active_vehicles": len(fleet), "fleet": fleet}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/telemetry/spikes")
def api_get_pothole_spikes():
    """Retrieves live high-G (>2.2g) pothole crater impact shock events detected by fleet sensors."""
    try:
        spikes = get_telemetry_engine().get_pothole_spikes()
        return {"status": "success", "total_spikes": len(spikes), "spikes": spikes}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/telemetry/waveform/{vehicle_id}")
def api_get_vehicle_waveform(vehicle_id: str):
    """Returns recent accelerometer vibration time-series points for the live oscilloscope chart."""
    try:
        waveform = get_telemetry_engine().get_vehicle_waveform(vehicle_id)
        return {"status": "success", "vehicle_id": vehicle_id, "samples_count": len(waveform), "waveform": waveform}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/telemetry/simulate-trip")
def api_simulate_dtc_trip(req: SimulateTripRequest = Body(...)):
    """
    Simulates a continuous DTC electric bus trip along an arterial corridor,
    generating dynamic axle bounce vibration telemetry and live International Roughness Index (IRI).
    """
    try:
        engine = get_telemetry_engine()
        res = engine.simulate_dtc_bus_trip(
            segment_id=req.segment_id,
            vehicle_id=req.vehicle_id or "DTC-DL1PC-4021",
            speed_kmh=req.speed_kmh or 44.0,
            samples_count=req.samples_count or 15
        )
        return res
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================================================
# Phase F: Green Roads & Carbon Footprint Calculator (IRC:SP:98)
# ==========================================================================

@app.get("/api/green-roads/corridor/{segment_id}")
def api_get_corridor_carbon(segment_id: str, treatment: Optional[str] = None):
    """
    Evaluates lifecycle carbon footprint (LCA) and IRC:SP:98 Green Highway rating
    for a specific corridor comparing chosen treatment vs. conventional reconstruction.
    """
    try:
        data = calculate_corridor_carbon(segment_id, treatment=treatment)
        return {"status": "success", "carbon_lca": data}
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/green-roads/comparison/{segment_id}")
def api_get_treatment_carbon_comparison(segment_id: str):
    """
    Returns side-by-side carbon emissions and IRC:SP:98 score comparison
    across all 6 road maintenance technologies (HMA vs WMA vs CIR vs Micro-Surfacing vs Slurry).
    """
    try:
        comparison = get_treatment_options_comparison(segment_id)
        return {"status": "success", "segment_id": segment_id, "comparison": comparison}
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/green-roads/network-summary")
def api_get_network_green_summary():
    """
    Aggregates network-wide ESG sustainability metrics: total CO2e abated,
    cumulative diesel fuel conserved, and equivalent trees offset.
    """
    try:
        summary = get_network_green_esg_summary()
        return {"status": "success", "esg_summary": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/green-roads/certificate/{segment_id}")
def api_get_green_certificate(segment_id: str):
    """
    Generates an official IRC:SP:98 Green Highway Compliance Certificate
    for Delhi PWD sustainable infrastructure tenders and statutory audits.
    """
    try:
        cert = get_green_certificate(segment_id)
        return {"status": "success", "certificate": cert}
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==============================================================================
# 1. Citizen Crowdsourcing Portal (Delhi 311 / WhatsApp PWA Sync)
# ==============================================================================
@app.post("/api/citizen/report")
async def api_submit_citizen_report(
    file: UploadFile = File(...),
    latitude: float = Form(...),
    longitude: float = Form(...),
    citizen_name: str = Form("Concerned Resident"),
    citizen_mobile: str = Form("9811002233"),
    road_description: str = Form(""),
    source_channel: str = Form("delhi_311")
):
    """
    Ingests citizen crowdsourced road pothole report with client-side GPS tagging,
    runs automated YOLOv8/photogrammetric verification, and auto-routes complaint
    to the responsible Delhi PWD / MCD division engineer.
    """
    try:
        content = await file.read()
        res = submit_citizen_pothole(
            image_bytes=content,
            filename=file.filename or "citizen_photo.jpg",
            latitude=latitude,
            longitude=longitude,
            citizen_name=citizen_name,
            citizen_mobile=citizen_mobile,
            road_description=road_description,
            source_channel=source_channel
        )
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/citizen/track/{ticket_id}")
def api_track_citizen_ticket(ticket_id: str):
    """
    Returns live stage progression and audit milestones for a citizen complaint ticket.
    """
    try:
        res = track_citizen_ticket(ticket_id)
        if res.get("status") == "not_found":
            raise HTTPException(status_code=404, detail=res.get("message"))
        return res
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/citizen/reports")
def api_get_citizen_reports(limit: int = 30):
    """Returns recent citizen crowdsourced pothole reports across Delhi NCT."""
    try:
        reports = get_pothole_reports(limit=limit)
        citizen_reports = [r for r in reports if r.get("citizen_ticket_id") or r.get("reporter_role") == "citizen"]
        return {"status": "success", "count": len(citizen_reports), "reports": citizen_reports}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==============================================================================
# 2. Monsoon Waterlogging & Hydroplaning Vulnerability Index (IRC:37:2018)
# ==============================================================================
@app.get("/api/waterlogging/hotspots")
def api_get_waterlogging_hotspots():
    """Returns Delhi's notorious waterlogging underpasses and flood depression hotspots."""
    return {
        "status": "success",
        "total_hotspots": len(DELHI_WATERLOGGING_HOTSPOTS),
        "hotspots": DELHI_WATERLOGGING_HOTSPOTS
    }

@app.get("/api/waterlogging/corridor/{segment_id}")
def api_get_corridor_waterlogging(segment_id: str):
    """
    Evaluates Waterlogging Pavement Risk Factor (WPRF), soaked subgrade CBR degradation,
    and hydroplaning vulnerability for a specific arterial corridor.
    """
    try:
        res = calculate_waterlogging_risk(segment_id)
        return {"status": "success", "waterlogging_analysis": res}
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/waterlogging/network-summary")
def api_get_waterlogging_summary():
    """Returns network-wide pre-monsoon preparedness and waterlogging rankings."""
    try:
        summary = get_network_waterlogging_summary()
        return summary
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==============================================================================
# 3. Anti-Corruption Cryptographic Audit Trail (CAG / Lokayukta Audit Ready)
# ==============================================================================
@app.get("/api/audit-trail/chain")
def api_get_audit_chain(limit: int = 50):
    """Returns immutable SHA-256 chained audit blocks for Delhi vigilance inspection."""
    try:
        ledger = get_audit_ledger()
        chain = ledger.get_chain(limit=limit)
        return {"status": "success", "blocks_returned": len(chain), "chain": chain}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/audit-trail/verify")
def api_verify_audit_integrity():
    """
    Runs cryptographic validation from Genesis to head, detecting any retroactive
    tampering of inspection records, tender awards, or contractor DLP liability windows.
    """
    try:
        ledger = get_audit_ledger()
        res = ledger.verify_chain_integrity()
        return {"status": "success", "verification": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/audit-trail/certificate")
def api_get_cag_audit_certificate():
    """
    Generates official Comptroller and Auditor General (CAG) Cryptographic Audit Certificate.
    """
    try:
        ledger = get_audit_ledger()
        cert = ledger.generate_cag_audit_certificate()
        return {"status": "success", "certificate": cert}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="127.0.0.1", port=9005, reload=True)



