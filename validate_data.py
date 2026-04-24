"""Validate route.json files against DATA_FORMAT.md spec.

Usage: PYTHONUTF8=1 python validate_data.py [--quiet]
Exits 0 if clean, 1 if issues found.
"""
import json
import re
import sys
from pathlib import Path

SUFFIX_RE = re.compile(r"_[A-Z]{2,}$")
AUDIO_ROOT = Path("audio")
DATA_ROOT = Path("data")


def load(path) -> dict:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    quiet = "--quiet" in sys.argv
    translations = load(DATA_ROOT / "translations.json")
    train_types = load(DATA_ROOT / "train_types.json")
    stations = load(DATA_ROOT / "stations.json")

    if not quiet:
        print(f"translations.json: {len(translations)} entries")
        print(f"train_types.json:  {len(train_types)} entries")
        print(f"stations.json:     {len(stations)} entries")
        n_code_3 = sum(1 for v in stations.values() if "code_3" in v)
        print(f"stations.json code_3 count: {n_code_3} (spec: 22)")
        if n_code_3 != 22:
            print(f"  WARNING: code_3 count drifted from documented 22")

    issues = []
    for route_path in sorted(AUDIO_ROOT.rglob("route.json")):
        rel = route_path.parent.relative_to(AUDIO_ROOT).as_posix()
        try:
            data = load(route_path)
        except json.JSONDecodeError as e:
            issues.append((rel, f"JSON parse error: {e}"))
            continue

        # Route-level
        route_type = data.get("type", "")
        if route_type and route_type not in train_types:
            issues.append((rel, f'type "{route_type}": no train_types.json entry'))

        dest = data.get("dest", "")
        if dest and dest not in translations:
            issues.append((rel, f'dest "{dest}": no translations.json entry'))

        stops = data.get("stops", [])
        for i, stop in enumerate(stops):
            name = stop.get("name", "?")
            is_first = i == 0
            is_passing = stop.get("pa") == [] and not is_first

            # sta_code presence (value or null)
            if "sta_code" not in stop:
                issues.append((rel, f"[{i}] {name}: missing sta_code key"))
            else:
                sc = stop["sta_code"]
                if isinstance(sc, str) and SUFFIX_RE.search(sc):
                    issues.append((rel, f'[{i}] {name}: sta_code "{sc}" has suffix'))

            # Translation
            if name and name not in translations:
                issues.append((rel, f"[{i}] {name}: no translations.json entry"))

            # Stop-level dest override
            stop_dest = stop.get("dest")
            if stop_dest and stop_dest not in translations:
                issues.append((rel, f'[{i}] {name}: dest "{stop_dest}" no translation'))

            # Passing station must not have sta/time/sta_cut
            if is_passing:
                if "sta" in stop:
                    issues.append((rel, f"[{i}] {name}: passing has sta (forbidden)"))
                if "time" in stop:
                    issues.append((rel, f"[{i}] {name}: passing has time (forbidden)"))
                if "sta_cut" in stop:
                    issues.append((rel, f"[{i}] {name}: passing has sta_cut (forbidden)"))

            # First station should have time: 0
            if is_first and stop.get("time") != 0:
                issues.append((rel, f"[{i}] {name}: first station time={stop.get('time')!r} (expected 0)"))

        # Audio file references
        audio_dir = route_path.parent
        pa_dir = audio_dir / "pa"
        sta_dir = audio_dir / "sta"
        for i, stop in enumerate(stops):
            for track in stop.get("pa") or []:
                if track and not (pa_dir / f"{track}.mp3").exists():
                    issues.append((rel, f"[{i}] {stop.get('name')}: pa/{track}.mp3 missing"))
            for track in stop.get("sta") or []:
                if track and not (sta_dir / f"{track}.mp3").exists():
                    issues.append((rel, f"[{i}] {stop.get('name')}: sta/{track}.mp3 missing"))

    if not issues:
        if not quiet:
            print("\nAll routes clean.")
        return 0

    # Group by route
    by_route = {}
    for rel, msg in issues:
        by_route.setdefault(rel, []).append(msg)
    print(f"\n{len(issues)} issues across {len(by_route)} routes:")
    for rel in sorted(by_route):
        print(f"\n{rel}")
        for msg in by_route[rel]:
            print(f"  - {msg}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
