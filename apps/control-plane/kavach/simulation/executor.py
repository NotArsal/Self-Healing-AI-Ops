from kavach.tnr.models import Action, UndoRecord


class ExecutorError(Exception):
    pass


from kavach.catalogue.loader import load_catalogue

def execute_action(action: Action, state: dict[str, str]) -> UndoRecord:
    """
    Executes a simulated action dynamically via Catalogue. Mutates `state` in place.
    Returns an UndoRecord containing the inverse action and the pre-state witness.
    """
    catalogue = load_catalogue()
    
    if action.name not in catalogue.actions:
        raise ExecutorError(f"Unknown action in catalogue: {action.name}")
        
    act_def = catalogue.actions[action.name]
    
    # 1. Capture witness for all mutated keys
    pre_state = {}
    for state_key in act_def.mutations.keys():
        pre_state[state_key] = state.get(state_key, "unavailable") # Default fallback
        
    # We must also capture anything the inverse needs if it's dynamic
    # e.g., if inverse restores target, we need to know what target was.
    # We can just witness the whole state generically or just the mutations
    # Actually, the original implementation did pre_state["active_model"] = state.get("active_model", target)
    if "target" in action.params:
        target_key = action.params["target"]
        if target_key not in pre_state:
            pre_state[target_key] = state.get(target_key, "unavailable")

    # 2. Apply mutations
    for state_key, val_template in act_def.mutations.items():
        if val_template.startswith("$"):
            param_name = val_template[1:]
            state[state_key] = str(action.params.get(param_name, "unknown"))
        else:
            state[state_key] = val_template
            
    # 3. Construct Inverse Action
    inverse_params = {}
    for k, v in act_def.inverse.params_mapping.items():
        if v.startswith("$"):
            param_name = v[1:]
            inverse_params[k] = action.params.get(param_name, "unknown")
        else:
            inverse_params[k] = v
            
    inverse_action = Action(name=act_def.inverse.name, params=inverse_params)
    
    return UndoRecord(
        original_action=action,
        inverse_action=inverse_action,
        pre_state_witness=pre_state,
        applied=True,
    )
