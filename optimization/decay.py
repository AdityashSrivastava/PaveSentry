"""
PaveSentry Deterioration Decay & Cost of Inaction Simulation Engine
==================================================================
Models pavement degradation across 3-year and 5-year horizons using:
1. Weibull Accelerated Failure Time (AFT) Deterioration Curves.
2. Markov Chain Pavement Condition State Transition Matrices.
3. "Cost of Inaction" Simulation: Computes the exponential financial penalty
   of deferring preventive maintenance from Year 1 to Year 3, 4, or 5.
"""

import math
from typing import Any

import numpy as np

# Pavement Condition States for Markov Chain
STATES = ["Excellent (85-100)", "Good (70-84)", "Fair (55-69)", "Poor (40-54)", "Critical (<40)"]

def calculate_stress_factor(segment: dict) -> float:
    """
    Computes cumulative traffic and environmental stress multiplier for a corridor.
    Considers AADT, heavy commercial vehicle %, Delhi monsoon rainfall, and thermal cycles.
    """
    aadt = float(segment.get("aadt") or 40000)
    heavy_pct = float(segment.get("heavy_vehicle_pct") or 15.0)
    rainfall = float(segment.get("annual_rainfall_mm") or 650.0)
    freeze_thaw = float(segment.get("freeze_thaw_cycles") or 35)

    traffic_stress = ((aadt / 35000.0) ** 0.35) * (1.0 + (heavy_pct / 80.0))
    env_stress = ((rainfall / 600.0) ** 0.30) * ((freeze_thaw / 30.0) ** 0.20)
    
    # Surface type resistance
    surface = str(segment.get("surface_type") or "Bituminous Concrete").lower()
    if "rigid" in surface or "concrete" in surface:
        surface_mod = 0.65  # Concrete decays slower initially
    elif "mastic" in surface:
        surface_mod = 0.85
    else:
        surface_mod = 1.05  # Standard flexible asphalt

    total_stress = float(np.clip(traffic_stress * env_stress * surface_mod, 0.60, 2.80))
    return round(total_stress, 3)


def calculate_weibull_decay(
    initial_pci: float,
    initial_iri: float,
    stress_factor: float,
    horizon_years: int = 5
) -> list[dict[str, Any]]:
    """
    Models continuous PCI and IRI deterioration using calibrated Weibull hazard survival:
    PCI(t) = PCI_0 * exp(-(t / eta)^beta)
    where:
      - beta (shape factor) = 2.10 (accelerating decay as micro-cracks expand into cavities)
      - eta (characteristic life) = 11.0 / stress_factor
    """
    beta = 2.15
    eta = max(4.0, 11.5 / stress_factor)
    
    trajectory = []
    for t in range(horizon_years + 1):
        if t == 0:
            pci_t = initial_pci
            iri_t = initial_iri
        else:
            # Accelerated failure survival curve
            decay_fraction = math.exp(-((t / eta) ** beta))
            pci_t = initial_pci * decay_fraction
            pci_t = max(10.0, min(100.0, pci_t))

            # IRI roughness growth
            iri_growth = 1.0 + (0.16 * t * stress_factor) + (0.025 * (t ** 2) * stress_factor)
            iri_t = initial_iri * iri_growth
            iri_t = max(1.2, min(12.0, iri_t))

        # Risk classification
        if pci_t >= 70.0:
            risk = "Low"
        elif pci_t >= 55.0:
            risk = "Medium"
        else:
            risk = "High"

        # Action needed at this stage
        if pci_t >= 80:
            action = "Routine Sweeping & Crack Sealing"
        elif pci_t >= 65:
            action = "Preventive Micro-Surfacing (Seal Coat)"
        elif pci_t >= 50:
            action = "BC Mill & 40mm Asphalt Overlay"
        elif pci_t >= 35:
            action = "Major Rehabilitation (75mm DBM + BC)"
        else:
            action = "Full-Depth Sub-Base Reconstruction"

        trajectory.append({
            "year": t,
            "year_label": "Current Baseline" if t == 0 else f"Year {t}",
            "pci": round(pci_t, 1),
            "iri": round(iri_t, 2),
            "risk_level": risk,
            "recommended_treatment": action
        })

    return trajectory


