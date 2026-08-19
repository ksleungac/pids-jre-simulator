# WIP — Licensing posture (MIT split grant + asset carve-out)

**Tracking:** not filed as an issue — the outcome is repo-level rather than user-facing.

**Status:** core artifacts landed 2026-07-27. Remaining items are sequencing-blocked or are
decisions for the author, listed under § Pending.

Prompted by an outside report noting the repo had no license file (so it defaulted to
all-rights-reserved) and that `fonts/` redistributes commercial font software.

---

## EDIT-CONTRACT

- **Holds:** the licensing decisions and their reasoning, what remains open, and the rejected
  alternatives.
- **Does NOT hold:** the grant itself (that is `LICENSE`), the asset inventory (that is
  `THIRD-PARTY.md`), or rules already codified (`conventions.md § Tooling`).
- **Graduation trigger:** when § Pending is empty, fold anything still load-bearing into
  `conventions.md` and delete this doc.

---

## Landed

- **`LICENSE`** — MIT, verbatim body first so GitHub's detector still identifies it, then a
  separated scope note limiting the grant to authored code and documentation.
- **`THIRD-PARTY.md`** — the carve-out. Detail scales with how compliant each class is:
  attribution-bearing material is itemized, everything else is disclaimed by category with its
  rights holder named.
- **README credits** in all three languages (`## Credits` / `## 鳴謝` / `## 鸣谢`) — thanks plus
  the required CC BY-SA attribution, pointing at `THIRD-PARTY.md`.
- **`conventions.md § Tooling`** — new asset class must update `THIRD-PARTY.md` in the same
  change; classify per file class, not per folder.
- **SPDX headers** (2026-08-08) — `# SPDX-License-Identifier: MIT` on all 124 tracked `.py`
  files, which is what makes the split per-file and machine-readable instead of asking a reader
  to apply the scope note by judgment. Inserted byte-level so each file kept its own line
  terminator, after any shebang or PEP 263 coding declaration. Full REUSE compliance stays
  rejected as disproportionate — the identifier without the `SPDX-FileCopyrightText` line.
  Coverage is held by a `spdx-header` pre-commit hook (`_dev_scripts/check_spdx.py`), which
  reads only the first 3 lines so a module that merely *mentions* SPDX cannot pass; mutation-
  tested at birth against a missing header and against a tag sitting below the header.
  **It found a latent defect on contact:** `_tests/t1_unit/test_start_station_labels.py` (now merged into `test_startup.py`) carried
  a UTF-8 BOM (the § Tooling PowerShell round-trip trap). Python accepts a BOM at byte 0, so the
  test had always passed; pushed to line 2 by the header it became a `SyntaxError`. BOM removed.
  A sweep of every tracked file found one other, `assets/README.md`, harmless in Markdown and
  left alone.
- **8 of 9 releases deleted, tags included** (2026-08-08) — v0.6.0, v0.5.4, v0.5.3a, v0.5.3,
  v0.5.2, v0.5.1, v0.5.0b, v0.5.0. `fonts/ShinGoPr6N-Medium.otf` entered in the initial commit,
  so every tag carried it; there was no old-versus-new split to draw. Each tag's SHA was recorded
  before deletion, since every one is still reachable from `master`. Verified after: `v0.5.4`'s
  source archive returns 404, `v0.6.2`'s still 200.
- **ShinGo untracked** (2026-08-19) — `git rm --cached fonts/ShinGoPr6N-*.otf`; the files stay on
  the author's machines, history keeps the blobs by the no-rewrite decision. This is what closes the
  forward exposure a clone of `master` carried. **The 2026-08-08 commit that claimed this added the
  `.gitignore` rule and stopped there** — an ignore rule has no effect on a tracked file, so all
  three faces kept shipping in every clone for eleven days while the commit message, `WIP_font_atlas.md`
  and `THIRD-PARTY.md § Fonts` all stated they were gone. A compliance claim that nothing checks is
  a claim about intent. Gated now by the `no-tracked-ignored` pre-commit hook
  (`_dev_scripts/check_tracked_ignored.py`), which fails on any tracked file the repo's own
  `.gitignore` matches; mutation-tested at birth by re-adding a face to the index.
