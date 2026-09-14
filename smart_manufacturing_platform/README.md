# AERO-MES 4.0 | Smart Manufacturing & Production Control Platform

> **"Building a production control system where every unit can tell its story, resources can never be double-booked, and a problem can be traced before it becomes a production shutdown."**

---

## 1. System Overview & Problem Statement

In high-mix precision manufacturing, sudden disruptions create chaotic ripple effects:
* **The Material Hold**: A lot fails an incoming chemical assay and is flagged on hold.
* **The Idle Station**: The machine is ready, the operator is waiting, and the order is already overdue.
* **The Double-Booking Collision**: Another production order attempts to reserve the remaining inventory of that same material.
* **The Critical Question**: When defects or line stoppages occur, factories need to know:
  > *"What exactly went wrong — which material, which machine, which operator, which batch, and at what point did the problem begin?"*

**AERO-MES 4.0** solves this with an integrated, real-time Production Execution & Control System:
1. **Live Resource Twin**: Sub-second tracking of machines (vibration, heat, spindle load), material lots (genealogy, QA hold gates), and operators (certifications, active stations).
2. **Deterministic Anti-Double-Booking**: Two-phase ACID transaction locking that prevents machines, material lots, or operators from being double-booked across competing production runs.
3. **Digital Thread ("Every Unit Tells Its Story")**: Bidirectional forward & backward lineage linking every finished serialized unit to its exact supplier raw heat, operator badge, machine telemetry snapshot at fabrication, and inspection records.
4. **Predictive Early Warning System (EWS)**: Statistical Process Control (SPC) applying Western Electric rules to detect sensor drift, cycle time creep, and shelf-life expiration *before* a tool snaps or line stops.
5. **Root-Cause Post-Mortem & Patient Zero Detection**: Multi-factor statistical correlation engine that isolates the primary culprit and pinpoints the exact earliest unit and timestamp where the defect began.

---

## 2. Platform Architecture

```
                               ┌────────────────────────────────────────┐
                               │   Industrial Control Room UI (SPA)     │
                               │  - Factory Twin    - Anti-Collision    │
                               │  - Digital Thread  - Early Warning EWS │
                               │  - RCA Studio      - Scenario Lab      │
                               └───────────────────▲────────────────────┘
                                                   │ WebSockets & REST
                                                   ▼
┌───────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                FastAPI Production Engine                                         │
│                                                                                                   │
│  ┌───────────────────────┐   ┌───────────────────────┐   ┌─────────────────────────────────────┐  │
│  │ LockManager           │   │ TraceabilityEngine    │   │ AnomalyDetector (SPC)               │  │
│  │ - 2-Phase ACID Mutex  │   │ - Unit Story Builder  │   │ - 3-Sigma Trip & Drift Detection    │  │
│  │ - Hold Gatekeeper     │   │ - Forward/Backward    │   │ - Cycle Creep & Shelf-Life Tracker  │  │
│  │ - Concurrency Audit   │   │ - Patient Zero & RCA  │   │ - Real-Time Alert Dispatch          │  │
│  └───────────────────────┘   └───────────────────────┘   └─────────────────────────────────────┘  │
│                                                   ▲                                               │
│                                                   │ Live Event Ticks                              │
│                                      ┌────────────┴───────────┐                                   │
│                                      │ Factory Floor Sim Loop │                                   │
│                                      └────────────────────────┘                                   │
└───────────────────────────────────────────────────▲───────────────────────────────────────────────┘
                                                    │ WAL Mode SQLite
                                                    ▼
                               ┌────────────────────────────────────────┐
                               │       ACID SQLite Relational DB        │
                               │  - machines        - materials         │
                               │  - operators       - production_runs   │
                               │  - serialized_units- resource_locks    │
                               │  - telemetry_hist  - alerts            │
                               └────────────────────────────────────────┘
```

---

## 3. Key Capabilities & Technical Solutions

### A. Live Tracking of Materials, Machines & Operators
- **Machines**: Dials and progress gauges display continuous vibration ($mm/s$), core temperature ($^\circ C$), and spindle load ($\%$).
- **Materials**: Quantities, supplier heats, expiration countdowns, and instant hold status toggles.
- **Operators**: Shift schedules, qualification matrices, and single-active-station constraints.

