# SPDX-License-Identifier: MIT
"""Train model display registry.

Maps a model key (matching both the optional route.json ``model`` field and
the package folder name under ``displays/train_models/``) to that model's
display classes, window dimensions, and human-readable label.

- ``app.py`` resolves the active model here at ``PASimulator`` construction.
  The model is an explicit constructor arg sourced from the setup-screen
  picker (which is seeded from the route's default). ``None`` / unknown →
  the default model.
- ``tims/setup/model_select.py`` reads ``model_choices()`` for the per-route model picker.

Imports are STATIC (not ``importlib``): the ``app.py -> here -> leaf
package`` chain is visible to PyInstaller's static analyzer, so every model
package is bundled automatically — no ``--hidden-import`` in the build. A
dynamic ``import_module`` would be invisible and risk a silent missing-model
in the frozen exe. See critical_lessons.md §4 (deployment-frame divergence).
"""

from collections import namedtuple

from displays.train_models import e235_0, e235_1000

TrainModel = namedtuple("TrainModel", ["key", "label", "upper_cls", "lower_cls", "s_width", "s_height"])

# Insertion order = dropdown order on the setup screen.
TRAIN_MODELS = {
    "e235_1000": TrainModel("e235_1000", "E235-1000", e235_1000.UpperDisplay, e235_1000.LowerDisplay, e235_1000.S_WIDTH, e235_1000.S_HEIGHT),
    "e235_0": TrainModel("e235_0", "E235-0", e235_0.UpperDisplay, e235_0.LowerDisplay, e235_0.S_WIDTH, e235_0.S_HEIGHT),
}

DEFAULT_MODEL_KEY = "e235_1000"


def resolve_model_key(key) -> str:
    """Normalize a possibly-absent/unknown model key to a valid registry key.

    The route.json ``model`` field is optional and free-form, and the
    setup-screen default is seeded from it — anything not in the registry
    (including ``None``) falls back to the default model rather than erroring.
    """
    return key if key in TRAIN_MODELS else DEFAULT_MODEL_KEY


def get_train_model(key) -> TrainModel:
    """Return the ``TrainModel`` record for ``key`` (default if unknown/None)."""
    return TRAIN_MODELS[resolve_model_key(key)]


def model_choices() -> list:
    """Ordered ``(key, label)`` pairs for the setup-screen model picker."""
    return [(m.key, m.label) for m in TRAIN_MODELS.values()]
