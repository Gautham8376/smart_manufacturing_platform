import sqlite3
import json
from datetime import datetime, timedelta
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "factory.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=20.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. Machines
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS machines (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        cell TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('IDLE', 'RUNNING', 'WARNING', 'BLOCKED', 'MAINTENANCE', 'CALIBRATION_DUE')),
        current_run_id TEXT,
        target_cycle_time_sec REAL DEFAULT 10.0,
        last_maintenance TEXT,
        temperature_c REAL DEFAULT 45.0,
        vibration_mms REAL DEFAULT 1.2,
        spindle_load_pct REAL DEFAULT 42.0,
        temp_threshold_warning REAL DEFAULT 75.0,
        temp_threshold_critical REAL DEFAULT 88.0,
        vib_threshold_warning REAL DEFAULT 4.0,
        vib_threshold_critical REAL DEFAULT 6.5
    );
    """)

    # 2. Materials
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS materials (
        lot_id TEXT PRIMARY KEY,
        material_code TEXT NOT NULL,
        name TEXT NOT NULL,
        supplier_name TEXT NOT NULL,
        supplier_lot TEXT NOT NULL,
        initial_qty REAL NOT NULL,
        remaining_qty REAL NOT NULL,
        unit_of_measure TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('AVAILABLE', 'RESERVED', 'IN_USE', 'ON_HOLD', 'QUARANTINED', 'EXPIRED', 'DEPLETED')),
        reserved_by_run_id TEXT,
        hold_reason TEXT,
        expiration_date TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """)

    # 3. Operators
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS operators (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        badge_id TEXT NOT NULL UNIQUE,
        shift TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('AVAILABLE', 'ASSIGNED', 'ON_BREAK', 'OFFLINE')),
        active_machine_id TEXT,
        active_run_id TEXT,
        certified_operations TEXT NOT NULL, -- JSON array
        certification_expires TEXT NOT NULL
    );
    """)

    # 4. Production Runs
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS production_runs (
        id TEXT PRIMARY KEY,
        order_number TEXT NOT NULL,
        product_sku TEXT NOT NULL,
        product_name TEXT NOT NULL,
        target_qty INTEGER NOT NULL,
        produced_qty INTEGER DEFAULT 0,
        scrap_qty INTEGER DEFAULT 0,
        machine_id TEXT,
        operator_id TEXT,
        required_material_lot_id TEXT,
        required_material_qty REAL DEFAULT 1.0,
        status TEXT NOT NULL CHECK(status IN ('SCHEDULED', 'RUNNING', 'PAUSED', 'BLOCKED', 'COMPLETED', 'ABORTED')),
        blocked_reason TEXT,
        due_date TEXT NOT NULL,
        start_time TEXT,
        end_time TEXT,
        created_at TEXT NOT NULL
    );
    """)

    # 5. Serialized Units (Genealogy / Digital Thread)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS serialized_units (
        serial_number TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        order_number TEXT NOT NULL,
        product_sku TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        machine_id TEXT NOT NULL,
        operator_id TEXT NOT NULL,
        consumed_lot_id TEXT NOT NULL,
        consumed_lot_code TEXT,
        consumed_supplier_lot TEXT,
        cycle_time_sec REAL,
        telemetry_temp_c REAL,
        telemetry_vib_mms REAL,
        telemetry_spindle_load REAL,
        qc_status TEXT NOT NULL CHECK(qc_status IN ('PASSED', 'DEFECTIVE', 'QUARANTINED')),
        defect_code TEXT,
        defect_description TEXT,
        defect_stage TEXT
    );
    """)

    # 6. Resource Locks (Strict Mutex / Concurrency tracking)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS resource_locks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        resource_type TEXT NOT NULL CHECK(resource_type IN ('MACHINE', 'MATERIAL', 'OPERATOR')),
        resource_id TEXT NOT NULL,
        run_id TEXT NOT NULL,
        acquired_at TEXT NOT NULL,
        released_at TEXT,
        lock_status TEXT NOT NULL CHECK(lock_status IN ('HELD', 'RELEASED', 'REJECTED')),
        notes TEXT
    );
    """)

    # 7. Telemetry History (For SPC Charts and Drift Analysis)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS telemetry_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        machine_id TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        temperature_c REAL,
        vibration_mms REAL,
        spindle_load_pct REAL,
        cycle_time_sec REAL
    );
    """)

    # 8. Predictive Early Warnings and Alerts
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS alerts (
        id TEXT PRIMARY KEY,
        timestamp TEXT NOT NULL,
        severity TEXT NOT NULL CHECK(severity IN ('INFO', 'WARNING', 'CRITICAL')),
        source_type TEXT NOT NULL CHECK(source_type IN ('MACHINE', 'MATERIAL', 'OPERATOR', 'RUN')),
        source_id TEXT NOT NULL,
        title TEXT NOT NULL,
        message TEXT NOT NULL,
        recommended_action TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('ACTIVE', 'ACKNOWLEDGED', 'RESOLVED')),
        resolved_at TEXT
    );
    """)

    # Check if database needs initial seeding
    cursor.execute("SELECT COUNT(*) FROM machines")
    if cursor.fetchone()[0] == 0:
        seed_data(cursor)

    cursor.close()
    conn.close()

