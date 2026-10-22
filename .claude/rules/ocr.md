---
paths:
  - "auto_input/**"
  - "ocr_templates/**"
  - "_dev_scripts/ocr_*.py"
  - "_dev_scripts/extract_ocr_assets.py"
  - "_dev_scripts/_badge_*.py"
  - "_dev_scripts/test_dxcam.py"
  - "_tests/**/test_ocr_*.py"
  - "_tests/**/test_auto_driver.py"
  - "_tests/fixtures/ocr/**"
---

# OCR and auto-drive rules

Path-scoped: Claude Code loads this file when a file matching `paths:` is read or edited, not at session start. These rules moved here from `conventions.md`, `principles.md` and `critical_lessons.md` on 2026-10-22, to keep the always-loaded corpus under the combined-size limit. Same rules, narrower trigger.

## Conventions

### Tooling

- **`np.astype(uint8)` TRUNCATES — always `np.rint()` first when converting computed pixels back.** Any resample / blend / filter that works in float and casts back biases every pixel down by up to 1 LSB: a uniform field of 137 came back as 136 from an exact area-average whose arithmetic was provably correct. Invisible to a shape check, a fixture pass, and to eyeballing the image. It matters here because the OCR binarizes with an Otsu threshold, and one level of systematic darkening is the margin that threshold works in (§ 7 below). 2026-07-26, `sampling._resize_area`; caught only by asserting a uniform input survives a round-trip — a cheap invariant worth keeping on any pixel-math helper.

### Domain vocabulary bindings

Some domain docs (`auto_input/README.md`, `docs/DISPLAY.md`) define canonical names and notation for non-obvious concepts. Use the canonical forms in any discussion, design doc or code edit about those domains, including when you are not editing the doc itself. The doc holds the content. This section holds the binding rule, which fires whether or not claude opened the doc.

- **AutoDriver, OCR and state-machine vocabulary is canonical in [auto_input/README.md](../../auto_input/README.md) § "State machine layering" and § "Vocabulary discipline".** Read it before reasoning about layer state. Use its Layer 1/2/3 names and arrow notation in any autodriver or OCR chat, review, code edit or commit. Don't redesign the state machine without an explicit "I want to change this."
- **The layer names are deliberately not restated here.** This binding enumerated them once and the copy drifted: it mislabelled badge reads as "Layer 2" when they are Layer 3 *inputs*, and readers were misled for months. (2026-07-16.)
- **A preloaded binding points; it never copies.** A duplicated definition is a drift waiting to happen, and when the two disagree the preloaded copy is the one that wins.

## Principles

#### Don't justify a change by demoting an input the architecture trusts
When a system ranks its inputs (this one: badge > distance/speed), an argument of the form "this branch only fires when the trusted input is wrong" is circular — it borrows the reliability of A to gate B, then denies it to win the argument. Argue from the invariant instead; a correct rule holds whatever the trusted input is doing.

**Why:** the circular version sounds like evidence and quietly inverts the trust model. Examples:
- (2026-08-11) I justified removing a `MOVING→PASSING` guard exemption as "that branch only fires on badge misreads." User: *"we've already agreed badge is the most stable read; when you use badge to enhance the logic of a less accurate read, you can't back assume badge itself is unreliable, otherwise you are trapped in this loop."* The same conclusion follows without the circularity — the exemption exists to absorb a change of the distance TARGET, and that transition has no target change to absorb.

**How to apply:** state the rule so it stands on the invariant, not on a reliability claim about a specific read. If the justification needs the trusted input to be unreliable, you have the wrong justification, not necessarily the wrong change.