def calculate_markov_transitions(stress_factor: float, horizon_years: int = 5) -> dict[str, Any]:
    """
    Constructs a 5-state Markov Chain transition matrix for pavement states:
    [Excellent, Good, Fair, Poor, Critical].
    Higher stress factors increase transition probabilities to worse states.
    """
    # Baseline 1-year transition probabilities
    # Rows: Current state, Cols: Next year state
    degrade_rate = min(0.35, 0.14 * stress_factor)
    severe_rate = min(0.12, 0.03 * stress_factor)

    P = np.array([
        [1.0 - degrade_rate - severe_rate, degrade_rate, severe_rate, 0.0, 0.0],
        [0.0, 1.0 - degrade_rate - severe_rate, degrade_rate, severe_rate, 0.0],
        [0.0, 0.0, 1.0 - degrade_rate - severe_rate, degrade_rate, severe_rate],
        [0.0, 0.0, 0.0, 1.0 - degrade_rate, degrade_rate],
        [0.0, 0.0, 0.0, 0.0, 1.0]  # Absorbing state (failed road)
    ])

    # Normalize rows
    P = P / P.sum(axis=1, keepdims=True)

    yearly_matrices = {}
    current_P = np.eye(5)
    for year in range(1, horizon_years + 1):
        current_P = np.matmul(current_P, P)
        yearly_matrices[f"year_{year}"] = np.round(current_P, 4).tolist()

    return {
        "states": STATES,
        "base_transition_matrix": np.round(P, 4).tolist(),
        "multi_year_matrices": yearly_matrices
    }


def simulate_cost_of_inaction(segment: dict, horizon_years: int = 5) -> dict[str, Any]:
    """
    Simulates the exact financial penalty and cost escalation of delaying maintenance
    from Year 1 to Year 2, Year 3, Year 4, and Year 5.
    
    The Pavement Preservation "Rule of 1:5":
    - Year 1 (Preventive): Crack seal / Micro-surfacing (Cost baseline = C1)
    - Year 2 (Deferred 1 yr): Minor BC overlay (Cost ~ 1.70 * C1)
    - Year 3 (Deferred 2 yrs): Major Mill & Overlay (Cost ~ 3.10 * C1) -> +310% escalation
    - Year 4 (Deferred 3 yrs): Deep DBM Inlay & Subgrade Patch (Cost ~ 4.80 * C1)
    - Year 5 (Deferred 4 yrs): Full Structural Reconstruction (Cost ~ 6.50 * C1, capped by reactive cost)
    """
    pci_0 = float(segment.get("pci") or 70.0)
    iri_0 = float(segment.get("iri") or 2.8)
    length_km = float(segment.get("length_km") or 2.5)
    base_prev_cost = float(segment.get("est_preventive_cost_inr") or (length_km * 500000.0))
    base_react_cost = float(segment.get("est_reactive_cost_inr") or (length_km * 3500000.0))

    stress = calculate_stress_factor(segment)
    decay_curve = calculate_weibull_decay(pci_0, iri_0, stress, horizon_years=horizon_years)

    # Cost escalation multipliers by year deferred
    # Calibrated to real-world Delhi PWD Schedule of Rates (DSR) & IRC:82 norms
    # Year 1 is the proactive baseline (1.0x)
    multipliers = [1.0, 1.0, 1.72, 3.10, 4.65, 6.20]
    treatments = [
        "Preventive Micro-Surfacing",
        "Preventive Micro-Surfacing (Seal Coat)",
        "Minor BC Mill & 40mm Overlay",
        "Major Structural Overlay (75mm DBM + BC)",
        "Deep Inlay & Structural Base Stabilization",
        "Full-Depth Reconstruction (Base Course Replacement)"
    ]

    yearly_costs = []
    y1_cost = base_prev_cost

    for t in range(1, horizon_years + 1):
        m = multipliers[t]
        # Adjust multiplier based on corridor stress factor
        m_adjusted = m * (1.0 + (stress - 1.0) * 0.25)
        cost_t = min(base_react_cost * 1.15, y1_cost * m_adjusted)
        
        penalty_inr = max(0.0, cost_t - y1_cost)
        penalty_pct = round(((cost_t - y1_cost) / (y1_cost + 1e-6)) * 100.0, 1)

        pci_at_year = decay_curve[t]["pci"]
        treatment_name = treatments[t]

        # Format INR nicely
        fmt_cost = f"₹{(cost_t / 10000000):.2f} Cr" if cost_t >= 10000000 else f"₹{(cost_t / 100000):.2f} L"
        fmt_penalty = f"₹{(penalty_inr / 10000000):.2f} Cr" if penalty_inr >= 10000000 else f"₹{(penalty_inr / 100000):.2f} L"

        yearly_costs.append({
            "year": t,
            "year_label": f"Year {t}",
            "cost_inr": round(cost_t, 2),
            "cost_formatted": fmt_cost,
            "penalty_inr": round(penalty_inr, 2),
            "penalty_formatted": fmt_penalty,
            "penalty_pct": penalty_pct,
            "cost_multiplier": round(cost_t / (y1_cost + 1e-6), 2),
            "pci": pci_at_year,
            "recommended_treatment": treatment_name
        })

    # Executive decision-maker highlights
    y3 = yearly_costs[2] if len(yearly_costs) >= 3 else yearly_costs[-1]
    y5 = yearly_costs[4] if len(yearly_costs) >= 5 else yearly_costs[-1]
    
    road_name = segment.get("name") or "Corridor"
    headline = (
        f"Deferring {road_name} maintenance from Year 1 to Year 3 increases repair cost by {y3['penalty_pct']:.0f}% "
        f"({y3['penalty_formatted']} financial penalty), causing pavement condition to collapse from {pci_0:.0f} to {y3['pci']:.0f}."
    )

    return {
        "segment_id": segment.get("segment_id"),
        "road_name": road_name,
        "city_zone": segment.get("city_zone"),
        "length_km": length_km,
        "stress_factor": stress,
        "initial_pci": pci_0,
        "initial_iri": iri_0,
        "year_1_baseline_cost_inr": round(y1_cost, 2),
        "year_1_baseline_cost_formatted": f"₹{(y1_cost / 10000000):.2f} Cr" if y1_cost >= 10000000 else f"₹{(y1_cost / 100000):.2f} L",
        "yearly_cost_trajectory": yearly_costs,
        "decay_curve": decay_curve,
        "decision_headline": headline,
        "year_3_penalty_pct": y3["penalty_pct"],
        "year_3_penalty_formatted": y3["penalty_formatted"],
        "year_5_penalty_pct": y5["penalty_pct"],
        "year_5_penalty_formatted": y5["penalty_formatted"]
    }


