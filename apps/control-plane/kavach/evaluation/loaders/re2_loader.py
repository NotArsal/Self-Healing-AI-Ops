from pathlib import Path

import pandas as pd

from kavach.evaluation.schema import EvaluationCase

FAULT_MAPPING = {
    "delay": "F02", 
    "socket": "F05",
    "cpu": "UNMAPPED",
    "disk": "UNMAPPED",
    "loss": "UNMAPPED",
    "mem": "UNMAPPED"
}

def load_re2_cases(base_path: str) -> list[EvaluationCase]:
    cases_path = Path(base_path) / "RCAEval/cases.parquet"
    if not cases_path.exists():
        raise FileNotFoundError(f"Cannot find {cases_path}")

    df = pd.read_parquet(cases_path)
    # Filter for RE2-TT
    df_re2 = df[df['dataset'] == 'RE2-TT']
    
    cases = []
    dataset_root = Path(base_path)
    
    for _, row in df_re2.iterrows():
        case_id = row['case']
        dataset_fault = row['fault']
        normalized = FAULT_MAPPING.get(dataset_fault, "UNMAPPED")
        
        # Determine case directory
        case_dir = dataset_root / "RCAEval-RE2" / case_id
        if not case_dir.exists():
            continue
            
        cases.append(EvaluationCase(
            case_id=case_id,
            dataset=row['dataset'],
            suite=row['suite'],
            root_cause_service=row['root_cause_service'],
            dataset_fault=dataset_fault,
            normalized_fault=normalized,
            inject_time=int(row['inject_time']),
            data_dir=str(case_dir.resolve())
        ))
        
    return cases
