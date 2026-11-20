"""
Helper utility to automatically unzip and update ml/models/ with exported models from Google Colab.
"""
import os
import shutil
import zipfile
from pathlib import Path

import sys

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent
MODELS_DIR = ROOT_DIR / "ml" / "models"
ZIP_CANDIDATES = [
    Path("D:/exported_models.zip"),
    Path("E:/exported_models.zip"),
    ROOT_DIR / "exported_models.zip",
    Path.home() / "Downloads" / "exported_models.zip",
    Path.home() / "Downloads" / "exported_models (1).zip",
]

def update_models():
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    zip_found = None
    
    for candidate in ZIP_CANDIDATES:
        if candidate.exists():
            zip_found = candidate
            break
            
    if not zip_found:
        print("[!] 'exported_models.zip' not found in project root or Downloads folder.")
        print("Please place the downloaded 'exported_models.zip' in this folder and run again.")
        return False
        
    print(f"[+] Found model archive at: {zip_found}")
    with zipfile.ZipFile(zip_found, 'r') as zf:
        zf.extractall(MODELS_DIR)
        
    print(f"[+] Extracted files directly into: {MODELS_DIR}")
    for item in MODELS_DIR.iterdir():
        print(f"   - {item.name} ({item.stat().st_size:,} bytes)")
        
    print("\n[+] Testing ML prediction pipeline with new models...")
    from ml.predict import run_predictions_and_update_db
    run_predictions_and_update_db()
    print("[SUCCESS] Successfully connected Colab models to local SQLite database and dashboard!")
    return True

if __name__ == "__main__":
    update_models()
