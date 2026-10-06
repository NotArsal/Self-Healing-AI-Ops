import subprocess

from kavach.remediation.tnr_gate import evaluate_safety


class RequiresHumanApprovalError(Exception):
    """Raised when an action is flagged as unsafe by the TNR gate and requires human approval."""
    def __init__(self, reason: str, command: str):
        self.reason = reason
        self.command = command
        super().__init__(f"Action requires human approval. Reason: {reason}")

def execute_command(command: str, incident_context: str = "") -> tuple[bool, str]:
    """
    Executes a shell command after verifying its safety via the TNR gate.
    
    Args:
        command: The shell command to execute.
        incident_context: The context of the incident for the TNR gate to evaluate.
        
    Returns:
        A tuple of (success, output).
        
    Raises:
        RequiresHumanApprovalError: If the TNR gate flags the command as unsafe.
    """
    # 1. TNR Safety Check
    safety_assessment = evaluate_safety(command, incident_context)
    
    if not safety_assessment.is_safe:
        raise RequiresHumanApprovalError(reason=safety_assessment.reason, command=command)
        
    # 2. Execution (Autonomously since it's verified safe)
    try:
        # Run command securely with timeout. In production we might not use shell=True 
        # but for Phase 9 local testing we simulate generic bash/powershell executions.
        result = subprocess.run(
            command,
            shell=True,
            check=False,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        output = result.stdout + "\n" + result.stderr
        success = result.returncode == 0
        return success, output.strip()
        
    except subprocess.TimeoutExpired:
        return False, "Command timed out after 30 seconds."
    except Exception as e:
        return False, f"Execution failed: {e!s}"

def verify_execution(output_text: str, command: str) -> str:
    """
    Uses Laya to verify if the executed command logically succeeded based on its output.
    Returns: 'success', 'failure', or 'unknown'
    """
    from laya import Router
    router = Router()
    
    questions = {
        "status": {
            "type": "choice",
            "instructions": "Did this terminal command succeed or fail based on the output?",
            "criteria": {
                "success": "Output indicates success, completion, running state, or OK",
                "failure": "Output contains error, fatal, denied, not found, or exception tracebacks",
                "unknown": "Output is empty or ambiguous"
            }
        }
    }
    
    prompt = f"Command: {command}\nOutput: {output_text}"
    result = router.predict(prompt, questions)
    
    return result["answers"]["status"].get("choice", "unknown")
