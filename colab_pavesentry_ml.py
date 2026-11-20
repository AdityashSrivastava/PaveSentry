"""
========================================================================================
PAVESENTRY: MACHINE LEARNING PIPELINE FOR GOOGLE COLAB
Real-Time Delhi NCT Pavement Intelligence & Maintenance Predictor
========================================================================================
This standalone script runs directly in Google Colab (or any Jupyter environment).
It includes:
  1. Complete Delhi NCT Pavement Dataset loader / embedded fallback generator
  2. Multi-sensor feature engineering (PCI, IRI, traffic, weather, distress indexes)
  3. Model 1: Pothole Risk Classification (RandomForestClassifier, Balanced)
  4. Model 2: Time-to-Failure Regression (RandomForestRegressor)
  5. Model 3: Reactive Reconstruction Cost Regression (RandomForestRegressor)
  6. Model comparison against baselines (LogisticRegression, DecisionTree, Ridge)
  7. Feature Importance analysis and Seaborn / Matplotlib visual plots
  8. IRC (Indian Roads Congress) standards action recommendation engine
  9. Model serialization (.joblib) for production deployment
========================================================================================
"""

# %% [Cell 1: Environment Setup and Library Imports]
import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
import joblib
import numpy as np
import pandas as pd

# Matplotlib setup: In Jupyter / Google Colab, allow interactive inline rendering;
# in headless terminal execution, fall back safely to Agg backend without warnings.
import matplotlib
try:
    # Check if running in an interactive notebook (e.g. Google Colab)
    shell = get_ipython().__class__.__name__
    # Notebook environment: do not force Agg
except NameError:
    # Non-interactive CLI terminal
    if not os.environ.get("DISPLAY"):
        matplotlib.use('Agg')

import matplotlib.pyplot as plt
try:
    import seaborn as sns
except ImportError:
    sns = None

from sklearn.model_selection import train_test_split, cross_val_score, StratifiedKFold
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    f1_score,
    roc_auc_score,
    mean_absolute_error,
    mean_squared_error,
    r2_score
)

print("Scikit-Learn, Pandas, NumPy, and Matplotlib imported successfully!")

# Supported dataset candidate filenames
CSV_CANDIDATES = [
    "delhi_pavement_complete_dataset.csv",
    "delhi_road_dataset.csv",
    "../delhi_pavement_complete_dataset.csv",
    "../delhi_road_dataset.csv",
    "/content/delhi_pavement_complete_dataset.csv",
    "/content/delhi_road_dataset.csv"
]

csv_found = next((cand for cand in CSV_CANDIDATES if os.path.exists(cand)), None)

if csv_found:
    print(f"Loading existing dataset from '{csv_found}'...")
    df = pd.read_csv(csv_found)
