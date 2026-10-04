from kavach.tnr.models import Action, UndoRecord


class ExecutorError(Exception):
    pass


def execute_action(action: Action, state: dict[str, str]) -> UndoRecord:
    """
    Executes a simulated action. Mutates `state` in place.
    Returns an UndoRecord containing the inverse action and the pre-state witness.
    """
    if action.name == "switch_model":
        # Witness the current model
        target = action.params.get("target", "model_primary")
        fallback = action.params.get("fallback", "model_backup")

        pre_state = {
            target: state.get(target, "unavailable"),
            "active_model": state.get("active_model", target),
        }

        # Mutate
        state["active_model"] = fallback

        inverse_action = Action(name="restore_model", params={"target": target})

        return UndoRecord(
            original_action=action,
            inverse_action=inverse_action,
            pre_state_witness=pre_state,
            applied=True,
        )

    if action.name == "restore_model":
        target = action.params.get("target")
        target_str = str(target) if target else "model_primary"
        # In a real un-wind we might not need an inverse-of-inverse, but for completeness:
        pre_state = {"active_model": state.get("active_model")}
        state["active_model"] = target_str
        return UndoRecord(
            original_action=action,
            inverse_action=Action(name="noop", params={}),
            pre_state_witness=pre_state,
            applied=True,
        )

    raise ExecutorError(f"Unknown simulated action: {action.name}")