#### A "bonus" feature that writes the sovereign state is not a bonus
When a secondary path shares the same state and gates as the primary — not just reads them, writes them — it cannot be reasoned about as an isolated add-on, because every rule added to make it smarter becomes a new way to corrupt the primary. The signal is a run of regressions where fixing the secondary keeps breaking the base.
- Ask whether the primary can stand entirely on its own with the secondary removed. If not they are one feature: design the primary sovereign FIRST, then make the secondary structurally incapable of touching it (a flag defaulting off, a separate signal the primary can ignore), never merely "careful". On a run of "fixed X, broke Y in the base", isolate or cut the secondary rather than adding the next rule. When the user calls it a bonus, honour that literally — the base must pass with it disabled.
- (2026-07-24) Auto-driver re-entry was framed as "a bonus re-aligning feature" but silently advances Layer 1 through the same fire gates the normal drive owns. In one session its edits caused a stranded-at-1A bug (re-anchor set `at_station_observed=True` while a sibling change removed the edge that reset it) and a lost-departure bug (a provenance gate disarmed the fallback on a case the primary's speed ceiling then dropped). Each was locally correct and broke the base: *"re-entry was supposed to be a bonus … however it is breaking the normal drive multiple times now."*

## Critical lessons

### 7. Dev-quality capture masks input-degradation bugs (2026-07-20)

The 1080p speed OCR dropped the decimal on ~40% of a user's frames (19.1 → "191"), yet was invisible on every dev machine: 0 slips on crisp local calibration + a 0/69 live drive. Root: on a *softened* capture (H.264 compression, or a hair less contrast) the decimal dot binarizes to a SINGLE dark column, and `finalize()` can't form a bbox from one column, so the decimal-stop missed it; dev captures render the dot at 2 solid columns → detected. The margin between works/fails is one pixel of darkness. I nearly abandoned the (real) fix, conceding "the reader is stable," on can't-reproduce-locally + the crisp sample — until running the production OCR over the user's screen-recording reproduced it.

**Rule:** for any read from captured / rendered input (OCR, vision, screen-scrape), the dev machine's capture is CLEANER than a real user's (compression, GPU scaling, contrast, DPI). "It reads fine here" — plus a small crisp local sample — is NOT evidence the bug is absent. Same root as lessons 3–6: reasoning from the developer's environment, not the user's.

**Pattern:**
- Reproduce against the USER's captured artifact — run the production pipeline over their recording / uploaded frame; don't trust a fresh local capture to represent theirs.
- The stable target is the DEGRADED case. For this project that is **1080p at real capture quality** — the multi-resolution path downscales all inputs to 1080p, so 1080p is canonical and must be absolutely stable (`auto_input/README.md` § "Resolution handling"), NOT the crisp dev frame or the higher-native 1440p.
- A detector resting on a feature at the binarization floor (one-pixel margin) is a bug even when it passes on dev — widen the tolerance.

**Scope:** all OCR / vision reads; anything whose correctness depends on input pixel fidelity.

### 8. Dev GPU topology masks capture-availability bugs (2026-07-23)

A user's `AutoDriver` thread crashed on `dxcam.create()` with `DXGI_ERROR_UNSUPPORTED`
(0x887A0004) from `IDXGIOutput1::DuplicateOutput`. Invisible on the dev machine, which has a
discrete GPU that owns the display and is dxcam's `device_idx=0` — Desktop Duplication against
an adapter's own output always succeeds there. The bug lives in the *topology*: on a Microsoft
Hybrid (Optimus) system the captured display can be owned by a different adapter than device 0,
and DDA against the discrete GPU on a hybrid system is unsupported by design. `dxcam.create()`
defaulting to `device_idx=0` was a deployment-frame assumption, exactly like the `_MEIPASS`
path (§4) and the crisp-capture assumption (§7) — reasoning from the developer's single-GPU box,
not the user's.

Two failures compounded: the assumption itself, and that the resulting `COMError` was
**unhandled** — it killed the whole thread with a raw traceback instead of degrading, because
the guard only covered `create()` *returning* None, not *raising*.

**Rule:** any capture / GPU / display-topology assumption (`device_idx=0`, "the primary output",
"one adapter", a single capture backend) is invisible on a dev box whose topology happens to make
it hold. Enumerate the real hardware set and pick the combo that works; never trust index 0.

**Corollary (2026-07-26) — check the restriction's SCOPE before assuming enumeration covers it.**
Walking a per-call parameter cannot fix a constraint scoped to the PROCESS. DDA's hybrid rule is
about which GPU the calling process runs on, so when Windows launches the app on the dGPU every
combo the walk tries raises `UNSUPPORTED` and it exhausts. The reporter fixed it by setting the
app's Windows GPU preference to power saving — no adapter, monitor or cable changed. The fix
above is still correct; it just addresses the other half.

**Pattern:**
- Screen/GPU capture: enumerate adapters × outputs (`dxcam.output_info()`), try each until one
  succeeds — don't hardcode device 0. `auto_input/driver.py::_open_capture_camera`.
- Wrap the init in try/except so a topology mismatch degrades gracefully — but **print the full
  original traceback**; muting it blinds the next report (user: *"if you mute the trace we cannot
  debug such problem next time"*).
- Residual (no working combo — the process is on the dGPU, or the display's only owner is): the
  levers are the per-app GPU preference (`HKCU\Software\Microsoft\DirectX\UserGpuPreferences`) or a
  different backend (`winrt` / Windows.Graphics.Capture); note it, don't pretend enumeration covers it.
- A graceful-degradation path that re-prints the original traceback reads IDENTICALLY to the crash
  it replaced, so "same error" in a user report distinguishes nothing. Keep the trace, and give the
  degraded path a distinct leading line to ask the reporter to quote.

**Scope:** dxcam / DXGI Desktop Duplication, any GPU-adapter or monitor-topology-dependent code.
