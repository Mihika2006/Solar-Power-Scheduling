"""NASA POWER hourly weather ingestion with a physically-shaped synthetic fallback."""
import math
import time
from datetime import date, timedelta

import numpy as np
import pandas as pd
import requests

NASA_URL = "https://power.larc.nasa.gov/api/temporal/hourly/point"
NASA_PARAMS = "ALLSKY_SFC_SW_DWN,T2M,RH2M,CLOUD_AMT"
HISTORY_DAYS = 45
_CACHE: dict = {}
_CACHE_TTL = 3600


def clear_sky_irradiance(lat, doy, solar_hour):
    """Clear-sky GHI (W/m^2) from solar geometry. Inputs may be numpy arrays; hours are local solar time."""
    lat_r = math.radians(lat)
    decl = np.radians(23.45) * np.sin(2 * np.pi * (284 + np.asarray(doy)) / 365.0)
    hour_angle = np.radians(15.0 * (np.asarray(solar_hour) - 12.0))
    cosz = np.sin(lat_r) * np.sin(decl) + np.cos(lat_r) * np.cos(decl) * np.cos(hour_angle)
    return 1050.0 * np.clip(cosz, 0.0, None) ** 1.15


def fetch_nasa_power(lat: float, lon: float, days: int = HISTORY_DAYS) -> pd.DataFrame:
    end = date.today() - timedelta(days=7)  # NASA POWER hourly data lags real time
    start = end - timedelta(days=days - 1)
    params = {
        "parameters": NASA_PARAMS, "community": "AG", "longitude": lon, "latitude": lat,
        "start": start.strftime("%Y%m%d"), "end": end.strftime("%Y%m%d"),
        "format": "JSON", "time-standard": "LST",
    }
    r = requests.get(NASA_URL, params=params, timeout=25)
    r.raise_for_status()
    p = r.json()["properties"]["parameter"]
    df = pd.DataFrame({"G": p["ALLSKY_SFC_SW_DWN"], "T": p["T2M"], "RH": p["RH2M"], "CLOUD": p["CLOUD_AMT"]})
    df.index = pd.to_datetime(df.index, format="%Y%m%d%H")
    df = df.sort_index().replace(-999, np.nan)
    df = df.interpolate(limit_direction="both")
    if df.isna().any().any() or len(df) < 24 * 10:
        raise ValueError("NASA POWER returned insufficient data")
    df["G"] = df["G"].clip(lower=0.0)
    df["CLOUD"] = df["CLOUD"].clip(0, 100)
    df["RH"] = df["RH"].clip(0, 100)
    return df


def generate_synthetic(lat: float, lon: float, days: int = HISTORY_DAYS) -> pd.DataFrame:
    rng = np.random.default_rng(int(abs(lat) * 1000 + abs(lon) * 10))
    idx = pd.date_range(end=pd.Timestamp(date.today()) + pd.Timedelta(hours=23), periods=days * 24, freq="h")
    doy = idx.dayofyear.values
    hour = idx.hour.values + 0.5
    day_cloud = np.repeat(np.clip(rng.beta(1.3, 2.4, days) * 100, 0, 100), 24)
    cloud = np.clip(day_cloud + rng.normal(0, 12, len(idx)), 0, 100)
    g = clear_sky_irradiance(lat, doy, hour) * (1 - 0.75 * (cloud / 100) ** 3.4)
    g = np.clip(g * (1 + rng.normal(0, 0.04, len(idx))), 0, None)
    base_t = 31.0 - 0.35 * abs(lat) + 4.0 * np.sin(2 * np.pi * (doy - 100) / 365.0)
    temp = base_t + 7.0 * np.sin(2 * np.pi * (hour - 9) / 24.0) - 0.04 * cloud + rng.normal(0, 0.8, len(idx))
    rh = np.clip(70 - 2.0 * (temp - base_t) + 0.18 * cloud + rng.normal(0, 4, len(idx)), 15, 100)
    return pd.DataFrame({"G": g, "T": temp, "RH": rh, "CLOUD": cloud}, index=idx)


def get_weather(lat: float, lon: float, use_live: bool = True):
    """Return (DataFrame, info dict). Falls back to synthetic data if NASA POWER is unreachable."""
    key = (round(lat, 2), round(lon, 2), use_live)
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < _CACHE_TTL:
        return hit[1].copy(), hit[2]
    if use_live:
        try:
            df = fetch_nasa_power(lat, lon)
            info = {"source": "NASA POWER", "synthetic": False, "note": "Live hourly data from NASA POWER."}
        except Exception as exc:  # network error, API error, malformed payload
            df = generate_synthetic(lat, lon)
            info = {"source": "Synthetic fallback", "synthetic": True,
                    "note": f"NASA POWER unavailable ({type(exc).__name__}); using synthetic weather."}
    else:
        df = generate_synthetic(lat, lon)
        info = {"source": "Synthetic", "synthetic": True, "note": "Synthetic weather selected by user."}
    _CACHE[key] = (time.time(), df, info)
    return df.copy(), info
