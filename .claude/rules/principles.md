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

**Why:** Discussion-first matters at decision points, not at session-end housekeeping. The user shouldn't have to reaffirm 5 commits in a row when they've already decided.

**How to apply:** Waiver applies to the *current batch* only, not session-wide. The next commit-worthy moment requires fresh signal.

### Discussion-first for data work specifically
When splitting audio, importing route data, or adding any batch of files — present the parse + flag uncertainties + ask before generating splitter scripts or touching `route.json`.

**Why:** Format variance between sources is common and surprises are normal; "the format" doesn't reliably exist. Quoting the user: "the idea is to not have fixed script, my format is variable."

**How to apply:** Inspect the source first, surface the parse + uncertainties, get sign-off, then write the per-source ad-hoc script.

### Verify before claiming
Before claiming "X is a bug" or "X works like Y" in existing code, verify by reading the actual call sites and tracing state transitions. Don't infer from partial context, and don't propose a "fix" without that trace.

**Why:** During the 2026-04-28 click-to-jump design discussion, I claimed `jump_to_stop`'s `cnt_pa = 0` skipped `pa[0]` and proposed changing it to `cnt_pa = -1`. The user pushed back: *"not my original design?"* Verification (reading `audio/sobu/1217F/route.json` + `upper_lcd.py:629-639`) showed `pa[0] = "{prev}-dep"`, `pa[1] = "{this}-arr"`, and `cnt_pa = 0` correctly lands the display in "次は X" mode for the click semantic "heading toward X." The proposed `-1` would have introduced a foreign sentinel value never used anywhere in active code. User: *"next time when you discuss with me do not just guess on convention."*

**How to apply:** When proposing a fix to existing code, the bar is "I have read the relevant call sites + traced the state transitions," not "this looks wrong." When uncertain about a convention, say so explicitly and verify before taking a position. The user's "original design" is a strong prior — assume it's coherent until the trace says otherwise.

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
Before running tools that re-encode / overwrite / delete files in place (e.g. `data_tools/trim_sta_silence.py`, manual `ffmpeg -filter_complex` splices, `route.json` multi-value patches), snapshot the target into `audio_src/<line>/<diagram>/` (gitignored) first. Mention the safety net in the pre-flight summary so the user knows the rollback path exists.

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
