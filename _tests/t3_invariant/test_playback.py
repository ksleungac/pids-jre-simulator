# SPDX-License-Identifier: MIT
# TIER: T3 — the STA head/tail split serves the halves it claims
"""Locks `audio.AudioPlayer._load_and_play_sta`'s split against a real corpus file (#141).

The last sta track at a stop is cut at `sta_cut` into a head that loops and a tail
that plays once, and BOTH are built up front from one decode so the conductor's cut
lands on the keystroke.

The head and the tail are ONE operation. The file is written once, decoded once, and
`split_raw_at` cuts that Sound's own buffer in memory, so the tail cannot fail for
any reason the head did not already fail for. That is the architectural guarantee
this module exists to hold: `channel.play` is the last statement in the try, so under
the earlier build-then-build-then-play shape anything raising while making the tail
silenced a head that was already playable, and silence is what "the departure melody
is missing" looks like (#142). The earlier shape also rested on `Sound()` copying at
construction — measured true on pygame 2.6.1 / SDL 2.28.4 (#141), but a platform
assumption the app had no reason to be taking. One write cannot alias itself.

THE ORACLE IS PRODUCTION'S OWN NO-SPLIT BRANCH, not a restatement of the split.
`loop=False` writes the file once and builds one Sound, so it cannot be aliased by a
later write. Its buffer is the reference:

    head.get_raw() + tail.get_raw() == whole.get_raw()      (byte for byte)

That holds because production slices AFTER normalising, so the two halves are a
partition of exactly the bytes the unsplit branch produces. Nothing here re-derives
the loudness gain, the cut sample or the slice.

The lengths are checked separately, and the two checks are complementary rather than
redundant: concatenation pins the CONTENT (a head carrying tail bytes fails it), the
lengths pin WHERE the cut landed (a split at the wrong sample still concatenates).

Two further checks guard what the in-memory split newly risks. The write COUNT, which
is the guarantee itself — one press must cause exactly one `sf.write`, so a future
refactor that serves the tail from a second write reintroduces the failure and this
says so. And FRAME ALIGNMENT, because a byte offset that is not a whole number of
frames swaps the channels for the rest of the track while every length stays right.

Discriminates: slice the head as `normalized[cut_sample:]`, cut at a non-frame
boundary, or split with a second `sf.write`, and this fails. Verified by mutation on
2026-09-08 — the misaligned cut and the reintroduced second write each turn it red.

Byte equality needs the mixer to do no resampling, so the mixer is opened AT the rate
the corpus is in, derived from the files rather than pinned. pygame's default is
44100 and this corpus is 48000, so a pinned rate silently compared resampled buffers;
the fixtures are also required to agree with each other, since one mixer serves both.
"""

import json
import os
import sys
from pathlib import Path

# No display is needed and no sound card should be: the test reads Sound BUFFERS and
# the armed flags, never `Channel.get_busy()`, so a dummy device is enough and keeps
# the result independent of the machine's audio hardware.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pygame.mixer as mixer  # noqa: E402
import soundfile as sf  # noqa: E402

import audio as audio_mod  # noqa: E402
from app_paths import project_root  # noqa: E402
from audio import AudioPlayer  # noqa: E402
from route_loader import resolve_audio_root  # noqa: E402

# The line and stops named in the report behind #141. Two stations, not one, so a
# hardcoded-length bug cannot pass by coincidence — their cuts differ (7.9 / 10.6).
WORK_DIR = project_root() / "audio" / "chuo" / "1654T"
STATIONS = ("八王子", "西八王子")


def fixtures(stops, audio_root):
    """Resolve each station to (index, stop, track, sta_cut, duration, rate).

    Anything unresolvable is returned as an error string rather than skipped, so a
    fixture that moves fails the test instead of quietly shrinking its scope.
    """
    out, errs = [], []
    for name in STATIONS:
        idx = next((i for i, s in enumerate(stops) if s["name"] == name), None)
        if idx is None:
            errs.append(f"  {name} is not in {WORK_DIR.name}/route.json — fixture moved, test is testing nothing")
            continue
        stop = stops[idx]
        cut = stop.get("sta_cut", 0)
        if not stop.get("sta") or not cut:
            errs.append(f"  {name} has no usable sta/sta_cut — fixture changed, test is testing nothing")
            continue
        track = Path(audio_root) / "sta" / f"{stop['sta'][-1]}.mp3"
        if not track.exists():
            errs.append(f"  {name}: {track} is missing")
            continue
        info = sf.info(str(track))
        out.append((idx, stop, track, cut, info.frames / info.samplerate, info.samplerate))
    return out, errs


