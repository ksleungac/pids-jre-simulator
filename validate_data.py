"""Validate the project's authored data against the DATA_FORMAT.md spec.

Covers route.json files (per audio/<line>/<diagram>/) and the top-level
data/{translations,train_types,stations,lines}.json catalogs, including
cross-references between them (transfer slugs resolve in lines.json,
badge icons exist on disk, etc.).

Usage: PYTHONUTF8=1 python validate_data.py [--quiet]
Exits 0 if clean, 1 if issues found.
"""

import os

# Suppress pygame's greeting on import — we transitively pull pygame via
# `displays.transfer_info` (for production's slug-resolution parser) +
# `route_loader` (for the loader smoke-check). Validator output should
# not include the library banner.
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import json
import re
import sys
from pathlib import Path

# Kanji-bearing issue text (station names, _resolve_frames errors) crashes on
# cp1252 stdout under a piped/CI run. Reconfigure at entry — same fix as the
# harness sensors. See conventions.md § Tooling.
sys.stdout.reconfigure(encoding="utf-8")

SUFFIX_RE = re.compile(r"_[A-Z]{2,}$")
AUDIO_ROOT = Path("audio")
DATA_ROOT = Path("data")
LINE_ICONS_DIR = DATA_ROOT / "line_icons"

PASSING_FORBIDDEN = ("sta", "sta_cut", "time", "pa_at_station")
PRE_STOP_FORBIDDEN = ("pa", "pa_at_station", "sta", "sta_cut", "time")
VALID_LINE_CATEGORIES = {"jr_east", "shinkansen", "non_jr"}
# Active-line badge codes (route-level `line_code`) — drives the transfer-info
# active-line filter. See DATA_FORMAT.md § Route-Level Fields.
VALID_LINE_CODES = {"JY", "JK", "JC", "JO", "JU", "JT", "JJ", "JE", "JN", "JA"}
# UI-chrome locales every data/translations_app.json key must carry.
APP_LOCALES = ("en", "zh_HK", "zh_CN")


def load(path) -> dict:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def is_fixture(rel: str) -> bool:
    """A route under audio/_*/ is a fixture (mock catalog, archive). Skip
    cross-reference checks (translations existence, audio file existence)
    for fixtures — they intentionally use out-of-scope strings + lack real
    audio. Shape rules still apply (passing-forbidden, first-time=0, etc.)."""
    return rel.startswith("_") or "/_" in rel


def _check_badge_icons(slug: str, badges: list, suffix: str, issues: list) -> None:
    """Each badge.icon must have a matching <icon>.png under data/line_icons/."""
    for badge in badges:
        icon = badge.get("icon")
        if not icon:
            continue
        if not (LINE_ICONS_DIR / f"{icon}.png").exists():
            issues.append(("data/lines.json", f"'{slug}{suffix}': badge icon '{icon}.png' missing in data/line_icons/"))


def check_lines_json(lines_data: dict, issues: list) -> None:
    """lines.json shape: category enum + badge icons exist on disk
    (base + variants)."""
    for slug, entry in lines_data.items():
        cat = entry.get("category")
        if cat is not None and cat not in VALID_LINE_CATEGORIES:
            issues.append(("data/lines.json", f"'{slug}': category={cat!r} — not in {sorted(VALID_LINE_CATEGORIES)}"))

        _check_badge_icons(slug, entry.get("badges", []), "", issues)
        for vname, vdata in entry.get("variants", {}).items():
            _check_badge_icons(slug, vdata.get("badges", []), f".{vname}", issues)