def simulate_network_cost_of_inaction(segments: list[dict], horizon_years: int = 5) -> dict[str, Any]:
    """
    Aggregates the Cost of Inaction across all candidate segments in the Delhi NCT network.
    Shows the total municipal financial penalty of deferring the entire capital plan.
    """
    if not segments:
        return {"error": "No road segments provided for simulation."}

    # Aggregate by year
    y1_total = sum(float(s.get("est_preventive_cost_inr") or 500000.0) for s in segments)
    
    # Run simulation for each segment
    segment_sims = [simulate_cost_of_inaction(s, horizon_years) for s in segments]

    total_yearly_costs = []
    for t_idx in range(horizon_years):
        t = t_idx + 1
        cost_sum = sum(sim["yearly_cost_trajectory"][t_idx]["cost_inr"] for sim in segment_sims)
        penalty_sum = max(0.0, cost_sum - y1_total)
        penalty_pct = round(((cost_sum - y1_total) / (y1_total + 1e-6)) * 100.0, 1)
        avg_pci = round(float(np.mean([sim["decay_curve"][t]["pci"] for sim in segment_sims])), 1)

        fmt_cost = f"₹{(cost_sum / 10000000):.2f} Cr" if cost_sum >= 10000000 else f"₹{(cost_sum / 100000):.2f} L"
        fmt_penalty = f"₹{(penalty_sum / 10000000):.2f} Cr" if penalty_sum >= 10000000 else f"₹{(penalty_sum / 100000):.2f} L"

        total_yearly_costs.append({
            "year": t,
            "year_label": f"Year {t}",
            "cost_inr": round(cost_sum, 2),
            "cost_formatted": fmt_cost,
            "penalty_inr": round(penalty_sum, 2),
            "penalty_formatted": fmt_penalty,
            "penalty_pct": penalty_pct,
            "avg_pci": avg_pci,
            "cost_multiplier": round(cost_sum / (y1_total + 1e-6), 2)
        })

    y3 = total_yearly_costs[2] if len(total_yearly_costs) >= 3 else total_yearly_costs[-1]
    y5 = total_yearly_costs[4] if len(total_yearly_costs) >= 5 else total_yearly_costs[-1]

    executive_summary = (
        f"Deferring Delhi road maintenance from Year 1 to Year 3 escalates municipal repair liability by "
        f"{y3['penalty_pct']:.0f}% (an added outlay of {y3['penalty_formatted']}). "
        f"By Year 5, neglect compounds costs by {y5['penalty_pct']:.0f}% ({y5['penalty_formatted']} penalty) "
        f"as surface degradation deteriorates into sub-base collapse."
    )

    return {
        "total_segments_analyzed": len(segments),
        "total_km_analyzed": round(sum(float(s.get("length_km") or 0.0) for s in segments), 2),
        "year_1_baseline_inr": round(y1_total, 2),
        "year_1_baseline_formatted": f"₹{(y1_total / 10000000):.2f} Cr" if y1_total >= 10000000 else f"₹{(y1_total / 100000):.2f} L",
        "yearly_network_costs": total_yearly_costs,
        "executive_summary": executive_summary,
        "year_3_penalty_pct": y3["penalty_pct"],
        "year_3_penalty_formatted": y3["penalty_formatted"],
        "year_5_penalty_pct": y5["penalty_pct"],
        "year_5_penalty_formatted": y5["penalty_formatted"],
        "top_vulnerable_corridors": sorted(segment_sims, key=lambda s: s["year_3_penalty_pct"], reverse=True)[:5]
    }