def main() -> int:
    failures: list[str] = []

    def check(cond, msg):
        if not cond:
            failures.append("  " + msg)

    route = json.loads((WORK_DIR / "route.json").read_text(encoding="utf-8"))
    stops = route["stops"]
    audio_root = str(resolve_audio_root(WORK_DIR, route))

    fx, errs = fixtures(stops, audio_root)
    failures.extend(errs)

    rates = {f[5] for f in fx}
    if len(rates) > 1:
        failures.append(f"  fixtures disagree on sample rate {sorted(rates)} — one mixer cannot serve both without resampling")
        fx = []

    if not fx:
        print(f"FAIL: STA head/tail split (#141) — 0/{len(STATIONS)} stations checked")
        print("\n".join(failures))
        return 1

    # Open the mixer AT the corpus rate so no resampling stands between the written
    # samples and the buffers compared below.
    mixer.init(frequency=rates.pop(), size=-16, channels=2)
    player = AudioPlayer(audio_root, stops)

    checked = 0
    for idx, stop, track, cut, dur, _rate in fx:
        name = stop["name"]
        # Reference arm: the unsplit branch. One write, one Sound, no later overwrite.
        player.play_sta(idx, len(stop["sta"]) - 1, cut_position=0, loop=False)
        whole = player._sta_sound
        check(whole is not None, f"{name}: loop=False armed no Sound")
        check(player._sta_tail_sound is None, f"{name}: loop=False must arm no tail, got one")
        check(not player._sta_looping, f"{name}: loop=False must not arm the loop")
        if whole is None:
            continue
        whole_raw = whole.get_raw()

        # Split arm: the head loops, the tail is parked for the cut.
        player.play_sta(idx, len(stop["sta"]) - 1, cut_position=cut, loop=True)
        head, tail = player._sta_sound, player._sta_tail_sound
        check(head is not None and tail is not None, f"{name}: loop=True must arm BOTH head and tail, got {head} / {tail}")
        check(player._sta_looping, f"{name}: loop=True must arm the loop flag that gates the cut")
        if head is None or tail is None:
            continue

        # WHERE the cut landed. Tolerance is far inside the gap between the two
        # expected lengths, so a head serving tail bytes cannot pass it.
        gh, gt = head.get_length(), tail.get_length()
        check(abs(gh - cut) < 0.05, f"{name}: head must run to sta_cut {cut}s, got {gh:.2f}s")
        check(abs(gt - (dur - cut)) < 0.05, f"{name}: tail must run {dur - cut:.2f}s, got {gt:.2f}s")

        # WHAT the two halves contain. Byte-exact against the unsplit branch.
        head_raw, tail_raw = head.get_raw(), tail.get_raw()
        check(
            head_raw == whole_raw[: len(head_raw)],
            f"{name}: head bytes are not the file's first {gh:.2f}s — the head is serving something else",
        )
        check(
            tail_raw == whole_raw[len(head_raw) :],
            f"{name}: tail bytes are not the file's remainder after sta_cut",
        )
        check(
            head_raw + tail_raw == whole_raw,
            f"{name}: head+tail must reconstitute the unsplit file exactly",
        )

        # Frame alignment, asked of `split_raw_at` DIRECTLY rather than of the Sounds
        # it feeds. `Sound(buffer=)` truncates a misaligned buffer to the frame
        # boundary, so the constructed head always measures aligned and a check on it
        # reads pygame's normalisation instead of our arithmetic — inert, and verified
        # inert by mutation. The offset is what can be wrong: one byte out swaps the
        # channels for the whole remainder.
        freq, size, channels = mixer.get_init()
        frame = channels * (abs(size) // 8)
        h, t = audio_mod.split_raw_at(whole, cut)
        check(len(h) % frame == 0, f"{name}: split_raw_at head is {len(h)} bytes, not whole {frame}-byte frames")
        check(len(t) % frame == 0, f"{name}: split_raw_at tail is {len(t)} bytes, not whole {frame}-byte frames")
        check(h + t == whole_raw, f"{name}: split_raw_at must partition the buffer, losing nothing")
        check(
            len(h) == int(cut * freq) * frame,
            f"{name}: split_raw_at cut at byte {len(h)}, expected {int(cut * freq) * frame} for {cut}s",
        )

        # THE GUARANTEE: one press, one write. The head and the tail come out of a
        # single decoded buffer, so the tail cannot fail on its own. A second write
        # here would mean the tail is independent I/O again, and a failure in it would
        # silence a head that was already playable (#142).
        writes = []
        real_write = audio_mod.sf.write

        def counting_write(*a, **kw):
            writes.append(a[0] if a else kw.get("file"))
            return real_write(*a, **kw)

        audio_mod.sf.write = counting_write
        try:
            player.play_sta(idx, len(stop["sta"]) - 1, cut_position=cut, loop=True)
        finally:
            audio_mod.sf.write = real_write
        check(
            len(writes) == 1,
            f"{name}: one press must cause exactly ONE sf.write; got {len(writes)} — the tail is separate I/O again",
        )
        check(
            player._sta_sound is not None and player._sta_tail_sound is not None,
            f"{name}: the counted press must still arm both halves",
        )
        checked += 1

        # A cut outside the file is no cut at all: whole file, once, no loop, no tail.
        # This is what keeps `is_sta_looping()` honest, and it is the branch that stops
        # a bad sta_cut looping an empty head forever.
        player.play_sta(idx, len(stop["sta"]) - 1, cut_position=dur + 5, loop=True)
        check(not player._sta_looping, f"{name}: an out-of-range sta_cut must not arm the loop")
        check(player._sta_tail_sound is None, f"{name}: an out-of-range sta_cut must arm no tail")
        check(
            player._sta_sound is not None and player._sta_sound.get_raw() == whole_raw,
            f"{name}: an out-of-range sta_cut must fall back to the whole file",
        )

    player.stop()
    mixer.quit()

    # Print N alongside the verdict: a green run over zero stations is not a pass.
    if failures or checked != len(STATIONS):
        print(f"FAIL: STA head/tail split (#141) — {checked}/{len(STATIONS)} stations checked")
        print("\n".join(failures))
        return 1
    print(f"PASS: STA head/tail split serves head+tail byte-exactly — {checked} stations, head+tail == unsplit file (#141)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
