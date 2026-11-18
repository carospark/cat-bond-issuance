"""Loss timing by deal: the roll-forward under --loss-timing loss against
--loss-timing settlement, row by row, so the yearly gaps in HANDOFF.md can be
traced to the deals that open them.

    ./.venv/bin/python src/compare_loss_timing.py [--as-of YYYY-MM] [--no-write]

Outputs (data/validation_dashboards/):

    loss_timing_by_deal.csv   one row per settled, linked, amount-bearing loss
                              row: the loss month the default run uses, the
                              settlement month the alternative reads (blank
                              with its reason when the row states none),
                              months apart, and the deal's year-end stock
                              difference (settlement minus loss) for every
                              December it touches
    loss_timing_by_year.csv   closing stock and gap to the publisher under both
                              settings, their difference, and the deals that
                              account for the largest share of it each year

The by-deal differences are exact: each deal's ledger is rebuilt alone under
both settings, so a deal whose remainder also repays later under settlement
shows that too: the ledger repays the remainder at the later of the maturity
and the last settled loss, and under settlement the last loss is the
settlement month, so a deal with a small loss settled years after its
maturity is held whole until then. `deal_diff_mechanism` says which it is:
`write_down_moved` when the largest year-end difference is within the deal's
settled loss, `remainder_held_to_settlement` when it exceeds it. Nothing
here changes either run; both come from `roll_forward.build`.
"""
import argparse
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import net_supply as ns  # noqa: E402
import roll_forward as rf  # noqa: E402

DASH_OUT = rf.DASH_OUT
CLASS_RE = re.compile(r"\bClass\s+([A-Z0-9][A-Z0-9-]{0,5})\b", re.I)
TOP_N = 3


def _year_end(book, as_of):
    """Year -> closing stock for the deals in `book` alone."""
    if book.empty:
        return pd.Series(dtype=float)
    y = rf.outstanding_by_year(rf.monthly_flows(book), as_of)
    return y.set_index("year").outstanding


def deal_year_end_diffs(book_loss, book_set, as_of=rf.AS_OF):
    """{slug: {year: settlement_minus_loss}} for every deal whose two ledgers
    differ at any December (or the as-of month), each deal rebuilt alone."""
    touched = set(book_set.loc[book_set["flags"].str.contains("loss_timing=settlement|loss_settlement_unknown", na=False), "slug"])
    out = {}
    for slug in sorted(touched):
        a = _year_end(book_loss[book_loss.slug == slug], as_of)
        b = _year_end(book_set[book_set.slug == slug], as_of)
        years = sorted(set(a.index) | set(b.index))
        diffs = {int(y): round(float(b.get(y, 0.0)) - float(a.get(y, 0.0)), 3) for y in years}
        diffs = {y: d for y, d in diffs.items() if abs(d) > 1e-6}
        if diffs:
            out[slug] = diffs
    return out


def _fmt_diffs(diffs):
    return ";".join("%d:%+.1f" % (y, d) for y, d in sorted(diffs.items()))


def mechanism(diffs, settled_loss_m):
    """'write_down_moved' when the largest year-end difference is within the
    deal's settled loss, 'remainder_held_to_settlement' when it exceeds it
    (the remainder's repay month followed the settlement month), '' when
    the ledgers do not differ."""
    if not diffs:
        return ""
    peak = max(abs(v) for v in diffs.values())
    return "remainder_held_to_settlement" if peak > settled_loss_m + 1e-6 else "write_down_moved"


