# OpenRCA 2.0 ops-lite Taxonomy & Mapping Report

## 1. Dataset Structure
The `ops-lite` dataset is structured via a HuggingFace snapshot layout.
- **Scale**: 455 total cases.
- **Complexity**: 279 single-fault cases, 176 hybrid (multi-root-cause) cases.
- **Systems Covered**: `ts` (TrainTicket), `hs` (HotelReservation), `otel-demo` (OpenTelemetry Demo).

For each case, evidence is split into windows:
- `normal_metrics.parquet` / `abnormal_metrics.parquet` (Host/K8s metrics)
- `normal_logs.parquet` / `abnormal_logs.parquet` (Application logs)
- `normal_traces.parquet` / `abnormal_traces.parquet` (Raw OpenTelemetry spans)
- `causal_graph.json` (Ground truth span-level cascade graph)
- `label.json` & `injection.json` (Fault metadata)

## 2. Fault Taxonomy
The dataset contains 26 distinct infrastructure and chaos-mesh injection types. 
Top occurrences:
- `PodFailure`: 118
- `NetworkDelay`: 68
- `JVMRuntimeMutator`: 61
- `NetworkPartition`: 54
- `MemoryStress`: 46
- `CPUStress`: 45
- `NetworkLoss`: 34
- `JVMLatency`: 31
- ... followed by HTTP aborts, container kills, bandwidth caps, and DNS errors.

## 3. Sample Case Analysis & Evidence Availability
Unlike RE2, which provided pre-aggregated application metrics (`service_error`, `latency-50`), `ops-lite` provides:
1. **Raw K8s/Host Metrics**: `container.cpu.usage`, `k8s.pod.memory.rss`, etc.
2. **Raw Spans**: Trace ID, span duration, HTTP status codes, parent span relationships.
3. **Raw Logs**: Standard container log streams.

**Gaps/Impact on Extractor**: Kavach's LLM relies heavily on application-level telemetry (API latency, error rates, throughput). In `ops-lite`, these are not available as pre-calculated time-series metrics. To feed Kavach, our evaluator will need to parse the `abnormal_traces.parquet` to calculate P50/P90 latencies and error rates per service on the fly. 

## 4. Proposed OpenRCA → Kavach Mapping Table

| OpenRCA Chaos Type | Kavach Fault Class | Rationale |
|--------------------|--------------------|-----------|
| `NetworkDelay`, `HTTPResponseDelay`, `HTTPRequestDelay`, `JVMLatency` | **F02** (API Latency) | Delay injections perfectly mimic network bottlenecks and circuit breaker stress testing. These reliably manifest as downstream API latency storms, which exactly matches F02 semantics. |

## 5. UNMAPPED Categories (Semantically Indefensible)

| OpenRCA Chaos Type | Rationale for `UNMAPPED` Classification |
|--------------------|------------------------------------------|
| `PodFailure`, `PodKill`, `ContainerKill` | Hard crashes are K8s infrastructure lifecycle events. Kavach F01-F09 models complex logic-based cascades (e.g., deadlock, retry storm), not basic service availability drops. |
| `CPUStress`, `MemoryStress`, `JVMMemoryStress` | These inject artificial physical constraints via OS-level stress tests. Kavach's F01/F04 are caused by internal application logic flaws (algorithmic complexity, cache poisoning). Mapping them would blur infrastructure vs logic faults. |
| `NetworkPartition`, `NetworkLoss`, `NetworkCorrupt` | Packet loss/isolation. While Kavach has `F06` (RabbitMQ Split-Brain), a general service partition is not semantically equivalent to a specific database or message broker split-brain. |
| `JVMException`, `HTTPResponseReplaceCode`, `HTTPResponseAbort` | Hard-aborting or failing requests simulates 5xx errors. While similar to Kavach `F03` (Partial Retrieval), F03 assumes incomplete/truncated payloads, not hard crashes. Better kept unmapped to preserve semantic purity. |

## 6. Recommended 5 Representative Validation Cases
To safely validate the new trace-based evidence extractor, we recommend these 5 single-fault cases representing mapped and unmapped behaviors across different systems:
1. **`NetworkDelay` (Mapped to F02)**: `hs1-frontend-delay-24srn4`
2. **`HTTPResponseDelay` (Mapped to F02)**: `ts0-ts-travel-plan-service-response-delay-pfwcqk`
3. **`PodFailure` (UNMAPPED)**: `hs0-attractions-pod-failure-s8fsgm`
4. **`CPUStress` (UNMAPPED)**: `hs1-geo-cpu-exhaustion-q8nln6`
5. **`HTTPResponseReplaceCode` (UNMAPPED)**: `ts0-ts-travel-plan-service-response-replace-code-7ps8tm`

## 7. Risks & Threats to Validity
- **Trace Parsing Overhead**: `ops-lite` contains massive raw trace files. Calculating windowed P50/P90 latencies dynamically in python pandas for 455 cases will be computationally heavy and requires rewriting the evidence extractor.
- **Extreme Unmapped Ratio**: Over 80% of `ops-lite` fault classes (and nearly all 176 hybrid cases) will be `UNMAPPED`. Mapped Top-1 accuracy will represent a very narrow slice of the dataset.
- **Multi-Root-Cause (Hybrid) Cases**: 176 cases inject 2 simultaneous faults. Kavach's current RCA schema expects a primary single `root_cause_service` and `fault_class`. Hybrid cases may confound the mapping severely.
