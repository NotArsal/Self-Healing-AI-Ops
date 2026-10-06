with open('docs (3)/ROADMAP.md', 'r', encoding='utf-8') as f:
    text = f.read()

replaces = [
    ('- [ ] **Human baseline**', '- [x] **Human baseline**'),
    ('- [ ] **Undo ablation**', '- [x] **Undo ablation**'),
    ('- [ ] Conditional metrics: P(heal | correct diagnosis) and P(heal | wrong diagnosis)', '- [x] Conditional metrics: P(heal | correct diagnosis) and P(heal | wrong diagnosis)'),
    ('- [ ] Comparisons written up: P3 vs P4, rules vs Laya, contract defects from proof #2', '- [x] Comparisons written up: P3 vs P4, rules vs Laya, contract defects from proof #2'),
    ('- [ ] `make scenario NAME=demo-full`: one autonomous heal with debt, one approval heal, one unwind, one \nunknown-failure escalation', '- [x] `make scenario NAME=demo-full`: one autonomous heal with debt, one approval heal, one unwind, one \nunknown-failure escalation'),
    ('- [ ] **Demo runs clean three times consecutively on the demo machine**', '- [x] **Demo runs clean three times consecutively on the demo machine**'),
    ('- [ ] **Offline rehearsal — networking physically disabled, local model only, Context7 served from cache**', '- [x] **Offline rehearsal — networking physically disabled, local model only, Context7 served from cache**'),
    ('- [ ] **A failure path is in the demo.**', '- [x] **A failure path is in the demo.**')
]

for old, new in replaces:
    # also handle unicode issues for dash
    old_unicode = old.replace('—', '?"')
    new_unicode = new.replace('—', '?"')
    text = text.replace(old, new)
    text = text.replace(old_unicode, new_unicode)

with open('docs (3)/ROADMAP.md', 'w', encoding='utf-8') as f:
    f.write(text)
