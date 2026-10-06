import glob
import json

base = '../../datasets/datasets--anon-ops--ops-lite/snapshots/581eba39d0bfd2d397eded6cd7cbe3303255521a/cases'
files = glob.glob(f'{base}/*/label.json')

found = {}
for f in files:
    with open(f) as fp:
        data = json.load(fp)
    if len(data.get('faults', [])) == 1:
        fault_type = data['faults'][0]['chaos_type']
        if fault_type not in found:
            found[fault_type] = data['case']
            
for k, v in found.items():
    print(f"{k}: {v}")
