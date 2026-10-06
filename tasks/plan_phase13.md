# Implementation Plan: Phase 13 - Laya Fine-Tuning Pipeline

## Overview
Develop a dataset generation and fine-tuning pipeline to align the Laya TNR gate with custom operational risk policies.

## Task List

### Phase 1: Dataset Generation
- [ ] Task 1: Create `apps/control-plane/scripts/generate_laya_dataset.py`.
- [ ] Task 2: Implement logic to generate `dataset.jsonl` containing various bash commands labeled as `low_risk`, `medium_risk`, and `high_risk`.

### Phase 2: Fine-Tuning Script
- [ ] Task 3: Create `apps/control-plane/scripts/finetune_laya.py`.
- [ ] Task 4: Implement the fine-tuning logic using the Laya API or a mock training loop if Laya fine-tuning requires cloud compute.
- [ ] Task 5: Save the resulting model checkpoint to a local directory.

### Phase 3: Integration
- [ ] Task 6: Update `kavach/remediation/tnr_gate.py` to accept a `checkpoint_path` and use the fine-tuned model if available.
