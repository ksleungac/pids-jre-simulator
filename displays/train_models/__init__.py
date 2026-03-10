"""Train model display modules."""

from displays.train_models.e235_1000 import UpperDisplay as E235_1000UpperDisplay

# Registry of available train model displays (Upper LCD)
TRAIN_DISPLAYS = {
    "e235_1000": E235_1000UpperDisplay,
}


def get_train_display(train_model: str, screen, route_data: dict, stops: list):
    """
    Get upper display instance for specified train model.

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
