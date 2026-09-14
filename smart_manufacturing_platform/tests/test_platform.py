import unittest
import os
import json
from datetime import datetime

from backend.database import init_db, get_connection, DB_PATH
from backend.lock_manager import LockManager, ResourceConflictException
from backend.traceability import TraceabilityEngine
from backend.anomaly_detector import AnomalyDetector

class SmartManufacturingPlatformTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Reset and initialize fresh DB
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)
        init_db()

    def test_01_prevent_machine_double_booking(self):
        """
        Verify that a machine currently running a job cannot be booked by another run.
        """
        # CNC-01 is seeded as RUNNING for RUN-2026-001
        with self.assertRaises(ResourceConflictException) as ctx:
            LockManager.allocate_and_lock(
                run_id="RUN-2026-003",
                machine_id="CNC-01",
                operator_id="OP-103",
                material_lot_id="LOT-RESIN-205"
            )
        self.assertEqual(ctx.exception.conflict_type, "MACHINE_DOUBLE_BOOKED")
        self.assertIn("already double-booked", str(ctx.exception))

    def test_02_prevent_operator_double_booking(self):
        """
        Verify that an operator currently assigned cannot be double-booked to another machine.
        """
        # OP-101 is seeded as ASSIGNED to CNC-01
        with self.assertRaises(ResourceConflictException) as ctx:
            LockManager.allocate_and_lock(
                run_id="RUN-2026-003",
                machine_id="LSW-04",
                operator_id="OP-101",
                material_lot_id="LOT-RESIN-205"
            )
        self.assertEqual(ctx.exception.conflict_type, "OPERATOR_DOUBLE_BOOKED")
        self.assertIn("busy on Machine", str(ctx.exception))

    def test_03_prevent_material_on_hold_booking(self):
        """
        Verify that a material lot on hold immediately blocks booking and triggers alert.
        """
        # Put LOT-RESIN-204 ON HOLD
        hold_result = LockManager.set_material_hold(
            "LOT-RESIN-204", 
            "Incoming quality check: viscosity index out of spec"
        )
        self.assertTrue(hold_result["success"])

        # Attempt to allocate LOT-RESIN-204
        with self.assertRaises(ResourceConflictException) as ctx:
            LockManager.allocate_and_lock(
                run_id="RUN-2026-003",
                machine_id="INJ-03",
                operator_id="OP-103",
                material_lot_id="LOT-RESIN-204"
            )
        self.assertEqual(ctx.exception.conflict_type, "MATERIAL_ON_HOLD")
        self.assertIn("Lot is ON HOLD", str(ctx.exception))

    def test_04_successful_atomic_allocation_and_release(self):
        """
        Verify valid resource allocation succeeds atomically and releases cleanly.
        """
        # INJ-03 is IDLE, OP-103 is AVAILABLE, LOT-RESIN-205 is AVAILABLE
        alloc_res = LockManager.allocate_and_lock(
            run_id="RUN-2026-003",
            machine_id="INJ-03",
            operator_id="OP-103",
            material_lot_id="LOT-RESIN-205",
            required_qty=2.0
        )
        self.assertTrue(alloc_res["success"])

        # Verify DB states
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT status, current_run_id FROM machines WHERE id = 'INJ-03'")
        mach = cursor.fetchone()
        self.assertEqual(mach["status"], "RUNNING")
        self.assertEqual(mach["current_run_id"], "RUN-2026-003")

        cursor.execute("SELECT status, active_run_id FROM operators WHERE id = 'OP-103'")
        op = cursor.fetchone()
        self.assertEqual(op["status"], "ASSIGNED")

        cursor.execute("SELECT status, reserved_by_run_id FROM materials WHERE lot_id = 'LOT-RESIN-205'")
        mat = cursor.fetchone()
        self.assertEqual(mat["status"], "IN_USE")
        self.assertEqual(mat["reserved_by_run_id"], "RUN-2026-003")
        conn.close()

        # Now release
        rel_res = LockManager.release_locks("RUN-2026-003", "COMPLETED")
        self.assertTrue(rel_res["success"])

        # Verify release states
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT status, current_run_id FROM machines WHERE id = 'INJ-03'")
        mach = cursor.fetchone()
        self.assertEqual(mach["status"], "IDLE")
        self.assertIsNone(mach["current_run_id"])
        conn.close()

    def test_05_digital_thread_unit_story(self):
        """
        Verify that a serialized unit can tell its complete lifecycle story.
        """
        story = TraceabilityEngine.get_unit_story("SN-VALVE-2026-1017")
        self.assertEqual(story["serial_number"], "SN-VALVE-2026-1017")
        self.assertEqual(story["qc_status"], "DEFECTIVE")
        self.assertEqual(story["defect_code"], "ERR-CHIP-BURR")
        self.assertEqual(story["machine"]["id"], "CNC-01")
        self.assertEqual(story["operator"]["id"], "OP-101")
        self.assertEqual(story["material"]["lot_id"], "LOT-ALU-101")
        self.assertGreater(len(story["story_timeline"]), 3)

    def test_06_forward_traceability(self):
        """
        Verify forward traceability from material lot to all manufactured serialized units.
        """
        trace = TraceabilityEngine.trace_material_forward("LOT-ALU-101")
        self.assertEqual(trace["lot_id"], "LOT-ALU-101")
        self.assertGreater(trace["total_units_produced"], 20)
        self.assertIn("SN-VALVE-2026-1017", [u["serial_number"] for u in trace["serialized_units"]])
        self.assertIn("quarantine_scope", trace)

    def test_07_root_cause_analysis_patient_zero(self):
        """
        Verify root-cause analysis identifies Patient Zero and factors with confidence.
        """
        rca = TraceabilityEngine.root_cause_investigation()
        self.assertIsNotNone(rca["patient_zero_unit"])
        self.assertEqual(rca["patient_zero_unit"]["serial_number"], "SN-VALVE-2026-1017")
        self.assertEqual(rca["patient_zero_unit"]["machine_id"], "CNC-01")
        self.assertGreater(rca["confidence_pct"], 70.0)

    def test_08_predictive_spc_drift_detection(self):
        """
        Verify SPC drift rule surfaces a developing vibration problem before trip limit.
        """
        # Feed 6 consecutive increasing vibration values strictly below warning threshold (4.0)
        vibrations = [1.2, 1.45, 1.70, 1.95, 2.20, 2.45, 2.70]
        alerts = []
        for v in vibrations:
            a = AnomalyDetector.evaluate_machine_telemetry("LSW-04", 40.0, v, 30.0, 6.5)
            if a:
                alerts.extend(a)

        # Check if predictive drift alert was generated
        drift_alerts = [al for al in alerts if "ALT-SPC-DRIFT" in al["id"]]
        self.assertGreater(len(drift_alerts), 0)
        self.assertIn("Predictive Warning", drift_alerts[0]["title"])

if __name__ == "__main__":
    unittest.main()
