import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import classification_report, mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

from database.db_manager import get_all_segments

MODELS_DIR = Path(__file__).resolve().parent / "models"
MODELS_DIR.mkdir(exist_ok=True)

def extract_features(df):
    """
    Constructs segment-level feature matrix for machine learning models.
    Fuses pavement condition indicators, traffic loads, weather, and structural age.
    """
    current_year = 2026
    
    features = pd.DataFrame()
    features["pci"] = df["pci"]
    features["iri"] = df["iri"]
    features["crack_density_pct"] = df["crack_density_pct"]
    features["rut_depth_mm"] = df["rut_depth_mm"]
    features["pothole_count"] = df["pothole_count"]
    features["aadt"] = df["aadt"]
    features["heavy_vehicle_pct"] = df["heavy_vehicle_pct"]
    features["annual_rainfall_mm"] = df["annual_rainfall_mm"]
    features["freeze_thaw_cycles"] = df["freeze_thaw_cycles"]
    features["avg_temperature_c"] = df["avg_temperature_c"]
    features["length_km"] = df["length_km"]
    features["lanes"] = df["lanes"]
    
    features["structural_age"] = current_year - df["construction_year"]
    features["maint_age"] = current_year - df["last_major_maintenance_year"]
    
    # Interaction terms
    features["traffic_load_index"] = (df["aadt"] / 1000.0) * (1.0 + df["heavy_vehicle_pct"] / 50.0)
    features["weather_exposure_index"] = (df["freeze_thaw_cycles"] * 1.5) + (df["annual_rainfall_mm"] / 100.0)
    features["structural_distress_index"] = df["crack_density_pct"] * 0.6 + df["rut_depth_mm"] * 0.4
    
    return features

def train_and_save_models():
    """
    Trains Pothole Risk Classification model, Time-to-Failure Regression model,
    and Repair Cost Regression model, saving artifacts to ml/models/.
    """
    print("Fetching training dataset from SQLite database...")
    segments = get_all_segments()
    df = pd.DataFrame(segments)
    
    X = extract_features(df)
    
    # Target 1: Risk Level Classification (High=2, Medium=1, Low=0)
    # High risk defined by low PCI (<55), active potholes, or severe structural distress + heavy traffic
    risk_labels = []
    for idx, row in df.iterrows():
        pci = row["pci"]
        potholes = row["pothole_count"]
        if pci < 55 or potholes >= 3:
            risk_labels.append("High")
        elif pci < 72 or potholes >= 1:
            risk_labels.append("Medium")
        else:
            risk_labels.append("Low")
            
    y_risk = np.array(risk_labels)
    
    # Target 2: Time-to-Failure (Months until PCI drops below 40 failure limit)
    # Estimated decay rate per month based on traffic and weather
    monthly_decay = (X["traffic_load_index"] * 0.05 + X["weather_exposure_index"] * 0.04 + X["maint_age"] * 0.1) / (df["surface_type"].apply(lambda s: 1.3 if s == "Concrete" else 1.0))
    y_failure_months = np.maximum(1.0, (df["pci"] - 40.0) / (monthly_decay + 0.1) * 12.0)
    
    # Target 3: Estimated Reactive Patching/Reconstruction Cost in ₹ INR
    y_reactive_cost = df["length_km"] * (df["lanes"] / 2.0) * (
        np.where(df["pci"] < 48, 32000000, np.where(df["pci"] < 68, 7500000, 1800000)) + X["pothole_count"] * 120000
    )
    
    # Split data
    X_train, X_test, y_risk_tr, y_risk_te, y_fail_tr, y_fail_te, y_cost_tr, y_cost_te = train_test_split(
        X, y_risk, y_failure_months, y_reactive_cost, test_size=0.2, random_state=42
    )
    
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    
    print("\n--- 1. Training Pothole Risk Classification Model (Random Forest) ---")
    clf_risk = RandomForestClassifier(n_estimators=100, max_depth=8, random_state=42, class_weight="balanced")
    clf_risk.fit(X_train_scaled, y_risk_tr)
    risk_preds = clf_risk.predict(X_test_scaled)
    print(classification_report(y_risk_te, risk_preds))
    
    print("\n--- 2. Training Time-to-Failure Regressor ---")
    reg_fail = RandomForestRegressor(n_estimators=100, max_depth=8, random_state=42)
    reg_fail.fit(X_train_scaled, y_fail_tr)
    fail_preds = reg_fail.predict(X_test_scaled)
    print(f"Time-to-Failure MAE: {mean_absolute_error(y_fail_te, fail_preds):.2f} months")
    print(f"Time-to-Failure R² Score: {r2_score(y_fail_te, fail_preds):.3f}")
    
    print("\n--- 3. Training Reactive Repair Cost Regressor (INR) ---")
    reg_cost = RandomForestRegressor(n_estimators=100, max_depth=8, random_state=42)
    reg_cost.fit(X_train_scaled, y_cost_tr)
    cost_preds = reg_cost.predict(X_test_scaled)
    print(f"Repair Cost MAE: INR {mean_absolute_error(y_cost_te, cost_preds):,.2f}")
    print(f"Repair Cost R² Score: {r2_score(y_cost_te, cost_preds):.3f}")
    
    # Save artifacts
    print("\nSaving trained models and scaler to ml/models/...")
    joblib.dump(scaler, MODELS_DIR / "scaler.joblib")
    joblib.dump(clf_risk, MODELS_DIR / "risk_classifier.joblib")
    joblib.dump(reg_fail, MODELS_DIR / "decay_regressor.joblib")
    joblib.dump(reg_cost, MODELS_DIR / "cost_regressor.joblib")
    
    print("All models successfully trained and serialized!")

if __name__ == "__main__":
    train_and_save_models()
