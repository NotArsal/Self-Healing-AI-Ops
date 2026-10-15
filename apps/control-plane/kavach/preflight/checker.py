"""Preflight P01-P14: what the platform can actually verify about an application.

Every check from P02 to P13 used to report `PASS ... (Simulated)` on the strength
of a declaration alone, including "P13: Baseline captured successfully
(Simulated)" directly above the code that really captures one. Any manifest that
parsed was certified `L3 - Healable`, which is the strongest claim the contract
can make about an application.

Three outcomes now, not two. A check that measured what it claims is PASS, one
that measured a failure is FAIL, and one the platform cannot measure is
UNVERIFIED -- and UNVERIFIED does not satisfy a conformance level. An
unverifiable obligation and a satisfied one being indistinguishable is the same
defect as proof #2's #5, one layer up.

Checks needing the filesystem or the network require `manifest_path`. Without it
(a manifest supplied as a bare string, as the tests do) they report UNVERIFIED
rather than inventing a result.
"""

import socket
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import yaml
from pydantic import ValidationError

from kavach.preflight.schema import KavachManifest

if TYPE_CHECKING:
    # Imported for typing only: scenarios.schema imports preflight.schema, and
    # preflight/__init__ imports this module, so a real import here is a cycle
    # that resolves or not depending on which package is imported first.
    from kavach.scenarios.schema import TargetBinding

TIMEOUT_S = 5.0
NO_PATH = (
    "not verified: no manifest path was supplied, so nothing could be probed "
    "from disk or over the network"
)


class CheckResult:
    def __init__(
        self,
        code: str,
        passed: bool,
        message: str,
        remediation: str | None = None,
        verified: bool = True,
    ):
        self.code = code
        self.passed = passed
        self.message = message
        self.remediation = remediation
        # False means the platform could not establish the claim either way. It
        # is not a pass, and determine_level will not count it as one.
        self.verified = verified

    @property
    def status(self) -> str:
        if not self.passed:
            return "FAIL"
        return "PASS" if self.verified else "UNVERIFIED"


class PreflightReport:
    def __init__(self) -> None:
        self.checks: list[CheckResult] = []
        self.conformance_level: str = "UNARMED"
        self._capped_by: list[str] = []

    def add(self, result: CheckResult) -> None:
        self.checks.append(result)

    def determine_level(self) -> None:
        # Only a measured pass counts. A check the platform could not verify
        # leaves the obligation unproven, and an unproven obligation cannot earn
        # a level -- that is the whole content of a conformance claim.
        passed_codes = {c.code for c in self.checks if c.passed and c.verified}

        # L0: Requires C1 (services), C2 (liveness), C7 (telemetry)
        # That maps to P01, P04, P05, P11, P12
        l0_reqs = {"P01", "P04", "P05", "P11", "P12"}
        # L1: Requires L0 + C3 (quality), C4 (objectives)
        # Maps to P06, P07, P13
        l1_reqs = {"P06", "P07", "P13"}
        # L2: Requires L1 + C5 (reversibility), C6 (permission)
        # Maps to P02, P03, P08, P09, P10
        l2_reqs = {"P02", "P03", "P08", "P09", "P10"}

        if not l0_reqs.issubset(passed_codes):
            self.conformance_level = "UNARMED"
            self._capped_by = sorted(l0_reqs - passed_codes)
        elif not l1_reqs.issubset(passed_codes):
            self.conformance_level = "L0 - Observed"
            self._capped_by = sorted(l1_reqs - passed_codes)
        elif not l2_reqs.issubset(passed_codes):
            self.conformance_level = "L1 - Protected"
            self._capped_by = sorted(l2_reqs - passed_codes)
        else:
            self.conformance_level = "L3 - Healable"
            self._capped_by = []

    def unverified(self) -> list[CheckResult]:
        return [c for c in self.checks if c.status == "UNVERIFIED"]

    def level_capped_by(self) -> list[CheckResult]:
        """The checks standing between this application and the next level.

        Without this, a level is a verdict with no appeal. Some of these will be
        the application's to fix and some will be the platform's -- P12 cannot
        pass for anyone until span ingestion exists -- and the onboarder is
        entitled to know which they are looking at.
        """
        by_code = {c.code: c for c in self.checks}
        return [by_code[code] for code in self._capped_by if code in by_code]


