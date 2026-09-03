"""Parse the catastrophe bond losses table.

This is the only place the source records capital LEAVING. Everything else in
this project measures issuance, which is an inflow; a written-down tranche is
an outflow, and the project question is about both directions.

Two tiers of fidelity, kept apart on purpose:

  VERBATIM   the seven table cells, copied exactly. A real HTML table with
             explicit cells, so this is a structural read and should be
             lossless -- the same mechanism as the deal index, which is the
             one table that has never produced a defect under review.

  DERIVED    numbers and statuses extracted FROM those cells, which are prose:
             "Principal reduced to $91.12m and extended to April 2029" is a
             sentence, not a figure. Derived fields carry confidence and
             evidence like every other mined value in this project.

Never overwrite a verbatim cell with a derived reading. If they disagree the
cell is right.
"""

import re
import sys
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from fetch import fetch                                   # noqa: E402
from parse_deal import _money_to_number, _clean           # noqa: E402

URL = "https://www.artemis.bm/cat-bond-losses/"

COLUMNS = ["cat_bond", "sponsor", "orig_size", "cause_of_loss",
           "loss_amount", "time_to_resolution", "date_of_loss"]

# Loss status, most specific first. A cell can say several things; the first
# match is the outcome that determines the principal.
#
# Ordering matters and is the classification policy: "TBC. Mark-to-market
# implied ~80% to ~90% loss" is an ESTIMATE, not a settled loss, and must not
# be counted as realised capital leaving. Confirmed outcomes are checked before
# estimates for that reason.
STATUS_CUES = [
    ("total_loss", r"100%\s*loss|reduced to zero|total loss|full loss of principal"),
    ("repaid_in_full", r"repaid in full|returned in full|redeemed in full|"
                       r"recovered to par|no loss|matured with no|would not be"),
    ("partial_loss", r"principal\s+(?:\w+\s+){0,2}reduced|reduced (?:down )?to|"
                     r"reduced by|partial loss|written down|pay ?out|paid out|"
                     r"recovered by sponsor|of principal returned|"
                     r"reduction in principal|loss payments|"
                     r"[\d,.]+\s*(?:m|million)?\s+(?:recovered|returned)"),
    ("marked_to_market", r"mark(?:ed)?[- ]to[- ]market|marked down|implied"),
    ("marked_at_risk", r"marked (?:for|as)|at[- ]risk|considered at risk|reserve"),
    ("extended", r"extended to|maturity extended|remaining .* extended"),
]

# A cell that is nothing but a money figure states the loss amount directly.
BARE_AMOUNT_RE = re.compile(
    r"^(?:A|C|NZ|US|HK)?[$€£¥][\d,.]+\s*(?:m|million|bn|billion)?\.?$",
    re.IGNORECASE)

# "$60m - 30% loss of principal", "35% of $150m Class B notes - $52.5m":
# an amount stated alongside its percentage. The amount is the loss.
AMOUNT_WITH_PCT_RE = re.compile(
    r"(?:A|C|NZ|US|HK)?[$€£¥][\d,.]+\s*(?:m|million|bn|billion)?[^.]{0,40}?\d+(?:[.,]\d+)?\s*%\s*loss|"
    r"\d+(?:[.,]\d+)?\s*%[^.]{0,40}?[-–]\s*(?:A|C|NZ|US|HK)?[$€£¥][\d,.]+", re.IGNORECASE)

# The source's own placeholders, as in the deal directory: an unknown, not a
# zero. Counting these as no-loss would understate outflows.
PLACEHOLDERS = {"?", "tbc", "tbc.", "n/a", "-", "unknown", ""}

def _pct_range(text):
    """(low, high) percent loss. Ranges are common: "~80% to ~90% loss"."""
    m = re.search(r"~?\s*(\d+(?:[.,]\d+)?)\s*%\s*(?:to|-|\u2013)\s*~?\s*"
                  r"(\d+(?:[.,]\d+)?)\s*%", text, re.IGNORECASE)
    if m:
        return (float(m.group(1).replace(",", ".")),
                float(m.group(2).replace(",", ".")))
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*%\s*(?:loss|of principal)", text, re.IGNORECASE)
    if m:
        v = float(m.group(1).replace(",", "."))
        return (v, v)
    return (None, None)


def _remaining_principal(text):
    """'Principal reduced to $91.12m' -> the REMAINING principal, not the loss.

    The distinction matters: the cell states what is LEFT, and the loss is the
    original size minus that. Reading it as the loss would invert the figure.
    """
    m = re.search(r"reduced (?:down )?to\s*(\$[\d,.]+\s*(?:m|million|bn|billion)?)",
                  text, re.IGNORECASE)
    if m:
        return _clean(m.group(1))
    if re.search(r"reduced to zero|100%\s*loss|full loss of principal", text, re.IGNORECASE):
        return "$0"
    return None


