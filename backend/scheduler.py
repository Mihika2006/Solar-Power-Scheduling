"""Smart agricultural load decision tree (Level 1 > Level 2 > Level 3)."""
from typing import List

IRRIGATION_KW = 3.5
COLD_STORAGE_KW = 2.0
CROP_DRYER_KW = 1.5
IRRIGATION_HOURS = 4    # daily irrigation requirement
DRYER_HOURS = 6         # daily batch-drying requirement
COLD_HOURS = 24         # continuous refrigeration
GRID_EMISSION_KG_PER_KWH = 0.82


def schedule_loads(p_pred_kw: List[float]) -> dict:
    n = len(p_pred_kw)
    # Level 1: irrigation takes the strongest hours where P_pred >= 3.5 kW
    eligible = [h for h in range(n) if p_pred_kw[h] >= IRRIGATION_KW]
    irrigation_hours = set(sorted(eligible, key=lambda h: -p_pred_kw[h])[:IRRIGATION_HOURS])

    # Level 2: cold storage whenever power remains after Level 1
    remaining, cold_on, irr_on = [], [], []
    for h in range(n):
        rem = p_pred_kw[h]
        irr = h in irrigation_hours
        if irr:
            rem -= IRRIGATION_KW
        cold = rem >= COLD_STORAGE_KW
        if cold:
            rem -= COLD_STORAGE_KW
        irr_on.append(irr)
        cold_on.append(cold)
        remaining.append(rem)

    # Level 3: crop dryer only on surplus once Levels 1 and 2 are served
    candidates = [h for h in range(n) if cold_on[h] and remaining[h] >= CROP_DRYER_KW]
    dryer_hours = set(sorted(candidates, key=lambda h: -remaining[h])[:DRYER_HOURS])

    rows = []
    for h in range(n):
        dry = h in dryer_hours
        used = (IRRIGATION_KW if irr_on[h] else 0) + (COLD_STORAGE_KW if cold_on[h] else 0) + (CROP_DRYER_KW if dry else 0)
        nxt = p_pred_kw[h + 1] if h + 1 < n else p_pred_kw[h]
        rows.append({
            "hour": h,
            "irrigation_kw": IRRIGATION_KW if irr_on[h] else 0.0,
            "cold_storage_kw": COLD_STORAGE_KW if cold_on[h] else 0.0,
            "crop_dryer_kw": CROP_DRYER_KW if dry else 0.0,
            "precool": bool(cold_on[h] and nxt < COLD_STORAGE_KW),
            "unused_kw": round(max(p_pred_kw[h] - used, 0.0), 3),
        })

    generated = sum(p_pred_kw)
    solar_used = sum(r["irrigation_kw"] + r["cold_storage_kw"] + r["crop_dryer_kw"] for r in rows)
    demand = IRRIGATION_HOURS * IRRIGATION_KW + COLD_HOURS * COLD_STORAGE_KW + DRYER_HOURS * CROP_DRYER_KW
    summary = {
        "total_generated_kwh": round(generated, 2),
        "solar_used_kwh": round(solar_used, 2),
        "surplus_unused_kwh": round(max(generated - solar_used, 0.0), 2),
        "farm_demand_kwh": round(demand, 2),
        "grid_import_kwh": round(max(demand - solar_used, 0.0), 2),
        "grid_saved_pct": round(100.0 * solar_used / demand, 1) if demand else 0.0,
        "carbon_reduction_kg": round(solar_used * GRID_EMISSION_KG_PER_KWH, 2),
        "irrigation_hours_met": len(irrigation_hours),
        "dryer_hours_met": len(dryer_hours),
        "cold_storage_hours_met": sum(cold_on),
        "emission_factor": GRID_EMISSION_KG_PER_KWH,
    }
    return {"rows": rows, "summary": summary}
