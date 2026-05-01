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
from pathlib import Path

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


def render_transfer(surf: pygame.Surface, transfers: list, lines: dict):
    # --- Tuneable params (adjust freely) ---
    margin_x_factor = 1.6          # Side margin = N × badge_h (user spec: 1.6 badge widths)

    banner_size_ja = 16            # JA size (user spec: 16+ px)
    banner_size_en = 21            # EN size (user spec: +2 from 14)
    banner_h_padding = 4           # Extra px around tallest banner text
    banner_text_gap_factor = 1.0   # Gap between JA and EN = N × JA em width (user spec: ~1)
    banner_bg_color = (230, 230, 230)  # PASSED_COLOR — same dim as past-station route bar
    banner_text_color = TEXT_COLOR     # Same black as body text
    banner_to_body_gap = 10

    name_size_ja = 23
    name_size_en = 12
    name_line_gap = -4             # Gap between badge bottom and EN text top (negative = overlap)
    ja_compress_factor = 0.90      # Horizontal compression for entries with > 7 chars
    ja_compress_factor_short = 0.75  # More aggressive compression for 7-char entries
    ja_compress_threshold = 6      # Only compress JA when char count > this
    ja_compress_short_max = 7      # Up to this length uses the more-aggressive factor
    badge_text_gap = 3             # Gap between badge group and JA/EN text (user spec: 3 px IRL)
    inter_badge_gap = 2

    inter_row_gap_factor = 1.0     # Multiples of badge_h
    max_entries_per_row = 4        # IRL PIDS caps at 4 entries per row
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

    def render_ja(text: str):
        natural_len = len(text)
        text = compact_dots(text)
        surf = render_with_dot_pad(text, lambda s: font_ja.render(s, True, TEXT_COLOR))
        # Two-tier compression: 7-char entries (e.g. 上野東京ライン) get a more
        # aggressive squeeze; longer entries (shinkansens) get a gentler one.
        # Short names (≤ threshold) stay natural width.
        if natural_len > ja_compress_threshold and surf.get_width() > 0:
            if natural_len <= ja_compress_short_max:
                factor = ja_compress_factor_short
            else:
                factor = ja_compress_factor
            new_w = max(1, int(round(surf.get_width() * factor)))
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
        ja_w = render_ja(entry["name_ja"]).get_width()
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
        ja_surf = render_ja(entry["name_ja"])
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
        ((slug, lines[slug]) for slug in transfers),
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
    # Row-grouping (independent of positioning): natural-flow with
    # max_entries_per_row=4, max_rows=3, shinkansen row-fenced.

    positions = []  # list of (entry, x, y_rel)
    right_edge_canvas = W - margin_x

    # Step 1: group entries into rows.
    rows = []  # list of [entry, ...]
    cur_row: list = []
    prev_category = None
    for _, entry in ordered_entries:
        cur_category = entry.get("category", "non_jr")
        wrap_for_count = len(cur_row) >= max_entries_per_row
        wrap_for_shinkansen_fence = (
            prev_category == "shinkansen" and cur_category != "shinkansen"
        ) or (
            prev_category not in (None, "shinkansen") and cur_category == "shinkansen"
        )
        if cur_row and (wrap_for_count or wrap_for_shinkansen_fence):
            rows.append(cur_row)
            cur_row = []
            if len(rows) >= max_rows:
                break
        cur_row.append(entry)
        prev_category = cur_category
    if cur_row and len(rows) < max_rows:
        rows.append(cur_row)
    rows = rows[:max_rows]

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

    row_anchors_list: list = []  # per-row chosen left-edge x's
    row_widths_list: list = []   # per-row entry widths
    row_rights_list: list = []   # per-row right-edges (x + width)

    for r_idx, row in enumerate(rows):
        widths = [measure_entry(e) for e in row]
        n = len(row)
        chosen_xs = None

        if r_idx == 0:
            # Row 0 has no upper row to anchor against. First entry at margin,
            # last right-edge-anchored, middles distribute.
            if n == 1:
                chosen_xs = [margin_x]
            else:
                head_x = margin_x
                tail_x = right_edge_canvas - widths[-1]
                mid_xs = distribute_middles(head_x + widths[0], tail_x, widths[1:-1])
                if mid_xs is not None:
                    attempt = [head_x] + mid_xs + [tail_x]
                    if check_no_overlap(attempt, widths):
                        chosen_xs = attempt
        else:
            upper_anchors = row_anchors_list[r_idx - 1]
            m = len(upper_anchors)

            # Rule 1 — per-entry left-to-right sweep with asymmetric
            # predecessor-intrusion check. Only fires when N ≤ M. Entry k
            # anchors at upper[k] iff its predecessor's right edge ≤ upper[k].
            # Successful entries stay anchored even if a later entry fails —
            # failure is per-entry, not row-wide. The first failure stops
            # the sweep; remaining entries fall to Rule 2 as a segment.
            #
            # When N > M, Rule 1 doesn't fire at all. Entry 0 is anchored at
            # upper[0] to start Rule 2's segment from index 1; Rule 2 then
            # places middles[1..N-2] + tail[N-1] via head+tail+distribute.
            rule1_xs: list = []
            first_failed = n  # sentinel: no failure
            if n <= m:
                for k in range(n):
                    a = upper_anchors[k]
                    if k == 0:
                        rule1_xs.append(a)
                    else:
                        prev_right = rule1_xs[-1] + widths[k - 1]
                        if prev_right > a:
                            first_failed = k
                            break
                        rule1_xs.append(a)
            else:
                # N > M: anchor entry 0 at upper[0], Rule 2 handles the rest.
                rule1_xs.append(upper_anchors[0])
                first_failed = 1

            if first_failed == n:
                # All entries placed cleanly under Rule 1.
                chosen_xs = rule1_xs
            else:
                # Rule 2 — head + tail + distribute, applied to the failed
                # segment [first_failed..n-1]. Head's right edge is the last
                # Rule-1-successful entry's right edge (NOT row's first entry).
                # Tail iterates upper anchors leftmost-first, picks the
                # leftmost where (a) middles fit between head_right and the
                # candidate (or — when no middles — head_right ≤ candidate),
                # AND (b) candidate + tail_w fits canvas. If no candidate
                # works → Rule 3.
                f = first_failed
                head_right = rule1_xs[f - 1] + widths[f - 1]
                middle_widths = widths[f:n - 1]
                tail_w = widths[n - 1]
                tail_anchor = None
                tail_mid_xs: list = []
                for cand in upper_anchors:
                    if middle_widths:
                        mid_xs = distribute_middles(head_right, cand, middle_widths)
                        if mid_xs is None:
                            continue
                    else:
                        if head_right > cand:
                            continue
                        mid_xs = []
                    if cand + tail_w > right_edge_canvas:
                        continue
                    tail_anchor = cand
                    tail_mid_xs = mid_xs
                    break

                if tail_anchor is not None:
                    chosen_xs = rule1_xs + tail_mid_xs + [tail_anchor]
                else:
                    # Rule 3 — right-edge fallback. Tail's right edge aligns
                    # to the rightmost edge of any row above. Middles
                    # distribute between head's right edge and tail's anchor.
                    # If head_right > tail_x (no-middles branch) or middles
                    # don't fit (with-middles branch), tail_x is voided and
                    # the last-ditch pack-from-margin path takes over.
                    right_edge_target = max(
                        row_rights_list[i][-1] for i in range(r_idx)
                    )
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

        if chosen_xs is None:
            # Last-ditch (also catches the r_idx==0 path where row 0's
            # head/tail/distribute didn't validate). Pack from margin with
            # zero gap — readability suffers but no crash.
            chosen_xs = [margin_x]
            for kk in range(1, n):
                chosen_xs.append(chosen_xs[-1] + widths[kk - 1])

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
        "--limit",
        type=int,
        default=0,
        help="Render only first N transfers (post-filter). 0 = no limit. Use for testing "
        "raw drawing logic with a small input — e.g. --limit 2 → just the shinkansen pair.",
    )
    args = parser.parse_args()

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
            slug for slug in transfers
            if not any(b.get("code") == active for b in lines[slug].get("badges", []))
        ]
        print(f"Filter active line {active!r}: {len(transfers)} transfers remain")

    if args.limit > 0:
        transfers = transfers[: args.limit]
        print(f"Limit to first {args.limit}: {transfers}")

    render_transfer(surf, transfers, lines)

    out_path = root / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(surf, str(out_path))
    print(f"Saved to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
