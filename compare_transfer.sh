#!/usr/bin/env bash
# Build a side-by-side composite of the IRL Tokyo PIDS reference vs the
# current transfer-display render. The reference photo is height-aligned
# (same width-scale) above the render.
#
# Usage:
#   ./compare_transfer.sh                    # uses defaults
#   ./compare_transfer.sh <render.png>       # custom render path
#   ./compare_transfer.sh <render.png> "<label>"
#
# Output: <render-stem>_compare.png next to the render.

set -euo pipefail

REF="lcd_references/transfer_tokyo.png"
RENDER="${1:-_visual_iter/v_neue_world.png}"
LABEL="${2:-RENDER}"

if [ ! -f "$REF" ]; then
  echo "Reference photo not found: $REF" >&2
  exit 1
fi
if [ ! -f "$RENDER" ]; then
  echo "Render not found: $RENDER" >&2
  exit 1
fi

# Output path: <render-dir>/<render-stem>_compare.png
DIR="$(dirname "$RENDER")"
STEM="$(basename "$RENDER" .png)"
OUT="$DIR/${STEM}_compare.png"
TMP="$DIR/_compare_scaled.png"

# Reference is 881 wide; scale render to match for a fair side-by-side.
magick "$RENDER" -resize 881x "$TMP"
magick \
  \( "$REF" -gravity north -background "#222" -splice 0x32 \
     -fill white -font Arial -pointsize 18 \
     -annotate +0+8 "REFERENCE (IRL Tokyo PIDS, JO train)" \) \
  \( "$TMP" -gravity north -background "#222" -splice 0x32 \
     -fill white -font Arial -pointsize 18 \
     -annotate +0+8 "$LABEL" \) \
  -append \
  -bordercolor "#222" -border 8 \
  "$OUT"
rm -f "$TMP"

echo "Saved $OUT"
