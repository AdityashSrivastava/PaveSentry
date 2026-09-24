import os
import sys
from pathlib import Path
from fastapi import FastAPI, HTTPException, Body
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

from database.db_manager import get_all_segments, get_segments_geojson, get_network_stats, init_db
from ml.predict import run_predictions_and_update_db
from ml.train_models import train_and_save_models
from optimization.scheduler import optimize_maintenance_schedule
from data.seed_db import seed_database
from data.fetch_real_delhi_data import fetch_live_delhi_weather

app = FastAPI(
    title="PaveSentry: Real-Time Delhi Pavement Intelligence API",
    description="AI-driven predictive pavement management and budget optimization for Delhi NCR road networks (Delhi PWD / MCD / CRRI / NDMC)",
    version="2.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = ROOT_DIR / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

class OptimizationRequest(BaseModel):
    annual_budget: float = 100000000.0  # ₹10 Crores default
    max_km_per_month: float = 15.0
    max_months: int = 12

@app.on_event("startup")
def startup_event():
    """Ensure DB and model predictions exist on startup."""
    init_db()

@app.get("/", response_class=HTMLResponse)
def read_root():
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return "<h2>PaveSentry API is running. Dashboard static files not found.</h2>"

@app.get("/api/segments")
def api_get_segments():
    try:
        segments = get_all_segments()
        return {"count": len(segments), "segments": segments}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/segments/geojson")
def api_get_segments_geojson():
    try:
        return get_segments_geojson()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/dashboard/stats")
def api_get_stats():
    try:
        return get_network_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/delhi/weather")
def api_get_delhi_weather():
    try:
        weather = fetch_live_delhi_weather()
        return weather
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/delhi/live-sync")
def api_delhi_live_sync():
    """
    Triggers live synchronization of Delhi road networks and Open-Meteo weather telemetry,
    refreshes the SQLite database, retrains ML models, and re-calculates all predictions.
    """
    try:
        seed_database(num_segments=350)
        train_and_save_models()
        run_predictions_and_update_db()
        weather = fetch_live_delhi_weather()
        stats = get_network_stats()
        return {
            "status": "success",
            "message": "Live Delhi OSM road network and Open-Meteo weather telemetry synced successfully!",
            "weather": weather,
            "stats": stats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/predict")
def api_trigger_prediction():
    try:
        run_predictions_and_update_db()
        return {"status": "success", "message": "ML inference executed and SQLite database updated successfully!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/train")
def api_trigger_training():
    try:
        train_and_save_models()
        run_predictions_and_update_db()
        return {"status": "success", "message": "ML models retrained and predictions recalculated!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/optimize")
def api_optimize_schedule(req: OptimizationRequest = Body(...)):
    try:
        result = optimize_maintenance_schedule(
            annual_budget_inr=req.annual_budget,
            max_km_per_month=req.max_km_per_month,
            max_months=req.max_months
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=9005, reload=True)
