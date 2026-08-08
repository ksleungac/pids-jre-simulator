# SPDX-License-Identifier: MIT
"""TIMS console package — the JR East cab-look UI.

Groups the shared TIMS primitives and both TIMS surfaces:
- ``tims.widgets``  — draw primitives (buttons, low-res AA-off text).
- ``tims.chrome``   — shared vocabulary (PALETTE, button presets, role fonts).
- ``tims.band``     — the persistent status band (setup screens + live in-drive OCR panel).
- ``tims.setup``    — the setup/OOBE flow screens (``tims.setup.run`` is the entry).

Kept intentionally empty of re-exports: ``import tims.band`` (from app/constants) must
NOT eagerly pull in ``tims.setup`` (which imports app lazily). Import submodules directly.
"""
