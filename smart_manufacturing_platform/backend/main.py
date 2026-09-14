import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager

from backend.database import init_db
from backend.routes import router as api_router, active_connections, simulator

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize database and start simulation engine
    init_db()
    simulator.start()
    yield
    # Shutdown: clean up background tasks
    simulator.stop()

app = FastAPI(
    title="Smart Manufacturing & Production Control Platform",
    description="MES 4.0: Live resource tracking, anti-collision locking, digital thread genealogy, and predictive early-warning.",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

# Mount static frontend assets
frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
static_dir = os.path.join(frontend_dir, "static")

if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
def serve_dashboard():
    index_path = os.path.join(frontend_dir, "index.html")
    return FileResponse(index_path)

@app.websocket("/ws/factory")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    try:
        while True:
            # Keep connection alive and receive incoming client commands
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in active_connections:
            active_connections.remove(websocket)
    except Exception:
        if websocket in active_connections:
            active_connections.remove(websocket)
