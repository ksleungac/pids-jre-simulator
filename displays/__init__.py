"""Train display system.

Provides display rendering for different train models with support for
multiple display modes (KANJI, FURIGANA, ENGLISH). Top-level façade for
the multi-model factory pattern — see `displays/train_models/__init__.py`
for the registry it pairs with.

Intended usage once wired in:

    from displays import get_train_display, DisplayMode
    from displays.utils import draw_text, draw_text_given_width

    display = get_train_display("e235_1000", screen, route_data, stops)
    display.update(current_time)
    display.draw()
"""

# NOTE: deliberately NOT consumed by `app.py` YET.
#
# Why no caller today: only one train model exists, so `app.py` and the
# LCD modules reach into submodules directly (`displays.base`,
# `displays.utils`, `displays.train_models.e235_1000`). The re-exports
# below form the public façade the application is meant to import from
# once the multi-model factory pattern (paired with the registry in
# `displays/train_models/__init__.py`) becomes load-bearing.
#
# When to wire it in: when a SECOND train model lands and `app.py` starts
# calling `get_train_display(...)`, switch other call sites in `app.py`
# and the test harness to import from `displays` directly so the façade
# becomes the canonical public surface.

from displays.base import DisplayMode, ModeCycler
from displays.utils import draw_text, draw_text_given_width
from displays.train_models import get_train_display

__all__ = [
    "DisplayMode",
    "ModeCycler",
    "get_train_display",
    "draw_text",
    "draw_text_given_width",
]
