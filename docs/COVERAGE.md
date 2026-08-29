# Coverage — the game's routes vs ours

What JR EAST Train Simulator ships, what this app covers, and therefore what is left to build.
This is the input to "what do we support next"; it is not a backlog (that's GitHub Issues).

**Scope: JR lines in the Tokyo capital region only.** Non-JR packs (Tobu, Seibu) and out-of-region
lines (Ōito, Shin'etsu, Koumi, Senzan, Hachinohe, Rumoi, Oga, Senseki) are out of scope and are not
tracked here. Rolling-stock-only packs (185, E231, 209-500) add trains, not routes.

## Start here — what to pick up

**Route data / audio → which line?**

1. **Utsunomiya**, `3520M` first (快速ラビット, the only full-section diagram). Last pre-cutoff gap.
   Pure audio — E233-3000 has no LCD, so it brings no display work and competes with nothing.
2. Then the remaining gap set: **Nambu Branch + Tsurumi** (7 diagrams, pack already owned, but wants
   a 205 model first) and **Takasaki 831M**. *(Chūō 602H — 通勤特快 — shipped 2026-08-29.)*
3. Post-cutoff routes are by choice, not gap-filling — and want the phase model first if a full PA
   corpus isn't affordable.

**Feature / display → which model?**

1. **E233-0.** Best single item in the project: fixes chuo's two diagrams (existing users), unlocks
   **Ōme** (a new route, same model, free), and gives tokaido + takasaki a defensible *fictional*
   render. Pays the family architecture the rest inherit.
2. Then the skins: **E233-1000** (keihin) · **-5000** (keiyo) · **-7000** (saikyo) · **-8000** (nambu).
3. Beyond the catalogue: **E233-6000** (Yokohama Line) · **E231-500** (Chūō・Sōbu Local).
4. **Never:** E233-3000, E531, E217 — no LCD exists IRL.

Before any model, **#17 (calibration editor — route bar wiring + lower-view dispatch)** lowers the
cost of every one of them. It is the cheapest thing here and the only one that makes the expensive
things cheaper.

**Fictional renders are a third category, not a failure.** In-spec means matching a real PIDS;
out-of-spec means best-effort on a line the model doesn't serve IRL. A line whose stock has *no LCD
at all* is neither — there is no spec to depart from, so the only bar is plausibility. A linear
model on a linear line (E233-0 on tokaido / takasaki) needs no adaptation at all, and asking "what
would the E233-3000's LCD look like" is best answered by its nearest real relative, another E233.
That is a better-founded render than today's E235-1000 borrow, and it is the one thing the game
cannot compete on — it will only ever model what exists.

## The announcement cutoff

**Yokosuka Line (2024-10-29) is the boundary.** Route packs released from Yokosuka onward ship with
in-game passenger announcements. Everything before it shipped without them, which is the gap this
app was built to fill.

**The boundary also moves backwards over routes already shipped, and it is TRIGGERED rather than
gradual.** Two known instances:

| line | released | what was added | apparent trigger |
|---|---|---|---|
| Jōban | 2023-08-29 | driver voice + automatic broadcasting | unexplained — no Jōban pack is recorded below, though that list is a floor (§ Method) |
| **Tōkaidō Outbound** | 2022-11-14 | passenger announcements | **Tōkaidō Inbound shipped 2026-07-28** |

Tōkaidō is the instance with a visible cause: the new Inbound pack brought the line up to the
current standard and the Outbound pack came with it (author, 2026-08-29). The back catalogue is not
being worked through in release order, so **a pre-cutoff route's exposure is a function of whether a
NEW pack lands on the same line, not of how old it is**. "The game doesn't announce this route" is a
fact with a date on it, and the date to re-check is the day a neighbouring pack ships.

**Which of ours already have a trigger on the board**, strongest adjacency first. Every unchecked
row is settled by loading the route and listening:

| our line | pack that shipped afterwards | adjacency | status |
|---|---|---|---|
| **tokaido** | Tōkaidō Inbound (2026-07-28) | same line, other direction | **fired** |
| **chuo** | Ōme (2024-11-27) · Chūō・Sōbu Local (2025-12-22) | through service · same corridor | **unchecked** |
| **sobu** | Yokosuka (2024-10-29) | through service over the same track | **unchecked** |
| **takasaki** | Hachikō (2025-03-25) · Shōnan-Shinjuku (2025-09-26) | shares a terminus only | **unchecked** |
| keihin · yamanote · saikyo · keiyo · nambu | none recorded | — | no trigger yet |
| *(joban)* | none recorded | — | retro-fitted anyway |

`chuo` is the row that matters most — it is the line E233-0 is being built for, and it has had two
neighbouring packs land since release.

## Our catalog is the pre-cutoff set

Every line in `audio/` maps to a game route released before the cutoff, in release order, with no
exceptions and no arbitrary picks:

| our line | game route | released |
|---|---|---|
| keihin | base game | 2022 |
| tokaido | Tōkaidō Line Outbound (Tokyo–Atami) | 2022-11-14 → **retro-updated 2026** |
| chuo | Chūō Line Rapid Service (Takao–Tokyo) | 2022-11-14 |
| saikyo | Saikyō-Kawagoe Line (Ōsaki–Kawagoe) | 2023-02-20 |
| keiyo | Keiyō Line (Soga–Tokyo) | 2023-06-26 |
| yamanote | Yamanote Line (Ōsaki–Ōsaki) | 2023-07-24 |
| *(`_joban`, staged)* | Jōban Line (Shinagawa–Katsuta) | 2023-08-29 → **retro-updated** |
| nambu | Nambu / Nambu Branch / Tsurumi | 2023-11-27 |
| sobu | Sōbu Line Rapid (Tokyo–Narita Airport T1) | 2023-12-18 |
| takasaki | Takasaki Line (Ueno–Takasaki) | 2024-02-26 |
| **— not built —** | **Utsunomiya Line (Kuroiso–Tokyo)** | **2024-08-26** |

## Diagram-level state

A second diagram earns its place only for a **different stopping pattern** (`CLAUDE.md` § Mental
Model). Measured against that:

| line | game diagrams | ours | gap |
|---|---|---|---|
| Keiyō | 780Y, 1510Y | both | — |
| Saikyō | 759K, 1349F | both | — |
| Nambu main | 603F, 843F, 4027F | both patterns | — |
| Yamanote | 1208G, 876G | 1208G | none — 876G is the same pattern; the pack has no 外回り |
| Tōkaidō Out | 1525E, 1531E, 1865E, 1567E, 3535E | 1865E, 3535E | none — the rest are 普通 terminating short |
| Sōbu Rapid | 627F, 845F, 1217F | 1217F | none — all 快速; the others terminate short |
| **Takasaki** | 829M, 831M, 3922E, 833M | 3922E | **831M** — 普通 over the full section |
| Chūō | 602H, 692T, 916H, 1034T, 1654T | 602H, 916H, 1654T | none checkable — 692T / 1034T are label-only calls (§ Method) |
| **Nambu pack** | +Branch ×3, +Tsurumi ×4 | none | **two whole lines** |
| **Utsunomiya** | 1539E, 1567E, 1591E, 3520M, 2531Y, 4521Y | none | **whole route** |
| Keihin-Tōhoku | *unknown — base game, no DLC page* | 1275A, 727B | unverified |

## What is actually left

All three are pre-cutoff, so the game ships no announcements for any of them **as of this writing**.
That is gap-filling in the original sense, not duplication — but it is a status with a shelf life,
and the trigger for losing it is a neighbouring pack, not the passage of time (§ "The announcement
cutoff"). Re-check the specific line before starting its build.

1. **Utsunomiya** — 6 diagrams. Canonical pick is 3520M (快速ラビット, full Kuroiso→Ueno) plus a 普通.
   Note 1567E appears in both this pack and Tōkaidō Outbound — one through service over the
   Ueno-Tokyo Line, so half its route is already modelled in `tokaido`.
   **That shared diagram is now the cheapest exposure test available**: Tōkaidō Outbound has been
   retro-fitted, so if 1567E is one run rather than two copies, the Utsunomiya pack may already
   announce. Load it and listen before committing to a 6-diagram PA corpus.
2. **Nambu Branch + Tsurumi** — 7 diagrams, two lines, inside a pack already owned. Different stock
   (205-1000, 205-1100), so they need their own display treatment.
3. **Takasaki 831M** — 普通 to 高崎; only the 快速アーバン is built.

*(Chūō 602H, 通勤特快, was the fourth. Shipped 2026-08-29 — `audio/chuo/602H/`.)*

## Post-cutoff routes (in-game announcements exist)

Not gaps. Buildable by choice, not to fill an absence — see `CLAUDE.md` § Mental Model on
gaps-first being a priority rule, not a permission rule.

| route | section | released |
|---|---|---|
| Yokosuka | Kurihama–Tokyo | 2024-10-29 |
| Ōme | Tachikawa–Okutama | 2024-11-27 |
| Tōkaidō Freight | Nebukawa–Tokyo/Shinjuku | 2024-12-16 |
| Hachikō | Takasaki–Komagawa | 2025-03-25 |
| Shōnan-Shinjuku | Ōmiya–Zushi | 2025-09-26 |
| Yokohama Line | Ōfuna–Hachiōji | 2025-10-27 |
| Chūō・Sōbu Local | Chiba–Mitaka | 2025-12-22 |
| Tōkaidō Line Inbound | Atami–Tokyo | 2026-07-28 |

## Directions for future support

### Now — Utsunomiya, full route first

**3520M** (快速ラビット, Kuroiso 07:14 → Ueno) is the only diagram in the pack that runs the full
section; the other five start mid-route at Koganei or Utsunomiya. Build it first as the canonical
full-line diagram, then partials as wanted.

**1567E is half-paid already** — it is a through service over the Ueno-Tokyo Line and appears in the
Tōkaidō Outbound pack too, so its Tokyo-end stations are modelled in `tokaido`.

### Then — the rest of the gap set

Pre-cutoff, so no in-game announcements exist for any of them.

1. **Nambu Branch + Tsurumi** — 7 diagrams, two lines, in a pack already owned. Also a *display*
   gap: 205-1000 / 205-1100 stock, and no 205 model exists.
2. **Takasaki 831M** — 普通 over the full section.

### Enabler — the route phase model

Lets a route ship without a PA corpus: an **STA phase** carries departure melodies only, which
duplicates nothing (the game ships no melodies at any point on the timeline) and costs no PA cutting
— the constraint that makes new routes expensive, since a diagram is a *(pattern, destination,
formation, day type)* tuple and each variant needs its own cuts.

**Blocker:** `app.py::_advance_to_next_stop` defines a stopping station as
`bool(stop.get("pa")) or bool(stop.get("pa_at_station"))`, so a route without PA has no stops at all
and the advance runs to the terminus. Needs the stop marker separated from the audio: a schema
field, the predicate change, a `validate_data.py` rule that accepts an STA-phase route rather than
flagging it, and a phase indicator in the picker. Touches the state machine — design before patching.

A phase is a waypoint, not a verdict; PA can land later on any route, by choice rather than to fill
an absence.

### Display — per-line-native train models

`displays/train_models/` holds **e235_0** and **e235_1000** only, and just `yamanote/1208G` declares
a model. The other 14 diagrams fall to the e235_1000 default, which is in-spec only for
`sobu/1217F`. Per `CLAUDE.md` § Per-model IRL line scope, those renders are transitional and are
meant to be retired as native models land.

**Not every line has LCD work at all.** IRL only **E233 (non-3000)**, **E235** and **E231-500**
carry an LCD PIDS. A line whose stock is outside that set has no native display to build, so its
e235_1000 render is **permanent, not transitional** — the `CLAUDE.md` § Per-model IRL line scope
promise that out-of-spec renders retire "as native models land" does not reach them, because no
native model can ever exist.

| line | stock | LCD work |
|---|---|---|
| yamanote | E235-0 | built |
| sobu | E235-1000 | built |
| chuo | E233-0 | **available** |
| keihin | E233-1000 | **available** |
| keiyo | E233-5000 | **available** |
| saikyo | E233-7000 | **available** |
| nambu | E233-8000 | **available** |
| tokaido | E233-3000 | none exists |
| takasaki | E233-3000 | none exists |
| *(joban)* | E531 | none exists |

So the display roadmap is **five lines**, all E233 non-3000. **E233-0 first** — it serves chuo's two
diagrams now and Ōme later, and pays the family architecture that -1000 / -5000 / -7000 / -8000
inherit as skins. Beyond the catalogue: **E233-6000** (Yokohama Line) and **E231-500**
(Chūō・Sōbu Local) are LCD; **E217** (Yokosuka) is not.

**Utsunomiya brings no display work** — E233-3000, pure audio route. Same for Tōkaidō Inbound.

### Post-cutoff routes — by choice

The eight routes listed above. **Tōkaidō Line Inbound** is the notable one: the catalogue holds 下り
only, so it is the sole case where the game offers a direction we lack on a line we already cover.
It is also the pack that retro-fitted our 下り (§ "The announcement cutoff"), so `tokaido` is now
duplicated in both directions — building 上り would add a direction, not close a gap.

## Method, and what it cannot tell you

Compiled 2026-08-15 from the Steam store pages (aggregate DLC list + per-pack pages).

- **Stopping pattern is not the only axis.** Formation length varies too (Takasaki 829M is 10-car
  and 833M 15-car under the same 普通 label; Tōkaidō and Utsunomiya mix 10 and 15), and day type
  varies (weekday vs weekend runs under one service name). Both can change what is announced.
  Treat a diagram as the tuple *(pattern, destination, formation, day type)*, not the label alone.
- **A store page gives a service LABEL, times and section — never the stop list.** So every
  "same pattern" call above is an inference from the label, and it is unsafe wherever day type or
  origin differs. Known-unsafe calls: Chūō **1034T** (weekend, from Ōme) and **692T** (weekday 快速
  but a rush-hour run against 1654T's afternoon one); Takasaki **829M / 833M** (same label, 10-car
  vs 15-car). The same service name can carry a different pattern on Sat/Sun. **Only the game
  settles these** — the three items in "What is actually left" are safe because they differ by more
  than a label.
- **The aggregate DLC page paginates and returns different subsets per fetch.** Two passes here
  returned different route sets; this table is a union of both plus targeted lookups, so treat it as
  a floor. The store numbers packs ("DLC No. 7" = Yamanote) — if that numbering is contiguous it is
  a cheaper completeness check than scraping.
- **Keihin-Tōhoku is base-game content**, so it has no DLC page and its diagram list is unverified.

Refresh when a new pack lands (roughly every two months) or before starting any route build.
**A new pack is also the retro-fit trigger**, so refreshing is not only "what route was added" — it
is "which line did it land on, and does that line's existing pack announce now." The store page
cannot answer the second question; only loading the route can.
