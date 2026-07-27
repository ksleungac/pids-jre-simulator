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

- **SPDX headers** — `# SPDX-License-Identifier: MIT` on 114 tracked `.py` files (currently
  zero). This is the layer that makes the split per-file and machine-readable rather than
  requiring a reader to apply the scope note by judgment. **Blocked** behind the five
  uncommitted working files, deliberately — it touches every Python file and would tangle with
  them. Add a pre-commit check in the same pass so coverage cannot rot; full REUSE compliance
  considered and rejected as disproportionate.
- **Old release source archives.** GitHub auto-attaches a generated "Source code (zip)" to every
  release, built from its tag. Those keep serving whatever the tag contained, indefinitely, no
  matter what HEAD does. Deleting the affected releases is the only way to stop it — author's
  decision, not a mechanical fix.
- **In-app non-affiliation statement.** Currently only in `THIRD-PARTY.md`. The app has its own
  disclaimer surface, which is where it would actually be seen.
- **zh-HK punctuation.** `conventions`-adjacent: the `/readme` skill records zh-HK as full-width
  punctuation, but the older zh-HK README paragraphs use half-width `,` and `(`. New text follows
  the rule; the older lines are an unswept inconsistency.
(Audio is not pending — see below.)

## Decided, do not re-litigate

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
