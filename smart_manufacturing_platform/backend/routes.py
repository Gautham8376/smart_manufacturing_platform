from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.responses import JSONResponse
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

from backend.database import get_connection
from backend.models import (
    MachineResponse, MaterialResponse, OperatorResponse, ProductionRunResponse,
    ProductionRunCreate, ProductionRunDispatch, MaterialHoldRequest, MaterialReleaseRequest,
    SerializedUnitResponse, AlertResponse, RootCauseAnalysisRequest, ScenarioTriggerRequest
)
from backend.lock_manager import LockManager, ResourceConflictException
from backend.traceability import TraceabilityEngine
from backend.anomaly_detector import AnomalyDetector
from backend.simulator import FactorySimulator

router = APIRouter(prefix="/api")

# Active WebSocket connections
active_connections: List[WebSocket] = []

async def broadcast_ws(payload: Dict[str, Any]):
    disconnected = []
    for ws in active_connections:
        try:
            await ws.send_json(payload)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        if ws in active_connections:
            active_connections.remove(ws)

# Global simulator instance
simulator = FactorySimulator(broadcast_callback=broadcast_ws)

# ================= REST ENDPOINTS =================

@router.get("/status")
def get_factory_status():
    """
    Returns high-level status of the factory floor, overall equipment effectiveness (OEE),
    active work orders, and open alerts.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM machines")
        machines = [dict(r) for r in cursor.fetchall()]

        cursor.execute("SELECT * FROM materials")
        materials = [dict(r) for r in cursor.fetchall()]

        cursor.execute("SELECT id, name, badge_id, shift, status, active_machine_id, active_run_id, certified_operations, certification_expires FROM operators")
        operators = []
        for r in cursor.fetchall():
            d = dict(r)
            d["certified_operations"] = json.loads(d["certified_operations"] or "[]")
            operators.append(d)

        cursor.execute("SELECT * FROM production_runs ORDER BY created_at DESC")
        runs = [dict(r) for r in cursor.fetchall()]

        cursor.execute("SELECT * FROM alerts WHERE status = 'ACTIVE' ORDER BY timestamp DESC")
        active_alerts = [dict(r) for r in cursor.fetchall()]

        cursor.execute("SELECT * FROM resource_locks WHERE lock_status = 'HELD'")
        active_locks = [dict(r) for r in cursor.fetchall()]

        # Compute summary stats
        running_machines = sum(1 for m in machines if m["status"] == "RUNNING")
        total_machines = len(machines)
        availability = (running_machines / total_machines * 100.0) if total_machines else 0.0

        return {
            "timestamp": datetime.now().isoformat(),
            "simulation_running": simulator.is_running,
            "simulation_speed": simulator.simulation_speed,
            "machines": machines,
            "materials": materials,
            "operators": operators,
            "production_runs": runs,
            "active_alerts": active_alerts,
            "active_locks": active_locks,
            "kpis": {
                "active_runs_count": sum(1 for r in runs if r["status"] == "RUNNING"),
                "blocked_runs_count": sum(1 for r in runs if r["status"] == "BLOCKED"),
                "overdue_runs_count": sum(1 for r in runs if r["status"] == "SCHEDULED" and "2026" in r["due_date"]), # Overdue tag
                "machine_availability_pct": round(availability, 1),
                "total_alerts": len(active_alerts)
            }
        }
    finally:
        conn.close()

@router.get("/machines")
def list_machines():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM machines")
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()

@router.get("/materials")
def list_materials():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM materials")
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()

@router.post("/materials/hold")
async def set_material_hold(req: MaterialHoldRequest):
    try:
        res = LockManager.set_material_hold(req.lot_id, req.hold_reason)
        await broadcast_ws({"event": "MATERIAL_HOLD_TRIGGERED", "lot_id": req.lot_id, "data": res})
        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/materials/release")
async def release_material_hold(req: MaterialReleaseRequest):
    try:
        res = LockManager.release_material_hold(req.lot_id)
        await broadcast_ws({"event": "MATERIAL_HOLD_RELEASED", "lot_id": req.lot_id})
        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/operators")
def list_operators():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM operators")
        ops = []
        for r in cursor.fetchall():
            d = dict(r)
            d["certified_operations"] = json.loads(d["certified_operations"] or "[]")
            ops.append(d)
        return ops
    finally:
        conn.close()

@router.get("/runs")
def list_runs():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM production_runs ORDER BY created_at DESC")
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()

@router.post("/runs/create")
async def create_production_run(run: ProductionRunCreate):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        run_id = f"RUN-2026-{int(datetime.now().timestamp()) % 10000:04d}"
        now_str = datetime.now().isoformat()
        due_str = run.due_date or (datetime.now()).strftime("%Y-%m-%d %H:%M")
        
        cursor.execute("""
        INSERT INTO production_runs (
            id, order_number, product_sku, product_name, target_qty, 
            machine_id, operator_id, required_material_lot_id, required_material_qty,
            status, due_date, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'SCHEDULED', ?, ?)
        """, (
            run_id, run.order_number, run.product_sku, run.product_name, run.target_qty,
            run.machine_id, run.operator_id, run.required_material_lot_id, run.required_material_qty,
            due_str, now_str
        ))
        conn.commit()
        await broadcast_ws({"event": "RUN_CREATED", "run_id": run_id})
        return {"success": True, "run_id": run_id, "order_number": run.order_number}
    finally:
        conn.close()

@router.post("/runs/dispatch")
async def dispatch_run(req: ProductionRunDispatch):
    """
    Attempts to dispatch a production run to machine, operator, and material.
    Protected by strict anti-double-booking locks. Returns HTTP 409 Conflict if resources are blocked.
    """
    try:
        res = LockManager.allocate_and_lock(
            run_id=req.run_id,
            machine_id=req.machine_id,
            operator_id=req.operator_id,
            material_lot_id=req.material_lot_id
        )
        await broadcast_ws({"event": "RUN_DISPATCHED", "data": res})
        return res
    except ResourceConflictException as ex:
        # 409 Conflict with rich diagnostic details
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "error": "RESOURCE_COLLISION_PREVENTED",
                "message": str(ex),
                "conflict_type": ex.conflict_type,
                "resource_id": ex.resource_id,
                "conflicting_run_id": ex.conflicting_run_id
            }
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/runs/{run_id}/complete")
async def complete_run(run_id: str):
    try:
        res = LockManager.release_locks(run_id, "COMPLETED")
        await broadcast_ws({"event": "RUN_COMPLETED", "data": res})
        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/runs/{run_id}/abort")
async def abort_run(run_id: str):
    try:
        res = LockManager.release_locks(run_id, "ABORTED")
        await broadcast_ws({"event": "RUN_ABORTED", "data": res})
        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/locks")
def list_locks():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM resource_locks ORDER BY id DESC LIMIT 50")
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()

@router.get("/alerts")
def list_alerts():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM alerts ORDER BY timestamp DESC LIMIT 50")
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()

@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE alerts SET status = 'ACKNOWLEDGED' WHERE id = ?", (alert_id,))
        conn.commit()
        await broadcast_ws({"event": "ALERT_ACKNOWLEDGED", "alert_id": alert_id})
        return {"success": True, "alert_id": alert_id}
    finally:
        conn.close()

@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: str):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE alerts SET status = 'RESOLVED', resolved_at = ? WHERE id = ?", (datetime.now().isoformat(), alert_id))
        conn.commit()
        await broadcast_ws({"event": "ALERT_RESOLVED", "alert_id": alert_id})
        return {"success": True, "alert_id": alert_id}
    finally:
        conn.close()

# ================= TRACEABILITY & RCA ENDPOINTS =================

@router.get("/trace/unit/{serial_number}")
def get_unit_story(serial_number: str):
    try:
        return TraceabilityEngine.get_unit_story(serial_number)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/trace/material/{lot_id}")
def trace_material(lot_id: str):
    try:
        return TraceabilityEngine.trace_material_forward(lot_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/trace/rca")
def execute_rca(req: RootCauseAnalysisRequest):
    return TraceabilityEngine.root_cause_investigation(req.serial_number, req.run_id, req.lot_id)

@router.get("/telemetry/history")
def get_telemetry_history(machine_id: str = "CNC-01"):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT * FROM telemetry_history 
        WHERE machine_id = ? 
        ORDER BY id DESC LIMIT 40
        """, (machine_id,))
        rows = [dict(r) for r in cursor.fetchall()]
        rows.reverse()
        return rows
    finally:
        conn.close()

# ================= SIMULATOR & SCENARIOS =================

@router.post("/simulator/toggle")
def toggle_simulator(running: Optional[bool] = None, speed: Optional[float] = None):
    if speed is not None:
        simulator.simulation_speed = max(0.5, min(5.0, speed))
    if running is not None:
        if running:
            simulator.start()
        else:
            simulator.stop()
    return {"running": simulator.is_running, "speed": simulator.simulation_speed}

@router.post("/simulator/scenario")
async def trigger_scenario(req: ScenarioTriggerRequest):
    if req.scenario_name == "prompt_freeze":
        res = simulator.trigger_prompt_freeze_scenario()
    elif req.scenario_name == "spindle_drift":
        res = simulator.trigger_spindle_drift_scenario()
    elif req.scenario_name == "genealogy_recall":
        res = simulator.trigger_genealogy_recall_scenario()
    elif req.scenario_name == "reset":
        res = simulator.reset_factory()
    else:
        raise HTTPException(status_code=400, detail="Unknown scenario name.")
    
    await broadcast_ws({"event": "SCENARIO_TRIGGERED", "scenario": req.scenario_name, "result": res})
    return res
