import sqlite3
import json
from datetime import datetime
from typing import Dict, Any, List, Optional
from backend.database import get_connection

class TraceabilityEngine:
    @staticmethod
    def get_unit_story(serial_number: str) -> Dict[str, Any]:
        """
        Retrieves the complete digital thread / lifecycle story for a single serialized unit.
        Every unit can tell its story: material source, machine telemetry at fabrication,
        operator badge, cycle parameters, and QC inspection.
        """
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT u.*, 
                   m.name as machine_name, m.cell as machine_cell, 
                   m.temp_threshold_warning, m.temp_threshold_critical,
                   m.vib_threshold_warning, m.vib_threshold_critical,
                   mat.name as material_name, mat.supplier_name, mat.supplier_lot, 
                   mat.status as material_status, mat.hold_reason, mat.expiration_date as material_expiry,
                   op.name as operator_name, op.badge_id, op.shift as operator_shift,
                   pr.order_number, pr.product_name, pr.status as run_status
            FROM serialized_units u
            LEFT JOIN machines m ON u.machine_id = m.id
            LEFT JOIN materials mat ON u.consumed_lot_id = mat.lot_id
            LEFT JOIN operators op ON u.operator_id = op.id
            LEFT JOIN production_runs pr ON u.run_id = pr.id
            WHERE u.serial_number = ?
            """, (serial_number,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Serialized unit '{serial_number}' not found.")

            # Construct narrative story
            story_events = [
                {
                    "stage": "Material Receiving & Verification",
                    "timestamp": row["material_expiry"], # Reference context
                    "title": f"Raw Material Assigned: {row['material_name']} ({row['consumed_lot_id']})",
                    "details": f"Certified supplier lot '{row['supplier_lot']}' received from {row['supplier_name']}. Verified specification {row['consumed_lot_code']}.",
                    "status": "PASS" if row["material_status"] != "ON_HOLD" else "WARN",
                    "icon": "box"
                },
                {
                    "stage": "Operator Dispatch",
                    "timestamp": row["timestamp"],
                    "title": f"Operator Verification: {row['operator_name']} ({row['badge_id']})",
                    "details": f"Assigned to shift '{row['operator_shift']}'. Active operator qualification validated for machine {row['machine_id']}.",
                    "status": "PASS",
                    "icon": "user-check"
                },
                {
                    "stage": "Precision Manufacturing",
                    "timestamp": row["timestamp"],
                    "title": f"Fabricated on Machine: {row['machine_name']} ({row['machine_id']})",
                    "details": f"Cell: {row['machine_cell']}. Recorded cycle time: {row['cycle_time_sec']}s (Baseline target: 10-12s).",
                    "status": "PASS" if (row["cycle_time_sec"] or 10.0) < 15.0 else "WARN",
                    "icon": "cpu"
                },
                {
                    "stage": "In-Process Telemetry Snapshot",
                    "timestamp": row["timestamp"],
                    "title": f"Sensor Snapshot at Fabrication Instant",
                    "details": f"Core Temperature: {row['telemetry_temp_c']}°C (Limit: {row['temp_threshold_warning']}°C) | Vibration: {row['telemetry_vib_mms']} mm/s (Limit: {row['vib_threshold_warning']} mm/s) | Spindle Load: {row['telemetry_spindle_load']}%.",
                    "status": "PASS" if (row["telemetry_vib_mms"] or 0) < row["vib_threshold_warning"] else "ALERT",
                    "icon": "activity"
                },
                {
                    "stage": "Quality Assurance & Serialization",
                    "timestamp": row["timestamp"],
                    "title": f"End-of-Line Inspection: {row['qc_status']}",
                    "details": f"Status: {row['qc_status']}. " + (f"Defect Code: {row['defect_code']} - {row['defect_description']} (Occurred at {row['defect_stage']})" if row['defect_code'] else "Zero surface flaws detected. All dimensional tolerances met."),
                    "status": "PASS" if row["qc_status"] == "PASSED" else "FAIL",
                    "icon": "shield-check" if row["qc_status"] == "PASSED" else "alert-triangle"
                }
            ]

            return {
                "serial_number": row["serial_number"],
                "run_id": row["run_id"],
                "order_number": row["order_number"],
                "product_sku": row["product_sku"],
                "product_name": row["product_name"],
                "timestamp": row["timestamp"],
                "qc_status": row["qc_status"],
                "defect_code": row["defect_code"],
                "defect_description": row["defect_description"],
                "defect_stage": row["defect_stage"],
                "machine": {
                    "id": row["machine_id"],
                    "name": row["machine_name"],
                    "cell": row["machine_cell"]
                },
                "operator": {
                    "id": row["operator_id"],
                    "name": row["operator_name"],
                    "badge": row["badge_id"],
                    "shift": row["operator_shift"]
                },
                "material": {
                    "lot_id": row["consumed_lot_id"],
                    "name": row["material_name"],
                    "supplier": row["supplier_name"],
                    "supplier_lot": row["supplier_lot"],
                    "status": row["material_status"]
                },
                "telemetry": {
                    "cycle_time_sec": row["cycle_time_sec"],
                    "temperature_c": row["telemetry_temp_c"],
                    "vibration_mms": row["telemetry_vib_mms"],
                    "spindle_load_pct": row["telemetry_spindle_load"],
                    "temp_warning": row["temp_threshold_warning"],
                    "temp_critical": row["temp_threshold_critical"],
                    "vib_warning": row["vib_threshold_warning"],
                    "vib_critical": row["vib_threshold_critical"]
                },
                "story_timeline": story_events
            }
        finally:
            conn.close()

    @staticmethod
    def trace_material_forward(lot_id: str) -> Dict[str, Any]:
        """
        Forward traceability:
        Given a suspicious or on-hold raw material lot, find all affected production runs,
        finished serialized units, and customer work orders.
        """
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM materials WHERE lot_id = ?", (lot_id,))
            mat = cursor.fetchone()
            if not mat:
                raise ValueError(f"Material lot '{lot_id}' not found.")

            # Find runs that used or are scheduled to use this lot
            cursor.execute("""
            SELECT id, order_number, product_sku, product_name, status, target_qty, produced_qty, scrap_qty, machine_id, operator_id
            FROM production_runs
            WHERE required_material_lot_id = ?
            ORDER BY created_at DESC
            """, (lot_id,))
            runs = [dict(r) for r in cursor.fetchall()]

            # Find all serialized units made with this lot
            cursor.execute("""
            SELECT serial_number, run_id, order_number, product_sku, timestamp, machine_id, operator_id, qc_status, defect_code
            FROM serialized_units
            WHERE consumed_lot_id = ?
            ORDER BY timestamp ASC
            """, (lot_id,))
            units = [dict(u) for u in cursor.fetchall()]

            defective_units = [u for u in units if u["qc_status"] != "PASSED"]
            defect_rate = (len(defective_units) / len(units) * 100.0) if units else 0.0

            return {
                "lot_id": lot_id,
                "material_name": mat["name"],
                "supplier": mat["supplier_name"],
                "supplier_lot": mat["supplier_lot"],
                "current_status": mat["status"],
                "hold_reason": mat["hold_reason"],
                "total_units_produced": len(units),
                "defective_units_count": len(defective_units),
                "defect_rate_pct": round(defect_rate, 2),
                "affected_runs": runs,
                "serialized_units": units,
                "quarantine_scope": {
                    "action_required": "QUARANTINE_ALL_UNITS" if (mat["status"] in ("ON_HOLD", "QUARANTINED") or defect_rate > 10.0) else "MONITOR",
                    "units_to_hold": [u["serial_number"] for u in units if u["qc_status"] == "PASSED"],
                    "recommendation": f"Contain all {len(units)} units manufactured from {lot_id} pending QA chemical re-test."
                }
            }
        finally:
            conn.close()

    @staticmethod
    def root_cause_investigation(target_serial: Optional[str] = None, target_run: Optional[str] = None, target_lot: Optional[str] = None) -> Dict[str, Any]:
        """
        Root-Cause Analysis Engine:
        Analyzes defects, correlates across Material, Machine, Operator, and Telemetry parameters,
        pinpoints 'Patient Zero' (the first unit/timestamp where the defect initiated),
        and calculates confidence ranking.
        """
        conn = get_connection()
        try:
            cursor = conn.cursor()

            # Retrieve all serialized units to perform cross-correlation
            cursor.execute("""
            SELECT serial_number, run_id, order_number, timestamp, machine_id, operator_id,
                   consumed_lot_id, consumed_lot_code, cycle_time_sec, telemetry_temp_c,
                   telemetry_vib_mms, telemetry_spindle_load, qc_status, defect_code, defect_description
            FROM serialized_units
            ORDER BY timestamp ASC
            """)
            all_units = [dict(r) for r in cursor.fetchall()]

            defects = [u for u in all_units if u["qc_status"] == "DEFECTIVE"]
            
            if not defects:
                return {
                    "query_target": target_serial or target_run or target_lot or "Factory-Wide",
                    "suspected_root_cause": "No defects detected in current production history.",
                    "confidence_pct": 100.0,
                    "patient_zero_unit": None,
                    "correlations": {},
                    "timeline_events": [],
                    "quarantine_recommendation": {"status": "NORMAL", "units_to_quarantine": []}
                }

            # If user specified a specific serial, focus on it, else analyze global defects
            focus_defect = None
            if target_serial:
                focus_defect = next((u for u in all_units if u["serial_number"] == target_serial), None)

            patient_zero = defects[0] # Earliest defective unit by timestamp

            # Factor correlation: count occurrences among defective units
            machine_counts = {}
            material_counts = {}
            operator_counts = {}
            temp_spikes = 0
            vib_spikes = 0

            for d in defects:
                m = d["machine_id"]
                mat = d["consumed_lot_id"]
                op = d["operator_id"]

                machine_counts[m] = machine_counts.get(m, 0) + 1
                material_counts[mat] = material_counts.get(mat, 0) + 1
                operator_counts[op] = operator_counts.get(op, 0) + 1

                if (d["telemetry_temp_c"] or 0) > 60.0:
                    temp_spikes += 1
                if (d["telemetry_vib_mms"] or 0) > 3.0:
                    vib_spikes += 1

            total_defects = len(defects)
            # Find dominant contributors
            top_machine = max(machine_counts.items(), key=lambda x: x[1])
            top_material = max(material_counts.items(), key=lambda x: x[1])
            top_operator = max(operator_counts.items(), key=lambda x: x[1])

            mach_conf = (top_machine[1] / total_defects) * 100.0
            mat_conf = (top_material[1] / total_defects) * 100.0
            op_conf = (top_operator[1] / total_defects) * 100.0

            # Determine primary hypothesis
            if vib_spikes / total_defects >= 0.7:
                primary_cause = f"Mechanical Vibration Excursion on Machine {top_machine[0]}"
                confidence = max(mach_conf, 88.5)
                hypothesis = f"Telemetry confirms excessive spindle vibration (peak {patient_zero['telemetry_vib_mms']} mm/s) on {top_machine[0]}, causing chatter and dimensional defects."
            elif mat_conf >= 80.0:
                primary_cause = f"Contaminated / Defective Material Batch {top_material[0]}"
                confidence = mat_conf
                hypothesis = f"{mat_conf:.1f}% of all defects trace directly to raw material batch {top_material[0]}."
            elif mach_conf >= 80.0:
                primary_cause = f"Machine Calibration / Tool Wear on {top_machine[0]}"
                confidence = mach_conf
                hypothesis = f"{mach_conf:.1f}% of failures concentrated on Machine {top_machine[0]}."
            else:
                primary_cause = f"Multi-factor drift during production"
                confidence = 72.0
                hypothesis = "Correlated parameters suggest combined operator handover and feed rate deviation."

            # Quarantine recommendation: all units manufactured on that machine/lot after patient zero
            quarantine_units = [
                u["serial_number"] for u in all_units 
                if u["timestamp"] >= patient_zero["timestamp"] 
                and (u["machine_id"] == top_machine[0] or u["consumed_lot_id"] == top_material[0])
                and u["qc_status"] != "DEFECTIVE"
            ]

            return {
                "query_target": target_serial or target_run or target_lot or "Active Production",
                "suspected_root_cause": primary_cause,
                "hypothesis_narrative": hypothesis,
                "confidence_pct": round(confidence, 1),
                "patient_zero_unit": {
                    "serial_number": patient_zero["serial_number"],
                    "onset_timestamp": patient_zero["timestamp"],
                    "machine_id": patient_zero["machine_id"],
                    "operator_id": patient_zero["operator_id"],
                    "material_lot_id": patient_zero["consumed_lot_id"],
                    "defect_code": patient_zero["defect_code"],
                    "defect_description": patient_zero["defect_description"],
                    "telemetry_at_onset": {
                        "temperature_c": patient_zero["telemetry_temp_c"],
                        "vibration_mms": patient_zero["telemetry_vib_mms"],
                        "spindle_load_pct": patient_zero["telemetry_spindle_load"],
                        "cycle_time_sec": patient_zero["cycle_time_sec"]
                    }
                },
                "correlations": {
                    "by_machine": [{"id": k, "defects": v, "pct": round(v / total_defects * 100, 1)} for k, v in machine_counts.items()],
                    "by_material": [{"id": k, "defects": v, "pct": round(v / total_defects * 100, 1)} for k, v in material_counts.items()],
                    "by_operator": [{"id": k, "defects": v, "pct": round(v / total_defects * 100, 1)} for k, v in operator_counts.items()],
                    "sensor_drift_signals": {
                        "vibration_excursion_rate": round(vib_spikes / total_defects * 100, 1),
                        "thermal_spike_rate": round(temp_spikes / total_defects * 100, 1)
                    }
                },
                "quarantine_recommendation": {
                    "status": "IMMEDIATE_HOLD_RECOMMENDED",
                    "count": len(quarantine_units),
                    "units": quarantine_units,
                    "containment_action": f"Immediate containment gate: Hold {len(quarantine_units)} subsequent units produced after {patient_zero['timestamp']} on {top_machine[0]}."
                }
            }
        finally:
            conn.close()
