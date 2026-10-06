from kavach.remediation.executor import verify_execution


def test_verify_execution_success():
    command = "kubectl rollout restart deployment/api"
    output = "deployment.apps/api restarted"
    status = verify_execution(output, command)
    assert status == "success"


def test_verify_execution_failure():
    command = "kubectl get pods"
    output = 'Error from server (NotFound): pods "xyz" not found'
    status = verify_execution(output, command)
    assert status == "failure"
