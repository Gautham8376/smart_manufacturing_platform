from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class MachineTelemetry(BaseModel):
    temperature_c: float
    vibration_mms: float
    spindle_load_pct: float
    cycle_time_sec: Optional[float] = None

class MachineResponse(BaseModel):
    id: str
    name: str
    cell: str
    status: str
    current_run_id: Optional[str] = None
    target_cycle_time_sec: float
    last_maintenance: Optional[str] = None
    temperature_c: float
    vibration_mms: float
    spindle_load_pct: float
    temp_threshold_warning: float
    temp_threshold_critical: float
    vib_threshold_warning: float
    vib_threshold_critical: float

class MaterialHoldRequest(BaseModel):
    lot_id: str
    hold_reason: str

class MaterialReleaseRequest(BaseModel):
    lot_id: str

class MaterialResponse(BaseModel):
    lot_id: str
    material_code: str
    name: str
    supplier_name: str
    supplier_lot: str
    initial_qty: float
    remaining_qty: float
    unit_of_measure: str
    status: str
    reserved_by_run_id: Optional[str] = None
    hold_reason: Optional[str] = None
    expiration_date: str
    created_at: str

class OperatorResponse(BaseModel):
    id: str
    name: str
    badge_id: str
    shift: str
    status: str
    active_machine_id: Optional[str] = None
    active_run_id: Optional[str] = None
    certified_operations: List[str]
    certification_expires: str

class ProductionRunCreate(BaseModel):
    order_number: str
    product_sku: str
    product_name: str
    target_qty: int
    required_material_lot_id: str
    required_material_qty: float = 1.0
    machine_id: Optional[str] = None
    operator_id: Optional[str] = None
    due_date: Optional[str] = None

class ProductionRunDispatch(BaseModel):
    run_id: str
    machine_id: str
    operator_id: str
    material_lot_id: str

class ProductionRunResponse(BaseModel):
    id: str
    order_number: str
    product_sku: str
    product_name: str
    target_qty: int
    produced_qty: int
    scrap_qty: int
    machine_id: Optional[str] = None
    operator_id: Optional[str] = None
    required_material_lot_id: Optional[str] = None
    required_material_qty: float
    status: str
    blocked_reason: Optional[str] = None
    due_date: str
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    created_at: str

class SerializedUnitResponse(BaseModel):
    serial_number: str
    run_id: str
    order_number: str
    product_sku: str
    timestamp: str
    machine_id: str
    operator_id: str
    consumed_lot_id: str
    consumed_lot_code: Optional[str] = None
    consumed_supplier_lot: Optional[str] = None
    cycle_time_sec: Optional[float] = None
    telemetry_temp_c: Optional[float] = None
    telemetry_vib_mms: Optional[float] = None
    telemetry_spindle_load: Optional[float] = None
    qc_status: str
    defect_code: Optional[str] = None
    defect_description: Optional[str] = None
    defect_stage: Optional[str] = None

class ResourceLockResponse(BaseModel):
    id: int
    resource_type: str
    resource_id: str
    run_id: str
    acquired_at: str
    released_at: Optional[str] = None
    lock_status: str
    notes: Optional[str] = None

class AlertResponse(BaseModel):
    id: str
    timestamp: str
    severity: str
    source_type: str
    source_id: str
    title: str
    message: str
    recommended_action: str
    status: str
    resolved_at: Optional[str] = None

class RootCauseAnalysisRequest(BaseModel):
    serial_number: Optional[str] = None
    run_id: Optional[str] = None
    lot_id: Optional[str] = None

class RootCauseAnalysisResponse(BaseModel):
    query_target: str
    suspected_root_cause: str
    confidence_pct: float
    patient_zero_unit: Optional[Dict[str, Any]] = None
    correlations: Dict[str, Any]
    timeline_events: List[Dict[str, Any]]
    quarantine_recommendation: Dict[str, Any]

class ScenarioTriggerRequest(BaseModel):
    scenario_name: str # "prompt_freeze", "spindle_drift", "double_booking_collision", "genealogy_recall"