### B. Strict Concurrency & Anti-Double-Booking Engine (`LockManager`)
- Implements two-phase resource acquisition within atomic SQLite transactions:
  1. Validates that the target machine is `IDLE` and has no active lease.
  2. Verifies that the operator is `AVAILABLE`, certified for the process, and not active on another machine.
  3. Verifies that the material lot is `AVAILABLE` (NOT `ON_HOLD`, `QUARANTINED`, or `EXPIRED`) and unreserved.
- **Collision Protection**: If any conflict occurs, rolls back immediately and returns HTTP `409 Conflict` with explicit diagnostic details (e.g. `Machine CNC-01 is already double-booked by active run RUN-2026-001`).

### C. Digital Thread: "Every Unit Tells Its Story" (`TraceabilityEngine`)
- Enter or scan any serial number (e.g. `SN-VALVE-2026-1017`) to display:
  - **Material Lineage**: Raw billet lot `LOT-ALU-101`, supplier heat `KPA-2026-992` from Kaiser Precision Alloys.
  - **Machine Fabrication**: Milling Center `CNC-01` in Machining Cell A.
  - **Human Element**: Operator Marcus Vance (`BADGE-MV-882`), Shift A.
  - **Sensor Snapshot at Instant of Cut**: Vibration ($3.8\text{ mm/s}$ vs $4.0\text{ mm/s}$ limit), Core Temp ($61.2^\circ\text{C}$), Spindle Load ($64\%$), Cycle Time ($16.4\text{s}$).
  - **Quality Inspection**: Defect code `ERR-CHIP-BURR` and root cause classification.

### D. Predictive Early Warning System (`AnomalyDetector`)
- Uses Western Electric rules:
  - **Rule 1**: Absolute limit trip ($V > 6.5\text{ mm/s}$ or $T > 88^\circ\text{C}$).
  - **Rule 2**: 6+ consecutive sample points steadily increasing (sloping vibration or thermal runaway). Triggers a predictive warning **before** reaching emergency shutdown levels.
  - **Rule 3**: Cycle time creep ($>25\%$ over nominal baseline).

### E. Root-Cause Post-Mortem & Patient Zero (`RCA Engine`)
- Correlates defect patterns across multi-dimensional parameters:
  - **Defect % by Machine** (e.g. $100\%$ on `CNC-01`).
  - **Defect % by Material Lot** (e.g. `LOT-ALU-101`).
  - **Defect % by Operator** (`OP-101`).
- **Patient Zero Pinpoint**: Identifies the exact first unit and timestamp where the defect began.
- **Targeted Containment**: Lists all subsequent units produced under the same condition for targeted quarantine.

---

## 4. Quick Start & Execution

### Prerequisites
- Python 3.10+ (tested with Python 3.11)
- FastAPI, Uvicorn, WebSockets (already configured)

### Running the Application
From the project directory:
```bash
python run.py
```
Open your web browser at:
```
http://localhost:8000
```

### Running Automated Test Suite
```bash
python -m unittest tests/test_platform.py -v
```

---

## 5. Interactive Scenarios Walkthrough

The platform includes 4 pre-engineered interactive scenarios accessible from the **Interactive Scenarios** tab:

1. **Scenario 1: The Production Freeze Incident (Prompt Context)**
   - Material `LOT-RESIN-204` is placed `ON_HOLD` by QA.
   - Machine `INJ-03` is ready, Operator `OP-103` is waiting, and Work Order `WO-9013` is overdue.
   - A competing run (`RUN-2026-004`) attempts to reserve `LOT-RESIN-204`.
   - The platform prevents double-booking, raises a collision alert, and suggests alternate validated batch `LOT-RESIN-205`.

2. **Scenario 2: Spindle Thermal & Vibration Drift**
   - Injects progressive vibration drift on `CNC-01`.
   - The Early Warning Radar triggers predictive warnings at cycle 6, long before catastrophic tool breakage.

3. **Scenario 3: Defect Genealogy & Patient Zero Audit**
   - Simulates a customer complaint for `SN-VALVE-2026-1017`.
   - Runs root-cause analysis, identifies machine vibration excursion as the primary cause ($88.5\%$ confidence), and identifies all exposed parts for quarantine.

4. **Scenario 4: Clean Factory State Reset**
   - Restores the factory to clean baseline state.
