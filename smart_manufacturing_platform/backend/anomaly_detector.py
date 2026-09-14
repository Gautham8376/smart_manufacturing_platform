import sqlite3
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from backend.database import get_connection

class AnomalyDetector:
    @staticmethod
    def evaluate_machine_telemetry(machine_id: str, current_temp: float, current_vib: float, current_load: float, cycle_time: Optional[float] = None) -> List[Dict[str, Any]]:
        """
        Runs Statistical Process Control (SPC) and trend slope detection on machine telemetry.
        Surfaces developing problems before an emergency shutdown occurs.
        """
        conn = get_connection()
        alerts_generated = []
        try:
            cursor = conn.cursor()
            now_str = datetime.now().isoformat()

            # Retrieve machine thresholds
            cursor.execute("""
            SELECT name, status, target_cycle_time_sec, temp_threshold_warning, temp_threshold_critical,
                   vib_threshold_warning, vib_threshold_critical
            FROM machines WHERE id = ?
            """, (machine_id,))
            mach = cursor.fetchone()
            if not mach:
                return []

            # Retrieve last 20 telemetry readings for this machine
            cursor.execute("""
            SELECT temperature_c, vibration_mms, spindle_load_pct, cycle_time_sec
            FROM telemetry_history
            WHERE machine_id = ?
            ORDER BY id DESC
            LIMIT 20
            """, (machine_id,))
            history = cursor.fetchall()

            # Record the new reading into telemetry_history
            cursor.execute("""
            INSERT INTO telemetry_history (machine_id, timestamp, temperature_c, vibration_mms, spindle_load_pct, cycle_time_sec)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (machine_id, now_str, current_temp, current_vib, current_load, cycle_time or mach["target_cycle_time_sec"]))

            # Update machine current telemetry
            cursor.execute("""
            UPDATE machines 
            SET temperature_c = ?, vibration_mms = ?, spindle_load_pct = ? 
            WHERE id = ?
            """, (current_temp, current_vib, current_load, machine_id))

            # 1. IMMEDIATE THRESHOLD CHECKS
            if current_vib >= mach["vib_threshold_critical"]:
                alert = {
                    "id": f"ALT-VIB-CRIT-{int(datetime.now().timestamp() * 1000)}",
                    "severity": "CRITICAL",
                    "source_type": "MACHINE",
                    "source_id": machine_id,
                    "title": f"Spindle Vibration Trip on {mach['name']}",
                    "message": f"Critical vibration level {current_vib:.2f} mm/s exceeds absolute threshold {mach['vib_threshold_critical']} mm/s. Tool breakage imminent.",
                    "recommended_action": "Safely halt spindle, inspect cutter insert for chipping, and verify workpiece clamping."
                }
                alerts_generated.append(alert)
            elif current_vib >= mach["vib_threshold_warning"]:
                alert = {
                    "id": f"ALT-VIB-WARN-{int(datetime.now().timestamp() * 1000)}",
                    "severity": "WARNING",
                    "source_type": "MACHINE",
                    "source_id": machine_id,
                    "title": f"Elevated Vibration on {mach['name']}",
                    "message": f"Vibration level {current_vib:.2f} mm/s exceeds warning limit {mach['vib_threshold_warning']} mm/s.",
                    "recommended_action": "Reduce axis feed rate by 20% and schedule cutter inspection at end of current cycle."
                }
                alerts_generated.append(alert)

            if current_temp >= mach["temp_threshold_critical"]:
                alert = {
                    "id": f"ALT-TEMP-CRIT-{int(datetime.now().timestamp() * 1000)}",
                    "severity": "CRITICAL",
                    "source_type": "MACHINE",
                    "source_id": machine_id,
                    "title": f"Bearing Overheat on {mach['name']}",
                    "message": f"Temperature {current_temp:.1f}°C exceeded critical shutdown limit {mach['temp_threshold_critical']}°C.",
                    "recommended_action": "Emergency spindle cool-down. Check coolant flow and spindle lubrication pressure."
                }
                alerts_generated.append(alert)
            elif current_temp >= mach["temp_threshold_warning"]:
                alert = {
                    "id": f"ALT-TEMP-WARN-{int(datetime.now().timestamp() * 1000)}",
                    "severity": "WARNING",
                    "source_type": "MACHINE",
                    "source_id": machine_id,
                    "title": f"Thermal Warning on {mach['name']}",
                    "message": f"Temperature {current_temp:.1f}°C is in warning range [{mach['temp_threshold_warning']}°C - {mach['temp_threshold_critical']}°C].",
                    "recommended_action": "Verify coolant spray nozzle alignment and check filter differential pressure."
                }
                alerts_generated.append(alert)

            # 2. PREDICTIVE DRIFT & TREND ANALYSIS (Western Electric Rules)
            if len(history) >= 5:
                # history is ORDER BY id DESC, so reverse to chronological order
                past_vibs = [r["vibration_mms"] for r in reversed(history[:5])]
                past_temps = [r["temperature_c"] for r in reversed(history[:5])]
                vibs = past_vibs + [current_vib]
                temps = past_temps + [current_temp]

                # Check for strictly increasing trend across consecutive points (thermal or vibration drift)
                is_vib_drifting_up = all(vibs[i] < vibs[i+1] for i in range(len(vibs)-1))
                is_temp_drifting_up = all(temps[i] < temps[i+1] for i in range(len(temps)-1))

                if is_vib_drifting_up:
                    # Surface proactive alert before or as it reaches warning
                    alert = {
                        "id": f"ALT-SPC-DRIFT-VIB-{int(datetime.now().timestamp() * 1000)}",
                        "severity": "WARNING",
                        "source_type": "MACHINE",
                        "source_id": machine_id,
                        "title": f"Predictive Warning: Vibration Drift on {mach['name']}",
                        "message": f"SPC Rule Alert: Vibration has monotonically increased for {len(vibs)} consecutive cycles (+{(current_vib - vibs[0]):.2f} mm/s drift). Predicted warning breach imminent.",
                        "recommended_action": "Proactive tool wear inspection before quality degradation occurs."
                    }
                    alerts_generated.append(alert)

                if is_temp_drifting_up:
                    alert = {
                        "id": f"ALT-SPC-DRIFT-TEMP-{int(datetime.now().timestamp() * 1000)}",
                        "severity": "WARNING",
                        "source_type": "MACHINE",
                        "source_id": machine_id,
                        "title": f"Predictive Warning: Thermal Runaway Slope on {mach['name']}",
                        "message": f"Thermal gradient detected: steady temperature climb across {len(temps)} sample intervals (+{(current_temp - temps[0]):.1f}°C).",
                        "recommended_action": "Top off spindle coolant reservoir before line stops."
                    }
                    alerts_generated.append(alert)

            # 3. CYCLE TIME CREEP (Bottleneck early-warning)
            if cycle_time and mach["target_cycle_time_sec"]:
                creep_pct = ((cycle_time - mach["target_cycle_time_sec"]) / mach["target_cycle_time_sec"]) * 100.0
                if creep_pct >= 25.0:
                    alert = {
                        "id": f"ALT-CYCLE-CREEP-{int(datetime.now().timestamp() * 1000)}",
                        "severity": "WARNING",
                        "source_type": "MACHINE",
                        "source_id": machine_id,
                        "title": f"Cycle Time Creep (+{creep_pct:.1f}%) on {mach['name']}",
                        "message": f"Actual cycle time {cycle_time:.1f}s is lagging target {mach['target_cycle_time_sec']}s. Downstream starving risk.",
                        "recommended_action": "Check operator ergonomic assist or robotic unloader feed delay."
                    }
                    alerts_generated.append(alert)

            # Persist newly generated alerts
            for a in alerts_generated:
                cursor.execute("""
                INSERT OR IGNORE INTO alerts (id, timestamp, severity, source_type, source_id, title, message, recommended_action, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE')
                """, (a["id"], now_str, a["severity"], a["source_type"], a["source_id"], a["title"], a["message"], a["recommended_action"]))

            conn.commit()
            return alerts_generated
        finally:
            conn.close()

    @staticmethod
    def check_material_shelf_life() -> List[Dict[str, Any]]:
        """
        Inspects material lots approaching expiration or expiry dates.
        """
        conn = get_connection()
        alerts = []
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT lot_id, name, remaining_qty, expiration_date, status FROM materials WHERE status IN ('AVAILABLE', 'IN_USE')")
            materials = cursor.fetchall()
            now = datetime.now()

            for mat in materials:
                try:
                    exp_date = datetime.fromisoformat(mat["expiration_date"])
                    days_remaining = (exp_date - now).total_seconds() / 86400.0
                    if days_remaining <= 2.0:
                        alert = {
                            "id": f"ALT-EXP-{mat['lot_id']}",
                            "timestamp": now.isoformat(),
                            "severity": "WARNING" if days_remaining > 0 else "CRITICAL",
                            "source_type": "MATERIAL",
                            "source_id": mat["lot_id"],
                            "title": f"Material Expiration Warning: {mat['lot_id']}",
                            "message": f"Lot '{mat['name']}' expires in {max(0, days_remaining):.1f} days ({mat['remaining_qty']} units remain).",
                            "recommended_action": "Prioritize consumption in current shift or perform QA recertification test."
                        }
                        cursor.execute("""
                        INSERT OR IGNORE INTO alerts (id, timestamp, severity, source_type, source_id, title, message, recommended_action, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE')
                        """, (alert["id"], alert["timestamp"], alert["severity"], alert["source_type"], alert["source_id"], alert["title"], alert["message"], alert["recommended_action"]))
                        alerts.append(alert)
                except Exception:
                    pass

            conn.commit()
            return alerts
        finally:
            conn.close()