- **`font_atlas/` in `THIRD-PARTY.md`** (2026-08-08) — the release carries pre-rendered raster
  output of the LCD typefaces, a shipped class that appeared in no inventory path. Cross-
  referenced from § Assets derived from third-party software to § Fonts rather than restated.

## Why MIT and not Apache-2.0

Apache's three advantages do not apply here. No patent surface. Its trademark clause disclaims
only the licensor's own marks, not the operator marks actually in play. Its NOTICE-propagation
mechanism was the one real contender, and per-file SPDX identifiers do that job more precisely.
What remained was 200 lines against 170 words for a project whose license exists to signal
"you may read and fork this." Copyleft was ruled out: it fights the goal of easy reuse, and
GPL over a tree holding non-free assets is a known mess.

## Asset findings worth keeping

- **The icons are the healthiest class in the repo.** All 37 come from Wikimedia Commons; 34 are
  `PD-textlogo` (below the threshold of originality — nothing to comply with, no attribution
  owed), and 3 are CC BY-SA 4.0, now properly attributed. Verified against the Commons API, not
  assumed.
- **Copyright and trademark are separate axes.** Public-domain status says nothing about
  trademark; 11 of the 37 carry Commons' trademark warning. Displaying an operator's mark to
  identify that operator's own line is nominative use, and the non-affiliation statement in
  `THIRD-PARTY.md` is the standard mitigation.
- **`data/` is mixed** — authored JSON alongside 37 third-party operator marks and game-derived
  screenshots. This is what drove the per-file-class rule.
- **Audio metadata hygiene.** Shipped mp3s should carry no ID3 tags. A 2026-07-27 scan found 351
  of 858 carrying inherited tags — encoder strings, mp4 container brands, and on 78 files a title
  and artist frame. Tags serve no purpose here (playback is by filename), so the standing rule is
  that shipped audio ships bare.

---

## Pending

- **v0.6.2 is the last release still serving font software.** Its zip, its exe and its source
  archive all carry `fonts/ShinGoPr6N-*.otf`; it was kept deliberately (2026-08-08) because it is
  the live download — 154 zip + 57 exe pulls, and where the YouTube traffic lands. Deleting it
  before a replacement exists would 404 every download pointer. Closed by shipping a fonts-clean
  release from current `master` and then deleting it, in that order.
(Audio is not pending — see below.)

## Decided, do not re-litigate

- **No in-app non-affiliation statement** (2026-08-08). Author declined; `THIRD-PARTY.md` carries
  it and that is the endpoint. Don't re-propose a disclaimer surface in the app.
- **A release's source archive is served from its TAG, not from the Release object** (verified
  2026-08-08, not assumed: `/archive/refs/heads/master.zip` returns 200 and no Release exists for
  a branch). So `gh release delete` alone leaves the tree one click away — deleting the tag is
  what stops it, and `--cleanup-tag` does both. Recoverable in one direction only: a tag pointing
  at a commit still reachable from `master` can be recreated from its SHA, but uploaded assets
  are gone for good.
- **No history rewrite** (2026-07-27). Past commits keep what they had; the posture is
  forward-clean, aimed at future exposure rather than retroactive cleanliness. Every measure here
  should be judged against that goal, not against making the history clean.
- **Audio: disclaimed by category, and that is the endpoint** (2026-07-27). No transformation
  exists that changes the nature of the act, unlike the font atlas (`WIP_font_atlas.md`), so there
  is no equivalent fix to build. `THIRD-PARTY.md` names the rights holders by category; the
  practical mitigations are non-monetisation, non-concealment, and responding promptly to any
  removal request. Not a task list — don't reopen it as one.
- **Shipped mp3s keep their ID3 tags — do NOT strip them as hygiene** (2026-07-27). Considered and
  rejected. Removing rights-holder identifying metadata (title / artist frames) is an affirmative
  act addressed by copyright-management-information provisions in its own right (US 17 U.S.C.
  §1202(b), and analogues elsewhere), it makes conduct read as willful rather than passive, and it
  reduces real-world discoverability by approximately nothing — audio is matched by fingerprint,
  not by metadata. The asymmetry is one-directional: all cost, no benefit. A future tidy pass will
  read 351 tagged files as untidy; they are deliberate.
