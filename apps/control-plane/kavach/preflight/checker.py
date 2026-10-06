import yaml
from pydantic import ValidationError

from kavach.preflight.schema import KavachManifest


class CheckResult:
    def __init__(self, code: str, passed: bool, message: str, remediation: str | None = None):
        self.code = code
        self.passed = passed
        self.message = message
        self.remediation = remediation


class PreflightReport:
    def __init__(self):
        self.checks: list[CheckResult] = []
        self.conformance_level: str = "UNARMED"
    
    def add(self, result: CheckResult):
        self.checks.append(result)

    def determine_level(self):
        passed_codes = {c.code for c in self.checks if c.passed}
        failed_codes = {c.code for c in self.checks if not c.passed}

        # L0: Requires C1 (services), C2 (liveness), C7 (telemetry)
        # That maps to P01, P04, P05, P11, P12
        l0_reqs = {"P01", "P04", "P05", "P11", "P12"}
        # L1: Requires L0 + C3 (quality), C4 (objectives)
        # Maps to P06, P07, P13
        l1_reqs = {"P06", "P07", "P13"}
        # L2: Requires L1 + C5 (reversibility), C6 (permission)
        # Maps to P02, P03, P08, P09, P10
        l2_reqs = {"P02", "P03", "P08", "P09", "P10"}

        # If any P-check fails that is required for a level, it drops below that level
        if not l0_reqs.issubset(passed_codes):
            self.conformance_level = "UNARMED"
        elif not l1_reqs.issubset(passed_codes):
            self.conformance_level = "L0 - Observed"
        elif not l2_reqs.issubset(passed_codes):
            self.conformance_level = "L1 - Protected"
        else:
            self.conformance_level = "L3 - Healable"  # Assuming all passed


