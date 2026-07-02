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
        cfg.orientation = st.radio(
            "Orientation",
            [C.ORIENT_LANDSCAPE, C.ORIENT_PORTRAIT],
            format_func=lambda v: "Sideways / landscape (hang tag)"
            if v == C.ORIENT_LANDSCAPE else "Upright / portrait",
        )
        cfg.flip_mode = st.radio(
            "Flip mode (manual duplex)",
            [C.FLIP_LONG_EDGE, C.FLIP_SHORT_EDGE],
            format_func=lambda v: "Long edge (flip like a book)"
            if v == C.FLIP_LONG_EDGE else "Short edge (flip like a notepad)",
            help="Which way you turn the stack over between sides. Confirm with "
                 "the duplex test PDFs.",
        )
        cfg.ordering_mode = st.radio(
            "Card ordering",
            [C.ORDER_CUT_STACK, C.ORDER_SEQUENTIAL],
            format_func=lambda v: "Cut-stack (cut into 4 piles & stack)"
            if v == C.ORDER_CUT_STACK else "Sequential (plain page order)",
        )
        cfg.cut_lines = st.checkbox(
            "Cut lines (full lines for guillotine)", value=True)

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
st.subheader("⑤ Generate PDFs")
st.caption("Print **front_cards.pdf**, flip the stack, then print "
           "**back_cards.pdf** on the same sheets. Cut with the guillotine along "
           "the lines, then stack per the cut-stack order. Test on plain paper first.")

g1, g2 = st.columns(2)
with g1:
    st.markdown("**Customer cards**")
    if st.button("Generate customer cards", type="primary"):
        with st.spinner("Building card PDFs…"):
            st.session_state["front_pdf"] = pdf.generate_front(customers, cfg, logo_img)
            st.session_state["back_pdf"] = pdf.generate_back(customers, cfg, logo_img)
    if "front_pdf" in st.session_state:
        st.download_button("⬇︎ front_cards.pdf", st.session_state["front_pdf"],
                           "front_cards.pdf", "application/pdf")
        st.download_button("⬇︎ back_cards.pdf", st.session_state["back_pdf"],
                           "back_cards.pdf", "application/pdf")

with g2:
    st.markdown("**Duplex alignment test**")
    st.caption("Numbered cards to verify flip alignment before using cardstock.")
    if st.button("Generate duplex test"):
        with st.spinner("Building test PDFs…"):
            f, b = pdf.generate_duplex_test(cfg, n=8)
            st.session_state["test_front"] = f
            st.session_state["test_back"] = b
    if "test_front" in st.session_state:
        st.download_button("⬇︎ duplex_test_front.pdf", st.session_state["test_front"],
                           "duplex_test_front.pdf", "application/pdf")
        st.download_button("⬇︎ duplex_test_back.pdf", st.session_state["test_back"],
                           "duplex_test_back.pdf", "application/pdf")
