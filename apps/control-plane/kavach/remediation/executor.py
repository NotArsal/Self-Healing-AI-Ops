import subprocess
import httpx

from kavach.remediation.tnr_gate import evaluate_safety

class RequiresHumanApprovalError(Exception):
    def __init__(self, reason: str, command: str):
        self.reason = reason
        self.command = command
        super().__init__(f"Action requires human approval. Reason: {reason}")

def execute_command(command: str, incident_context: str = "") -> tuple[bool, str]:
    safety_assessment = evaluate_safety(command, incident_context)
    if not safety_assessment.is_safe:
        raise RequiresHumanApprovalError(reason=safety_assessment.reason, command=command)

    try:
        result = subprocess.run(
            command, shell=True, check=False, capture_output=True, text=True, timeout=30
        )
        output = result.stdout + "\n" + result.stderr
        success = result.returncode == 0
        return success, output.strip()
    except subprocess.TimeoutExpired:
        return False, "Command timed out after 30 seconds."
    except Exception as e:
        return False, f"Execution failed: {e!s}"

def execute_http(method: str, url: str, payload: dict, incident_context: str = "") -> tuple[bool, str]:
    # Very basic HTTP executor for Proof2
    safety_assessment = evaluate_safety(url, incident_context)
    if not safety_assessment.is_safe:
        raise RequiresHumanApprovalError(reason=safety_assessment.reason, command=url)

    try:
        with httpx.Client(timeout=30) as client:
            req = client.build_request(method, url, json=payload)
            res = client.send(req)
            success = res.is_success
            return success, res.text
    except Exception as e:
        return False, f"HTTP Execution failed: {e!s}"

def verify_execution(output_text: str, command: str) -> str:
    from laya import Router
    router = Router()
    questions = {
        "status": {
            "type": "choice",
            "instructions": "Did this terminal command succeed or fail based on the output?",
            "criteria": {
                "success": "Output indicates success, completion, running state, or OK",
                "failure": "Output contains error, fatal, denied, not found, or exception tracebacks",
                "unknown": "Output is empty or ambiguous",
            },
        }
    }
    prompt = f"Command: {command}\nOutput: {output_text}"
    result = router.predict(prompt, questions)
    return result["answers"]["status"].get("choice", "unknown")

