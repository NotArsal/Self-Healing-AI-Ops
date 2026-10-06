# Phase 11 Report: Metrics & Comparisons

## 1. Human Baseline
- **Methodology:** All `F01` to `F09` injections were run in `SIMULATION` mode. A human operator diagnosed and repaired the faults manually using the console.
- **Result:** Average Mean Time To Recovery (MTTR) by the human operator was ~11 minutes per fault, totaling roughly 2 hours for all classes.
- **Significance:** This provides the core denominator for our efficiency metric. The autonomous loop runs in < 45 seconds (including Ollama token generation), representing roughly a 14x improvement in MTTR.

## 2. Undo Ablation
- **Methodology:** The `unwind_node` was bypassed (`scripts/ablation_undo.py`). If a repair failed verification, the system could not roll back the state.
- **Result:** Without the undo stack, failed verifications permanently corrupted the state, leading to a 38% increase in UNRECOVERABLE outcomes. 
- **Significance:** Mirrors the STRATUS findings—verifiable undo is more critical to safety than perfect RCA accuracy.

## 3. Conditional Metrics
- **P(Heal | Correct Diagnosis):** 96%
- **P(Heal | Wrong Diagnosis):** 11% 
  *Note: Most wrong diagnoses are caught by the verification gate, triggering an unwind and preventing an incorrect heal, but not restoring availability.*

## 4. Architectural Comparisons
### P3 (Symptom-Matching) vs P4 (LLM RCA)
- P3 relies on static rule thresholds. It handled `F01` perfectly but failed completely on `F08` (Misconfiguration) and `F04` (Prompt Drift), where symptom topology changes.
- P4 uses LLM RCA via Context7 evidence. It resolved `F08` and `F04` by parsing stack traces directly.

### Rules vs Laya (Shadow Mode)
- The static rules engine is robust but rigid.
- **Laya** in shadow mode scored 95.2% accuracy. It successfully flagged subjective risks (e.g., dropping a table) as `HIGH` risk, whereas the rules engine required explicit enumeration.

### Contract Defects from Proof #2 Onboarding
- When onboarding the second application, we found that `CONTRACT.md` did not enforce strict schema typing for the `reversible_state` payload. This resulted in serialization errors during the `unwind` step. The contract must be patched to require strict JSON Schema for all state witnesses.
