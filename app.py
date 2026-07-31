"""
app.py — Havn Club Hang-Tag Generator (Streamlit).

Weekly workflow for a non-technical operator:
  1. Upload this week's packing-sheet CSV and a Havn logo.
  2. Confirm which columns are meals and edit their printed names.
  3. Tune layout in the sidebar (optional) and preview sample cards.
  4. Generate & download the four PDFs, then manually duplex-print on cardstock.

Cards are sideways (landscape) hang tags: FRONT = name + logo, BACK = name +
their meals + logo. Nothing about the menu is hardcoded — meal columns are
detected from the CSV each week.
"""

from __future__ import annotations

import hmac

import pandas as pd
import streamlit as st

import config as C
from config import Config
import csv_parser as parser
import pdf_generator as pdf

st.set_page_config(page_title="Havn Club · Hang-Tag Generator",
                   page_icon="🏷️", layout="wide")


# ---------------------------------------------------------------------------
# Password gate (for the hosted web link). Set `app_password` in the app's
# Streamlit secrets to require a password; if none is set (e.g. running locally)
# the app is open. Uses a constant-time compare.
# ---------------------------------------------------------------------------
def check_password() -> bool:
    try:
        configured = st.secrets["app_password"]
    except Exception:
        configured = ""
    if not configured:
        return True  # no password configured -> open (local use)
    if st.session_state.get("pw_ok"):
        return True
    st.markdown("#### 🔒 Havn Club Hang-Tag Generator")
    with st.form("login"):
        pw = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Enter")
    if submitted:
        if hmac.compare_digest(pw, str(configured)):
            st.session_state["pw_ok"] = True
            st.rerun()
        else:
            st.error("Incorrect password.")
    return False


if not check_password():
    st.stop()

st.markdown(
    """
    <style>
      .stApp { background: #faf7f1; }
      h1, h2, h3 { font-family: Georgia, 'Times New Roman', serif; color:#2a2723; }
      .hc-title { font-size: 2.2rem; letter-spacing:.12em; font-weight:600;
                  color:#14361b; margin-bottom:0; }
      .hc-sub  { color:#7a7266; letter-spacing:.18em; text-transform:uppercase;
                 font-size:.8rem; margin-top:.1rem; }
      .stDownloadButton button { width:100%; }
    </style>
    """,
    unsafe_allow_html=True,
)
st.markdown('<div class="hc-title">HAVN CLUB</div>', unsafe_allow_html=True)
st.markdown('<div class="hc-sub">Customer Hang-Tag Generator</div>',
            unsafe_allow_html=True)
st.write("")


