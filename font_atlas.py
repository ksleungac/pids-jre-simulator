"""Font access for the LCD renderers — one seam, two modes, identical call site.

A renderer always writes the same line:

    font = lcd_font("ShinGoPr6N-Medium.otf", 25)
    surf = font.render(text, True, color)

What backs `font` depends only on whether the font files are present:

  LIVE    a real `pygame.font.Font` from `fonts/`. The development default, so
          editing an LCD — nudging a size, moving a position — behaves exactly
          as it did before any atlas existed.
  ATLAS   served from a baked atlas. No font files need to exist.

# CONTRACT: LCD renderers resolve fonts through lcd_font() — never a bare
# pygame.font.Font(), never pygame.font.SysFont(). See WIP_font_atlas.md.
# A renderer that constructs its own Font bypasses this seam: it keeps working
# in dev, where the fonts exist, and fails in a build that ships none — the
# invisible-in-dev failure mode critical_lessons.md §4 is about.

The atlas stores render OUTPUT, not glyph outlines. Layout, kerning and
compression already work and live in `displays/utils.py`; storing output means
none of it is recomputed, so a stored render cannot drift from what the live
font produced.

STALENESS IS LOUD. The manifest carries a fingerprint of the data the atlas was
built from. If `data/` or a `route.json` changes — a new station, a new transfer
— the fingerprint stops matching and the atlas refuses to load, naming the fix.
Silence here would mean tofu in a shipped build, so it is an error, never a
fallback.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
from typing import Dict, Optional, Tuple

import pygame

from app_paths import project_root

LIVE, ATLAS = "live", "atlas"
ATLAS_DIRNAME = "font_atlas"

# Face families the atlas backs. A face NOT listed here loads as a plain
# pygame Font in BOTH modes, so it must ship with the app.
#
# This is the one place that fact lives. Every renderer routes every font
# through `lcd_font`, so a display author never decides — and never needs to
# know — whether the face they asked for is baked or shipped; widening the atlas
# to another family is a change to this tuple and to nothing else.
ATLAS_FACES = ("ShinGoPr6N",)


def is_atlas_face(face: str) -> bool:
    return face.startswith(ATLAS_FACES)


_mode: Optional[str] = None
_forced: Optional[str] = None
_atlas: Optional["Atlas"] = None
_cache: Dict[Tuple[str, int, bool, bool], object] = {}
# id(font) -> identity, for the live Fonts lcd_font hands out. `_cache` keeps
# every one of them alive for the process lifetime, so the ids stay valid.
_record: Optional[dict] = None
_suppressed = False
_walk: Optional[dict] = None


class LcdFont(pygame.font.Font):
    """A live font that carries its own atlas identity.

    The identity has to travel ON the object. Keeping it in a side table keyed by
    `id(font)` looked equivalent and is not: `force_mode` clears the font cache,
    CPython reuses the freed address, and the stale entry then claims an unrelated
    font — a bare HelveticaNeue-Medium@24 was identified as ShinGoPr6N-Medium@11
    and routed into the atlas. Subclassing is what makes the attribute possible at
    all; `pygame.font.Font` is a C type and rejects attributes directly.
    """

    def __init__(self, path, size, ident):
        super().__init__(path, size)
        self._id = ident
        self._draws = ()

    # Validation runs on the LIVE font itself, not on the recording wrapper, so
    # an undeclared draw fails on the first ordinary dev frame that performs it —
    # not only during a bake. That is what keeps a declaration from drifting
    # behind the code it sits in.
    def render(self, text, antialias, color, background=None):
        check_declared(self, text)
        return super().render(text, antialias, color, background)

    def size(self, text):
        check_declared(self, text)
        return super().size(text)

    # Style is part of the atlas IDENTITY (`lcd_font(..., bold=True)`), so a
    # post-construction mutation is invisible to the bake AND corrupts the shared
    # cached instance for every other call site. Raising makes that unwritable
    # rather than merely documented; `lcd_font` sets the initial style through the
    # base class, which is the one sanctioned path.
    def _no_mutate(self, *_a, **_k):
        raise TypeError(
            f"font_atlas: cannot set_bold/set_italic on {self._id} after construction. "
            "Pass bold=/italic= to lcd_font() — style is part of the atlas key, so a "
            "later mutation is absent from the bake and mutates the shared instance."
        )

    set_bold = _no_mutate
    set_italic = _no_mutate


# ---------------------------------------------------------------------------
# data fingerprint — one implementation, used by the baker AND at load
# ---------------------------------------------------------------------------


def code_fingerprint() -> str:
    """Hash of every source file that decides WHAT text is drawn, or HOW.

    The data fingerprint below cannot see any of this, and that gap was a real
    shipped-crash shape: adding a `当駅止まり` literal at a new point size changes no
    JSON, so the data fingerprint stayed identical, a stale atlas loaded happily,
    and it raised KeyError only at the terminus stop of every non-circular route —
    invisible in dev, where the live fonts serve any size. The same gap covers a
    layout edit: changing `compose_text_parts`'s `exp = 7` alters no cache key, so
    stored pixels would silently stop matching what the code now draws.

    Coarse on purpose. Any renderer edit invalidates the atlas, which costs nothing
    in practice: dev runs LIVE (the fonts are present) and `/build` re-bakes every
    run, so this only ever fires on a deliberately stale local atlas.
    """
    root = project_root()
    parts = []
    files = sorted(root.glob("displays/**/*.py"))
    files += [root / "font_atlas.py", root / "constants.py"]
    for p in files:
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        parts.append(f"{rel}:{hashlib.sha256(p.read_bytes()).hexdigest()}")
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()[:16]


def data_fingerprint() -> str:
    """Hash of every file whose contents can introduce new text to render.

    The baker stamps this into the manifest; loading compares. Keep the file set
    here in step with the baker's text domain — a source the domain reads but
    this ignores would change the text without changing the fingerprint, which
    is exactly the silent case this exists to prevent.
    """
    root = project_root()
    parts = []
    for p in sorted(root.glob("data/*.json")) + sorted(root.glob("audio/**/route.json")):
        rel = p.relative_to(root).as_posix()
        if any(seg.startswith("_") for seg in rel.split("/")):
            continue  # not shipped, so it cannot reach a shipped render
        parts.append(f"{rel}:{hashlib.sha256(p.read_bytes()).hexdigest()}")
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# text sources — what a renderer DECLARES it draws
# ---------------------------------------------------------------------------
#
# Coverage of the atlas must not depend on driving LCD state. Three axes were
# patched in sequence during this work — through-service frames, train models,
# lower-LCD slots — and each was a hole that had shipped or would have. An axis
# list is never provably complete, so a renderer states where its text COMES
# FROM and the bake satisfies that, leaving no reachability in the correctness
# path. Adding a slot or a view can then no longer break coverage.
#
# Declared at the `lcd_font` call site, so it cannot be separated from the code
# it describes, and validated at use, so it cannot drift from it. That pairing is
# the whole difference from the `_dev_scripts` combo table this replaces: that
# table sat far from the code with nothing forcing sync, and silently missed all
# nine transfer-panel sizes.


class Source:
    """Where a renderer's text comes from — a data location or a literal set."""

    __slots__ = ("locations", "literals", "prefix", "suffix", "split", "replace", "wrap")

    def __init__(self, locations=(), literals=(), prefix="", suffix="", split=False, replace=None, wrap=""):
        self.locations = tuple(locations)
        self.literals = tuple(literals)
        self.prefix, self.suffix = prefix, suffix
        self.split = split
        self.replace = tuple(replace) if replace else ()
        self.wrap = wrap

    def key(self) -> tuple:
        """Value identity, so two equivalent declarations share one cached font."""
        return (self.locations, self.literals, self.prefix, self.suffix, self.split, self.replace, self.wrap)

    def __repr__(self):
        bits = list(self.locations) + [repr(s) for s in self.literals]
        fix = f" {self.prefix!r}+..+{self.suffix!r}" if (self.prefix or self.suffix) else ""
        return f"Source({', '.join(bits)}{fix})"


