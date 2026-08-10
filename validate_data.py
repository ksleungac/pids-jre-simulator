# SPDX-License-Identifier: MIT
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


def _is_within(child: Path, parent: Path) -> bool:
    """True if `child` is `parent` or lies under it. Path relation, not string prefix."""
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


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


# Kana -> romaji, enough to re-derive a station name's English from its reading.
# Digraphs must be tried before single kana.
_KANA_2 = {
    "きゃ": "kya",
    "きゅ": "kyu",
    "きょ": "kyo",
    "しゃ": "sha",
    "しゅ": "shu",
    "しょ": "sho",
    "ちゃ": "cha",
    "ちゅ": "chu",
    "ちょ": "cho",
    "にゃ": "nya",
    "にゅ": "nyu",
    "にょ": "nyo",
    "ひゃ": "hya",
    "ひゅ": "hyu",
    "ひょ": "hyo",
    "みゃ": "mya",
    "みゅ": "myu",
    "みょ": "myo",
    "りゃ": "rya",
    "りゅ": "ryu",
    "りょ": "ryo",
    "ぎゃ": "gya",
    "ぎゅ": "gyu",
    "ぎょ": "gyo",
    "じゃ": "ja",
    "じゅ": "ju",
    "じょ": "jo",
    "びゃ": "bya",
    "びゅ": "byu",
    "びょ": "byo",
    "ぴゃ": "pya",
    "ぴゅ": "pyu",
    "ぴょ": "pyo",
}
_KANA_1 = {
    "あ": "a",
    "い": "i",
    "う": "u",
    "え": "e",
    "お": "o",
    "か": "ka",
    "き": "ki",
    "く": "ku",
    "け": "ke",
    "こ": "ko",
    "が": "ga",
    "ぎ": "gi",
    "ぐ": "gu",
    "げ": "ge",
    "ご": "go",
    "さ": "sa",
    "し": "shi",
    "す": "su",
    "せ": "se",
    "そ": "so",
    "ざ": "za",
    "じ": "ji",
    "ず": "zu",
    "ぜ": "ze",
    "ぞ": "zo",
    "た": "ta",
    "ち": "chi",
    "つ": "tsu",
    "て": "te",
    "と": "to",
    "だ": "da",
    "ぢ": "ji",
    "づ": "zu",
    "で": "de",
    "ど": "do",
    "な": "na",
    "に": "ni",
    "ぬ": "nu",
    "ね": "ne",
    "の": "no",
    "は": "ha",
    "ひ": "hi",
    "ふ": "fu",
    "へ": "he",
    "ほ": "ho",
    "ば": "ba",
    "び": "bi",
    "ぶ": "bu",
    "べ": "be",
    "ぼ": "bo",
    "ぱ": "pa",
    "ぴ": "pi",
    "ぷ": "pu",
    "ぺ": "pe",
    "ぽ": "po",
    "ま": "ma",
    "み": "mi",
    "む": "mu",
    "め": "me",
    "も": "mo",
    "や": "ya",
    "ゆ": "yu",
    "よ": "yo",
    "ら": "ra",
    "り": "ri",
    "る": "ru",
    "れ": "re",
    "ろ": "ro",
    "わ": "wa",
    "ゐ": "i",
    "ゑ": "e",
    "を": "o",
    "ん": "n",
}
_MACRON = {"a": "ā", "i": "ī", "u": "ū", "e": "ē", "o": "ō"}
_KANJI = re.compile(r"[㐀-䶿一-鿿豈-﫿]")

# Keys whose `english` is a deliberate TRANSLATION rather than a romanization, so
# no reading can derive it. Kept as an explicit list because each one is an
# editorial decision, not a spelling: 葛西臨海公園 was Kasairinkaikōen and JR East
# now writes Park (author, 2026-08-01).
_TRANSLATED_NAMES = {"葛西臨海公園", "成田空港", "空港第2ビル"}


class _Unromanizable(Exception):
    pass