def _resolve_slug_ref(ref: str, lines_data: dict) -> tuple[bool, str]:
    """Resolve a slug reference via production's parser
    (``displays.transfer_info.resolve_entry``). Returns (ok, error_msg).

    Reusing production's parser is dual-purpose: validator and runtime can't
    drift on what counts as a valid reference (e.g. `.scale(abc)` rejected
    identically), AND running the validator exercises production code on
    every authored data point — bugs in resolve_entry surface here.

    Beyond "does it resolve", require the name fields the transfer renderers
    hard-subscript — ``name_ja`` (both models) + ``name_en`` (e235_1000,
    transfer_info.py:283/305). A slug whose names live ONLY in its variants,
    referenced plain (no `.variant`), resolves cleanly but yields a name-less
    entry → the renderer KeyErrors at draw time, far from the data gate. Catch
    it here, where the message can name the slug. This is validator-only:
    production's badge/filter path calls ``resolve_entry`` directly and
    tolerates name-less entries (``_resolve_badges`` reads only ``badges``), so
    this never reaches it — the guard belongs at the data gate, not the shared
    resolver."""
    from displays.transfer_info import resolve_entry

    try:
        entry = resolve_entry(ref, lines_data)
    except (KeyError, ValueError) as e:
        return False, str(e).strip("'\"")
    missing = [f for f in ("name_ja", "name_en") if f not in entry]
    if missing:
        return False, f"'{ref}' resolves but lacks {'/'.join(missing)} — reference it with a '.variant' that provides the name fields"
    return True, ""


def check_stations_transfers(stations_data: dict, lines_data: dict, issues: list) -> None:
    """Every transfers[] slug resolves in lines.json; '.variant' refs match a
    declared variant; dot-notation depth ≤ 1."""
    for sname, sdata in stations_data.items():
        for entry in sdata.get("transfers", []):
            ok, err = _resolve_slug_ref(entry, lines_data)
            if not ok:
                issues.append(("data/stations.json", f"'{sname}': {err}"))


def check_transfers_by_view(stations_data: dict, lines_data: dict, issues: list) -> None:
    """Per-view ops on a station's transfers:
    - drop entries must match a base slug already in transfers[]
    - edit keys must match a base slug in transfers[]; edit values must resolve in lines.json
    - rows array must sum to len(transfers) - len(drop)  (edit doesn't change count)
    """
    from displays.transfer_info import SCALE_SUFFIX_RE

    for sname, sdata in stations_data.items():
        transfers = sdata.get("transfers", [])
        base_slugs_in_transfers = {SCALE_SUFFIX_RE.sub("", entry).split(".")[0] for entry in transfers}
        for view_key, ops in sdata.get("transfers_by_view", {}).items():
            # drop validity
            for d in ops.get("drop", []):
                if d not in base_slugs_in_transfers:
                    issues.append(("data/stations.json", f"'{sname}' view '{view_key}': drop '{d}' — not a base slug in transfers[]"))
            # edit validity
            for ek, ev in ops.get("edit", {}).items():
                if ek not in base_slugs_in_transfers:
                    issues.append(("data/stations.json", f"'{sname}' view '{view_key}': edit key '{ek}' — not a base slug in transfers[]"))
                ok, err = _resolve_slug_ref(ev, lines_data)
                if not ok:
                    issues.append(("data/stations.json", f"'{sname}' view '{view_key}': edit value {err}"))
            # rows sum (edit doesn't change count, so post-ops count = len(transfers) - len(drop))
            rows = ops.get("rows")
            if rows is not None:
                expected = len(transfers) - len(ops.get("drop", []))
                if sum(rows) != expected:
                    issues.append(
                        (
                            "data/stations.json",
                            f"'{sname}' view '{view_key}': rows={rows} sum={sum(rows)} — expected {expected} (len(transfers) - len(drop))",
                        )
                    )


def _check_color(rel: str, field: str, val, issues: list) -> None:
    """A color field, when present, must be [R, G, B] ints in 0-255. Colors are
    consumed at render time, so a malformed value slips past the loader
    smoke-check and only crashes / mis-renders in the live drive."""
    if val is None:
        return
    if not (isinstance(val, list) and len(val) == 3 and all(isinstance(c, int) and 0 <= c <= 255 for c in val)):
        issues.append((rel, f"{field}={val!r}: expected [R, G, B] ints 0-255"))


