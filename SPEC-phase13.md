# Spec: Phase 13 - Laya Fine-Tuning Pipeline

## Objective
Provide a pipeline to fine-tune the Laya zero-shot TNR (Task Negative Representation) classifier based on organizational policies. The un-tuned Laya model is highly conservative (e.g., flagging `restart` as `medium_risk`), but organizations often have specific rules about what commands are safe or destructive. Fine-tuning allows the model to align with these specific operational constraints.

## Current State
- The TNR Gate in `kavach.remediation.tnr_gate` uses the raw, zero-shot `laya.Router`.
- We rely strictly on heavily detailed prompts to bias the model's zero-shot classifications.
- There is no pipeline for collecting feedback or training the model on domain-specific datasets.

## Target State
1. **Dataset Generation**: Create a tool `scripts/generate_laya_dataset.py` that generates a synthetic dataset of operational commands labeled with risk tiers (low, medium, high).
2. **Fine-Tuning Script**: Create `scripts/finetune_laya.py` that uses the Laya SDK's fine-tuning capabilities (or standard HuggingFace tools if Laya exposes them) to fine-tune a model checkpoint.
3. **Integration**: Update `tnr_gate.py` to optionally load a fine-tuned model checkpoint if it exists.

## Architecture Details
- The dataset will be a JSONL file with `text` (the operational command) and `label` (the expected risk tier).
- The fine-tuning script will output a saved model checkpoint into `apps/control-plane/models/laya_finetuned`.

## Success Criteria
- A script successfully generates a training dataset of at least 50 operational commands.
- A script successfully simulates or runs a fine-tuning loop for the TNR classifier.
- The `tnr_gate.py` is capable of loading the customized model path.