def at(*locations: str, prefix: str = "", suffix: str = "", split=False, replace=None, wrap: str = "") -> Source:
    """Every value at these data locations, e.g. `audio/*/route.json:stops[].name`.

    Locations are fnmatch patterns over the keys `walk_shipped_json` produces, so
    `data/lines.json:*.name_ja` covers every line id without naming one.

    The options cover text a renderer DERIVES from a data value — text that exists
    in no JSON file, and would otherwise be in the atlas only because some state
    happened to be reachable:

      suffix=/prefix=  a composed form: `at(…, suffix="駅")` is the
                       `station_name + "駅"` transfer-panel header.
      replace=(a, b)   a substitution applied before drawing: the transfer panel
                       swaps the JSON's `・` for the narrower `·`.
      split=True       the whitespace-separated parts as well as the whole, for a
                       name laid out over two lines (a space inside a station name
                       is the data format's own line-break marker).
      split="·"        parts split on a given separator instead of whitespace.

    Applied in that order — replace, then split — because a renderer that
    substitutes and then splits is splitting on the substituted character.
    """
    return Source(locations=locations, prefix=prefix, suffix=suffix, split=split, replace=replace, wrap=wrap)


def lit(*strings: str) -> Source:
    """A fixed set of literals — text that lives in the source, not in the data."""
    return Source(literals=strings)


