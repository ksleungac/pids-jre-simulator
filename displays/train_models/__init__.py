"""Train model display modules.

Holds the model registry + factory for selecting which train series'
displays to instantiate at runtime. See CLAUDE.md "Mental Model" for the
per-model IRL scope policy this is intended to serve.
"""

# NOTE: deliberately NOT called from app.py YET.
#
# Why no caller today: only one train model exists (e235_1000), so
# `app.py` imports `UpperDisplay` / `LowerDisplay` directly from the leaf
# package. The registry + factory are scaffolding for the multi-model
# future where the user picks a series at startup (E235-1000 / E233 /
# E231-500 / ...) and `app.py` queries this factory for the matching
# display classes.
#
# When to wire it in: once a SECOND train model lands, replace the direct
# leaf imports in `app.py` with `get_train_display(...)` calls. At that
# point also extend `TRAIN_DISPLAYS` to include LowerDisplay alongside
# UpperDisplay (currently Upper-only — Lower is co-located but not yet
# part of this registry).

from displays.train_models.e235_1000 import UpperDisplay as E235_1000UpperDisplay

TRAIN_DISPLAYS = {
    "e235_1000": E235_1000UpperDisplay,
}


def get_train_display(train_model: str, screen, route_data: dict, stops: list):
    """Get upper display instance for specified train model.

    Args:
        train_model: Model identifier (e.g., "e235_1000")
        screen: Pygame surface to draw on
        route_data: Route configuration dictionary
        stops: List of stop dictionaries

    Returns:
        UpperDisplay instance for the specified model

    Raises:
        ValueError: If train_model is not registered
    """
    if train_model not in TRAIN_DISPLAYS:
        raise ValueError(f"Unknown train model: {train_model}")

    return TRAIN_DISPLAYS[train_model](screen, route_data, stops)
