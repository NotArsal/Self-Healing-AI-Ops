from pathlib import Path

import pandas as pd

from kavach.evaluation.schema import EvaluationCase
from kavach.scenarios.schema import EvidenceItem, Scenario


def extract_trace_metrics(df_traces: pd.DataFrame) -> dict:
    if df_traces.empty:
        return {}

    # Ensure numeric columns
    df_traces["duration"] = pd.to_numeric(
        df_traces["duration"], errors="coerce"
    ).fillna(0)
    df_traces["duration_ms"] = df_traces["duration"] / 1e6

    # Status code logic
    if "attr.http.response.status_code" in df_traces.columns:
        http_status = pd.to_numeric(
            df_traces["attr.http.response.status_code"], errors="coerce"
        ).fillna(200)
    else:
        http_status = pd.Series(200, index=df_traces.index)

    if "attr.status_code" in df_traces.columns:
        span_status = df_traces["attr.status_code"] == "STATUS_CODE_ERROR"
    else:
        span_status = pd.Series(False, index=df_traces.index)

    df_traces["is_error"] = (http_status >= 500) | span_status

    metrics = {}
    for svc, group in df_traces.groupby("service_name"):
        metrics[f"{svc}_latency-50"] = float(group["duration_ms"].median())
        metrics[f"{svc}_latency-90"] = float(group["duration_ms"].quantile(0.90))
        metrics[f"{svc}_error"] = float(group["is_error"].mean())

    return metrics


def build_scenario_from_opslite(case: EvaluationCase) -> Scenario:
    case_dir = Path(case.data_dir)
    evidence_list = []
    anomalous_services = set()

    # 1. Traces -> Application Metrics (Latency, Error)
    normal_traces_path = case_dir / "normal_traces.parquet"
    abnormal_traces_path = case_dir / "abnormal_traces.parquet"

    if normal_traces_path.exists() and abnormal_traces_path.exists():
        df_norm = pd.read_parquet(normal_traces_path)
        df_abn = pd.read_parquet(abnormal_traces_path)

        pre_metrics = extract_trace_metrics(df_norm)
        post_metrics = extract_trace_metrics(df_abn)

        scores = {}
        for metric, post_val in post_metrics.items():
            pre_val = pre_metrics.get(metric, 0.0)

            if "error" in metric:
                # Absolute change for error rates
                diff = abs(post_val - pre_val)
                score = diff * 1000  # Boost error weight
            else:
                # Relative/absolute combo for latency (assume std is 10% of mean for traces since we only have aggregated data)
                diff = abs(post_val - pre_val)
                score = diff / (pre_val * 0.1 + 1.0)

            scores[metric] = {"val": post_val, "score": score}

        # Top 5 metrics by score
        sorted_metrics = sorted(
            scores.items(), key=lambda x: x[1]["score"], reverse=True
        )[:5]

        for m_name, m_data in sorted_metrics:
            svc = m_name.split("_")[0]
            anomalous_services.add(svc)
            evidence_list.append(
                EvidenceItem(
                    id=f"ev-metric-{m_name}",
                    kind="metric",
                    source=m_name,
                    value=m_data["val"],
                    payload={"anomaly_score": m_data["score"]},
                )
            )

    # 2. Extract Logs
    logs_path = case_dir / "abnormal_logs.parquet"
    if logs_path.exists():
        df_l = pd.read_parquet(logs_path)
        df_l = df_l.sort_values("time")

        # Filter for errors
        pattern = r"error|exception|timeout|fail|fatal|denied"
        error_logs = df_l[
            df_l["message"].str.contains(pattern, regex=True, case=False, na=False)
        ]

        selected_logs = error_logs.drop_duplicates(subset=["service_name"]).head(3)

        if len(selected_logs) < 3:
            for svc in anomalous_services:
                if len(selected_logs) >= 3:
                    break
                if svc not in selected_logs["service_name"].values:
                    svc_logs = df_l[df_l["service_name"] == svc]
                    if not svc_logs.empty:
                        selected_logs = pd.concat([selected_logs, svc_logs.head(1)])

        for idx, row in selected_logs.iterrows():
            evidence_list.append(
                EvidenceItem(
                    id=f"ev-log-{idx}",
                    kind="log",
                    source=str(row.get("service_name", "unknown")),
                    value=None,
                    payload={"message": str(row.get("message", ""))[:500]},
                )
            )

    # Contextual services
    services = {}
    for ev in evidence_list:
        if ev.kind == "metric":
            parts = ev.source.split("_")
            svc = parts[0]
            if svc not in services:
                services[svc] = {"role": "service"}

    if not services:
        services["unknown"] = {"role": "service"}

    return Scenario(
        id=f"eval-{case.case_id}",
        fault_class="UNKNOWN",
        services=services,
        health={s: "healthy" for s in services},
        quality=None,
        objectives={},
        tolerance=None,
        reversible_state={},
        permissions=None,
        signals={ev.source: ev.value for ev in evidence_list if ev.kind == "metric"},
        evidence=evidence_list,
        state={},
    )