# Recurring declarations, named once so every renderer drawing the same KIND of
# text declares the same source — both train models draw station names, and a
# per-module copy of the location list is a copy that drifts. These are aliases,
# not claims: `check_declared` still validates real draws against them, so a name
# here cannot quietly over-promise.
# `split=True` tracks a data-format convention: a space inside a station name
# means "render over two vertical lines", so `さいたま 新都心` is drawn as
# `さいたま` + `新都心` — two strings that are values in no JSON file. See
# DATA_FORMAT.md § "Station names". The validator surfaced this on keihin/727B;
# before the declaration, both parts were in the atlas only because that stop
# happens to be reachable.
STATION_NAMES = at(
    "audio/*/route.json:stops[].name",
    "audio/*/route.json:pre_stops[].name",
    split=True,
)
# `{name}駅` — E235-0's transfer-panel header composes it at draw time, so the
# drawn string is in no JSON. Reuses STATION_NAMES' locations rather than copying
# the list, which is the drift this naming exists to prevent.
STATION_NAMES_EKI = at(*STATION_NAMES.locations, suffix="駅")
STATION_READINGS = at("data/translations.json:*.furigana", split=True)
DESTINATIONS = at(
    "audio/*/route.json:dest",
    "audio/*/route.json:stops[].dest",
    split=True,
)
TRAIN_TYPES = at("audio/*/route.json:type", "data/train_types.json:*")


def undeclared_sites() -> list:
    """Call-site signatures still resolving a baked face with no `draws=`.

    The migration's real finish line. Counting per COMBO is optimistic — ShinGo
    Medium @25 serves both the route-bar labels and the PA prefixes, so declaring
    one makes the combo look done while the other still rides on whatever the sweep
    happened to draw. A cache key is per call site (the declaration is part of it),
    so this counts sites.
    """
    return sorted({k[:4] for k in _cache if not k[4] and is_atlas_face(k[0])})


def _norm_file(rel: str) -> str:
    """Collapse a route path so every route shares one location.

    Every `route.json` has the same SHAPE, so a location must mean the same thing
    on all of them; per-route locations would make a declaration per-route and
    reintroduce the coverage-by-reachability this exists to remove.
    """
    return "audio/*/route.json" if rel.split("/")[0] == "audio" else rel


def walk_shipped_json() -> dict:
    """Every string VALUE in every shipped JSON, mapped to where it appears.

    Names no key. An earlier attempt derived the text domain by reading `stops`
    and missed the 18 stations in `sobu/1217F`'s `pre_stops`; naming keys IS the
    failure mode, so this knows nothing about any schema and finds both arrays
    precisely because it asks for neither.

    Returns `{string: {location, ...}}`, a location being
    `audio/*/route.json:pre_stops[].name` — list indices collapsed to `[]` so
    every member of an array shares one location. Cached; the file set is the same
    one `data_fingerprint` hashes, deliberately, so the domain and the staleness
    check can never disagree about what counts as a text source.
    """
    global _walk
    if _walk is not None:
        return _walk
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

    root = project_root()
    for p in sorted(root.glob("data/*.json")) + sorted(root.glob("audio/**/route.json")):
        rel = p.relative_to(root).as_posix()
        if any(seg.startswith("_") for seg in rel.split("/")):
            continue  # staging, not shipped
        rec(json.loads(p.read_text(encoding="utf-8")), _norm_file(rel) + ":")
    _walk = out
    return out


