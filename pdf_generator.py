"""
pdf_generator.py — Build the print-ready hang-tag PDFs.

Produces four documents:
  * front_cards.pdf        NAME side  (customer name + logo)
  * back_cards.pdf         MEALS side (customer name + their meals + logo),
                           imposed for MANUAL duplex
  * duplex_test_front.pdf  numbered alignment test
  * duplex_test_back.pdf   numbered alignment test

Cards are hang tags: physically 4.25 x 5.5 (so they tile 4-up and the cut-stack
math is simple), but the artwork is drawn SIDEWAYS (landscape) by default.

Four tricky pieces, each documented at its function:
  1. CUT-STACK IMPOSITION (build_pages)  — order cards so that after cutting the
     printed stack into 4 position-piles and stacking them, the cards come out in
     customer order.
  2. ORIENTATION PLACEMENT (_place)      — rotate landscape artwork into the
     portrait 4.25x5.5 cell, composing cleanly with the duplex flip.
  3. DUPLEX FLIP LOGIC (_back_cell)      — put each back card at the mirrored cell
     (and rotate 180 for short-edge) so it lands behind the right front card.
  4. CUT LINES (_draw_cut_lines)         — full edge-to-edge guides for a
     guillotine cutter.
"""

from __future__ import annotations

import io
import math

import fitz  # PyMuPDF — rasterize a PDF logo and render previews
from PIL import Image
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

import config as C
from config import Config
from csv_parser import Customer

# Grid cells (row, col); row 0 is the TOP row.
TL, TR, BL, BR = (0, 0), (0, 1), (1, 0), (1, 1)

# Physical pile-stacking order the operator performs: cut into 4 position-piles,
# then stack them clockwise TL -> TR -> BR -> BL. (From the spec's worked example.)
STACK_ORDER = [TL, TR, BR, BL]
READING_ORDER = [TL, TR, BL, BR]  # plain "sequential" mode


# ===========================================================================
# Fonts
# ===========================================================================
_FONTS_READY = False


def register_fonts() -> dict:
    """Register DM Sans + Cormorant Garamond; fall back to Helvetica/Times."""
    global _FONTS_READY
    resolved = {"body": "Helvetica", "heading": "Times-Roman"}
    if not _FONTS_READY:
        try:
            pdfmetrics.registerFont(TTFont("DMSans", str(C.FONT_DIR / "DMSans.ttf")))
            resolved["body"] = "DMSans"
        except Exception:
            resolved["body"] = "Helvetica"
        try:
            pdfmetrics.registerFont(
                TTFont("Cormorant", str(C.FONT_DIR / "CormorantGaramond.ttf")))
            resolved["heading"] = "Cormorant"
        except Exception:
            resolved["heading"] = "Times-Roman"
        _FONTS_READY = True
    else:
        reg = set(pdfmetrics.getRegisteredFontNames())
        resolved["body"] = "DMSans" if "DMSans" in reg else "Helvetica"
        resolved["heading"] = "Cormorant" if "Cormorant" in reg else "Times-Roman"
    return resolved


def _resolve(cfg: Config) -> dict:
    """Map cfg font choices to registered names (with fallbacks)."""
    avail = register_fonts()
    reg = set(pdfmetrics.getRegisteredFontNames())
    heading = cfg.name_font if cfg.name_font in reg else avail["heading"]
    body = cfg.body_font if cfg.body_font in reg else avail["body"]
    return {"heading": heading, "body": body}


# ===========================================================================
# Logo loading / recoloring
# ===========================================================================
def load_logo(file_bytes: bytes, filename: str) -> Image.Image:
    """Load an uploaded logo (PNG/JPG/PDF) into an RGBA PIL image."""
    name = (filename or "").lower()
    if name.endswith(".pdf") or file_bytes[:5] == b"%PDF-":
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        page = doc[0]
        pix = page.get_pixmap(matrix=fitz.Matrix(8, 8), alpha=True)  # ~600dpi
        img = Image.frombytes("RGBA", (pix.width, pix.height), pix.samples)
        doc.close()
        return _autocrop(img)
    return _autocrop(Image.open(io.BytesIO(file_bytes)).convert("RGBA"))