def by_deal(losses, book_loss, book_set, as_of=rf.AS_OF):
    """One row per settled, linked, amount-bearing loss row."""
    diffs = deal_year_end_diffs(book_loss, book_set, as_of)
    names = dict(zip(book_loss.slug, book_loss.issuer_name)) if "issuer_name" in book_loss.columns else {}
    settled = dict(zip(book_loss.slug, book_loss.written_down_m))
    in_book = set(book_loss.slug)
    rows = []
    linked = losses[(losses.deal_slug.str.strip() != "") & (losses.is_settled == "True")
                    & (losses.loss_amount_derived.astype(str).str.strip() != "")]
    for r in linked.itertuples(index=False):
        lm, imputed = rf.loss_month(r.date_of_loss)
        sm, flag = rf.settlement_month(r, lm) if lm else (None, "loss_undated_not_applied")
        amount = float(r.loss_amount_derived) / 1e6
        ccy = rf._currency(str(r.orig_size or ""))
        fx = ""
        if ccy and ccy != "USD":
            rate = ns.load_fx().get((ccy, lm)) if lm else None
            if rate:
                amount, fx = amount * rate, "converted_from_%s" % ccy
            else:
                fx = "rate_missing_%s" % ccy
        m = CLASS_RE.search(str(r.cat_bond or ""))
        stated = sm if flag != "loss_settlement_unknown" else None
        d = diffs.get(r.deal_slug, {})
        rows.append({
            "deal_slug": r.deal_slug,
            "deal": names.get(r.deal_slug, ""),
            "loss_row": r.cat_bond,
            "class": m.group(1) if m else "",
            "in_book": r.deal_slug in in_book,
            "loss_amount_usd_m": round(amount, 3),
            "loss_fx": fx,
            "loss_month": lm or "",
            "loss_month_imputed": bool(imputed),
            "settlement_month": stated or "",
            "settlement_basis": flag,
            "months_apart": (rf.month_index(stated) - rf.month_index(lm)) if (stated and lm) else "",
            "time_to_resolution": r.time_to_resolution,
            "deal_settled_loss_usd_m": round(float(settled.get(r.deal_slug, 0.0)), 3),
            "deal_year_end_diff_m": _fmt_diffs(d),
            "deal_max_abs_diff_m": round(max((abs(v) for v in d.values()), default=0.0), 3),
            "deal_cum_abs_diff_m": round(sum(abs(v) for v in d.values()), 3),
            "deal_diff_mechanism": mechanism(d, float(settled.get(r.deal_slug, 0.0))),
        })
    cols = ["deal_slug", "deal", "loss_row", "class", "in_book", "loss_amount_usd_m", "loss_fx", "loss_month",
            "loss_month_imputed", "settlement_month", "settlement_basis", "months_apart", "time_to_resolution",
            "deal_settled_loss_usd_m", "deal_year_end_diff_m", "deal_max_abs_diff_m", "deal_cum_abs_diff_m",
            "deal_diff_mechanism"]
    out = pd.DataFrame(rows, columns=cols)
    return out.sort_values(["deal_cum_abs_diff_m", "deal_slug", "loss_month"], ascending=[False, True, True]).reset_index(drop=True)


def by_year(flows_loss, flows_set, diffs, theirs=None, as_of=rf.AS_OF, top_n=TOP_N):
    """Closing stock under both settings per year, the publisher beside them
    when given, and the deals accounting for the largest share of each
    year's difference."""
    a = rf.outstanding_by_year(flows_loss, as_of).set_index("year").outstanding
    b = rf.outstanding_by_year(flows_set, as_of).set_index("year").outstanding
    years = sorted(set(a.index) | set(b.index))
    per_year = {}
    for slug, d in diffs.items():
        for y, v in d.items():
            per_year.setdefault(y, []).append((slug, v))
    rows = []
    for y in years:
        la, lb = float(a.get(y, 0.0)), float(b.get(y, 0.0))
        diff = lb - la
        contributors = sorted(per_year.get(y, []), key=lambda t: -abs(t[1]))
        total_abs = sum(abs(v) for _, v in contributors) or 1.0
        top = ";".join("%s:%+.1f(%.0f%%)" % (s, v, 100 * abs(v) / total_abs) for s, v in contributors[:top_n])
        rows.append({"year": y, "outstanding_loss": round(la, 3), "outstanding_settlement": round(lb, 3),
                     "settlement_minus_loss": round(diff, 3), "deals_differing": len(contributors),
                     "top_deals": top})
    out = pd.DataFrame(rows)
    if theirs is not None and not theirs.empty:
        out = out.merge(theirs[["year", "artemis_outstanding"]], on="year", how="left")
        out["gap_loss"] = (out.outstanding_loss - out.artemis_outstanding).round(3)
        out["gap_settlement"] = (out.outstanding_settlement - out.artemis_outstanding).round(3)
        out = out[["year", "outstanding_loss", "outstanding_settlement", "artemis_outstanding", "gap_loss",
                   "gap_settlement", "settlement_minus_loss", "deals_differing", "top_deals"]]
    return out


