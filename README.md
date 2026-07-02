# Havn Club — Customer Hang-Tag Generator

A local Streamlit app that turns the **weekly packing-sheet CSV** + a **Havn logo**
into print-ready, premium customer hang tags. It produces **two PDFs** (front /
back) for **manual duplex printing** on 100 lb ivory cardstock, plus a **duplex
alignment test**.

- 4 cards per 8.5" × 11" sheet · card size 4.25" × 5.5"
- **Sideways (landscape) hang tags** — the name reads across the wide edge
  (toggle to portrait in the sidebar).
- **Front** = customer name (large, bold) + green Havn logo
- **Back** = customer name + the meals they ordered + green Havn logo
- **Green logo**: the supplied white-on-green "inverted" asset is auto-cleaned and
  recolored to brand green (`#0C200E`, adjustable with a color picker).
- **Full cut lines** edge-to-edge for a guillotine cutter (not corner ticks).
- **Cut-stack imposition**: print all sheets, cut the stack into 4 position-piles,
  stack them, and the cards come out in customer order.
- Nothing about the menu is hardcoded — meal columns are detected from the CSV
  each week and you rename them for printing.

## Run it

**Hosted (for your workers):** deploy once to Streamlit Community Cloud and share
the URL + password — see [DEPLOY.md](DEPLOY.md). Workers just open the link in a
browser; nothing to install.

**Local (on this Mac, for testing):**

```bash
./run.sh
```

The script creates a virtualenv, installs everything, and opens the app in your
browser. (Manual alternative: `pip install -r requirements.txt` then
`streamlit run app.py`.)

## Weekly steps

1. **Upload** the packing-sheet CSV and a logo (PDF/PNG/JPG).
2. **Confirm meal columns** and edit the name printed for each
   (e.g. `Chicken 2 (Basil Pesto)` → `Basil Pesto Chicken`).
3. **Preview** sample cards, the customer list, and the mapping.
4. **Generate** and download `front_cards.pdf` + `back_cards.pdf`.
5. Optionally generate the **duplex test** and print it on plain paper to confirm
   your flip mode lines up.

## Printing (manual duplex)

1. Print `front_cards.pdf`.
2. Flip the stack (long-edge = like a book, short-edge = like a notepad — set
   **Flip mode** in the sidebar to match your printer; confirm with the test).
3. Print `back_cards.pdf` on the same sheets.
4. Cut every sheet into 4 cards. Make 4 piles by position — **Top-Left,
   Top-Right, Bottom-Left, Bottom-Right** — then stack the piles (TL, TR, BR, BL).
   The deck is now in customer order.

## Files

| File | Purpose |
|------|---------|
| `app.py` | Streamlit UI, uploads, preview, downloads |
| `csv_parser.py` | CSV reading, customer filtering, quantity + name parsing |
| `pdf_generator.py` | Card rendering, cut-stack imposition, duplex flip, crop marks |
| `config.py` | All tunable settings (the sidebar builds this) |
| `fonts/` | DM Sans + Cormorant Garamond (falls back to Helvetica / Times) |

## Fonts

Bundled: **DM Sans** (body) and **Cormorant Garamond** (headings). If the TTFs are
missing the app falls back to Helvetica / Times-Roman automatically.
