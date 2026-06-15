"""E235-1000 transfer-info display (concrete).

Renders the resolved transfer list onto the lower LCD area
(S_WIDTH × (S_HEIGHT − UPPER_HEIGHT) = 730 × 303), positioned right
below the upper LCD.

Module-level helpers (``load_icon``, ``render_mixed``, ``render_transfer``)
are exposed so the dev-tooling CLI ``preview_transfers.py`` can render
into a standalone surface for visual iteration without instantiating
the class. ``resolve_entry`` is the parent's responsibility — see
``displays/transfer_info.py``.
"""

from typing import List, Optional

import pygame

from displays.train_models.e235_1000 import S_WIDTH, S_HEIGHT, UPPER_HEIGHT
from displays.transfer_info import (
    TransferInfoDisplay as _BaseTransferInfoDisplay,
    resolve_entry,
)
from app_paths import project_root

# Canvas width for the transfer-info body (lower-LCD region). Height is read
# per-render from the actual subsurface (render_transfer uses surf.get_height())
# so it adapts to each model's UPPER_HEIGHT.
W = S_WIDTH
BG_COLOR = (255, 255, 255)
TEXT_COLOR = (0, 0, 0)


# Module-level font cache — render_transfer is called per frame, so creating
# pygame.font.Font objects every call (one per N-tier × language × variant)
# burns measurable CPU. Cache by (path_str, size) — N-tier scaling means the
# same path is requested at multiple sizes, but always the same set per session.
_FONT_CACHE: dict = {}


def _font(filename: str, size: int) -> pygame.font.Font:
    key = (filename, size)
    cached = _FONT_CACHE.get(key)
    if cached is not None:
        return cached
    f = pygame.font.Font(str(project_root() / "fonts" / filename), size)
    _FONT_CACHE[key] = f
    return f


def load_icon(slug: str, target_h: int, cache: dict) -> pygame.Surface:
    key = (slug, target_h)
    if key in cache:
        return cache[key]
    path = project_root() / "data" / "line_icons" / f"{slug}.png"
    if not path.exists():
        # Fail loud per critical_lessons.md § "Runtime-required materials must be committed".
        raise FileNotFoundError(f"line_icon asset missing: {path} (slug={slug!r}). " f"Drop a PNG at that path or fix the badge slug in lines.json.")
    img = pygame.image.load(str(path)).convert_alpha()
    sw, sh = img.get_size()
    target_w = int(round(sw * (target_h / sh)))
    scaled = pygame.transform.smoothscale(img, (target_w, target_h))
    cache[key] = scaled
    return scaled


