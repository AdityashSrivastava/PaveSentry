"""
Explainable AI (XAI) & Feature Attribution Engine.
Uses TreeSHAP (SHapley Additive exPlanations) to explain Machine Learning risk predictions.
Conforms to CSIR-CRRI, Delhi PWD & Central Vigilance Commission (CVC) Audit Transparency Standards.
"""
from typing import Dict, Any, List, Optional
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import shap

from database.db_manager import get_all_segments, get_segment_by_id
from ml.train_models import extract_features, MODELS_DIR

# Feature Metadata & Engineering Descriptions
FEATURE_METADATA = {
    "traffic_load_index": {
        "display_name": "Heavy Traffic Load Index",
        "category": "Traffic & Axle Loading",
        "unit": "Index",
        "rationale_high": "Excessive commercial axle loading (multi-axle trucks) compounding cumulative pavement fatigue under IRC:37.",
        "rationale_low": "Low commercial truck traffic providing structural fatigue relief."
    },
    "heavy_vehicle_pct": {
        "display_name": "Commercial Heavy Vehicle %",
        "category": "Traffic & Axle Loading",
        "unit": "%",
        "rationale_high": "High proportion of commercial freight trucks accelerating sub-base shear strain.",
        "rationale_low": "Predominantly light vehicular traffic resulting in minimal structural damage."
    },
    "aadt": {
        "display_name": "Annual Average Daily Traffic (AADT)",
        "category": "Traffic & Axle Loading",
        "unit": "PCU/day",
        "rationale_high": "Extremely high daily vehicle volume generating continuous cyclic surface fatigue.",
        "rationale_low": "Moderate daily traffic volume within design capacity."
    },
    "annual_rainfall_mm": {
        "display_name": "Monsoon Rainfall Exposure",
        "category": "Environmental & Drainage",
        "unit": "mm/year",
        "rationale_high": "Intense monsoon rainfall inducing subgrade saturation, moisture stripping, and base softening.",
        "rationale_low": "Moderate moisture exposure with adequate drainage preservation."
    },
    "weather_exposure_index": {
        "display_name": "Monsoon & Thermal Stress Index",
        "category": "Environmental & Drainage",
        "unit": "Index",
        "rationale_high": "Combined peak summer heat (46°C) and monsoon ponding causing bitumen stripping and oxidation.",
        "rationale_low": "Stable environmental exposure without severe moisture trapping."
    },
    "freeze_thaw_cycles": {
        "display_name": "Thermal Expansion Cycles",
        "category": "Environmental & Drainage",
        "unit": "Cycles",
        "rationale_high": "Severe seasonal temperature swings between winter nights (4°C) and summer days (46°C).",
        "rationale_low": "Low thermal cycling stress."
    },
    "avg_temperature_c": {
        "display_name": "Peak Summer Temperature",
        "category": "Environmental & Drainage",
        "unit": "°C",
        "rationale_high": "Extreme pavement surface temperatures causing binder softening and rutting susceptibility.",
        "rationale_low": "Moderate operational temperature."
    },
    "pci": {
        "display_name": "Pavement Condition Index (PCI)",
        "category": "Current Condition",
        "unit": "/100",
        "rationale_high": "Severely depressed PCI reflecting established fatigue cracking and raveling.",
        "rationale_low": "High PCI indicating intact structural surface with strong ride quality."
    },
    "iri": {
        "display_name": "International Roughness Index (IRI)",
        "category": "Current Condition",
        "unit": "m/km",
        "rationale_high": "High road roughness causing increased dynamic axle bounce and vehicle impact forces.",
        "rationale_low": "Smooth riding surface with low dynamic impact load."
    },
    "pothole_count": {
        "display_name": "Active Potholes Count",
        "category": "Current Condition",
        "unit": "Potholes",
        "rationale_high": "Multiple open pothole craters directly exposing the granular sub-base to water ingress.",
        "rationale_low": "Zero active potholes preventing immediate moisture penetration."
    },
    "crack_density_pct": {
        "display_name": "Alligator & Linear Crack Density",
        "category": "Structural Distress",
        "unit": "%",
        "rationale_high": "Extensive crack network facilitating deep rainwater seepage into pavement layers.",
        "rationale_low": "Minimal surface cracking maintaining impermeable seal."
    },
    "rut_depth_mm": {
        "display_name": "Wheelpath Rut Depth",
        "category": "Structural Distress",
        "unit": "mm",
        "rationale_high": "Permanent subgrade deformation causing water accumulation in wheel paths.",
        "rationale_low": "Negligible rutting preserving transverse camber drainage."
    },
    "structural_distress_index": {
        "display_name": "Composite Structural Distress",
        "category": "Structural Distress",
        "unit": "Index",
        "rationale_high": "Combined cracking and rutting indicating late-stage structural fatigue breakdown.",
        "rationale_low": "Sound structural matrix without widespread distress."
    },
    "maint_age": {
        "display_name": "Years Since Major Maintenance",
        "category": "Pavement Age & History",
        "unit": "Years",
        "rationale_high": "Oxidative age embrittlement of bitumen binder over extended unmaintained service life.",
        "rationale_low": "Recent resurfacing providing ductile, crack-resistant wearing course."
    },
    "structural_age": {
        "display_name": "Total Pavement Structural Age",
        "category": "Pavement Age & History",
        "unit": "Years",
        "rationale_high": "Pavement has exceeded its design fatigue life under IRC:37.",
        "rationale_low": "Relatively new pavement structure with substantial fatigue reserve."
    },
    "length_km": {
        "display_name": "Corridor Section Length",
        "category": "Geometry & Layout",
        "unit": "km",
        "rationale_high": "Longer corridor stretch multiplying cumulative exposure area.",
        "rationale_low": "Short section allowing focused maintenance."
    },
    "lanes": {
        "display_name": "Number of Lanes",
        "category": "Geometry & Layout",
        "unit": "Lanes",
        "rationale_high": "High lane count multiplying maintenance square meterage.",
        "rationale_low": "Standard road section width."
    }
}