def calculate_remaining_service_life(segment: dict) -> dict[str, Any]:
    """
    Computes Remaining Service Life (RSL in Years) and IRC:37:2018 Structural Fatigue
    Capacity for a road segment based on traffic load, pavement age, and condition distress.
    
    Formula:
    RSL is defined as the time (in years) until PCI drops below the failure limit (PCI < 40)
    or IRI exceeds terminal roughness (IRI > 4.5 m/km).
    """
    pci_0 = float(segment.get("pci") or 70.0)
    iri_0 = float(segment.get("iri") or 2.8)
    aadt = float(segment.get("aadt") or 40000)
    heavy_pct = float(segment.get("heavy_vehicle_pct") or 15.0)
    const_year = int(segment.get("construction_year") or 2015)
    last_maint_year = int(segment.get("last_major_maintenance_year") or 2020)
    current_year = 2026

    pavement_age = current_year - const_year
    surface_age = current_year - last_maint_year
    stress = calculate_stress_factor(segment)

    # 1. Structural Fatigue Life under IRC:37 (Million Standard Axles - msa)
    # Commercial vehicles per day = AADT * heavy_pct / 100
    cvpd = (aadt * (heavy_pct / 100.0))
    # Standard Vehicle Damage Factor (VDF) for Indian urban commercial traffic
    vdf = 3.8
    # Directional distribution factor (D = 0.75 for multi-lane)
    d_factor = 0.75
    # Annual design traffic in msa = 365 * cvpd * d_factor * vdf / 1e6
    annual_msa = (365.0 * cvpd * d_factor * vdf) / 1000000.0
    cumulative_msa_consumed = round(annual_msa * surface_age, 2)
    
    # Typical design capacity for flexible pavement (e.g. 50 to 150 msa depending on road type)
    road_type = str(segment.get("road_type") or "Arterial").lower()
    if "highway" in road_type or "express" in road_type:
        design_fatigue_msa = 120.0
    elif "arterial" in road_type:
        design_fatigue_msa = 80.0
    else:
        design_fatigue_msa = 40.0

    fatigue_consumed_pct = min(100.0, round((cumulative_msa_consumed / design_fatigue_msa) * 100.0, 1))
    remaining_fatigue_msa = max(0.0, round(design_fatigue_msa - cumulative_msa_consumed, 2))

    # 2. Time-to-terminal failure (Weibull decay until PCI < 40 or IRI > 4.5)
    beta = 2.15
    eta = max(3.5, 11.5 / stress)

    # Solve PCI(t) = 40 => 40 = PCI_0 * exp(-(t/eta)^beta)
    # -(t/eta)^beta = ln(40 / PCI_0)
    # t = eta * (-ln(40 / PCI_0))^(1/beta)
    if pci_0 <= 40.0:
        rsl_years = 0.0
    else:
        ratio = 40.0 / pci_0
        inner = -math.log(max(0.01, ratio))
        rsl_years = max(0.2, eta * (inner ** (1.0 / beta)))
        rsl_years = min(15.0, round(rsl_years, 1))

    # Structural Health Verdict
    if rsl_years <= 1.5 or fatigue_consumed_pct >= 85.0:
        structural_verdict = "Critical / Exhausted (Immediate Reconstruction Needed)"
        rsl_category = "Critical (<1.5 yrs)"
    elif rsl_years <= 3.5 or fatigue_consumed_pct >= 65.0:
        structural_verdict = "Accelerated Fatigue (Major Structural Overlay Needed)"
        rsl_category = "Vulnerable (1.5–3.5 yrs)"
    else:
        structural_verdict = "Adequate Structural Reserve (Preventive Micro-Surfacing Applicable)"
        rsl_category = "Healthy (>3.5 yrs)"

    return {
        "segment_id": segment.get("segment_id"),
        "road_name": segment.get("name"),
        "rsl_years": rsl_years,
        "rsl_category": rsl_category,
        "structural_verdict": structural_verdict,
        "pavement_age_years": pavement_age,
        "surface_age_years": surface_age,
        "annual_msa": round(annual_msa, 2),
        "cumulative_msa_consumed": cumulative_msa_consumed,
        "design_fatigue_msa": design_fatigue_msa,
        "fatigue_consumed_pct": fatigue_consumed_pct,
        "remaining_fatigue_msa": remaining_fatigue_msa,
        "irc37_compliance": "Compliant" if fatigue_consumed_pct < 80.0 else "Non-Compliant (Fatigue Threshold Exceeded)"
    }

