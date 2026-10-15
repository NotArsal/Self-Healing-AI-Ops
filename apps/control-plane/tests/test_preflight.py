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


def test_a_manifest_that_only_parses_is_not_healable():
    """This test used to assert L3 - Healable for exactly this input.

    It could, because every check from P02 to P13 reported `PASS (Simulated)` on
    the strength of the declaration in front of it. The manifest below names
    services at `http://api:8080` and a collector at `otel-collector:4318`, none
    of which exist on the machine running this test, and it was certified with
    the strongest claim the contract can make.
    """
    report = PreflightChecker(VALID_YAML).run_all()
    by_code = {c.code: c for c in report.checks}

    assert report.conformance_level != "L3 - Healable"
    # The manifest is well-formed, and that much is still a real pass.
    assert by_code["P01"].status == "PASS"
    # Nothing answers at those hostnames, and the checks now say so.
    assert by_code["P04"].status == "FAIL"
    assert by_code["P11"].status == "FAIL"
    # Structural checks need no network and are measured either way.
    assert by_code["P09"].status == "PASS", by_code["P09"].message


def test_checks_needing_a_path_report_unverified_rather_than_passing():
    """A result the platform could not establish must not look like a pass."""
    report = PreflightChecker(VALID_YAML).run_all()
    by_code = {c.code: c for c in report.checks}

    # P06 runs the golden set, which is resolved relative to the manifest.
    assert by_code["P06"].status == "UNVERIFIED"
    assert "no manifest path" in by_code["P06"].message
    # P12 cannot pass for any application yet: there is no span ingestion.
    assert by_code["P12"].status == "UNVERIFIED"

    assert {c.code for c in report.unverified()} >= {"P06", "P12"}
    # And the report names what is standing in the way of the next level.
    assert report.level_capped_by(), "a capped level with no explanation"


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
    assert "api" in p05.message
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
    assert "Quality configuration missing" in p06.message
    # Not L0 either: these services are unreachable from the test machine and
    # P12 cannot be verified at all, so the ladder was never climbed. The old
    # expectation of "L0 - Observed" came from checks that measured nothing.
    assert report.conformance_level == "UNARMED"
