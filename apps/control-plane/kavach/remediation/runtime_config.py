"""Adapter for `reversible_state.kind: runtime_config` declarations.

This is the only place that mutates a live application's runtime configuration.
It reads the prior value before writing so the inverse is derived from observed
state rather than from what the catalogue *expected* the prior state to be --
the distinction the rollback guarantee rests on (AGENTS.md 4a).
"""

import httpx

from kavach.catalogue.schema import EffectDef
from kavach.httpclient import shared_client
from kavach.preflight.schema import ReversibleStateDef
from kavach.tnr.models import Action, UndoRecord

TIMEOUT_S = 5.0


class RuntimeConfigError(Exception):
    pass


def read_value(rs_def: ReversibleStateDef) -> str:
    """Read the current value, in the application's own vocabulary."""
    if not rs_def.read:
        raise RuntimeConfigError("reversible_state declares no read endpoint")
    if not rs_def.field:
        raise RuntimeConfigError("reversible_state declares no field")

    try:
        res = shared_client().get(rs_def.read, timeout=TIMEOUT_S)
        res.raise_for_status()
        body = res.json()
    except (httpx.HTTPError, ValueError) as e:
        raise RuntimeConfigError(f"read from {rs_def.read} failed: {e}") from e

    if rs_def.field not in body:
        raise RuntimeConfigError(
            f"read from {rs_def.read} returned no '{rs_def.field}' field"
        )
    return str(body[rs_def.field])


def write_value(rs_def: ReversibleStateDef, app_value: str) -> None:
    """Write a value expressed in the application's own vocabulary."""
    if not rs_def.write:
        raise RuntimeConfigError("reversible_state declares no write endpoint")
    if not rs_def.field:
        raise RuntimeConfigError("reversible_state declares no field")

    try:
        res = shared_client().post(
            rs_def.write, json={rs_def.field: app_value}, timeout=TIMEOUT_S
        )
        res.raise_for_status()
    except httpx.HTTPError as e:
        raise RuntimeConfigError(f"write to {rs_def.write} failed: {e}") from e


def _resolve(template: str, params: dict[str, object]) -> str:
    if template.startswith("$"):
        return str(params.get(template[1:], ""))
    return template


def apply_effect(
    effect: EffectDef,
    action: Action,
    rs_def: ReversibleStateDef,
    mode: str,
) -> UndoRecord:
    """Realise `action` against the live application and return its undo record.

    In SIMULATION the prior value is still read -- a read has no side effect and
    the witness is what makes the dry run worth anything -- but nothing is
    written and the record is marked unapplied.
    """
    catalogue_value = _resolve(effect.value, action.params)
    if not catalogue_value:
        raise RuntimeConfigError(
            f"action {action.name} resolved an empty value from '{effect.value}'"
        )

    prior_app_value = read_value(rs_def)
    prior_catalogue_value = rs_def.to_catalogue_value(prior_app_value)

    applied = False
    if mode != "SIMULATION":
        write_value(rs_def, rs_def.to_app_value(catalogue_value))
        applied = True

    # Built from the witness, never from the catalogue's declared fallback: if the
    # app was somewhere unexpected when we arrived, that is where we put it back.
    inverse = Action(
        name=action.name,
        params={**action.params, "target": prior_catalogue_value, "fallback": catalogue_value},
    )

    return UndoRecord(
        original_action=action,
        inverse_action=inverse,
        pre_state_witness={effect.key: prior_app_value},
        applied=applied,
    )


def revert_effect(
    effect: EffectDef,
    record: UndoRecord,
    rs_def: ReversibleStateDef,
    mode: str,
) -> bool:
    """Restore the witnessed prior value and read it back to confirm.

    Returns True when the application reports the witnessed value afterwards. A
    2xx on the write is not evidence the state moved: the undo ablation measured
    a working rollback and no rollback reporting the same outcome, because
    nothing ever checked (docs/MEASUREMENTS.md). A readback that fails counts as
    unconfirmed, and unconfirmed is not restored.

    Idempotent: writing the witnessed value twice is a no-op.
    """
    if mode == "SIMULATION" or not record.applied:
        return True

    witnessed = record.pre_state_witness.get(effect.key)
    if witnessed is None:
        raise RuntimeConfigError(
            f"undo record carries no witness for '{effect.key}'; cannot restore"
        )
    write_value(rs_def, str(witnessed))

    try:
        return read_value(rs_def) == str(witnessed)
    except RuntimeConfigError:
        return False