def ranking(diffs, names=None, settled=None, n=10):
    """The deals that open the largest cumulative year-end differences."""
    names, settled = names or {}, settled or {}
    rows = [{"deal_slug": s, "deal": names.get(s, ""), "cum_abs_diff_m": round(sum(abs(v) for v in d.values()), 3),
             "max_abs_diff_m": round(max(abs(v) for v in d.values()), 3),
             "settled_loss_m": round(float(settled.get(s, 0.0)), 3),
             "mechanism": mechanism(d, float(settled.get(s, 0.0))),
             "years": "%d-%d" % (min(d), max(d)) if len(d) > 1 else str(min(d)),
             "year_end_diff_m": _fmt_diffs(d)} for s, d in diffs.items()]
    out = pd.DataFrame(rows, columns=["deal_slug", "deal", "cum_abs_diff_m", "max_abs_diff_m", "settled_loss_m",
                                      "mechanism", "years", "year_end_diff_m"])
    return out.sort_values(["cum_abs_diff_m", "deal_slug"], ascending=[False, True]).head(n).reset_index(drop=True)


def compare_frames(deals, losses, as_of=rf.AS_OF, theirs=None, exclude_mortgage=True, **kw):
    """The three tables from in-memory deal and loss frames (tests, and the
    atlas side). `kw` goes to `deal_book` (trace, classes, tranches)."""
    books = {}
    flows = {}
    for timing in ("loss", "settlement"):
        b = rf.deal_book(deals, losses, as_of, loss_timing=timing, **kw)
        b = rf.select_book(b, exclude_mortgage)
        books[timing] = b
        flows[timing] = rf.monthly_flows(b, losses[losses.link_method == "unlinked"] if "link_method" in losses.columns else None)
    diffs = deal_year_end_diffs(books["loss"], books["settlement"], as_of)
    names = dict(zip(books["loss"].slug, books["loss"].issuer_name))
    settled = dict(zip(books["loss"].slug, books["loss"].written_down_m))
    return (by_deal(losses, books["loss"], books["settlement"], as_of),
            by_year(flows["loss"], flows["settlement"], diffs, theirs, as_of),
            ranking(diffs, names, settled))


def compare(as_of=rf.AS_OF, trace_path="auto", classes_path="auto"):
    """The three tables from the parsed tables under data/, with the
    publisher's outstanding series beside the yearly one."""
    deals = pd.read_csv(rf.ROOT / "data" / "deals.csv", keep_default_na=False, dtype=str)
    losses = rf.link_losses(pd.read_csv(rf.ROOT / "data" / "losses.csv", keep_default_na=False, dtype=str), deals)
    path = rf.resolve_trace_path(trace_path)
    trace = rf.load_trace_maturities(path) if path else None
    cpath = rf.resolve_classes_path(classes_path) if path else None
    classes = rf.load_class_maturities(path, cpath) if cpath else None
    tranches = pd.read_csv(rf.ROOT / "data" / "tranches.csv", keep_default_na=False, dtype=str) if cpath else None
    theirs = ns.dashboard_series()[["year", "artemis_outstanding"]]
    return compare_frames(deals, losses, as_of, theirs, trace=trace, classes=classes, tranches=tranches)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--as-of", default=rf.AS_OF)
    ap.add_argument("--trace-maturities", default="auto", metavar="PATH")
    ap.add_argument("--cusip-classes", default="auto", metavar="PATH")
    ap.add_argument("--no-write", action="store_true", help="print the ranking, write no files")
    args = ap.parse_args()
    deal_rows, year_rows, top = compare(args.as_of, args.trace_maturities, args.cusip_classes)
    pd.set_option("display.width", 250)
    n_stated = int((deal_rows.settlement_month != "").sum())
    per_deal = deal_rows.drop_duplicates("deal_slug")
    print("settled, linked, amount-bearing loss rows: %d; with a settlement month: %d; deals whose ledgers differ: %d "
          "(write-down moved: %d; remainder held to settlement: %d)"
          % (len(deal_rows), n_stated, int((per_deal.deal_cum_abs_diff_m > 0).sum()),
             int((per_deal.deal_diff_mechanism == "write_down_moved").sum()),
             int((per_deal.deal_diff_mechanism == "remainder_held_to_settlement").sum())))
    print("\nyear by year ($m):")
    print(year_rows[year_rows.year >= 2010].to_string(index=False))
    print("\nten deals opening the largest cumulative year-end differences ($m, settlement minus loss):")
    print(top.to_string(index=False))
    if args.no_write:
        return
    DASH_OUT.mkdir(exist_ok=True)
    deal_rows.to_csv(DASH_OUT / "loss_timing_by_deal.csv", index=False)
    year_rows.to_csv(DASH_OUT / "loss_timing_by_year.csv", index=False)
    print("\nwrote data/validation_dashboards/loss_timing_by_deal.csv, data/validation_dashboards/loss_timing_by_year.csv")


if __name__ == "__main__":
    main()
