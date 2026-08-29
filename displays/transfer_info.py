# SPDX-License-Identifier: MIT
"""Transfer-info display base class (model-agnostic).

Resolves the per-stop transfer list each frame: looks up the current
station in ``data/stations.json``, applies the active-line filter
(drops slugs whose badges include the route's own ``line_code``), then
applies any per-station view drop/edit ops keyed by the route's
``transfer_view``. The resolved slug list is handed to ``_render``,
which subclasses implement per train model.

Also hosts ``resolve_entry`` — the generic ``slug``/``slug.variant``/
``...scale(N)`` reference resolver used by both the base class
filter logic and per-model renderers.
"""

import json
import re
from typing import List, Optional

import pygame

from app_paths import project_root as _project_root


def load_icon(slug: str, target_h: int, cache: dict) -> pygame.Surface:
    """A line badge PNG, scaled to `target_h` and cached by `(slug, height)`.

    Model-agnostic, and lives here rather than in a train model's own module
    because three renderers already want it — E235-1000's horizontal slot,
    E235-0's inline panel and now E233-0's — and a shared asset loader reached
    through one model's package is the misfiling `conventions.md` § "Display
    module structure" names. `e235_1000.transfer_info` re-exports it, so every
    existing import site keeps working unchanged.

    Fails loud on a missing asset per `critical_lessons.md` § "Runtime-required
    materials must be committed": a silent placeholder would hide a bad badge
    slug until someone noticed the wrong icon on a shipped screen.
    """
    key = (slug, target_h)
    if key in cache:
        return cache[key]
    path = _project_root() / "data" / "line_icons" / f"{slug}.png"
    if not path.exists():
        raise FileNotFoundError(f"line_icon asset missing: {path} (slug={slug!r}). " f"Drop a PNG at that path or fix the badge slug in lines.json.")
    img = pygame.image.load(str(path)).convert_alpha()
    sw, sh = img.get_size()
    scaled = pygame.transform.smoothscale(img, (int(round(sw * (target_h / sh))), target_h))
    cache[key] = scaled
    return scaled


def wrap_two_lines(name: str, font, avail_w: int):
    """Greedy-to-width split of a line name into `(line1, line2)`.

    Model-agnostic, and here rather than on a train model because three
    renderers want it — E235-0's inline panel, E233-0's 6-station band and now
    its transfer view. `docs/wip/WIP_e233_0_display.md` § 10.3.5 asked for the
    lift rather than a third copy; `conventions.md` § "Display module structure"
    is the rule behind it.

    Three separators, tried in order, each keeping its own side:

    - `･` (half-width U+FF65, the separator `docs/DATA_FORMAT.md` § "Punctuation
      in `name_ja`" names as the wrap point) stays on LINE 1. The longest run of
      segments whose joined width including that trailing dot fits `avail_w`
      goes first; the dot is not dropped at the break, which is what pins the
      IRL cut 東北･山形･秋田 | 北海道･上越･北陸新幹線.
    - `（` moves to LINE 2, so a parenthetical qualifier takes its own line
      whole: 横浜市営地下鉄 | （ブルーライン）. Same rule the E233-0 6-station
      band applies, and the reason it is here rather than a caller's special
      case — breaking anywhere else inside a parenthetical strands the bracket.
    - a space is DROPPED, which is what an English name offers.

    Failing all three, break at the longest character prefix that fits. Always
    returns two strings; line 2 may overrun a remainder too wide for any split.
    """
    for sep, side in (("･", 1), ("（", 2), (" ", 0)):
        if sep in name and not name.startswith(sep):
            segs = name.split(sep)
            k = 1  # at least the first segment stays on line 1
            for i in range(1, len(segs)):
                if font.size(sep.join(segs[:i]) + (sep if side == 1 else ""))[0] <= avail_w:
                    k = i
                else:
                    break
            head = sep.join(segs[:k]) + (sep if side == 1 else "")
            return head, (sep if side == 2 else "") + sep.join(segs[k:])
    for i in range(len(name) - 1, 0, -1):
        if font.size(name[:i])[0] <= avail_w:
            return name[:i], name[i:]
    return name, ""


SCALE_SUFFIX_RE = re.compile(r"\.scale\(([0-9]*\.?[0-9]+)\)$")


