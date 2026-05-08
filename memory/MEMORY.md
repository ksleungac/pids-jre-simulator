# Memory Index

Long-term curated memories. One-line pointers — daily logs hold the detail.

---

- [2026-05-08 PM](2026-05-08.md) — pre-commit infra: `.pre-commit-config.yaml` + `_dev_scripts/lint_primitives.py` (SysFont / `_MEIPASS` / `Path(__file__).parent` / `sys.frozen`) + Black wired; 24 files Black-reformatted, 24 alignment-critical sites wrapped `# fmt: off`; session-recap placement table split into region-scoped vs primitive-scoped; conventions.md § Tooling: stale "Black via pre-commit" rewritten + new path-resolution rule sibling to SysFont
- [2026-05-08 AM](2026-05-08.md) — principles.md cleanup: EDIT-CONTRACT added; 16 Collaboration entries (12 trimmed + 5 promoted to peer + 1 folded) + 5 more trimmed in Engineering rigor / Tooling / Data modeling; /distill-rules sibling skill created (rules-corpus audit, restructure allowed)
- [2026-05-07](2026-05-07.md) — E235-0 Yamanote sub-series: upper-LCD fork (no train-type cell) + circular full-route lower-LCD renderer (rounded-rect track, JY-code row mapping, breath-animated pentagon); boot-frame `current_time` race fix in `app.py:run()`; triage-policy rewrite (all deferred review findings → TODO.md, 22 past entries migrated)
- [2026-05-06 late evening](2026-05-06.md) — validator extension: Tier 1 transfer-data checks (lines.json category + icons exist; stations transfers slug resolution) + Tier 2 transfers_by_view ops (drop/edit slug validity + rows sum) + vibe-check pass + A1 (production `resolve_entry` is canonical, validator imports) + A2 (route-loader smoke-check) + B1 (transfer_view consumed by at-least-one stop on this route — direction matters because some station configs are forward-looking)
- [2026-05-06 evening](2026-05-06.md) — Yamanote dest-switching loader seed: route_loader.py + sticky-override closure at load time; "JSON is input grammar; runtime is closure" principle; validator gap-fills + `audio/_*/` fixture-skip; new principles.md § "Engineering rigor" with "Test the change, not just the bug" (distinct from claim-defense Verify-before-claiming)
- [2026-05-06](2026-05-06.md) — v0.5.3 release shipped + PyInstaller deployment-frame pathology codified across 3 layers (principles + vibe-check #11/#12 + review-dirty Lens 1/2); `app_paths.py` canonical helper consolidates 8 sites across 6 modules; /build Step 4 inverted to default-ship + exclusion list; /release skill replaces release.ps1; session-recap Rule 8 (cross-layer alignment)
- [2026-05-05 PM](2026-05-05.md) — transfer-info: render_transfer promoted to production (E235-1000 concrete); E235-1000 color-square policy (`_universal+color`) shipped; WIP_transfer_display.md dissolved into DISPLAY.md (~215 lines); `project_root()` consolidated to displays/utils.py; review+fix Ralph loop 2 cycles (1 critical + 9 warnings fixed)
- [2026-05-05](2026-05-05.md) — transfer-info: N=2/N=3 structural row-grouping rules + `rows` data override + Step 4 column-aware anchor row placement (with 1-vs-2 shinkansen dispatch); corpus 22/22 in-spec ✓; Preserve-named-user-frameworks extended with vocabulary-framing recurrence
- [2026-05-04 evening](2026-05-04.md) — transfer-info: GOLDEN-rule pipeline implementation + 19/22 corpus ✓; cascade vs greedy threshold split (min_inter_gap 0.5× / inter_element_margin 0.7×); sotetsu_through reclassified non_jr; MKG JO_north populated
- [2026-05-04 PM](2026-05-04.md) — transfer-info: per-N text scaling discovery (IRL ladder ≤5/6-9/≥10) + algorithm work paused pending Step 1 calibration; Scope-fidelity + Analytical-confirmation principles codified
- [2026-05-03 eve](2026-05-03.md) — Upper-LCD clip-rect refactor: region-rect manifest + `clip()` context manager → bleed structurally impossible; DISPLAY.md tightened ~58→12 lines; Verify-before-claiming recurrence note extended (3 more substrates)
- [2026-05-03 PM](2026-05-03.md) — transfer-info: name_ja_compress migration + 4 algorithm enhancements (capped row-grouping, single-row equal-spacing + side_pad formula, Rule 1 canvas-fit, blueprint placement) + 新橋/浜松町/大崎 populated; Preserve-named-user-frameworks principle codified
- [2026-05-03](2026-05-03.md) — OOBE action-history feature + ActionFlow refactor + STA seek bar + bundled-EN-fonts; Step 0 codified scope-expansion + weirdness-as-signal patterns
- [2026-05-02 PM cont 3](2026-05-02.md) — transfer-info layout: lex-maximin row-grouping + Rule 4 equal-spacing fallback + `transfers_by_view.edit` op; Pre-stated scope fences codified
- [2026-05-02 PM cont 2](2026-05-02.md) — transfer-info schema: nested variants, dot-notation refs, drop-only `transfers_by_view`
- [2026-05-02 PM cont](2026-05-02.md) — memory-system overhaul: killed log-only middle, sync codification + dedup gate, Step 0 friction loop + third-man behavioral review
- [2026-05-02 PM](2026-05-02.md) — transfer-info Rule 1/2/3 algorithm correction (per-entry asymmetric / leftmost-fit / per-segment) + implementation-completion-as-spec promoted to principles.md (recurrence #4)
- [2026-05-02](2026-05-02.md) — yellow-square nag indicator (blink + disappear-on-acknowledged + audio-busy gate) + dual-stream audio (PA on music, STA on Channel) + APPROACHING/STOPPING auto-fire asymmetry promoted to CLAUDE.md
- [2026-05-01](2026-05-01.md) — transfer-info Yokohama validated + Rule 1/2/3 refactor + through-service variant pattern (option b sibling slugs) + /third-man skill
- [2026-04-30 late evening](2026-04-30.md) — autodriver `pa_at_station` silent drain in `_fire_departure` + AUTO_INPUT.md vocabulary-discipline rules extended (arrow flows)
- [2026-04-30 evening](2026-04-30.md) — /distill pass + MEMORY.md drift traced to 4-23 + /session-recap MEMORY.md gate tightened
- [2026-04-30 PM](2026-04-30.md) — dep-classification pathology + `_dev_scripts/` rename + deployment-frame section in CLAUDE.md
- [2026-04-30 AM](2026-04-30.md) — OOBE tutorial vibe-pass: 9→8 steps, CJK chrome refactor, bilingual zh-HK/zh-CN translations shipped
- [2026-04-29 overnight](2026-04-29.md) — OOBE tutorial built (8-step walkthrough, state-jump pause convention, mixed-script renderer)
- [2026-04-29 late evening](2026-04-29.md) — chrome i18n foundation: i18n.py + language picker + setup translation + line badge + theme refresh
- [2026-04-29 evening](2026-04-29.md) — click-jump MVP shipped + autodriver Layer 3 refactor + state-machine docs split across 3 homes
- [2026-04-29 morning](2026-04-29.md) — pre_stops through-service feature + per_line refactor + Tighten-before-appending convention + omiya cut
- [2026-04-28 late evening](2026-04-28.md) — pentagon polish + autodriver STOPPING hook + final-approach-PA rule + skill chain validation
- [2026-04-28 evening](2026-04-28.md) — STOPPING state shipped: pa_at_station schema + unified state machine + lower-LCD pentagon
- [2026-04-28 PM cont](2026-04-28.md) — click-to-jump design discussion (paused); OCR state vocabulary settled; jump_to_stop verified single-purpose
- [2026-04-28 PM](2026-04-28.md) — manual distill pilot + /distill-memory skill + rules-taxonomy refinement (rule/fact/preference shape split)
- [2026-04-28 AM](2026-04-28.md) — drive recorder (JSONL) + interactive HTML report + state-machine PASSING fix + auto-commit incidents
- [2026-04-27](2026-04-27.md) — auto-input system end-to-end: dxcam HUD OCR + AutoDriver + setup-toggle + debug panel + PASSING badge classifier
- [2026-04-27 (STA)](2026-04-27.md) — saikyo + keiyo STA refresh; verify_sta_listen.py interactive trim + 0.5s pre-voice rule
- [2026-04-27 (vibe-check)](2026-04-27.md) — vibe-check cleanup + new /vibe-check skill + per-model `__init__.py` manifests
- [2026-04-26](2026-04-26.md) — doc reorganization (preloaded vs progressive split) + continuity arrows + dest-terminus fix + STA verifier UI
- [2026-04-25](2026-04-25.md) — 8-station view + LowerDisplay refactor + 2-line English station + Containment principle + Sobu Rapid 1217F end-to-end
- [2026-04-24](2026-04-24.md) — LowerDisplay global-index render + data audit + validate_data.py + v0.5.2 GitHub release + /build + /commit skills
- [2026-04-23](2026-04-23.md) — Station code badge: data/stations.json + Yamanote sta_code backfill + ModeCycler.enabled gotcha
- [2026-04-21](2026-04-21.md) — Docs deduplication, single-source-of-truth routing in session-recap
- [2026-03-31](2026-03-31.md) — Ralph loop skills implementation, key learning about agent roles
- [2026-03-27](2026-03-27.md) — CLAUDE.md reorganization, memory directory setup
