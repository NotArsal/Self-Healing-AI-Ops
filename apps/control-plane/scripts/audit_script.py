import json
from collections import Counter


def audit():
    with open('eval_results/audit_ops_lite_baseline.json', 'r') as f:
        data = json.load(f)
        
    mapped_cases = [c for c in data if c['normalized_fault'] != 'UNMAPPED']
    unmapped_cases = [c for c in data if c['normalized_fault'] == 'UNMAPPED']
    
    print(f"Total Cases: {len(data)}")
    print(f"Mapped Cases: {len(mapped_cases)}")
    print(f"Unmapped Cases: {len(unmapped_cases)}")
    
    mapped_chaos_types = Counter(c['dataset_fault'] for c in mapped_cases)
    print(f"Mapped Chaos Types: {mapped_chaos_types}")
    
    unmapped_chaos_types = Counter(c['dataset_fault'] for c in unmapped_cases)
    # Check if any mapped types accidentally slipped into unmapped or vice versa
    allowed_mapped = {"NetworkDelay", "HTTPResponseDelay", "HTTPRequestDelay", "JVMLatency"}
    
    for t in mapped_chaos_types:
        assert t in allowed_mapped, f"ILLEGAL MAPPED TYPE: {t}"
    for t in unmapped_chaos_types:
        assert t not in allowed_mapped, f"ILLEGAL UNMAPPED TYPE: {t}"
        
    print("MAPPING AUDIT PASSED")
    
    # ACCURACY
    correct = sum(1 for c in mapped_cases if c['passed'])
    print(f"Overall Accuracy: {correct}/{len(mapped_cases)} = {correct/len(mapped_cases)*100:.1f}%")
    
    # SINGLE VS HYBRID
    mapped_single = [c for c in mapped_cases if not c['is_hybrid']]
    mapped_hybrid = [c for c in mapped_cases if c['is_hybrid']]
    
    correct_single = sum(1 for c in mapped_single if c['passed'])
    correct_hybrid = sum(1 for c in mapped_hybrid if c['passed'])
    
    print(f"Single Accuracy: {correct_single}/{len(mapped_single)} = {correct_single/len(mapped_single)*100:.1f}%")
    print(f"Hybrid Accuracy: {correct_hybrid}/{len(mapped_hybrid)} = {correct_hybrid/len(mapped_hybrid)*100:.1f}%")

if __name__ == "__main__":
    audit()
