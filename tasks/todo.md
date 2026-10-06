## Task 1: Dataset Generation

**Description:** Generate a dataset of labeled operational commands.

**Acceptance criteria:**
- [x] Create `scripts/generate_laya_dataset.py`.
- [x] Generate at least 50 examples in `dataset.jsonl`.

**Verification:**
- [x] Manual review of the generated JSONL file.

**Dependencies:** None

---

## Task 2: Fine-Tuning Script

**Description:** Create the script to train Laya on the dataset.

**Acceptance criteria:**
- [x] Create `scripts/finetune_laya.py`.
- [x] Implement training loop (or mock if local compute is insufficient).
- [x] Output a model checkpoint.

**Verification:**
- [x] Script runs without errors and produces output.

**Dependencies:** Task 1

---

## Task 3: Integration

**Description:** Allow TNR gate to load the custom model.

**Acceptance criteria:**
- [x] Modify `tnr_gate.py` to optionally load a local checkpoint.
- [x] Test the gate with the fine-tuned model (or the original if the script mocks it).

**Verification:**
- [x] `tnr_gate.py` imports without errors.

**Dependencies:** Task 2