# ===========================================================================
# Sidebar — configuration panel
# ===========================================================================
def build_config() -> Config:
    cfg = Config()
    s = st.sidebar
    s.header("⚙️ Configuration")

    with s.expander("Layout & printing", expanded=True):
        cfg.duplex_mode = st.radio(
            "Printer / duplex",
            [C.DUPLEX_AUTO, C.DUPLEX_MANUAL],
            format_func=lambda v: "Auto-duplex printer — one file"
            if v == C.DUPLEX_AUTO else "Manual duplex — two files, flip yourself",
            help="Pick 'Auto-duplex' if your printer prints both sides on its own "
                 "(you choose Two-Sided in the print dialog). You'll get ONE file. "
                 "Pick 'Manual' to get separate front/back files you flip by hand.",
        )
        _is_auto = cfg.duplex_mode == C.DUPLEX_AUTO
        cfg.orientation = st.radio(
            "Orientation",
            [C.ORIENT_LANDSCAPE, C.ORIENT_PORTRAIT],
            format_func=lambda v: "Sideways / landscape (hang tag)"
            if v == C.ORIENT_LANDSCAPE else "Upright / portrait",
        )
        cfg.flip_mode = st.radio(
            "Printer binding" if _is_auto else "Flip mode (manual duplex)",
            [C.FLIP_LONG_EDGE, C.FLIP_SHORT_EDGE],
            format_func=(
                (lambda v: "Long-edge binding (printer default)"
                 if v == C.FLIP_LONG_EDGE else "Short-edge binding")
                if _is_auto else
                (lambda v: "Long edge (flip like a book)"
                 if v == C.FLIP_LONG_EDGE else "Short edge (flip like a notepad)")
            ),
            help=("Match this to your printer's Two-Sided setting (Long-Edge is the "
                  "usual default). If backs come out on the wrong card, switch this."
                  if _is_auto else
                  "Which way you turn the stack over between sides.")
                 + " Confirm with the alignment test first.",
        )
        _order_opts = [C.ORDER_HOTDOG, C.ORDER_CUT_STACK, C.ORDER_SEQUENTIAL]
        cfg.ordering_mode = st.radio(
            "Card ordering",
            _order_opts,
            index=_order_opts.index(Config().ordering_mode),
            format_func=lambda v: {
                C.ORDER_HOTDOG: "Hot-dog (2 cuts) — cut lengthwise, stack, cut again",
                C.ORDER_CUT_STACK: "Cut-stack (cut into 4 piles & stack)",
                C.ORDER_SEQUENTIAL: "Sequential (plain page order)",
            }[v],
            help="Hot-dog = the simple 2-cut method: cut the printed stack down the "
                 "middle lengthwise into two strips, put the RIGHT strip on top of "
                 "the LEFT, cut across the middle, then drop the pile starting with "
                 "#1 on top. Customer #1 prints at the top-right of sheet 1. "
                 "Confirm with the alignment test on plain paper first.",
        )
        cfg.back_flip_180 = st.checkbox(
            "Rotate back 180°",
            value=True,
            help="Rotates every back card 180° in place (positions unchanged). "
                 "Untick only if the meals side prints upside-down with it on.",
        )
        _mark_opts = [C.MARK_CROSS, C.MARK_CENTER, C.MARK_TICKS, C.MARK_CORNERS,
                      C.MARK_LINES, C.MARK_NONE]
        cfg.cut_style = st.selectbox(
            "Cut guide marks",
            _mark_opts,
            index=_mark_opts.index(Config().cut_style),  # default from Config
            format_func=lambda v: {
                C.MARK_CROSS: "Center cross (recommended)",
                C.MARK_CENTER: "Center cut-lines (dashed — can show on cards)",
                C.MARK_TICKS: "Edge ticks (get clipped by some printers)",
                C.MARK_CORNERS: "Corner ticks",
                C.MARK_LINES: "Soft full lines",
                C.MARK_NONE: "None",
            }[v],
            help="Soft guides for the guillotine. The small center cross marks where "
                 "the two cuts meet but stays tiny, so it gets cut away and doesn't "
                 "show on the customer's card (a guillotine never lines up 100%, so "
                 "full lines would leave visible bits). Same cross prints on both sides.",
        )

    with s.expander("Logo"):
        cfg.logo_color = st.selectbox(
            "Logo color", [C.LOGO_GREEN, C.LOGO_BLACK, C.LOGO_WHITE, C.LOGO_ORIGINAL],
            format_func=str.title)
        cfg.logo_hex = st.color_picker("Brand green / custom color",
                                       value=C.BRAND_GREEN_HEX)
        st.session_state["logo_knockout"] = st.checkbox(
            "Knock out logo background", value=True,
            help="Make the logo's solid background transparent (needed for the "
                 "green-tile 'inverted' asset).")
        st.session_state["logo_tol"] = st.slider(
            "Background removal strength", 10, 120, 45, 5)
        cfg.front_logo_w = st.slider("Front logo width (in)", 0.6, 3.5,
                                     cfg.front_logo_w, 0.05)
        cfg.back_logo_w = st.slider("Back logo width (in)", 0.5, 3.0,
                                    cfg.back_logo_w, 0.05)

    with s.expander("Typography"):
        cfg.name_bold = st.checkbox("Bold customer name", value=True)
        cfg.name_size = st.slider("Front name size (pt)", 18.0, 96.0,
                                  cfg.name_size, 1.0)
        cfg.back_name_size = st.slider("Back name size (pt)", 14.0, 48.0,
                                       cfg.back_name_size, 1.0)
        cfg.item_size = st.slider("Meal-line size (pt)", 8.0, 20.0,
                                  cfg.item_size, 0.5)
        cfg.item_leading = st.slider("Meal-line spacing", 1.2, 2.5,
                                     cfg.item_leading, 0.1)
        cfg.back_title = st.text_input("Back label", cfg.back_title)

    with s.expander("Card dimensions & marks"):
        cfg.page_w = st.number_input("Page width (in)", value=cfg.page_w, step=0.25)
        cfg.page_h = st.number_input("Page height (in)", value=cfg.page_h, step=0.25)
        cfg.card_w = st.number_input("Card width (in)", value=cfg.card_w, step=0.05)
        cfg.card_h = st.number_input("Card height (in)", value=cfg.card_h, step=0.05)
        cfg.gutter_x = st.number_input("Gutter X (in)", value=cfg.gutter_x, step=0.05)
        cfg.gutter_y = st.number_input("Gutter Y (in)", value=cfg.gutter_y, step=0.05)
        cfg.card_pad = st.slider("Inner padding (in)", 0.1, 0.8, cfg.card_pad, 0.02)
        cfg.show_border = st.checkbox("Keyline border", value=cfg.show_border)
        cfg.show_divider = st.checkbox("Divider under back label",
                                       value=cfg.show_divider)

    return cfg