def _tcp_reachable(host: str, port: int, timeout: float = TIMEOUT_S) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _host_port(target: str, default_port: int) -> tuple[str, int]:
    """Split host:port or a URL. Accepts both; manifests use both."""
    if "://" in target:
        parsed = urlparse(target)
        return parsed.hostname or "", parsed.port or (
            443 if parsed.scheme == "https" else default_port
        )
    host, _, port = target.rpartition(":")
    if not host:
        return target, default_port
    return host, int(port) if port.isdigit() else default_port


class PreflightChecker:
    def __init__(self, manifest_yaml: str, manifest_path: Path | str | None = None):
        self.manifest_yaml = manifest_yaml
        self.manifest_path = Path(manifest_path) if manifest_path else None
        self.report = PreflightReport()
        self.manifest: KavachManifest | None = None

    # -- helpers ----------------------------------------------------------

    def _target(self) -> "TargetBinding | None":
        """A TargetBinding for the live probes, or None if we have no path."""
        if self.manifest_path is None or self.manifest is None:
            return None
        from kavach.scenarios.schema import TargetBinding

        return TargetBinding(
            manifest=self.manifest, manifest_path=str(self.manifest_path)
        )

    def _unverified(self, code: str, message: str = NO_PATH) -> None:
        self.report.add(CheckResult(code, True, message, verified=False))

    def _git_states(self) -> list[tuple[str, object]]:
        if not self.manifest or not self.manifest.reversible_state:
            return []
        return [
            (name, s)
            for name, s in self.manifest.reversible_state.items()
            if s.kind in ("git_directory", "git_file")
        ]

    def _git(self, *args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
        # check=False: a non-zero exit is an answer here, not an error.
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

    # -- checks -----------------------------------------------------------

    def run_all(self) -> PreflightReport:
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
        self._check_p14()

        # Resolve Context7 dependencies at onboarding
        try:
            from kavach.knowledge.context7 import resolve_dependencies_at_onboarding

            dependencies = []
            if self.manifest and self.manifest.dependencies:
                dependencies = [d.name for d in self.manifest.dependencies]
            resolve_dependencies_at_onboarding(dependencies)
        except Exception:
            pass  # Non-fatal

        self.report.determine_level()
        return self.report

    def _check_p01(self) -> bool:
        """P01: kavach.yaml parses and validates against the schema"""
        try:
            data = yaml.safe_load(self.manifest_yaml)
            self.manifest = KavachManifest(**data)
            self.report.add(
                CheckResult("P01", True, "Manifest parses and validates successfully.")
            )
            return True
        except ValidationError as e:
            self.report.add(
                CheckResult(
                    "P01",
                    False,
                    f"Schema validation failed: {e!s}",
                    "Fix schema errors in kavach.yaml according to CONTRACT.md",
                )
            )
        except yaml.YAMLError as e:
            self.report.add(
                CheckResult(
                    "P01",
                    False,
                    f"YAML parsing failed: {e!s}",
                    "Fix YAML syntax errors in kavach.yaml",
                )
            )
        except Exception as e:
            self.report.add(
                CheckResult(
                    "P01",
                    False,
                    f"Unknown error during parsing: {e!s}",
                    "Check kavach.yaml format",
                )
            )
        return False

    def _check_p02(self) -> None:
        """P02: Git repository initialised, worktree clean"""
        states = self._git_states()
        if not states:
            self.report.add(
                CheckResult(
                    "P02", True, "No git reversible states declared, nothing to check."
                )
            )
            return
        if self.manifest_path is None:
            self._unverified("P02")
            return

        base = self.manifest_path.parent
        for name, state in states:
            path = (base / (state.path or ".")).resolve()  # type: ignore[attr-defined]
            repo = path if path.is_dir() else path.parent
            if not repo.exists():
                self.report.add(
                    CheckResult(
                        "P02", False, f"reversible_state '{name}' path missing: {repo}",
                        "Create the declared path or correct it in kavach.yaml.",
                    )
                )
                return
            try:
                rev = self._git("rev-parse", "--is-inside-work-tree", cwd=repo)
                if rev.returncode != 0:
                    self.report.add(
                        CheckResult(
                            "P02", False, f"{repo} is not inside a git worktree",
                            "Run `git init` in the declared reversible_state path.",
                        )
                    )
                    return
                dirty = self._git("status", "--porcelain", cwd=repo)
            except (OSError, subprocess.SubprocessError) as e:
                self._unverified("P02", f"not verified: could not run git: {e}")
                return
            if dirty.stdout.strip():
                n = len(dirty.stdout.strip().splitlines())
                self.report.add(
                    CheckResult(
                        "P02", False, f"{repo} has {n} uncommitted change(s)",
                        "Commit or stash the worktree; Kavach will not write over "
                        "uncommitted work.",
                    )
                )
                return
        self.report.add(
            CheckResult("P02", True, f"git worktree clean for {len(states)} state(s).")
        )

    def _check_p03(self) -> None:
        """P03: kavach/ops branch creatable"""
        states = self._git_states()
        if not states:
            self.report.add(CheckResult("P03", True, "No git reversible states declared."))
            return
        if self.manifest_path is None:
            self._unverified("P03")
            return

        base = self.manifest_path.parent
        path = (base / (states[0][1].path or ".")).resolve()  # type: ignore[attr-defined]
        repo = path if path.is_dir() else path.parent
        try:
            # Nothing is created: the question is whether the name is free or
            # already a branch, and whether HEAD exists to branch from.
            head = self._git("rev-parse", "--verify", "HEAD", cwd=repo)
            if head.returncode != 0:
                self.report.add(
                    CheckResult(
                        "P03", False, f"{repo} has no commits to branch from",
                        "Make an initial commit so kavach/ops can be created.",
                    )
                )
                return
            existing = self._git(
                "rev-parse", "--verify", "--quiet", "refs/heads/kavach/ops", cwd=repo
            )
        except (OSError, subprocess.SubprocessError) as e:
            self._unverified("P03", f"not verified: could not run git: {e}")
            return
        state = "already exists" if existing.returncode == 0 else "is creatable"
        self.report.add(CheckResult("P03", True, f"kavach/ops {state} in {repo}."))

    def _check_p04(self) -> None:
        """P04: Runtime reachable; every declared service resolves and is running"""
        assert self.manifest is not None
        unreachable, unprobeable = [], []
        for name, srv in self.manifest.services.items():
            if not srv.health:
                unprobeable.append(f"{name} (no health target declared)")
                continue
            host, port = _host_port(srv.health.target, 80)
            if not host:
                unprobeable.append(f"{name} (health target has no host)")
                continue
            if not _tcp_reachable(host, port, srv.health.timeout_s or TIMEOUT_S):
                unreachable.append(f"{name} ({host}:{port})")

        if unreachable:
            self.report.add(
                CheckResult(
                    "P04", False, f"Services not reachable: {', '.join(unreachable)}",
                    "Start the application before onboarding; Kavach cannot "
                    "baseline or protect what it cannot reach.",
                )
            )
            return
        if unprobeable:
            self._unverified(
                "P04",
                "not verified: reachable services responded, but these could not "
                f"be probed: {', '.join(unprobeable)}",
            )
            return
        self.report.add(
            CheckResult(
                "P04", True,
                f"All {len(self.manifest.services)} declared service(s) accepted a "
                "connection.",
            )
        )

    def _check_p05(self) -> None:
        """P05: Every declared health endpoint responds correctly"""
        assert self.manifest is not None
        missing = [n for n, s in self.manifest.services.items() if not s.health]
        if missing:
            self.report.add(
                CheckResult(
                    "P05", False,
                    f"Services missing health endpoints: {', '.join(missing)}",
                    "Add health endpoints to all declared services.",
                )
            )
            return

        target = self._target()
        if target is None:
            self._unverified("P05")
            return

        from kavach.verification.live import probe_health

        results = probe_health(target)
        unhealthy = [n for n, v in results.items() if v == "unhealthy"]
        unknown = [n for n, v in results.items() if v == "unknown"]
        if unhealthy:
            self.report.add(
                CheckResult(
                    "P05", False,
                    f"Health endpoints did not respond as declared: "
                    f"{', '.join(unhealthy)}",
                    "Fix the service or correct expect_status in kavach.yaml.",
                )
            )
            return
        if unknown:
            self._unverified(
                "P05",
                "not verified: http endpoints responded as declared, but these use "
                f"a check type this platform does not probe: {', '.join(unknown)}",
            )
            return
        self.report.add(
            CheckResult("P05", True, f"All {len(results)} health endpoint(s) responded "
                                     "with their declared status.")
        )

    def _check_p06(self) -> None:
        """P06: Golden set parses; >= min_cases; runner reachable; a full run completes"""
        assert self.manifest is not None
        if not self.manifest.quality:
            self.report.add(
                CheckResult(
                    "P06", False, "Quality configuration missing.",
                    "Add a quality section to kavach.yaml",
                )
            )
            return
        if self.manifest.quality.min_cases < 20:
            self.report.add(
                CheckResult(
                    "P06", False, f"min_cases {self.manifest.quality.min_cases} < 20",
                    "Increase min_cases in golden_set to at least 20 to reduce noise.",
                )
            )
            return

        target = self._target()
        if target is None:
            self._unverified("P06")
            return

        from kavach.verification.live import LiveProbeError, measure_eval_pass_rate

        try:
            # A real run of the declared golden set against the running
            # application. This is the check's actual claim, and it was the one
            # most worth faking: a golden set that does not run cannot detect a
            # quality regression, which is the whole of conformance level L1.
            rate = measure_eval_pass_rate(target)
        except LiveProbeError as e:
            self.report.add(
                CheckResult(
                    "P06", False, f"Golden set did not run: {e}",
                    "Fix the golden_set path, min_cases or the runner target.",
                )
            )
            return
        self.report.add(
            CheckResult(
                "P06", True,
                f"Golden set ran against the application; pass rate {rate:.3f}.",
            )
        )

    def _check_p07(self) -> None:
        """P07: Every objective metric exists and currently returns a value"""
        assert self.manifest is not None
        if not self.manifest.objectives:
            self.report.add(
                CheckResult(
                    "P07", False, "Objectives missing.",
                    "Declare at least one availability and one quality objective.",
                )
            )
            return

        has_avail = len(self.manifest.objectives.availability) > 0
        has_qual = len(self.manifest.objectives.quality) > 0
        if not has_avail or not has_qual:
            self.report.add(
                CheckResult(
                    "P07", False,
                    f"Missing required objectives: Availability={has_avail}, "
                    f"Quality={has_qual}",
                    "Declare at least one availability and one quality objective to "
                    "protect against silent degradation.",
                )
            )
            return

        from kavach.verification.live import (
            LiveProbeError,
            measure_objectives,
            unmeasurable_metrics,
        )

        unmeasurable = sorted(set(unmeasurable_metrics(self.manifest)))
        target = self._target()
        if target is None:
            self._unverified("P07")
            return

        try:
            measured = measure_objectives(target)
        except LiveProbeError as e:
            self.report.add(
                CheckResult(
                    "P07", False, f"Declared objectives could not be measured: {e}",
                    "Fix the runner or health targets the objectives are probed "
                    "through.",
                )
            )
            return

        if unmeasurable:
            # CONTRACT 5.1: an unmeasurable objective must not be reported as
            # satisfied. Verification skips it, so nothing it protects is
            # protected.
            self._unverified(
                "P07",
                f"not verified: measured {', '.join(sorted(measured))}, but these "
                f"declared metrics cannot be probed and will never be verified: "
                f"{', '.join(unmeasurable)}",
            )
            return
        pretty = ", ".join(f"{k}={v:.3f}" for k, v in sorted(measured.items()))
        self.report.add(
            CheckResult("P07", True, f"Every declared objective returned a value ({pretty}).")
        )

    def _check_p08(self) -> None:
        """P08: Every reversible state path exists; snapshot and restore both execute"""
        assert self.manifest is not None
        if not self.manifest.reversible_state:
            self.report.add(
                CheckResult(
                    "P08", False, "No reversible state declared.",
                    "Declare at least one reversible state path.",
                )
            )
            return

        from kavach.remediation.runtime_config import RuntimeConfigError, read_value

        read_ok, unprobeable, failures = [], [], []
        for name, state in self.manifest.reversible_state.items():
            if state.kind != "runtime_config":
                # Running snapshot_cmd/restore_cmd at onboarding would mutate the
                # application to find out whether it can be mutated. Declining to
                # is a limit, not a pass.
                unprobeable.append(f"{name} ({state.kind})")
                continue
            try:
                value = read_value(state)
                read_ok.append(f"{name}={value}")
            except RuntimeConfigError as e:
                failures.append(f"{name}: {e}")

        if failures:
            self.report.add(
                CheckResult(
                    "P08", False,
                    "Reversible state could not be read: " + "; ".join(failures),
                    "Fix the read endpoint and field, per CONTRACT.md 6.1.",
                )
            )
            return
        if unprobeable:
            self._unverified(
                "P08",
                (f"not verified: read {', '.join(read_ok)}; " if read_ok else
                 "not verified: ")
                + f"these kinds are not probed at onboarding because doing so "
                f"would mutate the application: {', '.join(unprobeable)}",
            )
            return
        self.report.add(
            CheckResult("P08", True, f"Reversible state readable: {', '.join(read_ok)}.")
        )

    def _check_p09(self) -> None:
        """P09: Every allowed action has an adapter and a working inverse"""
        assert self.manifest is not None
        allowed = self.manifest.permissions.allowed_actions if self.manifest.permissions else []
        if not allowed:
            self.report.add(
                CheckResult(
                    "P09", False, "No allowed actions declared.",
                    "Add allowed_actions to permissions.",
                )
            )
            return

        from kavach.catalogue.loader import load_catalogue

        catalogue = load_catalogue()
        unknown, no_inverse = [], []
        for name in allowed:
            act = catalogue.actions.get(name)
            if act is None:
                unknown.append(name)
            elif act.inverse.name != "noop" and act.inverse.name not in catalogue.actions:
                no_inverse.append(f"{name} -> {act.inverse.name}")

        if unknown or no_inverse:
            parts = []
            if unknown:
                parts.append(f"no adapter in the catalogue: {', '.join(unknown)}")
            if no_inverse:
                parts.append(f"inverse not registered: {', '.join(no_inverse)}")
            self.report.add(
                CheckResult(
                    "P09", False, "; ".join(parts),
                    "Remove the action from allowed_actions, or add it to the "
                    "catalogue with a working inverse.",
                )
            )
            return
        self.report.add(
            CheckResult(
                "P09", True,
                f"All {len(allowed)} allowed action(s) resolve to a catalogue adapter "
                "with a registered inverse.",
            )
        )

    def _check_p10(self) -> None:
        """P10: No allowed action targets a forbidden_services entry"""
        assert self.manifest is not None
        forbidden = (
            self.manifest.permissions.forbidden_services if self.manifest.permissions else []
        )
        if not forbidden:
            self.report.add(CheckResult("P10", True, "No forbidden services declared."))
            return
        # Nothing in the catalogue says which service an action touches, so this
        # cannot be decided here. safety/engine.py enforces forbidden_services at
        # execution time; what is missing is the onboarding-time proof.
        self._unverified(
            "P10",
            "not verified: the catalogue declares no action-to-service mapping, so "
            f"whether an allowed action can touch {', '.join(forbidden)} cannot be "
            "decided at onboarding. The gate still enforces it per execution.",
        )

    def _check_p11(self) -> None:
        """P11: OTLP endpoint reachable"""
        assert self.manifest is not None
        if not self.manifest.telemetry:
            self.report.add(
                CheckResult(
                    "P11", False, "Telemetry configuration missing.",
                    "Declare telemetry configuration with otlp_endpoint.",
                )
            )
            return
        host, port = _host_port(self.manifest.telemetry.otlp_endpoint, 4318)
        if not host:
            self.report.add(
                CheckResult(
                    "P11", False,
                    f"otlp_endpoint has no host: {self.manifest.telemetry.otlp_endpoint}",
                    "Give otlp_endpoint a host:port or a URL.",
                )
            )
            return
        if not _tcp_reachable(host, port):
            self.report.add(
                CheckResult(
                    "P11", False, f"OTLP endpoint {host}:{port} refused a connection",
                    "Start the collector, or correct otlp_endpoint.",
                )
            )
            return
        self.report.add(
            CheckResult("P11", True, f"OTLP endpoint {host}:{port} accepted a connection.")
        )

    def _check_p12(self) -> None:
        """P12: Required GenAI attributes present on a real span"""
        assert self.manifest is not None
        if not self.manifest.telemetry or not self.manifest.telemetry.genai_instrumented:
            self.report.add(
                CheckResult(
                    "P12", False, "genai_instrumented is false or missing.",
                    "Ensure the application has GenAI-level OTLP instrumentation.",
                )
            )
            return
        # A declaration is not a span, and there is nothing here to check one
        # against: kavach/telemetry/ and kavach/evidence/ are empty directories,
        # there is no ingestion route, and ARCHITECTURE.md 2.3's GenAI
        # normalisation is unbuilt. This check cannot pass until it exists, and
        # saying so is the only honest outcome.
        required = ", ".join(self.manifest.telemetry.required_attributes) or "none declared"
        self._unverified(
            "P12",
            "not verified: the manifest declares genai_instrumented with required "
            f"attributes [{required}], but this platform has no span ingestion "
            "path to check them against -- no ingestion route and no GenAI "
            "normalisation (ARCHITECTURE.md 2.3). Not a property of your "
            "application.",
        )

    def _check_p13(self) -> None:
        """P13: Baseline captured"""
        assert self.manifest is not None
        if not (self.manifest.objectives and self.manifest.reversible_state):
            self.report.add(
                CheckResult(
                    "P13", False,
                    "Cannot capture baseline without objectives and reversible_state.",
                    "Ensure objectives and reversible_state are defined.",
                )
            )
            return
        if self.manifest_path is None:
            self._unverified("P13")
            return

        from kavach.verification.baseline import load_baseline

        baseline = load_baseline(self.manifest_path)
        if not baseline:
            self.report.add(
                CheckResult(
                    "P13", False, "No healthy baseline has been captured.",
                    "Run `make onboard APP=<app>` with the application healthy; "
                    "without a baseline a degraded repair is scored against the "
                    "outage it replaced and looks like an improvement.",
                )
            )
            return
        pretty = ", ".join(f"{k}={v:.3f}" for k, v in sorted(baseline.items()))
        self.report.add(CheckResult("P13", True, f"Healthy baseline on file ({pretty})."))

    def _check_p14(self) -> None:
        """P14: Exclude unsupported faults based on application roles"""
        from kavach.catalogue.loader import load_catalogue

        if not self.manifest:
            return

        app_roles = self.manifest.active_roles
        full_catalogue = load_catalogue(app_roles=None)

        excluded_faults = []
        for f_class, f_def in full_catalogue.faults.items():
            if f_def.applies_to_roles and not set(f_def.applies_to_roles).intersection(app_roles):
                req_roles = ", ".join(f_def.applies_to_roles)
                excluded_faults.append(f"{f_class} (requires {req_roles})")

        if excluded_faults:
            msg = f"Excluded unsupported fault classes due to missing roles: {', '.join(excluded_faults)}"
        else:
            msg = "All declared fault classes are supported by the application's roles."

        self.report.add(CheckResult("P14", True, msg))