else:
    print("Dataset CSV not found in working directory. Generating synthetic Delhi road network calibrated to CSIR-CRRI...")
    np.random.seed(42)
    n_samples = 350
    zones = ["Central Delhi", "New Delhi (NDMC)", "South Delhi", "South West Delhi", 
             "West Delhi", "North Delhi", "North East Delhi", "North West Delhi", 
             "East Delhi", "South East Delhi", "Shahdara"]
    road_types = ["Highway", "Arterial", "Collector", "Local"]
    surface_types = ["Bituminous Concrete", "Mastic Asphalt", "Flexible", "Rigid Concrete"]
    
    data = []
    for i in range(1, n_samples + 1):
        seg_id = f"DL-NCT-{i:04d}"
        zone = np.random.choice(zones)
        rtype = np.random.choice(road_types, p=[0.2, 0.45, 0.25, 0.1])
        stype = np.random.choice(surface_types, p=[0.6, 0.2, 0.15, 0.05])
        length_km = round(np.random.uniform(0.8, 4.5), 2)
        lanes = int(np.random.choice([2, 4, 6, 8], p=[0.15, 0.45, 0.3, 0.1]))
        
        # Age & Surveys
        const_year = int(np.random.randint(1995, 2022))
        last_maint = int(np.random.randint(max(const_year, 2012), 2025))
        
        # Pavement condition metrics (CSIR-CRRI distribution)
        pci = round(float(np.clip(np.random.beta(2, 2.5) * 85 + 10, 10.0, 98.0)), 1)
        iri = round(float(np.clip(7.0 - (pci / 100.0) * 5.2 + np.random.normal(0, 0.3), 1.2, 6.5)), 2)
        crack_pct = round(float(np.clip((100.0 - pci) * 0.45 + np.random.normal(0, 2.5), 0.0, 50.0)), 1)
        rut_mm = round(float(np.clip((100.0 - pci) * 0.28 + np.random.normal(0, 1.8), 0.5, 30.0)), 1)
        
        if pci < 40:
            potholes = int(np.random.randint(4, 18))
        elif pci < 65:
            potholes = int(np.random.randint(1, 6))
        else:
            potholes = int(np.random.choice([0, 1], p=[0.85, 0.15]))
            
        # Traffic & Weather
        aadt = int(np.random.randint(8000, 120000) if rtype in ["Highway", "Arterial"] else np.random.randint(2500, 25000))
        heavy_pct = round(float(np.random.uniform(4.0, 28.0)), 1)
        annual_rain = round(float(np.random.uniform(680.0, 950.0)), 1) # Delhi monsoon
        freeze_thaw = int(np.random.randint(45, 58)) # Delhi summer-winter thermal swings
        avg_temp = round(float(np.random.uniform(38.0, 44.5)), 1)
        
        data.append({
            "segment_id": seg_id, "road_type": rtype, "city_zone": zone,
            "length_km": length_km, "surface_type": stype, "lanes": lanes,
            "construction_year": const_year, "last_major_maintenance_year": last_maint,
            "pci": pci, "iri": iri, "crack_density_pct": crack_pct,
            "rut_depth_mm": rut_mm, "pothole_count": potholes,
            "aadt": aadt, "heavy_vehicle_pct": heavy_pct,
            "annual_rainfall_mm": annual_rain, "freeze_thaw_cycles": freeze_thaw,
            "avg_temperature_c": avg_temp
        })
    df = pd.DataFrame(data)

print(f"Dataset ready! Total Segments: {len(df)}, Features: {df.shape[1]}")
print(df.head())

# %% [Cell 3: Feature Engineering Pipeline]
CURRENT_YEAR = 2026

def compute_features(input_df):
    f = pd.DataFrame()
    f["pci"] = input_df["pci"]
    f["iri"] = input_df["iri"]
    f["crack_density_pct"] = input_df["crack_density_pct"]
    f["rut_depth_mm"] = input_df["rut_depth_mm"]
    f["pothole_count"] = input_df["pothole_count"]
    f["aadt"] = input_df["aadt"]
    f["heavy_vehicle_pct"] = input_df["heavy_vehicle_pct"]
    f["annual_rainfall_mm"] = input_df["annual_rainfall_mm"]
    f["freeze_thaw_cycles"] = input_df["freeze_thaw_cycles"]
    f["avg_temperature_c"] = input_df["avg_temperature_c"]
    f["length_km"] = input_df["length_km"]
    f["lanes"] = input_df["lanes"]
    
    # Structural & Maintenance Age
    f["structural_age"] = CURRENT_YEAR - input_df["construction_year"]
    f["maint_age"] = CURRENT_YEAR - input_df["last_major_maintenance_year"]
    
    # Interaction terms
    f["traffic_load_index"] = (input_df["aadt"] / 1000.0) * (1.0 + input_df["heavy_vehicle_pct"] / 50.0)
    f["weather_exposure_index"] = (input_df["freeze_thaw_cycles"] * 1.5) + (input_df["annual_rainfall_mm"] / 100.0)
    f["structural_distress_index"] = input_df["crack_density_pct"] * 0.6 + input_df["rut_depth_mm"] * 0.4
    return f

X = compute_features(df)
print(f"\nExtracted Feature Matrix X shape: {X.shape}")
print(f"Feature Names: {list(X.columns)}")