def _autocrop(img: Image.Image) -> Image.Image:
    """Trim fully-transparent margins so logo sizing hugs the real content."""
    bbox = img.split()[-1].getbbox()
    return img.crop(bbox) if bbox else img


def knockout_background(img: Image.Image, tol: int = 45) -> Image.Image:
    """
    Make the logo's background transparent by color-keying the corner color.

    Havn's "inverted" asset is a white mark on a solid dark-green tile — every
    pixel is opaque, so recoloring would produce a filled square. We sample the
    four corners, take their median as the background, and clear every pixel
    within `tol` (RGB distance). Logos already on transparency are untouched.
    """
    import numpy as np

    arr = np.asarray(img.convert("RGBA")).astype(int)
    h, w, _ = arr.shape
    corner_alpha = [arr[0, 0, 3], arr[0, w - 1, 3], arr[h - 1, 0, 3], arr[h - 1, w - 1, 3]]
    if max(corner_alpha) == 0:
        return img
    corners = np.array([arr[0, 0, :3], arr[0, w - 1, :3],
                        arr[h - 1, 0, :3], arr[h - 1, w - 1, :3]])
    bg = np.median(corners, axis=0)
    dist = np.sqrt(((arr[:, :, :3] - bg) ** 2).sum(axis=2))
    out = arr.copy()
    out[dist <= tol, 3] = 0
    return Image.fromarray(out.astype("uint8"), "RGBA")


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def prepare_logo(img: Image.Image, mode: str, knockout: bool = True,
                 tol: int = 45, hex_color: str = C.BRAND_GREEN_HEX) -> Image.Image:
    """
    Get the logo print-ready: optionally knock out the background, then recolor
    the remaining (foreground) pixels. 'green' uses hex_color (brand green),
    'black'/'white' use those, 'original' keeps the artwork's colors.
    """
    if knockout:
        img = knockout_background(img, tol)
    img = _autocrop(img)
    if mode == C.LOGO_ORIGINAL:
        return img
    if mode == C.LOGO_GREEN:
        r, g, b = _hex_to_rgb(hex_color)
    elif mode == C.LOGO_WHITE:
        r = g = b = 255
    else:  # black
        r = g = b = 0
    img = img.convert("RGBA")
    _, _, _, a = img.split()
    fill = Image.merge("RGBA", (
        Image.new("L", img.size, r), Image.new("L", img.size, g),
        Image.new("L", img.size, b), a))
    return fill


def logo_reader(img: Image.Image | None):
    return ImageReader(img) if img is not None else None


# ===========================================================================
# 1. CUT-STACK IMPOSITION
# ===========================================================================
def build_pages(n_customers: int, ordering: str) -> tuple[list[list[tuple]], int]:
    """
    Assign customer indices to (row, col) cells on each sheet.

    Returns (pages, n_pages); pages[p] is a list of (row, col, cust_index) with
    cust_index == None for blank slots.

    CUT-STACK MATH — with P = ceil(N/4) pages, the operator prints all sheets,
    cuts the stack into 4 position-piles, then stacks them TL, TR, BR, BL (page 0
    on top within each pile). To make the final deck read 0..N-1 we give each
    pile a contiguous run: card at (page p, STACK_ORDER[k]) = customer k*P + p.

    Worked example N=8 -> P=2:
        page0: TL=0 TR=2 BR=4 BL=6      page1: TL=1 TR=3 BR=5 BL=7
    After cut+stack (TL[0,1] TR[2,3] BR[4,5] BL[6,7]) the deck is 0..7. Matches
    the spec exactly. 'sequential' just lays cards out in reading order.
    """
    per = 4
    n_pages = max(1, math.ceil(n_customers / per)) if n_customers else 0
    pages: list[list[tuple]] = []
    order = STACK_ORDER if ordering == C.ORDER_CUT_STACK else READING_ORDER
    for p in range(n_pages):
        cells = []
        for k, (r, col) in enumerate(order):
            idx = (k * n_pages + p) if ordering == C.ORDER_CUT_STACK else (p * per + k)
            cells.append((r, col, idx if idx < n_customers else None))
        pages.append(cells)
    return pages, n_pages