def render_mixed(text: str, latin_font, cjk_font, color, latin_fallback=None, kern=True):
    """Render text with per-codepoint Latin/CJK font dispatch.

    Latin codepoints route to ``latin_font``; if that font lacks the glyph
    (e.g. Frutiger LT Std doesn't carry macron chars ō/ū/ī from Latin
    Extended-A) AND ``latin_fallback`` is provided, the fallback handles
    those chars only. Anything beyond Latin (incl U+30FB ・) routes to
    ``cjk_font``. Surfaces concatenated horizontally, baseline-aligned via
    per-font ascent.

    ``kern=True`` groups consecutive same-font chars into segments so the
    font's pair-kerning applies. ``kern=False`` renders each codepoint
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
    h = max(s.get_height() for s in surfs)

    out = pygame.Surface((total_w, h), pygame.SRCALPHA)
    x = 0
    for (_, f), s in zip(runs, surfs):
        out.blit(s, (x, max_ascent - f.get_ascent()))
        x += s.get_width()
    return out


def render_transfer(
    surf: pygame.Surface,
    transfers: list,
    lines: dict,
    debug: bool = False,
    rows_override: Optional[list] = None,
):
    """Render the transfer-info frame onto ``surf`` (W × H).

    Pure procedural renderer — no class state. Same signature as the
    standalone preview, so ``preview_transfers.py`` can call it directly
    against a freshly-allocated surface.
    """

    # CONTRACT: Pipeline = scaling → row-grouping → blueprint → Rules 1-4 + track-back.
    # See DISPLAY_E235.md § "Transfer Info" for definitions + worked examples.
    # Tuning lives in the params block below — adjust named constants, not the IRL math.
    def _dprint(*args, **kwargs):
        if debug:
            print(*args, **kwargs)

    # fmt: off
    # --- Tuneable params (adjust freely) ---
    margin_x_factor = 1.6          # Side margin = N × badge_h (user spec: 1.6 badge widths)
    inter_element_margin_ratio = 0.7  # Greedy walk comfort TARGET: predecessor inter-spacing = ratio × margin_x. < 1.0 → "cramped-centered" look.
    min_inter_gap_ratio = 0.5      # Cascade Rule 2/3 absolute FLOOR: distribute_middles rejects gap < ratio × margin_x. Lower than inter_element_margin_ratio because cascade has anchor structure (column-aligned tighter spacing is visually OK).
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
    # Resolve each slug exactly once — reused below for category-sort + measure cache.
    resolved_pairs = [(ref, resolve_entry(ref, lines)) for ref in transfers]
    _shinkansen_count = sum(1 for _, e in resolved_pairs if e.get("category") == "shinkansen")
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
    name_size_en = round(name_size_ja * 12 / 23)
    # name_line_gap scales with EN size: larger EN → more negative (closer to JA visually).
    name_line_gap = -4 - (name_size_en - 12)
    badge_text_gap = 3             # Gap between badge group and JA/EN text (user spec: 3 px IRL)
    inter_badge_gap = 2

    inter_row_gap_factor = 1.0     # Multiples of badge_h
    max_rows = 3                   # IRL PIDS max 3 rows of transfers

    # IRL JR PIDS renders the JIS middle dot with much tighter side-bearings
    # than ShinGo/Helvetica's default U+30FB. Substitute U+00B7 (Middle Dot,
    # Latin block) at render time + add `dot_side_pad` px on each side (user spec).
    dot_side_pad = 1

    # Body is vertically centered between banner-bottom and canvas-bottom,
    # but bottom gap is `bottom_extra` px taller than top gap (user spec: 5-10 px).
    bottom_extra = 7
    # ----------------------------------------
    # fmt: on

    font_ja = _font("ShinGoPr6N-Medium.otf", name_size_ja)
    font_en = _font("NeueFrutigerWorld-Bold.otf", name_size_en)
    font_en_cjk = _font("ShinGoPr6N-Medium.otf", name_size_en)
    font_banner_ja = _font("ShinGoPr6N-Medium.otf", banner_size_ja)
    font_banner_en = _font("HelveticaNeue-Medium.otf", banner_size_en)
    banner_text_gap = int(round(font_banner_ja.size("国")[0] * banner_text_gap_factor))

    # Badge dimension = 1.1 × JA text size (user spec). Square badges (square sources).
    badge_h = int(round(1.1 * font_ja.get_height()))
    inter_row_gap = int(badge_h * inter_row_gap_factor)
    margin_x = int(badge_h * margin_x_factor)
    inter_element_margin = int(round(margin_x * inter_element_margin_ratio))
    min_inter_gap = int(round(margin_x * min_inter_gap_ratio))
    banner_h = max(font_banner_ja.get_height(), font_banner_en.get_height()) + 2 * banner_h_padding

    icon_cache: dict = {}

    def get_badges(entry: dict):
        return entry.get("badges") or [{"icon": "_universal"}]

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
        total_w = sum(s.get_width() for s in part_surfs) + n_dots * (dot_surf.get_width() + 2 * dot_side_pad)
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
        s = render_with_dot_pad(text, lambda t: font_ja.render(t, True, TEXT_COLOR))
        if compress != 1.0 and s.get_width() > 0:
            new_w = max(1, int(round(s.get_width() * compress)))
            s = pygame.transform.smoothscale(s, (new_w, s.get_height()))
        return s

    def render_en(text: str):
        # `・` substituted to `·` upstream. Render char-by-char (kern=False) to
        # avoid NeueFrutigerWorld's aggressive Y-a / Y-o / T-ō pair-kerning.
        text = compact_dots(text)
        return render_with_dot_pad(
            text,
            # NeueFrutigerWorld carries macron support natively → no fallback needed.
            lambda t: render_mixed(t, font_en, font_en_cjk, TEXT_COLOR, latin_fallback=None, kern=False),
        )

    def is_color_square(b: dict) -> bool:
        # E235-1000 policy: universal-icon line with a `color` field renders
        # as a solid color square instead of the universal icon.
        return b["icon"] == "_universal" and b.get("color") is not None

    def badge_width(b: dict) -> int:
        if is_color_square(b):
            return badge_h
        return load_icon(b["icon"], badge_h, icon_cache).get_width()

    def measure_entry(entry: dict) -> int:
        """Full entry width = badges + gap + max(JA, EN) text. Drives both
        positioning and overlap checks — text from one entry must not
        reach into the next entry's badge."""
        badges = get_badges(entry)
        bw = sum(badge_width(b) for b in badges)
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
            if is_color_square(b):
                pygame.draw.rect(surf, pygame.Color(*b["color"]), (bx, y, badge_h, badge_h))
                bx += badge_h
            else:
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
        resolved_pairs,
        key=lambda se: cat_order.get(se[1].get("category", "non_jr"), 99),
    )

    surf.fill(BG_COLOR)

    # Top banner: full-width dim-gray bar with normal-black "のりかえ案内　Transfer".
    pygame.draw.rect(surf, banner_bg_color, pygame.Rect(0, 0, W, banner_h))
    banner_ja = font_banner_ja.render("のりかえ案内", True, banner_text_color)
    banner_en = font_banner_en.render("Transfer", True, banner_text_color)
    banner_total_w = banner_ja.get_width() + banner_text_gap + banner_en.get_width()
    banner_x = (W - banner_total_w) // 2
    banner_en_bottom_margin = 1
    ja_blit_y = (banner_h - banner_ja.get_height()) // 2
    en_blit_y = banner_h - banner_en_bottom_margin - banner_en.get_height()
    surf.blit(banner_ja, (banner_x, ja_blit_y))
    surf.blit(
        banner_en,
        (banner_x + banner_ja.get_width() + banner_text_gap, en_blit_y),
    )

    entry_h = badge_h + name_line_gap + font_en.get_height()

    positions = []  # list of (entry, x, y_rel)
    right_edge_canvas = W - margin_x

    def distribute_middles(left_x, right_x, mid_widths, min_gap=0):
        """Place mid entries between left_x (start cursor) and right_x with
        equal whitespace gaps both sides + between. Returns list of x positions,
        or None if any gap < min_gap.

        Real render passes min_gap=0 (only rejects negative — physical overlap).
        Dry-run cascade passes min_gap=inter_element_margin (rejects too-tight
        spacing that would over-pack rows beyond the comfort threshold)."""
        n_mid = len(mid_widths)
        if n_mid == 0:
            return []
        span = right_x - left_x
        sum_w = sum(mid_widths)
        n_gaps = n_mid + 1
        gap = (span - sum_w) / n_gaps
        if gap < min_gap:
            return None
        xs = []
        cursor = left_x + gap
        for w in mid_widths:
            xs.append(int(round(cursor)))
            cursor += w + gap
        return xs

    def check_no_overlap(xs, widths):
        for k in range(1, len(xs)):
            if xs[k - 1] + widths[k - 1] > xs[k]:
                return False
        return True

    entries_seq = [e for _, e in ordered_entries]
    # measure_entry allocates pygame surfaces per call; cache by entry identity
    # so debug + dry_run + per-row recomputation don't re-render text just to
    # read widths (lower-LCD redraws every frame).
    _width_cache: dict = {}

    def width_of(entry: dict) -> int:
        wid = _width_cache.get(id(entry))
        if wid is None:
            wid = measure_entry(entry)
            _width_cache[id(entry)] = wid
        return wid

    widths_seq = [width_of(e) for e in entries_seq]
    N_total = len(entries_seq)

    right_edge_canvas_provisional = W - margin_x

    def cascade_test(widths, upper_anchors):
        """Pure-test variant of Rules 1/2/3 placement (no Rule 4).
        Returns chosen_xs on success, None on Case B / unrecoverable canvas overflow.
        """
        n = len(widths)
        m = len(upper_anchors)
        rec = right_edge_canvas_provisional

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
                    if a + widths[k] > rec:
                        first_failed = k
                        break
                rule1_xs.append(a)
        else:
            rule1_xs.append(upper_anchors[0])
            first_failed = 1

        if first_failed == n:
            return rule1_xs

        f = first_failed
        head_right = rule1_xs[f - 1] + widths[f - 1]
        middle_widths = widths[f : n - 1]
        tail_w = widths[n - 1]
        predecessor_clean_seen = False
        tail_anchor = None
        tail_mid_xs: list = []
        for cand in upper_anchors:
            if middle_widths:
                mid_xs = distribute_middles(head_right, cand, middle_widths, min_gap=min_inter_gap)
                if mid_xs is None:
                    continue
            else:
                if cand - head_right < min_inter_gap:
                    continue
                mid_xs = []
            predecessor_clean_seen = True
            if cand + tail_w > rec:
                continue
            tail_anchor = cand
            tail_mid_xs = mid_xs
            break

        if tail_anchor is not None:
            return rule1_xs + tail_mid_xs + [tail_anchor]

        if predecessor_clean_seen:
            tail_x = rec - tail_w
            if middle_widths:
                mid_xs = distribute_middles(head_right, tail_x, middle_widths, min_gap=min_inter_gap)
                if mid_xs is None:
                    return None
            else:
                if tail_x - head_right < min_inter_gap:
                    return None
                mid_xs = []
            if tail_x - head_right < min_inter_gap:
                return None
            return rule1_xs + mid_xs + [tail_x]

        return None

    def compute_row0_provisional(row_widths):
        """Edge-pin row 0 positions for dry-run upper-anchor purposes only."""
        n = len(row_widths)
        if n == 0:
            return []
        if n == 1:
            return [margin_x]
        head_x = margin_x
        tail_x = W - margin_x - row_widths[-1]
        if n == 2:
            return [head_x, tail_x]
        mid_xs = distribute_middles(head_x + row_widths[0], tail_x, row_widths[1:-1])
        if mid_xs is None:
            h = (W - sum(row_widths)) / (n + 1)
            cursor = h
            xs = []
            for w in row_widths:
                xs.append(int(round(cursor)))
                cursor += w + h
            return xs
        return [head_x] + mid_xs + [tail_x]

    def dry_run_cascade():
        """GOLDEN-rule row grouping. Returns (rows, debug_trace)."""
        trace: list = []
        if N_total == 0:
            return [], trace

        rows_out: list = []
        rows_xs_out: list = []

        if rows_override is not None:
            if sum(rows_override) != N_total:
                trace.append(
                    f"⚠ rows_override {rows_override} sums to {sum(rows_override)} " f"but N_total={N_total}; ignored, falling back to algorithm"
                )
            else:
                cursor_idx = 0
                for r_idx, n in enumerate(rows_override):
                    row_entries = list(entries_seq[cursor_idx : cursor_idx + n])
                    row_widths = list(widths_seq[cursor_idx : cursor_idx + n])
                    if r_idx == 0:
                        row_xs = compute_row0_provisional(row_widths)
                    else:
                        row_xs = cascade_test(row_widths, rows_xs_out[-1])
                        if row_xs is None:
                            row_xs = []
                            cur = margin_x
                            for w in row_widths:
                                row_xs.append(int(cur))
                                cur += w + inter_element_margin
                    rows_out.append(row_entries)
                    rows_xs_out.append(row_xs)
                    cursor_idx += n
                trace.append(f"rows override applied: {rows_override}")
                return rows_out, trace

        shinkansen_prefix = 0
        for i, e in enumerate(entries_seq):
            if e.get("category") == "shinkansen":
                shinkansen_prefix = i + 1
            else:
                break

        if shinkansen_prefix > 0:
            r0_entries = entries_seq[:shinkansen_prefix]
            r0_widths = widths_seq[:shinkansen_prefix]
            r0_xs = compute_row0_provisional(r0_widths)
            rows_out.append(r0_entries)
            rows_xs_out.append(r0_xs)
            trace.append(f"row 0 = {shinkansen_prefix} shinkansen (no greedy walk)")
            remaining_idx = shinkansen_prefix
        elif N_total == 2:
            if sum(widths_seq) <= W - 2 * margin_x:
                r0_entries = list(entries_seq[:2])
                r0_widths = list(widths_seq[:2])
                r0_xs = compute_row0_provisional(r0_widths)
                trace.append("row 0 = N=2 structural: both fit → (2,)")
                remaining_idx = 2
            else:
                r0_entries = [entries_seq[0]]
                r0_widths = [widths_seq[0]]
                r0_xs = compute_row0_provisional(r0_widths)
                trace.append("row 0 = N=2 structural: don't fit → (1,1)")
                remaining_idx = 1
            rows_out.append(r0_entries)
            rows_xs_out.append(r0_xs)
        elif N_total == 3:
            r0_entries = list(entries_seq[:2])
            r0_widths = list(widths_seq[:2])
            r0_xs = compute_row0_provisional(r0_widths)
            rows_out.append(r0_entries)
            rows_xs_out.append(r0_xs)
            trace.append("row 0 = N=3 structural: (2,1) — first 2 on row 0")
            remaining_idx = 2
        else:
            r0_entries: list = []
            r0_widths: list = []
            r0_xs: list = []
            cursor = margin_x
            for i in range(N_total):
                w = widths_seq[i]
                if not r0_entries:
                    r0_entries.append(entries_seq[i])
                    r0_widths.append(w)
                    r0_xs.append(cursor)
                    cursor = cursor + w + inter_element_margin
                else:
                    if cursor + w > right_edge_canvas_provisional:
                        break
                    r0_entries.append(entries_seq[i])
                    r0_widths.append(w)
                    r0_xs.append(cursor)
                    cursor = cursor + w + inter_element_margin
            rows_out.append(r0_entries)
            rows_xs_out.append(r0_xs)
            trace.append(f"row 0 = greedy walk → {len(r0_entries)} entries (xs={r0_xs})")
            remaining_idx = len(r0_entries)

        cur_entries: list = []
        cur_widths: list = []
        cur_xs: list = []
        upper_anchors = rows_xs_out[-1]

        def close_current_row():
            nonlocal cur_entries, cur_widths, cur_xs, upper_anchors
            if cur_entries:
                rows_out.append(cur_entries)
                rows_xs_out.append(cur_xs)
                upper_anchors = cur_xs
                cur_entries = []
                cur_widths = []
                cur_xs = []

        for i in range(remaining_idx, N_total):
            entry = entries_seq[i]
            w = widths_seq[i]

            trial_widths = cur_widths + [w]
            cascade_xs = cascade_test(trial_widths, upper_anchors)

            if cascade_xs is not None:
                cur_entries.append(entry)
                cur_widths.append(w)
                cur_xs = cascade_xs
                trace.append(f"  entry [{i}] cascade ✓ on row {len(rows_out)} (xs={cascade_xs})")
                continue

            if cur_entries:
                pred_right = cur_xs[-1] + cur_widths[-1]
                new_x = pred_right + inter_element_margin
                if new_x + w <= right_edge_canvas_provisional:
                    cur_entries.append(entry)
                    cur_widths.append(w)
                    cur_xs = cur_xs + [int(round(new_x))]
                    trace.append(f"  entry [{i}] greedy ✓ on row {len(rows_out)} (provisional x={int(round(new_x))})")
                    continue

            if cur_entries and len(rows_out) + 1 >= max_rows:
                cur_entries.append(entry)
                cur_widths.append(w)
                pred_right = cur_xs[-1] + cur_widths[-2]
                cur_xs.append(int(round(pred_right + inter_element_margin)))
                trace.append(f"  entry [{i}] force-pack on row {len(rows_out)} (max_rows cap)")
                continue

            close_current_row()
            cur_entries = [entry]
            cur_widths = [w]
            single_xs = cascade_test([w], upper_anchors)
            cur_xs = single_xs if single_xs is not None else [margin_x]
            trace.append(f"  entry [{i}] opens row {len(rows_out)} (provisional x={cur_xs[0]})")

        close_current_row()
        return rows_out, trace

    rows, dry_run_trace = dry_run_cascade()

    if debug:
        _dprint("\n=== layout debug ===")
        _dprint(f"canvas: W={W}  margin_x={margin_x}  inter_element_margin={inter_element_margin}")
        names_widths = [(e.get("name_ja", "?"), width_of(e)) for e in entries_seq]
        _dprint(f"entries: {N_total}  total_w={sum(widths_seq)}")
        for i, (nm, w) in enumerate(names_widths):
            _dprint(f"  [{i}] {nm}  w={w}")
        _dprint(f"\n--- dry-run cascade trace ---")
        for line in dry_run_trace:
            _dprint(line)
        _dprint(f"\nfinal rows: {[len(r) for r in rows]}")

    rows_widths_pre = [[width_of(e) for e in row] for row in rows]
    row_sums_pre = [sum(rw) for rw in rows_widths_pre]
    row_h_required = [(W - row_sums_pre[i]) / (len(rows[i]) + 1) for i in range(len(rows))]
    h_narrowest = min(row_h_required) if row_h_required else float("inf")
    effective_margin_x = max(margin_x, int(round(h_narrowest)))
    blueprint_widened = effective_margin_x > margin_x

    row_anchors_list: list = []

    anchor_row_idx = 0
    if rows and rows[0] and all(e.get("category") == "shinkansen" for e in rows[0]):
        if len(rows[0]) == 1:
            anchor_row_idx = 1
        else:
            anchor_row_idx = -1

    column_aware_xs = None
    column_aware_M = 0
    column_aware_col_max_widths: list = []
    col_slack = 0
    if anchor_row_idx >= 0 and anchor_row_idx < len(rows) and len(rows) - anchor_row_idx >= 2:
        non_shink_rows_widths = rows_widths_pre[anchor_row_idx:]
        column_aware_M = max(len(rw) for rw in non_shink_rows_widths)
        column_aware_col_max_widths = []
        for k in range(column_aware_M):
            in_col = [rw[k] for rw in non_shink_rows_widths if k < len(rw)]
            column_aware_col_max_widths.append(max(in_col))
        col_x_packed = [effective_margin_x]
        for k in range(1, column_aware_M):
            col_x_packed.append(col_x_packed[k - 1] + column_aware_col_max_widths[k - 1])
        last_right_packed = col_x_packed[column_aware_M - 1] + column_aware_col_max_widths[column_aware_M - 1]
        col_slack = (W - effective_margin_x) - last_right_packed
        if col_slack >= 0:
            col_x_final = [col_x_packed[0]]
            if column_aware_M >= 2:
                for k in range(1, column_aware_M):
                    col_x_final.append(int(round(col_x_packed[k] + col_slack * k / (column_aware_M - 1))))
            n_anchor = len(rows[anchor_row_idx])
            column_aware_xs = col_x_final[:n_anchor]

    if debug:
        _dprint(f"\n--- blueprint (margin-only widening) ---")
        h_fmt = [round(h, 2) for h in row_h_required]
        _dprint(f"row sums: {row_sums_pre}  h_per_row: {h_fmt}")
        _dprint(f"h_narrowest = min(h) = {h_narrowest:.2f}  (row {row_h_required.index(min(row_h_required))})")
        _dprint(f"effective_margin_x = max({margin_x}, {int(round(h_narrowest))}) = {effective_margin_x}  widened={blueprint_widened}")
        _dprint(f"\n--- column-aware anchor placement ---")
        _dprint(f"anchor_row_idx={anchor_row_idx}  M={column_aware_M}  col_max_widths={column_aware_col_max_widths}")
        if column_aware_xs is not None:
            _dprint(f"col_slack={col_slack}  → anchor row xs={column_aware_xs}")
        else:
            _dprint(f"column-aware not applied (single-row layout, single anchor row, or slack<0)")
        _dprint(f"\n--- row layout ---")

    for r_idx in range(len(rows)):
        row = rows[r_idx]
        widths = rows_widths_pre[r_idx]
        n = len(row)
        chosen_xs = None
        right_edge_canvas = W - effective_margin_x
        rule_taken: str = "?"

        is_seed_row = r_idx == 0
        is_anchor_row = r_idx == anchor_row_idx and column_aware_xs is not None
        upper_anchors: list = []
        if not is_seed_row:
            upper_anchors = row_anchors_list[r_idx - 1]

        if debug:
            role = "seed (row 0)" if is_seed_row else f"cascade vs row {r_idx - 1}"
            if is_anchor_row:
                role = f"anchor row (column-aware), {role}"
            _dprint(f"\n[row {r_idx}] {role}  N={n}  widths={widths}  Σ={sum(widths)}")
            if not is_seed_row:
                _dprint(f"  upper_anchors={upper_anchors}  M={len(upper_anchors)}")

        if is_anchor_row:
            chosen_xs = list(column_aware_xs)
            rule_taken = f"column-aware anchor row (col_x={column_aware_xs})"
        elif is_seed_row:
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
                elif h_equal >= min_inter_gap:
                    side_gap = h_equal
                    inter_gap = h_equal
                    rule_taken = f"row 0 single-row tight equal-spacing (h_equal={h_equal:.1f}, no side_pad)"
                    chosen_xs = []
                    cursor = side_gap
                    for k in range(n):
                        chosen_xs.append(int(round(cursor)))
                        cursor += widths[k] + inter_gap
            if chosen_xs is None:
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
                f = first_failed
                head_right = rule1_xs[f - 1] + widths[f - 1]
                middle_widths = widths[f : n - 1]
                tail_w = widths[n - 1]
                tail_anchor = None
                tail_anchor_idx = -1
                tail_mid_xs: list = []
                predecessor_clean_seen = False
                for cand_i, cand in enumerate(upper_anchors):
                    if middle_widths:
                        mid_xs = distribute_middles(head_right, cand, middle_widths)
                        if mid_xs is None:
                            continue
                    else:
                        if head_right > cand:
                            continue
                        mid_xs = []
                    predecessor_clean_seen = True
                    if cand + tail_w > right_edge_canvas:
                        continue
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

        if chosen_xs is None and not is_seed_row:
            h = (W - sum(widths)) / (n + 1)
            if h >= margin_x:
                cursor = h
                rule4_xs = []
                for kk in range(n):
                    rule4_xs.append(int(round(cursor)))
                    cursor += widths[kk] + h
                chosen_xs = rule4_xs
                delta = int(round(h)) - effective_margin_x
                rule_taken = f"Rule 4 equal-spacing (h={h:.2f}; track-back delta={delta})"
                if delta != 0:
                    pos_cursor = 0
                    for i in range(r_idx):
                        prev_anchors = row_anchors_list[i]
                        new_anchors = [x + delta for x in prev_anchors]
                        row_anchors_list[i] = new_anchors
                        for k in range(len(new_anchors)):
                            e, _, y = positions[pos_cursor + k]
                            positions[pos_cursor + k] = (e, new_anchors[k], y)
                        pos_cursor += len(new_anchors)
                effective_margin_x = int(round(h))

        if chosen_xs is None:
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
        row_y = r_idx * (entry_h + inter_row_gap)
        for k in range(n):
            positions.append((row[k], chosen_xs[k], row_y))

    content_h = (max(p[2] for p in positions) + entry_h) if positions else 0

    avail = surf.get_height() - banner_h
    top_gap = max(banner_to_body_gap, (avail - content_h - bottom_extra) // 2)
    body_y_start = banner_h + top_gap

    for entry, x, y_rel in positions:
        draw_entry(entry, x, body_y_start + y_rel)


class TransferInfoDisplay(_BaseTransferInfoDisplay):
    """E235-1000-specific transfer-info renderer."""

    def __init__(self, screen, route_data, stops, upper_height=UPPER_HEIGHT):
        super().__init__(screen, route_data, stops)
        # Upper-LCD height for the ACTIVE model — drives the lower-LCD subsurface
        # top. Defaults to e235_1000's UPPER_HEIGHT (117); e235_0 overrides to its
        # own (130) so the transfer slot's lower region aligns with the full-route
        # and 5-station slots (otherwise the upper LCD looks 13px shorter here).
        self.upper_height = upper_height

    def _render(self, transfers: List[str], current_time: float) -> None:
        del current_time  # not used yet — animations may consume it later

        lower_h = S_HEIGHT - self.upper_height
        sub = self.screen.subsurface(pygame.Rect(0, self.upper_height, S_WIDTH, lower_h))

        # render_transfer's blueprint algorithm calls max() on derived row
        # sums — an empty transfers list crashes it. Bail early with a blank
        # white fill (matches lower-LCD WHITE_BG); the cycle still rotates
        # past this slot.
        if not transfers:
            sub.fill((255, 255, 255))
            return

        render_transfer(sub, transfers, self.lines)