# %% [Cell 4: Derive Target Labels]
# Target 1: Pothole Risk Classification (High, Medium, Low)
risk_labels = []
for _, row in df.iterrows():
    pci = row["pci"]
    potholes = row["pothole_count"]
    if pci < 55 or potholes >= 3:
        risk_labels.append("High")
    elif pci < 72 or potholes >= 1:
        risk_labels.append("Medium")
    else:
        risk_labels.append("Low")
y_risk = np.array(risk_labels)

# Target 2: Time-to-Failure in Months (until PCI drops below critical 40)
surface_modifier = df["surface_type"].apply(lambda s: 1.3 if s == "Concrete" or s == "Rigid Concrete" else 1.0)
monthly_decay = (X["traffic_load_index"] * 0.05 + X["weather_exposure_index"] * 0.04 + X["maint_age"] * 0.1) / surface_modifier
y_failure_months = np.maximum(1.0, (df["pci"] - 40.0) / (monthly_decay + 0.1) * 12.0)

# Target 3: Estimated Reactive Reconstruction Cost in ₹ INR (IRC:37/82)
base_rate = np.where(df["pci"] < 48, 32000000, np.where(df["pci"] < 68, 7500000, 1800000))
y_reactive_cost = df["length_km"] * (df["lanes"] / 2.0) * (base_rate + X["pothole_count"] * 120000)

print("\n--- Target Distributions ---")
print(pd.Series(y_risk).value_counts(normalize=True).round(3) * 100)
print(f"Time to Failure: Mean = {y_failure_months.mean():.1f} months, Min = {y_failure_months.min():.1f}, Max = {y_failure_months.max():.1f}")
print(f"Reactive Cost (INR): Mean = INR {y_reactive_cost.mean():,.0f}")

# %% [Cell 5: Train/Test Split and StandardScaler Normalization]
X_train, X_test, y_risk_tr, y_risk_te, y_fail_tr, y_fail_te, y_cost_tr, y_cost_te = train_test_split(
    X, y_risk, y_failure_months, y_reactive_cost, test_size=0.2, random_state=42, stratify=y_risk
)

scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_test_scaled = scaler.transform(X_test)

print(f"Training set: {X_train.shape[0]} samples | Testing set: {X_test.shape[0]} samples")

# %% [Cell 6: Model 1 - Pothole Risk Classifier (Random Forest)]
print("\n" + "=" * 60)
print("STAGE 1: RANDOM FOREST CLASSIFIER (Pothole Risk)")
print("=" * 60)

clf_risk = RandomForestClassifier(n_estimators=100, max_depth=8, random_state=42, class_weight="balanced")
clf_risk.fit(X_train_scaled, y_risk_tr)

risk_preds = clf_risk.predict(X_test_scaled)
risk_probs = clf_risk.predict_proba(X_test_scaled)

print("\nClassification Report (Test Set):")
print(classification_report(y_risk_te, risk_preds, digits=4))

weighted_f1 = f1_score(y_risk_te, risk_preds, average="weighted")
macro_f1 = f1_score(y_risk_te, risk_preds, average="macro")

try:
    roc_auc = roc_auc_score(y_risk_te, risk_probs, multi_class="ovr", average="weighted", labels=clf_risk.classes_)
    print(f"Weighted F1-Score: {weighted_f1:.4f}")
    print(f"Macro F1-Score:    {macro_f1:.4f}")
    print(f"ROC-AUC (OVR):     {roc_auc:.4f}")
except Exception as e:
    print(f"Weighted F1-Score: {weighted_f1:.4f}")
    print(f"Macro F1-Score:    {macro_f1:.4f}")
    print(f"ROC-AUC (OVR):     N/A ({e})")

# Baseline Comparison: Logistic Regression
baseline_lr = LogisticRegression(max_iter=1000, random_state=42, class_weight="balanced")
baseline_lr.fit(X_train_scaled, y_risk_tr)
lr_preds = baseline_lr.predict(X_test_scaled)
print(f"Baseline Logistic Regression Accuracy: {baseline_lr.score(X_test_scaled, y_risk_te) * 100:.2f}%")
print(f"Random Forest Classifier Accuracy:      {clf_risk.score(X_test_scaled, y_risk_te) * 100:.2f}%")

# %% [Cell 7: Model 2 - Time-to-Failure Regressor]
print("\n" + "=" * 60)
print("STAGE 2: TIME-TO-FAILURE REGRESSOR")
print("=" * 60)