cfg = build_config()


# ===========================================================================
# Main — uploads
# ===========================================================================
col_a, col_b = st.columns(2)
with col_a:
    csv_file = st.file_uploader("① Weekly packing-sheet CSV", type=["csv"])
with col_b:
    logo_file = st.file_uploader("② Havn Club logo (PDF / PNG / JPG)",
                                 type=["pdf", "png", "jpg", "jpeg"])

# Use the uploaded logo if provided, otherwise fall back to the bundled Havn logo
# (the "inverted" PDF), so it's used on both sides with no upload needed.
logo_img = None
logo_bytes = logo_file.getvalue() if logo_file is not None else None
logo_name = logo_file.name if logo_file is not None else "havn_logo.pdf"
if logo_bytes is None and C.DEFAULT_LOGO.exists():
    logo_bytes = C.DEFAULT_LOGO.read_bytes()
    st.caption("Using the bundled Havn Club logo — upload one above to override.")
if logo_bytes is not None:
    logo_img = pdf.prepare_logo(
        pdf.load_logo(logo_bytes, logo_name), cfg.logo_color,
        knockout=st.session_state.get("logo_knockout", True),
        tol=st.session_state.get("logo_tol", 45),
        hex_color=cfg.logo_hex,
    )

if csv_file is None:
    st.info("Upload a packing-sheet CSV to begin. A logo is optional "
            "(a text wordmark is used if none is provided).")
    st.stop()


# ===========================================================================
# Parse CSV + meal-column configuration
# ===========================================================================
df = parser.read_sheet(csv_file.getvalue())
detected = parser.detect_meal_columns(df)

st.subheader("③ Meal columns")
st.caption("The menu changes weekly — confirm which columns are meals and edit "
           "the name printed on the card.")

selected = st.multiselect("Columns to treat as meals", options=detected,
                          default=detected)

display_names: dict[str, str] = {}
if selected:
    grid = st.columns(3)
    for i, col in enumerate(selected):
        with grid[i % 3]:
            display_names[col] = st.text_input(
                col, value=parser.prettify_column(col), key=f"disp_{col}")

customers = parser.build_customers(df, selected, display_names)


# ===========================================================================
# Preview
# ===========================================================================
st.subheader("④ Preview")
if not customers:
    st.warning("No customers detected. Check the CSV and meal-column selection.")
    st.stop()

pages, n_pages = pdf.build_pages(len(customers), cfg.ordering_mode)
m1, m2, m3 = st.columns(3)
m1.metric("Customers", len(customers))
m2.metric("Sheets (per side)", n_pages)
m3.metric("Meals mapped", len(selected))

# Show every excluded named row so a wrongly-dropped customer is caught at a
# glance (only driver/summary/section rows should ever appear here).
# getattr guard: after a deploy, Streamlit Cloud can briefly run a NEW app.py
# against a stale cached csv_parser module that predates this function — warn
# and degrade instead of crashing; a reboot clears it.
if hasattr(parser, "skipped_rows"):
    skipped = parser.skipped_rows(df, selected)
