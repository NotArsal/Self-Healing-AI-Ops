with open('docs (3)/ROADMAP.md', 'r', encoding='utf-8') as f:
    text = f.read()

replaces = [
    ('- [ ] Training set built: ~3000 synthetic + every real decision logged since P3', '- [x] Training set built: ~3000 synthetic + every real decision logged since P3'),
    ('- [ ] **Question 3 labelled from verification outcomes, not rule-engine output.** If all three questions are rule-labelled, the model is a distilled copy of the rule table and the result is worthless — this check is the phase\'s real deliverable', '- [x] **Question 3 labelled from verification outcomes, not rule-engine output.** If all three questions are rule-labelled, the model is a distilled copy of the rule table and the result is worthless — this check is the phase\'s real deliverable'),
    ('- [ ] Fine-tune completes on Kaggle 2xT4; checkpoint versioned', '- [x] Fine-tune completes on Kaggle 2xT4; checkpoint versioned'),
    ('- [ ] **No `noul` questions anywhere** — booleans are two-option `choice` with neutral keys', '- [x] **No `noul` questions anywhere** — booleans are two-option `choice` with neutral keys')
]

for old, new in replaces:
    text = text.replace(old, new)

with open('docs (3)/ROADMAP.md', 'w', encoding='utf-8') as f:
    f.write(text)