class ExplainableAIEngine:
    """Singleton TreeSHAP inference engine for PaveSentry ML models."""
    _instance = None

    def __init__(self):
        self.scaler = joblib.load(MODELS_DIR / "scaler.joblib")
        self.clf_risk = joblib.load(MODELS_DIR / "risk_classifier.joblib")
        self.reg_decay = joblib.load(MODELS_DIR / "decay_regressor.joblib")
        self.reg_cost = joblib.load(MODELS_DIR / "cost_regressor.joblib")
        
        self.explainer = shap.TreeExplainer(self.clf_risk)
        self.classes = list(self.clf_risk.classes_)
        self.high_risk_idx = self.classes.index("High") if "High" in self.classes else 0

        # Background reference cache
        self._global_shap_cache = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = ExplainableAIEngine()
        return cls._instance

    def explain_corridor(self, segment_id: str) -> Dict[str, Any]:
        """
        Computes local SHAP waterfall attribution for a specific corridor.
        Returns percentage influences, directional drivers, and human engineering justification.
        """
        segment = get_segment_by_id(segment_id)
        if not segment:
            raise ValueError(f"Corridor '{segment_id}' not found.")

        df = pd.DataFrame([segment])
        X = extract_features(df)
        feature_names = list(X.columns)
        X_scaled = self.scaler.transform(X)

        # Predict probability
        probs = self.clf_risk.predict_proba(X_scaled)[0]
        pothole_prob = float(probs[self.high_risk_idx])
        predicted_risk = str(self.clf_risk.predict(X_scaled)[0])

        # Compute SHAP values
        raw_shap = self.explainer.shap_values(X_scaled)
        
        # Handle binary or multiclass SHAP output format
        if isinstance(raw_shap, list):
            sample_shap = raw_shap[self.high_risk_idx][0]
            base_val = float(self.explainer.expected_value[self.high_risk_idx])
        elif len(np.array(raw_shap).shape) == 3:
            sample_shap = raw_shap[0, :, self.high_risk_idx]
            base_val = float(self.explainer.expected_value[self.high_risk_idx])
        else:
            sample_shap = raw_shap[0]
            base_val = float(self.explainer.expected_value)

        # Normalize relative influence percentages
        abs_sum = float(np.sum(np.abs(sample_shap))) + 1e-6

        waterfall_items = []
        for feat_name, shap_val in zip(feature_names, sample_shap):
            val = float(X[feat_name].iloc[0])
            s_val = float(shap_val)
            pct = round((abs(s_val) / abs_sum) * 100.0, 1)

            meta = FEATURE_METADATA.get(feat_name, {
                "display_name": feat_name.replace("_", " ").title(),
                "category": "General",
                "unit": "",
                "rationale_high": "Increases probability of failure.",
                "rationale_low": "Reduces probability of failure."
            })

            direction = "Increases Risk" if s_val > 0 else "Reduces Risk"
            rationale = meta["rationale_high"] if s_val > 0 else meta["rationale_low"]

            waterfall_items.append({
                "feature_name": feat_name,
                "display_name": meta["display_name"],
                "category": meta["category"],
                "raw_value": round(val, 2),
                "unit": meta["unit"],
                "shap_value": round(s_val, 4),
                "influence_pct": pct,
                "direction": direction,
                "is_risk_driver": s_val > 0,
                "engineering_rationale": rationale
            })

        # Sort items: highest positive risk drivers first, then strongest mitigating factors
        risk_drivers = sorted([i for i in waterfall_items if i["shap_value"] > 0], key=lambda x: x["shap_value"], reverse=True)
        mitigating_factors = sorted([i for i in waterfall_items if i["shap_value"] <= 0], key=lambda x: x["shap_value"])

        # Construct official audit justification narrative
        top_drivers_text = ", ".join([f"{d['display_name']} ({d['raw_value']} {d['unit']}, +{d['influence_pct']}%)" for d in risk_drivers[:3]])
        
        audit_justification = (
            f"CSIR-CRRI DEFENSIVE AUDIT JUSTIFICATION: Corridor '{segment.get('name')}' ({segment.get('city_zone')}) "
            f"was flagged as {predicted_risk.upper()} RISK (Pothole Probability: {pothole_prob:.1%}) by the machine learning engine. "
            f"Local TreeSHAP attribution demonstrates that this classification is {round(sum(d['influence_pct'] for d in risk_drivers[:3]))}% driven by "
            f"{top_drivers_text}. {risk_drivers[0]['engineering_rationale'] if risk_drivers else ''} "
            f"Prioritizing this corridor is mathematically defensible before municipal vigilance audits (IRC:37:2018 / CVC guidelines)."
        )

        return {
            "segment_id": segment_id,
            "road_name": segment.get("name"),
            "city_zone": segment.get("city_zone"),
            "predicted_risk": predicted_risk,
            "pothole_probability": pothole_prob,
            "base_expected_value": round(base_val, 4),
            "total_features_analyzed": len(waterfall_items),
            "waterfall_attribution": waterfall_items,
            "top_risk_drivers": risk_drivers[:5],
            "top_mitigating_factors": mitigating_factors[:3],
            "audit_justification": audit_justification
        }

    def get_global_feature_importance(self) -> Dict[str, Any]:
        """
        Computes network-wide global feature importance using mean absolute SHAP values.
        Identifies the primary macro drivers of pavement failure across all Delhi corridors.
        """
        if self._global_shap_cache is not None:
            return self._global_shap_cache

        segments = get_all_segments()
        if not segments:
            return {"status": "error", "message": "No segments in database"}

        df = pd.DataFrame(segments)
        X = extract_features(df)
        X_scaled = self.scaler.transform(X)

        raw_shap = self.explainer.shap_values(X_scaled)
        if isinstance(raw_shap, list):
            high_shap = raw_shap[self.high_risk_idx]
        elif len(np.array(raw_shap).shape) == 3:
            high_shap = raw_shap[:, :, self.high_risk_idx]
        else:
            high_shap = raw_shap

        mean_abs_shap = np.mean(np.abs(high_shap), axis=0)
        total_mag = float(np.sum(mean_abs_shap)) + 1e-6

        ranked_features = []
        for feat_name, mag in zip(X.columns, mean_abs_shap):
            pct = round((float(mag) / total_mag) * 100.0, 1)
            meta = FEATURE_METADATA.get(feat_name, {
                "display_name": feat_name.replace("_", " ").title(),
                "category": "General",
                "unit": ""
            })
            ranked_features.append({
                "feature_name": feat_name,
                "display_name": meta["display_name"],
                "category": meta["category"],
                "mean_shap": round(float(mag), 4),
                "global_importance_pct": pct
            })

        ranked_features.sort(key=lambda x: x["mean_shap"], reverse=True)

        res = {
            "status": "success",
            "total_corridors_analyzed": len(df),
            "ranked_global_features": ranked_features,
            "top_macro_driver": ranked_features[0]["display_name"],
            "top_macro_driver_pct": ranked_features[0]["global_importance_pct"]
        }
        self._global_shap_cache = res
        return res

    def simulate_counterfactual(
        self,
        segment_id: str,
        overrides: Dict[str, float]
    ) -> Dict[str, Any]:
        """
        Simulates hypothetical engineering interventions (e.g. diverting 50% heavy traffic,
        installing monsoon drain sumps, or sealing cracks) and measures the resulting drop in risk.
        """
        segment = get_segment_by_id(segment_id)
        if not segment:
            raise ValueError(f"Corridor '{segment_id}' not found.")

        # Baseline explanation
        baseline = self.explain_corridor(segment_id)

        # Apply counterfactual modifications
        cf_segment = dict(segment)
        for k, v in overrides.items():
            if k in cf_segment:
                cf_segment[k] = float(v)

        df_cf = pd.DataFrame([cf_segment])
        X_cf = extract_features(df_cf)
        X_cf_scaled = self.scaler.transform(X_cf)

        # Predict new outcome
        cf_probs = self.clf_risk.predict_proba(X_cf_scaled)[0]
        cf_pothole_prob = float(cf_probs[self.high_risk_idx])
        cf_risk_level = str(self.clf_risk.predict(X_cf_scaled)[0])

        prob_drop = round(baseline["pothole_probability"] - cf_pothole_prob, 3)
        pct_improvement = round((prob_drop / max(0.01, baseline["pothole_probability"])) * 100.0, 1)

        verdict = (
            f"Simulated engineering interventions reduce failure risk by {pct_improvement}% "
            f"(Pothole probability drops from {baseline['pothole_probability']:.1%} to {cf_pothole_prob:.1%}, "
            f"shifting predicted status from {baseline['predicted_risk']} to {cf_risk_level})."
        )

        return {
            "segment_id": segment_id,
            "road_name": segment.get("name"),
            "applied_overrides": overrides,
            "baseline_risk": baseline["predicted_risk"],
            "baseline_probability": baseline["pothole_probability"],
            "counterfactual_risk": cf_risk_level,
            "counterfactual_probability": cf_pothole_prob,
            "probability_reduction": prob_drop,
            "percentage_risk_drop": max(0.0, pct_improvement),
            "verdict": verdict
        }


def explain_corridor_risk(segment_id: str) -> Dict[str, Any]:
    return ExplainableAIEngine.get_instance().explain_corridor(segment_id)

def get_global_shap_importance() -> Dict[str, Any]:
    return ExplainableAIEngine.get_instance().get_global_feature_importance()

def simulate_intervention_counterfactual(segment_id: str, overrides: Dict[str, float]) -> Dict[str, Any]:
    return ExplainableAIEngine.get_instance().simulate_counterfactual(segment_id, overrides)
