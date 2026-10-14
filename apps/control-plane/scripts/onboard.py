import sys
from pathlib import Path

from kavach.preflight.checker import PreflightChecker
from kavach.scenarios.from_manifest import TargetLoadError, load_target
from kavach.verification.baseline import save_baseline
from kavach.verification.live import (
    LiveProbeError,
    measure_objectives,
    unmeasurable_metrics,
)


def capture_baseline(path: Path) -> None:
    """Measure the application while it is healthy.

    Verification compares against this. Without it, a degraded repair is scored
    against the outage it replaced and looks like an improvement, so onboarding
    says plainly when it could not capture one.
    """
    try:
        target = load_target(path)
    except TargetLoadError as e:
        print(f"[WARN] baseline not captured: {e}")
        return

    missing = unmeasurable_metrics(target.manifest)
    if missing:
        print(
            "[WARN] these declared metrics cannot be measured by active probing "
            f"and will not be verified: {', '.join(sorted(set(missing)))}"
        )

    try:
        measured = measure_objectives(target)
    except LiveProbeError as e:
        print(f"[WARN] baseline not captured: {e}")
        return

    if not measured:
        print("[WARN] baseline not captured: no measurable objectives declared")
        return

    saved_to = save_baseline(path, measured)
    pretty = ", ".join(f"{k}={v:.3f}" for k, v in sorted(measured.items()))
    print(f"[PASS] baseline captured ({pretty}) -> {saved_to.name}")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python onboard.py <path_to_kavach.yaml>")
        sys.exit(1)

    path = Path(sys.argv[1])
    try:
        manifest_yaml = path.read_text(encoding="utf-8")
    except OSError as e:
        print(f"Error reading file: {e}")
        sys.exit(1)

    checker = PreflightChecker(manifest_yaml)
    report = checker.run_all()

    print(f"Conformance Level: {report.conformance_level}")
    for c in report.checks:
        icon = "[PASS]" if c.passed else "[FAIL]"
        print(f"{icon} {c.code}: {c.message}")
        if not c.passed and c.remediation:
            print(f"    Remediation: {c.remediation}")

    capture_baseline(path)


if __name__ == "__main__":
    main()