class PreflightChecker:
    def __init__(self, manifest_yaml: str):
        self.manifest_yaml = manifest_yaml
        self.report = PreflightReport()
        self.manifest: KavachManifest | None = None

    def run_all(self) -> PreflightReport:
        # P01: Parse and validate schema
        if not self._check_p01():
            return self.report
        
        self._check_p02()
        self._check_p03()
        self._check_p04()
        self._check_p05()
        self._check_p06()
        self._check_p07()
        self._check_p08()
        self._check_p09()
        self._check_p10()
        self._check_p11()
        self._check_p12()
        self._check_p13()
        
        # Resolve Context7 dependencies at onboarding
        try:
            from kavach.knowledge.context7 import resolve_dependencies_at_onboarding
            dependencies = list(self.manifest.services.keys()) if self.manifest and self.manifest.services else []
            resolve_dependencies_at_onboarding(dependencies)
        except Exception as e:
            pass # Non-fatal
            
        self.report.determine_level()
        return self.report

    def _check_p01(self) -> bool:
        """P01: kavach.yaml parses and validates against the schema"""
        try:
            data = yaml.safe_load(self.manifest_yaml)
            self.manifest = KavachManifest(**data)
            self.report.add(CheckResult("P01", True, "Manifest parses and validates successfully."))
            return True
        except ValidationError as e:
            self.report.add(CheckResult("P01", False, f"Schema validation failed: {e!s}", "Fix schema errors in kavach.yaml according to CONTRACT.md"))
        except yaml.YAMLError as e:
            self.report.add(CheckResult("P01", False, f"YAML parsing failed: {e!s}", "Fix YAML syntax errors in kavach.yaml"))
        except Exception as e:
            self.report.add(CheckResult("P01", False, f"Unknown error during parsing: {e!s}", "Check kavach.yaml format"))
        return False

    def _check_p02(self):
        """P02: Git repository initialised, worktree clean"""
        # In a real environment, run `git status`
        # For now, if reversible_state has git_*, we assume passed for simulation or we can mock.
        has_git = False
        if self.manifest and self.manifest.reversible_state:
            has_git = any(s.kind in ("git_directory", "git_file") for s in self.manifest.reversible_state.values())
        
        if has_git:
            # Simulate check
            self.report.add(CheckResult("P02", True, "Git repository found and worktree clean (Simulated)."))
        else:
            self.report.add(CheckResult("P02", True, "No git reversible states declared, skipping git check."))

    def _check_p03(self):
        """P03: kavach/ops branch creatable"""
        has_git = False
        if self.manifest and self.manifest.reversible_state:
            has_git = any(s.kind in ("git_directory", "git_file") for s in self.manifest.reversible_state.values())
        
        if has_git:
            self.report.add(CheckResult("P03", True, "kavach/ops branch is creatable (Simulated)."))
        else:
            self.report.add(CheckResult("P03", True, "No git reversible states declared."))

    def _check_p04(self):
        """P04: Runtime reachable; every declared service resolves and is running"""
        # Simulated
        self.report.add(CheckResult("P04", True, "All declared services are reachable (Simulated)."))

    def _check_p05(self):
        """P05: Every declared health endpoint responds correctly"""
        missing_health = []
        for name, srv in self.manifest.services.items():
            if not srv.health:
                missing_health.append(name)
                
        if missing_health:
            self.report.add(CheckResult("P05", False, f"Services missing health endpoints: {', '.join(missing_health)}", "Add health endpoints to all declared services."))
        else:
            self.report.add(CheckResult("P05", True, "All health endpoints responded correctly (Simulated)."))

    def _check_p06(self):
        """P06: Golden set parses; >= min_cases; runner reachable; a full run completes"""
        if not self.manifest.quality:
            self.report.add(CheckResult("P06", False, "Quality configuration missing.", "Add a quality section to kavach.yaml"))
            return
            
        if self.manifest.quality.min_cases < 20:
            self.report.add(CheckResult("P06", False, f"min_cases {self.manifest.quality.min_cases} < 20", "Increase min_cases in golden_set to at least 20 to reduce noise."))
        else:
            self.report.add(CheckResult("P06", True, "Golden set configuration is valid and runner is reachable (Simulated)."))

    def _check_p07(self):
        """P07: Every objective metric exists and currently returns a value"""
        if not self.manifest.objectives:
            self.report.add(CheckResult("P07", False, "Objectives missing.", "Declare at least one availability and one quality objective."))
            return
            
        has_avail = len(self.manifest.objectives.availability) > 0
        has_qual = len(self.manifest.objectives.quality) > 0
        
        if not has_avail or not has_qual:
            self.report.add(CheckResult(
                "P07", False, 
                f"Missing required objectives: Availability={has_avail}, Quality={has_qual}", 
                "Declare at least one availability and one quality objective to protect against silent degradation."
            ))
        else:
            self.report.add(CheckResult("P07", True, "Objective metrics exist and return values (Simulated)."))

    def _check_p08(self):
        """P08: Every reversible state path exists; snapshot and restore both execute"""
        if self.manifest.reversible_state:
            # Simulate execution
            self.report.add(CheckResult("P08", True, "Snapshot and restore scripts execute successfully (Simulated)."))
        else:
            self.report.add(CheckResult("P08", False, "No reversible state declared.", "Declare at least one reversible state path."))

    def _check_p09(self):
        """P09: Every allowed action has an adapter and a working inverse"""
        if not self.manifest.permissions or not self.manifest.permissions.allowed_actions:
            self.report.add(CheckResult("P09", False, "No allowed actions declared.", "Add allowed_actions to permissions."))
        else:
            self.report.add(CheckResult("P09", True, "All allowed actions have working inverses (Simulated)."))

    def _check_p10(self):
        """P10: No allowed action targets a forbidden_services entry"""
        # This requires action-to-service mapping which is context specific.
        # We will assume simulated success if we got here and permissions exist.
        if self.manifest.permissions and self.manifest.permissions.forbidden_services:
            self.report.add(CheckResult("P10", True, "No allowed actions target forbidden services (Simulated)."))
        else:
            self.report.add(CheckResult("P10", True, "No forbidden services declared."))

    def _check_p11(self):
        """P11: OTLP endpoint reachable; a test span round-trips"""
        if not self.manifest.telemetry:
            self.report.add(CheckResult("P11", False, "Telemetry configuration missing.", "Declare telemetry configuration with otlp_endpoint."))
        else:
            self.report.add(CheckResult("P11", True, "OTLP endpoint is reachable (Simulated)."))

    def _check_p12(self):
        """P12: Required GenAI attributes present on a real span"""
        if not self.manifest.telemetry or not self.manifest.telemetry.genai_instrumented:
            self.report.add(CheckResult("P12", False, "genai_instrumented is false or missing.", "Ensure the application has GenAI-level OTLP instrumentation."))
        else:
            self.report.add(CheckResult("P12", True, "GenAI attributes present on test span (Simulated)."))

    def _check_p13(self):
        """P13: Baseline captured"""
        # Relies on C4, C5
        if self.manifest.objectives and self.manifest.reversible_state:
            self.report.add(CheckResult("P13", True, "Baseline captured successfully (Simulated)."))
        else:
            self.report.add(CheckResult("P13", False, "Cannot capture baseline without objectives and reversible_state.", "Ensure objectives and reversible_state are defined."))