def resolve_entry(slug_ref: str, lines: dict) -> dict:
    """Resolve 'slug', 'slug.variant', or '...scale(N)' to effective entry dict.

    Variant fields override base fields; missing fields inherit from base.
    Dot-notation is one-level only for variants — `slug.variant.subvariant`
    is invalid. A trailing `.scale(N)` modifier (parsed first) overrides
    `name_ja_compress` for this reference only; default is 1.0 if neither
    suffix nor any inherited field provides one.
    Fails loud (KeyError) on missing base or unknown variant; per
    `critical_lessons.md` § runtime-required artifacts, silent fallback on
    missing data hides bugs at the worst time.
    """
    scale_override = None
    m = SCALE_SUFFIX_RE.search(slug_ref)
    if m:
        scale_override = float(m.group(1))
        slug_ref = slug_ref[: m.start()]

    if "." in slug_ref:
        base_slug, variant_name = slug_ref.split(".", 1)
        if "." in variant_name:
            raise ValueError(f"Dot-notation is one level only; got '{slug_ref}'")
        if base_slug not in lines:
            raise KeyError(f"Base slug '{base_slug}' not in lines.json (referenced as '{slug_ref}')")
        base = lines[base_slug]
        variants = base.get("variants", {})
        if variant_name not in variants:
            raise KeyError(f"Variant '{variant_name}' not under '{base_slug}' (referenced as '{slug_ref}')")
        merged = {k: v for k, v in base.items() if k != "variants"}
        merged.update(variants[variant_name])
    else:
        if slug_ref not in lines:
            raise KeyError(f"Slug '{slug_ref}' not in lines.json")
        merged = {k: v for k, v in lines[slug_ref].items() if k != "variants"}

    if scale_override is not None:
        merged["name_ja_compress"] = scale_override
    return merged


def apply_transfer_filter(
    transfers: List[str],
    line_code: Optional[str],
    transfer_view: Optional[str],
    station_data: dict,
    lines: dict,
) -> List[str]:
    """Apply view adds, then the active-line filter, then view drops, then edits.

    Single source of truth for the transfer filtering pipeline shared by
    the production class (``TransferInfoDisplay._resolve_transfers``) and
    the preview CLI. Pure function — no class state.

    ``add`` exempts an exact ref from the active-line filter, which is the
    only thing it can undo — so it is read BEFORE that filter runs, not
    after. It exists for a SIBLING service sharing the active line's code:
    宇都宮線 and 高崎線 are both ``JU``, so riding either drops both, yet at
    大宮 (where they physically diverge) the PA announces the other one.
    Matching is by exact ref, not base slug, because the route's own variant
    must still be dropped while the sibling survives. A later ``drop`` of the
    same base still wins — drop is applied after.
    """
    view_ops = station_data.get("transfers_by_view", {}).get(transfer_view, {}) if transfer_view else {}
    keep = set(view_ops.get("add", []))

    if line_code:
        transfers = [
            ref for ref in transfers if ref in keep or not any(b.get("code") == line_code for b in resolve_entry(ref, lines).get("badges", []))
        ]

    if view_ops:
        dropset = set(view_ops.get("drop", []))
        if dropset:
            transfers = [r for r in transfers if r.split(".", 1)[0] not in dropset]
        editmap = view_ops.get("edit", {})
        if editmap:
            transfers = [editmap.get(r.split(".", 1)[0], r) for r in transfers]
            # DE-DUPLICATED, so an `edit` can MERGE. `edit` maps by base slug and
            # is applied to every entry, so pointing a base at one ref collapses
            # all of that base's variants onto it — which is how a view says
            # "show this through-service as one line". 東京 lists 横須賀線 and
            # 総武線快速 separately, and the Chūō display names them once as
            # 横須賀線・総武線快速; without this the merge renders that name twice.
            #
            # This is what makes the op match its own documented wording,
            # "replaces whatever X-base entry the flat list has" — singular. It
            # is inert on every existing config: no station today maps two
            # entries onto the same ref, so nothing else can produce a duplicate.
            #
            # The DIRECTION matters. A view can merge but never split, so the
            # flat list holds the finest-grained form and views coarsen it. That
            # fails safe: a view with no ops shows the two branches, never three
            # entries or a silently missing one.
            #
            # CONSECUTIVE ONLY, and that bound is load-bearing. `edit` is allowed
            # to produce a duplicate at a DISTANCE — two unrelated entries can
            # legitimately map onto one ref from different places in the list,
            # and `_tests/t1_unit/test_transfer_info.py` pins exactly that. A
            # merge is collapsing a RUN, not making the list unique: the branches
            # of one through-service are adjacent by construction, because
            # `transfers[]` is in IRL reading order.
            collapsed = [transfers[0]] if transfers else []
            for ref in transfers[1:]:
                if ref != collapsed[-1]:
                    collapsed.append(ref)
            transfers = collapsed

        # `order` — the view's own reading order, by BASE slug, leading. Nothing
        # else can permute: `transfers[]` is one ordered list shared by every
        # view, and add / drop / edit / rows all preserve position. Reordering
        # the list itself would move every other view with it, and the IRL order
        # is a property of the PIDS being read, not of the station: Chūō names
        # 中央・総武線 first at 新宿 where the Yamanote panel does not.
        #
        # LEADING, not total: listed slugs come first in the order given, and
        # everything else keeps its relative position behind them. So a view
        # states only the part it cares about — usually the JR block — and a line
        # added to `transfers[]` later does not silently jump to the front.
        ordering = view_ops.get("order", [])
        if ordering:
            rank = {slug: i for i, slug in enumerate(ordering)}
            transfers = sorted(transfers, key=lambda r: rank.get(r.split(".", 1)[0], len(rank)))

    return transfers


