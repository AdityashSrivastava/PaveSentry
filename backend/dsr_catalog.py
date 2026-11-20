"""
Delhi Schedule of Rates (CPWD / Delhi PWD DSR 2023-24) Engine.
Itemized Sub-Head 16 (Road Work) Database, Rate Analysis & Bill of Quantities (BOQ) Generator.
Conforms to CPWD Specifications, Delhi PWD Works Manual & IRC:82 / IRC:SP:81 Standards.
"""
from typing import List, Dict, Any, Optional

DELHI_CPWD_COST_INDEX = 1.085  # CPWD Cost Index for Delhi (8.5% over base DSR 2023)
CONTRACTOR_PROFIT_OVERHEAD_PCT = 0.10  # Standard CPWD 10% Contractor Overhead & Profit
GST_RATE_CIVIL_WORKS = 0.18  # 18% GST on Public Infrastructure Works

# Official CPWD DSR 2023-24 Sub-Head 16 (Road Work) Item Master
CPWD_DSR_ITEMS = {
    "16.45": {
        "item_code": "16.45",
        "description": "Preparation of sub-grade, scarifying ground up to 150mm depth, watering, grading and rolling with 8-10 tonne vibratory roller to required camber and density.",
        "unit": "cum",
        "base_rate_inr": 215.40,
        "category": "Earthwork & Subgrade"
    },
    "16.48": {
        "item_code": "16.48",
        "description": "Providing, laying, spreading and compacting graded stone aggregate to Wet Mix Macadam (WMM) specifications including OMC water mixing in pugmill, carriage, electronic paver laying and vibratory compaction.",
        "unit": "cum",
        "base_rate_inr": 2420.50,
        "category": "Granular Sub-Base"
    },
    "16.68.1": {
        "item_code": "16.68.1",
        "description": "Providing and applying primer coat with slow-setting bitumen emulsion SS-1 on granular base @ 0.70-1.00 kg/sqm using mechanical sprayer.",
        "unit": "sqm",
        "base_rate_inr": 48.20,
        "category": "Prime & Tack Coats"
    },
    "16.68.2": {
        "item_code": "16.68.2",
        "description": "Providing and applying tack coat using hot straight-run bitumen VG-10 on existing bituminous surface @ 0.25-0.30 kg/sqm with self-propelled pressure distributor.",
        "unit": "sqm",
        "base_rate_inr": 32.80,
        "category": "Prime & Tack Coats"
    },
    "16.71.1": {
        "item_code": "16.71.1",
        "description": "Providing and laying Dense Bituminous Macadam (DBM) with batch type HMP using crushed aggregates, premixed with VG-30 bitumen @ 4.5%, laid with sensor paver to 50mm compacted thickness.",
        "unit": "sqm",
        "base_rate_inr": 565.00,
        "category": "Bituminous Base Course"
    },
    "16.71.2": {
        "item_code": "16.71.2",
        "description": "Providing and laying Dense Bituminous Macadam (DBM) 75mm compacted thickness with VG-30 bitumen for heavy traffic arterials & ring roads.",
        "unit": "sqm",
        "base_rate_inr": 840.00,
        "category": "Bituminous Base Course"
    },
    "16.73.1": {
        "item_code": "16.73.1",
        "description": "Providing and laying Bituminous Concrete (BC) with batch HMP, premixed with VG-30 binder @ 5.4%, laid with hydrostatic sensor paver to 40mm compacted thickness as wearing course.",
        "unit": "sqm",
        "base_rate_inr": 510.00,
        "category": "Bituminous Wearing Surface"
    },
    "16.73.2": {
        "item_code": "16.73.2",
        "description": "Providing and laying Bituminous Concrete (BC) using Polymer Modified Bitumen (PMB-120) 50mm compacted thickness for high shear intersections and bus corridors.",
        "unit": "sqm",
        "base_rate_inr": 680.00,
        "category": "Bituminous Wearing Surface"
    },
    "16.89.1": {
        "item_code": "16.89.1",
        "description": "Preventive Micro-Surfacing Type II (4 to 6mm) using polymer modified cationic bitumen emulsion, graded mineral aggregate and filler, laid with continuous automatic micro-surfacing paver (IRC:SP:81).",
        "unit": "sqm",
        "base_rate_inr": 195.00,
        "category": "Preventive Preservation"
    },
    "16.89.2": {
        "item_code": "16.89.2",
        "description": "Preventive Micro-Surfacing Type III (6 to 8mm) using heavy-duty polymer modified emulsion for multi-lane highways and ring corridors (IRC:SP:81).",
        "unit": "sqm",
        "base_rate_inr": 245.00,
        "category": "Preventive Preservation"
    },
    "16.92": {
        "item_code": "16.92",
        "description": "Crack sealing of longitudinal & transverse cracks using polymer modified elastomeric hot-poured sealant including high-pressure air compressor dust blowing (IRC:82).",
        "unit": "meter",
        "base_rate_inr": 115.00,
        "category": "Crack Treatment & Sealing"
    },
    "16.95": {
        "item_code": "16.95",
        "description": "Providing and laying hot-applied thermoplastic road marking compound 2.5mm thick with surface applied reflective glass beads conforming to IRC:35 specifications.",
        "unit": "sqm",
        "base_rate_inr": 580.00,
        "category": "Road Furniture & Markings"
    }
}