else:
    skipped = []
    st.warning("App update only partially loaded — use **Manage app → Reboot** "
               "(lower right) to finish updating.")
if skipped:
    with st.expander(f"Rows excluded from the print run ({len(skipped)}) — "
                     "check no real customer is listed here"):
        st.dataframe(
            pd.DataFrame(skipped, columns=["Row", "Why excluded"]),
            hide_index=True, use_container_width=True)

tab_cards, tab_names, tab_map = st.tabs(
    ["Sample cards", "Customer names", "Column mapping"])

with tab_cards:
    pick = st.selectbox("Preview customer", range(len(customers)),
                        format_func=lambda i: f"{i + 1}. {customers[i].name}")
    cust = customers[pick]
    if cust.is_plastic:
        st.warning(f"🟧 {cust.name} is a **PLASTIC** order.")
    pc1, pc2 = st.columns(2)
    with pc1:
        st.caption("FRONT — name")
        st.image(pdf.render_card_png(cust, "front", cfg, logo_img))
    with pc2:
        st.caption("BACK — meals")
        st.image(pdf.render_card_png(cust, "back", cfg, logo_img))

with tab_names:
    st.caption("Print order (route/stop order from the sheet).")
    st.dataframe(
        pd.DataFrame({
            "#": range(1, len(customers) + 1),
            "Name": [c.name for c in customers],
            "Type": [c.order_type for c in customers],
            "Meals": [", ".join(f"{q}× {n}" for n, q in c.items) or "—"
                      for c in customers],
        }),
        hide_index=True, use_container_width=True)

with tab_map:
    st.dataframe(
        pd.DataFrame({"CSV column": selected,
                      "Printed as": [display_names[c] for c in selected]}),
        hide_index=True, use_container_width=True)


# ===========================================================================
# Generate PDFs
# ===========================================================================
st.subheader("⑤ Generate & download")
if cfg.duplex_mode == C.DUPLEX_AUTO:
    st.caption("Print the cards **Two-Sided** — your printer does both sides. Then "
               "cut and stack (see below). Run the alignment test on plain paper first. "
               "Use **PNG** below if your printer garbles the PDF.")
else:
    st.caption("Print the fronts, flip the stack, then print the backs on the same "
               "sheets. Then cut and stack (see below). Test on plain paper first. "
               "Use **PNG** below if your printer garbles the PDF.")

if cfg.ordering_mode == C.ORDER_HOTDOG:
    st.info(
        "**Hot-dog cut & stack (2 cuts):**\n"
        "1. Keep the printed sheets in order and cut the whole stack **down the "
        "middle lengthwise** (hot-dog) → a left strip and a right strip.\n"
        "2. Put the **right strip on top of the left strip**.\n"
        "3. Cut the stack **across the middle**.\n"
        "4. Put the **pile that starts with #1 on top** of the other pile — the "
        "deck is now in customer order.\n\n"
        "The little cross in the middle marks where both cuts meet. (Customer #1 "
        "prints at the top-right of sheet 1.)")
elif cfg.ordering_mode == C.ORDER_CUT_STACK:
    st.info("**Cut-stack:** cut every sheet into its 4 cards, make 4 position-piles "
            "(top-left, top-right, bottom-right, bottom-left), then stack those "
            "piles in that order → the deck is in customer order.")

# --- Print scope: all / only customs / hand-picked ---------------------------
# For partial reprints (e.g. a batch that was missed, or one damaged card)
# without re-printing the whole run. The subset keeps route order and the
# cut-stack imposition works the same on it.
scope = st.radio(
    "Which customers?",
    ["All customers", "Only customs customers", "Pick specific customers"],
    horizontal=True,
)
if scope == "Only customs customers":
    print_customers = [c for c in customers if c.has_customs]
elif scope == "Pick specific customers":
    labels = [f"{i + 1}. {c.name}" for i, c in enumerate(customers)]
    picked = st.multiselect("Customers to print", labels)
    picked_idx = {labels.index(p) for p in picked}
    print_customers = [c for i, c in enumerate(customers) if i in picked_idx]
else:
    print_customers = customers

