from kavach.preflight.checker import PreflightChecker

VALID_YAML = """
services:
  api:
    role: application
    depends_on: [vector_store, model_primary]
    health:
      type: http
      target: http://api:8080/healthz
      timeout_s: 3
      expect_status: 200
  pgvector:
    role: vector_store
    health:
      type: tcp
      target: pgvector:5432
      timeout_s: 3
  model_primary:
    role: model_primary
    health:
      type: http
      target: http://model:8080/healthz
      timeout_s: 3

quality:
  golden_set: ./golden_set.yaml
  min_cases: 20
  scorers: [groundedness, answer_match]
  schedule_s: 300
  runner:
    type: http
    target: http://api:8080/v1/query

objectives:
  availability:
    - metric: http_requests_errors_ratio
      comparator: <
      threshold: 0.01
      window_s: 120
      weight: 1.0
  quality:
    - metric: kavach_eval_pass_rate
      comparator: ">="
      threshold: 0.85
      window_s: 300
      weight: 1.0

tolerance:
  quality_drop_pct: 15

reversible_state:
  prompts:
    kind: git_directory
    path: ./prompts

permissions:
  allowed_actions: [switch_model]
  forbidden_services: [pgvector]
  max_risk_tier: MEDIUM

telemetry:
  otlp_endpoint: http://otel-collector:4318
  semconv_version: "1.42.0"
  genai_instrumented: true
  required_attributes: [provider]
"""


def test_preflight_valid_l3():
    checker = PreflightChecker(VALID_YAML)
    report = checker.run_all()

    # Check all passed
    assert all(c.passed for c in report.checks), [
        c.message for c in report.checks if not c.passed
    ]
    assert report.conformance_level == "L3 - Healable"


def test_preflight_invalid_yaml():
    checker = PreflightChecker("foo: [unclosed")
    report = checker.run_all()

    p01 = next(c for c in report.checks if c.code == "P01")
    assert not p01.passed
    assert report.conformance_level == "UNARMED"


def test_preflight_missing_liveness_drops_l0():
    import yaml

    data = yaml.safe_load(VALID_YAML)
    del data["services"]["api"]["health"]
    bad_yaml = yaml.dump(data)

    checker = PreflightChecker(bad_yaml)
    report = checker.run_all()

    p05 = next(c for c in report.checks if c.code == "P05")
    assert not p05.passed
    assert report.conformance_level == "UNARMED"


def test_preflight_missing_quality_drops_l1():
    # Quality config missing drops it below L1 (so it's L0)
    no_qual = (
        VALID_YAML.split("quality:")[0]
        + "\n"
        + "objectives:\n"
        + VALID_YAML.split("objectives:\n")[1]
    )
    no_qual = no_qual.replace(
        'quality:\n    - metric: kavach_eval_pass_rate\n      comparator: ">="\n      threshold: 0.85\n      window_s: 300\n      weight: 1.0',
        "",
    )

    checker = PreflightChecker(no_qual)
    report = checker.run_all()

    p06 = next(c for c in report.checks if c.code == "P06")
    assert not p06.passed
    # Conformance level drops to L0
    assert report.conformance_level == "L0 - Observed"