def _romanize_kana(kana: str) -> tuple[str, str | None]:
    """Reading -> modified Hepburn with macrons, JR East signage form.

    Returns ``(strict, loose)``. ``loose`` is non-None only when the reading
    contains a doubled bare vowel, which kana cannot disambiguate: inside a
    morpheme it is a long vowel (おおくぼ -> Ōkubo), across one it is two short
    vowels (きた+あかばね -> Kita-Akabane). The caller accepts ``loose`` only when
    the English marks that boundary with a hyphen or space.

    Raises ``_Unromanizable`` on a kanji, which is how a half-converted IME entry
    like よの本まち is caught -- the field is a reading and can hold no kanji.
    """
    # Katakana is legitimate inside a reading (くうこうだいにビル). Fold it onto
    # hiragana so one table serves both; ー is handled below.
    kana = "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in kana)

    out: list[str] = []
    i = 0
    sokuon = False
    while i < len(kana):
        two = kana[i : i + 2]
        if two in _KANA_2:
            syl, step = _KANA_2[two], 2
        elif kana[i] == "っ":
            sokuon = True
            i += 1
            continue
        elif kana[i] == "ー":
            if out and out[-1][-1] in _MACRON:
                out[-1] = out[-1][:-1] + _MACRON[out[-1][-1]]
            i += 1
            continue
        elif kana[i] in _KANA_1:
            syl, step = _KANA_1[kana[i]], 1
        else:
            raise _Unromanizable(kana[i])
        if sokuon:
            syl = ("t" if syl.startswith("ch") else syl[0]) + syl
            sokuon = False
        out.append(syl)
        i += step

    merged: list[str] = []
    ambiguous = False
    for syl in out:
        if merged and merged[-1][-1] in _MACRON:
            prev, tail = merged[-1], merged[-1][-1]
            if syl == "u" and tail in ("o", "u"):
                merged[-1] = prev[:-1] + _MACRON[tail]
                continue
            if syl == tail and tail in ("a", "o", "e"):
                merged[-1] = prev[:-1] + _MACRON[tail]
                ambiguous = True
                continue
        merged.append(syl)

    # ん assimilates to m before a labial. JR East signage does this everywhere --
    # Shimbashi, Shimmachi, Shim-Misato, Yono-Hommachi, Jimbohara -- so it is a
    # rule here rather than a list of exceptions.
    strict = re.sub(r"n(?=[bmp])", "m", "".join(merged))
    return strict, (re.sub(r"n(?=[bmp])", "m", "".join(out)) if ambiguous else None)


def _romaji_skeleton(s: str) -> str:
    """Strip editorial decoration so only the romanization itself is compared.

    Hyphenation is deliberately NOT checked: whether a name takes a hyphen depends
    on it being a prefix (Kita-Akabane) versus one place name (Sashiōgi), which no
    reading encodes.
    """
    for ch in "-‐‑ '’.\n":
        s = s.replace(ch, "")
    return s.lower()


def check_station_translations(translations: dict, issues: list) -> None:
    """data/translations.json: `furigana` is a reading, and `english` derives from it.

    Guards a class `check_route` cannot see, because both fields can be individually
    well-formed and still wrong. Found 24 defects on its first run from a report of
    one (2026-08-01): a furigana holding a kanji (`よの本まち`, an IME half-conversion
    that renders kanji in the one mode that exists to remove it), 18 English names
    missing a macron, 3 carrying one the reading does not support, and 2 wrong kana.

    DATA_FORMAT.md § "Things the validator can't catch" listed Hepburn correctness
    as by-eye; this is that gap closed.
    """
    rel = "data/translations.json"
    for key, entry in translations.items():
        if not isinstance(entry, dict):
            continue
        eng, fur = entry.get("english"), entry.get("furigana")
        if fur is None:
            continue
        try:
            strict, loose = _romanize_kana(fur)
        except _Unromanizable as exc:
            issues.append((rel, f"'{key}': furigana {fur!r} contains kanji {str(exc)!r} — must be a reading"))
            continue
        if not eng or key in _TRANSLATED_NAMES:
            continue
        accepted = {_romaji_skeleton(strict)}
        if loose and any(sep in eng for sep in "- "):
            accepted.add(_romaji_skeleton(loose))
        if _romaji_skeleton(eng) not in accepted:
            issues.append((rel, f"'{key}': english {eng!r} does not match furigana {fur!r} (expected {strict!r})"))


