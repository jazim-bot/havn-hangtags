"""
csv_parser.py — Read a Havn Club weekly packing-sheet CSV and turn it into a
clean list of customer orders.

The weekly export mixes real customer rows with junk:
  * a header row (Customer, Order Count, Type, Customizations, <meals...>, Stop)
  * driver rows          e.g. "Driver 1 — 3 stops"
  * route-total rows     Customizations == "ROUTE TOTAL"
  * grand-total row      Customizations == "GRAND TOTAL"
  * section headers      e.g. "Pending Address — 1 orders (not routed)"
  * blank spacer rows

We keep ONLY genuine customers, and we do NOT hardcode the meal columns — the
menu changes every week, so meal columns are detected dynamically as "any column
that isn't one of the fixed structural columns".
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

import pandas as pd

# The fixed, structural columns that are present every week. Everything else
# between them (the variable middle of the sheet) is treated as a meal column.
RESERVED_COLS = {"customer", "order count", "type", "customizations", "stop"}


@dataclass
class Customer:
    """One real customer order, ready to be printed on a card."""
    name: str                       # title-cased display name, e.g. "Kirsten Wilson"
    order_type: str = ""            # "Glass" / "Plastic"
    items: list = field(default_factory=list)  # [(display_name, qty), ...] qty>0
    stop: str = ""
    is_plastic: bool = False


# ---------------------------------------------------------------------------
# Reading the file
# ---------------------------------------------------------------------------
def read_sheet(file_bytes: bytes) -> pd.DataFrame:
    """
    Load the CSV into a DataFrame with EVERY cell kept as a raw string.

    Why all-strings: meal cells can look like "2", "(1)" or "1 (1)". If pandas
    guessed dtypes it might turn "(1)" into a number or NaN and we'd lose the
    custom-count. We also keep blanks as "" (not NaN) so downstream code is
    simple. UTF-8 with a BOM-tolerant decode keeps em-dashes / accents intact.
    """
    text = file_bytes.decode("utf-8-sig", errors="replace")
    df = pd.read_csv(
        io.StringIO(text),
        dtype=str,
        keep_default_na=False,  # blank -> "" instead of NaN
        na_filter=False,
    )
    # Normalise column names (strip stray whitespace) but keep original casing
    # so the operator recognises them.
    df.columns = [str(c).strip() for c in df.columns]
    return df


def detect_meal_columns(df: pd.DataFrame) -> list[str]:
    """Return the columns that look like meal columns (everything non-structural)."""
    return [c for c in df.columns if c.strip().lower() not in RESERVED_COLS]


def _col(df: pd.DataFrame, name: str) -> str | None:
    """Case-insensitive lookup of a structural column's real header."""
    for c in df.columns:
        if c.strip().lower() == name:
            return c
    return None


# ---------------------------------------------------------------------------
# Quantity parsing
# ---------------------------------------------------------------------------
def parse_qty(cell: str) -> int:
    """
    Turn a meal cell into the TOTAL number of that meal the customer receives.

    Havn notation:  "2"      -> 2 regular            -> 2
                    "(1)"    -> 1 custom             -> 1
                    "1 (1)"  -> 1 regular + 1 custom -> 2
                    ""       -> nothing              -> 0
    A custom meal is still a physical meal that gets packed, so it counts toward
    the total shown on the hang tag. We sum the leading regular number and every
    parenthesised custom number.
    """
    s = str(cell).strip()
    if not s:
        return 0
    total = 0
    lead = re.match(r"^\s*(\d+)", s)      # regular count at the start
    if lead:
        total += int(lead.group(1))
    for m in re.findall(r"\((\d+)\)", s):  # each custom count in parens
        total += int(m)
    return total


# ---------------------------------------------------------------------------
# Row classification
# ---------------------------------------------------------------------------
def _is_customer_row(row: pd.Series, cust_col, type_col, customz_col, meal_cols) -> bool:
    """
    Decide whether a row is a genuine customer we should print a card for.

    Rejects, in order:
      * blank customer name
      * driver rows            ("Driver" anywhere in the name)
      * total rows             ("TOTAL" in the Customizations cell)
      * section headers / spacers (no order Type AND no meals) — e.g.
        "Pending Address — 1 orders (not routed)"
    A real customer always has an order Type (Glass/Plastic) or at least one meal.
    """
    name = str(row.get(cust_col, "")).strip()
    if not name:
        return False
    if "driver" in name.lower():
        return False

    customz = str(row.get(customz_col, "")).strip().lower() if customz_col else ""
    # Reject ONLY the summary rows. Match the exact phrases — a bare "total"
    # test also matched customer notes like "Partial customs- 2 total" /
    # "All are customs- 5 total" and silently dropped every customs customer.
    if "route total" in customz or "grand total" in customz:
        return False

    order_type = str(row.get(type_col, "")).strip() if type_col else ""
    has_meal = any(parse_qty(row.get(m, "")) > 0 for m in meal_cols)
    if not order_type and not has_meal:
        return False                  # section header / empty routing row

    return True


