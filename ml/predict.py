import os
import sys
import joblib
import sqlite3
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

from database.db_manager import get_all_segments, get_connection
from ml.train_models import extract_features, MODELS_DIR

def run_predictions_and_update_db():
    """
    Runs ML inference on all database segments, calculates composite priority scores,
    establishes preventive vs. reactive cost estimates, and updates the SQLite predictions table.
    """
    scaler_path = MODELS_DIR / "scaler.joblib"
    risk_clf_path = MODELS_DIR / "risk_classifier.joblib"
    decay_reg_path = MODELS_DIR / "decay_regressor.joblib"
    cost_reg_path = MODELS_DIR / "cost_regressor.joblib"
    
    if not (scaler_path.exists() and risk_clf_path.exists()):
        raise FileNotFoundError("Trained model files not found. Please run ml/train_models.py first.")
        
    scaler = joblib.load(scaler_path)
    clf_risk = joblib.load(risk_clf_path)
    reg_decay = joblib.load(decay_reg_path)
    reg_cost = joblib.load(cost_reg_path)
    
    segments = get_all_segments()
    if not segments:
        print("No segments found in database.")
        return
        
    df = pd.DataFrame(segments)
    X = extract_features(df)
    X_scaled = scaler.transform(X)
    
    # Predict risk levels and probabilities
    risk_preds = clf_risk.predict(X_scaled)
    risk_probs = clf_risk.predict_proba(X_scaled)
    
    # Map high-risk index
    classes = list(clf_risk.classes_)
    high_idx = classes.index("High") if "High" in classes else 0
    pothole_probs = risk_probs[:, high_idx]
    
    # Predict time to failure (months)
    fail_months_preds = reg_decay.predict(X_scaled)
    
    # Predict reactive cost
    reactive_cost_preds = reg_cost.predict(X_scaled)
    
    # Calculate preventive cost (typically ~25-35% of reactive cost for early intervention)
    preventive_cost_preds = np.round(reactive_cost_preds * 0.28, 2)
    reactive_cost_preds = np.round(reactive_cost_preds, 2)
    
    # Priority Score calculation
    # Normalized AADT factor (0 to 1)
    aadt_factor = np.clip(df["aadt"] / 50000.0, 0.0, 1.0)
    pci_distress_factor = np.clip((100.0 - df["pci"]) / 100.0, 0.0, 1.0)
    savings_ratio = np.clip((reactive_cost_preds - preventive_cost_preds) / (preventive_cost_preds + 1.0), 0.0, 5.0) / 5.0
    
    priority_scores = np.round(
        0.40 * pothole_probs + 
        0.25 * aadt_factor + 
        0.20 * pci_distress_factor + 
        0.15 * savings_ratio, 
        3
    )
    
    predictions_data = []
    updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    for i, row in df.iterrows():
        seg_id = row["segment_id"]
        risk_level = risk_preds[i]
        p_prob = float(round(pothole_probs[i], 3))
        fail_m = float(round(fail_months_preds[i], 1))
        prev_cost = float(preventive_cost_preds[i])
        react_cost = float(reactive_cost_preds[i])
        p_score = float(priority_scores[i])
        pci = row["pci"]
        
        # Action recommendation logic based on IRC (Indian Roads Congress) standards
        if pci < 48 or (risk_level == "High" and pci < 58):
            action = "Full Reconstruction & Sub-base Work (IRC:37)"
        elif pci < 68 or risk_level == "High":
            action = "Bituminous Concrete (BC) Mill & Overlay (IRC:82)"
        elif pci < 82 or risk_level == "Medium":
            action = "Preventive Micro-Surfacing & Slurry Seal (IRC:SP:81)"
        else:
            action = "Routine Inspection & Monsoon Drain Clearance"
            
        predictions_data.append((
            seg_id,
            risk_level,
            p_prob,
            fail_m,
            prev_cost,
            react_cost,
            p_score,
            action,
            updated_at
        ))
        
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.executemany("""
    INSERT OR REPLACE INTO predictions (
        segment_id,
        predicted_risk_level,
        pothole_probability,
        est_time_to_failure_months,
        est_preventive_cost_inr,
        est_reactive_cost_inr,
        priority_score,
        recommended_action,
        updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, predictions_data)
    
    conn.commit()
    conn.close()
    print(f"Updated predictions for {len(predictions_data)} segments in SQLite database!")

if __name__ == "__main__":
    run_predictions_and_update_db()