def parse_losses(html):
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", id="tablepress-2") or soup.find("table")
    if table is None:
        raise SystemExit("losses table not found")

    records = []
    for tr in table.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) < len(COLUMNS):
            continue                      # header row uses <th>
        row = {c: _clean(cells[i].get_text(" ", strip=True))
               for i, c in enumerate(COLUMNS)}

        # The join key: many rows link to the deal page, which is how this
        # table connects to the issuance side.
        link = cells[0].find("a", href=True)
        row["deal_url"] = link["href"] if link and "/deal-directory/" in link["href"] else None
        row["deal_slug"] = (row["deal_url"].rstrip("/").rsplit("/", 1)[-1]
                            if row["deal_url"] else None)

        # ---- derived, from the prose in `loss_amount` ---------------------
        loss = row["loss_amount"]
        bare = loss.strip().lower() in PLACEHOLDERS

        status, cue = None, None
        if bare:
            status = None                      # the source is silent, not zero
        elif BARE_AMOUNT_RE.match(loss.strip()):
            status, cue = "stated_amount", loss.strip()
        elif AMOUNT_WITH_PCT_RE.search(loss):
            status = "stated_amount"
            cue = AMOUNT_WITH_PCT_RE.search(loss).group(0)[:40]
        else:
            for name, pattern in STATUS_CUES:
                m = re.search(pattern, loss, re.IGNORECASE)
                if m:
                    status, cue = name, m.group(0)
                    break
        row["loss_status"] = status
        row["loss_status_cue"] = cue
        row["source_placeholder"] = loss.strip() if bare else None

        lo, hi = _pct_range(loss)
        row["loss_pct_low"], row["loss_pct_high"] = lo, hi
        rem_text = _remaining_principal(loss)
        if rem_text is None and status == "total_loss":
            # Keep the two readings consistent: if the status says the whole
            # principal went, the remainder is zero regardless of which phrase
            # the cell happened to use.
            rem_text = "$0"
        row["principal_remaining"] = rem_text

        orig = _money_to_number(row["orig_size"])
        rem = _money_to_number(row["principal_remaining"] or "")
        if status == "stated_amount":
            row["loss_amount_derived"] = _money_to_number(loss)
        elif orig is not None and rem is not None:
            row["loss_amount_derived"] = orig - rem
        elif orig is not None and lo is not None and lo == hi:
            row["loss_amount_derived"] = orig * lo / 100.0
        else:
            row["loss_amount_derived"] = None

        row["loss_pct_derived"] = (
            round(100 * row["loss_amount_derived"] / orig, 2)
            if row["loss_amount_derived"] is not None and orig else None)

        # Is this a realised loss or an estimate? Only the former is capital
        # that has actually left.
        row["is_settled"] = status in ("total_loss", "partial_loss",
                                       "stated_amount", "repaid_in_full")
        row["derived_confidence"] = (
            "high" if status in ("total_loss", "stated_amount", "repaid_in_full")
            else "medium" if status in ("partial_loss",)
            else "low" if status else None)

        records.append(row)

    return pd.DataFrame(records)


def main():
    df = parse_losses(fetch(URL))
    out = ROOT / "data" / "losses.csv"
    df.to_csv(out, index=False, encoding="utf-8")
    print("wrote %s  (%d rows x %d cols)" % (out, len(df), len(df.columns)))

    print("\n=== verbatim completeness (should be 100%%) ===")
    for c in COLUMNS:
        filled = (df[c].astype(str).str.strip() != "").sum()
        print("  %-20s %3d/%d  %5.1f%%" % (c, filled, len(df), 100 * filled / len(df)))

    print("\n=== join to the issuance side ===")
    print("  rows linking to a deal page: %d of %d (%.0f%%)"
          % (df.deal_slug.notna().sum(), len(df),
             100 * df.deal_slug.notna().mean()))

    print("\n=== derived (prose-mined, NOT verbatim) ===")
    print(df.loss_status.value_counts(dropna=False).to_string())
    print("\n  a percent loss stated:   %d" % df.loss_pct_low.notna().sum())
    print("  principal remaining:     %d" % df.principal_remaining.notna().sum())
    print("  loss amount computable:  %d" % df.loss_amount_derived.notna().sum())
    print("  source placeholder (?):  %d" % df.source_placeholder.notna().sum())

    settled = df[df.is_settled & df.loss_amount_derived.notna()]
    print("\n=== realised outflow, settled rows only ===")
    print("  %d rows, $%.2fbn of principal lost"
          % (len(settled), settled.loss_amount_derived.sum() / 1e9))
    est = df[(~df.is_settled) & df.loss_pct_high.notna()]
    print("  %d further rows carry only an ESTIMATE and are excluded" % len(est))


if __name__ == "__main__":
    main()