def resolve(source: Source, walk: Optional[dict] = None) -> set:
    """Every string a Source stands for, with prefix/suffix applied."""
    if walk is None:
        walk = walk_shipped_json()
    out = set(source.literals)
    for pattern in source.locations:
        for text, locs in walk.items():
            if any(fnmatch.fnmatchcase(loc, pattern) for loc in locs):
                out.add(text)
    if source.replace:
        old, new = source.replace
        out = {s.replace(old, new) for s in out}
    if source.wrap:
        # Greedy line-wrapping at a separator, KEEPING it on the leading line:
        # E235-0's transfer panel wraps 東北･山形･秋田･北海道･上越･北陸新幹線 to two
        # lines at a width-dependent point, so every boundary is a possible cut and
        # none of the resulting strings is a value in any file. Enumerating all of
        # them over-approximates by a handful per name and removes the dependence
        # on which width the panel happened to pick.
        sep, extra = source.wrap, set()
        for s in out:
            bits = s.split(sep)
            for i in range(1, len(bits)):
                extra.add(sep.join(bits[:i]) + sep)
                extra.add(sep.join(bits[i:]))
        out |= extra
    if source.split:
        sep = None if source.split is True else source.split
        out |= {part for s in out for part in s.split(sep)}
        if sep is None:
            # A space inside a station name is the data format's line-break marker,
            # and the two LCDs treat it differently: the lower route bar HONOURS it
            # (さいたま over 新都心) while the upper station name IGNORES it, drawing
            # さいたま新都心 on one line. Both are derivations of the same marker, so a
            # source that declares one declares the other.
            out |= {"".join(s.split()) for s in out}
    if source.prefix or source.suffix:
        out = {source.prefix + s + source.suffix for s in out}
    return out


def declared_domain(font) -> Optional[tuple]:
    """`(strings, characters)` a font's call site declared, or None if undeclared.

    Cached on the font: resolving walks the whole shipped-JSON index, and this is
    consulted on every draw in dev.
    """
    draws = getattr(font, "_draws", None)
    if not draws:
        return None
    cached = getattr(font, "_domain", None)
    if cached is None:
        strings = set()
        for s in draws:
            strings |= resolve(s)
        # Characters as well as whole strings: the route-bar labels measure the
        # whole name and then draw it one character at a time.
        cached = (strings, {c for s in strings for c in s})
        font._domain = cached
    return cached


def check_declared(font, text: str) -> None:
    """Raise if `text` falls outside what this font's call site declared.

    The half that keeps a declaration honest. An undeclared draw fails on the
    first dev frame that performs it, so the declaration cannot quietly fall
    behind the code — which is the failure mode of every table this replaces.
    Fonts with no declaration are not checked, so sites migrate one at a time.
    """
    dom = declared_domain(font)
    if dom is None or not text:
        return
    strings, chars = dom
    if text in strings or (len(text) == 1 and text in chars):
        return
    raise ValueError(
        f"font_atlas: {getattr(font, '_id', font)} drew {text!r}, which is outside what "
        f"its call site declared: {list(getattr(font, '_draws', ()))}. Either widen the "
        f"`draws=` declaration at that lcd_font() call, or draw text that comes from a "
        f"declared source. An undeclared string is absent from the bake, so it is a "
        f"KeyError in a build that ships no font files."
    )


def force_mode(mode: Optional[str]) -> None:
    """Pin the mode instead of auto-detecting. `None` restores auto-detection.

    Used by the verification pass that renders the same frames both ways and
    requires zero pixel difference.
    """
    global _forced, _mode, _cache, _atlas
    _forced, _mode, _atlas = mode, None, None
    _cache.clear()


def mode() -> str:
    global _mode
    if _mode is None:
        if _forced:
            _mode = _forced
        else:
            have_fonts = (project_root() / "fonts").is_dir()
            have_atlas = (project_root() / ATLAS_DIRNAME / "manifest.json").is_file()
            if not have_fonts and not have_atlas:
                raise RuntimeError(
                    f"font_atlas: neither {project_root() / 'fonts'} nor a baked atlas at "
                    f"{project_root() / ATLAS_DIRNAME} exists. Put your licensed fonts in "
                    "fonts/ to develop against live fonts, or run "
                    "`uv run _dev_scripts/bake_font_atlas.py` to bake an atlas from them."
                )
            _mode = LIVE if have_fonts else ATLAS
    return _mode


