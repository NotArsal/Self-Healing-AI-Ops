import glob
import json
from collections import Counter

base = '../../datasets/datasets--anon-ops--ops-lite/snapshots/581eba39d0bfd2d397eded6cd7cbe3303255521a/cases'
files = glob.glob(f'{base}/*/label.json')

fault_types = Counter()
systems = Counter()
fault_counts = Counter()
services_affected = Counter()

for f in files:
    with open(f) as fp:
        data = json.load(fp)
    sys = data.get('system', 'unknown')
    systems[sys] += 1
    
    ft = data.get('faults', [])
    fault_counts[len(ft)] += 1
    
    for fault in ft:
        fault_types[fault.get('chaos_type')] += 1
        services_affected[fault.get('service')] += 1

print(f"Total cases: {len(files)}")
print(f"Systems: {systems}")
print(f"Fault counts per case: {fault_counts}")
print(f"Taxonomy: {fault_types}")
print(f"Services: {services_affected}")
