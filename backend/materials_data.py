"""Lab-measured DSSC baseline parameters (Control, Ag, Cu, Mn, La doped ZnO/TiO2 ETL).

eta (%) = Voc * Jsc * FF / P_in, with P_in = 100 mW/cm^2 (AM 1.5G).
"""
from functools import lru_cache
import numpy as np

P_IN_MW_CM2 = 100.0

MATERIALS = {
    "Control": {"label": "Control (Undoped TiO2/ZnO)", "voc": 0.70, "jsc": 11.2, "ff": 0.62, "eta": 4.86},
    "Ag": {"label": "Ag-doped ZnO/TiO2", "voc": 0.76, "jsc": 14.5, "ff": 0.68, "eta": 7.50},
    "Cu": {"label": "Cu-doped ZnO/TiO2", "voc": 0.74, "jsc": 13.8, "ff": 0.66, "eta": 6.74},
    "Mn": {"label": "Mn-doped ZnO/TiO2", "voc": 0.72, "jsc": 12.9, "ff": 0.64, "eta": 5.94},
    "La": {"label": "La-doped ZnO/TiO2", "voc": 0.78, "jsc": 15.1, "ff": 0.70, "eta": 8.24},
}


def get_material(key: str) -> dict:
    if key not in MATERIALS:
        raise KeyError(f"Unknown dopant '{key}'. Choose from {list(MATERIALS)}")
    return {"key": key, **MATERIALS[key]}


def _fill_factor(a: float, voc: float) -> float:
    v = np.linspace(0.0, voc, 600)
    j = 1.0 - (np.exp(v / a) - 1.0) / (np.exp(voc / a) - 1.0)
    return float((v * j).max() / voc)


@lru_cache(maxsize=16)
def _ideality_scale(key: str) -> float:
    """Bisect the diode shape parameter so the modelled FF matches the measured FF."""
    m = MATERIALS[key]
    lo, hi = 0.004, 2.0  # FF falls as the shape parameter grows
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if _fill_factor(mid, m["voc"]) > m["ff"]:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


@lru_cache(maxsize=16)
def iv_curve(key: str, points: int = 80) -> dict:
    """Reconstruct a J-V curve (mA/cm^2) anchored on measured Voc, Jsc and FF."""
    m = MATERIALS[key]
    a = _ideality_scale(key)
    v = np.linspace(0.0, m["voc"], points)
    j = m["jsc"] * (1.0 - (np.exp(v / a) - 1.0) / (np.exp(m["voc"] / a) - 1.0))
    p = v * j  # mW/cm^2
    k = int(np.argmax(p))
    return {
        "voltage": [round(float(x), 4) for x in v],
        "current": [round(float(x), 4) for x in j],
        "power": [round(float(x), 4) for x in p],
        "mpp": {"v": round(float(v[k]), 4), "j": round(float(j[k]), 4), "p": round(float(p[k]), 4)},
    }