def check_app_translations(issues: list) -> None:
    """data/translations_app.json: every key carries all APP_LOCALES with a
    non-empty value, and {placeholder} tokens match across locales. Guards the
    recurring missing-locale-key -> tofu / dropped-{placeholder} -> format-break
    class (e.g. the packaged zh_CN tofu). EN is the placeholder reference
    (authoritative per the file's own _comment)."""
    data = load(DATA_ROOT / "translations_app.json")
    ph = re.compile(r"\{[^}]+\}")
    for key, val in data.items():
        if key.startswith("_"):  # _comment metadata
            continue
        if not isinstance(val, dict):
            issues.append(("data/translations_app.json", f"'{key}': expected {{locale: text}} object"))
            continue
        for loc in APP_LOCALES:
            if loc not in val:
                issues.append(("data/translations_app.json", f"'{key}': missing '{loc}' translation"))
            elif not val[loc]:
                issues.append(("data/translations_app.json", f"'{key}': '{loc}' is empty"))
        en_ph = set(ph.findall(val["en"])) if isinstance(val.get("en"), str) else set()
        for loc in APP_LOCALES:
            if loc == "en" or not isinstance(val.get(loc), str):
                continue
            loc_ph = set(ph.findall(val[loc]))
            if loc_ph != en_ph:
                issues.append(("data/translations_app.json", f"'{key}': '{loc}' placeholders {sorted(loc_ph)} != en {sorted(en_ph)}"))


def check_route(route_path: Path, translations: dict, train_types: dict, issues: list) -> None:
    rel = route_path.parent.relative_to(AUDIO_ROOT).as_posix()
    try:
        data = load(route_path)
    except json.JSONDecodeError as e:
        issues.append((rel, f"JSON parse error: {e}"))
        return

    fixture = is_fixture(rel)

    # Route-level: type → train_types.json (cross-ref)
    route_type = data.get("type", "")
    if not fixture and route_type and route_type not in train_types:
        issues.append((rel, f'type "{route_type}": no train_types.json entry'))

    # Route-level: dest → translations (cross-ref)
    dest = data.get("dest", "")
    if not fixture and dest and dest not in translations:
        issues.append((rel, f'dest "{dest}": no translations.json entry'))

    # Route-level: model → train-model registry (cross-ref)
    model = data.get("model")
    if not fixture and model:
        from displays.train_models import TRAIN_MODELS

        if model not in TRAIN_MODELS:
            issues.append((rel, f'model "{model}": not a registered train model (displays/train_models)'))

    # Route-level: line_code enum + color [R,G,B] shape
    line_code = data.get("line_code")
    if not fixture and line_code and line_code not in VALID_LINE_CODES:
        issues.append((rel, f'line_code "{line_code}": not a known active-line code {sorted(VALID_LINE_CODES)}'))
    if not fixture:
        for cfield in ("color", "contrast_color", "type_color"):
            _check_color(rel, cfield, data.get(cfield), issues)

    # pre_stops shape (shape rule, applies to fixtures too)
    for i, ps in enumerate(data.get("pre_stops", [])):
        psname = ps.get("name", "?")
        if "name" not in ps:
            issues.append((rel, f"pre_stops[{i}]: missing required 'name'"))
        if "sta_code" not in ps:
            issues.append((rel, f"pre_stops[{i}] {psname}: missing required 'sta_code'"))
        for forbidden in PRE_STOP_FORBIDDEN:
            if forbidden in ps:
                issues.append((rel, f"pre_stops[{i}] {psname}: '{forbidden}' forbidden"))

    # Stop-level
    stops = data.get("stops", [])
    for i, stop in enumerate(stops):
        name = stop.get("name", "?")
        is_first = i == 0

        # pa field required (shape rule). Without this, downstream rules
        # silently bypass on missing pa.
        if "pa" not in stop:
            issues.append((rel, f"[{i}] {name}: missing required 'pa' field"))
            continue  # downstream rules depend on pa

        is_passing = stop["pa"] == [] and not is_first

        # sta_code presence + no _XX suffix (shape)
        if "sta_code" not in stop:
            issues.append((rel, f"[{i}] {name}: missing sta_code key"))
        else:
            sc = stop["sta_code"]
            if isinstance(sc, str) and SUFFIX_RE.search(sc):
                issues.append((rel, f'[{i}] {name}: sta_code "{sc}" has suffix'))

        # name → translations (cross-ref)
        if not fixture and name and name not in translations:
            issues.append((rel, f"[{i}] {name}: no translations.json entry"))

        # stop-level dest → translations (cross-ref)
        stop_dest = stop.get("dest")
        if not fixture and stop_dest and stop_dest not in translations:
            issues.append((rel, f'[{i}] {name}: dest "{stop_dest}" no translation'))

        # Passing station forbidden fields (shape)
        if is_passing:
            for forbidden in PASSING_FORBIDDEN:
                if forbidden in stop:
                    issues.append((rel, f"[{i}] {name}: passing has '{forbidden}' (forbidden)"))

        # First station: time must be 0 (shape)
        if is_first and stop.get("time") != 0:
            issues.append((rel, f"[{i}] {name}: first station time={stop.get('time')!r} (expected 0)"))

        # Non-first non-passing stops: time required (shape)
        if not is_first and not is_passing and "time" not in stop:
            issues.append((rel, f"[{i}] {name}: missing required 'time' field"))

    # Audio file references (cross-ref)
    if not fixture:
        # Resolve through the same single-root helper the runtime uses, so a
        # shared-pool route validates against the pool it will actually read.
        from route_loader import resolve_audio_root

        audio_dir = resolve_audio_root(route_path.parent, data)
        pa_dir = audio_dir / "pa"
        sta_dir = audio_dir / "sta"
        for i, stop in enumerate(stops):
            for track in stop.get("pa") or []:
                if track and not (pa_dir / f"{track}.mp3").exists():
                    issues.append((rel, f"[{i}] {stop.get('name')}: pa/{track}.mp3 missing"))
            for track in stop.get("pa_at_station") or []:
                if track and not (pa_dir / f"{track}.mp3").exists():
                    issues.append((rel, f"[{i}] {stop.get('name')}: pa/{track}.mp3 (at-station) missing"))
            for track in stop.get("sta") or []:
                if track and not (sta_dir / f"{track}.mp3").exists():
                    issues.append((rel, f"[{i}] {stop.get('name')}: sta/{track}.mp3 missing"))


