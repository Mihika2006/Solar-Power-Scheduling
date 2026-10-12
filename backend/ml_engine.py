"""Random Forest G(t) forecaster and experimental calibration coupling."""
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from weather_service import clear_sky_irradiance

FEATURES = ["hr_sin", "hr_cos", "doy_sin", "doy_cos", "T", "RH", "CLOUD", "G_cs"]
TEST_HOURS = 72  # chronological hold-out (no leakage)


def build_features(df: pd.DataFrame, lat: float) -> pd.DataFrame:
    out = df.copy()
    hour = out.index.hour.values
    doy = out.index.dayofyear.values
    out["hr_sin"] = np.sin(2 * np.pi * hour / 24.0)
    out["hr_cos"] = np.cos(2 * np.pi * hour / 24.0)
    out["doy_sin"] = np.sin(2 * np.pi * doy / 365.0)
    out["doy_cos"] = np.cos(2 * np.pi * doy / 365.0)
    out["G_cs"] = clear_sky_irradiance(lat, doy, hour + 0.5)
    return out


def temperature_factor(temp_c):
    """C_temp = 1 - 0.0045 * (T - 25), floored at 0."""
    return np.clip(1.0 - 0.0045 * (np.asarray(temp_c, dtype=float) - 25.0), 0.0, None)


def calibrated_power_kw(g_wm2, temp_c, area_m2: float, eta_exp_pct: float):
    """P_pred(t) = G(t) * A * eta_exp * C_temp, returned in kW."""
    g = np.asarray(g_wm2, dtype=float)
    return g * area_m2 * (eta_exp_pct / 100.0) * temperature_factor(temp_c) / 1000.0


class SolarForecaster:
    def __init__(self, seed: int = 42):
        self.model = RandomForestRegressor(n_estimators=150, max_depth=14, min_samples_leaf=2,
                                           n_jobs=-1, random_state=seed)
        self.metrics: dict = {}
        self.importances: dict = {}

    def train_and_forecast(self, df: pd.DataFrame, lat: float) -> pd.DataFrame:
        """Train on all but the last 72 h, score on them, and return the final 24 h forecast."""
        feat = build_features(df, lat)
        train, test = feat.iloc[:-TEST_HOURS], feat.iloc[-TEST_HOURS:]
        self.model.fit(train[FEATURES], train["G"])
        pred_test = np.clip(self.model.predict(test[FEATURES]), 0.0, None)
        pred_test[test["G_cs"].values <= 0] = 0.0
        self.metrics = {
            "rmse": round(float(np.sqrt(mean_squared_error(test["G"], pred_test))), 2),
            "mae": round(float(mean_absolute_error(test["G"], pred_test)), 2),
            "r2": round(float(r2_score(test["G"], pred_test)), 4),
            "train_samples": int(len(train)),
            "test_samples": int(len(test)),
        }
        self.importances = {f: round(float(v), 4) for f, v in zip(FEATURES, self.model.feature_importances_)}
        day = test.iloc[-24:].copy()
        day["G_pred"] = pred_test[-24:]
        return day
