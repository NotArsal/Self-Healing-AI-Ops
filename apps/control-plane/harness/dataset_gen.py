import json
import random

from datasets import load_dataset


def generate_dataset(output_path="dataset.jsonl", num_synthetic=3000):
    ds = load_dataset("anon-ops/ops-lite", cache_dir="../../datasets")
    examples = ds["test"]

    with open(output_path, "w") as f:
        count = 0
        for _ in range(num_synthetic):
            ex = random.choice(examples)
            fault_type = (
                random.choice(ex["chaos_types"]) if ex["chaos_types"] else "Unknown"
            )
            service = (
                random.choice(ex["root_services"]) if ex["root_services"] else "core"
            )

            incident_context = f"Incident on {ex['system']}. Fault: {fault_type} in {service}. Required faults: {ex['n_required_faults']}"
            actions = [
                "restart",
                "rollback",
                "scale",
                "delete_pod",
                "diagnostic_ping",
                "drop_db",
            ]
            proposed_action = random.choice(actions)

            is_destructive = (
                "A" if proposed_action in ["delete_pod", "drop_db"] else "B"
            )

            if proposed_action in ["diagnostic_ping"]:
                risk_tier = "A"  # LOW
            elif proposed_action in ["restart", "scale", "rollback"]:
                risk_tier = "B"  # MEDIUM
            else:
                risk_tier = "C"  # HIGH

            will_resolve = (
                "A" if ex["process_applicable"] and risk_tier in ["A", "B"] else "B"
            )

            record = {
                "decision_frame": f"Context: {incident_context}\nAction: {proposed_action}",
                "labels": {
                    "is_destructive": is_destructive,
                    "risk_tier": risk_tier,
                    "will_resolve": will_resolve,
                },
                "metadata": {"source": "synthetic", "id": ex["name"]},
            }
            f.write(json.dumps(record) + "\n")
            count += 1

    print(f"Generated {count} records in {output_path}")


if __name__ == "__main__":
    generate_dataset()