def check_route_transfer_view(route_path: Path, stations_data: dict, issues: list) -> None:
    """Each route's ``transfer_view`` must be consumed by at least one stop
    on the route — i.e. some stop in ``stops[]`` has a stations.json entry
    with this view key in its ``transfers_by_view``. Otherwise the view
    config is dead on this route (every stop's transfer-info renders raw,
    no drop/edit/rows ops apply).

    Direction matters: we check route -> stop -> station.transfers_by_view,
    NOT station.transfers_by_view -> route. The reverse direction would
    false-positive on station configs that are forward-looking or
    test-only (e.g. 大船/武蔵小杉's JO_north).
    """
    rel = route_path.parent.relative_to(AUDIO_ROOT).as_posix()
    data = load(route_path)
    transfer_view = data.get("transfer_view")
    if not transfer_view:
        return
    stops = data.get("stops", [])
    consumed = any(transfer_view in stations_data.get(stop.get("name", ""), {}).get("transfers_by_view", {}) for stop in stops)
    if not consumed:
        issues.append(
            (rel, f"transfer_view '{transfer_view}': no stop on this route has a stations.json transfers_by_view entry for it (config is dead)")
        )


def check_route_frames(route_path: Path, issues: list) -> None:
    """Through-service ``frames[]`` authored-shape: each entry carries
    string ``from`` / ``to`` / ``line`` keys. Collects every shape issue
    (loader fails fast on the first).

    Semantic validation — ``from``/``to`` resolve to a stop, ``line``
    resolves in lines.json, frames abut at the shared boundary + tile the
    whole route — lives solely in ``route_loader._resolve_frames`` and
    surfaces via ``check_route_loads``. Not re-checked here, to keep one
    source of truth for the frame rules (per principles.md "Sync downstream
    enforcers"). See DATA_FORMAT.md § frames.
    """
    rel = route_path.parent.relative_to(AUDIO_ROOT).as_posix()
    frames = load(route_path).get("frames")
    if not frames:
        return
    if not isinstance(frames, list):
        issues.append((rel, f"frames: expected array, got {type(frames).__name__}"))
        return
    for i, fr in enumerate(frames):
        if not isinstance(fr, dict):
            issues.append((rel, f"frames[{i}]: expected object, got {type(fr).__name__}"))
            continue
        for key in ("from", "to", "line"):
            if key not in fr:
                issues.append((rel, f"frames[{i}]: missing required '{key}'"))
            elif not isinstance(fr[key], str):
                issues.append((rel, f"frames[{i}]: '{key}' must be a string"))