def seed_data(cursor):
    now = datetime.now()
    now_str = now.isoformat()
    future_30d = (now + timedelta(days=30)).isoformat()
    future_60d = (now + timedelta(days=60)).isoformat()
    future_180d = (now + timedelta(days=180)).isoformat()
    past_10d = (now - timedelta(days=10)).isoformat()

    # 1. Machines
    machines = [
        ("CNC-01", "5-Axis High-Precision CNC Milling", "Cell A - Precision Machining", "RUNNING", "RUN-2026-001", 12.5, past_10d, 52.3, 1.4, 48.0, 75.0, 88.0, 4.0, 6.5),
        ("SMT-02", "High-Speed SMT Pick & Place Line", "Cell B - Surface Mount Electronics", "RUNNING", "RUN-2026-002", 8.0, past_10d, 42.0, 0.8, 35.0, 65.0, 80.0, 3.0, 5.0),
        ("INJ-03", "Precision Hydraulic Injection Molder", "Cell C - Engineered Polymers", "IDLE", None, 15.0, past_10d, 68.4, 2.1, 55.0, 95.0, 115.0, 5.0, 7.5),
        ("LSW-04", "Robotic 6kW Fiber Laser Welder", "Cell D - Micro-Joining & Fab", "IDLE", None, 6.5, past_10d, 38.2, 0.9, 28.0, 60.0, 75.0, 2.5, 4.5),
    ]
    cursor.executemany("""
    INSERT INTO machines (id, name, cell, status, current_run_id, target_cycle_time_sec, last_maintenance, 
                          temperature_c, vibration_mms, spindle_load_pct, temp_threshold_warning, temp_threshold_critical, 
                          vib_threshold_warning, vib_threshold_critical)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, machines)

    # 2. Materials
    materials = [
        ("LOT-ALU-101", "ALU-6061-T6", "Aerospace Aluminum Billet 6061", "Kaiser Precision Alloys", "KPA-2026-992", 200.0, 155.0, "kg", "IN_USE", "RUN-2026-001", None, future_180d, now_str),
        ("LOT-PCB-305", "FR4-ML8", "Multi-Layer FR4 Telemetry Board Substrate", "TTM Electronics", "TTM-8831-C", 300.0, 240.0, "units", "IN_USE", "RUN-2026-002", None, future_60d, now_str),
        ("LOT-RESIN-204", "EPX-AERO-9", "High-Temp Aerospace Epoxy Resin Matrix", "Hexion Advanced Polymers", "HEX-4410-Q", 50.0, 50.0, "kg", "AVAILABLE", None, None, future_30d, now_str),
        ("LOT-RESIN-205", "EPX-AERO-9", "High-Temp Aerospace Epoxy Resin Matrix (Batch B)", "Hexion Advanced Polymers", "HEX-4411-Q", 60.0, 60.0, "kg", "AVAILABLE", None, None, future_30d, now_str),
        ("LOT-MCU-408", "STM32-AERO", "AEC-Q100 Automotive Microcontroller", "STMicroelectronics", "STM-9021-A", 1000.0, 850.0, "units", "AVAILABLE", None, None, future_180d, now_str),
        ("LOT-STL-510", "SS-316L", "Medical/Aero 316L Stainless Steel Rod", "Carpenter Technology", "CARP-339", 100.0, 100.0, "kg", "AVAILABLE", None, None, future_180d, now_str),
    ]
    cursor.executemany("""
    INSERT INTO materials (lot_id, material_code, name, supplier_name, supplier_lot, initial_qty, remaining_qty, 
                          unit_of_measure, status, reserved_by_run_id, hold_reason, expiration_date, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, materials)

    # 3. Operators
    operators = [
        ("OP-101", "Marcus Vance", "BADGE-MV-882", "Shift A (06:00 - 14:00)", "ASSIGNED", "CNC-01", "RUN-2026-001", json.dumps(["CNC-01", "LSW-04"]), future_180d),
        ("OP-102", "Elena Rostova", "BADGE-ER-409", "Shift A (06:00 - 14:00)", "ASSIGNED", "SMT-02", "RUN-2026-002", json.dumps(["SMT-02", "CNC-01", "INJ-03"]), future_180d),
        ("OP-103", "David Kim", "BADGE-DK-115", "Shift B (14:00 - 22:00)", "AVAILABLE", None, None, json.dumps(["INJ-03", "LSW-04"]), future_180d),
        ("OP-104", "Sarah Chen", "BADGE-SC-924", "Shift B (14:00 - 22:00)", "AVAILABLE", None, None, json.dumps(["SMT-02", "CNC-01"]), future_180d),
    ]
    cursor.executemany("""
    INSERT INTO operators (id, name, badge_id, shift, status, active_machine_id, active_run_id, 
                           certified_operations, certification_expires)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, operators)

    # 4. Production Runs
    due_tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
    due_overdue = (now - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M")
    due_next_week = (now + timedelta(days=5)).strftime("%Y-%m-%d %H:%M")

    runs = [
        ("RUN-2026-001", "WO-9011", "SKU-VALVE-A1", "Aerospace Hydraulic Control Valve", 50, 28, 1, "CNC-01", "OP-101", "LOT-ALU-101", 1.5, "RUNNING", None, due_tomorrow, now_str, None, now_str),
        ("RUN-2026-002", "WO-9012", "SKU-ECU-T4", "Telemetry Flight Control Computer", 100, 60, 0, "SMT-02", "OP-102", "LOT-PCB-305", 1.0, "RUNNING", None, due_tomorrow, now_str, None, now_str),
        ("RUN-2026-003", "WO-9013", "SKU-POLY-BRKT", "High-Load Carbon-Polymer Bracket", 40, 0, 0, None, None, "LOT-RESIN-204", 1.2, "SCHEDULED", None, due_overdue, None, None, now_str),
        ("RUN-2026-004", "WO-9014", "SKU-AERO-DUCT", "Composite Engine Intake Manifold", 25, 0, 0, None, None, "LOT-RESIN-204", 1.0, "SCHEDULED", None, due_next_week, None, None, now_str),
    ]
    cursor.executemany("""
    INSERT INTO production_runs (id, order_number, product_sku, product_name, target_qty, produced_qty, scrap_qty,
                                machine_id, operator_id, required_material_lot_id, required_material_qty,
                                status, blocked_reason, due_date, start_time, end_time, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, runs)

    # 5. Resource Locks for the 2 running orders
    locks = [
        ("MACHINE", "CNC-01", "RUN-2026-001", now_str, None, "HELD", "Locked by CNC Milling Run 001"),
        ("OPERATOR", "OP-101", "RUN-2026-001", now_str, None, "HELD", "Assigned to CNC-01"),
        ("MATERIAL", "LOT-ALU-101", "RUN-2026-001", now_str, None, "HELD", "Active batch consumption"),
        ("MACHINE", "SMT-02", "RUN-2026-002", now_str, None, "HELD", "Locked by SMT Run 002"),
        ("OPERATOR", "OP-102", "RUN-2026-002", now_str, None, "HELD", "Assigned to SMT-02"),
        ("MATERIAL", "LOT-PCB-305", "RUN-2026-002", now_str, None, "HELD", "Active reel consumption"),
    ]
    cursor.executemany("""
    INSERT INTO resource_locks (resource_type, resource_id, run_id, acquired_at, released_at, lock_status, notes)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, locks)

    # 6. Seed some serialized units for the running orders
    units = []
    for i in range(1, 29):
        unit_time = (now - timedelta(minutes=(28 - i) * 3)).isoformat()
        is_defective = (i == 17)
        units.append((
            f"SN-VALVE-2026-{1000 + i}",
            "RUN-2026-001",
            "WO-9011",
            "SKU-VALVE-A1",
            unit_time,
            "CNC-01",
            "OP-101",
            "LOT-ALU-101",
            "ALU-6061-T6",
            "KPA-2026-992",
            12.2 if not is_defective else 16.4,
            52.0 if not is_defective else 61.2,
            1.3 if not is_defective else 3.8,
            47.5 if not is_defective else 64.0,
            "PASSED" if not is_defective else "DEFECTIVE",
            None if not is_defective else "ERR-CHIP-BURR",
            None if not is_defective else "Micro-burr on bore chamber due to momentary feed vibration",
            None if not is_defective else "Finishing Mill Stage 3"
        ))

    for j in range(1, 61):
        unit_time = (now - timedelta(minutes=(60 - j) * 1.5)).isoformat()
        units.append((
            f"SN-ECU-2026-{2000 + j}",
            "RUN-2026-002",
            "WO-9012",
            "SKU-ECU-T4",
            unit_time,
            "SMT-02",
            "OP-102",
            "LOT-PCB-305",
            "FR4-ML8",
            "TTM-8831-C",
            7.8,
            41.8,
            0.75,
            34.2,
            "PASSED",
            None,
            None,
            None
        ))

    cursor.executemany("""
    INSERT INTO serialized_units (serial_number, run_id, order_number, product_sku, timestamp, machine_id, operator_id,
                                 consumed_lot_id, consumed_lot_code, consumed_supplier_lot, cycle_time_sec,
                                 telemetry_temp_c, telemetry_vib_mms, telemetry_spindle_load, qc_status,
                                 defect_code, defect_description, defect_stage)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, units)

    # 7. Seed baseline telemetry history for CNC-01 and SMT-02
    telemetry_rows = []
    for k in range(30):
        t_time = (now - timedelta(minutes=30 - k)).isoformat()
        telemetry_rows.append(("CNC-01", t_time, 50.0 + (k * 0.1), 1.2 + (0.05 if k % 2 == 0 else -0.04), 46.0 + (k % 4), 12.3))
        telemetry_rows.append(("SMT-02", t_time, 41.5 + (k * 0.05), 0.7 + (0.02 if k % 3 == 0 else -0.02), 34.0, 7.9))

    cursor.executemany("""
    INSERT INTO telemetry_history (machine_id, timestamp, temperature_c, vibration_mms, spindle_load_pct, cycle_time_sec)
    VALUES (?, ?, ?, ?, ?, ?)
    """, telemetry_rows)

    # 8. Seed initial alert
    cursor.execute("""
    INSERT INTO alerts (id, timestamp, severity, source_type, source_id, title, message, recommended_action, status)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "ALT-INIT-001",
        now_str,
        "WARNING",
        "RUN",
        "RUN-2026-003",
        "Overdue Work Order Alert",
        "Order WO-9013 is overdue by 2.0 hours. Injection Molder INJ-03 is currently IDLE.",
        "Dispatch Run #RUN-2026-003 immediately to INJ-03 using validated Lot LOT-RESIN-204.",
        "ACTIVE"
    ))