# ===========================================================================
# Geometry
# ===========================================================================
def _grid_origin(cfg: Config):
    cw, ch = cfg.card_w * inch, cfg.card_h * inch
    gx, gy = cfg.gutter_x * inch, cfg.gutter_y * inch
    grid_w = cfg.cols * cw + (cfg.cols - 1) * gx
    grid_h = cfg.rows * ch + (cfg.rows - 1) * gy
    return (cfg.page_w * inch - grid_w) / 2, (cfg.page_h * inch - grid_h) / 2, cw, ch


def _cell_rect(cfg: Config, row: int, col: int):
    """Bottom-left (x, y) and size (w, h) in points for a grid cell. Row 0 = top."""
    off_x, off_y, cw, ch = _grid_origin(cfg)
    gx, gy = cfg.gutter_x * inch, cfg.gutter_y * inch
    x = off_x + col * (cw + gx)
    y = off_y + (cfg.rows - 1 - row) * (ch + gy)
    return x, y, cw, ch


def _back_cell(cfg: Config, row: int, col: int):
    """
    3. DUPLEX FLIP LOGIC — map a FRONT cell to its BACK cell + rotate flag.

    long_edge  (flip about vertical edge): columns mirror, upright.
               -> (row, cols-1-col), rotate=False
    short_edge (flip about horizontal edge): rows mirror, upside-down.
               -> (rows-1-row, col), rotate=True (180 deg)
    """
    if cfg.flip_mode == C.FLIP_SHORT_EDGE:
        return cfg.rows - 1 - row, col, True
    return row, cfg.cols - 1 - col, False


# ===========================================================================
# 2. ORIENTATION PLACEMENT
# ===========================================================================
def _logical_dims(cfg: Config, cw: float, ch: float) -> tuple[float, float]:
    """Content-box size: landscape swaps so width is the long (5.5") edge."""
    if cfg.orientation == C.ORIENT_LANDSCAPE:
        return ch, cw   # wide x short
    return cw, ch       # upright


def _place(c, cfg, cell, rotate180, draw_fn):
    """
    Draw a card into its physical cell, applying orientation + optional duplex
    180 rotation. `draw_fn(c, 0, 0, lw, lh)` draws in a logical content box.

    Transform order (CTM composes right-to-left): the landscape +90 mapping is
    innermost (places upright landscape art in the cell), then the optional 180
    about the cell center flips the whole cell for short-edge duplex.
    """
    x, y, cw, ch = cell
    lw, lh = _logical_dims(cfg, cw, ch)
    c.saveState()
    if rotate180:
        c.translate(x + cw / 2, y + ch / 2)
        c.rotate(180)
        c.translate(-(x + cw / 2), -(y + ch / 2))
    if cfg.orientation == C.ORIENT_LANDSCAPE:
        # Rotate the landscape box 90 deg CCW into the portrait cell.
        c.translate(x + cw, y)
        c.rotate(90)
        draw_fn(c, 0, 0, lw, lh)
    else:
        draw_fn(c, x, y, lw, lh)
    c.restoreState()


# ===========================================================================
# Text + logo primitives
# ===========================================================================
def _text_width(text, font, size, tracking=0.0):
    w = pdfmetrics.stringWidth(text, font, size)
    if tracking and len(text) > 1:
        w += tracking * (len(text) - 1)
    return w


def _draw_centered(c, cx, baseline, text, font, size, tracking=0.0,
                   color=(0, 0, 0), bold=False):
    """Center `text` on cx at `baseline`. Honors tracking + faux-bold."""
    w = _text_width(text, font, size, tracking)
    to = c.beginText(cx - w / 2, baseline)
    to.setFont(font, size)
    to.setFillColorRGB(*color)
    to.setCharSpace(tracking)  # always set: Tc persists across text objects
    if bold:
        c.setStrokeColorRGB(*color)
        c.setLineWidth(size * 0.022)
        to.setTextRenderMode(2)  # fill + stroke -> heavier weight
    to.textOut(text)
    c.drawText(to)


def _fit_size(text, font, max_w, start, floor):
    size = start
    while size > floor and pdfmetrics.stringWidth(text, font, size) > max_w:
        size -= 0.5
    return size