class Atlas:
    """A baked atlas: shelf-packed sheets plus the measurement scalars."""

    def __init__(self, root):
        self.root = root
        self.manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        for label, key, current, why in (
            ("data", "data_fingerprint", data_fingerprint(), "Route or translation data changed, so the atlas may be missing text."),
            (
                "code",
                "code_fingerprint",
                code_fingerprint(),
                "A renderer changed, so it may draw text or a point size that was never " "baked, or lay text out differently from what is stored.",
            ),
        ):
            stamped = self.manifest.get(key)
            if stamped != current:
                raise RuntimeError(
                    f"font_atlas: atlas is STALE on the {label} fingerprint. Baked from "
                    f"{stamped!r}; now {current!r}. {why} Re-run "
                    "`uv run _dev_scripts/bake_font_atlas.py`."
                )
        self._sheets: Dict[str, pygame.Surface] = {}
        self._by_key = {(c["face"], c["size"], c["bold"], c["italic"]): c for c in self.manifest["combos"]}

    def combo(self, key):
        return self._by_key.get(key)

    def sheet(self, name: str) -> pygame.Surface:
        s = self._sheets.get(name)
        if s is None:
            s = pygame.image.load(str(self.root / name))
            self._sheets[name] = s
        return s


def _load_atlas() -> Atlas:
    global _atlas
    if _atlas is None:
        _atlas = Atlas(project_root() / ATLAS_DIRNAME)
    return _atlas


class AtlasFont:
    """Serves a baked combo through the pygame.font.Font surface callers use.

    `render` reconstructs from stored alpha coverage: SDL_ttf's blended render
    produces `RGB = colour, A = coverage`, so filling a flat colour against the
    stored coverage reproduces it exactly, and one entry serves every colour.
    The opaque `render(..., background)` form is stored as SDL composited it,
    because that blend is not reproduced here — so colour is part of its key.
    """

    def __init__(self, atlas: Atlas, combo: dict, ident):
        self._atlas, self._c, self._id = atlas, combo, ident

    def _entry(self, text, color=None, bg=None):
        if bg is not None:
            table = self._c["entries_bg"]
            key = f"{list(color)[:3]}|{list(bg)[:3]}|{text}"
        else:
            table, key = self._c["entries"], text
        e = table.get(key)
        if e is None:
            raise KeyError(
                f"font_atlas: nothing baked for {self._id} text={text!r} colour={color!r} "
                f"bg={bg!r}. Re-run `uv run _dev_scripts/bake_font_atlas.py`; if the text is "
                "new, check the baker's text domain covers its source."
            )
        return e

    def render(self, text, antialias, color, background=None):
        if text == "":
            return pygame.Surface((0, self._c["get_height"]), pygame.SRCALPHA, 32)
        e = self._entry(text, color, background)
        sheet = self._atlas.sheet(e["sheet"])
        region = pygame.Rect(e["x"], e["y"], e["w"], e["h"])
        if background is not None:
            out = pygame.Surface((e["w"], e["h"]))
            out.blit(sheet, (0, 0), region)
            return out
        out = pygame.Surface((e["w"], e["h"]), pygame.SRCALPHA, 32)
        out.fill((color[0], color[1], color[2], 0))
        alpha = pygame.surfarray.pixels_alpha(out)
        alpha[:] = pygame.surfarray.array_alpha(sheet.subsurface(region))
        del alpha
        return out

    def size(self, text):
        """Measure text. Not every measured string has pixels.

        `draw_text_given_width` measures the WHOLE string (utils.py:642) to pick
        a compression ratio, then renders it one character at a time. So the
        assembled name is measured but never drawn — the baker stores its two
        numbers in `sizes` and spends no atlas area on it.
        """
        if text == "":
            return (0, self._c["get_height"])
        m = self._c["sizes"].get(text)
        if m is not None:
            return tuple(m)
        return tuple(self._entry(text)["size"])

    def metrics(self, text):
        out = []
        for ch in text:
            m = self._c["metrics"].get(ch, "absent")
            if m == "absent":
                # NOT None: callers use a None metric as "this face has no glyph"
                # and reroute to a CJK fallback. Conflating the two would silently
                # reroute a new station's kanji instead of tripping this.
                raise KeyError(f"font_atlas: character {ch!r} (U+{ord(ch):04X}) was never baked for " f"{self._id}. Re-run the baker.")
            out.append(tuple(m) if m is not None else None)
        return out

    def get_height(self):
        return self._c["get_height"]

    def get_ascent(self):
        return self._c["get_ascent"]


