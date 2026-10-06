from pathlib import Path

import pandas as pd

from kavach.evaluation.schema import EvaluationCase
from kavach.scenarios.schema import EvidenceItem, Scenario


def build_scenario_from_case(case: EvaluationCase) -> Scenario:
    # 1. Read files
    case_dir = Path(case.data_dir)
    logs_path = case_dir / "logs.parquet"
    metrics_path = case_dir / "metrics.parquet"
    
    evidence_list = []
    anomalous_services = set()
    
    # 2. Extract metrics
    if metrics_path.exists():
        df_m = pd.read_parquet(metrics_path)
        t_inject = case.inject_time
        df_pre = df_m[(df_m['time'] >= t_inject - 300) & (df_m['time'] < t_inject)]
        df_post = df_m[(df_m['time'] >= t_inject) & (df_m['time'] <= t_inject + 300)]
        
        if not df_pre.empty and not df_post.empty:
            pre_mean = df_pre.drop(columns=['time']).mean()
            pre_std = df_pre.drop(columns=['time']).std().fillna(0)
            post_mean = df_post.drop(columns=['time']).mean()
            
            # Robust anomaly score (avoid denominator explosion)
            score = (post_mean - pre_mean).abs() / (pre_std + pre_mean.abs() * 0.1 + 1e-9)
            
            # Sort descending and take top 5
            top_metrics = score.sort_values(ascending=False).head(5)
            
            for metric_name, variance in top_metrics.items():
                anomalous_services.add(str(metric_name).split('_')[0])
                val = float(post_mean[metric_name]) if not pd.isna(post_mean[metric_name]) else 0.0
                evidence_list.append(EvidenceItem(
                    id=f"ev-metric-{metric_name}",
                    kind="metric",
                    source=str(metric_name),
                    value=val,
                    payload={"anomaly_score": float(variance)}
                ))

    # 3. Extract logs
    if logs_path.exists():
        df_l = pd.read_parquet(logs_path)
        t_inject = case.inject_time
        # Post-injection logs
        df_l_post = df_l[(df_l['timestamp'] >= t_inject) & (df_l['timestamp'] <= (t_inject + 300))]
        df_l_post = df_l_post.sort_values('timestamp')
        
        # Filter for errors
        pattern = r'error|exception|timeout|fail|fatal|denied'
        error_logs = df_l_post[df_l_post['message'].str.contains(pattern, regex=True, case=False, na=False)]
        
        # Deduplicate by container to avoid overwhelming with 1 generic error
        selected_logs = error_logs.drop_duplicates(subset=['container_name']).head(3)
        
        if len(selected_logs) < 3:
            # Pad with normal logs from the most anomalous services
            for svc in anomalous_services:
                if len(selected_logs) >= 3:
                    break
                if svc not in selected_logs['container_name'].values:
                    svc_logs = df_l_post[df_l_post['container_name'] == svc]
                    if not svc_logs.empty:
                        selected_logs = pd.concat([selected_logs, svc_logs.head(1)])
            
        for idx, row in selected_logs.iterrows():
            evidence_list.append(EvidenceItem(
                id=f"ev-log-{idx}",
                kind="log",
                source=str(row.get('container_name', 'unknown')),
                value=None,
                payload={"message": str(row.get('message', ''))[:500]}  # Truncate just in case
            ))

    # Extract unique services from metric names for context
    services = {}
    for ev in evidence_list:
        if ev.kind == "metric":
            parts = ev.source.split('_')
            svc = parts[0]
            if svc not in services:
                services[svc] = {"role": "service"}
                
    if not services:
        services["unknown"] = {"role": "service"}

    # Construct the Kavach Scenario object
    return Scenario(
        id=f"eval-{case.case_id}",
        fault_class="UNKNOWN", # Will be guessed
        services=services,
        health={s: "healthy" for s in services}, # Mock
        quality=None,
        objectives={},
        tolerance=None,
        reversible_state={},
        permissions=None,
        signals={ev.source: ev.value for ev in evidence_list if ev.kind == "metric"},
        evidence=evidence_list,
        state={}
    )
