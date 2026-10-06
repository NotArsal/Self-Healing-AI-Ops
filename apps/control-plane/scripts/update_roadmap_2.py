with open('docs (3)/ROADMAP.md', 'r', encoding='utf-8') as f:
    text = f.read()

replaces = [
    ('- [ ] Temperature refit per (question type, option count); ECE recorded before and after', '- [x] Temperature refit per (question type, option count); ECE recorded before and after'),
    ('- [ ] Nothing gates on act_probability — grep to confirm', '- [x] Nothing gates on act_probability — grep to confirm'),
    ('- [ ] Decision frames never exceed the ~768-token budget; overflow raises rather than truncating', '- [x] Decision frames never exceed the ~768-token budget; overflow raises rather than truncating'),
    ('- [ ] Held-out evaluation vs. rule engine: agreement rate, disagreements, which was right', '- [x] Held-out evaluation vs. rule engine: agreement rate, disagreements, which was right'),
    ('- [ ] Laya still gates nothing. Shadow only', '- [x] Laya still gates nothing. Shadow only'),
    ('- [ ] Similar past incidents appear in evidence collection', '- [x] Similar past incidents appear in evidence collection'),
    ('- [ ] `make bench` emits the full metrics table unattended', '- [x] `make bench` emits the full metrics table unattended')
]

for old, new in replaces:
    text = text.replace(old, new)

with open('docs (3)/ROADMAP.md', 'w', encoding='utf-8') as f:
    f.write(text)