def check_route_readings(route_path: Path, translations: dict, issues: list) -> None:
    """Every station a shipped route draws needs a reading, not just an English name.

    `route_loader._merge_station_translations` fills what it finds and silently
    skips what it does not, so a station with `english` but no `furigana` renders
    as kanji in furigana mode with no error anywhere. 11 Yokosuka-line stations in
    sobu/1217F's pre_stops sat that way until 2026-08-01.
    """
    rel = route_path.parent.relative_to(AUDIO_ROOT).as_posix()
    if is_fixture(rel):
        return
    data = load(route_path)
    for arr in ("pre_stops", "stops"):
        for stop in data.get(arr, []):
            name = stop.get("name", "")
            entry = translations.get(name)
            if not name or entry is None or "furigana" in stop:
                continue
            if "furigana" not in entry:
                issues.append((rel, f"{arr} '{name}': no furigana in translations.json — renders as kanji in furigana mode"))


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

    # audio_root shape — checked for EVERY route including fixtures, because a wrong value
    # surfaces only as N separate "pa/X.mp3 missing" lines, which names the wrong cause.
    # conventions.md § Tooling: a data-field addition updates this validator in the same change.
    from route_loader import resolve_audio_root

    raw_root = data.get("audio_root")
    shown = repr(raw_root) if raw_root is not None else "(absent → the per-line pool)"
    if raw_root is not None and not isinstance(raw_root, str):
        issues.append((rel, f"audio_root must be a string, got {type(raw_root).__name__}"))
    else:
        # Check the RESOLVED root whether or not the key is authored: absent now MEANS the
        # pool, so the 14 shipped routes (which no longer carry it) still get shape-checked.
        resolved = resolve_audio_root(route_path.parent, data)
        if not _is_within(resolved, AUDIO_ROOT.resolve()):
            # Path containment, NOT a string prefix: "../../../audio_src/<line>" startswith
            # ".../audio" and would have passed, resolving into this workflow's own gitignored
            # working tree — clean on the authoring machine, no audio in the shipped zip.
            issues.append((rel, f"audio_root {shown} escapes audio/ (resolves to {resolved})"))
        elif not resolved.is_dir():
            issues.append((rel, f"audio_root {shown} is not a directory ({resolved})"))
        elif not fixture and not (resolved / "pa").is_dir() and not (resolved / "sta").is_dir():
            # Fixtures are exempt: _mock/main ships no audio at all (preview uses _SilentAudio).
            issues.append((rel, f"audio_root {shown} holds neither pa/ nor sta/ ({resolved})"))

    # Audio file references (cross-ref)
    if not fixture:
        # Resolve through the same single-root helper the runtime uses, so a
        # shared-pool route validates against the pool it will actually read.
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


