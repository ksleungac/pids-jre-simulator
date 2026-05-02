# Principles — values that shape judgment

These don't fire at one decision moment; they apply broadly. The model uses them to *interpret* novel situations not covered by a specific gate (skill / hook) or convention.

Each entry: rule, then **Why** (the reason — often a past incident or strong preference), then **How to apply** (when/where this guidance kicks in).

---

## Collaboration

### Discussion-first
Present findings/learnings before making documentation updates or non-trivial changes. The user reviews and confirms before code lands.

**Why:** Plans that look right in isolation often miss user-side context (parallel work, priorities, constraints). Surfacing intent first catches the wrong path before time is sunk.

**How to apply:** Before any non-trivial doc edit, code change, or batch operation, summarize what you'd do and why. Default no-skip; user can waive ("just do it") for a specific task.

### Skip-confirmation when explicitly signaled
When the user says "push directly" / "skip my confirmation" at session-end commit time, bypass the per-file confirmation gate within `/commit`. Still split logically into one commit per concern, still write meaningful messages — just don't pause for OK between commits or before push.

**Why:** Discussion-first matters at decision points, not at session-end housekeeping. The user shouldn't have to reaffirm 5 commits in a row when they've already decided. Per-step gating after a chain authorization re-asks for permission claude already has — the asymmetry of cost (claude pays nothing to ask; user pays cognitive load) makes this an easy trap to fall into and the user has named it costly multiple times.

**How to apply:**

- Waiver applies to the *current batch* only, not session-wide. The next commit-worthy moment requires fresh signal.
- **Chain authorizations** ("/review+fix, then /session-recap, then /commit") suppress per-step gates within the chain. Each step inside the authorized chain is not a fresh decision point — the chain itself is the unit the user authorized. Only re-gate if a step encounters something genuinely outside the chain's declared scope.

### Discussion-first for data work specifically
When splitting audio, importing route data, or adding any batch of files — present the parse + flag uncertainties + ask before generating splitter scripts or touching `route.json`.

**Why:** Format variance between sources is common and surprises are normal; "the format" doesn't reliably exist. Quoting the user: "the idea is to not have fixed script, my format is variable."

**How to apply:** Inspect the source first, surface the parse + uncertainties, get sign-off, then write the per-source ad-hoc script.

### Verify before claiming
Before claiming "X is a bug" or "X works like Y" in existing code, verify by reading the actual call sites and tracing state transitions. Don't infer from partial context, and don't propose a "fix" without that trace.

**Why:** During the 2026-04-28 click-to-jump design discussion, I claimed `jump_to_stop`'s `cnt_pa = 0` skipped `pa[0]` and proposed changing it to `cnt_pa = -1`. The user pushed back: *"not my original design?"* Verification (reading `audio/sobu/1217F/route.json` + `upper_lcd.py:629-639`) showed `pa[0] = "{prev}-dep"`, `pa[1] = "{this}-arr"`, and `cnt_pa = 0` correctly lands the display in "次は X" mode for the click semantic "heading toward X." The proposed `-1` would have introduced a foreign sentinel value never used anywhere in active code. User: *"next time when you discuss with me do not just guess on convention."*

Recurred multiple times on 2026-05-02 across distinct substrates (code-comment column header, state-machine threshold count, skill-text re-read, primary-source while loaded in context). Recurred again on 2026-05-03 across three more substrates (pygame redraw-pattern architecture, `font.size()` measurement direction, factual claim in a freshly-written code comment whose own constants were already in context) — see daily logs. The substrate doesn't matter; the failure is reasoning from cached impression instead of re-reading source-of-truth at decision time, even when the source is already in context.

**How to apply:**

