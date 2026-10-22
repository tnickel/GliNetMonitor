import os
import json
import logging
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, Query, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from glinet_client import GliNetClient
from database import Database
from collector import DataCollector

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("GliNetMonitor")

# Load config
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
EXAMPLE_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.example.json")

if not os.path.exists(CONFIG_PATH) and os.path.exists(EXAMPLE_CONFIG_PATH):
    import shutil
    shutil.copyfile(EXAMPLE_CONFIG_PATH, CONFIG_PATH)
    logger.info("Created config.json from config.example.json template.")

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = json.load(f)

router_cfg = config.get("router", {})
collector_cfg = config.get("collector", {})
db_cfg = config.get("database", {})

db = Database(db_cfg.get("path", "glinet_monitor.db"))
client = GliNetClient(
    ip=router_cfg.get("ip", "192.168.178.93"),
    username=router_cfg.get("username", "root"),
    password=router_cfg.get("password", ""),
    timeout=router_cfg.get("timeout", 10)
)
collector = DataCollector(
    client=client,
    db=db,
    poll_interval=collector_cfg.get("poll_interval_seconds", 5),
    backfill_limit=collector_cfg.get("backfill_limit", 1000)
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting GL.iNet Collector...")
    collector.start()
    yield
    # Shutdown
    logger.info("Stopping GL.iNet Collector...")
    collector.stop()

app = FastAPI(title="GL.iNet Gateway Network Monitor", lifespan=lifespan)

# API Endpoints
@app.get("/api/status")
def get_status():
    """Return health & connectivity status."""
    c_status = collector.get_status()
    return {
        "router_ip": client.ip,
        "router_model": "GL-MT2500 (Brume 2)",
        "collector": c_status
    }

@app.get("/api/summary")
def get_summary():
    """Return global KPI metrics."""
    return db.get_summary()

@app.get("/api/clients")
def get_clients(search: Optional[str] = Query(None, description="Search client name or IP")):
    """Get list of network clients with activity counts."""
    return db.get_clients(search=search)

@app.get("/api/clients/{client_ip}/domains")
def get_client_domains(
    client_ip: str,
    search: Optional[str] = Query(None, description="Filter domain names"),
    status: str = Query("all", description="all, allowed, blocked"),
    sort: str = Query("count", description="count, last_accessed, domain"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    """Get web addresses visited by a specific client."""
    return db.get_client_domains(
        client_ip=client_ip,
        search=search,
        filter_status=status,
        sort_by=sort,
        limit=limit,
        offset=offset
    )

@app.get("/api/domains")
def get_top_domains(
    limit: int = Query(50, ge=1, le=200),
    search: Optional[str] = Query(None, description="Filter domain")
):
    """Get top domains across all network clients."""
    return db.get_network_top_domains(limit=limit, search=search)

@app.get("/api/activity")
def get_activity(
    client_ip: Optional[str] = Query(None, description="Filter by client IP"),
    limit: int = Query(50, ge=1, le=200)
):
    """Get live recent DNS requests."""
    return db.get_recent_activity(client_ip=client_ip, limit=limit)

@app.get("/api/trends")
def get_trends(hours: int = Query(24, ge=1, le=168)):
    """Get hourly query activity for charts."""
    return db.get_hourly_activity(hours=hours)

@app.post("/api/sync")
def trigger_sync():
    """Trigger manual polling step."""
    return collector.sync_now()

# Mount static web UI
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
def serve_index():
    index_file = os.path.join(static_dir, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "GL.iNet Monitor API is running. UI files missing in static/."}

if __name__ == "__main__":
    import uvicorn
    server_cfg = config.get("server", {})
    host = server_cfg.get("host", "0.0.0.0")
    port = server_cfg.get("port", 8080)
    print(f"Starting GliNetMonitor on http://localhost:{port} ...")
    uvicorn.run("main:app", host=host, port=port, reload=False)
