"""
config.py — All tunable settings for the Havn Club hang-tag generator.

Everything the operator can change lives here as a single `Config` dataclass.
Streamlit builds a `Config` from the sidebar widgets each run and hands it to the
PDF generator. All *distances are stored in INCHES* (the unit the operator thinks
in); `pdf_generator` multiplies by 72 (points-per-inch) at draw time.

Nothing about the weekly menu is stored here — meal columns and their display
names are detected from the uploaded CSV every week (see csv_parser.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Location of the bundled TTF fonts (DM Sans / Cormorant Garamond).
FONT_DIR = Path(__file__).parent / "fonts"

# Bundled default Havn logo (used automatically when nothing is uploaded).
DEFAULT_LOGO = Path(__file__).parent / "assets" / "havn_logo.pdf"

# ---------------------------------------------------------------------------
# Flip modes for MANUAL duplex printing.
#   long_edge  — you flip the printed stack about the LONG (vertical) edge, like
#                turning a book page. Back cards are mirrored LEFT<->RIGHT, upright.
#   short_edge — you flip about the SHORT (horizontal, top) edge, like a notepad.
#                Back cards are mirrored TOP<->BOTTOM and rotated 180 degrees.
# The duplex test PDFs let you confirm which one your printer needs.
# ---------------------------------------------------------------------------
FLIP_LONG_EDGE = "long_edge"
FLIP_SHORT_EDGE = "short_edge"

# ---------------------------------------------------------------------------
# Card ordering modes.
#   cut_stack  — impose so that after printing every sheet, cutting the whole
#                stack into 4 position-piles (TL/TR/BR/BL) and stacking those
#                piles, the cards come out in customer order (see pdf_generator).
#   sequential — plain left-to-right, top-to-bottom order on each sheet.
# ---------------------------------------------------------------------------
ORDER_CUT_STACK = "cut_stack"
ORDER_SEQUENTIAL = "sequential"

# Card content orientation. The physical card is always 4.25 x 5.5 (so it tiles
# 4-up and the cut-stack math is unchanged) — orientation only rotates the
# artwork inside each card.
#   landscape — content reads sideways (the 5.5" edge is horizontal). Standard
#               hang-tag look; the customer name spans the wide dimension.
#   portrait  — content reads upright (the 4.25" edge is horizontal).
ORIENT_LANDSCAPE = "landscape"
ORIENT_PORTRAIT = "portrait"

# Logo color treatments.
LOGO_GREEN = "green"        # recolor the mark to the brand green (default)
LOGO_BLACK = "black"
LOGO_WHITE = "white"
LOGO_ORIGINAL = "original"  # leave the artwork's own colors

# Havn brand green (sampled from the supplied logo tile).
BRAND_GREEN_HEX = "#0C200E"

# Cut-guide mark styles (soft guides for a guillotine — never hard full lines
# across the card faces unless you explicitly pick "lines").
#   ticks   — short ticks at the sheet edges marking each cut position (default):
#             line the guillotine blade up to the top+bottom ticks for the vertical
#             cut and the left+right ticks for the horizontal cut. Faces stay clean.
#   cross   — a small soft cross where the cuts intersect (sheet center).
#   corners — soft corner ticks at each card's corners.
#   lines   — full soft edge-to-edge lines (old behavior; light gray).
#   none    — no marks.
MARK_TICKS = "ticks"
MARK_CROSS = "cross"
MARK_CORNERS = "corners"
MARK_LINES = "lines"
MARK_NONE = "none"


@dataclass
class Config:
    # --- Sheet / card geometry (inches) --------------------------------------
    page_w: float = 8.5      # US Letter width
    page_h: float = 11.0     # US Letter height
    card_w: float = 4.25     # quarter-letter width  (physical card, always)
    card_h: float = 5.5      # quarter-letter height (physical card, always)
    cols: int = 2            # cards across
    rows: int = 2            # cards down  (cols*rows = cards-per-sheet = 4)
    gutter_x: float = 0.0    # horizontal space between cards (inches)
    gutter_y: float = 0.0    # vertical space between cards (inches)
    # Inner padding — also the SAFE MARGIN from the paper edge. The 4 cards fill
    # the whole sheet, so the outer cards' edges sit in the printer's non-printable
    # border; this keeps content clear of it. Increase if your printer still clips.
    card_pad: float = 0.45

    orientation: str = ORIENT_LANDSCAPE  # sideways hang tags by default

    # --- Logo -----------------------------------------------------------------
    front_logo_w: float = 1.45   # printed logo width on the FRONT (inches)
    front_logo_top: float = 0.42 # gap from card top edge to top of logo (inches)
    back_logo_w: float = 1.05    # printed logo width on the BACK (inches)
    back_logo_bottom: float = 0.42  # gap from card bottom edge to bottom of logo
    logo_color: str = LOGO_GREEN
    logo_hex: str = BRAND_GREEN_HEX  # used when logo_color == green (or custom)

    # --- Typography -----------------------------------------------------------
    # Customer name — the hero element on BOTH sides.
    name_size: float = 56.0       # front cap / fallback point size
    name_stack: bool = True       # front: stack first name over last name, filling
    name_size_max: float = 92.0   # ceiling when auto-filling the stacked name
    back_name_size: float = 23.0  # back point size (sits above the meals)
    name_bold: bool = True
    name_tracking: float = 0.5
    name_font: str = "Cormorant"  # falls back to Times-Roman

    # Meal lines (back).
    back_title: str = "YOUR MEALS"
    back_title_size: float = 11.0
    back_title_tracking: float = 3.0
    item_size: float = 12.0
    item_leading: float = 1.55
    body_font: str = "DMSans"     # falls back to Helvetica

    # --- Decorative touches ---------------------------------------------------
    show_divider: bool = True     # short rule under the back title
    show_border: bool = False     # subtle keyline frame around each card
    border_inset: float = 0.16    # keyline inset from card edge (inches)

    # --- Printing / imposition -----------------------------------------------
    flip_mode: str = FLIP_LONG_EDGE
    ordering_mode: str = ORDER_CUT_STACK
    cut_style: str = MARK_TICKS   # soft guide-mark style (see MARK_* above)
    mark_len: float = 0.2         # guide-mark length (inches)
    mark_weight: float = 0.5      # guide-mark stroke weight (points)

    # ------------------------------------------------------------------ helpers
    @property
    def per_sheet(self) -> int:
        return self.cols * self.rows