def check_route_loads(route_path: Path, station_db: dict, issues: list) -> None:
    """Smoke-check: route.json runs through production's loader without
    crashing. Catches anything ``route_loader.finalize_route`` trips on
    (missing fields, dict shape mismatches, future loader-time
    computations). Dual-purpose — surfaces loader bugs on real authored
    data the moment the validator runs.

    Today the loader is intentionally lenient (silent skip on missing
    keys), so this fires rarely. Value grows as more loader-time
    computations are added per the principle "JSON is input grammar;
    runtime is the closure."
    """
    from route_loader import load_route_from_dir

    rel = route_path.parent.relative_to(AUDIO_ROOT).as_posix()
    try:
        load_route_from_dir(route_path.parent, station_db)
    except Exception as e:
        issues.append((rel, f"route_loader.finalize_route raised {type(e).__name__}: {e}"))


def main():
    quiet = "--quiet" in sys.argv
    route_arg = None
    if "--route" in sys.argv:
        idx = sys.argv.index("--route")
        if idx + 1 >= len(sys.argv):
            print("--route requires an argument", file=sys.stderr)
            sys.exit(1)
        route_arg = Path(sys.argv[idx + 1])

    translations = load(DATA_ROOT / "translations.json")
    train_types = load(DATA_ROOT / "train_types.json")
    stations = load(DATA_ROOT / "stations.json")
    lines = load(DATA_ROOT / "lines.json")

    if not quiet and route_arg is None:
        print(f"translations.json: {len(translations)} entries")
        print(f"train_types.json:  {len(train_types)} entries")
        print(f"stations.json:     {len(stations)} entries")
        print(f"lines.json:        {len(lines)} entries")
        n_code_3 = sum(1 for v in stations.values() if "code_3" in v)
        print(f"stations.json code_3 count: {n_code_3} (spec: 22)")
        if n_code_3 != 22:
            print(f"  WARNING: code_3 count drifted from documented 22")

    issues = []

    if route_arg is None:
        check_lines_json(lines, issues)
        check_stations_transfers(stations, lines, issues)
        check_transfers_by_view(stations, lines, issues)
        check_app_translations(issues)
        route_paths = sorted(AUDIO_ROOT.rglob("route.json"))
    else:
        route_paths = [route_arg]

    for route_path in route_paths:
        rel = route_path.parent.relative_to(AUDIO_ROOT).as_posix()
        # Full-scan = shipped-data gate; `_*/` routes (mock / archive / WIP like
        # _joban) are not shipped, so don't gate the release on them. An explicit
        # --route still validates whatever's named (fixture-aware in check_route).
        if route_arg is None and is_fixture(rel):
            continue
        check_route(route_path, translations, train_types, issues)
        check_route_frames(route_path, issues)
        check_route_loads(route_path, translations, issues)
        check_route_transfer_view(route_path, stations, issues)

    if not issues:
        if not quiet and route_arg is None:
            print("\nAll routes clean.")
        return 0

    # Group by file path (route or top-level data file)
    by_file = {}
    for rel, msg in issues:
        by_file.setdefault(rel, []).append(msg)
    print(f"\n{len(issues)} issues across {len(by_file)} locations:")
    for rel in sorted(by_file):
        print(f"\n{rel}")
        for msg in by_file[rel]:
            print(f"  - {msg}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
