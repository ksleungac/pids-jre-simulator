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
| `README.zh-HK.md` | Traditional Chinese (HK) | Mirror of English structure. |
| `README.zh-CN.md` | Simplified Chinese (Mainland) | Mirror of English structure. |
| `ROUTES.md` | Shared | Language-agnostic (Japanese line names + diagram codes work for all three reader audiences). Linked from each README's top bar. |

**Top link bar** on every README lists the *other two* languages + the shared doc:
```
**[English](README.md)** · **[繁體中文](README.zh-HK.md)** · **[對應路線](ROUTES.md)**
```
- The current language is NOT linked from its own bar (avoid self-link).
- The `ROUTES.md` label is translated (`Supported Routes` / `對應路線` / `支持的路线`) — the label is localized, the target file is shared.

## Workflow

### Step 1 — Update English first

All changes land in `README.md` first. Discuss wording with the user; get it to "happy with this" before translating. The current English README's section order — **Download → Usage → Planned Features** — is the canonical shape; don't invent new sections unless the user asks.

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
| Supported Routes (top-bar label) | Supported Routes | 對應路線 | 支持的路线 |
| Planned Features (section heading) | Planned Features | 計劃中的功能 | 计划中的功能 |

## Things to NOT do

- **Don't** translate section headings inconsistently across releases. If `## Download` was `## 下載` last release, it stays `## 下載` — don't drift to `## 下載方式` for no reason.
- **Don't** expand one language's section and leave the others behind. A discrepancy is worse than a uniform but slightly-stale translation.
- **Don't** translate filenames, keybindings (`Page Down` stays `Page Down`), or code-block content.
- **Don't** add Japanese furigana / pinyin annotations unless the user asks. The terminology table decisions stand.
- **Don't** touch `ROUTES.md` as part of routine README updates. It changes when a route is added/removed/renamed — that's a separate, data-driven edit.
- **Don't** re-prompt for terminology already in the table above. If the user introduces a new term, add it to the table in the same session.
