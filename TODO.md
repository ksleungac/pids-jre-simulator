# TODO — moved to GitHub Issues

The active backlog now lives in **GitHub Issues**: https://github.com/ksleungac/pids-jre-simulator/issues

- **Browse / triage** on the Issues tab. Filter by area label: `auto-input`, `display`, `chrome-i18n`, `distribution`, `housekeeping`, `review-finding`, `build-incident`.
- **Status lives in labels:** `in-progress` (a session is actively on it), `deferred` (parked — see the issue's reason comment). Closure is authoritative: a pushed commit with `Closes #N` closes the issue.
- **Working loop:** session start (`_harness/session_init.py`) prints the open / in-progress / recently-closed / stale summary · `/commit` writes the `Closes #N` / `Refs #N` trailer · `/session-recap` reconciles against `gh issue list`.

Only the **closed-off paths** ledger stays in-repo below — it's an anti-backlog (ground we've decided NOT to walk), not work items, so it never becomes an issue.

---

## Directions — wanted, not yet scoped

Paths the author intends to walk **some day**, held here rather than as GitHub Issues: a direction has no closure event, so as a ticket it reads as owed work forever. The opposite pole of the closed-off ledger below — these are *yes, later*, not *never*.

Each entry carries its own description on purpose, so picking one up needs no re-explaining. `_harness/session_init.py` prints these headings at session start. Promoting one = scope it, open an issue, delete the entry here. Abandoning one = move it down into the closed-off ledger.

### Standalone on a phone or tablet, without the PC