class TransferInfoDisplay:
    """Base class for the lower-LCD transfer-info view.

    Subclasses (per train model) implement ``_render`` to draw the
    resolved transfer list. The base handles state binding, station
    lookup, filter application, and the public LCD interface.
    """

    def __init__(self, screen, route_data: dict, stops: list):
        self.screen = screen
        self.route_data = route_data
        self.stops = stops

        root = _project_root()
        self.lines = json.loads((root / "data" / "lines.json").read_text(encoding="utf-8"))
        self.stations = json.loads((root / "data" / "stations.json").read_text(encoding="utf-8"))

        # Route-level filter knobs read once. Both optional — absent means
        # "no filtering" (renders raw transfers list). Out-of-spec routes
        # without these fields still get a best-effort render per CLAUDE.md
        # "Per-model IRL line scope" soft floor.
        self.line_code: Optional[str] = route_data.get("line_code")
        self.transfer_view: Optional[str] = route_data.get("transfer_view")
        self._state = None

    def set_state(self, state) -> None:
        """Bind to an AppState instance; subsequent show_stops reads live state."""
        self._state = state

    def _resolve_badges(self, slug_ref: str) -> list:
        """Look up badges for a slug_ref via lines.json + variant resolution.

        Empty-list fallback (vs the renderer's ``_universal`` fallback) is
        intentional: filter logic uses badges to read ``code`` for line-match;
        a badgeless entry has no code → never filter-dropped, always passes.
        """
        return resolve_entry(slug_ref, self.lines).get("badges", [])

    def _resolve_transfers(self, station_name: str) -> List[str]:
        """Return the post-filter / post-view-edit slug_ref list for a station.

        Empty when the station has no transfers entry, or when filtering
        wipes everything out. Delegates to ``apply_transfer_filter`` so
        preview tooling and production share one filter pipeline.
        """
        sd = self.stations.get(station_name, {})
        return apply_transfer_filter(
            list(sd.get("transfers", [])),
            self.line_code,
            self.transfer_view,
            sd,
            self.lines,
        )

    def show_stops(self, state, current_time: float = 0.0) -> None:
        """Render the transfer-info frame for the current stop.

        Public interface mirrors the other lower-LCD renderers
        (JapaneseDisplay / JapaneseEightStationDisplay) so LowerDisplay
        can dispatch to any of them uniformly.
        """
        if state is None:
            return
        sim_curr_stop = state.curr_stop
        if not (0 <= sim_curr_stop < len(self.stops)):
            return
        station_name = self.stops[sim_curr_stop].get("name", "")
        transfers = self._resolve_transfers(station_name)
        self._render(transfers, current_time)

    def _render(self, transfers: List[str], current_time: float) -> None:
        """Draw the resolved transfer list. Subclass responsibility."""
        del transfers, current_time
        raise NotImplementedError("TransferInfoDisplay subclass must implement _render")
