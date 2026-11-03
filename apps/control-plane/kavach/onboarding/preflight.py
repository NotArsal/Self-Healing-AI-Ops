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
from urllib.parse import urlparse, urlunparse

from kavach.executor.adapters import docker as docker_adapter
from kavach.onboarding.manifest import Manifest, load
from kavach.verification.fast import resolve_set


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
        # STILL FAILS, AND STILL BLOCKS. The console states the rule this
        # follows - "a skipped check blocks enablement, because unknown is
        # not healthy" - and a git state that cannot be read is unknown.
        #
        # Only the wording changed, on 2026-11-03. It used to read
        # "/app/target is not a git repository" and advise `git init`, which
        # is wrong twice over when this runs in the control-plane container:
        # the target IS a repository on the host, and /app/target is a
        # container path holding only the mounted manifest, so `git init`
        # there would create an empty repository that answers nothing. An
        # operator following that remedy would be acting on a false premise.
        mounted_only = (repo / "kavach.yaml").is_file() and not (
            repo / ".git").exists()
        detail = f"no git repository readable at {repo}"
        if mounted_only:
            detail += (" - only the manifest is mounted there, so this is "
                       "the containerised view, not the target's real state")
        out.append(CheckResult(
            "git repository", False, detail,
            "run the host-side preflight (`make onboard`), where the "
            "target's working tree is visible; from the control-plane "
            "container the git checks cannot be performed at all"
            if mounted_only else
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


_LOOPBACK = frozenset({"localhost", "127.0.0.1", "::1"})


def relocate(url: str, host: str) -> tuple[str, bool]:
    """Point a loopback health URL at `host`, keeping port, path and scheme.

    ADDED 2026-11-03, after the console's preflight page reported
    "Preflight blocked - 3 of 20 checks" against a target whose every
    container was up and healthy.

    The manifest describes the target FROM THE HOST: `tcp://localhost:5432`,
    `http://localhost:3000/`. That is the right thing for it to say, because
    the ports are published on the host and a person running `make onboard`
    is standing there. But the control plane answers `GET /v1/preflight`
    from inside a container, where `localhost` is the container itself - so
    the probe asked the control plane whether it was a Postgres, got
    ECONNREFUSED, and reported the target's database down while it was
    serving. The same registry gave two different answers depending on where
    it ran, and the console - the demo surface - gave the wrong one.

    THIS IS AN ADDRESS CORRECTION, NOT A RELAXATION. The probe still opens a
    real socket to a real service; a database that is genuinely down still
    fails this check. Nothing is skipped, no result is assumed, and the
    rewrite is reported in the check's detail so a reader is never told a
    different address was probed than the one that was.

    Only a loopback host is rewritten, and only when `host` is given - which
    the API route does and the host-side CLI does not, so `make onboard`
    keeps probing exactly what it probes today.
    """
    if not host:
        return url, False
    parsed = urlparse(url)
    if (parsed.hostname or "").lower() not in _LOOPBACK:
        return url, False
    netloc = host if parsed.port is None else f"{host}:{parsed.port}"
    if parsed.username:
        creds = parsed.username + (f":{parsed.password}" if parsed.password else "")
        netloc = f"{creds}@{netloc}"
    return urlunparse(parsed._replace(netloc=netloc)), True


def check_services(m: Manifest, service_host: str = "") -> list[CheckResult]:
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

        probe, moved = relocate(svc.health, service_host)
        u = urlparse(probe)
        if u.scheme in ("http", "https"):
            ok, detail = _http_ok(probe)
        elif u.scheme == "tcp":
            ok, detail = _tcp_ok(u.hostname or "localhost", u.port or 0)
        else:
            ok, detail = False, f"unsupported scheme {u.scheme!r}"
        # Say which address was probed when it is not the declared one.
        shown = f"{svc.health} -> {detail}" if not moved else (
            f"{svc.health} probed as {probe} (loopback is this container) "
            f"-> {detail}")
        out.append(CheckResult(
            f"service {name!r} health", ok, shown,
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
    """Containers and their compose labels, through the adapter.

    This opened its own `docker.from_env()` client until 2026-10-20, which
    broke `AGENTS.md` rule 14 - the docker SDK is imported in exactly one
    module so that the most dangerous privilege in the system has one place
    to audit. The listing itself is unchanged.
    """
    return docker_adapter.list_containers()


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


def check_corpus_fingerprint(m: Manifest, kavach_root: Path,
                             prometheus_url: str) -> CheckResult:
    """The live corpus must match the fingerprint the fast set was built on.

    THE GAP THIS CLOSES, which `PRD.md` §12 named and carried to P6 unbuilt:
    the fingerprint was written down in `fast_set.yaml` and nothing ever
    asserted it. The loop's own corpus guard compares before against after
    WITHIN one incident, so absolute drift between sessions stayed invisible.

    It drifted three times and nothing caught any of them: 162 chunks / 3 files
    on 2026-10-04 (a syllabus PDF had been added), 13 / 1 on 2026-10-16 (the
    target's database was reset and `1662.pdf` was gone), and 0 / 0 on
    2026-11-01 after the machine was reformatted.

    The 13/1 case is why this is not cosmetic. Every fast-set case reads from
    those two documents, and the fast set is the post-repair verification the
    loop runs before it may return RESOLVED. On the wrong corpus it FAILS on a
    healthy system, so a correct detection and a correct repair still end in
    `escalated` - which is exactly what was observed that day.

    Read-only, like every other check here.
    """
    import json
    from urllib.parse import quote

    import yaml

    name = "corpus matches the fast set's fingerprint"
    # `resolve_set` is imported rather than re-typed: it and `check_fast_set`
    # must look in the same two places, or one reports on a file the other
    # never reads.
    path = resolve_set(m.verification.fast.set, kavach_root)
    if path is None:
        return CheckResult(name, False, f"fast set not found: "
                           f"{m.verification.fast.set}",
                           "preflight cannot read the expected fingerprint")
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        fp = (doc.get("budget") or {}).get("corpus_fingerprint") or {}
        want_chunks = int(fp["chunks"])
        want_files = fp["files"]
    except Exception as exc:                       # malformed is not a pass
        return CheckResult(name, False, f"{type(exc).__name__}: {exc}",
                           f"declare budget.corpus_fingerprint in {path.name}")

    live: dict[str, float] = {}
    for metric in ("ragapp_corpus_chunks", "ragapp_corpus_files"):
        url = (f"{prometheus_url.rstrip('/')}/api/v1/query"
               f"?query={quote(metric)}")
        try:
            with urllib.request.urlopen(url, timeout=10) as r:
                payload = json.load(r)
            result = payload.get("data", {}).get("result", [])
            if not result:
                return CheckResult(
                    name, False, f"{metric} returned no series",
                    "the target is not exporting corpus metrics; a corpus "
                    "that cannot be read is not a corpus that is correct")
            live[metric] = float(result[0]["value"][1])
        except Exception as exc:
            return CheckResult(name, False, f"{metric}: {exc}",
                               f"check Prometheus is reachable at "
                               f"{prometheus_url}")

    got_chunks = int(live["ragapp_corpus_chunks"])
    got_files = int(live["ragapp_corpus_files"])
    want_n_files = len(want_files) if isinstance(want_files, list) else int(
        want_files)

    if got_chunks != want_chunks or got_files != want_n_files:
        expected_names = (", ".join(want_files)
                          if isinstance(want_files, list) else str(want_files))
        return CheckResult(
            name, False,
            f"live corpus is {got_chunks} chunks / {got_files} files, "
            f"the fast set was built on {want_chunks} / {want_n_files}",
            f"re-ingest the corpus ({expected_names}) until the fingerprint "
            f"matches. Every quality number is measured against this corpus, "
            f"and the fast set fails on a healthy system without it")

    return CheckResult(name, True,
                       f"{got_chunks} chunks / {got_files} files")


# --- the runner -------------------------------------------------------------


def run(target_path: str | Path, prometheus_url: str,
        kavach_root: str | Path = ".",
        service_host: str = "") -> PreflightReport:
    """Run every check against a target. Read-only.

    `service_host` is where the TARGET's published ports can be reached from
    wherever this is running. Empty - the host-side default - probes the
    manifest's addresses verbatim. The API passes the host it already uses to
    reach the target, because inside a container the manifest's `localhost`
    means the container. See `relocate`.
    """
    target = Path(target_path)
    manifest_path = target / "kavach.yaml"

    first = check_manifest(manifest_path)
    if not first.passed:
        return PreflightReport(project=str(target), results=[first])

    m = load(manifest_path)
    report = PreflightReport(project=m.project.name, results=[first])
    report.results += check_git(target, m)
    report.results += check_services(m, service_host)
    report.results += check_ownership(m)
    report.results += check_slo_expressions(m, prometheus_url)
    report.results.append(check_fast_set(m, Path(kavach_root)))
    report.results.append(
        check_corpus_fingerprint(m, Path(kavach_root), prometheus_url))
    return report
