from pydantic import BaseModel


class EvaluationCase(BaseModel):
    case_id: str
    dataset: str
    suite: str
    root_cause_service: str
    dataset_fault: str
    normalized_fault: str
    inject_time: int
    data_dir: str

class CaseResult(BaseModel):
    case_id: str
    dataset_fault: str
    normalized_fault: str
    predicted_fault: str
    expected_result: str
    passed: bool
    latency_ms: float
    is_unmapped: bool
    scenario_dump: dict

class EvaluationReport(BaseModel):
    total_cases: int
    mapped_cases: int
    unmapped_cases: int
    mapped_top1_accuracy: float
    unmapped_rate: float
    failed_invalid_cases: int
    avg_latency_ms: float
    median_latency_ms: float
    p95_latency_ms: float
    confusion_matrix: dict
    results: list[CaseResult]
