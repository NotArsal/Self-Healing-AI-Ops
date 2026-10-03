"""Parsing and validation for `kavach.yaml`, the onboarding contract.

Validation is strict and total: a manifest either describes a project Kavach
can operate or it is rejected with every problem listed at once. Partial
acceptance is what lets a project reach `ARMED` with an unevaluable SLO or an
ownership key that matches nothing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

Mode = Literal["SIMULATION", "APPROVAL", "AUTONOMOUS"]
Comparator = Literal["<", "<=", ">", ">=", "=="]


class GitContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_branch: str
    ops_branch: str = "kavach/ops"
    push: bool = False
    protected_branches: list[str] = Field(default_factory=lambda: ["main"])

    @field_validator("push")
    @classmethod
    def push_must_be_false(cls, v: bool) -> bool:
        # Not a toggle. There is no push code path, and a manifest claiming
        # otherwise is a manifest describing a system this is not.
        if v:
            raise ValueError("push must be false; Kavach never pushes to a remote")
        return v

    @field_validator("ops_branch")
    @classmethod
    def ops_branch_is_namespaced(cls, v: str) -> str:
        if not v.startswith("kavach/"):
            raise ValueError("ops_branch must be under the kavach/ namespace")
        return v


class ProjectContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    compose_file: str
    compose_project: str
    git: GitContract

    @field_validator("compose_project")
    @classmethod
    def ownership_key_present(cls, v: str) -> str:
        if not v.strip():
            raise ValueError(
                "compose_project is the Docker ownership key and cannot be blank"
            )
        return v.strip()


class ServiceContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str
    container_name: str | None = None
    health: str | None = None
    host_port: int | None = None
    metrics: str | None = None
    profile: str | None = None
    enabled: bool = True


class SloContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    expression: str
    comparator: Comparator
    threshold: float
    window_s: int
    note: str | None = None

    @field_validator("expression")
    @classmethod
    def not_a_bare_metric_name(cls, v: str) -> str:
        """Reject the mistake the previous draft of the spec made.

        A bare metric name with a comparator is not an SLO Kavach can evaluate,
        and `quantile="0.95"` on a histogram silently matches nothing.
        """
        expr = v.strip()
        if not expr:
            raise ValueError("expression is empty")
        if 'quantile="' in expr and "histogram_quantile" not in expr:
            raise ValueError(
                "a `quantile` label on a histogram matches nothing; "
                "use histogram_quantile() over the _bucket series"
            )
        if "status=~" in expr and "5.." in expr:
            raise ValueError(
                'status is bucketed as 2xx/4xx/5xx, not numeric; '
                'status=~"5.." matches nothing - use status="5xx"'
            )
        return expr


class FastVerification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    set: str
    max_duration_s: int = 120
    execution: Literal["serial"] = "serial"

    @field_validator("max_duration_s")
    @classmethod
    def must_fit_the_loop(cls, v: int) -> int:
        # The full detect-to-resolved budget is 180s. A verification probe
        # that can consume all of it cannot be used inside the loop.
        if not (10 <= v <= 150):
            raise ValueError("max_duration_s must be between 10 and 150")
        return v


class FullVerification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runner: str
    schedule_s: int = 0
    requires_cloud_key: bool = False


class VerificationContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fast: FastVerification
    full: FullVerification | None = None


class ControlInterface(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config: str
    auth: str
    auth_env: str
    settable: list[str] = Field(default_factory=list)

    @field_validator("settable")
    @classmethod
    def embed_model_never_settable(cls, v: list[str]) -> list[str]:
        """The single most dangerous setting in this target.

        `db.py` infers the embedding dimension from the model name and runs
        DROP TABLE document_chunks CASCADE when it changes, so a settable
        embed_model is a settable corpus deletion.
        """
        if "embed_model" in v:
            raise ValueError(
                "embed_model must never be settable: changing it makes the "
                "target drop its own document_chunks table"
            )
        return v


class LlmPaths(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary: str
    backup: str | None = None


class LlmContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    model: str
    embedding_model: str
    paths: LlmPaths
    control_plane_path: str
    shared_with_control_plane: bool = False

    @field_validator("control_plane_path")
    @classmethod
    def not_behind_a_proxy(cls, v: str) -> str:
        if "toxiproxy" in v.lower():
            raise ValueError(
                "control_plane_path must not route through the fault-injection "
                "proxy; breaking the target would blind the diagnostician"
            )
        return v


class CorpusFingerprint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunks: int
    files: list[str]


class BaselineContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    captures: list[str] = Field(default_factory=list)
    corpus_fingerprint: CorpusFingerprint | None = None


DENY_ALWAYS = {"embed_model_change", "data_delete", "database_drop",
               "scale_to_zero", "migration"}


class Manifest(BaseModel):
    """A validated `kavach.yaml`."""

    model_config = ConfigDict(extra="forbid")

    # Mixed case is the actual YAML key in kavach.yaml, not a style choice.
    apiVersion: Literal["kavach/v1"]  # noqa: N815
    project: ProjectContract
    services: dict[str, ServiceContract]
    llm: LlmContract | None = None
    slo: list[SloContract]
    verification: VerificationContract
    versioned_paths: dict[str, str] = Field(default_factory=dict)
    control_interface: ControlInterface | None = None
    allowed_actions: list[str] = Field(default_factory=list)
    denied_mutations: list[str] = Field(default_factory=list)
    mode: Mode = "SIMULATION"
    confidence_threshold: float = 0.75
    baseline: BaselineContract | None = None

    @field_validator("slo")
    @classmethod
    def at_least_one_slo(cls, v: list[SloContract]) -> list[SloContract]:
        if not v:
            raise ValueError("at least one SLO is required before enabling")
        names = [s.name for s in v]
        dupes = {n for n in names if names.count(n) > 1}
        if dupes:
            raise ValueError(f"duplicate SLO names: {sorted(dupes)}")
        return v

    @field_validator("denied_mutations")
    @classmethod
    def deny_list_is_complete(cls, v: list[str]) -> list[str]:
        missing = DENY_ALWAYS - set(v)
        if missing:
            raise ValueError(
                f"denied_mutations must include {sorted(missing)}; these are "
                "refused unconditionally and the manifest must say so"
            )
        return v

    @field_validator("allowed_actions")
    @classmethod
    def no_denied_action_allowed(cls, v: list[str]) -> list[str]:
        overlap = set(v) & DENY_ALWAYS
        if overlap:
            raise ValueError(f"allowed_actions contains denied mutations: {sorted(overlap)}")
        return v


def load(path: str | Path) -> Manifest:
    """Read and validate a manifest. Raises on any problem."""
    p = Path(path)
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{p} does not contain a YAML mapping")
    return Manifest.model_validate(raw)