class RecordingFont:
    """A live font that logs what production asked it for.

    Not every LCD text goes through `compose_text_block`: the destination suffix,
    the countdown 分, the transfer banner and the route-bar labels call `render`,
    `size` or `metrics` directly. Those calls are captured here, so the worklist
    is what the app did rather than what a baker guessed it would do.
    """

    def __init__(self, font, ident, sink):
        self._f, self._id, self._sink = font, ident, sink

    def _log(self, table, key, value):
        if _suppressed:
            return
        self._sink.setdefault(self._id, {}).setdefault(table, {})[key] = value

    def render(self, text, antialias, color, background=None):
        surf = self._f.render(text, antialias, color, background)
        if text != "":
            if background is None:
                self._log("entries", text, surf)
            else:
                self._log("entries_bg", f"{list(color)[:3]}|{list(background)[:3]}|{text}", surf)
        return surf

    def size(self, text):
        s = self._f.size(text)
        if text != "":
            self._log("sizes", text, list(s))
        return s

    def metrics(self, text):
        m = self._f.metrics(text)
        for ch, entry in zip(text, m):
            self._log("metrics", ch, list(entry) if entry else None)
        return m

    def get_height(self):
        self._log("scalars", "get_height", self._f.get_height())
        return self._f.get_height()

    def get_ascent(self):
        self._log("scalars", "get_ascent", self._f.get_ascent())
        return self._f.get_ascent()

    def __getattr__(self, name):  # anything not overridden goes to the real font
        return getattr(self._f, name)


def ident_of(font):
    """The atlas identity of a font, or None if it isn't atlas-backed.

    Only fonts handed out by `lcd_font` are atlas-backed. Helvetica and Frutiger
    ship with the app, so text drawn in them composes live in every mode — which
    is why this returns None for them rather than raising.
    """
    return getattr(font, "_id", None)


def _block_key(text, color, width, collapse, script) -> str:
    """Identity of a laid-out block.

    Colour is IN the key rather than reapplied at blit time. The block is a
    composite of several already-coloured character surfaces, some of them
    scaled; re-deriving a flat colour from that composite would be an argument I
    would have to keep making, and the colour set here is small (WHITE_BG plus
    the per-route type colours).
    """
    return f"{width}|{int(bool(collapse))}|{script}|{list(color)[:3]}|{text}"


def text_parts(compose, font, text, color, width, collapse=False, script="japanese"):
    """The laid-out parts for `text` — composed live, or read back from the atlas.

    `compose` is `displays.utils.compose_text_parts`, passed in rather than
    imported so the dependency points one way. In LIVE mode this calls it; in
    ATLAS mode it is never called, because the atlas holds precisely what it
    returned at bake time. One layout implementation, its output stored, so
    spacing / compression / branch selection cannot diverge between the modes.

    Parts come back in the order they were composed, and the caller blits them in
    that order — the same sequence of blits the LCD has always done.
    """
    ident = ident_of(font)
    if ident is None:
        # Not atlas-backed: Helvetica and Frutiger ship with the app, so their
        # text lays out live in every mode.
        return compose(font, text, color, width, collapse, script)

    key = _block_key(text, color, width, collapse, script)

    if mode() == ATLAS:
        atlas = _load_atlas()
        combo = atlas.combo(ident)
        stored = (combo or {}).get("parts", {}).get(key)
        if stored is None:
            raise KeyError(
                f"font_atlas: no baked parts for {ident} {key!r}. The bake records what "
                "the app actually draws, so this state was never visited — re-run "
                "`uv run _dev_scripts/bake_font_atlas.py`."
            )
        out = []
        for e in stored:
            surf = pygame.Surface((e["w"], e["h"]), pygame.SRCALPHA, 32)
            surf.blit(atlas.sheet(e["sheet"]), (0, 0), pygame.Rect(e["x"], e["y"], e["w"], e["h"]))
            out.append((e["off"], surf))
        return out

    _suppress(True)
    try:
        parts = compose(font, text, color, width, collapse, script)
    finally:
        _suppress(False)
    if _record is not None and parts:
        _record.setdefault(ident, {}).setdefault("parts", {})[key] = parts
    return parts


