---
name: readme
description: README / i18n maintenance — keep English and translated READMEs in sync, extract language-agnostic content, apply the project's Chinese phrasing preferences.
triggers:
  - /readme
  - update readme
  - sync readme
  - translate readme
---

## Purpose

The project ships with three READMEs — English, Traditional Chinese (zh-HK), Simplified Chinese (zh-CN) — plus a shared language-agnostic `ROUTES.md`. This skill keeps them aligned in structure, extracts things that don't need translation, and codifies the Chinese phrasing preferences the user has already taught (once; don't re-learn).

## When to run

- Feature or data change surfaces in the user-facing flow (new install path, new keybinding, new route, new LCD feature).
- Release cadence: at minimum when cutting a GitHub release that changes install instructions or bundled contents.
- User says "update readme" / "sync readmes" / "translate X".

## Files & structure

| File | Language | Scope |
|------|----------|-------|
| `README.md` | English | Primary. Author here first, translations follow. |
| `docs/README.zh-HK.md` | Traditional Chinese (HK) | Mirror of English structure. |
| `docs/README.zh-CN.md` | Simplified Chinese (Mainland) | Mirror of English structure. |
| `docs/ROUTES.md` | Shared | Language-agnostic (Japanese line names + diagram codes work for all three reader audiences). Linked from each README's top bar. |

**Top link bar** on every README lists the *other two* languages + the shared doc:
```
root README.md:  **[繁體中文](docs/README.zh-HK.md)** · **[简体中文](docs/README.zh-CN.md)** · **[Supported Routes](docs/ROUTES.md)**
docs/README.zh-*: **[English](../README.md)** · **[简体中文](README.zh-CN.md)** · **[對應路線](ROUTES.md)**
```
- The current language is NOT linked from its own bar (avoid self-link).
- Only `README.md` sits at the repo root; the translations and `ROUTES.md` live in `docs/`, so the root bar prefixes `docs/` and the translated bars reach back with `../`.
- The `ROUTES.md` label is translated (`Supported Routes` / `對應路線` / `支持的路线`) — the label is localized, the target file is shared.

## Workflow

### Step 1 — Update English first

All changes land in `README.md` first. Discuss wording with the user; get it to "happy with this" before translating. The current English README's section order — **Download → Usage → Planned Features → Credits** — is the canonical shape; don't invent new sections unless the user asks.

**`## Credits` is thanks only — licensing does NOT go in the README.** The grant lives in `LICENSE`, the asset carve-out in `THIRD-PARTY.md`, and GitHub shows the license in its own sidebar, so a README licensing section is redundant. Credits name who to thank (and thereby satisfy any attribution obligation — CC BY-SA §3(a)(2) allows attribution by linking to a resource that carries the detail), then point at `THIRD-PARTY.md`. Don't add "code is MIT, assets are not" breakdowns. 2026-07-27, over two rounds: user — *"don't need to be super clear like to draft in readme"*, then *"no need to say which part are in which license, only just credits are enough"*.

### Badges — three, one style, each answering a real question

Under the description, above the language bar, in all three READMEs. Current set: **latest
release** (is this alive), **downloads** (do people use it), **platform** (Windows — saves
a wasted download, since nothing else above the fold says so). Labels are localized in the
zh files via shields' `&label=`, URL-encoded; the badge STYLE is `flat-square` everywhere.