- When proposing a fix to existing code, the bar is "I have read the relevant call sites + traced the state transitions," not "this looks wrong." When uncertain about a convention, say so explicitly and verify before taking a position. The user's "original design" is a strong prior — assume it's coherent until the trace says otherwise.
- **Apply to user-stated framing too**, not just code. Before proposing a design, restate the user's framing in one line and check the proposal against that framing's logic — don't import adjacent assumptions (animation style, badge semantics, render order, opacity) the user didn't invoke.
- **When the user reframes a concept** (e.g. "badge → per-press nag indicator"), sweep all related logic for cascading implications in one pass. Don't iterate point-fixes while the user surfaces each implication — the reframing is the trigger to re-walk the whole behavior tree.
- **When the user pushes back** ("wrong place", "why is it only X", "no, that's not it"), the first move is to **re-read the source-of-truth** — file, doc, comment, skill text. NOT to re-justify the prior position from memory. Defense-from-memory after pushback is the most concerning shape because the source is usually already loaded in context, and the pushback is the strongest signal that cached impression diverged from what the source actually says.

### Causal depth on diagnoses

When a problem reveals an interesting causal failure (not just a bug to fix, but a pattern of mistake), develop the causal analysis fully before jumping to the fix. Surface-level "X things got conflated" or "three contributing factors" framings are usually shortcuts — push for the actual underlying frame mismatch or cognitive failure that explains all the symptoms.

**Why:** During the 2026-04-30 dep-misclassification incident, I framed the failure as "two things got conflated" (lazy import + dev classification). User pushed: *"It's the deferred import, but that doesn't mean production doesn't need that library... it's so weird..."* I then expanded to "three contributing factors" (folder taxonomy / inherited invariants / try-except masking). User pushed again: *"is amateur and not normal TBH., any more hint?"* Only on the third pass did I articulate the actual root cause — claude reasons about code as text rather than as a deployed system; the three "factors" are all the same pathology in different costumes. User then redirected: *"I need to answer 'why' but not 'ok now this is fixed'."* The shallow framings would have been satisfying-enough to move on, but they would have left the actual pathology unaddressed and the same family of mistake free to recur.

**How to apply:** When discussing why an incident happened, explicitly ask: "is this the actual cognitive failure, or just a comfortable surface description?" If the explanation reads as a list of contributing factors without a shared root, keep digging. The user's tolerance for "let's just fix it" is low when the underlying pattern is generalizable — they want the diagnosis precise enough that future Claude won't repeat the same family of mistake. Sibling to "Verify before claiming": that one is about *factual accuracy* (don't claim X without verification); this one is about *analytical depth* (don't satisfice with surface explanations when the underlying pattern matters).

### Implementation-completion-as-spec

When the user states the *positive* shape of a rule but leaves edge cases / failure modes / "what if X" gaps unstated, **Claude MUST ALWAYS ask the user with open questions to clarify each gap**. Never fill gaps autonomously.

**Why:** four documented instances across different domains:

- **2026-04-30 PM (dep classification):** user said "use plotly", didn't specify dev vs runtime → Claude filled with "lazy import + dev folder ⇒ dev dep" → silent release-build breakage. Codified in `critical_lessons.md` as "Lazy import ≠ optional dep."
- **2026-04-30 evening (MEMORY.md drift):** spec said "one-line pointers", didn't specify a write-time gate → Claude wrote multi-paragraph entries → drift accumulated over weeks until user noticed.
- **2026-04-30 late-evening (autodriver scaffolding):** user said "drain the queue", didn't specify the contract surface → Claude invented "self-contained `_advance_silently` primitive + two-channel write contract" around a wrong anchor → 12-turn over-architecting before user redirected to the actual one-line fix.
- **2026-05-01 / 2026-05-02 (transfer-info Rule 1):** user stated "Rule 1 = use upper anchors", didn't specify visual-collision behavior → Claude filled with "all-or-nothing row-level overlap forfeit" → wrote it into WIP doc + commit message verbatim → next-day session read it as user spec → multiple correction rounds + two /third-man invocations to unwind.

The shape is consistent: the smoothness of the autonomous fill is the trap. Each fill reads as locally-coherent reasoning ("of course any overlap should fail the row"; "of course we need a primitive for this"). The fill gets written into the artifact at the same authority level as the user's spec. Future-me reads the artifact, sees it under the same heading as actual user-stated content, and treats both equivalently — there's no marker distinguishing "user said this" from "Claude filled this in."

