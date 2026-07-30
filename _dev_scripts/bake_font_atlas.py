"""Bake the font atlas that `font_atlas.py` reads in ATLAS mode.

The atlas holds what the PRODUCTION code produced. This script does not lay text
out, does not decide which characters or strings are needed, and does not read
route data to guess at the text. It drives the real app across its state space
with `font_atlas` recording, and stores whatever the renderers asked their fonts
for:

  parts       the laid-out output of `displays.utils.compose_text_parts`, per
              (text, colour, width, collapse, script) — station names, route-bar
              labels, the train-type box
  entries     direct `font.render(...)` calls — the prefix, the countdown 分, the
              transfer banner
  entries_bg  the opaque `font.render(..., background)` form, stored as SDL
              composited it
  sizes       `font.size(...)` results the renderers read
  metrics     `font.metrics(...)` per character
  scalars     get_height / get_ascent

Anything this script decided for itself would be a second implementation of a
production decision, and a second implementation drifts. An earlier version
declared a combo table and derived the text domain from route.json; both were
guesses about what the code does, and both were wrong in ways that render as
plausible-looking output.

Coverage therefore rests on the sweep being EXHAUSTIVE, not on a declaration:
every shipped route x every stop x every mode x every view x every PA phase.
`--verify` re-drives the identical sweep in ATLAS mode and fails on any miss, so
an incomplete recording stops the build instead of shipping a crash.

Usage:
    uv run _dev_scripts/bake_font_atlas.py            # record + bake
    uv run _dev_scripts/bake_font_atlas.py --verify   # re-drive in ATLAS mode

Not shipped (`_dev_scripts/`); `/build` invokes both steps as a pre-flight.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import sys
import traceback
from pathlib import Path

os.environ["SDL_VIDEODRIVER"] = "dummy"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pygame  # noqa: E402

import font_atlas  # noqa: E402

# Sheet width, as a game texture atlas: entries shelf-pack left-to-right and
# wrap. Everything at one point size shares a height, so rows come out uniform
# and a glyph is findable by eye in the PNG.
SHEET_W = 2048


def _modes() -> tuple:
    """Display modes from the production enum, not a tuple typed in here."""
    from displays.base import DisplayMode

    return tuple(m.name.lower() for m in DisplayMode)


# The app-state machine's own arity: APPROACHING_EARLY / APPROACHING_FINAL /
# STOPPING, which `preview_display.apply_state` maps to 次は / まもなく / ただいま.
# Not derivable from an enum — see DISPLAY.md § "Unified State Machine".
PA_PHASES = (0, 1, 2)

FROZEN = 1750000000.0


def freeze_clock() -> None:
    """Pin every clock source before any state is rendered.

    Not cosmetic. Animation and the mode scheduler read the wall clock directly,
    so two passes over the same states at different real times produce different
    frames — which reported 1122 of 10476 frames as ATLAS-vs-LIVE mismatches when
    every one of them rendered identically in isolation. Passing a fixed
    `timestamp` into render_frame is not enough; the sources inside reach for the
    clock themselves.
    """
    import time

    fixed = time.localtime(FROZEN)
    time.time = lambda: FROZEN
    time.localtime = lambda t=None: fixed
    time.monotonic = lambda: FROZEN
    # SDL's own millisecond counter, which patching Python's `time` cannot reach.
    # The multi-PA hint blinks on `(get_ticks() // 500) % 2`
    # (e235_1000/upper_lcd.py:709), so two passes over the same states catch it in
    # opposite phases purely from how long the first pass took. Left unpinned this
    # reported ~1150 phantom mismatches per run, and a different set each run.
    pygame.time.get_ticks = lambda: 0


def shipped_routes() -> list:
    """Every route the build ships — `_`-prefixed dirs are staging, not shipped."""
    out = []
    for p in glob.glob(str(ROOT / "audio" / "**" / "route.json"), recursive=True):
        rel = Path(p).relative_to(ROOT).as_posix().split("/")
        if any(s.startswith("_") for s in rel[1:-1]):
            continue
        out.append("/".join(rel[1:-1]))
    return sorted(out)


# ---------------------------------------------------------------------------
# the cook — coverage comes from the DATA, not from the sweep
# ---------------------------------------------------------------------------


def _norm_file(rel: str) -> str:
    """Collapse a route path so every route shares one location.

    Every `route.json` holds the same SHAPE, so a station name observed on one
    route must bind that location on ALL routes. Keeping the paths per-route
    would make the domain per-route, and a route the sweep drove shallowly would
    stay uncovered — which is the hole this whole mechanism exists to close.
    """
    return "audio/*/route.json" if rel.split("/")[0] == "audio" else rel


def walk_shipped_json() -> dict:
    """Every string VALUE in every shipped JSON, mapped to where it appears.

    Names no key. Attempt 3 of this work derived the text domain by reading
    `stops` and missed the 18 stations in `sobu/1217F`'s `pre_stops`: naming keys
    IS the failure mode, so this walk knows nothing about any schema and finds
    both arrays precisely because it asks for neither.

    Returns `{string: {location, ...}}`, a location being
    `audio/*/route.json:pre_stops[].name` — list indices collapsed to `[]` so
    every member of an array shares one location.
    """
    out: dict = {}

    def rec(node, loc):
        if isinstance(node, str):
            out.setdefault(node, set()).add(loc)
        elif isinstance(node, dict):
            for k, v in node.items():
                rec(v, loc + ("" if loc.endswith(":") else ".") + k)
        elif isinstance(node, list):
            for v in node:
                rec(v, loc + "[]")

    for p in sorted(ROOT.glob("data/*.json")) + sorted(ROOT.glob("audio/**/route.json")):
        rel = p.relative_to(ROOT).as_posix()
        if any(seg.startswith("_") for seg in rel.split("/")):
            continue  # staging, not shipped
        rec(json.loads(p.read_text(encoding="utf-8")), _norm_file(rel) + ":")
    return out


def cook_from_data(sink: dict, walk: dict) -> dict:
    """Render every value the data can reach, at the combos that draw its kind.

    The sweep observed which data LOCATIONS feed which font combo; the walk knows
    every value at those locations. Rendering the difference is what makes
    coverage independent of whether a state can be driven to — `四街道` gets baked
    because it is a string in `route.json`, not because some frame reached it.

    The domain is the UNION of two sources, because neither is complete alone:

      what the sweep saw    catches hardcoded source literals — 次は / まもなく,
                            方面, ゆき, 分, のりかえ案内, the route disclaimers.
                            These live in .py and appear in no JSON, so a data
                            walk can never find them.
      what the walk yields  catches data values no reachable state renders — the
                            7 stations interior to sobu/1217F's frame 1.

    Shape is observed, not declared: a combo whose recorded entries are single
    characters is drawn per character (the route-bar labels), so its domain
    expands to characters; one whose entries are whole strings expands to
    strings. Nothing here decides which is which.
    """
    from displays.utils import compose_text_parts

    added = {"parts": 0, "entries": 0, "sizes": 0, "declared": [], "undeclared": []}

    for ident in list(sink):
        face, size, bold, italic = ident
        rec = sink[ident]
        entries, parts = rec.get("entries", {}), rec.get("parts", {})

        font = font_atlas.lcd_font(face, size, bold=bold, italic=italic)
        # Measured for every combo, so the manifest never has to default them.
        font.get_height()
        font.get_ascent()

        sizes = rec.get("sizes", {})
        observed = set(entries) | set(sizes)
        params: dict = {}
        for k in parts:
            w, coll, scr, rest = k.split("|", 3)
            col, txt = rest.split("|", 1)
            observed.add(txt)
            params.setdefault(txt, set()).add((int(w), int(coll), scr, col))

        # How a text is DRAWN is observed per data location, not per combo. Size
        # 25 serves both the per-character route-bar labels and the whole-string
        # prefix literals; a combo-wide shape would render every station name
        # whole as well — ~800 rasters production never asks for.
        #
        #   parts   laid out through compose_text_parts (its stored parts already
        #           hold the per-character rasters, so this supersedes `char`)
        #   char    measured whole, then drawn one character at a time
        #   string  drawn as one whole-string render
        shape_by_loc: dict = {}

        def mark(text, shape):
            for loc in walk.get(text, ()):
                shape_by_loc.setdefault(loc, set()).add(shape)

        for t in observed:
            # Exact-value match only. Substring matching would bind a station
            # name to any prose that happens to mention it.
            if t in params:
                mark(t, "parts")
            elif t in entries:
                mark(t, "string")
            elif t in sizes:
                mark(t, "char")

        all_params = set().union(*params.values()) if params else set()

        def shape_of(t):
            if t in params:
                return "parts"
            if t in entries:
                return "string"
            if t in sizes:
                return "char"
            return None

        def emit(text, shapes):
            if not shapes or not text or text in observed:
                return
            if "parts" in shapes:
                for width, coll, scr, col in all_params:
                    font_atlas.text_parts(
                        compose_text_parts,
                        font,
                        text,
                        tuple(json.loads(col)),
                        width,
                        bool(coll),
                        scr,
                    )
                    added["parts"] += 1
            elif "char" in shapes:
                for ch in text:
                    font.render(ch, True, (255, 255, 255))
                    added["entries"] += 1
            if "string" in shapes:
                font.render(text, True, (255, 255, 255))
                added["entries"] += 1
            font.size(text)
            added["sizes"] += 1

        declared = rec.get("draws") or []
        if declared:
            # A DECLARED combo takes its domain from the declaration, never from
            # what the sweep happened to draw. That is the whole point: coverage of
            # a declared site does not depend on any state being reachable, so a new
            # slot, view, frame or model cannot leave it short. It also reaches text
            # that is in no JSON at all — `さいたま` from a split name, `·` from the
            # transfer panel's dot substitution.
            added["declared"].append(ident)
            ident_shapes = {s for s in (shape_of(t) for t in observed) if s}
            for src in declared:
                dom = font_atlas.resolve(src, walk)
                # Shape per DECLARATION, read off the observed texts that
                # declaration covers — so ShinGo Medium @25 renders route-bar names
                # per character and PA prefixes whole, rather than applying both
                # shapes to the union of the two roles it serves.
                shapes = {s for s in (shape_of(t) for t in observed & dom) if s}
                if not shapes:
                    # Declared but never yet drawn — the transfer panel's CJK
                    # fallback for `name_en` fires only where the Latin face lacks a
                    # glyph. Bake it anyway so the first time it does fire, it is
                    # already there.
                    shapes = ident_shapes or {"string"}
                for text in sorted(dom):
                    emit(text, shapes)
        elif shape_by_loc:
            added["undeclared"].append(ident)
            domain = {s for s, locs in walk.items() if locs & set(shape_by_loc)}
            for text in sorted(domain):
                shapes = set()
                for loc in walk.get(text, ()):
                    shapes |= shape_by_loc.get(loc, set())
                emit(text, shapes)

    return added


# Modules whose ShinGo loads still bypass `font_atlas.lcd_font`. Their literals
# cannot be audited because nothing records them. Listed rather than skipped
# silently. Empty now that every train model resolves through the seam — keep it
# empty; an entry here is an un-auditable module, not a normal state.
UNCONVERTED = ()

_CJK = None


def audit_source_literals(sink: dict) -> tuple:
    """Every Japanese literal in display code must have been drawn by the sweep.

    This is the OTHER half of the text domain. `walk_shipped_json` cooks the data
    side; a literal authored inline is a text source no data walk can see, so if
    no state the sweep drove ever rendered it, it is a `KeyError` lying in wait
    in a shipped build.

    Deliberately a GATE, not a cook input: the scan finds the string but cannot
    know which combo draws it, so baking it blind would put the 50-character
    route disclaimer at size 78. Failing loudly and naming the literal puts the
    decision where it belongs — make the state reachable, or move the string.

    Strings used as PREDICATES (comparing a line or station name rather than
    drawing it) are not text sources. Mark those lines `# not-drawn`.
    """
    global _CJK
    import ast
    import re

    if _CJK is None:
        _CJK = re.compile(r"[぀-ヿ㐀-䶿一-鿿豈-﫿]")

    drawn = set()
    for rec in sink.values():
        drawn |= set(rec.get("entries", {})) | set(rec.get("sizes", {}))
        for k in rec.get("entries_bg", {}):
            drawn.add(k.split("|", 2)[2])
        for k in rec.get("parts", {}):
            drawn.add(k.split("|", 4)[4])

    missing, skipped = [], []
    for p in sorted((ROOT / "displays").rglob("*.py")):
        rel = p.relative_to(ROOT).as_posix()
        text = p.read_text(encoding="utf-8")
        lines = text.splitlines()
        tree = ast.parse(text)
        docstrings = {
            n.value.lineno for n in ast.walk(tree) if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)
        }
        for n in ast.walk(tree):
            if not (isinstance(n, ast.Constant) and isinstance(n.value, str)):
                continue
            if n.lineno in docstrings or not _CJK.search(n.value):
                continue
            src = lines[n.lineno - 1] if n.lineno <= len(lines) else ""
            if "not-drawn" in src:
                continue
            if any(u in rel for u in UNCONVERTED):
                skipped.append((rel, n.lineno, n.value))
                continue
            # A literal may be drawn on its own, or COMPOSED into a larger string
            # first — `station_name + "駅"` draws 東京駅, which appears in no JSON.
            # Substring satisfies the composed case.
            #
            # Note what this can and cannot promise: it proves the literal reached
            # the screen somehow, NOT that every composition of it did. The set of
            # compositions is bounded by what states are reachable, which is the
            # dependency this whole mechanism is trying to remove — so a composed
            # literal stays reachability-covered until renderers declare their
            # text sources outright.
            if n.value in drawn or any(n.value in d for d in drawn):
                continue
            missing.append((rel, n.lineno, n.value))
    return missing, skipped


def sweep(on_frame) -> tuple:
    """Drive every state of every shipped route, calling on_frame() after each.

    One PASimulator per route rather than one per state: building it is the
    expensive part, and rebuilding it thousands of times is what made an earlier
    version slow enough to look broken (and eventually segfault).
    """
    import preview_display
    from app import PASimulator

    from displays.train_models import TRAIN_MODELS

    MODES = _modes()
    ok = 0
    failures = {}
    # Models come from the production registry, not a name typed in here. The
    # setup picker can put ANY model on ANY route, and yamanote/route.json
    # already defaults to e235_0 — so a hardcoded model was not merely narrow,
    # it left a default path entirely unbaked.
    combos = [(r, m) for r in shipped_routes() for m in TRAIN_MODELS]
    routes = sorted({r for r, _ in combos})
    for route, model in combos:
        work_dir = preview_display._resolve_work_dir(route)
        sim = PASimulator(work_dir, preview=True, model=model)
        n_stops = len(sim.stops)
        # Frame count comes from PRODUCTION, not from a tuple typed in here. A
        # through-service route windows its route bar per frame, and pinning the
        # lower view disables the scheduler (preview_display.py:181 ->
        # base.py:167), so `_advance_frame` never runs and the sweep saw frame 0
        # forever: sobu/1217F shipped with NO raster for the 7 stations interior
        # to frame 1. Driving the axis explicitly is what makes the verify pass
        # able to see them at all.
        n_frames = getattr(sim.lower, "_frame_count", 1)
        # Slots likewise: every `_SLOT_*` the manager defines, not the three names
        # preview_display happens to map. A model that adds a fourth view joins
        # the sweep by defining it, with nothing to remember here.
        slots = sorted(sim.lower._SLOT_BEATS)
        for stop in range(n_stops):
            for mode in MODES:
                for slot in slots:
                    for pa in PA_PHASES:
                        for frame in range(n_frames):
                            try:
                                # lower_view pins the slot cycle and disables the
                                # scheduler; the slot itself is then set from the
                                # discovered set rather than the mapped name.
                                preview_display.apply_state(sim, stop=stop, pa=pa, mode=mode, lower_view="full")
                                sim.lower._current_slot = slot
                                sim.lower._active_frame_idx = frame
                                preview_display.render_frame(sim, timestamp=FROZEN)
                                on_frame()
                                ok += 1
                            except BaseException as e:
                                msg = f"{type(e).__name__}: {str(e)[:160]}"
                                failures.setdefault(msg, []).append((f"{route}[{model}]", stop, mode, slot, pa, traceback.format_exc()))
        # full_quit=False: pygame.quit() would tear down the font subsystem while
        # font_atlas's cache still holds live Font objects, and the next route
        # segfaults on the first render. The partial teardown is the sanctioned
        # re-entry path (app.py:970).
        sim.cleanup(full_quit=False)
        pygame.display.set_mode((1, 1))
        print(
            f"  {route:18} {model:10} {n_stops:>3} stops x "
            f"{len(MODES)}x{len(slots)}x{len(PA_PHASES)}x{n_frames}f  -> {ok} frames, "
            f"{sum(len(v) for v in failures.values())} failed"
        )
    return ok, failures, routes


# ---------------------------------------------------------------------------
# packing
# ---------------------------------------------------------------------------


def shelf_pack(items, path):
    """Shelf-pack (key, surface) items into one sheet; return key -> placement.

    Uniform rows: everything at a given point size shares a height, so ordered
    left-to-right wrapping is both near-optimal and readable in the PNG.
    """
    items = [(k, s) for k, s in items if s.get_width() and s.get_height()]
    if not items:
        return {}
    row_h = max(s.get_height() for _, s in items)
    x = y = 0
    placed, out, seen = [], {}, {}
    for k, s in items:
        # Identical rasters share one rect. Parts are stored per CHARACTER, so
        # the same glyph otherwise repeats once for every string it appears in —
        # and the data-driven domain multiplies that redundancy by the whole
        # station list. Content-hash dedup is what keeps the cook cheap.
        digest = (s.get_size(), hashlib.sha1(pygame.image.tostring(s, "RGBA")).digest())
        hit = seen.get(digest)
        if hit is not None:
            out[k] = dict(hit)
            continue
        w, h = s.get_size()
        if x + w > SHEET_W and x > 0:
            x, y = 0, y + row_h
        rect = {"x": x, "y": y, "w": w, "h": h, "sheet": path.name}
        out[k] = rect
        seen[digest] = rect
        placed.append((x, y, s))
        x += w
    sheet = pygame.Surface((SHEET_W, y + row_h), pygame.SRCALPHA, 32)
    for px, py, s in placed:
        sheet.blit(s, (px, py))
    pygame.image.save(sheet, str(path))
    return out


def pack_opaque(items, path):
    """Same, on an opaque sheet — the render(..., background) form has no alpha."""
    items = [(k, s) for k, s in items if s.get_width() and s.get_height()]
    if not items:
        return {}
    row_h = max(s.get_height() for _, s in items)
    x = y = 0
    placed, out = [], {}
    for k, s in items:
        w, h = s.get_size()
        if x + w > SHEET_W and x > 0:
            x, y = 0, y + row_h
        out[k] = {"x": x, "y": y, "w": w, "h": h, "sheet": path.name}
        placed.append((x, y, s))
        x += w
    sheet = pygame.Surface((SHEET_W, y + row_h))
    for px, py, s in placed:
        sheet.blit(s, (px, py))
    pygame.image.save(sheet, str(path))
    return out


def combo_slug(ident) -> str:
    face, size, bold, italic = ident
    stem = face.replace(".otf", "").replace("ShinGoPr6N-", "shingo_").lower()
    return f"{stem}_{size}{'b' if bold else ''}{'i' if italic else ''}"


def bake(outdir: Path) -> int:
    freeze_clock()
    pygame.init()
    pygame.font.init()
    pygame.display.set_mode((1, 1))  # draw_text calls .convert_alpha()

    font_atlas.force_mode(font_atlas.LIVE)
    sink = font_atlas.start_recording()

    print("recording the app across every shipped state...")
    frames, failures, routes = sweep(lambda: None)
    print(f"\n{frames} frames rendered across {len(routes)} routes")

    # The sweep only DISCOVERS which data locations feed which combo. Coverage
    # comes from the data: every value at a bound location is rendered whether or
    # not any reachable state draws it. Without this, an unreachable state is a
    # KeyError in a shipped build — sobu/1217F's frame 1 shipped exactly that.
    # Snapshot BEFORE cooking. `cook_from_data` resolves each ident with no `draws=`
    # on purpose — one ident can carry several declarations (ShinGo Medium @25 serves
    # the route-bar labels and the PA prefixes), so the baker cannot bind itself to
    # one of them. Those baker calls land in the same cache, so measuring after the
    # cook counts the instrument instead of production.
    prod_undeclared = font_atlas.undeclared_sites()

    walk = walk_shipped_json()
    print(f"\ncooking from data: {len(walk)} distinct strings across the shipped JSON")
    added = cook_from_data(sink, walk)
    print(f"  beyond what the sweep reached: +{added['parts']} laid-out, " f"+{added['entries']} rendered, +{added['sizes']} measured")
    n_dec = len(added["declared"])
    # The finish line, printed rather than tracked in a doc. Counted per CALL SITE,
    # not per combo: ShinGo Medium @25 serves both the route-bar labels and the PA
    # prefixes, so declaring one would make the combo look done while the other
    # still rode on whatever the sweep happened to draw. Zero means the atlas no
    # longer cares what states the LCD can be driven to.
    print(f"  {n_dec} combo(s) cooked from a `draws=` declaration; " f"{len(prod_undeclared)} production call site(s) still undeclared")
    for face, sz, b, i in prod_undeclared:
        print(f"    UNDECLARED  {face} @{sz}{'b' if b else ''}{'i' if i else ''}")

    missing, skipped = audit_source_literals(sink)
    if skipped:
        mods = sorted({r for r, _, _ in skipped})
        print(f"\n{len(skipped)} source literals NOT audited — not on the seam yet:")
        for mod in mods:
            print(f"  {mod}")
    if missing:
        print(f"\n{len(missing)} Japanese literal(s) in display code that no swept state drew:")
        for rel, ln, v in missing:
            print(f"  {rel}:{ln}  {v[:44]!r}")
        print("  Each is a KeyError waiting in a fontless build. Either make the state")
        print("  reachable in the sweep, or mark the line `# not-drawn` if the string is a")
        print("  predicate rather than text.")
    else:
        print("\nsource literals: every drawn Japanese literal was rendered by the sweep")
    if failures:
        print(f"{sum(len(v) for v in failures.values())} frames raised, " f"{len(failures)} distinct:")
        for msg, where in failures.items():
            r, s, m, v, p, tb = where[0]
            print(f"  x{len(where):<5} {msg}")
            print(f"          first: {r} stop={s} {m}/{v} pa={p}")

    outdir.mkdir(parents=True, exist_ok=True)
    for stale in outdir.glob("*.png"):
        stale.unlink()

    manifest = {
        "version": 4,
        "data_fingerprint": font_atlas.data_fingerprint(),
        # Renderer sources too: a new literal or point size in .py changes no JSON, so
        # the data fingerprint alone let a stale atlas load and then KeyError on one
        # stop. See font_atlas.code_fingerprint.
        "code_fingerprint": font_atlas.code_fingerprint(),
        "combos": [],
    }
    for ident in sorted(sink):
        rec = sink[ident]
        slug = combo_slug(ident)

        # `parts` values are lists of (offset, surface). Every surface across all
        # parts and all direct renders goes on ONE alpha sheet per combo, so a
        # combo is one file to open when something looks wrong.
        alpha_items = []
        for key, parts in rec.get("parts", {}).items():
            for i, (_off, surf) in enumerate(parts):
                alpha_items.append((f"p\x00{key}\x00{i}", surf))
        for text, surf in rec.get("entries", {}).items():
            alpha_items.append((f"e\x00{text}", surf))

        placed = shelf_pack(sorted(alpha_items, key=lambda kv: kv[0]), outdir / f"{slug}.png")
        bg_placed = pack_opaque(sorted(rec.get("entries_bg", {}).items()), outdir / f"{slug}_bg.png")

        parts_out = {}
        for key, parts in rec.get("parts", {}).items():
            seq = []
            for i, (off, _surf) in enumerate(parts):
                p = placed.get(f"p\x00{key}\x00{i}")
                if p is not None:
                    seq.append({"off": off, **p})
            parts_out[key] = seq

        face, size, bold, italic = ident
        manifest["combos"].append(
            {
                "face": face,
                "size": size,
                "bold": bold,
                "italic": italic,
                "slug": slug,
                "parts": parts_out,
                "entries": {t[2:]: p for t, p in placed.items() if t.startswith("e\x00")},
                "entries_bg": bg_placed,
                "sizes": rec.get("sizes", {}),
                "metrics": rec.get("metrics", {}),
                # Measured, never defaulted. The old `.get(..., size)` fallback was
                # accidentally right for get_height (ShinGo matches the point size at
                # every size in use) and silently WRONG for get_ascent (78 -> 69,
                # 22 -> 20), which would mis-baseline the first renderer to read it.
                # cook_from_data() calls both for every combo, so a KeyError here
                # means the cook did not run — worth failing the build over.
                "get_height": rec["scalars"]["get_height"],
                "get_ascent": rec["scalars"]["get_ascent"],
            }
        )
        n_parts = sum(len(v) for v in parts_out.values())
        print(
            f"  {slug:22} {len(parts_out):>5} laid-out texts ({n_parts} parts)"
            f" {len(rec.get('entries', {})):>4} direct"
            f" {len(bg_placed):>3} opaque"
            f" {len(rec.get('sizes', {})):>5} measured"
        )

    (outdir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    total = sum(p.stat().st_size for p in outdir.iterdir())
    print(f"\natlas: {len(manifest['combos'])} combos, {total / 1e6:.1f} MB in {outdir}")
    print(f"fingerprint: {manifest['data_fingerprint']}")
    return 1 if (failures or missing) else 0


def verify() -> int:
    """Re-drive the identical sweep in ATLAS mode. Any miss is a build failure."""
    freeze_clock()
    pygame.init()
    pygame.font.init()
    pygame.display.set_mode((1, 1))
    font_atlas.force_mode(font_atlas.ATLAS)

    # Coverage is not the only thing that matters: the shipped build has no ShinGo
    # FILES, so a code path that constructs one is a FileNotFoundError there even
    # though the atlas could have served it. Make that unmissable by removing the
    # file from reach for the whole pass — the dev tree still has every face, so
    # this failure is otherwise invisible here (critical_lessons.md §4).
    _real_font = pygame.font.Font

    def _no_baked_face(path, size, *a, **k):
        if font_atlas.is_atlas_face(Path(str(path)).name):
            raise AssertionError(
                f"ATLAS mode opened a baked font file: {path}. It resolves from the atlas, so "
                "a build shipping no ShinGo would raise FileNotFoundError here. Route this "
                "load through font_atlas.lcd_font()."
            )
        return _real_font(path, size, *a, **k)

    pygame.font.Font = _no_baked_face

    print("verifying: re-driving every shipped state in ATLAS mode, " "with the baked faces unreadable...")
    frames, failures, routes = sweep(lambda: None)
    bad = sum(len(v) for v in failures.values())
    print(f"\n{frames} frames rendered from the atlas, {bad} raised")
    if not failures:
        print("VERIFIED — the atlas served every lookup the app made, with no font files")
        return 0
    for msg, where in failures.items():
        r, s, m, v, p, tb = where[0]
        print(f"\n  x{len(where):<5} {msg}")
        print(f"          first: {r} stop={s} {m}/{v} pa={p}")
    return 1


def pixel_verify() -> int:
    """Render EVERY state twice — LIVE then ATLAS — and require identical frames.

    `--verify` only proves the atlas had an entry for every lookup. This proves
    the entry was the right pixels. Hashes are compared rather than kept, so the
    whole sweep costs one dict of digests.

    Two passes per route, not two modes per frame: switching mode invalidates the
    font cache, and the displays hold font references from construction, so the
    simulator is rebuilt once per pass instead of once per frame.
    """
    import hashlib

    import preview_display
    from app import PASimulator

    freeze_clock()
    pygame.init()
    pygame.font.init()
    pygame.display.set_mode((1, 1))

    from displays.train_models import TRAIN_MODELS

    MODES = _modes()

    def frames_for(route, model, mode_name):
        font_atlas.force_mode(mode_name)
        sim = PASimulator(preview_display._resolve_work_dir(route), preview=True, model=model)
        out = {}
        # Same production-derived axes as `sweep` — an axis this pass does not
        # walk is a state whose pixels were never compared.
        n_frames = getattr(sim.lower, "_frame_count", 1)
        slots = sorted(sim.lower._SLOT_BEATS)
        for stop in range(len(sim.stops)):
            for m in MODES:
                for v in slots:
                    for p in PA_PHASES:
                        for f in range(n_frames):
                            preview_display.apply_state(sim, stop=stop, pa=p, mode=m, lower_view="full")
                            sim.lower._current_slot = v
                            sim.lower._active_frame_idx = f
                            preview_display.render_frame(sim, timestamp=FROZEN)
                            raw = pygame.image.tostring(sim.screen, "RGB")
                            out[(stop, m, v, p, f)] = hashlib.sha256(raw).hexdigest()
        sim.cleanup(full_quit=False)
        pygame.display.set_mode((1, 1))
        return out

    print("pixel-verifying: every state rendered LIVE and ATLAS, frames compared...")
    total = mismatched = 0
    bad_routes = {}
    for route in shipped_routes():
        for model in TRAIN_MODELS:
            live = frames_for(route, model, font_atlas.LIVE)
            atlas = frames_for(route, model, font_atlas.ATLAS)
            diffs = [k for k in live if live[k] != atlas.get(k)]
            total += len(live)
            mismatched += len(diffs)
            if diffs:
                bad_routes[f"{route}[{model}]"] = diffs
            print(f"  {route:18} {model:10} {len(live):>5} states  " f"{len(diffs):>4} differing")

    print(f"\n{total} states compared, {mismatched} frames differ")
    if not bad_routes:
        print("IDENTICAL — every state renders the same from the atlas as from the fonts")
        return 0
    for route, diffs in bad_routes.items():
        print(f"  {route}: {len(diffs)} e.g. {diffs[:6]}")
    return 1


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="font_atlas")
    ap.add_argument("--verify", action="store_true", help="re-drive the sweep in ATLAS mode; fails on any missing entry")
    ap.add_argument("--pixel-verify", action="store_true", help="render every state both ways and require identical frames")
    a = ap.parse_args()
    if a.pixel_verify:
        sys.exit(pixel_verify())
    sys.exit(verify() if a.verify else bake(ROOT / a.out))


if __name__ == "__main__":
    main()