def _suppress(on: bool) -> None:
    """Mute recording while composing.

    Composing calls `font.render` / `font.size` per character, but ATLAS mode
    never runs the compose path — it replays the parts. Recording those inner
    calls would bake several hundred character surfaces per combo that nothing
    ever looks up, which is the indiscriminate dump this design exists to avoid.
    Direct `render` / `size` / `metrics` calls from the renderers are outside
    this window and stay recorded.
    """
    global _suppressed
    _suppressed = on


def start_recording() -> dict:
    """Capture what production draws. Returns the sink the baker reads."""
    global _record
    _record = {}
    return _record


def lcd_font(face: str, size: float, *, bold: bool = False, italic: bool = False, draws=None):
    """Resolve an LCD font by face filename + point size. Cached.

    `draws` declares where this call site's text comes from — `at("…json:path")`
    and/or `lit("次は", …)`, one Source or several. Declaring it is what puts the
    text in the bake without any state having to be reachable, and it is checked
    on every draw in dev, so an undeclared string fails immediately rather than
    becoming a KeyError in a build that ships no fonts. Undeclared sites keep
    working off sweep discovery, so migration is one call at a time.

    `bold` / `italic` request pygame's synthetic emboldening / slant as part of
    the font's IDENTITY, so a styled face is its own entry. Callers must not
    call set_bold()/set_italic() on the result: a post-construction mutation is
    invisible to the baker and would corrupt the shared cached instance.
    """
    if isinstance(draws, Source):
        draws = (draws,)
    draws = tuple(draws) if draws else ()

    ident = (face, max(1, int(round(size))), bool(bold), bool(italic))
    # Declarations are part of the cache key, not merged onto one shared font.
    # ShinGo Medium @25 serves BOTH the whole-string PA prefixes and the
    # per-character route-bar labels; a shared instance would carry whichever
    # declaration got there first and mis-validate the other site.
    key = ident + (tuple(d.key() for d in draws),)
    f = _cache.get(key)
    if f is not None:
        return f

    baked = is_atlas_face(face)
    if baked and mode() == ATLAS:
        atlas = _load_atlas()
        combo = atlas.combo(ident)
        if combo is None:
            raise KeyError(f"font_atlas: no baked combo {ident}. Re-run " "`uv run _dev_scripts/bake_font_atlas.py`.")
        f = AtlasFont(atlas, combo, ident)
    else:
        # `ident=None` for a face that ships with the app: `ident_of` then returns
        # None, so `text_parts` composes it live in both modes. Call sites still
        # route it through here, so none of them has to know which families are
        # baked — that fact lives only in ATLAS_FACES.
        f = LcdFont(str(project_root() / "fonts" / face), ident[1], ident if baked else None)
        # Through the base class: LcdFont.set_bold/set_italic raise, so that the
        # style cannot be changed anywhere BUT here, where it is part of the key.
        if bold:
            pygame.font.Font.set_bold(f, True)
        if italic:
            pygame.font.Font.set_italic(f, True)
    f._draws = draws

    if baked and mode() != ATLAS and _record is not None:
        # Record the REQUEST, not just the renders. A face can be constructed and
        # never drawn through — the transfer panel builds a CJK fallback for its
        # English variant that only fires when the Latin face lacks a glyph.
        # Without this the combo is absent from the manifest and ATLAS mode raises
        # at construction, before any lookup.
        rec = _record.setdefault(ident, {})
        if draws:
            # Hand the declaration to the baker. It cooks a declared combo from
            # `resolve(...)` rather than from what the sweep happened to draw, which
            # is what takes state reachability out of the coverage path. One ident
            # can be declared by several call sites (ShinGo Medium @25 serves both
            # the PA prefixes and the route-bar labels), so accumulate by value.
            declared = rec.setdefault("draws", [])
            known = {d.key() for d in declared}
            declared.extend(d for d in draws if d.key() not in known)
        f = RecordingFont(f, ident, _record)

    _cache[key] = f
    return f