def title_case_name(raw: str) -> str:
    """
    "KIRSTEN WILSON" -> "Kirsten Wilson".  Handles hyphens ("Yi-An Ko") and
    keeps short initials sensible ("L S", "D D"). Uses str.title() with a light
    touch-up for apostrophes (O'Brien).
    """
    name = str(raw).strip()
    titled = name.title()
    # Fix apostrophe-caps: "O'Brien".title() -> "O'Brien" already ok in py3.
    return titled


# ---------------------------------------------------------------------------
# Building the customer list
# ---------------------------------------------------------------------------
def build_customers(
    df: pd.DataFrame,
    meal_columns: list[str],
    display_names: dict[str, str],
) -> list[Customer]:
    """
    Produce the ordered list of Customer objects to print.

    Order is preserved exactly as the rows appear in the sheet, which is already
    route/stop order — that becomes the "customer order" the cut-stack imposition
    reproduces after cutting and stacking.

    `meal_columns`  : the CSV columns the operator marked as meals (a subset).
    `display_names` : {csv_column: pretty label to print}, e.g.
                      {"Chicken 2 (Basil Pesto)": "Basil Pesto Chicken"}.
    """
    cust_col = _col(df, "customer")
    type_col = _col(df, "type")
    customz_col = _col(df, "customizations")
    stop_col = _col(df, "stop")

    customers: list[Customer] = []
    for _, row in df.iterrows():
        if not _is_customer_row(row, cust_col, type_col, customz_col, meal_columns):
            continue

        items = []
        for col in meal_columns:            # keep sheet column order
            qty = parse_qty(row.get(col, ""))
            if qty > 0:
                label = display_names.get(col, col)
                items.append((label, qty))

        order_type = str(row.get(type_col, "")).strip() if type_col else ""
        customers.append(
            Customer(
                name=title_case_name(row.get(cust_col, "")),
                order_type=order_type,
                items=items,
                stop=str(row.get(stop_col, "")).strip() if stop_col else "",
                is_plastic="plastic" in order_type.lower(),
            )
        )
    return customers


def skipped_rows(df: pd.DataFrame, meal_columns: list[str]) -> list[tuple[str, str]]:
    """
    Return (name, reason) for every NON-blank Customer cell that was excluded.
    Shown in the app so a wrongly-dropped customer is visible immediately instead
    of silently missing from the print run.
    """
    cust_col = _col(df, "customer")
    type_col = _col(df, "type")
    customz_col = _col(df, "customizations")
    out: list[tuple[str, str]] = []
    for _, row in df.iterrows():
        name = str(row.get(cust_col, "")).strip()
        if not name:
            continue  # blank spacer — not worth listing
        if _is_customer_row(row, cust_col, type_col, customz_col, meal_columns):
            continue
        if "driver" in name.lower():
            reason = "driver row"
        else:
            customz = str(row.get(customz_col, "")).strip().lower() if customz_col else ""
            if "route total" in customz or "grand total" in customz:
                reason = "summary row"
            else:
                reason = "no order type and no meals (section header?)"
        out.append((name, reason))
    return out


# ---------------------------------------------------------------------------
# Pretty default display name for a meal column
# ---------------------------------------------------------------------------
def prettify_column(col: str) -> str:
    """
    Suggest a human display name for a raw meal column header. The operator can
    always override it in the UI.

      "Chicken 2 (Basil Pesto)"  -> "Basil Pesto Chicken"
      "Seafood 2 (Green Goddess)"-> "Green Goddess Seafood"
      "Oats (Chocolate Overnight)"->"Chocolate Overnight Oats"
      "Date Balls"               -> "Date Balls"
      "Shots"                    -> "Shots"

    Rule: if the header is "<Base> [n] (<Descriptor>)", combine as
    "<Descriptor> <Base>". Otherwise drop a trailing column-index number and keep
    the header as-is.
    """
    m = re.match(r"^\s*([A-Za-z][A-Za-z ]*?)\s*\d*\s*\((.+)\)\s*$", col)
    if m:
        base = m.group(1).strip()
        descriptor = m.group(2).strip()
        return f"{descriptor} {base}".strip()
    return re.sub(r"\s*\d+\s*$", "", col).strip() or col