def check_pool_sta_cut_sync(route_paths: list, issues: list) -> None:
    """One mp3 carries ONE sta_cut, wherever it is referenced.

    That is the shared pool's defining invariant, and it has already failed twice: a
    `break` in verify_sta_listen's writer half-patched a slug referenced at two stops in
    one route.json, leaving nambu's 矢川/西国立 melody at two different cuts. Until now the
    only enforcement was a stderr warning inside the by-ear GUI, which fires only while a
    human happens to be running it — never on the shipped-data gate.

    Scope is the resolved AUDIO ROOT, not the folder tree — ask resolve_audio_root rather
    than restating the pooling assumption here. Two diagrams that each keep audio beside
    their own route.json have separate sta/ dirs, so one slug is two different files and
    grouping them by line name would invent a desync that does not exist.
    """
    from route_loader import resolve_audio_root

    by_line: dict[str, dict[str, dict[float, list[str]]]] = {}
    for rp in route_paths:
        try:
            data = load(rp)
        except Exception:
            continue  # malformed route.json is already reported by check_route
        line = str(resolve_audio_root(rp.parent, data))
        for stop in data.get("stops") or []:
            cut = stop.get("sta_cut")
            for slug in stop.get("sta") or []:
                where = f"{rp.parent.name}:{stop.get('name')}"
                by_line.setdefault(line, {}).setdefault(slug, {}).setdefault(cut, []).append(where)
    for line, slugs in sorted(by_line.items()):
        label = Path(line).name
        for slug, cuts in sorted(slugs.items()):
            if len(cuts) > 1:
                detail = "; ".join(f"{c} at {', '.join(w)}" for c, w in sorted(cuts.items(), key=lambda kv: str(kv[0])))
                issues.append((label, f"sta/{slug}.mp3 has {len(cuts)} different sta_cut values — one file, one cut: {detail}"))


def check_sta_last_is_melody(route_paths: list, issues: list) -> None:
    """A multi-entry `sta` list needs a `sta_cut` that lands inside its LAST file.

    The list became positionally significant on 2026-08-11: the last entry is the
    departure melody and loops `[0, sta_cut)` until cut, while every earlier entry plays
    through once with `sta_cut` ignored. So one stop's single cut describes exactly one
    file — the last. See DATA_FORMAT.md § `sta` Array.

    WHAT THIS CANNOT CATCH: whether the last entry really IS the melody. Reversing Saikyo
    大宮's two entries leaves the cut inside the new last file too (both run 12–14 s), so
    this check passes on the exact mis-ordering that motivated it — measured, not assumed.
    Deciding which file is a melody and which is an announcement needs content analysis,
    and every derived instrument tried on that question here has returned a confident
    wrong answer (`critical_lessons.md` §11). It stays a by-ear property.

    What it DOES catch: a multi-entry stop with no `sta_cut` at all, and a cut that falls
    outside its last file — a live risk now, because a cut authored against an earlier
    entry can sit past the end of a shorter last one.
    """
    from route_loader import resolve_audio_root

    for rp in route_paths:
        try:
            data = load(rp)
        except Exception:
            continue  # malformed route.json is already reported by check_route
        sta_dir = Path(resolve_audio_root(rp.parent, data)) / "sta"
        for stop in data.get("stops") or []:
            entries = [s for s in (stop.get("sta") or []) if s]
            if len(entries) < 2:
                continue
            where = f"{rp.parent.name}:{stop.get('name')}"
            cut = stop.get("sta_cut")
            if cut is None:
                issues.append(
                    (where, f"{len(entries)} sta entries but no sta_cut — the last entry ({entries[-1]}) is the looping melody and needs one")
                )
                continue
            last = sta_dir / f"{entries[-1]}.mp3"
            if not last.exists():
                continue  # missing-file is already reported by check_route
            try:
                import soundfile as sf

                dur = sf.info(str(last)).duration
            except Exception:
                continue
            if not 0 < float(cut) < dur:
                issues.append(
                    (
                        where,
                        f"sta_cut {cut} is outside the LAST sta file {entries[-1]}.mp3 (0–{dur:.2f}s) — the cut belongs to the melody, which must be last",
                    )
                )


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
        check_station_translations(translations, issues)
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
        check_route_readings(route_path, translations, issues)
        check_route_transfer_view(route_path, stations, issues)

    # Same shipped-data scope as the loop above: `_*` routes are fixtures, not shipped, so
    # they must not be able to fail the release gate.
    scan = [route_arg] if route_arg else [p for p in route_paths if not is_fixture(p.parent.relative_to(AUDIO_ROOT).as_posix())]
    check_pool_sta_cut_sync(scan, issues)
    check_sta_last_is_melody(scan, issues)

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
