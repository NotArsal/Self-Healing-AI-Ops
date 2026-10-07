import sys
from pathlib import Path

from kavach.preflight.checker import PreflightChecker


def main():
    if len(sys.argv) < 2:
        print("Usage: python onboard.py <path_to_kavach.yaml>")
        sys.exit(1)

    path = Path(sys.argv[1])
    try:
        with open(path) as f:
            manifest_yaml = f.read()
    except Exception as e:
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


if __name__ == "__main__":
    main()
