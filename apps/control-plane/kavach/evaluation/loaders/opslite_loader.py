import glob
import json
from pathlib import Path

from kavach.evaluation.schema import EvaluationCase


def load_opslite_cases(dataset_dir: str) -> list[EvaluationCase]:
    cases = []
    base_dir = Path(dataset_dir) / 'snapshots/581eba39d0bfd2d397eded6cd7cbe3303255521a/cases'
    label_files = glob.glob(f"{base_dir}/*/label.json")
    
    # Mapped types
    F02_FAULTS = {"NetworkDelay", "HTTPResponseDelay", "HTTPRequestDelay", "JVMLatency"}
    
    for label_path in label_files:
        with open(label_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        case_id = data.get('case')
        faults = data.get('faults', [])
        
        # Determine dataset_fault and root_cause_service
        # For simplicity, just use the first fault if multiple exist
        dataset_fault = "Unknown"
        root_cause_service = "Unknown"
        if faults:
            dataset_fault = faults[0].get('chaos_type', "Unknown")
            root_cause_service = faults[0].get('service', "Unknown")
            
        if dataset_fault in F02_FAULTS:
            normalized_fault = "F02"
        else:
            normalized_fault = "UNMAPPED"
            
        cases.append(EvaluationCase(
            case_id=case_id,
            dataset="ops-lite",
            suite="default",
            dataset_fault=dataset_fault,
            normalized_fault=normalized_fault,
            root_cause_service=root_cause_service,
            inject_time=0, # ops-lite has pre-split normal/abnormal datasets instead of a single timestamp
            data_dir=str(Path(label_path).parent)
        ))
        
    return cases
