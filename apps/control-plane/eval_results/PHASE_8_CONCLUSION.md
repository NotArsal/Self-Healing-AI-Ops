# Phase 8: External Evaluation Conclusion

## 1. Objective
The objective of Phase 8 was to evaluate Kavach's Root Cause Analysis (RCA) engine (powered by Qwen) against established external IT/ops benchmark datasets (RCAEval-RE2 and OpenRCA 2.0 ops-lite) without fine-tuning the model, modifying the core Kavach taxonomy, or coupling the evaluator into the live operational runtime. 

## 2. RE2 Baseline
The RCAEval-RE2 benchmark proved that an LLM could accurately diagnose application-layer latency faults (F02) from purely deterministic evidence extraction. However, it also revealed that blindly mapping infrastructure-level faults (e.g., OS-level socket faults) to Kavach's application logic faults (e.g., F05 Connection Pool Exhaustion) heavily penalized accuracy due to severe semantic mismatch.

## 3. ops-lite Baseline
The OpenRCA 2.0 ops-lite benchmark involved 455 cases (279 single-fault, 176 hybrid). An advanced trace-based evidence extractor derived P50/P90 latencies and error rates from raw OpenTelemetry spans, demonstrating that Kavach's RCA graph is robust against raw, unaggregated telemetry. To avoid the RE2 mistake, we strictly mapped only `NetworkDelay`, `HTTPResponseDelay`, `HTTPRequestDelay`, and `JVMLatency` to `F02` (API Latency), leaving physical infrastructure failures `UNMAPPED`.

## 4. Final Validated Metrics
- **F02 Single-Fault Mapped Accuracy**: 89.7% (52/58)
- **F02 Overall Mapped Accuracy**: 86.8% (92/106)
- **Mapping Coverage**: 23.3% (106 mapped cases)
- **Execution Performance**: 0 extraction failures, 0 RCA execution failures.

## 5. Mapping Limitations
- **This is NOT overall Kavach RCA accuracy.**
- **This does NOT validate F01–F09 comprehensively.** The evaluated subset exclusively tests F02 (API Latency) because OpenRCA does not inject Kavach's AI-native logic faults (e.g., cache poisoning, auth saturation, retry storms).
- The 349 unmapped infrastructure cases are excluded from the mapped accuracy metric, not counted as failures. They were intentionally left `UNMAPPED` due to semantic mismatch with Kavach's taxonomy.

## 6. Hybrid Scoring Limitation
- **The hybrid 83.3% result must not be presented as a reliable performance metric.**
- Hybrid/multi-root-cause accuracy is considered unreliable because the current evaluator statically scores Kavach's prediction against `faults[0]` in the ground-truth array, arbitrarily penalizing or rewarding the LLM if it correctly identifies a symptomatically dominant secondary fault.

## 7. Ground-Truth Blindness Validation
Ground-truth blindness and deterministic extraction were independently audited. The evidence extractor strictly parsed normal/abnormal telemetry without any access to `chaos_type`, `label.json`, `causal_graph.json`, or injection metadata. Ground truth was only utilized for final scoring after the LLM prediction completed.

## 8. Threats to Validity
- **Lack of Autonomy**: This static benchmark does NOT prove autonomous remediation. It only proves static diagnostic capability on pre-packaged telemetry.
- **Taxonomy Mismatch**: Testing an application-layer logic evaluation framework against infrastructure-layer chaos mesh datasets severely limits mapping overlap, restricting performance validation to a single fault class (F02).

## 9. Final Conclusion
Phase 8 demonstrated that Kavach's RCA engine can diagnose F02-compatible API latency cascades with 89.7% Top-1 accuracy on mapped single-fault ops-lite cases (52/58), and 86.8% Top-1 accuracy across all mapped cases (92/106). The evaluation covered 23.3% of the 455-case ops-lite dataset because the remaining infrastructure-level fault types were intentionally left UNMAPPED due to semantic mismatch with Kavach's AI-native fault taxonomy. Hybrid/multi-root-cause accuracy is considered unreliable because the current evaluator scores against faults[0].

## 10. Phase 8 Exit Criteria
- [x] Read-only datasets ingested without modifying Kavach core runtime.
- [x] Ground-truth blind evidence extractor fully audited.
- [x] Unmapped semantics correctly separated from mapped accuracy calculations.
- [x] RE2 and ops-lite baselines successfully executed.
- [x] Final conclusion explicitly framing the exact limits of the claim.

## 11. What Phase 9 Will Test
Phase 9 will transition from static read-only benchmarking to **dynamic live-system remediation**. By integrating the **Laya** autonomous agent execution framework, Phase 9 will test whether Qwen can act upon these diagnoses to safely write code, execute CLI commands, modify infrastructure, and autonomously resolve live incidents using the TNR (Trust, Negotiate, Resolve) safety gate.