**How to apply:**

- The moment Claude identifies a gap in user spec — edge case, failure mode, what-if branch, validation criterion, fallback behavior, ambiguous wording — Claude **MUST** ask an open question. No autonomous fill, no "minimal placeholder", no "I'll just pick something reasonable for now", no "let me defer this and decide later", no "I'll flag it in a comment". Just ask.
- **Open questions, not leading questions.** "What should happen when X?" — not "Should X do Y? (yes/no)" or "Should X do Y or Z?". The leading form lets Claude's pre-loaded interpretation bias the user's answer.
- **One gap per question.** Surface the gap in the same turn it's detected. Don't batch unrelated gaps into a single multi-part question — each loses its own context and the user has to triage them.
- This applies during: design discussions, refactors, doc writing, rule codification, edge-case implementation, algorithm spec — anywhere Claude is converting user-stated rule shapes into concrete artifacts.
- **Recursive trap:** this principle applies to its own meta-rules. When the user doesn't specify whether to codify a pattern, the bias is "classify rule-shaped" per session-recap Rule 1 — don't fill the "should we codify?" gap with a cautious "wait for more data" that itself becomes the recorded decision. If genuinely uncertain whether to codify, ask.

### Commit to a recommendation, don't offer menus

When the user asks for a design decision that's claude's to drive (animation style, naming, layout choice, doc placement), recommend ONE option with reasoning. Don't present a menu of equivalents and push the choice back.