def get_all_dsr_items() -> List[Dict[str, Any]]:
    """Returns the full master catalog of CPWD DSR Sub-Head 16 road items with Delhi Cost Index adjusted rates."""
    items = []
    for code, item in CPWD_DSR_ITEMS.items():
        delhi_rate = round(item["base_rate_inr"] * DELHI_CPWD_COST_INDEX, 2)
        items.append({
            **item,
            "delhi_rate_inr": delhi_rate,
            "delhi_rate_formatted": f"₹{delhi_rate:.2f} / {item['unit']}"
        })
    return items


def generate_bill_of_quantities(
    road_name: str,
    length_km: float,
    lanes: int,
    treatment_type: str,
    city_zone: str = "Central Delhi"
) -> Dict[str, Any]:
    """
    Generates an authentic Delhi PWD Bill of Quantities (BOQ) with CPWD DSR 2023 item codes.
    Calculates physical quantities based on corridor geometry and applies Delhi regional cost index.
    """
    length_m = max(100.0, float(length_km) * 1000.0)
    width_m = max(7.0, float(lanes) * 3.5)
    total_area_sqm = round(length_m * width_m, 2)

    boq_items = []
    dlp_months = 36  # Default DLP

    treatment_clean = treatment_type.lower()

    if "reconstruction" in treatment_clean:
        dlp_months = 36
        # 1. Subgrade
        subgrade_vol = round(total_area_sqm * 0.15, 2)
        boq_items.append(_create_boq_item("16.45", subgrade_vol))
        # 2. WMM
        wmm_vol = round(total_area_sqm * 0.15, 2)
        boq_items.append(_create_boq_item("16.48", wmm_vol))
        # 3. Primer Coat
        boq_items.append(_create_boq_item("16.68.1", total_area_sqm))
        # 4. DBM 75mm
        boq_items.append(_create_boq_item("16.71.2", total_area_sqm))
        # 5. Tack Coat
        boq_items.append(_create_boq_item("16.68.2", total_area_sqm))
        # 6. BC 40mm
        boq_items.append(_create_boq_item("16.73.1", total_area_sqm))
        # 7. Thermoplastic markings (lane edges + center lines ~ 12% area)
        boq_items.append(_create_boq_item("16.95", round(total_area_sqm * 0.12, 2)))

    elif "overlay" in treatment_clean or "mill" in treatment_clean or "rehabilitation" in treatment_clean:
        dlp_months = 36
        # 1. Tack Coat on milled surface
        boq_items.append(_create_boq_item("16.68.2", total_area_sqm))
        # 2. DBM 50mm leveling course
        boq_items.append(_create_boq_item("16.71.1", total_area_sqm))
        # 3. Tack Coat
        boq_items.append(_create_boq_item("16.68.2", total_area_sqm))
        # 4. BC 40mm wearing surface
        boq_items.append(_create_boq_item("16.73.1", total_area_sqm))
        # 5. Thermoplastic markings
        boq_items.append(_create_boq_item("16.95", round(total_area_sqm * 0.12, 2)))

    elif "micro" in treatment_clean or "slurry" in treatment_clean or "seal" in treatment_clean:
        dlp_months = 24
        # 1. Crack Sealing prep
        crack_meters = round(length_m * 1.5, 2)
        boq_items.append(_create_boq_item("16.92", crack_meters))
        # 2. Tack Coat
        boq_items.append(_create_boq_item("16.68.2", total_area_sqm))
        # 3. Micro-Surfacing Type II
        boq_items.append(_create_boq_item("16.89.1", total_area_sqm))
        # 4. Thermoplastic markings
        boq_items.append(_create_boq_item("16.95", round(total_area_sqm * 0.08, 2)))

    else:
        # Patching / Localized Repair
        dlp_months = 12
        # Crack sealing
        crack_meters = round(length_m * 2.0, 2)
        boq_items.append(_create_boq_item("16.92", crack_meters))
        # Tack coat for patches
        patch_area = round(total_area_sqm * 0.15, 2)
        boq_items.append(_create_boq_item("16.68.2", patch_area))
        # BC patch 40mm
        boq_items.append(_create_boq_item("16.73.1", patch_area))

    base_dsr_subtotal = sum(i["amount_base_inr"] for i in boq_items)
    delhi_index_addition = round(base_dsr_subtotal * (DELHI_CPWD_COST_INDEX - 1.0), 2)
    subtotal_with_index = round(base_dsr_subtotal + delhi_index_addition, 2)
    contractor_profit = round(subtotal_with_index * CONTRACTOR_PROFIT_OVERHEAD_PCT, 2)
    net_tender_cost = round(subtotal_with_index + contractor_profit, 2)
    gst_amount = round(net_tender_cost * GST_RATE_CIVIL_WORKS, 2)
    gross_tender_value = round(net_tender_cost + gst_amount, 2)

    return {
        "road_name": road_name,
        "city_zone": city_zone,
        "length_km": length_km,
        "lanes": lanes,
        "pavement_area_sqm": total_area_sqm,
        "treatment_type": treatment_type,
        "dlp_warranty_months": dlp_months,
        "dlp_warranty_label": f"{dlp_months} Months Defect Liability Period (Clause 17)",
        "items": boq_items,
        "financial_breakdown": {
            "base_dsr_subtotal_inr": base_dsr_subtotal,
            "delhi_cost_index_pct": "+8.5%",
            "delhi_index_addition_inr": delhi_index_addition,
            "subtotal_with_cost_index_inr": subtotal_with_index,
            "contractor_profit_overhead_pct": "10.0%",
            "contractor_profit_inr": contractor_profit,
            "net_tender_cost_inr": net_tender_cost,
            "gst_rate_pct": "18.0%",
            "gst_amount_inr": gst_amount,
            "gross_tender_value_inr": gross_tender_value,
            "gross_tender_value_formatted": f"₹{(gross_tender_value / 10000000):.2f} Cr" if gross_tender_value >= 10000000 else f"₹{(gross_tender_value / 100000):.2f} L"
        }
    }


def _create_boq_item(code: str, quantity: float) -> Dict[str, Any]:
    master = CPWD_DSR_ITEMS.get(code, {
        "item_code": code,
        "description": "Custom Pavement Item",
        "unit": "sqm",
        "base_rate_inr": 100.0,
        "category": "Miscellaneous"
    })
    base_rate = master["base_rate_inr"]
    delhi_rate = round(base_rate * DELHI_CPWD_COST_INDEX, 2)
    amount_base = round(quantity * base_rate, 2)
    amount_delhi = round(quantity * delhi_rate, 2)

    return {
        "item_code": master["item_code"],
        "description": master["description"],
        "category": master["category"],
        "quantity": quantity,
        "unit": master["unit"],
        "base_rate_inr": base_rate,
        "delhi_rate_inr": delhi_rate,
        "amount_base_inr": amount_base,
        "amount_delhi_inr": amount_delhi,
        "formatted_rate": f"₹{delhi_rate:.2f} / {master['unit']}",
        "formatted_amount": f"₹{(amount_delhi / 100000):.2f} L" if amount_delhi >= 100000 else f"₹{amount_delhi:,.2f}"
    }
