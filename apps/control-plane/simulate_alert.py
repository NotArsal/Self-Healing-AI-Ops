import sys

import requests


def post_alert(description: str):
    payload = {
        "status": "firing",
        "alerts": [
            {
                "labels": {"alertname": "SimulatedAlert"},
                "annotations": {"description": description},
            }
        ],
    }

    print(f"Posting alert: {description}")
    resp = requests.post("http://localhost:8000/api/v1/alerts/webhook", json=payload)
    print("Response:", resp.json())
    return resp.json()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        post_alert(sys.argv[1])
    else:
        # Test 1: Application alert -> Should trigger F10 (Mitigated)
        r = post_alert("The API pod is experiencing 500 errors and high latency")

        # Test 2: Database alert -> Should trigger F11 (Escalated due to Laya DENY)
        r2 = post_alert("Database connection pool is full and queries are timing out")

        # Test 3: Unknown noise -> Should be ignored
        r3 = post_alert("CPU usage spiked to 80% briefly")
