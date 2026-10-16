"""The detection contract — shared types and the detector registry.

WHY THIS MODULE EXISTS, AND WHAT IT FIXES
`loop.py` used to `import retrieval_collapse as rc` and call `rc.collect()` and
`rc.evaluate()` by name, which made the generic orchestrator a RAG orchestrator
(`ARCHITECTURE.md` §1.4 recorded exactly this as unfixed debt). `KNOWN_FAULTS`
hardcoded one fault class to one repair in the loop's own module body, so a
second fault class could not be added without editing the core.

`ROADMAP.md` P6 states the test this has to pass: *each fault is an adapter,
not a fork — a new class supplies a detector, an evidence query set, a repair
action with its inverse and a verification probe, and changes nothing in the
core. If the core has to change, the seam was in the wrong place.* F01 is the
first fault added after P5, so this is that test, and the seam had to be built
before F01 could be added as an adapter rather than a second hardcoded branch.

THE VERDICT ENUM SHRANK, AND THAT IS THE WHOLE TRICK
It used to read `NO_FAULT | RETRIEVAL_COLLAPSE | INSUFFICIENT_EVIDENCE`. The
middle member named one specific fault, which is what made the type
un-shareable — a second detector cannot add a member to someone else's enum.
It was also redundant: *which* fault is already carried by `Detection`'s
`fault_class` and `fault_name` fields, so `RETRIEVAL_COLLAPSE` duplicated
information that lived two fields away. Collapsing it to a generic `FAULT`
removes the coupling and the duplication in one move, and loses nothing: every
caller that wants the specific fault reads `fault_class`.

CONFLICTS FAIL CLOSED
Several detectors may run against the same evidence. If two claim a fault, the
loop reports `INSUFFICIENT_EVIDENCE` rather than picking one, because a repair
chosen by registration order is a guess, and guessing is the symptom-matching
failure this project exists to avoid. In practice F01 and F06 are mutually
exclusive in evidence — F01 means the model never answered, F06 means it
answered from nothing — but the registry must not depend on every future pair
being that tidy.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

PromQL = Callable[[str, str], float | None]


class Verdict(StrEnum):
    NO_FAULT = "NO_FAULT"
    # A detector claimed a fault. WHICH fault is `Detection.fault_class`.
    FAULT = "FAULT"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass
class Evidence:
    """One observation. Carries its own interpretation so a diagnosis can cite it."""

    kind: str
    source: str
    value: Any
    expected: str
    supports_fault: bool

    def render(self) -> str:
        mark = "!!" if self.supports_fault else "ok"
        return f"[{mark}] {self.kind}: {self.value} (expected {self.expected})  <- {self.source}"


@dataclass
class Detection:
    verdict: Verdict
    fault_class: str | None = None
    fault_name: str | None = None
    service: str | None = None
    evidence: list[Evidence] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    @property
    def detected(self) -> bool:
        return self.verdict is Verdict.FAULT

    def citations(self) -> list[str]:
        return [e.render() for e in self.evidence if e.supports_fault]

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": str(self.verdict),
            "fault_class": self.fault_class,
            "fault_name": self.fault_name,
            "service": self.service,
            "reasons": self.reasons,
            "evidence": [
                {"kind": e.kind, "source": e.source, "value": e.value,
                 "expected": e.expected, "supports_fault": e.supports_fault}
                for e in self.evidence
            ],
        }

    def render(self) -> str:
        head = f"Detection: {self.verdict}"
        if self.detected:
            head += f"  {self.fault_class} {self.fault_name} on {self.service}"
        lines = [head, ""]
        lines += [f"  {e.render()}" for e in self.evidence]
        if self.reasons:
            lines += [""] + [f"  - {r}" for r in self.reasons]
        return "\n".join(lines)


# A detector's two functions, as the loop calls them. Deliberately plain
# callables rather than a class: every existing detector is already a module of
# pure functions, and an ABC here would be an interface with one shape and no
# behaviour of its own.
Collect = Callable[[str, PromQL], dict[str, float | None]]
Evaluate = Callable[[dict[str, float | None], bool, float], Detection]


@dataclass(frozen=True)
class DetectorSpec:
    """One fault class, as an adapter: how to see it and what repairs it.

    `repair_action` lives here rather than in a separate table in the loop
    because the detector and the repair are the same decision from the
    workload's point of view, and splitting them is what let `KNOWN_FAULTS`
    drift into the orchestrator's module body.
    """

    fault_class: str
    fault_name: str
    service: str
    collect: Collect
    evaluate: Evaluate
    repair_action: str


class DetectorRegistry:
    """Name → spec. The only way the loop obtains a detector."""

    def __init__(self) -> None:
        self._specs: dict[str, DetectorSpec] = {}

    def register(self, spec: DetectorSpec) -> None:
        if not spec.fault_class:
            raise ValueError("a detector must declare a fault_class")
        if spec.fault_class in self._specs:
            raise ValueError(
                f"detector for {spec.fault_class!r} is already registered; "
                f"the catalogue is assembled in exactly one place"
            )
        if not spec.repair_action:
            raise ValueError(
                f"{spec.fault_class!r} declares no repair_action. A detector "
                f"that can see a fault but names no repair would reach the "
                f"planner and escalate every time, which is worse than absent"
            )
        self._specs[spec.fault_class] = spec

    def specs(self) -> list[DetectorSpec]:
        """Registration order, which is the order the loop evaluates in."""
        return list(self._specs.values())

    def fault_classes(self) -> frozenset[str]:
        return frozenset(self._specs)

    def repair_for(self, fault_class: str) -> str:
        spec = self._specs.get(fault_class)
        return spec.repair_action if spec else ""

    def known_faults(self) -> dict[str, str]:
        """The fault-class → repair-action map, derived rather than declared."""
        return {k: v.repair_action for k, v in self._specs.items()}


registry = DetectorRegistry()


def run_all(
    specs: list[DetectorSpec],
    prometheus_url: str,
    promql: PromQL,
    fast_set_passed: bool,
    fast_set_pass_rate: float,
) -> Detection:
    """Evaluate every detector and return one verdict.

    - exactly one claim  -> that claim
    - several claims      -> INSUFFICIENT_EVIDENCE, naming them. Fail closed:
                             choosing between two live diagnoses by registration
                             order would be a guess dressed as a decision.
    - no claims, fast set passing -> NO_FAULT, even if some detector could not
                             read its signals. See below; this is not laxity.
    - no claims, fast set failing -> the merged INSUFFICIENT_EVIDENCE, because
                             there IS a symptom and nothing could explain it.

    A MISSING SERIES IS NOT A SYMPTOM, AND TREATING IT AS ONE IS A FALSE ALARM
    The first version of this returned INSUFFICIENT_EVIDENCE whenever any
    detector could not read its own signals, on the reasoning that it had not
    cleared the system. The test suite caught what that actually does: on a
    quiet target with no recent LLM traffic, F01's error-ratio series is empty,
    so a perfectly healthy system escalated. Every healthy run would page a
    human, and a gate that cries wolf is a gate someone turns off.

    The rule applied instead is the one both detectors already state in their
    own bodies: the fast set is measured NOW, the metric windows lag, so if the
    set passes the system is serving correctly at this moment whatever the
    windows remember or fail to remember. Absent evidence only matters once
    there is something to explain.
    """
    claims: list[Detection] = []
    others: list[Detection] = []
    for spec in specs:
        d = spec.evaluate(
            spec.collect(prometheus_url, promql), fast_set_passed, fast_set_pass_rate
        )
        (claims if d.detected else others).append(d)

    if len(claims) == 1:
        return claims[0]

    if len(claims) > 1:
        merged = Detection(Verdict.INSUFFICIENT_EVIDENCE)
        for d in claims:
            merged.evidence.extend(d.evidence)
            merged.reasons.extend(d.reasons)
        named = ", ".join(f"{d.fault_class} {d.fault_name}" for d in claims)
        merged.reasons.insert(
            0,
            f"{len(claims)} detectors claimed a fault at once ({named}). No "
            f"repair is proposed from an ambiguous diagnosis: picking one by "
            f"registration order would be a guess, and the wrong repair is "
            f"worse than none",
        )
        return merged

    insufficient = [d for d in others
                    if d.verdict is Verdict.INSUFFICIENT_EVIDENCE]
    if insufficient and not fast_set_passed:
        merged = Detection(Verdict.INSUFFICIENT_EVIDENCE)
        for d in insufficient:
            merged.evidence.extend(d.evidence)
            merged.reasons.extend(d.reasons)
        return merged

    merged = Detection(Verdict.NO_FAULT)
    for d in others:
        merged.evidence.extend(d.evidence)
        merged.reasons.extend(d.reasons)
    if insufficient:
        merged.reasons.append(
            f"{len(insufficient)} detector(s) could not read their own signals, "
            f"but the fast set passes now, so the system is serving correctly "
            f"and a missing series is not a symptom"
        )
    return merged