Today the app mirrors its window to a browser (`--stream` / `--stream-lan`), which still needs the PC running. Running on the device *alone* is a different thing, and it stays open rather than rejected. A port was weighed and declined: it means owning two renderers, so every train model and every calibration round is paid for twice on a project whose whole value is calibration fidelity; `audio/` is ~585 MB and not bundleable into a mobile build; and OCR auto-drive is structurally PC-only, so a standalone build permanently forks the product into with-auto-drive and without. If real demand appears the path is pygbag/WASM with per-route asset download, because it reuses the renderer instead of duplicating it. The mirroring that exists instead: `docs/APP.md` § "Window mirroring". *(#1 "提案：探索移动端 / 平板电脑支持" stays OPEN — it is an outside contributor's issue, not ours to close)*

### The mirrored window becomes a real second screen

The feature itself has landed — the whole app window mirrors over HTTP, touch comes back, and 2026-08-29 gave it its in-app switch (TIMS 設定), an address row on the band with a QR to scan, and a per-viewer view control. What it is and why: `docs/APP.md` § "Window mirroring".

What is left is **speed** (the author's own next-release wish). The concrete lever is capturing the app's CANVAS rather than the zoomed window: at zoom k the stream ships k² pixels of nearest-neighbour upscale carrying no information the canvas did not, and the client then resamples it back down. It is not urgent — zoom defaults to 1× at 1080p and 1440p, so only 4K users and anyone who dragged the window bigger pay it — and it moves the tap coordinate frame, so decide the capture source before touching the tap path. The other open end is **learning the address that actually works**: the handler can read which local interface a client arrived on (`getsockname` on a `0.0.0.0` listener), so the first successful connection could pin the right address permanently instead of ranking guesses. *(was #71, #73, #76)*

### OCR that does not misread, rather than OCR that guards its misreads

Accuracy today is earned through a stack of guards layered on the reader. The target is no misreads at all, which is a fair bar for a fixed font at a fixed size in a fixed position — real-world OCR handles handwriting and photographs. Rate measured at roughly 1 misread per 960 samples before the 2026-07-22 fixes. Four approaches, all measured that day: register glyphs by centroid/moments instead of a threshold-derived bounding box, because the box's own edges move when the threshold clips a column, so the registration frame itself shifts; slice digit cells by known geometry instead of rediscovering the layout from column runs every frame, which deletes a failure class rather than guarding it; fuse several frames before reading, since the driver samples ~3 Hz from a 60 fps source and discards 19 of every 20; and separate empty-cell detection from the adaptive threshold, which sits pinned at its clamp ceiling on ~82% of bright-content frames. *(was #91 parent + #92, #93, #94, #95)*

### The HUD is found on any screen shape, not just the ones measured

Downscaling made resolution itself a non-issue — every capture shrinks into the one 1080p model, so a new size costs no templates and no calibration round. What is still derived rather than seen is *where the HUD sits*, fitted against a 16:9 viewport, so some shapes are refused instead of guessed. The two that a screenshot would settle are already scoped as [#122 "21:9 and non-multiple-of-16 widths — the two geometry cases still unmeasured"](https://github.com/ksleungac/pids-jre-simulator/issues/122); this entry is the *general* fix behind them, which is unscoped. It replaces derivation with a user-drawn box: the user aligns a 50%-opaque rect to the real HUD, the box locks to the HUD's fixed aspect so the scale axis (the one that actually breaks alignment) disappears, and the live speed / distance / badge readout confirms it by eye — with a shipped preset box auto-applied on common sizes so the common case stays zero-config. Multi-monitor and windowed play fall out of it for free, since capture would follow the selected rect's own output. Three things are unsettled: how far to take auto-proposing the box (a scaled default vs landmark-matching the badge pentagon), whether a recognised resolution applies its preset silently or shows the screen pre-filled for confirmation, and how a box is keyed and persisted. One input is stale before any of it — the alignment tolerance window (the stopping-offset cell breaks at ±3% scale, ±8 px shift, and is the canary because it holds the smallest digits) was measured before the 2026-07-2x read hardening widened it, so re-measure against the committed fixtures rather than designing to those numbers. Current behaviour and the full support table: `auto_input/README.md` § "What a profile means, and what gets interpolated".

### Auto-drive fires more of what a driver would

Three wants against the same surface. **Multi-PA stops** — `_next_pa()` plays one announcement per call, so a transfer hub with three auto-fires only the first and the user presses for the rest; either space several `pending_next_pa` flags by audio duration, or chain them. **STA auto-fire** — deliberately not modelled, because the departure melody is the station master's IRL and not the driver's; the plumbing exists if that ever changes. **Announcements anchored to distance rather than to a press** — IRL the PA is geographic, and the arrival side already works that way (`arrival_lead_m`, 900 m base), while the 次は side fires on entering APPROACHING instead. The author's proposed shape is to carry the trigger distance in the PA filename, `d1234` = fires below 1234 m, which fits `principles.md` § "Filename-as-store" and needs no schema change. Only meaningful under auto-drive; manual has no distance to anchor to. *(was #9, #12, #124)*

### Transfer info covers every station, on every model

The pipeline is built and verified against ~48 stations. Filling it out is blocked deliberately: adding stations only pays once the models that render them exist, so it waits on E233. Three parked threads — populating `stations.json` beyond the current corpus, prioritising stations served by at least one LCD-equipped line, with `transfers_by_view` entered as raw observations and never derived; declaring E233's own badge policy when that model lands, since its sub-series render some entries as colour squares rather than icons and that belongs in its own `transfer_info.py` rather than a parameterised DSL; and the English size trade-off, with the shinkansen row parked at 12 pt. *(was #20, #21, #23)*

### The 423 MB corpus gets smaller

Two levers, neither taken. Encoding runs 75–321 kbps at 48 kHz stereo and much of it is mono content in a stereo container; normalising to ~96–128 kbps mono would take the corpus down substantially again, a bigger lever than pooling was — and it is lossy and irreversible, so it wants a deliberate decision rather than a sweep. Separately, different stations often play the same melody (高尾 / 荻窪 / 西八王子 share one; ~57 MB of such duplication corpus-wide), which the per-line pool cannot collapse because each file is the melody *plus* that station's own closing announcement, so no two files are actually identical. Collapsing them means splitting the two apart and changing how STA plays. *(was #119, #120)*

### Display fidelity threads waiting on evidence

Three that cannot proceed until something external arrives. **Pale-brand line colours** — Sōbu yellow `#FFD400` and Yamanote yellow-green render at full saturation and would be hard to read as eyebrow text on a white card; a W3C relative-luminance darkening was drafted and reverted, waiting on a drive recording that shows the problem for real. **Passing stations in the 5-station view** — drawn as an empty countdown ring, a degenerate reuse of a calibrated primitive; the proper native chevron needs calibration that does not exist. **Terminus fidelity** — the 8-station lock and the E235-0 ahead-walks measure to `len(stops)` rather than `dest_stop_idx`, which only shows on a route whose data runs past its operational terminus; blocked on a Sōbu reference photo of what the real display does there. **The E235-0 5-station view's own finetune sits here too** — marker sizes, positions and sweep timing, plus a re-probe of Yamanote's `contrast_color` (currently `[101,20,5]`, taken off a maxresdefault frame where JPEG clips saturated red; it wants a cleaner reference shot). *(was #2, #14, #99, #103)*

### The repo's front page leads with the README, not with a wall of files

GitHub always draws the root file list before the README, there is no setting, and the [collapse-button request](https://github.com/orgs/community/discussions/109986) was never built — so the only lever is how many entries sit at the top level. 42 today, and **18 of them are root `.py` files**, which is why the 2026-08-19 tidy (docs into `docs/`, reference photos into `_references/`) only reached 42 from 46. Putting the code in one named folder — the 13 production modules plus `displays/`, `tims/`, `auto_input/`, root keeping a `main.py` shim — reaches ~22; anything short of that stalls around 37. Note `src/` is a *different* proposal: that name exists to stop tests importing the working copy instead of the installed one, a library-on-PyPI problem, and this ships an exe, so the folder can be called anything. Two neighbouring consolidations were measured and rejected so a later tidy does not re-derive them: one `_dev/` for the four `_*` dirs (126 pointer sites to remove 3 rows) and merging the runtime asset dirs (touches the path resolution that has caused four release crashes). Gets `/third-man` before any file moves. Numbers and reasoning: `memory/2026-08-19.md`.

---

## Closed-off paths (don't re-propose)

Recording the ground we've explicitly decided NOT to walk, so future sessions don't re-litigate:

- **Memory hooking the game's `*saf.dll` modules.** Tried, dead end.
- **Decrypting SimDATA assets.** Encrypted; not pursuing.
- **Audio fingerprinting** for stop detection. Replaced by HUD OCR which works.
- **Full-desktop OCR** instead of window-bound capture. Privacy + perf concerns.
- **Tesseract-based OCR.** Too heavy; pixel-perfect template match works.
- **Mac build.** The companion game (JR EAST Train Sim Real) is Windows-only — no Mac audience exists for this app. Not worth the porting cost.
- ~~**Scaling to lines the game already covers**~~ — **rescoped 2026-08-15, no longer closed off.** Gaps-first is a *priority* rule, not a permission rule: a post-cutoff route the game already voices is still worth building when wanted, and the gap list is nearly exhausted. What stays closed is duplicating a route's PA *in order to compete with the game's own recordings* — that contest is unwinnable against the operator's source audio and was never the point. See [COVERAGE.md](docs/COVERAGE.md).
- **In-car advertising / news / weather screen.** IRL the pair of screens above a door splits duties — one runs service info, the other ads. Only the service screen is modelled, deliberately: the ad content is out of scope. Author-stated 2026-08-18.
- **OCR-as-display-layer fidelity-purity argument.** OCR is an *input layer* (replaces PageDown press), not display. Don't recycle.