_, n_scope_pages = pdf.build_pages(len(print_customers), cfg.ordering_mode)
st.caption(f"**{len(print_customers)}** customer(s) → **{n_scope_pages}** sheet(s) per side."
           + ("  ⚠️ None selected." if not print_customers else ""))

# --- Output format: PDF or PNG images ---------------------------------------
# Some older printer drivers (e.g. an old HP) choke on a vector/text PDF and try
# to "convert" it. Flat PNG images print exactly as laid out. PNG downloads as a
# ZIP of one image per sheet-side, named in print order.
import io as _io
import zipfile as _zipfile

fmt_col, dpi_col = st.columns([2, 1])
with fmt_col:
    output_format = st.radio(
        "Output format",
        ["PDF", "PNG images (ZIP)"],
        horizontal=True,
        help="Choose PNG if your printer garbles the PDF — it prints the sheets as "
             "flat images. Same layout, ordering and cut marks either way.",
    )
_is_png = output_format.startswith("PNG")
with dpi_col:
    png_dpi = st.selectbox("Image quality", [300, 200, 150, 600],
                           index=0, disabled=not _is_png,
                           format_func=lambda d: f"{d} dpi", key="png_dpi") \
        if _is_png else 300


def _zip_named(named: list[tuple[str, bytes]]) -> bytes:
    """Zip a list of (filename, bytes) into a single archive."""
    buf = _io.BytesIO()
    with _zipfile.ZipFile(buf, "w", _zipfile.ZIP_DEFLATED) as z:
        for fname, data in named:
            z.writestr(fname, data)
    return buf.getvalue()


def _png_names(n_pages_total: int, i: int, sheet: int, side: str) -> str:
    """Print-ordered PNG filename, e.g. '02_sheet-01-back.png'."""
    width = max(2, len(str(n_pages_total)))
    return f"{i:0{width}d}_sheet-{sheet:02d}-{side}.png"


# --- Stale-output guard ------------------------------------------------------
# The download buttons serve PDFs saved in session_state by the last "Generate"
# click. If ANY input changes (a sidebar setting, the CSV, meal names, the logo),
# those saved PDFs no longer reflect what's on screen — so drop them and make the
# operator regenerate. Without this, toggles like "Rotate back 180°" appear to
# "not work" because the old file keeps downloading.
import hashlib as _hashlib
import json as _json
from dataclasses import asdict as _asdict

_fp_payload = {
    "cfg": _asdict(cfg),
    "csv": _hashlib.md5(csv_file.getvalue()).hexdigest(),
    "cols": selected,
    "names": display_names,
    "logo": _hashlib.md5(logo_bytes).hexdigest() if logo_bytes else "none",
    "scope": [c.name for c in print_customers],
    "format": output_format,
    "dpi": png_dpi,
}
_fingerprint = _hashlib.md5(
    _json.dumps(_fp_payload, sort_keys=True, default=str).encode()).hexdigest()
_pdf_keys = ("front_pdf", "back_pdf", "combined_pdf",
             "test_front", "test_back", "test_combined",
             "combined_zip", "cards_zip", "test_zip")
if st.session_state.get("pdf_fingerprint") != _fingerprint:
    stale = any(k in st.session_state for k in _pdf_keys)
    for k in _pdf_keys:
        st.session_state.pop(k, None)
    st.session_state["pdf_fingerprint"] = _fingerprint
    if stale:
        st.info("Settings changed — click Generate again to rebuild the output.")

def _combined_pngs(pdf_bytes: bytes) -> bytes:
    """Rasterize an interleaved front/back PDF into a print-ordered PNG ZIP."""
    pages = pdf.pdf_to_png_pages(pdf_bytes, dpi=png_dpi)
    total = len(pages)
    named = [(_png_names(total, k + 1, k // 2 + 1,
                         "front" if k % 2 == 0 else "back"), p)
             for k, p in enumerate(pages)]
    return _zip_named(named)


