import os
import sys
from pathlib import Path

# Ensure UTF-8 output on Windows terminals
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

import uvicorn

ROOT_DIR = Path(__file__).resolve().parent
sys.path.append(str(ROOT_DIR))

from data.seed_db import seed_database
from ml.train_models import train_and_save_models, MODELS_DIR
from ml.predict import run_predictions_and_update_db
from database.db_manager import DB_PATH

def main():
    print("=" * 70, flush=True)
    print("      PAVESENTRY: REAL-TIME DELHI NCT PAVEMENT INTELLIGENCE     ", flush=True)
    print("      Real-Time Data Ingestion, ML Inference & Optimization     ", flush=True)
    print("=" * 70, flush=True)
    
    # Step 1: Check / Seed Database
    if not DB_PATH.exists():
        print("\n[Step 1/3] Database not found. Ingesting authentic Delhi OSM data...", flush=True)
        seed_database(num_segments=350)
    else:
        print(f"\n[Step 1/3] SQLite database found at: {DB_PATH}", flush=True)
        
    # Step 2: Check / Train ML Models & Run Predictions
    model_file = MODELS_DIR / "risk_classifier.joblib"
    if not model_file.exists() or "--retrain" in sys.argv:
        print("\n[Step 2/3] Training machine learning models on Delhi road dataset...", flush=True)
        train_and_save_models()
        print("\n[Step 3/3] Running ML predictions & updating SQLite database...", flush=True)
        run_predictions_and_update_db()
    else:
        print(f"\n[Step 2/3] Pre-trained models verified at: {MODELS_DIR}", flush=True)
        print("[Step 3/3] Model inference ready. Database up-to-date.", flush=True)
    
    print("\n" + "=" * 70, flush=True)
    print("🚀 Launching Delhi Road Maintenance Dashboard & REST API server...", flush=True)
    print("🌐 Dashboard URL: http://127.0.0.1:9005", flush=True)
    print("📚 API Documentation: http://127.0.0.1:9005/docs", flush=True)
    print("=" * 70 + "\n", flush=True)
    
    uvicorn.run("backend.main:app", host="127.0.0.1", port=9005, reload=True)

if __name__ == "__main__":
    main()