def _name_lines(name, font, max_w, start_size):
    """Fit a name to width; wrap to two lines (first / rest) if needed."""
    size = _fit_size(name, font, max_w, start_size, start_size * 0.55)
    if pdfmetrics.stringWidth(name, font, size) <= max_w or " " not in name:
        return [name], size
    first, *rest = name.split(" ")
    lines = [first, " ".join(rest)]
    size = min(_fit_size(lines[0], font, max_w, start_size, start_size * 0.5),
               _fit_size(lines[1], font, max_w, start_size, start_size * 0.5))
    return lines, size


def _draw_name_block(c, cx, center_y, name, font, max_w, start_size, cfg):
    """Draw a (possibly two-line) name vertically centered on center_y."""
    lines, size = _name_lines(name, font, max_w, start_size)
    line_h = size * 1.1
    top = center_y + (line_h * len(lines)) / 2 - size
    for i, ln in enumerate(lines):
        _draw_centered(c, cx, top - i * line_h, ln, font, size,
                       tracking=cfg.name_tracking, color=(0.08, 0.08, 0.08),
                       bold=cfg.name_bold)
    return line_h * len(lines)


def _draw_logo(c, reader, img, cx, target_w, *, top=None, bottom=None, fallback_font):
    """Draw logo centered on cx, anchored by top OR bottom. Returns height."""
    if reader is None or img is None:
        size = target_w * 0.15
        y = (top - size) if top is not None else (bottom or 0)
        _draw_centered(c, cx, y, "HAVN CLUB", fallback_font, size,
                       tracking=size * 0.28, color=_hex_rgb01(C.BRAND_GREEN_HEX))
        return size
    iw, ih = img.size
    w = target_w
    h = w * (ih / iw)
    y = (top - h) if top is not None else bottom
    c.drawImage(reader, cx - w / 2, y, width=w, height=h, mask="auto",
                preserveAspectRatio=True)
    return h


def _hex_rgb01(hx):
    r, g, b = _hex_to_rgb(hx)
    return (r / 255, g / 255, b / 255)


def _draw_border(c, x, y, w, h, cfg):
    if not cfg.show_border:
        return
    ins = cfg.border_inset * inch
    c.setLineWidth(0.6)
    c.setStrokeColorRGB(0.72, 0.70, 0.66)
    c.rect(x + ins, y + ins, w - 2 * ins, h - 2 * ins, stroke=1, fill=0)


# ===========================================================================
# Card faces  (draw in a logical box: x,y bottom-left, w x h)
# ===========================================================================
def _split_name(name: str, stack: bool):
    """First name / rest as two lines when stacking; else a single line."""
    name = (name or "").strip()
    if stack and " " in name:
        first, *rest = name.split(" ")
        return [first, " ".join(rest)]
    return [name]


def draw_front(c, x, y, w, h, cust: Customer, cfg, fonts, reader, img):
    """
    FRONT (name side): green logo at top, then the customer name filling the rest.

    The name is stacked (first name over last name) and auto-sized to FILL the
    available width and height, so it reads big and bold on the tag. Falls back to
    a single line for one-word names.
    """
    _draw_border(c, x, y, w, h, cfg)
    cx = x + w / 2
    pad = cfg.card_pad * inch
    font = fonts["heading"]

    logo_top = y + h - cfg.front_logo_top * inch
    logo_h = _draw_logo(c, reader, img, cx, cfg.front_logo_w * inch,
                        top=logo_top, fallback_font=font)

    region_top = logo_top - logo_h - 0.18 * inch
    region_bottom = y + pad
    region_h = region_top - region_bottom
    max_w = w - 2 * pad

    lines = _split_name(cust.name, cfg.name_stack)
    # Size the name to fill: widest line hits max_w, and all lines fit vertically.
    # stringWidth is linear in size, so size_for_width = max_w / width_at_1pt.
    widest = max((pdfmetrics.stringWidth(ln, font, 1.0) for ln in lines), default=1.0) or 1.0
    size_w = max_w / widest
    line_gap = 1.12
    size_h = region_h / (len(lines) * line_gap)
    size = min(size_w, size_h, cfg.name_size_max)

    line_h = size * line_gap
    top = (region_top + region_bottom) / 2 + (line_h * len(lines)) / 2 - size
    for i, ln in enumerate(lines):
        _draw_centered(c, cx, top - i * line_h, ln, font, size,
                       tracking=cfg.name_tracking, color=(0.08, 0.08, 0.08),
                       bold=cfg.name_bold)