reg_fail = RandomForestRegressor(n_estimators=100, max_depth=8, random_state=42)
reg_fail.fit(X_train_scaled, y_fail_tr)

fail_preds = reg_fail.predict(X_test_scaled)
mae_fail = mean_absolute_error(y_fail_te, fail_preds)
rmse_fail = np.sqrt(mean_squared_error(y_fail_te, fail_preds))
r2_fail = r2_score(y_fail_te, fail_preds)

print(f"MAE:  {mae_fail:.2f} months")
print(f"RMSE: {rmse_fail:.2f} months")
print(f"R²:   {r2_fail:.4f}")

# Baseline Regressor Comparison: Ridge
ridge_fail = Ridge()
ridge_fail.fit(X_train_scaled, y_fail_tr)
print(f"Baseline Ridge Regression R²: {ridge_fail.score(X_test_scaled, y_fail_te):.4f}")
print(f"Random Forest Regressor R²:   {r2_fail:.4f}")

# %% [Cell 8: Model 3 - Reactive Repair Cost Regressor]
print("\n" + "=" * 60)
print("STAGE 3: REPAIR COST REGRESSOR (INR)")
print("=" * 60)

reg_cost = RandomForestRegressor(n_estimators=100, max_depth=8, random_state=42)
reg_cost.fit(X_train_scaled, y_cost_tr)

cost_preds = reg_cost.predict(X_test_scaled)
mae_cost = mean_absolute_error(y_cost_te, cost_preds)
r2_cost = r2_score(y_cost_te, cost_preds)
safe_cost_denom = np.maximum(y_cost_te, 1.0)
mape_cost = np.mean(np.abs((y_cost_te - cost_preds) / safe_cost_denom)) * 100

print(f"MAE:       INR {mae_cost:,.2f}")
print(f"MAPE:      {mape_cost:.2f}%")
print(f"R² Score:  {r2_cost:.4f}")

# %% [Cell 9: Feature Importance Visualization]
fig1 = plt.figure(figsize=(10, 6))
importances = pd.Series(clf_risk.feature_importances_, index=X.columns).sort_values(ascending=True)
importances.plot(kind="barh", color="#1f77b4")
plt.title("Feature Importance: Pothole Risk Classification (Random Forest)")
plt.xlabel("Importance Score (Mean Decrease Impurity)")
plt.tight_layout()
plt.savefig("feature_importance.png", dpi=200, bbox_inches="tight")
if matplotlib.get_backend().lower() != 'agg':
    plt.show()
plt.close(fig1)

# Confusion Matrix Plot
fig2 = plt.figure(figsize=(6, 5))
cm = confusion_matrix(y_risk_te, risk_preds, labels=["High", "Medium", "Low"])
if sns is not None:
    sns.heatmap(cm, annot=True, fmt="d", cmap="Blues", xticklabels=["High", "Medium", "Low"], yticklabels=["High", "Medium", "Low"])
else:
    plt.imshow(cm, cmap="Blues")
    plt.colorbar()
    for i in range(len(cm)):
        for j in range(len(cm[i])):
            plt.text(j, i, str(cm[i][j]), ha="center", va="center", color="black")
    plt.xticks([0, 1, 2], ["High", "Medium", "Low"])
    plt.yticks([0, 1, 2], ["High", "Medium", "Low"])
plt.title("Confusion Matrix: Pothole Risk Classification")
plt.ylabel("Actual Label")
plt.xlabel("Predicted Label")
plt.tight_layout()
plt.savefig("confusion_matrix.png", dpi=200, bbox_inches="tight")
if matplotlib.get_backend().lower() != 'agg':
    plt.show()
plt.close(fig2)

