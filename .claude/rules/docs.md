---
paths:
  - "docs/**"
  - "TODO.md"
  - "**/README.md"
  - ".claude/rules/**"
  - ".claude/skills/**"
  - "CLAUDE.md"
---

# Documentation rules: WIP docs, where a rule lives, presentation changes

Path-scoped: Claude Code loads this file when a file matching `paths:` is read or edited, not at session start. These rules moved here from `conventions.md`, `principles.md` and `critical_lessons.md` on 2026-10-22, to keep the always-loaded corpus under the combined-size limit. Same rules, narrower trigger.

## Conventions

### Display module structure

- **WIP-doc → canonical-doc graduation.** Speculative or in-flight feature work lives in a `WIP_<topic>.md` doc with its own EDIT-CONTRACT, holding pending designs, transitional diffs and calibration insights. When the feature stabilizes the doc dissolves into its canonical home and is deleted, as a single-commit restructure with no parallel-existence period. The trigger is named in the doc itself. Precedents: `WIP_transfer_display.md` → `docs/DISPLAY.md` (2026-05-05, `render_transfer` promoted to production) and `WIP_E235_DISPLAYS.md` → new `docs/DISPLAY_E235.md` (2026-05-07, E235-0 lower-LCD circular renderer shipped).
  - **Trigger unmet → UPDATE it to current state; don't dissolve it and don't leave it stale.** A doc whose feature is partly shipped still holds the design and the rejected alternatives the remaining stage needs, so rewrite its status sections to what is true now and keep it. What this bars is a doc that is neither current nor gone. (2026-08-01: the atlas was shipped-verified for ShinGo but `#116` leaves Helvetica / Frutiger unbaked, so `fonts/` still ships and the doc's own trigger, "the proprietary faces are out of the tracked tree", was unmet — *"it is not desolving, just update with latest state."*)
  - **§ Pending is a graduation gate, so file by subject, not by whichever doc was open when you found it.** An item parked where it was discovered reads to every later reader as a claim about that subject, and it holds the doc open forever, since the trigger is an empty § Pending. Ask what the item is ABOUT and route it to its own home: an issue for work, the narrowest doc for a rule. Same error as `conventions.md` § Naming's name-by-cause rule, one artifact over — there it corrupts a name, here a location. (2026-08-08: a zh-HK punctuation sweep sat in `docs/wip/WIP_licensing.md`, filed by the session editing READMEs for the licence Credits — *"why is zh-hk chroms strings are a licensng problem?"*. It became `chrome-i18n` issue #121 and § Pending dropped to one real item.)
- **Read a WIP doc for its MODEL; take its STATE from git and the code — and read it before writing into it.** The design, the rejected alternatives and the numbers behind them stay true. `§ Status` and `§ State — pick up here` describe one moment and rot first, because work continues while the doc is updated at recap time, so trusting them re-solves what shipped or re-proposes what the author has since deferred. Check `git log` for the doc's own topic before believing any status line. The doc also holds the author's METHOD — scope fences, the per-element loop, the rule that an unresolved decision stays an `OPEN` bullet until they settle it — and a preloaded paraphrase of that workflow is not that workflow: a session resumed from a compacted summary carries the words with the gates stripped out, and it reads as sufficient. Open the doc's own scope and method sections at the start of any session that will touch it.
  - 2026-08-01: `WIP_font_atlas.md` still read "Nothing is committed" two commits after both landed. *"docs might be stale, just get the mental model from that and reapproach from professional view."*
  - 2026-08-25: `docs/wip/WIP_e233_0_display.md` was edited six or seven times in one session with four element sections appended, while §§ 4–6 were never opened. The drill-down-with-the-author step was skipped on every element, and four decisions the single reference could not settle — the clock's face, its `H:MM` form, its alignment, its corner — were made unilaterally and presented finished.

## Principles

#### Blind A/B verify presentation convention changes
Before adopting a new presentation convention, validate via blind A/B: parallel fresh-context agents with identical questions — one reads original, one reads new. Adopt only when answers match.

**How to apply:** Use for voice / structure / naming changes affecting prose. Not for code refactors or trivial tweaks.

**What it cannot measure: whether the text still reads as machine-written.** Both arms are Claude reading Claude against questions Claude wrote, so the A/B establishes comprehension parity and nothing about register. Rewriting a passage does not remove its machine-ness — it produces the same author's prose with the recognisable tics filed off. 2026-09-01, the author on a whole-corpus register pass: *"you can't just rewrite or rewrite that to think oh the claude-ness is gone."* Two things follow. Target the STRUCTURE rather than the wording, because splitting a sentence and unnesting a parenthetical are mechanical and lose no facts. And take the outside verdict from a human or from prose written outside this project; the corpus cannot audit its own voice.

**When the change is to the instruction files themselves, "fresh context" means a fresh PROCESS.** A subagent spawned with the Agent tool inherits the session's startup snapshot of `CLAUDE.md` and `.claude/rules/`, so it still holds the pre-edit corpus. A worktree nested inside the repo also loads the ancestor's `.claude/rules/`, so it holds the new one as well. Both arms then answer from both copies and the A/B measures nothing. Run each arm as headless `claude -p` from its own directory: the new tree, and a `git worktree add` of HEAD placed OUTSIDE the repo. 2026-10-22: both in-session arms of the path-scoped split reported seeing every rule twice, and the clean comparison needed the two headless runs.

#### No central kitchen-sink rules file
Each rule has exactly one home. Don't create aggregator files.

**How to apply:** Consult the placement table in `/session-recap`. Pick the narrowest-domain home.

#### Preloaded mental model vs progressive implementation detail
Mental model (what it models, scope, IRL framing) → pre-loaded files. Implementation details (draw-method gotchas, JSON-field minutiae) → domain docs, read on demand.

- **Compression buys ATTENTION, not tokens.** Preloaded rules (`.claude/rules/*`) load every turn — compress aggressively, strip rationale to one-liners; on-demand skills can afford fuller rationale, and mechanical classification (commit file sorting) offloads to hooks entirely. But the reason is that any one rule competes with ~33k tokens of sibling rules for attention, NOT that tokens are scarce. So a rule earns removal only by being WRONG or by actively causing bad behaviour (2026-07-26: rules cited as licence to widen scope); redundancy alone never does. (2026-07-27) User: *"i don't care about cost, don't save cost for me, i only care that you 99.9999999% of the time do the right thing."*
- **Rules do not reach that bar; gates do.** Advisory text competing for attention fails at some rate — the MEMORY.md cap sat stated and unread for three months at 97–100% violation. Where a rule must always hold, move it to a mechanical gate (pre-commit, publish-boundary refusal, a test) and let the prose describe rather than enforce.
- **Corpus out-competes a lone rule.** A preloaded rule that keeps getting violated is out-voted by the always-loaded docs modeling the counter-behavior — remove the counter-examples, don't restate the rule harder. (2026-07-24: the editorial-tone preference stuck only after de-polluting every rules/doc file, not after a stronger rule.)
  - **What gets modeled is the PROSE, not only the content.** A preloaded file is a style exemplar every turn, so its register is a functional property rather than decoration: write the corpus in four-clause sentences with nested parentheticals and the replies come back in that register, whatever § Writing tone says. 2026-09-01, measured across the 38.5k-word preloaded corpus: 2 slop words and 0 hedge phrases — the vocabulary layer § Writing tone polices was already clean — against 792 parentheticals, 382 sentences over 35 words and 148 X-not-Y constructions, which no rule covered. The author's report was that a friend's vanilla Claude Code output did not read this way. Sentence architecture is now ruled in `CLAUDE.md` § Writing tone; the point here is that the corpus teaches by example first and by instruction second.

#### Single source of truth
Don't duplicate facts across docs. Cross-reference instead.

#### Tighten before appending
When editing any audited doc, scan for redundant or stale claims about the topic first. Merge or delete in place rather than appending.

**How to apply:** Each audited doc carries an EDIT-CONTRACT. Re-read before non-trivial additions. Periodic sweep via `/distill-docs` or `/distill-rules`.

#### Sync downstream enforcers when reframing doc rules
When a doc rule is reframed from mechanical to case-by-case, audit tooling that hard-encodes the original form. Update or drop the enforcer in the same session.

**How to apply:** On any rule reframe, grep for enforcers referencing the old hard form; update or drop same session.

#### Big-bang rewrite when convention shifts
When a presentation convention changes and affects multiple files, do a one-off rewrite + write-time gate. Don't propose lazy incremental adoption.

**How to apply:** Propose rewrite + gate. Exception: if too large for one session, propose phased plan with deadline.