def draw_back(c, x, y, w, h, cust: Customer, cfg, fonts, reader, img):
    """
    BACK (meals side): bold customer name at top, the meals they ordered in the
    middle (only meals with qty>0), and the green logo near the bottom.
    """
    _draw_border(c, x, y, w, h, cfg)
    cx = x + w / 2
    pad = cfg.card_pad * inch
    max_w = w - 2 * pad

    # --- Name at top --------------------------------------------------------
    name_lines, nsize = _name_lines(cust.name or "", fonts["heading"], max_w,
                                    cfg.back_name_size)
    nlh = nsize * 1.08
    cursor = y + h - pad - nsize
    for i, ln in enumerate(name_lines):
        _draw_centered(c, cx, cursor - i * nlh, ln, fonts["heading"], nsize,
                       tracking=cfg.name_tracking, color=(0.08, 0.08, 0.08),
                       bold=cfg.name_bold)
    cursor -= nlh * len(name_lines)

    # --- Optional "YOUR MEALS" label + divider ------------------------------
    if cfg.back_title:
        cursor -= 0.06 * inch
        _draw_centered(c, cx, cursor, cfg.back_title, fonts["body"],
                       cfg.back_title_size, tracking=cfg.back_title_tracking,
                       color=(0.35, 0.35, 0.35))
        cursor -= cfg.back_title_size
    if cfg.show_divider:
        cursor -= 0.02 * inch
        half = 0.38 * inch
        c.setLineWidth(0.6)
        c.setStrokeColorRGB(0.55, 0.52, 0.47)
        c.line(cx - half, cursor, cx + half, cursor)
        cursor -= 0.10 * inch

    # --- Logo near bottom ---------------------------------------------------
    logo_h = _draw_logo(c, reader, img, cx, cfg.back_logo_w * inch,
                        bottom=y + cfg.back_logo_bottom * inch,
                        fallback_font=fonts["heading"])
    logo_top_edge = y + cfg.back_logo_bottom * inch + logo_h

    # --- Meals list, centered between the name block and the logo -----------
    items = cust.items or [("—", 0)]
    line_h = cfg.item_size * cfg.item_leading
    block_h = line_h * len(items)
    region_top = cursor
    region_bottom = logo_top_edge + 0.12 * inch
    start_baseline = (region_top + region_bottom) / 2 + block_h / 2 - cfg.item_size
    for i, (label, qty) in enumerate(items):
        text = f"{qty} × {label}" if qty else label
        size = _fit_size(text, fonts["body"], max_w, cfg.item_size, 7.0)
        _draw_centered(c, cx, start_baseline - i * line_h, text,
                       fonts["body"], size, color=(0.1, 0.1, 0.1))


# ===========================================================================
# 4. CUT LINES (guillotine guides)
# ===========================================================================
def _draw_cut_lines(c, cfg):
    """
    Draw thin, full edge-to-edge cut lines at every card boundary so a guillotine
    can be lined up straight. Verticals span the full page height, horizontals
    span the full page width. (With cards tiling exactly, these are the center
    cross plus the paper edges.)
    """
    if not cfg.cut_lines:
        return
    pw, ph = cfg.page_w * inch, cfg.page_h * inch
    xs, ys = set(), set()
    for row in range(cfg.rows):
        for col in range(cfg.cols):
            x, y, w, h = _cell_rect(cfg, row, col)
            xs.update([round(x, 2), round(x + w, 2)])
            ys.update([round(y, 2), round(y + h, 2)])
    c.setLineWidth(cfg.cut_line_width)
    c.setStrokeColorRGB(0.6, 0.6, 0.6)
    for x in sorted(xs):
        c.line(x, 0, x, ph)
    for y in sorted(ys):
        c.line(0, y, pw, y)


# ===========================================================================
# Document builders
# ===========================================================================
def _new_canvas(cfg):
    buf = io.BytesIO()
    return canvas.Canvas(buf, pagesize=(cfg.page_w * inch, cfg.page_h * inch)), buf


