import asyncio
import random
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from backend.database import get_connection
from backend.lock_manager import LockManager, ResourceConflictException
from backend.anomaly_detector import AnomalyDetector
from backend.traceability import TraceabilityEngine

class FactorySimulator:
    def __init__(self, broadcast_callback=None):
        self.is_running = False
        self.simulation_speed = 1.0 # 1.0 = normal, 2.0 = fast
        self.broadcast_callback = broadcast_callback
        self._task = None
        self._drift_active = False
        self._drift_machine = "CNC-01"
        self._drift_step = 0

    def start(self):
        if not self.is_running:
            self.is_running = True
            self._task = asyncio.create_task(self._simulation_loop())

    def stop(self):
        self.is_running = False
        if self._task:
            self._task.cancel()

    async def _simulation_loop(self):
        while self.is_running:
            try:
                await self.tick()
                if self.broadcast_callback:
                    await self.broadcast_callback({"event": "FACTORY_TICK", "timestamp": datetime.now().isoformat()})
            except Exception as e:
                print(f"Error in simulation loop: {e}")
            await asyncio.sleep(2.0 / self.simulation_speed)

    async def tick(self):
        """
        Executes one production cycle simulation step across all active machines.
        """
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT m.id as machine_id, m.name as machine_name, m.status as machine_status,
                   m.temperature_c, m.vibration_mms, m.spindle_load_pct, m.target_cycle_time_sec,
                   pr.id as run_id, pr.order_number, pr.product_sku, pr.product_name,
                   pr.target_qty, pr.produced_qty, pr.scrap_qty, pr.required_material_lot_id,
                   pr.required_material_qty, pr.operator_id,
                   mat.material_code, mat.supplier_lot, mat.remaining_qty, mat.status as material_status
            FROM machines m
            JOIN production_runs pr ON m.current_run_id = pr.id
            LEFT JOIN materials mat ON pr.required_material_lot_id = mat.lot_id
            WHERE m.status = 'RUNNING' AND pr.status = 'RUNNING'
            """)
            active_runs = cursor.fetchall()

            for run in active_runs:
                mach_id = run["machine_id"]
                run_id = run["run_id"]
                lot_id = run["required_material_lot_id"]
                op_id = run["operator_id"]

                # 1. Check if material was suddenly placed ON HOLD mid-run (like in prompt!)
                if run["material_status"] == "ON_HOLD":
                    # Line must stop immediately!
                    cursor.execute("UPDATE machines SET status = 'BLOCKED' WHERE id = ?", (mach_id,))
                    cursor.execute("""
                    UPDATE production_runs 
                    SET status = 'BLOCKED', blocked_reason = 'Material Lot placed ON HOLD mid-production run' 
                    WHERE id = ?
                    """, (run_id,))
                    continue

                # 2. Simulate Telemetry
                if self._drift_active and mach_id == self._drift_machine:
                    self._drift_step += 1
                    sim_temp = run["temperature_c"] + 1.2
                    sim_vib = run["vibration_mms"] + 0.45
                    sim_load = min(98.0, run["spindle_load_pct"] + 2.5)
                else:
                    # Normal stable fluctuation
                    sim_temp = max(35.0, min(80.0, run["temperature_c"] + random.uniform(-0.4, 0.4)))
                    sim_vib = max(0.5, min(6.0, run["vibration_mms"] + random.uniform(-0.08, 0.08)))
                    sim_load = max(20.0, min(75.0, run["spindle_load_pct"] + random.uniform(-1.5, 1.5)))

                # Evaluate Anomaly Detector on machine telemetry
                cycle_time = run["target_cycle_time_sec"] + random.uniform(-0.5, 0.8)
                new_alerts = AnomalyDetector.evaluate_machine_telemetry(mach_id, sim_temp, sim_vib, sim_load, cycle_time)
                
                # Check for critical vibration excursion causing machine shutdown
                if sim_vib >= 6.5 or sim_temp >= 88.0:
                    cursor.execute("UPDATE machines SET status = 'WARNING' WHERE id = ?", (mach_id,))

                # 3. Simulate unit fabrication (every ~10% probability per tick or when cycle finishes)
                if random.random() < 0.85:
                    new_produced = run["produced_qty"] + 1
                    # Chance of defect (higher if vibration is high)
                    is_defect = (sim_vib > 3.8) or (random.random() < 0.02)
                    qc_status = "DEFECTIVE" if is_defect else "PASSED"
                    defect_code = "ERR-SURFACE-CHATTER" if is_defect else None
                    defect_desc = f"Spindle chatter mark detected during {mach_id} milling pass" if is_defect else None
                    defect_stage = "Stage 2 - Finish Pass" if is_defect else None

                    new_scrap = run["scrap_qty"] + (1 if is_defect else 0)

                    # Deduct raw material
                    new_mat_qty = max(0.0, (run["remaining_qty"] or 10.0) - (run["required_material_qty"] or 1.0))
                    cursor.execute("UPDATE materials SET remaining_qty = ? WHERE lot_id = ?", (new_mat_qty, lot_id))

                    # Insert serialized unit for digital thread
                    unit_serial = f"SN-{run['product_sku'].split('-')[-1]}-{int(datetime.now().timestamp() * 1000) % 1000000}"
                    cursor.execute("""
                    INSERT INTO serialized_units (
                        serial_number, run_id, order_number, product_sku, timestamp, machine_id, operator_id,
                        consumed_lot_id, consumed_lot_code, consumed_supplier_lot, cycle_time_sec,
                        telemetry_temp_c, telemetry_vib_mms, telemetry_spindle_load, qc_status,
                        defect_code, defect_description, defect_stage
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        unit_serial, run_id, run["order_number"], run["product_sku"],
                        datetime.now().isoformat(), mach_id, op_id,
                        lot_id, run["material_code"], run["supplier_lot"],
                        round(cycle_time, 2), round(sim_temp, 2), round(sim_vib, 2), round(sim_load, 1),
                        qc_status, defect_code, defect_desc, defect_stage
                    ))

                    # Update run completion
                    if new_produced >= run["target_qty"]:
                        LockManager.release_locks(run_id, "COMPLETED")
                    else:
                        cursor.execute("""
                        UPDATE production_runs 
                        SET produced_qty = ?, scrap_qty = ? 
                        WHERE id = ?
                        """, (new_produced, new_scrap, run_id))

            conn.commit()
        finally:
            conn.close()

    # ================= PRE-ENGINEERED SCENARIOS =================
    def trigger_prompt_freeze_scenario(self) -> Dict[str, Any]:
        """
        Executes the exact prompt context:
        1. Production line is running.
        2. A batch of material (LOT-RESIN-204) is put ON HOLD.
        3. Machine INJ-03 is ready, Operator OP-103 is waiting, Order WO-9013 is already overdue.
        4. Another production run (RUN-2026-004) tries to reserve the remaining material LOT-RESIN-204.
        5. System prevents double booking, logs collision, issues early warning, and traces the hold.
        """
        # Step A: Put LOT-RESIN-204 ON HOLD due to QA inspection alert
        hold_res = LockManager.set_material_hold(
            "LOT-RESIN-204", 
            "Supplier Quality Bulletin SQB-889: Catalyst viscosity deviation detected by QA Lab."
        )

        # Step B: Attempt to dispatch competing RUN-2026-004 using LOT-RESIN-204 on INJ-03
        collision_prevented = False
        collision_error = ""
        try:
            LockManager.allocate_and_lock(
                run_id="RUN-2026-004",
                machine_id="INJ-03",
                operator_id="OP-103",
                material_lot_id="LOT-RESIN-204",
                required_qty=1.0
            )
        except ResourceConflictException as ex:
            collision_prevented = True
            collision_error = str(ex)

        return {
            "scenario": "Prompt Scenario: Material Hold Freeze & Collision Prevention",
            "material_placed_on_hold": hold_res,
            "machine_status": "Machine INJ-03 is IDLE and ready.",
            "operator_status": "Operator OP-103 is WAITING.",
            "overdue_order": "WO-9013 (RUN-2026-003) is blocked and overdue.",
            "competing_run": "RUN-2026-004 attempted to reserve the on-hold material.",
            "collision_prevention_result": {
                "blocked": collision_prevented,
                "reason": collision_error,
                "outcome": "System prevented invalid reservation. Alternative recommended: LOT-RESIN-205 (Batch B)."
            }
        }

    def trigger_spindle_drift_scenario(self) -> Dict[str, Any]:
        """
        Activates progressive vibration and thermal drift on CNC-01 to demonstrate
        SPC Rule 3 early warning triggering before catastrophic line stop.
        """
        self._drift_active = True
        self._drift_machine = "CNC-01"
        self._drift_step = 0
        return {
            "scenario": "Predictive Early Warning: CNC-01 Spindle Drift Initiated",
            "target_machine": "CNC-01",
            "mechanism": "Incrementing vibration by +0.45 mm/s each cycle. Watch Early Warning Radar trigger alert within 5 cycles before threshold trip."
        }

    def trigger_genealogy_recall_scenario(self) -> Dict[str, Any]:
        """
        Simulates customer quality inquiry on SN-VALVE-2026-1017 and runs instant Root Cause Analysis.
        """
        rca = TraceabilityEngine.root_cause_investigation(target_serial="SN-VALVE-2026-1017")
        return {
            "scenario": "Genealogy & Root Cause Trace: Unit SN-VALVE-2026-1017",
            "unit_story": TraceabilityEngine.get_unit_story("SN-VALVE-2026-1017"),
            "root_cause_analysis": rca
        }

    def reset_factory(self) -> Dict[str, Any]:
        """
        Resets the factory state to initial clean baseline.
        """
        from backend.database import DB_PATH, init_db
        import os
        self._drift_active = False
        self._drift_step = 0
        conn = get_connection()
        conn.close()
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)
        init_db()
        return {"scenario": "Factory Reset", "status": "Clean baseline re-established"}