**A badge row is the classic AI-slop tell, so the bar is that every one renders a real
value.** No `PRs Welcome`, no `Made with Python`, no `build: passing` on a repo whose CI
does not test anything. Two that were considered and rejected 2026-08-29: **stars** (19 at
the time — the badge invites a comparison you lose, and GitHub's sidebar already shows it)
and **license** (GitHub classifies this repo `NOASSERTION` because `LICENSE` carries the
`THIRD-PARTY.md` carve-out; hard-coding `MIT` would overstate a grant that does not cover
the audio or the fonts).

**The downloads badge is an `endpoint` badge, not a live one**, because shields can read a
value but cannot add two together and the real figure is `live releases + deleted ones`.
`.github/workflows/badge-downloads.yml` computes it and force-pushes a one-commit `badges`
branch. Consequences worth knowing: it renders `resource not found` until that workflow
has run once, and **deleting a release without first bumping `DELETED_BASE` silently drops
the number** — the rule lives in `/release` § "Deleting an old release", which is where
deletions happen.

### The hero image is GENERATED, and generated PER LANGUAGE

`_dev_scripts/gen_readme_hero.py` annotates one clean plate (`docs/assets/15-in-use.jpg`, a
screenshot of the game running with the app beside it) and writes one JPEG per language.
Each README points at its own. Edit `LANGS` in that script, never the images.

Two rules it enforces mechanically, because both failures are invisible until published:
the panels are **asserted clear of the app window and the canvas** (a longer translation
silently grows a panel over the thing the screenshot exists to show), and the HUD marker
box is **derived from `auto_input.hud_layout`** rather than typed, so it cannot drift into
pointing at scenery.

Panel copy takes its terms from the APP, not a dictionary — `OCR自動報站` / `OCR自动报站`,
`遠端控制` / `远程控制` are the strings on its own screens. `運転曲線` stays Japanese in all
three: it is the heading the report prints, so the zh form would name something the reader
never sees.

Font note: `NotoSansJP.otf` is weight **Thin** and far too light over a photograph — the
panel uses `NotoSansCJKsc-Bold.otf`. Latin-only faces render the kanji as tofu SILENTLY,
since PIL does not raise on a missing glyph.

### A README CANNOT embed anything live — verified, not assumed

`<iframe>`, `<script>`, `<style>` come back **escaped to literal text**; `<object>`,
`<embed>`, `<svg>`, `<canvas>`, `<form>`, `<video>` are **stripped**; `style`, `class` and
`on*` attributes are removed and `data:` URIs on `<img>` are dropped. So an interactive
chart cannot run on the README, and no clever SVG gets around it: `<img>`-referenced SVG
runs in a secure processing mode with scripting AND interactivity disabled, which is why
the animated-README-SVG ecosystem stops at animation. GitHub's own Mermaid / GeoJSON /
STL embeds *are* interactive, hydrated against a privileged render host on a fixed type
list user content cannot join.

**GitHub documents none of this.** The way to settle any future "will this survive a
README" question is to ask the renderer itself — the same pipeline the README uses:

```bash
curl -s -X POST -d '{"mode":"gfm","text":"<iframe src=\"x\"></iframe>"}' https://api.github.com/markdown
```

The only real option is a hosted page behind a link, ideally a clickable screenshot. Since
`style` is stripped, whatever signals "clickable" must live in the image's own pixels or
in the link text. (2026-08-30; the Pages workflow exists at
`.github/workflows/pages-drive-report.yml`, dormant until Pages is enabled.)

### Step 2 — Extract anything language-agnostic

Before translating, ask: *"Would the zh-HK and zh-CN translations of this section be identical to the English, character for character?"* If yes, it belongs in a shared file linked from all three READMEs. Current examples: `ROUTES.md` (all Japanese line names), anywhere you'd list raw file paths / diagram codes.

Don't extract prose that *happens* to be similar — only content that has no natural-language component.

### Step 3 — Translate zh-HK, then zh-CN

Mirror the English section order, heading count, and table shape one-for-one. Show the user terminology choices before writing if anything is new (see preferences below).

### Step 4 — Sanity check

- Each file's top link bar references the other two languages + the same shared docs.
- Section order identical across all three.
- Download asset names / version numbers match.
- No language-specific content accidentally living in a single file (e.g. a zh-HK note about HK railway conventions that doesn't exist in en/zh-CN).

## Chinese phrasing preferences (learned)

The user is in HK, writes both scripts fluently, and has strong preferences about natural phrasing. Apply these without re-asking:

### 1. Don't literal-translate — write native Chinese

**Bad:** `每個站都需要你手動按 Page Down 才會發生` (literal EN→ZH, reads as awkward construction)

**Good:** `播放廣播、切換到下一站都需要人手按 Page Down`

Rule: if a Chinese sentence reads like a grammar-corrected English sentence, rewrite it. Chinese prefers concrete actions over abstract "happens" / "occurs". Use verb-first construction, drop subjects when implicit.

### 2. "The app" — use 程式 / 程序, not 模擬器 / 模拟器

Talking about program BEHAVIOR (runs, waits, doesn't auto-advance) → `程式` (zh-HK) / `程序` (zh-CN). Reserve `模擬器` / `模拟器` for the project *name/identity* (title, elevator pitch).

**Bad:** `模擬器不會自動執行`

**Good:** `程式不會自動跳去下一站`

### 3. User POV, not developer POV

Strip technical terms users don't know. "PA track" → "announcement" → `廣播`. "Countdown" → drop unless user asks.

### 4. Yellow square + before-arrival phrasing

The yellow-square hint is framed as "play them before arriving at the station", not "play them all or they get skipped" (they don't get skipped; the sim stays stuck — but the narrative framing is about pacing, not about consequences).

- zh-HK: `請在到站之前按 Page Down 播完所有廣播。`
- zh-CN: `请在到站之前按 Page Down 播完所有广播。`

### 5. HK-specific word choices

- "按鍵" for keys (not "按键" — wait, that's zh-CN; HK uses 按鍵)
- "人手按" is natural HK/Cantonese-influenced phrasing for "manually press"; fine to use in zh-HK only
- "班次" for a train diagram/service (HK railway term); zh-CN uses "车次"

### 6. Punctuation — zh-HK is full-width

zh-HK strings use full-width punctuation — comma is `，` (U+FF0C), NOT half-width `,`. Applies to app-chrome i18n (`data/translations_app.json`) as well as the READMEs. **Don't bulk-convert zh-CN**: asked 2026-07-11 whether to switch both or zh-HK only, the user chose **zh-HK only** — leave zh-CN as authored.

### 7. TIMS / IRL-mirroring chrome — zh-HK may hug the Japanese kanji

For TIMS-console chrome that mirrors real IRL Japanese labels (the C07AA summary-table field labels, screen headings), the zh-HK translation may stay CLOSE to the source Japanese kanji — HK readers handle the kanji, and hugging the source preserves the console fidelity. zh-CN still gets proper Simplified. Convert JP-only chars (`駅`→`站`); keep shared kanji as-is (`路線名` / `列車種別` / `始發・終着站`). Action VERBS use native Chinese, NOT the Japanese kanji form: `啟動` / `启动` (start), never `起動`. 2026-07-11: TIMS summary-table labels localized (chose the (b) "zh-hk can stick close to JP terms" option) + OCR launch-cluster verbs corrected to "proper chinese". Distinct from #1 (native-Chinese-not-literal-EN) — this is a deliberate carve-out for JP-mirroring console chrome, where staying near the kanji is the goal.

## Terminology baseline

Keep this list updated whenever a new term is coined. Translate once, reuse everywhere.

| Concept | English | zh-HK | zh-CN |
|---|---|---|---|
| departure melody | departure melody | 發車音樂 | 发车音乐 |
| PA announcement | announcement | 廣播 | 广播 |
| closing-door announcement | closing-door announcement | 關門廣播 | 关门广播 |
| diagram (train service) | diagram | 班次 | 车次 |
| line / route | line | 路線 | 线路 |
| interchange station | interchange station | 轉車站 | 换乘站 |
| yellow square (UI) | yellow square | 黃色方格 | 黄色方块 |
| Page Down action description | Next PA announcement / advance to next stop | 下一則廣播／前往下一站 | 下一段广播／前往下一站 |
| quit | quit | 離開 | 退出 |
| series (E233-0 etc.) | series | 番台 | 番台 |
| the app (behavior) | the simulation / the sim | 程式 | 程序 |
| the project (title) | simulator | 模擬器 | 模拟器 |
| transfer station code | 3-letter Roman code | 3 個英文字母的車站代碼 | 3 个字母的车站代码 |
| setup screen | setup screen | 選擇畫面 | 选择界面 |
| 5-station view (LCD) | 5-station view | 5 站顯示 | 5 站显示 |
| Supported Routes (top-bar label) | Supported Routes | 對應路線 | 支持的路线 |
| Planned Features (section heading) | Planned Features | 計劃中的功能 | 计划中的功能 |
| Credits (section heading) | Credits | 鳴謝 | 鸣谢 |
| line symbol / operator logo | line symbol, operator logo | 路線標誌、營運商標誌 | 线路标志、运营商标志 |
| icon (UI asset) | icon | 圖示 | 图标 |

## Things to NOT do

- **Don't** translate section headings inconsistently across releases. If `## Download` was `## 下載` last release, it stays `## 下載` — don't drift to `## 下載方式` for no reason.
- **Don't** expand one language's section and leave the others behind. A discrepancy is worse than a uniform but slightly-stale translation.
- **Don't** translate filenames, keybindings (`Page Down` stays `Page Down`), or code-block content.
- **Don't** add Japanese furigana / pinyin annotations unless the user asks. The terminology table decisions stand.
- **Don't** touch `ROUTES.md` as part of routine README updates. It changes when a route is added/removed/renamed — that's a separate, data-driven edit.
- **Don't** re-prompt for terminology already in the table above. If the user introduces a new term, add it to the table in the same session.
