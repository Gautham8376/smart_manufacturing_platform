import sqlite3
import json
import threading
from datetime import datetime
from typing import Tuple, Optional, Dict, Any
from backend.database import get_connection

# Re-entrant mutex for in-process memory barrier alongside DB transactions
_LOCK = threading.RLock()

class ResourceConflictException(Exception):
    def __init__(self, message: str, conflict_type: str, resource_id: str, conflicting_run_id: Optional[str] = None):
        super().__init__(message)
        self.conflict_type = conflict_type
        self.resource_id = resource_id
        self.conflicting_run_id = conflicting_run_id

class LockManager:
    @staticmethod
    def allocate_and_lock(run_id: str, machine_id: str, operator_id: str, material_lot_id: str, required_qty: float = 1.0) -> Dict[str, Any]:
        """
        Atomically allocates and locks machine, operator, and material batch.
        Prevents double-booking across runs with strict validation.
        """
        with _LOCK:
            conn = get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("BEGIN IMMEDIATE;")
                now_str = datetime.now().isoformat()

                # 0. Check production run
                cursor.execute("SELECT id, status, order_number FROM production_runs WHERE id = ?", (run_id,))
                run_row = cursor.fetchone()
                if not run_row:
                    raise ResourceConflictException(f"Production run '{run_id}' not found.", "RUN_NOT_FOUND", run_id)
                if run_row["status"] == "RUNNING":
                    raise ResourceConflictException(f"Production run '{run_id}' is already active.", "RUN_ALREADY_RUNNING", run_id)

                # 1. Check Machine
                cursor.execute("SELECT id, name, status, current_run_id FROM machines WHERE id = ?", (machine_id,))
                mach_row = cursor.fetchone()
                if not mach_row:
                    raise ResourceConflictException(f"Machine '{machine_id}' does not exist.", "MACHINE_NOT_FOUND", machine_id)
                if mach_row["status"] == "RUNNING" or mach_row["current_run_id"] is not None:
                    raise ResourceConflictException(
                        f"Machine '{mach_row['name']} ({machine_id})' is already double-booked by active run '{mach_row['current_run_id']}'.",
                        "MACHINE_DOUBLE_BOOKED",
                        machine_id,
                        mach_row["current_run_id"]
                    )
                if mach_row["status"] in ("BLOCKED", "MAINTENANCE", "CALIBRATION_DUE"):
                    raise ResourceConflictException(
                        f"Machine '{mach_row['name']} ({machine_id})' is currently {mach_row['status']} and cannot accept new jobs.",
                        "MACHINE_UNAVAILABLE",
                        machine_id
                    )

                # 2. Check Operator
                cursor.execute("SELECT id, name, status, active_machine_id, active_run_id, certified_operations, certification_expires FROM operators WHERE id = ?", (operator_id,))
                op_row = cursor.fetchone()
                if not op_row:
                    raise ResourceConflictException(f"Operator '{operator_id}' does not exist.", "OPERATOR_NOT_FOUND", operator_id)
                if op_row["status"] != "AVAILABLE" or op_row["active_run_id"] is not None:
                    raise ResourceConflictException(
                        f"Operator '{op_row['name']} ({operator_id})' is currently busy on Machine '{op_row['active_machine_id']}' for run '{op_row['active_run_id']}'.",
                        "OPERATOR_DOUBLE_BOOKED",
                        operator_id,
                        op_row["active_run_id"]
                    )
                
                # Check Operator Certifications
                cert_ops = json.loads(op_row["certified_operations"] or "[]")
                if machine_id not in cert_ops:
                    raise ResourceConflictException(
                        f"Operator '{op_row['name']} ({operator_id})' is NOT certified for Machine '{machine_id}'. Qualified on: {', '.join(cert_ops)}.",
                        "OPERATOR_NOT_CERTIFIED",
                        operator_id
                    )

                # 3. Check Material Lot
                cursor.execute("SELECT lot_id, name, remaining_qty, status, reserved_by_run_id, hold_reason, expiration_date FROM materials WHERE lot_id = ?", (material_lot_id,))
                mat_row = cursor.fetchone()
                if not mat_row:
                    raise ResourceConflictException(f"Material lot '{material_lot_id}' does not exist.", "MATERIAL_NOT_FOUND", material_lot_id)
                
                if mat_row["status"] == "ON_HOLD":
                    raise ResourceConflictException(
                        f"Cannot book Material Lot '{material_lot_id}' ({mat_row['name']}): Lot is ON HOLD! Reason: '{mat_row['hold_reason']}'.",
                        "MATERIAL_ON_HOLD",
                        material_lot_id
                    )
                if mat_row["status"] == "QUARANTINED":
                    raise ResourceConflictException(
                        f"Material Lot '{material_lot_id}' is QUARANTINED due to quality excursion.",
                        "MATERIAL_QUARANTINED",
                        material_lot_id
                    )
                if mat_row["status"] == "EXPIRED":
                    raise ResourceConflictException(
                        f"Material Lot '{material_lot_id}' has expired ({mat_row['expiration_date']}).",
                        "MATERIAL_EXPIRED",
                        material_lot_id
                    )
                if mat_row["reserved_by_run_id"] and mat_row["reserved_by_run_id"] != run_id:
                    raise ResourceConflictException(
                        f"Material Lot '{material_lot_id}' is already reserved by run '{mat_row['reserved_by_run_id']}'. Double-booking rejected.",
                        "MATERIAL_DOUBLE_BOOKED",
                        material_lot_id,
                        mat_row["reserved_by_run_id"]
                    )
                if mat_row["remaining_qty"] < required_qty:
                    raise ResourceConflictException(
                        f"Material Lot '{material_lot_id}' has insufficient remaining quantity ({mat_row['remaining_qty']} available, {required_qty} requested).",
                        "MATERIAL_INSUFFICIENT_QTY",
                        material_lot_id
                    )

                # --- ALL CHECKS PASSED: ACQUIRE LOCKS ATOMICALLY ---
                # Update Machine
                cursor.execute("""
                UPDATE machines 
                SET status = 'RUNNING', current_run_id = ?
                WHERE id = ?
                """, (run_id, machine_id))

                # Update Operator
                cursor.execute("""
                UPDATE operators 
                SET status = 'ASSIGNED', active_machine_id = ?, active_run_id = ?
                WHERE id = ?
                """, (machine_id, run_id, operator_id))

                # Update Material Lot
                cursor.execute("""
                UPDATE materials
                SET status = 'IN_USE', reserved_by_run_id = ?
                WHERE lot_id = ?
                """, (run_id, material_lot_id))

                # Update Production Run
                cursor.execute("""
                UPDATE production_runs
                SET status = 'RUNNING', machine_id = ?, operator_id = ?, required_material_lot_id = ?, 
                    required_material_qty = ?, start_time = COALESCE(start_time, ?), blocked_reason = NULL
                WHERE id = ?
                """, (machine_id, operator_id, material_lot_id, required_qty, now_str, run_id))

                # Record in Resource Locks audit log
                locks_data = [
                    ("MACHINE", machine_id, run_id, now_str, "HELD", f"Machine locked for Run {run_id}"),
                    ("OPERATOR", operator_id, run_id, now_str, "HELD", f"Operator assigned to Machine {machine_id}"),
                    ("MATERIAL", material_lot_id, run_id, now_str, "HELD", f"Material reserved ({required_qty} units)")
                ]
                cursor.executemany("""
                INSERT INTO resource_locks (resource_type, resource_id, run_id, acquired_at, lock_status, notes)
                VALUES (?, ?, ?, ?, ?, ?)
                """, locks_data)

                cursor.execute("COMMIT;")
                return {
                    "success": True,
                    "run_id": run_id,
                    "machine_id": machine_id,
                    "operator_id": operator_id,
                    "material_lot_id": material_lot_id,
                    "timestamp": now_str
                }
            except Exception as e:
                cursor.execute("ROLLBACK;")
                raise e
            finally:
                cursor.close()
                conn.close()

    @staticmethod
    def release_locks(run_id: str, new_status: str = "COMPLETED") -> Dict[str, Any]:
        """
        Safely releases all locks associated with a production run upon completion, pause, or abort.
        """
        with _LOCK:
            conn = get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("BEGIN IMMEDIATE;")
                now_str = datetime.now().isoformat()

                cursor.execute("""
                SELECT id, machine_id, operator_id, required_material_lot_id, required_material_qty, 
                       produced_qty, target_qty 
                FROM production_runs WHERE id = ?
                """, (run_id,))
                run_row = cursor.fetchone()
                if not run_row:
                    raise ValueError(f"Run '{run_id}' not found.")

                machine_id = run_row["machine_id"]
                operator_id = run_row["operator_id"]
                lot_id = run_row["required_material_lot_id"]

                # Release machine
                if machine_id:
                    cursor.execute("""
                    UPDATE machines 
                    SET status = 'IDLE', current_run_id = NULL 
                    WHERE id = ? AND current_run_id = ?
                    """, (machine_id, run_id))

                # Release operator
                if operator_id:
                    cursor.execute("""
                    UPDATE operators 
                    SET status = 'AVAILABLE', active_machine_id = NULL, active_run_id = NULL 
                    WHERE id = ? AND active_run_id = ?
                    """, (operator_id, run_id))

                # Release material lot
                if lot_id:
                    # Check remaining qty
                    cursor.execute("SELECT remaining_qty FROM materials WHERE lot_id = ?", (lot_id,))
                    mat_row = cursor.fetchone()
                    new_mat_status = 'DEPLETED' if mat_row and mat_row["remaining_qty"] <= 0 else 'AVAILABLE'
                    cursor.execute("""
                    UPDATE materials 
                    SET status = ?, reserved_by_run_id = NULL 
                    WHERE lot_id = ? AND reserved_by_run_id = ?
                    """, (new_mat_status, lot_id, run_id))

                # Update production run
                cursor.execute("""
                UPDATE production_runs 
                SET status = ?, end_time = ? 
                WHERE id = ?
                """, (new_status, now_str if new_status in ("COMPLETED", "ABORTED") else None, run_id))

                # Update lock log
                cursor.execute("""
                UPDATE resource_locks 
                SET lock_status = 'RELEASED', released_at = ? 
                WHERE run_id = ? AND lock_status = 'HELD'
                """, (now_str, run_id))

                cursor.execute("COMMIT;")
                return {
                    "success": True,
                    "run_id": run_id,
                    "released_machine": machine_id,
                    "released_operator": operator_id,
                    "released_material": lot_id,
                    "run_status": new_status
                }
            except Exception as e:
                cursor.execute("ROLLBACK;")
                raise e
            finally:
                cursor.close()
                conn.close()

    @staticmethod
    def set_material_hold(lot_id: str, hold_reason: str) -> Dict[str, Any]:
        """
        Immediately puts a material lot on hold.
        Detects any active or queued runs utilizing this material,
        blocks the active run, pauses the machine, and generates high-priority alerts.
        """
        with _LOCK:
            conn = get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("BEGIN IMMEDIATE;")
                now_str = datetime.now().isoformat()

                # Get material details
                cursor.execute("SELECT lot_id, name, status, reserved_by_run_id FROM materials WHERE lot_id = ?", (lot_id,))
                mat = cursor.fetchone()
                if not mat:
                    raise ValueError(f"Material lot '{lot_id}' not found.")

                cursor.execute("""
                UPDATE materials 
                SET status = 'ON_HOLD', hold_reason = ? 
                WHERE lot_id = ?
                """, (hold_reason, lot_id))

                # Check runs using this material
                cursor.execute("""
                SELECT id, order_number, status, machine_id, operator_id 
                FROM production_runs 
                WHERE required_material_lot_id = ? AND status IN ('RUNNING', 'SCHEDULED')
                """, (lot_id,))
                affected_runs = cursor.fetchall()

                blocked_run_ids = []
                for run in affected_runs:
                    r_id = run["id"]
                    blocked_run_ids.append(r_id)
                    # If the run was active, block it and block its machine
                    if run["status"] == "RUNNING":
                        cursor.execute("""
                        UPDATE production_runs 
                        SET status = 'BLOCKED', blocked_reason = ? 
                        WHERE id = ?
                        """, (f"CRITICAL: Material Lot {lot_id} was placed ON HOLD: {hold_reason}", r_id))

                        if run["machine_id"]:
                            cursor.execute("""
                            UPDATE machines 
                            SET status = 'BLOCKED' 
                            WHERE id = ?
                            """, (run["machine_id"],))

                # Insert alert
                alert_id = f"ALT-HOLD-{int(datetime.now().timestamp() * 1000)}"
                cursor.execute("""
                INSERT INTO alerts (id, timestamp, severity, source_type, source_id, title, message, recommended_action, status)
                VALUES (?, ?, 'CRITICAL', 'MATERIAL', ?, ?, ?, ?, 'ACTIVE')
                """, (
                    alert_id,
                    now_str,
                    lot_id,
                    f"Material Lot {lot_id} Placed ON HOLD",
                    f"Lot '{mat['name']}' ({lot_id}) put on hold. Reason: '{hold_reason}'. {len(blocked_run_ids)} run(s) affected: {', '.join(blocked_run_ids) or 'None'}.",
                    f"Halt consumption immediately. Quarantine downstream parts and reallocate scheduled runs to alternate lots (e.g. LOT-RESIN-205)."
                ))

                cursor.execute("COMMIT;")
                return {
                    "success": True,
                    "lot_id": lot_id,
                    "hold_reason": hold_reason,
                    "affected_runs": blocked_run_ids,
                    "alert_id": alert_id
                }
            except Exception as e:
                cursor.execute("ROLLBACK;")
                raise e
            finally:
                cursor.close()
                conn.close()

    @staticmethod
    def release_material_hold(lot_id: str) -> Dict[str, Any]:
        """
        Releases hold on a material lot after QA verification.
        """
        with _LOCK:
            conn = get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("BEGIN IMMEDIATE;")
                now_str = datetime.now().isoformat()

                cursor.execute("SELECT lot_id, status FROM materials WHERE lot_id = ?", (lot_id,))
                mat = cursor.fetchone()
                if not mat:
                    raise ValueError(f"Material lot '{lot_id}' not found.")

                cursor.execute("""
                UPDATE materials 
                SET status = 'AVAILABLE', hold_reason = NULL 
                WHERE lot_id = ?
                """, (lot_id,))

                # Resolve active hold alerts for this lot
                cursor.execute("""
                UPDATE alerts 
                SET status = 'RESOLVED', resolved_at = ? 
                WHERE source_id = ? AND source_type = 'MATERIAL' AND status = 'ACTIVE'
                """, (now_str, lot_id))

                cursor.execute("COMMIT;")
                return {"success": True, "lot_id": lot_id, "status": "AVAILABLE"}
            except Exception as e:
                cursor.execute("ROLLBACK;")
                raise e
            finally:
                cursor.close()
                conn.close()
