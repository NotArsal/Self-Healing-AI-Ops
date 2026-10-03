"""Preflight: the checks that must pass before a project can be enabled.

Every check returns a result rather than raising, so one run reports every
problem instead of only the first. A failing check carries the remediation,
because a preflight that says "failed" without saying what to do is a preflight
nobody runs twice.

No check mutates anything. Preflight is read-only by construction — it runs
against a system nobody has agreed to let Kavach touch yet.
"""

from __future__ import annotations

import socket
import subprocess
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from kavach.onboarding.manifest import Manifest, load


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""
    remediation: str = ""
    # A check that cannot run is not a check that passed.
    skipped: bool = False

    @property
    def symbol(self) -> str:
        if self.skipped:
            return "SKIP"
        return "PASS" if self.passed else "FAIL"


@dataclass
class PreflightReport:
    project: str
    results: list[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """A skipped check blocks enablement. Unknown is not healthy."""
        return all(r.passed and not r.skipped for r in self.results)

    @property
    def blocking(self) -> list[CheckResult]:
        return [r for r in self.results if not r.passed or r.skipped]

    def render(self) -> str:
        lines = [f"Preflight: {self.project}", ""]
        for r in self.results:
            lines.append(f"  [{r.symbol}] {r.name}")
            if r.detail:
                lines.append(f"         {r.detail}")
            if not r.passed and r.remediation:
                lines.append(f"         -> {r.remediation}")
        lines.append("")
        lines.append("RESULT: " + ("PASS" if self.passed else
                                   f"BLOCKED ({len(self.blocking)} check(s))"))
        return "\n".join(lines)


# --- individual checks ------------------------------------------------------


def _http_ok(url: str, timeout: float = 5.0) -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return (200 <= r.status < 400), f"HTTP {r.status}"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except Exception as e:
        return False, str(e)


def _tcp_ok(host: str, port: int, timeout: float = 5.0) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, f"{host}:{port} open"
    except Exception as e:
        return False, str(e)


def check_manifest(path: Path) -> CheckResult:
    try:
        load(path)
        return CheckResult("manifest valid", True, f"{path.name} parsed and validated")
    except Exception as e:
        return CheckResult(
            "manifest valid", False, str(e),
            f"fix {path} until it validates against the kavach/v1 schema",
        )


def check_git(repo: Path, m: Manifest) -> list[CheckResult]:
    out: list[CheckResult] = []

    def git(*args: str) -> tuple[int, str]:
        p = subprocess.run(["git", "-C", str(repo), *args],
                           capture_output=True, text=True)
        return p.returncode, (p.stdout + p.stderr).strip()

    rc, _ = git("rev-parse", "--git-dir")
    if rc != 0:
        out.append(CheckResult(
            "git repository", False, f"{repo} is not a git repository",
            "run `git init` in the target, or correct the configured path"))
        return out
    out.append(CheckResult("git repository", True, str(repo)))

    rc, dirty = git("status", "--porcelain")
    out.append(CheckResult(
        "worktree clean", rc == 0 and not dirty,
        "clean" if not dirty else f"uncommitted changes:\n         {dirty[:200]}",
        "commit or stash the changes; Kavach will not act on a dirty worktree"))

    rc, _ = git("rev-parse", "--verify", m.project.git.base_branch)
    out.append(CheckResult(
        f"base branch {m.project.git.base_branch!r} exists", rc == 0, "",
        f"create {m.project.git.base_branch} or correct project.git.base_branch"))

    rc, head = git("rev-parse", "--abbrev-ref", "HEAD")
    protected = set(m.project.git.protected_branches)
    on_protected = head in protected and head != m.project.git.ops_branch
    out.append(CheckResult(
        "HEAD not on a protected branch", not on_protected, f"HEAD is {head!r}",
        f"git checkout {m.project.git.ops_branch} before enabling"))

    rc, _ = git("rev-parse", "--verify", m.project.git.ops_branch)
    exists = rc == 0
    out.append(CheckResult(
        f"ops branch {m.project.git.ops_branch!r} exists", exists, "",
        f"git branch {m.project.git.ops_branch} {m.project.git.base_branch}"))

    if exists:
        rc, up = git("rev-parse", "--abbrev-ref", "--symbolic-full-name",
                     f"{m.project.git.ops_branch}@{{u}}")
        has_upstream = rc == 0 and up
        out.append(CheckResult(
            "ops branch has no upstream", not has_upstream,
            f"upstream is {up!r}" if has_upstream else "no upstream, push has no target",
            "git branch --unset-upstream "
            f"{m.project.git.ops_branch} - Kavach must never be able to push"))

    return out


def check_services(m: Manifest) -> list[CheckResult]:
    out: list[CheckResult] = []
    for name, svc in m.services.items():
        if not svc.enabled:
            out.append(CheckResult(
                f"service {name!r} health", True,
                f"not enabled (profile {svc.profile!r}); skipped by design"))
            continue
        if not svc.health:
            out.append(CheckResult(
                f"service {name!r} health", False, "no health endpoint declared",
                f"add services.{name}.health to the manifest"))
            continue

        u = urlparse(svc.health)
        if u.scheme in ("http", "https"):
            ok, detail = _http_ok(svc.health)
        elif u.scheme == "tcp":
            ok, detail = _tcp_ok(u.hostname or "localhost", u.port or 0)
        else:
            ok, detail = False, f"unsupported scheme {u.scheme!r}"
        out.append(CheckResult(
            f"service {name!r} health", ok, f"{svc.health} -> {detail}",
            f"start {name}, or correct services.{name}.health"))
    return out


def check_ownership(
    m: Manifest, docker_ps: Callable[[], list[dict[str, str | None]]] | None = None
) -> list[CheckResult]:
    """Every declared container must carry the project's compose-project label.

    This is the check that stops Kavach acting on something it was never
    onboarded against.
    """
    if docker_ps is None:
        docker_ps = _docker_ps

    try:
        containers = docker_ps()
    except Exception as e:
        return [CheckResult(
            "docker socket reachable", False, str(e),
            "start Docker and ensure the socket is mounted into the control plane")]

    out = [CheckResult("docker socket reachable", True,
                       f"{len(containers)} container(s) visible")]

    want = m.project.compose_project
    by_name = {c["name"]: c for c in containers}

    for name, svc in m.services.items():
        if not svc.enabled or not svc.container_name:
            continue
        c = by_name.get(svc.container_name)
        if c is None:
            out.append(CheckResult(
                f"ownership of {svc.container_name!r}", False, "container not found",
                f"start {name}, or correct services.{name}.container_name"))
            continue
        got = c.get("project")
        out.append(CheckResult(
            f"ownership of {svc.container_name!r}", got == want,
            f"compose project {got!r} (expected {want!r})",
            "correct project.compose_project, or point Kavach at the right project"))
    return out


def _docker_ps() -> list[dict[str, str | None]]:
    import docker

    client = docker.from_env()
    try:
        client.ping()
        out: list[dict[str, str | None]] = []
        for c in client.containers.list(all=True):
            labels = c.labels or {}
            out.append({
                "name": c.name,
                "project": labels.get("com.docker.compose.project"),
                "service": labels.get("com.docker.compose.service"),
            })
        return out
    finally:
        client.close()


def check_slo_expressions(m: Manifest, prometheus_url: str) -> list[CheckResult]:
    """Every SLO expression must parse AND evaluate against live Prometheus.

    An expression that is syntactically valid but references a metric nobody
    exports returns an empty result, which is indistinguishable from "healthy"
    and is exactly how a detection layer ends up silently blind.
    """
    import json
    from urllib.parse import quote

    out: list[CheckResult] = []
    for slo in m.slo:
        url = f"{prometheus_url.rstrip('/')}/api/v1/query?query={quote(slo.expression)}"
        try:
            with urllib.request.urlopen(url, timeout=10) as r:
                payload = json.load(r)
        except Exception as e:
            out.append(CheckResult(
                f"SLO {slo.name!r} evaluates", False, str(e),
                f"check Prometheus is reachable at {prometheus_url}"))
            continue

        if payload.get("status") != "success":
            out.append(CheckResult(
                f"SLO {slo.name!r} evaluates", False,
                payload.get("error", "query rejected"),
                "fix the PromQL expression in kavach.yaml"))
            continue

        result = payload.get("data", {}).get("result", [])
        if not result:
            out.append(CheckResult(
                f"SLO {slo.name!r} evaluates", False,
                "query is valid but returned no series",
                "the referenced metric is not being exported; instrument it or "
                "correct the expression"))
            continue

        value = result[0].get("value", [None, "?"])[1]
        out.append(CheckResult(
            f"SLO {slo.name!r} evaluates", True, f"= {value}"))
    return out


def check_fast_set(m: Manifest, kavach_root: Path) -> CheckResult:
    rel = m.verification.fast.set
    # The set lives in the control plane, not the target.
    candidates = [kavach_root / rel, kavach_root / "apps/control-plane" / rel]
    for p in candidates:
        if p.is_file():
            try:
                import yaml
                doc = yaml.safe_load(p.read_text(encoding="utf-8"))
                n = len(doc.get("cases", []))
                if n != 3:
                    return CheckResult(
                        "fast verification set", False,
                        f"{p.name} declares {n} cases, expected exactly 3",
                        "the live probe is fixed at 3 serial cases")
                return CheckResult("fast verification set", True,
                                   f"{n} cases from {p.name}")
            except Exception as e:
                return CheckResult("fast verification set", False, str(e),
                                   f"fix {p}")
    return CheckResult(
        "fast verification set", False, f"not found: {rel}",
        "create the set in the control plane and select its cases empirically")


# --- the runner -------------------------------------------------------------


def run(target_path: str | Path, prometheus_url: str,
        kavach_root: str | Path = ".") -> PreflightReport:
    """Run every check against a target. Read-only."""
    target = Path(target_path)
    manifest_path = target / "kavach.yaml"

    first = check_manifest(manifest_path)
    if not first.passed:
        return PreflightReport(project=str(target), results=[first])

    m = load(manifest_path)
    report = PreflightReport(project=m.project.name, results=[first])
    report.results += check_git(target, m)
    report.results += check_services(m)
    report.results += check_ownership(m)
    report.results += check_slo_expressions(m, prometheus_url)
    report.results.append(check_fast_set(m, Path(kavach_root)))
    return report