def _front_back_pngs(front_bytes: bytes, back_bytes: bytes) -> bytes:
    """Rasterize separate front/back PDFs into a ZIP with fronts/ and backs/ folders."""
    fpngs = pdf.pdf_to_png_pages(front_bytes, dpi=png_dpi)
    bpngs = pdf.pdf_to_png_pages(back_bytes, dpi=png_dpi)
    named = [(f"fronts/sheet-{k + 1:02d}.png", p) for k, p in enumerate(fpngs)]
    named += [(f"backs/sheet-{k + 1:02d}.png", p) for k, p in enumerate(bpngs)]
    return _zip_named(named)


g1, g2 = st.columns(2)
with g1:
    st.markdown("**Customer cards**")
    if cfg.duplex_mode == C.DUPLEX_AUTO:
        if st.button("Generate customer cards", type="primary",
                     disabled=not print_customers):
            with st.spinner("Building cards…"):
                _combined = pdf.generate_combined(print_customers, cfg, logo_img)
                if _is_png:
                    st.session_state["combined_zip"] = _combined_pngs(_combined)
                else:
                    st.session_state["combined_pdf"] = _combined
        if _is_png and "combined_zip" in st.session_state:
            st.download_button("⬇︎ hang_tags_png.zip", st.session_state["combined_zip"],
                               "hang_tags_png.zip", "application/zip")
            st.caption("Unzip, select **all** the images, and print **Two-Sided**. "
                       "They're numbered in print order (front, back, front, back…).")
        elif not _is_png and "combined_pdf" in st.session_state:
            st.download_button("⬇︎ hang_tags.pdf", st.session_state["combined_pdf"],
                               "hang_tags.pdf", "application/pdf")
            st.caption("Print this with **Two-Sided** on. One file = both sides.")
    else:
        if st.button("Generate customer cards", type="primary",
                     disabled=not print_customers):
            with st.spinner("Building cards…"):
                _fp = pdf.generate_front(print_customers, cfg, logo_img)
                _bp = pdf.generate_back(print_customers, cfg, logo_img)
                if _is_png:
                    st.session_state["cards_zip"] = _front_back_pngs(_fp, _bp)
                else:
                    st.session_state["front_pdf"] = _fp
                    st.session_state["back_pdf"] = _bp
        if _is_png and "cards_zip" in st.session_state:
            st.download_button("⬇︎ cards_png.zip", st.session_state["cards_zip"],
                               "cards_png.zip", "application/zip")
            st.caption("Print the **fronts/** images, flip the stack, then print "
                       "the **backs/** images.")
        elif not _is_png and "front_pdf" in st.session_state:
            st.download_button("⬇︎ front_cards.pdf", st.session_state["front_pdf"],
                               "front_cards.pdf", "application/pdf")
            st.download_button("⬇︎ back_cards.pdf", st.session_state["back_pdf"],
                               "back_cards.pdf", "application/pdf")

with g2:
    st.markdown("**Duplex alignment test**")
    st.caption("Numbered cards to verify alignment before using cardstock.")
    if st.button("Generate duplex test"):
        with st.spinner("Building test…"):
            if cfg.duplex_mode == C.DUPLEX_AUTO:
                _tpdf = pdf.generate_duplex_test_combined(cfg, n=8)
                if _is_png:
                    st.session_state["test_zip"] = _combined_pngs(_tpdf)
                else:
                    st.session_state["test_combined"] = _tpdf
            else:
                _tf, _tb = pdf.generate_duplex_test(cfg, n=8)
                if _is_png:
                    st.session_state["test_zip"] = _front_back_pngs(_tf, _tb)
                else:
                    st.session_state["test_front"] = _tf
                    st.session_state["test_back"] = _tb
    if _is_png and "test_zip" in st.session_state:
        st.download_button("⬇︎ duplex_test_png.zip", st.session_state["test_zip"],
                           "duplex_test_png.zip", "application/zip")
    elif not _is_png and "test_combined" in st.session_state:
        st.download_button("⬇︎ duplex_test.pdf", st.session_state["test_combined"],
                           "duplex_test.pdf", "application/pdf")
    elif not _is_png and "test_front" in st.session_state:
        st.download_button("⬇︎ duplex_test_front.pdf", st.session_state["test_front"],
                           "duplex_test_front.pdf", "application/pdf")
        st.download_button("⬇︎ duplex_test_back.pdf", st.session_state["test_back"],
                           "duplex_test_back.pdf", "application/pdf")
