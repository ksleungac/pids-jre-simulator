# WIP — Rule firing vs rule reading (harness design discussion)

> **EDIT-CONTRACT.** Discussion scratchpad for an in-flight harness design conversation; NOT canonical.
> **Holds:** the 2026-06-11 analysis of the preloaded rules corpus, failure-class taxonomy, draft proposals, open questions.
> **Refuses:** final rules (those go to canonical homes on graduation), session narrative (memory/), duplicated rule text from `.claude/rules/*` (cite, don't copy).
> **Graduates when:** discussion concludes → accepted proposals codify into `conventions.md` / `principles.md` / skill text / hooks, then this file is deleted (single-commit restructure, per WIP precedents).

## Origin

User question (2026-06-11, verbatim): *"i regularly distill the rules to keep the preloaded context in size, however, i think the pre-loaded context are not kind of abstract and high-level, would you find it hard to apply, take a look?"* — with the framing that the daily driver is Opus, assumed equally capable of inferring preferences / best-choice-now.

Reviewed: `CLAUDE.md` + `.claude/rules/{principles,conventions,critical_lessons,redlines}.md`, ~21.5k preloaded tokens.

## Verdict

**The corpus is not too abstract. The failure mode is FIRING, not comprehension.** Most entries already carry the three things that make a rule applicable: trigger condition, action, dated incident with verbatim quote. The weak spots are structural — *when* a rule gets retrieved at the decision moment — not wording.

## What's strong (don't break in distillation)

- Mechanical triggers that pattern-match mid-edit: "Search before authoring" (*function < 20 lines, stdlib-only, name like `load_*`/`resolve_*`*), "Converge on the model" (*2+ corrections, non-monotonic state* — countable).
- critical_lessons §5 wrong/right code shapes side by side — zero interpretation needed.
- Verbatim user quotes pin scope down; they are what prevents preference *inference* (which drifts) from substituting for preference *record*.

## Three failure classes (where application is genuinely hard)

1. **Internal-state triggers.** Rules whose firing condition is the model's own cognition — "Causal depth" (*is this a comfortable surface description?*), "Weirdness-as-signal", parts of "Implementation-completion-as-spec". The failing cognition is the same cognition doing the check; self-assessment triggers fire weakest. Abstract in *detectability*, not wording.
2. **Reflex-fighting rules.** Prose loses to trained gradients under momentum. Evidence in-project: continuity band-aid shipped the SAME DAY the upstream-fix rule was codified (memory 2026-06-11: "the rule didn't fire during authoring"); urge-to-commit survived the soft phrasing, died only on absolute reasoning-path-block phrasing + redlines placement.
3. **Attention decay in long tool loops.** Mid-implementation the pre-load is ~100k tokens behind; salience decays. Existing counter is the right one: decision-moment injection (`edit_nudge_hook`, `unread_readme_hook`) — the sensor ladder is the harness's real engine.

## On model capability ("Opus as clever as you")

Cleverness is not the bottleneck. Any capable model applies a rule once it's in attention. Cross-model differences show up in (a) retrieval at the decision moment under load, (b) strength of the competing reflex. Both are addressed by structure (triggers, hooks, absolutes), not smarter wording. Optimizing rules for "a clever model will infer my intent" is the trap — verbatim quotes + mechanical triggers are the anti-drift mechanism.

## Draft proposals (to discuss)

1. **Distill rationale, never triggers or the sharpest example.** A rule stripped to its principle ("make surgical changes") becomes generic advice every model already knows and routinely violates. The dated example IS the rule's teeth. Candidate codification target: `/distill-rules` skill text — add an explicit "never compress away trigger lines or the single sharpest example" clause.
2. **Two-strikes-→-sensor promotion policy.** A prose rule violated twice (dated evidence exists in memory logs) moves DOWN the ladder — hook / linter / redlines absolute — rather than getting rewritten. Already happened implicitly (commit-prompting); make explicit. Candidate home: `conventions.md § Tooling` (sensor-tier paragraph).
3. **External proxies for internal-state triggers.** Class-1 rules can't be fixed by wording; give them textually-detectable proxies. E.g. "Causal depth" proxy: *diagnosis output contains a list of contributing factors with no shared root* — detectable in the model's own output. Needs per-rule proxy hunting; some may have none.
4. **Size policy: rule-count over token-count.** 21.5k preload is earning its space; the dilution risk is number of competing rules, not tokens. Prefer merging sibling entries (example-bullets on existing rules) over adding peers — already the practice, worth stating as the distill criterion.

## Open questions for the deeper discussion

- Which class-1 rules get proxies, and what are they? (Causal depth has a candidate; Weirdness-as-signal may be irreducible.)
- Does the two-strikes policy need a tracking mechanism, or is the memory-log + recurrence-count convention in TODO deferred-findings already enough?
- Are there current prose rules with one strike that should be pre-emptively watched? (Candidates: upstream-fix-not-draw-side — one shipped violation despite same-day codification.)
- What CAN'T move down the ladder: chat-behavior rules (commit-prompting was one) have no tool-call to hook. Is redlines.md the terminal home for all of these, and does redlines stay small enough to keep its salience advantage if so?
- Should `/session-recap` Step 0 (friction self-check) get the class-1 treatment too? It's itself an internal-state trigger.
