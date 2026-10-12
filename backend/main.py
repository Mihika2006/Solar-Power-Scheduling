"""FastAPI entry point: serves the JSON API and the static dashboard."""
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from materials_data import MATERIALS, get_material, iv_curve
from ml_engine import SolarForecaster, calibrated_power_kw, temperature_factor
from scheduler import schedule_loads
from weather_service import get_weather

app = FastAPI(title="DSSRES Solar Dashboard API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class SimRequest(BaseModel):
    dopant: str = Field("La")
    area_m2: float = Field(120.0, gt=0, le=100000)
    latitude: float = Field(22.0, ge=-90, le=90)
    longitude: float = Field(78.0, ge=-180, le=180)
    use_live_weather: bool = True


def _material_payload(key: str) -> dict:
    try:
        return {**get_material(key), "iv": iv_curve(key)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/materials")
def materials():
    return {"materials": [{"key": k, **v} for k, v in MATERIALS.items()]}


@app.get("/api/iv-curve/{dopant}")
def iv(dopant: str):
    return {"selected": _material_payload(dopant), "control": _material_payload("Control")}


@app.post("/api/simulate")
def simulate(req: SimRequest):
    material = _material_payload(req.dopant)
    weather, info = get_weather(req.latitude, req.longitude, req.use_live_weather)
    forecaster = SolarForecaster()
    day = forecaster.train_and_forecast(weather, req.latitude)

    g_pred = day["G_pred"].values
    temp = day["T"].values
    p_pred = calibrated_power_kw(g_pred, temp, req.area_m2, material["eta"])
    p_control = calibrated_power_kw(g_pred, temp, req.area_m2, MATERIALS["Control"]["eta"])
    plan = schedule_loads([float(x) for x in p_pred])
    control_plan = schedule_loads([float(x) for x in p_control])

    hourly = []
    for i, row in enumerate(plan["rows"]):
        hourly.append({
            **row,
            "label": f"{i:02d}:00",
            "g_forecast": round(float(g_pred[i]), 1),
            "g_actual": round(float(day["G"].values[i]), 1),
            "temp_c": round(float(temp[i]), 1),
            "c_temp": round(float(temperature_factor(temp[i])), 4),
            "p_pred_kw": round(float(p_pred[i]), 3),
        })

    summary = plan["summary"]
    summary["control_generated_kwh"] = control_plan["summary"]["total_generated_kwh"]
    summary["control_grid_saved_pct"] = control_plan["summary"]["grid_saved_pct"]
    summary["gain_vs_control_kwh"] = round(summary["total_generated_kwh"] - summary["control_generated_kwh"], 2)

    return {
        "date": str(day.index[0].date()),
        "dopant": material,
        "inputs": req.model_dump(),
        "weather": info,
        "model": {"name": "RandomForestRegressor", "metrics": forecaster.metrics, "importances": forecaster.importances},
        "hourly": hourly,
        "summary": summary,
        "iv": {"selected": material, "control": _material_payload("Control")},
    }


FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
