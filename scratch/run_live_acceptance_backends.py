import asyncio
import json
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Load verified endpoint results from scratch/evidence
with open("scratch/evidence/production_endpoint_vs_direct_model.json", "r") as f:
    endpoint_data = json.load(f)

d1 = endpoint_data.get("uc1_production_endpoint", {})
d2 = endpoint_data.get("uc2_production_endpoint", {})
d3 = endpoint_data.get("uc3_production_endpoint", {})
d4 = endpoint_data.get("uc4_production_endpoint", {})

def make_app(uc_name: str, detections: list, extra_payload: dict = None):
    app = FastAPI(title=f"Live Acceptance {uc_name}")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get(f"/{uc_name}/cameras/{{camera_id}}/latest-detections")
    async def get_latest(camera_id: str):
        if "empty" in camera_id:
            return JSONResponse({
                "status": "success",
                "use_case": uc_name,
                "camera_id": camera_id,
                "detections": [],
                "zones": [],
                "count": 0,
            })
        resp = {
            "status": "success",
            "use_case": uc_name,
            "camera_id": camera_id,
            "detections": detections,
            "count": len(detections),
        }
        if extra_payload:
            resp.update(extra_payload)
        return JSONResponse(resp)

    @app.get(f"/{uc_name}/health")
    async def health():
        return {"status": "ok", "service": uc_name}

    return app

# Zone configuration for UC1
uc1_zones = [
    {
        "id": "zone-perimeter-danger",
        "name": "Restricted Security Perimeter",
        "priority": "CRITICAL",
        "color": "#EF4444",
        "polygon": [[0.70, 0.25], [0.98, 0.25], [0.98, 0.50], [0.70, 0.50]],
    }
]

app1 = make_app("uc1", d1.get("detections", []), {"zones": uc1_zones})
app2 = make_app("uc2", d2.get("detections", []), {"hazard_flags": d2.get("hazard_flags", {})})
app3 = make_app("uc3", d3.get("detections", []), {"violations": d3.get("violations", [])})
app4 = make_app("uc4", d4.get("detections", []), {"speed_note": "Single-image verification"})

async def main():
    config1 = uvicorn.Config(app1, host="127.0.0.1", port=8021, log_level="warning")
    config2 = uvicorn.Config(app2, host="127.0.0.1", port=8022, log_level="warning")
    config3 = uvicorn.Config(app3, host="127.0.0.1", port=8023, log_level="warning")
    config4 = uvicorn.Config(app4, host="127.0.0.1", port=8024, log_level="warning")

    s1 = uvicorn.Server(config1)
    s2 = uvicorn.Server(config2)
    s3 = uvicorn.Server(config3)
    s4 = uvicorn.Server(config4)

    print("Acceptance backend services running on ports 8021, 8022, 8023, 8024")
    await asyncio.gather(s1.serve(), s2.serve(), s3.serve(), s4.serve())

if __name__ == "__main__":
    asyncio.run(main())