def _build(customers, cfg, img, draw_fn, is_back):
    fonts = _resolve(cfg)
    reader = logo_reader(img)
    c, buf = _new_canvas(cfg)
    pages, _ = build_pages(len(customers), cfg.ordering_mode)
    for cells in pages:
        _draw_cut_lines(c, cfg)
        for (row, col, idx) in cells:
            if idx is None:
                continue
            if is_back:
                brow, bcol, rot = _back_cell(cfg, row, col)
                cell = _cell_rect(cfg, brow, bcol)
            else:
                cell, rot = _cell_rect(cfg, row, col), False
            _place(c, cfg, cell, rot,
                   lambda cc, x, y, w, h, i=idx: draw_fn(cc, x, y, w, h,
                                                         customers[i], cfg, fonts, reader, img))
        c.showPage()
    c.save()
    return buf.getvalue()


def generate_front(customers, cfg: Config, img=None) -> bytes:
    """front_cards.pdf — the NAME side."""
    return _build(customers, cfg, img, draw_front, is_back=False)


def generate_back(customers, cfg: Config, img=None) -> bytes:
    """back_cards.pdf — the MEALS side, imposed for the chosen flip mode."""
    return _build(customers, cfg, img, draw_back, is_back=True)


# ===========================================================================
# Duplex alignment test
# ===========================================================================
def _draw_test(c, x, y, w, h, number, side, sub, cfg, fonts):
    _draw_border(c, x, y, w, h, cfg)
    cx = x + w / 2
    _draw_centered(c, cx, y + h * 0.42, str(number), fonts["heading"],
                   min(w, h) * 0.5, bold=True)
    _draw_centered(c, cx, y + h - 0.5 * inch, side, fonts["body"], 15,
                   tracking=3, color=(0.3, 0.3, 0.3))
    _draw_centered(c, cx, y + 0.3 * inch, sub, fonts["body"], 9,
                   color=(0.45, 0.45, 0.45))


def generate_duplex_test(cfg: Config, n: int = 8) -> tuple[bytes, bytes]:
    """
    Two numbered PDFs to verify alignment BEFORE using cardstock. Uses the exact
    same imposition + orientation + flip logic as the real cards, so each back
    number should land behind its matching front number, and cut+stack should
    yield 1,2,3,... in order. Print on plain paper and adjust FLIP_MODE to match.
    """
    fonts = _resolve(cfg)
    pages, n_pages = build_pages(n, cfg.ordering_mode)

    def render(is_back):
        c, buf = _new_canvas(cfg)
        for p, cells in enumerate(pages):
            _draw_cut_lines(c, cfg)
            for (row, col, idx) in cells:
                if idx is None:
                    continue
                if is_back:
                    brow, bcol, rot = _back_cell(cfg, row, col)
                    cell = _cell_rect(cfg, brow, bcol)
                else:
                    cell, rot = _cell_rect(cfg, row, col), False
                _place(c, cfg, cell, rot,
                       lambda cc, x, y, w, h, i=idx, pp=p: _draw_test(
                           cc, x, y, w, h, i + 1, "BACK" if is_back else "FRONT",
                           f"sheet {pp + 1}/{n_pages}", cfg, fonts))
            c.showPage()
        c.save()
        return buf.getvalue()

    return render(False), render(True)


# ===========================================================================
# Single-card preview (for the Streamlit UI) — drawn upright as the tag reads
# ===========================================================================
def render_card_png(cust: Customer, side: str, cfg: Config, img=None,
                    scale: float = 2.0) -> bytes:
    fonts = _resolve(cfg)
    reader = logo_reader(img)
    if cfg.orientation == C.ORIENT_LANDSCAPE:
        pw, ph = cfg.card_h * inch, cfg.card_w * inch
    else:
        pw, ph = cfg.card_w * inch, cfg.card_h * inch
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(pw, ph))
    draw_fn = draw_front if side == "front" else draw_back
    draw_fn(c, 0, 0, pw, ph, cust, cfg, fonts, reader, img)
    c.showPage()
    c.save()
    doc = fitz.open(stream=buf.getvalue(), filetype="pdf")
    png = doc[0].get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False).tobytes("png")
    doc.close()
    return png