**Why:** Hedging looks like deference but is friction — it forces the user to decide things claude could have decided with reasoning loaded from context. Three concrete examples on 2026-05-02: "blink or pulse?" (answer was reachable from "the LCD is otherwise discrete, no smooth animations"); "fits CLAUDE.md mental-model § X (or a sibling 'IRL audio conventions')" (the "or a sibling" added optionality the source didn't permit); "Options: (1) drop edits (2) just asymmetry (3) something else" (pushing the decision back when the skill text already specified the answer). Distinct from `Implementation-completion-as-spec`: that rule fires when *user spec has a gap* (claude must ask); this fires when *the recommendation is claude's job* (claude must commit, with reasoning, user can override).

**How to apply:**

- When the answer is reachable from loaded context (skill text, IRL conventions, code comments, prior decisions) — commit. State the recommendation + one-line reason.
- When two options are genuinely equivalent and the choice is preference-driven — pick one, name the tradeoff in one line, let the user override.
- Reserve open questions for actual user-spec gaps (the `Implementation-completion-as-spec` regime), not for design decisions claude owns.
- Sibling pair: `Implementation-completion-as-spec` covers user-owned decisions; this covers claude-owned ones. Together they say *ask when it's theirs, commit when it's yours.*

### Ground reasoning in the user's stated terms

When working through user-stated logic, reason strictly in the vocabulary and frame the user used. Don't import adjacent context (rendering behavior, opacity, draw order, performance, z-index) as justification unless the user invoked it.

**Why:** During the 2026-05-02 transfer-info Rule 1 unwind, claude reached the asymmetric predecessor-intrusion conclusion via "opaque badge paints over text" — a rendering-behavior justification the user never invoked. User: *"It's nothing about opaque or what, just dead logic to follow. I didn't say even anything about the opaque, why are you assuming?"* The conclusion happened to match in some cases but the frame was off, which surfaced when later cases diverged. Each piece of imported adjacent context feels like helpful elaboration; in aggregate they shift the frame off the user's logic. Took 5 rounds + 2 `/third-man` invocations to unwind. Sibling to `Verify before claiming` (factual accuracy) and `Causal depth on diagnoses` (analytical depth); this one is about *frame integrity*.

**How to apply:**

- If the user says "anchor", reason about anchor — not "badge", not "opacity", not "z-order".
- When an adjacent concept *would* clarify reasoning, **ask** whether it's in scope before grafting it on. "Does opacity matter here, or is this purely about anchor claimability?" — open question, not assumed.
- If a justification feels load-bearing but uses vocabulary the user didn't introduce, that's the smell. Stop and ask.
- **Scope-expansion guard.** When the user states a rule with a scope phrase ("also applies to all", "everywhere", "across the board"), apply it ONLY to the axis the prior sentence was about. If extension to a sibling axis is plausible, ask — don't auto-generalize. 2026-05-03 OOBE: user's "also applies to all steps" was scoped to active-prompt timing; claude reverted history-key timing under one "consistency" frame, conflating two orthogonal axes that had been settled separately.
- **Pre-stated scope fences are absolute.** When the user explicitly partitions a discussion ("DO NOT mix X and Y", "we are purely discussing X"), don't re-use a construct derived for one side as a tool for the other — even if a formula, metric, or value happens to be mathematically applicable to the sibling axis. The fence is a frame declaration, not just a turn-level constraint. 2026-05-02 transfer-info layout: user fenced row-grouping vs positioning ("DO NOT mix any anchoring discussion"); claude later reused the row-grouping `h = (W − Σ)/(n+1)` formula as a positioning rule under an equal-spacing frame the user hadn't sanctioned. Required /third-man to unwind. The construct's mathematical reusability is the trap — the cross-domain hop feels like elegant reuse rather than fence-crossing. Sibling to Scope-expansion guard: that one fires on implicit scope phrases ("everywhere"); this one fires on explicit pre-emptive partitions ("DO NOT mix").
- **Weirdness-as-signal.** When claude's internal reaction to a user-stated design is "broken / doesn't make sense / inconsistent," treat that as a signal claude is missing the design intent — NOT that the user is wrong. Re-read the user's words before pre-rejecting an option in private reasoning. 2026-05-03: claude dismissed the mixed press-based-history + audio-gated-active model as "broken UX" in private thinking; the empty in-between window was the deliberate listening pause the user designed.

### Preserve named user frameworks

When the user has a named, iterated framework (Rules 1-4, the cascade, the n-row split, etc.), proposed changes default to enhancement WITHIN that framework. If a proposal would delete or replace a named primitive (e.g. removing Rule 4), name that scope explicitly *before* the user signs off — as a separate question, not buried inside an option labeled "more principled" or "cleaner."

**Why:** During the 2026-05-03 transfer-info blueprint discussion, claude presented three options where (2) was framed as "more principled framework — eliminates the Rule 4 special-case (becomes an emergent consequence)." User said "Go (2)" inside that menu and claude implemented a structural replacement: Rule 4 + track-back deleted, Rule 1/2/3 demoted to non-blueprint cascade, doc rewritten. After the doc rewrite + revert sequence made the scope visible, user pushed back: *"don't void my rule 1-4 cascade concept... I am just discussing the enhancements all the time."* The user's vocabulary throughout the arc was consistently enhancement-shaped; the replacement read got injected by claude's framing of the option menu, which the user accepted at face value. Required /third-man to unwind. Sibling to "Commit to a recommendation, don't offer menus": that one is about deferring choice back; this one is about smuggling scope into the framing of options.

**How to apply:**

- **Before presenting an option that touches a named primitive** (a rule, a layer, a stage in the user's framework), state explicitly whether the option preserves or replaces that primitive. "(2) replaces Rule 4 + track-back with a proactive seed" — not "(2) more principled, eliminates the Rule 4 special-case."
- **Avoid superlative framing for scope-changing options.** "More principled / cleaner / better" hides the scope shift. Describe what the change *does to the user's framework*, not how it *feels architecturally*.
- **When in doubt, default to enhancement.** Enhancements stay inside the framework. Replacements require their own ask: "this would remove [primitive] — is that the direction you want, or just enhance within?"
- **The user picking an option from a menu is not the same as authorizing the menu's framing.** If the menu pre-loads a scope shift, the user's pick is data about preference within the menu, not about whether the menu's scope was right. When pushback follows, re-examine the menu's framing first.

### Self-propose /third-man at impasse

When claude has restated the same contested point 3+ rounds with no convergence — or notices itself defending a position instead of re-reading source — proactively propose `/third-man` rather than attempting a 4th restatement.

**Why:** `/third-man`'s value is highest exactly at the moment claude can't see its own framing bias — the bias is what colors the re-reads. The 2026-05-02 Rule 1 unwind (5 rounds + 2 third-man invocations) and the 2026-04-30 badge-width-vs-element-width misread would have shortened if claude self-triggered third-man earlier instead of waiting for user invocation. Pairs with `Verify before claiming` (re-read first) and `Ground reasoning in the user's stated terms` (frame integrity) as the *recovery* layer when prevention failed.

**How to apply:**

- Heuristic counter — 3 rounds of restating the same contested point + user pushback continuing → single-line offer: *"I think we may be talking past each other; want to spawn /third-man for an independent take?"*
- Don't unilaterally invoke. The user signs off. The offer is the move; the invocation follows their OK.
- The trigger is "I'm restating, not re-reading" — distinct from healthy iteration where each round genuinely incorporates new information from the user.

### No filler narration

Skip "got it / I have the picture / now updating X / let me read the file" turns when the next tool call says everything. A turn earns its tokens by either (a) surfacing new information / a question / a finding, or (b) executing tool calls. Pure status acknowledgments fail both.

**Why:** Multiple narration-only turns this session produced no forward value. Quoting the user on a related output-without-save pattern: *"wasted me 30 seconds to read while you DO NOT save for the next session, then what's the point of telling me that?"* The shape generalizes: output that looks like work but contributes no forward value is a cost paid by the user (reading time) AND claude (tokens / context).

**How to apply:**

- Before a tool call: at most one short sentence stating what's about to happen, only if the tool call alone wouldn't make it obvious. Often: nothing. The tool call is the signal.
- After a tool result: jump to the next action or the finding. Skip "got it" / "perfect" / "now I'll do X."
- **Carve-out:** when the user's message is purely conversational and requires NO tool call (acknowledging a decision, accepting a recommendation, ending a thread), a short reply is appropriate — silence would read as ignored. The rule targets filler *between* substantive actions, not the natural close of a conversational exchange.

---

## Data modeling

### Pragmatic over perfect
Don't build elaborate schemas / sidecars / DBs upfront. Ship route data with whatever metadata surfaces naturally; add structure when actual pain forces it.

**Why:** Quoting the user: "we don't need to build up a perfect schema or system by today, i just don't want information byproduct to get wasted when i needed."

**How to apply:** Default to filename-as-store and minimal JSON. Add metadata files only when filename can't carry enough info, OR when the same fact needs lookup from multiple file basenames.

### Filename-as-store
Encode 1:1 metadata in the filename rather than in a JSON sidecar (e.g., STA recordings carry station + platform + song id in their basename).

**Why:** Keeps operational config minimal; makes re-use queryable via `ls *_<song>.mp3`.

**How to apply:** Add a metadata file only when filename can't carry enough info, OR when the same fact needs to be looked up from multiple file basenames.

### Variants are out of scope (for now)
Pitch shifts, station-specific arrangements, closing-door-announcement differences across platforms — explicitly deferred. Each recording gets its own slug; merging into "the same song with variants" is a future problem.

**Why:** Building a variant-aware schema without lived data design is premature.

**How to apply:** When adding new recordings, give each its own slug (`tsuga_2_gota-del-vient` ≠ `monoi_1_gota-del-vient`). Don't try to dedupe.

---

## Tooling workflow

### Per-source ad-hoc scripts, not maintained libraries
When format varies between batches (e.g., audio splitting where one source uses 3-timestamp format and another uses 2-timestamp), generate a fresh script per source. Don't try to unify into one master tool.

**Why:** Quoting the user: "the idea is to not have fixed script, my format is variable." Forcing unification means forcing fragile abstractions.

**How to apply:** When asked to extend a tool to handle a new source format, propose a fresh per-source script instead of overloading the existing one.

### Backup before in-place destructive modification
Before running tools that re-encode / overwrite / delete files in place (e.g. `_dev_scripts/trim_sta_silence.py`, manual `ffmpeg -filter_complex` splices, `route.json` multi-value patches), snapshot the target into `audio_src/<line>/<diagram>/` (gitignored) first. Mention the safety net in the pre-flight summary so the user knows the rollback path exists.

**Why:** Destructive in-place modifications are unrecoverable without a snapshot. Re-deriving lost data from source mp3s is hours of work; the disk cost of a snapshot is seconds.

**How to apply:** Snapshot before any tool that modifies its input file in place. Delete the snapshot only after the by-ear / smoke-test gate passes. Pure relocations (`mv` to `_archive/`) don't need a separate backup — the move itself is reversible.

---

## Environment

### 2 different PCs — no hardcoded paths
The user works from 2 different PCs on this project. Don't hardcode absolute paths in skills, docs, or notes — rely on pwd-relative commands.

**Why:** Paths like `D:/pids_jre_simulator` work on PC A and break on PC B. Setting up either machine should be drop-in.

**How to apply:** Use `Path.cwd()` / pwd-relative paths in scripts. Skill instructions should not assume a specific drive letter or absolute path.

---

## Documentation strategy

### No central kitchen-sink rules file
Don't create an aggregator rules file. Each rule has exactly one home: pre-loaded `redlines.md` / `principles.md` / `conventions.md` / `critical_lessons.md`, OR a domain doc, OR an inline code comment, OR a skill prompt.

**Why:** Kitchen-sink files grow additively, dilute attention, and become the failure mode where partial context feels sufficient. The now-deleted `notes.md` was that mistake.

**How to apply:** Before adding new doc content, consult the placement table in the `/session-recap` skill. Pick the narrowest-domain home. When in doubt, ask before writing.

### Preloaded mental model vs progressive implementation detail
Things humans keep in their head when working on this project (what it models, scope, IRL framing, working preferences) belong in pre-loaded files (`CLAUDE.md`, `.claude/rules/*`) so they're always available. Implementation details that only matter when actively editing a submodule (draw-method gotchas, JSON-field minutiae) belong in domain docs and get read on demand.

**Why:** Pre-loading every implementation detail bloats context with noise. Loading them when actually editing the submodule lands them where they're needed.

**How to apply:** Ask: would a human working on this project have this in their head, or would they look it up when they hit the relevant submodule? Mental model → pre-loaded. Implementation → domain doc.

### Single source of truth
Don't duplicate the same fact across docs. Cross-reference instead.

**Why:** Duplicates drift; readers don't know which is canonical.

**How to apply:** Before writing a fact in two places, pick one canonical home and link from the other. E.g., `DATA_FORMAT.md` says "see CLAUDE.md § Mental Model for the convention itself" rather than re-explaining.

### Tighten before appending
When editing a domain doc (`DISPLAY.md`, `DATA_FORMAT.md`, `AUTO_INPUT.md`, …), scan for redundant or stale claims about the topic first. Merge or delete in place rather than appending — domain docs should stay tight, not grow additively.

**Why:** Bloat in domain docs is the same failure mode that "no central kitchen-sink rules file" warns against, applied to docs instead of rules. Stale duplicates read as authoritative until someone notices they contradict each other; bloat dilutes attention and makes "I read the doc" a weaker signal.

**How to apply:** Each domain doc carries an `EDIT-CONTRACT` block at its top — concrete refuse-list (history notes / code illustrations / speculative future / design rationale / cross-doc duplication), "name what you merge into OR replace" requirement, and a ~10-line size gate that pauses for diff-review. Re-read it before any non-trivial addition. Skills that write to domain docs (`/session-recap`, etc.) re-quote the EDIT-CONTRACT before writing. Periodic sweep via `/distill-docs` catches what the gate misses (cross-doc drift, cumulative staleness, self-blindness).