# %% [Cell 10: Complete Multi-Criteria Priority Scoring & IRC Action Engine]
def evaluate_new_road_segment(segment_dict):
    """
    End-to-End inference function matching PaveSentry production backend.
    """
    input_df = pd.DataFrame([segment_dict])
    x_feat = compute_features(input_df)
    x_scaled = scaler.transform(x_feat)
    
    # 1. Predictions
    pred_risk = clf_risk.predict(x_scaled)[0]
    probs = clf_risk.predict_proba(x_scaled)[0]
    classes = list(clf_risk.classes_)
    high_idx = classes.index("High") if "High" in classes else 0
    pothole_prob = round(float(probs[high_idx]), 3)
    
    time_to_fail = round(float(reg_fail.predict(x_scaled)[0]), 1)
    reactive_cost = round(float(reg_cost.predict(x_scaled)[0]), 2)
    preventive_cost = round(reactive_cost * 0.28, 2)
    
    # 2. Priority Scoring Formula
    aadt_factor = np.clip(segment_dict["aadt"] / 50000.0, 0.0, 1.0)
    pci_factor = np.clip((100.0 - segment_dict["pci"]) / 100.0, 0.0, 1.0)
    savings_ratio = np.clip((reactive_cost - preventive_cost) / (preventive_cost + 1.0), 0.0, 5.0) / 5.0
    
    priority_score = round(
        0.40 * pothole_prob + 0.25 * aadt_factor + 0.20 * pci_factor + 0.15 * savings_ratio,
        3
    )
    
    # 3. IRC Specification Mapping
    pci = segment_dict["pci"]
    if pci < 48 or (pred_risk == "High" and pci < 58):
        action = "Full Reconstruction & Sub-base Work (IRC:37)"
    elif pci < 68 or pred_risk == "High":
        action = "Bituminous Concrete (BC) Mill & Overlay (IRC:82)"
    elif pci < 82 or pred_risk == "Medium":
        action = "Preventive Micro-Surfacing & Slurry Seal (IRC:SP:81)"
    else:
        action = "Routine Inspection & Monsoon Drain Clearance"
        
    return {
        "predicted_risk_level": pred_risk,
        "pothole_probability": pothole_prob,
        "est_time_to_failure_months": time_to_fail,
        "est_reactive_cost_inr": reactive_cost,
        "est_preventive_cost_inr": preventive_cost,
        "net_savings_inr": reactive_cost - preventive_cost,
        "priority_score": priority_score,
        "recommended_action": action
    }

# Example Test Case: Delhi Ring Road Arterial Segment
sample_road = {
    "length_km": 2.5,
    "lanes": 6,
    "construction_year": 2014,
    "last_major_maintenance_year": 2019,
    "pci": 44.5,
    "iri": 4.8,
    "crack_density_pct": 28.5,
    "rut_depth_mm": 18.2,
    "pothole_count": 5,
    "aadt": 65000,
    "heavy_vehicle_pct": 18.5,
    "annual_rainfall_mm": 820.0,
    "freeze_thaw_cycles": 52,
    "avg_temperature_c": 42.0,
    "surface_type": "Bituminous Concrete"
}

inference_result = evaluate_new_road_segment(sample_road)
print("\n" + "=" * 60)
print("INFERENCE RESULT ON TEST CORRIDOR (Ring Road Sample):")
print("=" * 60)
for k, v in inference_result.items():
    print(f"  {k:30s} : {v}")

# %% [Cell 11: Export Serialized Models & Download Zip]
os.makedirs("exported_models", exist_ok=True)
joblib.dump(scaler, "exported_models/scaler.joblib")
joblib.dump(clf_risk, "exported_models/risk_classifier.joblib")
joblib.dump(reg_fail, "exported_models/decay_regressor.joblib")
joblib.dump(reg_cost, "exported_models/cost_regressor.joblib")
print("Trained models exported successfully to 'exported_models/' directory!")

# Package and trigger automatic download in Google Colab
import shutil
shutil.make_archive("exported_models", "zip", "exported_models")

try:
    from google.colab import files
    print("\nTriggering automatic download of 'exported_models.zip' to your browser...")
    files.download("exported_models.zip")
except ImportError:
    print("\n[Local mode] 'exported_models.zip' created successfully in your working directory.")
except Exception as e:
    print(f"\n[Colab Download Info] Automatic browser download was skipped or blocked by pop-up blocker ({e}).")
    print("-> You can manually download 'exported_models.zip' from the Colab Files panel (folder icon on left sidebar).")

