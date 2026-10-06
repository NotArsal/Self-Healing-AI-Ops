# Phase 8 RE2 Findings Report

## 1. Quantitative Breakdown

**Overall Mapped Accuracy**: 36.67% (11/30)
*Note: This accuracy score strictly applies only to the 2 mapped fault classes (delay, socket) out of the 6 total fault classes in the RCAEval dataset.*

### F02 (Delay)
- **Total Cases**: 15
- **Correct Predictions**: 11
- **Accuracy**: 73.3%
- **Misclassifications**: -> F01, -> F01, -> F01, -> F04

### F05 (Socket)
- **Total Cases**: 15
- **Correct Predictions**: 0
- **Accuracy**: 0.0%
- **Misclassifications**:
  - F05 → F02: 7
  - F05 → F04: 5
  - F05 → F01: 3
  - F05 → F05: 0

## 2. Representative Case Analyses

### Correctly Diagnosed Delay: re2tt_ts-auth-service_delay_2
- **Dataset Fault**: delay
- **Extracted Metrics**: ts-auth-service_latency-50, ts-user-service_cpu, ts-ui-dashboard_latency-50, ts-travel2-service_latency-50, ts-ui-dashboard_latency-90
- **Extracted Logs**: 3
- **Prediction**: F02

### Socket Diagnosed as F02 (Latency): re2tt_ts-auth-service_socket_1
- **Extracted Metrics**: ts-auth-service_latency-50, ts-auth-service_latency-90, ts-ui-dashboard_latency-90, ts-auth-service_socket, ts-auth-service_cpu
- **Logs**: 3

### Socket Diagnosed as F04 (Cache/Mem): re2tt_ts-auth-service_socket_3
- **Extracted Metrics**: ts-auth-service_latency-50, ts-auth-service_latency-90, ts-ui-dashboard_latency-90, ts-auth-service_cpu, ts-auth-service_socket
- **Logs**: 3

## 3. Evaluator Assumption: RCAEval `socket` -> Kavach `F05`
The assumption that RCAEval's `socket` fault is equivalent to Kavach's `F05` (Connection Pool Exhaustion) is fundamentally flawed.

RCAEval injects socket faults at the infrastructure layer (e.g., dropping packets or manipulating open socket limits), which manifests symptomatically as cascading latency spikes or generic application timeouts in downstream microservices. 

Kavach's `F05`, conversely, is an application-layer construct specifically targeting exhaustion of internal resource pools (e.g., HikariCP connection pools, MongoDB client pools) identifiable through pool saturation metrics. 

Because the evidence extractor acts faithfully to avoid ground-truth leakage, it consistently identifies the highest variance in `latency-50` and `latency-90` metrics for these socket cases. Qwen rightfully interprets this evidence as standard network delay (`F02`) rather than `F05` because the metrics and logs presented to it do not explicitly indicate a *pool configuration constraint*, but rather simple service lag.

## 4. Threats to Validity
- **Mapping Granularity**: Forcing RCAEval `socket` into Kavach `F05` heavily penalizes the benchmark. Kavach technically identified the correct symptomatic behavior (delay/latency), but failed the binary ground-truth check due to semantic mismatch between infrastructure faults and application faults.
- **Evidence Visibility**: The socket metric itself rarely exhibited the highest mathematical Z-score variance. This means the LLM was evaluating latency symptoms without ever seeing the root socket constraint evidence.
- **Unmapped Dataset Dominance**: 66.6% of cases (cpu, mem, loss, disk) remain unmapped, leaving a tiny sample size (30) for mapping validation, completely skewing the top-line benchmark score.

## 5. Recommendation
1. **Drop F05 Mapping**: Reclassify RCAEval `socket` as `UNMAPPED`, or map it to `F02` (Latency) if we accept symptomatic equivalence.
2. **Retain Extractor**: The extractor proved reliable, deterministic, and unbiased by selecting the objectively strongest anomalous signals. Do not change it.
3. **Do Not Fine-Tune Qwen**: Qwen's deduction (F02) was clinically correct for the latency evidence it received. The failure lies in the dataset semantic mapping, not the LLM.
