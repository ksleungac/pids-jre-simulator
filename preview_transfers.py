"""Standalone preview for the transfer-info display element.

Renders the transfer block for a given station onto a lower-LCD-sized surface,
saved to PNG. Used to iterate the layout against the IRL reference photo at
`lcd_references/transfer_tokyo.png`.

Usage:
    uv run preview_transfers.py [--station 東京] [--out _visual_iter/v2.png]
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

SCALE_SUFFIX_RE = re.compile(r"\.scale\(([0-9]*\.?[0-9]+)\)$")

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

W, H = 730, 303
BG_COLOR = (255, 255, 255)
TEXT_COLOR = (0, 0, 0)


def project_root() -> Path:
    return Path(__file__).resolve().parent


def load_icon(slug: str, target_h: int, cache: dict) -> pygame.Surface:
    key = (slug, target_h)
    if key in cache:
        return cache[key]
    path = project_root() / "data" / "line_icons" / f"{slug}.png"
    img = pygame.image.load(str(path)).convert_alpha()
    sw, sh = img.get_size()
    target_w = int(round(sw * (target_h / sh)))
    scaled = pygame.transform.smoothscale(img, (target_w, target_h))
    cache[key] = scaled
    return scaled


def resolve_entry(slug_ref: str, lines: dict) -> dict:
    """Resolve 'slug', 'slug.variant', or '...scale(N)' to effective entry dict.

    Variant fields override base fields; missing fields inherit from base.
    Dot-notation is one-level only for variants — `slug.variant.subvariant`
    is invalid. A trailing `.scale(N)` modifier (parsed first) overrides
    `name_ja_compress` for this reference only; default is 1.0 if neither
    suffix nor any inherited field provides one.
    Fails loud (KeyError) on missing base or unknown variant; per
    `critical_lessons.md` § runtime-required artifacts, silent fallback on
    missing data hides bugs at the worst time.
    """
    scale_override = None
    m = SCALE_SUFFIX_RE.search(slug_ref)
    if m:
        scale_override = float(m.group(1))
        slug_ref = slug_ref[: m.start()]

    if "." in slug_ref:
        base_slug, variant_name = slug_ref.split(".", 1)
        if "." in variant_name:
            raise ValueError(f"Dot-notation is one level only; got '{slug_ref}'")
        if base_slug not in lines:
            raise KeyError(
                f"Base slug '{base_slug}' not in lines.json (referenced as '{slug_ref}')"
            )
        base = lines[base_slug]
        variants = base.get("variants", {})
        if variant_name not in variants:
            raise KeyError(
                f"Variant '{variant_name}' not under '{base_slug}' (referenced as '{slug_ref}')"
            )
        merged = {k: v for k, v in base.items() if k != "variants"}
        merged.update(variants[variant_name])
    else:
        if slug_ref not in lines:
            raise KeyError(f"Slug '{slug_ref}' not in lines.json")
        merged = {k: v for k, v in lines[slug_ref].items() if k != "variants"}

    if scale_override is not None:
        merged["name_ja_compress"] = scale_override
    return merged


def render_mixed(text: str, latin_font, cjk_font, color, latin_fallback=None, kern=True):
    """Render text with per-codepoint Latin/CJK font dispatch.

    Latin codepoints route to `latin_font`; if that font lacks the glyph
    (e.g. Frutiger LT Std doesn't carry macron chars ō/ū/ī from Latin
    Extended-A) AND `latin_fallback` is provided, the fallback handles
    those chars only. Anything beyond Latin (incl U+30FB ・) routes to
    `cjk_font`. Surfaces concatenated horizontally, baseline-aligned via
    per-font ascent.

    `kern=True` groups consecutive same-font chars into segments so the
    font's pair-kerning applies. `kern=False` renders each codepoint
    individually so no kerning fires (each char gets its natural advance)
    — useful when the font's kerning is overly aggressive.
    """
    if not text:
        return latin_font.render("", True, color)

    def font_for(ch):
        if ord(ch) < 0x180:  # Latin range
            if latin_fallback is not None and latin_font.metrics(ch)[0] is None:
                return latin_fallback
            return latin_font
        return cjk_font

    runs = []  # list of (segment, font)
    if kern:
        cur_seg = ""
        cur_font = None
        for ch in text:
            f = font_for(ch)
            if cur_font is None or f is cur_font:
                cur_seg += ch
                cur_font = f
            else:
                runs.append((cur_seg, cur_font))
                cur_seg = ch
                cur_font = f
        runs.append((cur_seg, cur_font))
    else:
        # One char per run → font.render() has no neighbour to kern against.
        runs = [(ch, font_for(ch)) for ch in text]

    surfs = [f.render(s, True, color) for s, f in runs]
    max_ascent = max(f.get_ascent() for _, f in runs)
    total_w = sum(s.get_width() for s in surfs)
    # `max_ascent + max_descent` is smaller than `font.get_height()` (which
    # includes internal leading) — using the smaller value clips glyph
    # descenders. Use the actual source surface height instead.
    h = max(s.get_height() for s in surfs)

    out = pygame.Surface((total_w, h), pygame.SRCALPHA)
    x = 0
    for (_, f), s in zip(runs, surfs):
        out.blit(s, (x, max_ascent - f.get_ascent()))
        x += s.get_width()
    return out


def render_transfer(surf: pygame.Surface, transfers: list, lines: dict, debug: bool = False):
    def _dprint(*args, **kwargs):
        if debug:
            print(*args, **kwargs)

    # --- Tuneable params (adjust freely) ---
    margin_x_factor = 1.6          # Side margin = N × badge_h (user spec: 1.6 badge widths)
    single_row_side_pad_divisor = 14  # Single-row equal-spacing: side_pad = (W − Σ) / divisor. Sparse rows get more side_pad; crowded rows → true equal-spacing.

    banner_size_ja = 16            # JA size (user spec: 16+ px)
    banner_size_en = 18            # EN size (user spec 2026-05-04)
    banner_h_padding = 3           # Extra px around tallest banner text — tuned 2026-05-04 for banner_h=25
    banner_text_gap_factor = 1.0   # Gap between JA and EN = N × JA em width (user spec: ~1)
    banner_bg_color = (230, 230, 230)  # PASSED_COLOR — same dim as past-station route bar
    banner_text_color = TEXT_COLOR     # Same black as body text
    banner_to_body_gap = 10

    # Per-N text scaling (calibrated 2026-05-04 from IRL refs):
    # - Dense (N≥10 OR both shinkansen present): 1.375 × banner_size_ja → 22
    # - Mid (N=6-9): 1.6 × banner_size_ja → 26
    # - N=5: 1.8 × banner_size_ja → 29
    # - Sparse (N≤4): 2.0 × banner_size_ja → 32
    # IRL data points: Tokyo JO (9 lines, both shink) = 1.32x, Ueno JY_inner (7 lines) = 1.5x.
    # "Both shinkansen" rule overrides N (treats Tokyo-like density signal).
    _resolved = [resolve_entry(ref, lines) for ref in transfers]
    _shinkansen_count = sum(1 for e in _resolved if e.get("category") == "shinkansen")
    _N = len(transfers)
    if _N >= 10 or _shinkansen_count >= 2:
        name_size_ja = 22  # 1.375× banner JA
    elif _N >= 6:
        name_size_ja = 26  # 1.6× banner JA
    elif _N == 5:
        name_size_ja = 29  # 1.8× banner JA
    else:
        name_size_ja = 32  # 2.0× banner JA
    # EN scales proportionally with JA (baseline ratio 12/23 from pre-scaling settings).
    # → JA=22 → EN=11; JA=26 → EN=14; JA=29 → EN=15; JA=32 → EN=17.
    name_size_en = round(name_size_ja * 12 / 23)
    # name_line_gap scales with EN size: larger EN → more negative (closer to JA visually).
    # Formula: -4 (baseline at EN=12) − (EN − 12). → EN=11→-3, EN=14→-6, EN=15→-7, EN=17→-9.
    name_line_gap = -4 - (name_size_en - 12)
    badge_text_gap = 3             # Gap between badge group and JA/EN text (user spec: 3 px IRL)
    inter_badge_gap = 2

    inter_row_gap_factor = 1.0     # Multiples of badge_h
    max_rows = 3                   # IRL PIDS max 3 rows of transfers

    # Body is vertically centered between banner-bottom and canvas-bottom,
    # but bottom gap is `bottom_extra` px taller than top gap (user spec: 5-10 px).
    bottom_extra = 7
    # ----------------------------------------

    fonts_dir = project_root() / "fonts"
    font_ja = pygame.font.Font(str(fonts_dir / "ShinGoPr6N-Medium.otf"), name_size_ja)
    font_en = pygame.font.Font(str(fonts_dir / "NeueFrutigerWorld-Bold.otf"), name_size_en)
    font_en_macron = font_en  # NeueFrutigerWorld has macron support natively
    font_en_cjk = pygame.font.Font(str(fonts_dir / "ShinGoPr6N-Medium.otf"), name_size_en)
    font_banner_ja = pygame.font.Font(str(fonts_dir / "ShinGoPr6N-Medium.otf"), banner_size_ja)
    font_banner_en = pygame.font.Font(str(fonts_dir / "HelveticaNeue-Medium.otf"), banner_size_en)
    banner_text_gap = int(round(font_banner_ja.size("国")[0] * banner_text_gap_factor))

    # Badge dimension = 1.1 × JA text size (user spec). Square badges (square sources).
    badge_h = int(round(1.1 * font_ja.get_height()))
    inter_row_gap = int(badge_h * inter_row_gap_factor)
    margin_x = int(badge_h * margin_x_factor)
    # Banner height = tallest banner text rendered surface height + 2 × padding.
    # Using get_height() (not get_ascent()) so the surfaces actually fit and JA
    # vertical-centering is accurate.
    banner_h = max(font_banner_ja.get_height(), font_banner_en.get_height()) + 2 * banner_h_padding

    icon_cache: dict = {}

    def get_badges(entry: dict):
        return entry.get("badges") or [{"icon": "_universal"}]

    dot_side_pad = 1               # Extra px on each side of each `·` (user spec)

    def compact_dots(text: str) -> str:
        # IRL JR PIDS renders the JIS middle dot with much tighter side-bearings
        # than ShinGo/Helvetica's default U+30FB. Substitute U+00B7 (Middle Dot,
        # Latin block) at render time — narrower glyph, same visual semantic,
        # both fonts carry it. Keep U+30FB in JSON for data correctness.
        return text.replace("・", "·")

    def render_with_dot_pad(text: str, render_fn):
        """Render text, adding `dot_side_pad` px on each side of every `·`."""
        if "·" not in text:
            return render_fn(text)
        parts = text.split("·")
        part_surfs = [render_fn(p) for p in parts]
        dot_surf = render_fn("·")
        n_dots = len(parts) - 1
        total_w = sum(s.get_width() for s in part_surfs) + n_dots * (
            dot_surf.get_width() + 2 * dot_side_pad
        )
        max_h = max(s.get_height() for s in part_surfs + [dot_surf])
        out = pygame.Surface((total_w, max_h), pygame.SRCALPHA)
        x = 0
        for i, s in enumerate(part_surfs):
            out.blit(s, (x, 0))
            x += s.get_width()
            if i < n_dots:
                x += dot_side_pad
                out.blit(dot_surf, (x, 0))
                x += dot_surf.get_width() + dot_side_pad
        return out

    def render_ja(text: str, compress: float = 1.0):
        text = compact_dots(text)
        surf = render_with_dot_pad(text, lambda s: font_ja.render(s, True, TEXT_COLOR))
        if compress != 1.0 and surf.get_width() > 0:
            new_w = max(1, int(round(surf.get_width() * compress)))
            surf = pygame.transform.smoothscale(surf, (new_w, surf.get_height()))
        return surf

    def render_en(text: str):
        # `・` substituted to `·` upstream. Render char-by-char (kern=False) to
        # avoid NeueFrutigerWorld's aggressive Y-a / Y-o / T-ō pair-kerning.
        text = compact_dots(text)
        return render_with_dot_pad(
            text,
            lambda s: render_mixed(s, font_en, font_en_cjk, TEXT_COLOR, latin_fallback=font_en_macron, kern=False),
        )

    def measure_entry(entry: dict) -> int:
        """Full entry width = badges + gap + max(JA, EN) text. Drives both
        positioning and overlap checks — text from one entry must not
        reach into the next entry's badge."""
        badges = get_badges(entry)
        bw = sum(load_icon(b["icon"], badge_h, icon_cache).get_width() for b in badges)
        if len(badges) > 1:
            bw += (len(badges) - 1) * inter_badge_gap
        ja_w = render_ja(entry["name_ja"], entry.get("name_ja_compress", 1.0)).get_width()
        en_w = render_en(entry["name_en"]).get_width()
        return bw + badge_text_gap + max(ja_w, en_w)

    def draw_entry(entry: dict, x: int, y: int) -> int:
        """Layout: badge top-aligned with JA text top (same height); EN text
        sits below the badge bottom edge ("underhang"). Entry total height
        = badge_h + name_line_gap + en_h."""
        badges = get_badges(entry)
        bx = x
        for i, b in enumerate(badges):
            icon = load_icon(b["icon"], badge_h, icon_cache)
            surf.blit(icon, (bx, y))
            bx += icon.get_width()
            if i < len(badges) - 1:
                bx += inter_badge_gap

        text_x = bx + badge_text_gap
        ja_surf = render_ja(entry["name_ja"], entry.get("name_ja_compress", 1.0))
        en_surf = render_en(entry["name_en"])

        # JA top-aligned with badge top
        surf.blit(ja_surf, (text_x, y))
        # EN below the badge bottom (underhang)
        surf.blit(en_surf, (text_x, y + badge_h + name_line_gap))

        return text_x + max(ja_surf.get_width(), en_surf.get_width())

    # Order entries: shinkansen → jr_east → non_jr, preserving array order within each.
    # Categories don't force a row break — entries can flow into a shared row
    # when there's space (matches IRL: row 3 in Tokyo reference mixes JT/JE jr_east
    # with 丸ノ内線 non_jr).
    cat_order = {"shinkansen": 0, "jr_east": 1, "non_jr": 2}
    ordered_entries = sorted(
        ((slug_ref, resolve_entry(slug_ref, lines)) for slug_ref in transfers),
        key=lambda se: cat_order.get(se[1].get("category", "non_jr"), 99),
    )

    surf.fill(BG_COLOR)

    # Top banner: full-width dim-gray bar with normal-black "のりかえ案内　Transfer".
    # Bottom-aligned with 3 px margin from banner bottom (per user spec).
    pygame.draw.rect(surf, banner_bg_color, pygame.Rect(0, 0, W, banner_h))
    banner_ja = font_banner_ja.render("のりかえ案内", True, banner_text_color)
    banner_en = font_banner_en.render("Transfer", True, banner_text_color)
    banner_total_w = banner_ja.get_width() + banner_text_gap + banner_en.get_width()
    banner_x = (W - banner_total_w) // 2
    # Center JA rendered surface vertically in the banner band.
    # EN bottom-aligned to a fixed margin from banner bottom.
    banner_en_bottom_margin = 1
    ja_blit_y = (banner_h - banner_ja.get_height()) // 2
    en_blit_y = banner_h - banner_en_bottom_margin - banner_en.get_height()
    surf.blit(banner_ja, (banner_x, ja_blit_y))
    surf.blit(
        banner_en,
        (banner_x + banner_ja.get_width() + banner_text_gap, en_blit_y),
    )

    # Entry total vertical extent = badge_h + name_line_gap + en text height
    entry_h = badge_h + name_line_gap + font_en.get_height()

    # --- Layout pass: compute (entry, x, y_rel) for every entry without drawing.
    # Per-rule comments inline below; canonical narrative in WIP_transfer_display.md.

    positions = []  # list of (entry, x, y_rel)
    right_edge_canvas = W - margin_x

    # Step 1: group entries into rows via capped lex-maximin row-grouping.
    # CONTRACT: among splits respecting category-sorted order (no within-category
    # reorder) and max_rows cap, pick by sort-key:
    #   1. capped lex-maximin: each row's gap clamped to `gap_cap`, padded to
    #      max_rows length with `gap_cap`, sorted ascending. Larger tuple wins.
    #   2. -num_rows: when capped tuples tie, prefer fewer rows (avoids the
    #      "few small entries spread across separate rows" regression).
    #   3. uncapped lex-maximin: when above tie, the most-spread split wins.
    # Per-row gap formula (h):
    #   - n=1: h = (W - sum) / 2 (single-entry side margin).
    #   - n>=2 equal-spacing case (when (W - sum)/(n+1) >= margin_x):
    #       h = (W - sum) / (n + 1)  (sides == inters)
    #   - n>=2 stretch case (sides bottom out at margin_x):
    #       h = (W - 2*margin_x - sum) / (n - 1)
    # `gap_cap = 2 * margin_x`: beyond this, more whitespace is wasted canvas.
    # See WIP_transfer_display.md § "Open follow-ups" for derivation.
    from itertools import combinations
    entries_seq = [e for _, e in ordered_entries]
    widths_seq = [measure_entry(e) for e in entries_seq]
    N_total = len(entries_seq)
    gap_cap = 2 * margin_x

    def row_gap(widths_sum: float, n: int) -> float:
        if n <= 0:
            return float("inf")
        if n == 1:
            return (W - widths_sum) / 2
        h_equal = (W - widths_sum) / (n + 1)
        if h_equal >= margin_x:
            return h_equal
        return (W - 2 * margin_x - widths_sum) / (n - 1)

    best_counts = None
    best_key = None
    grouping_candidates: list = []  # (counts, key, row_sums, gaps) for debug
    for num_rows in range(1, max_rows + 1):
        if num_rows > N_total:
            break
        for splits in combinations(range(1, N_total), num_rows - 1) if num_rows > 1 else [()]:
            counts = []
            prev = 0
            for s in splits:
                counts.append(s - prev)
                prev = s
            counts.append(N_total - prev)
            row_sums = []
            idx = 0
            for c in counts:
                row_sums.append(sum(widths_seq[idx:idx + c]))
                idx += c
            gaps = [row_gap(row_sums[i], counts[i]) for i in range(len(counts))]
            if any(g < 0 for g in gaps):
                continue  # row physically overflows
            capped = [min(g, gap_cap) for g in gaps] + [gap_cap] * (max_rows - num_rows)
            # Top-heaviness tiebreaker: count (i, j) pairs with i < j AND
            # row_sums[i] < row_sums[j] (a Σ-inversion). Fewer inversions =
            # heavier rows toward the top. Negated so larger key wins.
            inversions = sum(
                1
                for i in range(len(row_sums))
                for j in range(i + 1, len(row_sums))
                if row_sums[i] < row_sums[j]
            )
            key = (tuple(sorted(capped)), -num_rows, -inversions, tuple(sorted(gaps)))
            grouping_candidates.append((tuple(counts), key, tuple(row_sums), tuple(gaps)))
            if best_key is None or key > best_key:
                best_key = key
                best_counts = counts

    rows = []
    if best_counts is not None:
        idx = 0
        for c in best_counts:
            rows.append(entries_seq[idx:idx + c])
            idx += c
    else:
        # Fallback: pack max_rows greedily even if overflowing — shouldn't happen
        # on real data; kept defensive.
        per = max(1, (N_total + max_rows - 1) // max_rows)
        for i in range(0, N_total, per):
            rows.append(entries_seq[i:i + per])
        rows = rows[:max_rows]

    if debug:
        _dprint("\n=== layout debug ===")
        _dprint(f"canvas: W={W}  margin_x={margin_x}  gap_cap={gap_cap}")
        names_widths = [(e.get("name_ja", "?"), measure_entry(e)) for e in entries_seq]
        _dprint(f"entries: {N_total}  total_w={sum(widths_seq)}")
        for i, (nm, w) in enumerate(names_widths):
            _dprint(f"  [{i}] {nm}  w={w}")
        _dprint(f"\n--- grouping candidates (top 6 by sort key, ✓ = chosen) ---")
        sorted_cands = sorted(grouping_candidates, key=lambda c: c[1], reverse=True)
        for counts, key, row_sums, gaps in sorted_cands[:6]:
            mark = "✓" if list(counts) == best_counts else " "
            gaps_fmt = tuple(round(g, 1) for g in gaps)
            capped_fmt = tuple(round(c, 1) for c in key[0])
            _dprint(
                f"  {mark} shape={counts}  Σ_per_row={row_sums}  "
                f"gaps={gaps_fmt}  capped_sorted={capped_fmt}  -nrows={key[1]}"
            )

    # Step 2: per-row positioning, threading anchors row-to-row.

    def distribute_middles(left_x, right_x, mid_widths):
        """Place mid entries between left_x (start cursor) and right_x (must
        end before this) with equal whitespace gaps both sides + between.
        Returns list of x positions, or None if any gap < 0."""
        n_mid = len(mid_widths)
        if n_mid == 0:
            return []
        span = right_x - left_x
        sum_w = sum(mid_widths)
        n_gaps = n_mid + 1
        gap = (span - sum_w) / n_gaps
        if gap < 0:
            return None
        xs = []
        cursor = left_x + gap
        for w in mid_widths:
            xs.append(int(round(cursor)))
            cursor += w + gap
        return xs

    def check_no_overlap(xs, widths):
        """Full-width check: previous entry's text right edge must not reach
        into the next entry's badge. Required because the next entry's badge
        sitting on top of trailing text from the prior entry would render
        unreadably."""
        for k in range(1, len(xs)):
            if xs[k - 1] + widths[k - 1] > xs[k]:
                return False
        return True

    # Blueprint enhancement: proactively widen margin_x for row 0 based on the
    # narrowest-gap row (= the row with max Σ). This compensates for cases where
    # cascade succeeds via Rule 1/2/3 but the result would be cramped (e.g. sparse
    # rows clustering left against a wider lower row). Rule 4 + track-back
    # remains the reactive backup if a row genuinely dies during cascade.
    rows_widths_pre = [[measure_entry(e) for e in row] for row in rows]
    row_sums_pre = [sum(rw) for rw in rows_widths_pre]
    row_h_required = [
        (W - row_sums_pre[i]) / (len(rows[i]) + 1)
        for i in range(len(rows))
    ]
    h_narrowest = min(row_h_required) if row_h_required else float("inf")
    effective_margin_x = max(margin_x, int(round(h_narrowest)))
    blueprint_widened = effective_margin_x > margin_x

    row_anchors_list: list = []
    row_widths_list: list = []
    row_rights_list: list = []
    iter_order = list(range(len(rows)))

    if debug:
        _dprint(f"\n--- blueprint (margin-only widening) ---")
        h_fmt = [round(h, 2) for h in row_h_required]
        _dprint(f"row sums: {row_sums_pre}  h_per_row: {h_fmt}")
        _dprint(f"h_narrowest = min(h) = {h_narrowest:.2f}  (row {row_h_required.index(min(row_h_required))})")
        _dprint(f"effective_margin_x = max({margin_x}, {int(round(h_narrowest))}) = {effective_margin_x}  widened={blueprint_widened}")
        _dprint(f"\n--- row layout (iter order: {iter_order}) ---")

    for r_idx in iter_order:
        row = rows[r_idx]
        widths = rows_widths_pre[r_idx]
        n = len(row)
        chosen_xs = None
        right_edge_canvas = W - effective_margin_x
        rule_taken: str = "?"

        # Standard top-down cascade: row 0 is the seed; every other row anchors
        # against the row directly above.
        is_seed_row = (r_idx == 0)
        if not is_seed_row:
            upper_anchors = row_anchors_list[r_idx - 1]

        if debug:
            role = "seed (row 0)" if is_seed_row else f"cascade vs row {r_idx - 1}"
            _dprint(f"\n[row {r_idx}] {role}  N={n}  widths={widths}  Σ={sum(widths)}")
            if not is_seed_row:
                _dprint(f"  upper_anchors={upper_anchors}  M={len(upper_anchors)}")

        if is_seed_row:
            # Row 0 (standard mode) has no upper row.
            # Single-row layout (len(rows) == 1): try equal-spacing first
            # (sides == inters == h_equal) when h_equal >= margin_x. Multi-row
            # row 0 skips this path so subsequent rows can column-align via
            # upper anchors at margin_x / right_edge_canvas.
            if len(rows) == 1:
                sum_w = sum(widths)
                h_equal = (W - sum_w) / (n + 1)
                if h_equal >= margin_x:
                    if n == 1:
                        side_gap = h_equal
                        inter_gap = 0
                        rule_taken = f"row 0 single-row n=1 (h_equal={h_equal:.1f})"
                    else:
                        side_pad = max(0, (W - sum_w) / single_row_side_pad_divisor)
                        side_gap = h_equal + side_pad
                        inter_gap = h_equal - 2 * side_pad / (n - 1)
                        rule_taken = f"row 0 single-row equal-spacing (h_equal={h_equal:.1f}, side_pad={side_pad:.1f})"
                    chosen_xs = []
                    cursor = side_gap
                    for k in range(n):
                        chosen_xs.append(int(round(cursor)))
                        cursor += widths[k] + inter_gap
            if chosen_xs is None:
                # head/tail/distribute (stretch). Uses effective_margin_x so
                # blueprint widening propagates to the seed row from the start.
                if n == 1:
                    chosen_xs = [effective_margin_x]
                    rule_taken = f"row 0 multi-row n=1 at effective_margin_x={effective_margin_x}"
                else:
                    head_x = effective_margin_x
                    tail_x = right_edge_canvas - widths[-1]
                    mid_xs = distribute_middles(head_x + widths[0], tail_x, widths[1:-1])
                    if mid_xs is not None:
                        attempt = [head_x] + mid_xs + [tail_x]
                        if check_no_overlap(attempt, widths):
                            chosen_xs = attempt
                            rule_taken = "row 0 multi-row head/tail/distribute"
        else:
            m = len(upper_anchors)

            # Rule 1 — per-entry left-to-right sweep with asymmetric
            # predecessor-intrusion check + canvas-fit defensive check.
            rule1_xs: list = []
            first_failed = n
            if n <= m:
                for k in range(n):
                    a = upper_anchors[k]
                    if k > 0:
                        prev_right = rule1_xs[-1] + widths[k - 1]
                        if prev_right > a:
                            first_failed = k
                            break
                        if a + widths[k] > right_edge_canvas:
                            first_failed = k
                            break
                    rule1_xs.append(a)
            else:
                rule1_xs.append(upper_anchors[0])
                first_failed = 1

            if first_failed == n:
                chosen_xs = rule1_xs
                rule_taken = f"Rule 1 success (N={n} ≤ M={m}, all {n} anchors fit)"
            else:
                # Rule 2 — head + tail + distribute, leftmost-fit tail.
                # Tracks predecessor_clean_seen to distinguish two failure modes:
                #   Case A: at least one cand passed predecessor check but
                #           failed canvas (tail overflows). → Rule 3 canvas-right.
                #   Case B: every cand failed predecessor (no usable anchor at
                #           all). → skip Rule 3, fall to Rule 4 equal-spacing.
                # The distinction matters because Rule 4's track-back is the
                # right widener for case B, but would visually misalign for case A
                # (and conversely canvas-right Rule 3 floats the tail too far
                # right in case B — the Shinagawa Tokaido pathology).
                f = first_failed
                head_right = rule1_xs[f - 1] + widths[f - 1]
                middle_widths = widths[f:n - 1]
                tail_w = widths[n - 1]
                tail_anchor = None
                tail_anchor_idx = -1
                tail_mid_xs: list = []
                predecessor_clean_seen = False
                for cand_i, cand in enumerate(upper_anchors):
                    if middle_widths:
                        mid_xs = distribute_middles(head_right, cand, middle_widths)
                        if mid_xs is None:
                            continue  # predecessor intrusion (middles can't fit)
                    else:
                        if head_right > cand:
                            continue  # predecessor intrusion (head intrudes)
                        mid_xs = []
                    predecessor_clean_seen = True
                    if cand + tail_w > right_edge_canvas:
                        continue  # canvas overflow (anchor usable, tail too wide)
                    tail_anchor = cand
                    tail_anchor_idx = cand_i
                    tail_mid_xs = mid_xs
                    break

                if tail_anchor is not None:
                    chosen_xs = rule1_xs + tail_mid_xs + [tail_anchor]
                    if n > m:
                        rule_taken = f"Rule 2 (N>M case: N={n}>M={m}; tail at upper[{tail_anchor_idx}]={tail_anchor})"
                    else:
                        rule_taken = f"Rule 1 partial (failed at k={f}) + Rule 2 (tail at upper[{tail_anchor_idx}]={tail_anchor})"
                elif predecessor_clean_seen:
                    # Case A — canvas-right Rule 3. An anchor existed where the
                    # predecessor didn't intrude, but the tail overflowed canvas
                    # at it. Drop the column-anchor constraint; align tail's
                    # right edge to the canvas right margin (W − effective_margin_x).
                    right_edge_target = W - effective_margin_x
                    tail_x = right_edge_target - tail_w
                    if middle_widths:
                        mid_xs = distribute_middles(head_right, tail_x, middle_widths)
                        if mid_xs is None:
                            tail_x = None
                    else:
                        if head_right > tail_x:
                            tail_x = None
                        mid_xs = []
                    if tail_x is not None:
                        chosen_xs = rule1_xs + mid_xs + [tail_x]
                        rule_taken = f"Case A → Rule 3 canvas-right (target={right_edge_target}, tail_x={tail_x})"
                # else: Case B — no predecessor-clean anchor. Skip Rule 3
                # entirely; fall through to Rule 4 equal-spacing + track-back.

        # Rule 4 — equal-spacing fallback. Tracks back earlier rows by delta
        # so they align to the new (wider) effective margin.
        if chosen_xs is None and not is_seed_row:
            h = (W - sum(widths)) / (n + 1)
            if h >= margin_x:
                cursor = h
                rule4_xs = []
                for kk in range(n):
                    rule4_xs.append(int(round(cursor)))
                    cursor += widths[kk] + h
                chosen_xs = rule4_xs
                # Track back: shift previously placed rows by delta.
                delta = int(round(h)) - effective_margin_x
                rule_taken = f"Rule 4 equal-spacing (h={h:.2f}; track-back delta={delta})"
                if delta != 0:
                    pos_cursor = 0
                    for i in range(r_idx):
                        prev_anchors = row_anchors_list[i]
                        new_anchors = [x + delta for x in prev_anchors]
                        row_anchors_list[i] = new_anchors
                        row_rights_list[i] = [
                            new_anchors[k] + row_widths_list[i][k]
                            for k in range(len(new_anchors))
                        ]
                        for k in range(len(new_anchors)):
                            e, _, y = positions[pos_cursor + k]
                            positions[pos_cursor + k] = (e, new_anchors[k], y)
                        pos_cursor += len(new_anchors)
                effective_margin_x = int(round(h))

        if chosen_xs is None:
            # Last-ditch — pack from margin.
            chosen_xs = [effective_margin_x]
            for kk in range(1, n):
                chosen_xs.append(chosen_xs[-1] + widths[kk - 1])
            rule_taken = "Last-ditch (pack from margin)"

        if debug:
            left_gap = chosen_xs[0]
            right_gap = W - (chosen_xs[-1] + widths[-1])
            inter_gaps = [chosen_xs[k + 1] - (chosen_xs[k] + widths[k]) for k in range(n - 1)]
            _dprint(f"  rule: {rule_taken}")
            _dprint(f"  → chosen_xs={chosen_xs}")
            _dprint(f"  gaps:  L={left_gap}  inter={inter_gaps}  R={right_gap}")

        row_anchors_list.append(chosen_xs)
        row_widths_list.append(widths)
        row_rights_list.append([chosen_xs[k] + widths[k] for k in range(n)])
        row_y = r_idx * (entry_h + inter_row_gap)
        for k in range(n):
            positions.append((row[k], chosen_xs[k], row_y))

    # Content vertical extent (bottom edge of last entry)
    content_h = (max(p[2] for p in positions) + entry_h) if positions else 0

    # --- Vertical centering with bottom_extra:
    # canvas below banner has H - banner_h px available.
    # top_gap + content_h + bottom_gap = available_for_body
    # bottom_gap = top_gap + bottom_extra  →  top_gap = (avail - content - extra) / 2
    avail = H - banner_h
    top_gap = max(banner_to_body_gap, (avail - content_h - bottom_extra) // 2)
    body_y_start = banner_h + top_gap

    # --- Draw pass
    for entry, x, y_rel in positions:
        draw_entry(entry, x, body_y_start + y_rel)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--station", default="東京")
    parser.add_argument("--out", default="_visual_iter/v2_transfer.png")
    parser.add_argument(
        "--filter-line",
        default="",
        help="Simulate active-line filter — drop transfers whose badges include this code "
        "(matches audio behavior: on a JT/JU train, audio skips JT/JU/Ueno-Tōkyō entirely, "
        "so UT's [JT, JU] compound also gets filtered). "
        "Pass e.g. 'JO' to mimic the IRL reference photo (taken on a JO train).",
    )
    parser.add_argument(
        "--view",
        default="",
        help="Apply per-view drops from station's transfers_by_view[<view>] map. "
        "Format: '<line>_<direction>' e.g. 'JY_inner'. Combines with --filter-line. "
        "Drop matches by base slug name, so a `drop: ['keihin_tohoku']` entry "
        "drops both plain `keihin_tohoku` and any `keihin_tohoku.<variant>` references.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Render only first N transfers (post-filter). 0 = no limit. Use for testing "
        "raw drawing logic with a small input — e.g. --limit 2 → just the shinkansen pair.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print structured layout trace: per-entry widths, grouping candidates, "
        "blueprint state, per-row rule taken, chosen xs, and gaps.",
    )
    args = parser.parse_args()

    if args.debug:
        # CJK strings in debug output crash cp1252 stdout on Windows.
        try:
            sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass

    pygame.init()
    pygame.display.set_mode((1, 1))  # required by convert_alpha() under SDL dummy
    surf = pygame.Surface((W, H))

    root = project_root()
    lines = json.loads((root / "data" / "lines.json").read_text(encoding="utf-8"))
    stations = json.loads((root / "data" / "stations.json").read_text(encoding="utf-8"))

    if args.station not in stations:
        print(f"Station {args.station!r} not in stations.json")
        return 1
    transfers = stations[args.station].get("transfers", [])
    if not transfers:
        print(f"Station {args.station!r} has no 'transfers' field")
        return 1

    if args.filter_line:
        active = args.filter_line
        transfers = [
            slug_ref for slug_ref in transfers
            if not any(
                b.get("code") == active
                for b in resolve_entry(slug_ref, lines).get("badges", [])
            )
        ]
        print(f"Filter active line {active!r}: {len(transfers)} transfers remain")

    if args.view:
        station_data = stations[args.station]
        view_map = station_data.get("transfers_by_view", {})
        view_ops = view_map.get(args.view, {})
        view_dropset = set(view_ops.get("drop", []))
        view_editmap = view_ops.get("edit", {})
        if view_dropset:
            before = len(transfers)
            transfers = [
                slug_ref for slug_ref in transfers
                if slug_ref.split(".", 1)[0] not in view_dropset
            ]
            print(
                f"View {args.view!r} drops {before - len(transfers)} entries: "
                f"{sorted(view_dropset)}"
            )
        if view_editmap:
            edited = []
            edit_count = 0
            for slug_ref in transfers:
                base = slug_ref.split(".", 1)[0]
                if base in view_editmap:
                    edited.append(view_editmap[base])
                    edit_count += 1
                else:
                    edited.append(slug_ref)
            transfers = edited
            print(
                f"View {args.view!r} edits {edit_count} entries: "
                f"{view_editmap}"
            )
        if not view_dropset and not view_editmap:
            print(f"View {args.view!r}: no ops defined (or view-key absent)")

    if args.limit > 0:
        transfers = transfers[: args.limit]
        print(f"Limit to first {args.limit}: {transfers}")

    render_transfer(surf, transfers, lines, debug=args.debug)

    out_path = root / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(surf, str(out_path))
    print(f"Saved to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
