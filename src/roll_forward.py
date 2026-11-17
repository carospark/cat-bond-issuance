"""Outstanding principal as a deal-level roll-forward.

    outstanding(t) = sum over deals of
        issued                      at the issue month
      - principal written down      at the loss month (losses.csv)
      + principal recovered         where the table says it came back to investors
      - principal repaid            at the scheduled maturity, or later when the
                                    deal was extended, for what is still there

The amount that matures is what is left after write-downs, so a lost dollar is
never also counted as repaid (the double subtraction the old approximation in
net_supply.py accepted). Extensions hold principal past the scheduled maturity:
to the stated extension date where the losses table gives one, otherwise to
the as-of date while the loss is unresolved. A deal with no maturity on its
page takes the TRACE maturity of its bridged CUSIPs where the companion
repository's bridge has one, else an imputed term and a flag; coverage is
reported by issued dollars.

Maturity precedence, per deal (`maturity_source`):

    stated      the page states a maturity; kept when TRACE agrees within
                TRACE_TOLERANCE_MONTHS (flag trace_corroborates_stated=+Nm);
                replaced by TRACE only when TRACE is LATER than the page by
                more than that (trace_maturity_overrides_stated=+Nm: the page
                gave a one-year class's or a predecessor's date) or when the
                page date was a per-class vote; a page date later than TRACE
                stands and is flagged page_later_than_trace=+Nm, since the
                bridge may hold only a deal's short classes while the page
                names its longest
    trace       the TRACE maturity of the deal's bridged CUSIPs: the month
                shared by most of them, the latest on a tie; replaces a
                term-derived or imputed page maturity, flagged with the
                difference and with trace_maturity_tranches_disagree when the
                CUSIPs do not share one month
    derived_from_term, imputed_*   as before, where no TRACE maturity exists

The bridge is read with --trace-maturities PATH (default: the sibling
analysis repository's data/bridge.csv when present; --no-trace-maturities
turns it off, and the module runs without the analysis repository).

Inputs are the parsed tables under data/ (gitignored). Outputs:

    data/outstanding_rollforward.csv   year-end stock, flows, publisher series
    data/outstanding_deals.csv         one row per deal: dates, sources, flags
    data/validation_dashboards/outstanding.csv   ours vs Artemis, with coverage
    data/validation_dashboards/maturities.csv    upcoming maturities by quarter

Every rule here is a documented convention, not a fact read from a page; the
flags on each deal say which conventions touched it.
"""

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import net_supply as ns                                  # noqa: E402
from parse_deal import _money_to_number, _currency       # noqa: E402

OUT = ROOT / "data"
DASH_OUT = OUT / "validation_dashboards"

# The directory snapshot the parsed tables come from (index fetched 2026-08-29).
# The publisher's current-year "outstanding" is the stock at that date, so the
# final year is measured here rather than at year end.
AS_OF = "2026-08"

# Imputed terms for deals whose page states neither a maturity nor a term:
# medians of the stated issue-to-maturity span, 36.5 months for public deals
# (n=226) and 12 months for private placements (n=124), measured 2026-10-25.
IMPUTED_TERM_MONTHS = {"public": 36, "private": 12}

# TRACE maturities for the bridged deals: one row per (Artemis deal, CUSIP)
# in the companion repository's strict bridge. Read when present, never
# required. A page-stated maturity within this many months of the TRACE
# month is kept (the page states months, TRACE the legal final; TRACE sits
# one month later than the page in 44% of stated deals and 44% of
# term-derived ones, measured 2026-11-17); beyond it TRACE wins, flagged.
TRACE_DEFAULT = ROOT.parent / "cat-bond-flow-analysis" / "data" / "bridge.csv"
TRACE_TOLERANCE_MONTHS = 3

# An unresolved loss with no stated extension date is carried past its
# scheduled maturity for at most this long. Cat bond extension provisions
# typically allow up to 36 months; after that the row is a stale table entry,
# not an outstanding note, and the principal leaves with a flag.
EXTENSION_CAP_MONTHS = 36

# Stated maturities sit at issue + term in 41% of issued dollars (165 deals
# with both), one month later in 24%, two later in 9%, one earlier in 8%
# (measured 2026-10-25). The mode is used: derived and imputed maturities are
# issue + term with no offset.

MONTH_NAMES = ("jan feb mar apr may jun jul aug sep oct nov dec".split())
EXT_DATE_RE = re.compile(
    r"extended\s+(?:again\s+)?to\s+(?:[A-Za-z]+\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+(\d{4})"
    r"|([A-Za-z]+)\s+(\d{4}))", re.IGNORECASE)
EXT_AMOUNT_RE = re.compile(
    r"(?:remaining|leaving|full)\s+\$([\d.,]+)\s*(m|million|bn|billion)?", re.IGNORECASE)
RETURNED_RE = re.compile(
    r"\$([\d.,]+)\s*(m|million|bn|billion)?\s+(?:of principal\s+)?(?:(?:was |were )?(?:also )?returned to investors|repaid)",
    re.IGNORECASE)
FULL_RECOVERY_RE = re.compile(
    r"recovered to par|full recovery for investors|redeemed in full|no loss to this tranche",
    re.IGNORECASE)
NAME_STOP = {"ltd", "ltd.", "limited", "plc", "dac", "pte", "pte.", "the", "inc", "inc."}


# ---------------------------------------------------------------- dates ----
def month_index(ym):
    """'2026-08' -> 24319 (months since year 0); None stays None."""
    if not ym:
        return None
    y, m = ym.split("-")
    return int(y) * 12 + int(m) - 1


def ym_from_index(i):
    return "%04d-%02d" % (i // 12, i % 12 + 1)


def add_months(ym, n):
    return ym_from_index(month_index(ym) + n)


def loss_month(date_text):
    """losses.csv date_of_loss -> ('YYYY-MM', imputed_flag) or (None, None).

    'Sep 2022' is a month. '2017', '2017 / 18', '2020/21' and '2024 / 2025
    risk period' name a year (the first one): the write-down is placed in its
    December so it leaves that year's closing stock, and the row is flagged.
    """
    s = str(date_text or "").strip()
    m = ns.issue_month(s)
    if m and re.search(r"[A-Za-z]{3}", s):
        return m, False
    y = re.search(r"\b((?:19|20)\d{2})\b", s)
    if y:
        return "%s-12" % y.group(1), True
    return None, None


# ------------------------------------------------------------- linking ----
def _norm_name(text):
    s = str(text or "").lower()
    s = re.sub(r"\s*[-–]?\s*class\s+[a-z0-9\-]+.*$", "", s)      # drop "Class B" and after
    s = re.sub(r"\(first event notes\)", "", s)
    s = s.replace("(", " ").replace(")", " ")
    s = re.sub(r"series\s+(\d{4})-([ivx]+)\b",
               lambda m: "series %s-%d" % (m.group(1), {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5}[m.group(2)]), s)
    s = re.sub(r"\b(\d{4}-\d+)\b", lambda m: "series " + m.group(1) if "series" not in s else m.group(1), s)
    toks = [t for t in re.findall(r"[a-z0-9\-/&]+", s) if t not in NAME_STOP]
    out = []
    for t in toks:                                   # collapse "series series"
        if not (t == "series" and out and out[-1] == "series"):
            out.append(t)
    return " ".join(out)


def link_losses(losses, deals):
    """Attach a deal_slug to every loss row that names a directory deal.

    The table links 60 of 114 rows itself. The rest name the deal in text,
    usually with a tranche suffix ("Caelus Re V Ltd. (Series 2018-1) Class B");
    the normalised name is matched against the directory's issuer names and
    the match is recorded in `link_method`.
    """
    by_name = {}
    for slug, name in zip(deals.deal_slug, deals.index_issuer_name):
        by_name.setdefault(_norm_name(name), slug)
    out = losses.copy()
    methods, slugs = [], []
    for slug, name in zip(out.deal_slug, out.cat_bond):
        if str(slug).strip():
            methods.append("table_link"); slugs.append(slug); continue
        hit = by_name.get(_norm_name(name))
        methods.append("name_match" if hit else "unlinked"); slugs.append(hit or "")
    out["deal_slug"] = slugs
    out["link_method"] = methods
    return out


def load_trace_maturities(path):
    """bridge.csv (one row per Artemis deal x TRACE CUSIP) -> one row per
    deal_url with the deal-level TRACE maturity.

    Rule: the maturity month shared by the most of the deal's bridged CUSIPs,
    the latest month on a tie. 645 of 700 bridged deals have one month; the
    55 that do not are multi-term series (Residential Re's one-year and
    four-year classes) where the longer classes are the majority, and the
    span between the earliest and latest month is kept for the flag.

    Columns: deal_url, trace_maturity_month, trace_cusips,
    trace_distinct_months, trace_span_months, trace_min_month, trace_max_month.
    """
    b = pd.read_csv(path, dtype=str, keep_default_na=False)
    b = b[(b.deal_url.str.strip() != "") & (b.trace_maturity_date.str.len() >= 7)]
    b = b.assign(month=b.trace_maturity_date.str[:7])
    rows = []
    for url, g in b.groupby("deal_url", sort=False):
        counts = g.month.value_counts()
        top = counts[counts == counts.max()].index
        chosen = max(top, key=month_index)
        months = sorted(counts.index, key=month_index)
        rows.append({"deal_url": url, "trace_maturity_month": chosen, "trace_cusips": int(len(g)),
                     "trace_distinct_months": int(len(counts)),
                     "trace_span_months": month_index(months[-1]) - month_index(months[0]),
                     "trace_min_month": months[0], "trace_max_month": months[-1]})
    return pd.DataFrame(rows, columns=["deal_url", "trace_maturity_month", "trace_cusips", "trace_distinct_months",
                                       "trace_span_months", "trace_min_month", "trace_max_month"])


def resolve_trace_path(arg="auto"):
    """'auto' -> the sibling repository's bridge when it exists, else None;
    None/'' -> off; anything else -> that path (must exist)."""
    if arg in (None, "", "off", "none"):
        return None
    if arg == "auto":
        return TRACE_DEFAULT if TRACE_DEFAULT.exists() else None
    path = Path(arg)
    if not path.exists():
        raise FileNotFoundError("TRACE maturities file not found: %s" % path)
    return path


# ------------------------------------------------------------- the book ----
def _amount_m(num_text, unit):
    n = _money_to_number("$%s%s" % (num_text, unit or ""))
    return n / 1e6 if n else None


def vintage_terms(book):
    """Size-weighted mean known term (months) per issue year for public deals,
    pooled by decade where a year has fewer than five known terms. The
    `--impute vintage` sensitivity run uses this instead of the flat median."""
    k = book[book.maturity_source.isin(["stated", "derived_from_term"]) & ~book.private
             & book.size_m.notna()].copy()
    k["term"] = [month_index(m) - month_index(i) for m, i in zip(k.maturity_month, k.issue_month)]
    k["year"] = k.issue_month.str[:4].astype(int)
    k["dec"] = k.year // 10 * 10
    out = {}
    for y, g in k.groupby("year"):
        pool = g if len(g) >= 5 else k[k.dec == y // 10 * 10]
        out[y] = int(round((pool.term * pool.size_m).sum() / pool.size_m.sum())) if len(pool) else IMPUTED_TERM_MONTHS["public"]
    return out


def deal_book(deals, losses, as_of=AS_OF, term_months=IMPUTED_TERM_MONTHS,
              extension_cap=EXTENSION_CAP_MONTHS, trace=None,
              trace_tolerance=TRACE_TOLERANCE_MONTHS):
    """One row per deal with everything the roll-forward needs.

    Columns: slug, issuer_name, issue_month, size_m (USD), maturity_month,
    maturity_source, page_maturity_month, page_maturity_source,
    trace_maturity_month (the bridge's month, even when rejected),
    trace_vs_page_months, written_down_m, recovered_m,
    extended_m, extension_month, repay_month (when the remainder actually
    leaves), remainder_m, flags.

    `term_months["public"]` may be an int or a {issue_year: int} map.
    `trace` is the frame from `load_trace_maturities`, joined on `deal_url`
    (ignored when `deals` has no such column). The precedence between the
    page's maturity and TRACE is in the module docstring.
    `deal_status` is not used to exclude anything: a deal with a size and an
    issue date is in the book and a non-"issued" status is only flagged (the
    five "cancelled" statuses that were a withdrawn sibling series or tranche
    read "issued" since 2026-11-17).
    """
    conv = [ns.convert_size(s, d) for s, d in zip(deals["size"], deals.date_of_issue)]
    book = pd.DataFrame({
        "slug": deals.deal_slug.values,
        "issuer_name": deals.index_issuer_name.values,
        "issue_month": deals.date_of_issue.map(ns.issue_month).values,
        "size_m": [c["usd_m"] for c in conv],
        "size_basis": [c["basis"] for c in conv],
        "private": deals.deal_is_private.str.lower().isin(["true", "1", "yes"]).values,
        "mortgage": deals.index_issuer_name.str.contains(ns.MORTGAGE_RE).values,
        "status": deals.deal_status.values,
    })
    stated = deals.maturity_date.str.strip() != ""
    derived = deals.maturity_date_derived.str.strip() != ""
    sched = deals.maturity_scheduled.map(ns.issue_month)
    class_vote = (deals["maturity_date__flags"].str.contains("maturity_from_class_agreement", regex=False)
                  if "maturity_date__flags" in deals.columns else pd.Series(False, index=deals.index))
    trace_by_url = {}
    if trace is not None and len(trace) and "deal_url" in deals.columns:
        trace_by_url = {r.deal_url: r for r in trace.itertuples(index=False)}
    urls = deals["deal_url"].values if "deal_url" in deals.columns else [None] * len(deals)
    src, mat, flags, page_src, page_mat, trace_mat, trace_diff = [], [], [], [], [], [], []
    for i in range(len(book)):
        f = []
        im = book.issue_month.iat[i]
        m = sched.iat[i]
        s = None
        if m and im and month_index(m) <= month_index(im):
            f.append("maturity_not_after_issue"); m = None
        if m:
            s = "stated" if stated.iat[i] else "derived_from_term"
        page_src.append(s); page_mat.append(m)
        tr = trace_by_url.get(urls[i])
        tm = tr.trace_maturity_month if tr is not None else None
        diff = None
        if tm and im and month_index(tm) <= month_index(im):
            f.append("trace_maturity_rejected_not_after_issue"); tm = None
        if tm:
            if tr.trace_distinct_months > 1:
                f.append("trace_maturity_tranches_disagree=%dm" % tr.trace_span_months)
            if m:
                diff = month_index(tm) - month_index(m)
            if s == "stated":
                if diff < -trace_tolerance:
                    # The page names a later month than every bridged CUSIP:
                    # the bridge holds the short classes only (Kilimanjaro II
                    # 2024-1: two 2025 classes bridged, page July 2028). The
                    # deal matures with its longest class; the page stands.
                    f.append("page_later_than_trace=%+dm" % -diff)
                elif abs(diff) <= trace_tolerance and not class_vote.iat[i]:
                    f.append("trace_corroborates_stated=%+dm" % diff)
                else:
                    # TRACE later than the page by more than the tolerance:
                    # the page's date was a one-year class's or a predecessor's.
                    f.append("trace_maturity_overrides_stated=%+dm%s" % (diff, "_class_vote" if class_vote.iat[i] else ""))
                    m, s = tm, "trace"
            elif s == "derived_from_term":
                f.append("trace_maturity_replaces_derived=%+dm" % diff)
                m, s = tm, "trace"
            else:
                f.append("trace_maturity_replaces_imputed")
                m, s = tm, "trace"
        trace_mat.append(tr.trace_maturity_month if tr is not None else None); trace_diff.append(diff)
        if not m:
            cls = "private" if book.private.iat[i] else "public"
            tm = term_months[cls]
            if isinstance(tm, dict):
                tm = tm.get(int(im[:4]), IMPUTED_TERM_MONTHS[cls]) if im else IMPUTED_TERM_MONTHS[cls]
                s = "imputed_%s_vintage" % cls
            else:
                s = "imputed_%s_%dm" % (cls, tm)
            f.append("term_imputed")
            m = add_months(im, tm) if im else None
        if book.status.iat[i] != "issued":
            f.append("deal_status_%s_ignored" % book.status.iat[i])
        src.append(s); mat.append(m); flags.append(f)
    book["maturity_month"] = mat
    book["maturity_source"] = src
    book["page_maturity_month"] = page_mat
    book["page_maturity_source"] = page_src
    book["trace_maturity_month"] = trace_mat
    book["trace_vs_page_months"] = trace_diff

    # Loss events, aggregated to the deal. losses.csv is tranche-level.
    linked = losses[losses.deal_slug.str.strip() != ""]
    wd, rec, ext_m, ext_month, last_loss, lflags, open_ext = ({} for _ in range(7))
    for _, r in linked.iterrows():
        slug = r.deal_slug
        lm, imputed = loss_month(r.date_of_loss)
        fl = lflags.setdefault(slug, set())
        if imputed:
            fl.add("loss_month_imputed")
        text = str(r.loss_amount or "")
        if r.is_settled == "True" and str(r.loss_amount_derived).strip():
            w = float(r.loss_amount_derived) / 1e6
            ccy = _currency(str(r.orig_size or ""))
            if ccy and ccy != "USD":
                rate = ns.load_fx().get((ccy, lm[:7] if lm else None))
                w = w * rate if rate else w
                fl.add("loss_fx_converted" if rate else "loss_fx_rate_missing")
            if lm:
                wd.setdefault(slug, []).append((lm, w))
                last_loss[slug] = max(last_loss.get(slug, lm), lm)
            else:
                fl.add("loss_undated_not_applied")
        ret = sum(_amount_m(a, u) or 0 for a, u in RETURNED_RE.findall(text))
        if ret and r.is_settled == "True" and lm:
            rec.setdefault(slug, []).append((lm, ret)); fl.add("recovery_to_investors")
        if FULL_RECOVERY_RE.search(text):
            fl.add("repaid_in_full_no_loss")
        em = EXT_DATE_RE.search(text)
        if em:
            if em.group(1):
                emon = "%s-12" % em.group(1)        # "April 7 2028" -> keep the year end? no:
                mm = re.search(r"([A-Za-z]+)\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+(\d{4})", em.group(0))
                emon = ns.issue_month("%s %s" % (mm.group(1), mm.group(2))) or emon
            else:
                emon = ns.issue_month("%s %s" % (em.group(2), em.group(3)))
            am = EXT_AMOUNT_RE.search(text)
            amt = _amount_m(am.group(1), am.group(2)) if am else None
            if amt is None:
                n = _money_to_number(str(r.orig_size or "")); amt = n / 1e6 if n else None
            if emon and amt:
                ext_m[slug] = ext_m.get(slug, 0) + amt
                ext_month[slug] = max(ext_month.get(slug, emon), emon)
                fl.add("extended_to_stated_date")
        elif r.is_settled != "True" and str(r.loss_status) in ("extended", "marked_at_risk", "marked_to_market", ""):
            # Unresolved: the tranche has not rolled off risk. Carry it past
            # its scheduled maturity, to the as-of date or the extension cap,
            # whichever comes first; the amount is the tranche's stated size.
            n = _money_to_number(str(r.orig_size or "")); amt = n / 1e6 if n else None
            if amt:
                open_ext.setdefault(slug, 0.0)
                open_ext[slug] += amt
                fl.add("extension_open")

    # Open extensions resolve to a month only once the scheduled maturity is
    # known: carried to min(maturity + cap, as-of + 1).
    sched_by_slug = dict(zip(book.slug, book.maturity_month))
    for slug, amt in open_ext.items():
        m = sched_by_slug.get(slug)
        if not m:
            continue
        cap = add_months(m, extension_cap)
        carried = min(month_index(cap), month_index(as_of) + 1)
        if carried <= month_index(m):
            continue
        carried_m = ym_from_index(carried)
        ext_m[slug] = ext_m.get(slug, 0) + amt
        ext_month[slug] = max(ext_month.get(slug, carried_m), carried_m)
        lflags.setdefault(slug, set()).add(
            "extension_open_capped_%dm" % extension_cap if carried == month_index(cap) else "extension_open_carried_to_as_of")

    def _sum(d, slug):
        return sum(a for _, a in d.get(slug, []))
    book["written_down_m"] = [min(_sum(wd, s), sz or 0) if sz else 0.0 for s, sz in zip(book.slug, book.size_m)]
    book["recovered_m"] = [min(_sum(rec, s), w) for s, w in zip(book.slug, book.written_down_m)]
    net_lost = book.written_down_m - book.recovered_m
    remainder = (book.size_m.fillna(0) - net_lost).clip(lower=0)
    book["extended_m"] = [min(ext_m.get(s, 0.0), r) for s, r in zip(book.slug, remainder)]
    book["extension_month"] = [ext_month.get(s) for s in book.slug]
    book["remainder_m"] = remainder - book.extended_m
    # The remainder leaves at maturity, or when the last loss settled if that
    # came later (an implicit extension while the loss developed).
    book["repay_month"] = [
        max(m, last_loss[s]) if (m and s in last_loss and month_index(last_loss[s]) > month_index(m)) else m
        for s, m in zip(book.slug, book.maturity_month)]
    book["flags"] = [";".join(sorted(set(f) | lflags.get(s, set())
                                     | ({"repay_after_maturity_loss_settlement"} if rp != m else set())))
                     for f, s, rp, m in zip(flags, book.slug, book.repay_month, book.maturity_month)]
    book["events"] = [{"wd": wd.get(s, []), "rec": rec.get(s, [])} for s in book.slug]
    return book


def monthly_flows(book, unlinked_losses=None):
    """Deal book -> DataFrame indexed by month with issued, written_down,
    recovered, repaid, extended_repaid (USD m). Unlinked losses (no deal) are
    written down at market level and flagged in the output."""
    rows = []
    for r in book.itertuples(index=False):
        if r.size_m is None or pd.isna(r.size_m) or not r.issue_month:
            continue
        rows.append((r.issue_month, "issued", r.size_m))
        for lm, w in r.events["wd"]:
            rows.append((lm, "written_down", w))
        over = sum(w for _, w in r.events["wd"]) - r.written_down_m      # cap excess
        if over > 1e-9:
            rows.append((r.events["wd"][-1][0], "written_down", -over))
        for lm, a in r.events["rec"]:
            rows.append((lm, "recovered", a))
        over = sum(a for _, a in r.events["rec"]) - r.recovered_m
        if over > 1e-9:
            rows.append((r.events["rec"][-1][0], "recovered", -over))
        if r.repay_month and r.remainder_m > 0:
            rows.append((r.repay_month, "repaid", r.remainder_m))
        if r.extension_month and r.extended_m > 0:
            rows.append((r.extension_month, "repaid_after_extension", r.extended_m))
    if unlinked_losses is not None:
        for _, l in unlinked_losses.iterrows():
            lm, _ = loss_month(l.date_of_loss)
            if lm and l.is_settled == "True" and str(l.loss_amount_derived).strip():
                rows.append((lm, "written_down_unlinked", float(l.loss_amount_derived) / 1e6))
    f = pd.DataFrame(rows, columns=["month", "flow", "m"])
    f = f.pivot_table(index="month", columns="flow", values="m", aggfunc="sum").fillna(0.0)
    for c in ["issued", "written_down", "recovered", "repaid", "repaid_after_extension", "written_down_unlinked"]:
        if c not in f.columns:
            f[c] = 0.0
    return f.sort_index()


def outstanding_by_year(flows, as_of=AS_OF):
    """Closing stock per year: December for completed years, the as-of month
    for the final year (the publisher's current figure is a snapshot)."""
    f = flows.copy()
    f["net"] = (f.issued - f.written_down - f.written_down_unlinked + f.recovered
                - f.repaid - f.repaid_after_extension)
    f["stock"] = f.net.cumsum()
    f["year"] = f.index.str[:4].astype(int)
    last_year = int(as_of[:4])
    rows = []
    for y in range(f.year.min(), last_year + 1):
        cut = as_of if y == last_year else "%d-12" % y
        upto = f[f.index <= cut]
        inyear = upto[upto.year == y]
        rows.append({"year": y, "measured_at": cut,
                     "issued": inyear.issued.sum(), "written_down": inyear.written_down.sum() + inyear.written_down_unlinked.sum(),
                     "written_down_unlinked": inyear.written_down_unlinked.sum(),
                     "recovered": inyear.recovered.sum(),
                     "repaid": inyear.repaid.sum() + inyear.repaid_after_extension.sum(),
                     "repaid_after_extension": inyear.repaid_after_extension.sum(),
                     "outstanding": upto.net.sum()})
    return pd.DataFrame(rows)


def coverage(book):
    """Share of issued dollars by maturity source (the roll-forward's
    load-bearing input), plus the loss-linkage shares."""
    b = book.dropna(subset=["size_m"])
    tot = b.size_m.sum()
    g = b.groupby("maturity_source").size_m.agg(["size", "sum"]).rename(columns={"size": "n_deals", "sum": "usd_m"})
    g["share_pct"] = g.usd_m / tot * 100
    return g.reset_index()


def upcoming_maturities(book, as_of=AS_OF):
    """Remaining principal scheduled to leave after the as-of month, by quarter,
    for comparison with the publisher's upcoming-maturities chart."""
    rows = []
    for r in book.itertuples(index=False):
        carried_open = "extension_open" in (r.flags or "") and "extended_to_stated_date" not in (r.flags or "")
        for month, amt, kind in ((r.repay_month, r.remainder_m, "scheduled"),
                                 (r.extension_month, r.extended_m, "carried_open" if carried_open else "extended_stated")):
            if month and amt and month_index(month) > month_index(as_of):
                y, m = month.split("-")
                rows.append(("Q%d %s" % ((int(m) - 1) // 3 + 1, y), month, amt, kind))
    return pd.DataFrame(rows, columns=["quarter", "month", "m", "kind"])


def publisher_maturities():
    """The publisher's upcoming-maturities chart, by quarter."""
    h = ns.fetch("https://www.artemis.bm/dashboard/catastrophe-bond-maturities/")
    cats = re.findall(r"['\"]([^'\"]+)['\"]", re.search(r"categories\s*:\s*\[(.*?)\]", h, re.S).group(1))
    for m in re.finditer(r"name\s*:\s*['\"]Risk capital maturing['\"].*?data\s*:\s*\[(.*?)\]", h, re.S):
        vals = [float(v) for v in m.group(1).split(",") if re.match(r"^\s*-?[\d.]+\s*$", v)]
        if len(vals) == len(cats):
            return pd.DataFrame({"quarter": cats, "artemis_maturing_m": vals})
    return pd.DataFrame(columns=["quarter", "artemis_maturing_m"])


def legacy_variants(book, flows, as_of=AS_OF):
    """Three runs that decompose the old approximation, holding this book fixed.

    `legacy_3y`   the old net_supply rule: scheduled maturity where known, else
                  issue + 36 months for every deal, no extensions, no
                  recoveries, and every written-down dollar counted again at
                  maturity.
    `no_netting`  this book's maturities (class-specific imputation) with the
                  double subtraction kept.
    `netted`      the same with the written-down portion removed from what
                  matures. netted - no_netting is what the double subtraction
                  alone explained; the rest of the move to the full
                  roll-forward is extensions and recoveries.
    """
    out = {}
    for label, netted in (("legacy_3y", False), ("no_netting", False), ("netted", True)):
        rows = []
        for r in book.itertuples(index=False):
            if r.size_m is None or pd.isna(r.size_m) or not r.issue_month or not r.maturity_month:
                continue
            rows.append((r.issue_month, "issued", r.size_m))
            for lm, w in r.events["wd"]:
                rows.append((lm, "written_down", w))
            mat = r.maturity_month
            if label == "legacy_3y":
                # The old rule saw only the page: its maturity where stated
                # or term-derived, else issue + 36 months. TRACE did not exist.
                mat = r.page_maturity_month if r.page_maturity_source else add_months(r.issue_month, 36)
            rows.append((mat, "repaid", r.size_m if not netted else r.size_m - r.written_down_m))
        f = pd.DataFrame(rows, columns=["month", "flow", "m"]).pivot_table(
            index="month", columns="flow", values="m", aggfunc="sum").fillna(0.0).sort_index()
        f["written_down_unlinked"] = flows.written_down_unlinked.reindex(f.index).fillna(0.0)
        for c in ["issued", "written_down", "repaid", "recovered", "repaid_after_extension"]:
            if c not in f.columns:
                f[c] = 0.0
        out[label] = outstanding_by_year(f, as_of).set_index("year").outstanding
    return pd.DataFrame(out)


def select_book(book, exclude_mortgage=True):
    """Which deals enter the ledger: every deal with a size, whatever its
    parsed `deal_status` (the publisher's totals count every sized deal, and
    the "cancelled" statuses seen so far were a withdrawn sibling series or
    tranche), minus mortgage ILS when the comparison is against the
    publisher's charts."""
    out = book[book.size_m.notna()]
    if exclude_mortgage:
        out = out[~out.mortgage]
    return out


def build(as_of=AS_OF, exclude_mortgage=True, impute="flat", trace_path="auto"):
    """`trace_path`: 'auto' (the sibling repository's bridge when present),
    None to run without TRACE maturities, or a path."""
    deals = pd.read_csv(ROOT / "data" / "deals.csv", keep_default_na=False, dtype=str)
    losses = link_losses(pd.read_csv(ROOT / "data" / "losses.csv", keep_default_na=False, dtype=str), deals)
    path = resolve_trace_path(trace_path)
    trace = load_trace_maturities(path) if path else None
    book = deal_book(deals, losses, as_of, trace=trace)
    if impute == "vintage":
        terms = {"public": vintage_terms(book), "private": IMPUTED_TERM_MONTHS["private"]}
        book = deal_book(deals, losses, as_of, term_months=terms, trace=trace)
    book.attrs["trace_path"] = str(path) if path else None
    book = select_book(book, exclude_mortgage)
    unlinked = losses[losses.link_method == "unlinked"]
    flows = monthly_flows(book, unlinked)
    return book, losses, flows


def trace_check(book):
    """How the page's maturities and TRACE's compare, on the deals in the book
    that have both: one row per (page source, outcome, TRACE minus page in
    months), with deal counts and issued dollars. Aggregates only."""
    b = book[book.trace_maturity_month.notna()]
    rows = []
    for r in b.itertuples(index=False):
        fl = r.flags or ""
        if "trace_corroborates_stated" in fl:
            outcome = "stated_kept"
        elif "page_later_than_trace" in fl:
            outcome = "stated_kept_page_later"
        elif "trace_maturity_overrides_stated" in fl:
            outcome = "trace_overrides_stated" + ("_class_vote" if "_class_vote" in fl else "")
        elif "trace_maturity_replaces_derived" in fl:
            outcome = "trace_replaces_derived"
        elif "trace_maturity_replaces_imputed" in fl:
            outcome = "trace_replaces_imputed"
        else:
            outcome = "trace_rejected"
        rows.append({"page_source": r.page_maturity_source or "none", "outcome": outcome,
                     "trace_minus_page_months": r.trace_vs_page_months, "size_m": r.size_m or 0.0})
    if not rows:
        return pd.DataFrame(columns=["page_source", "outcome", "trace_minus_page_months", "n_deals", "usd_m"])
    t = pd.DataFrame(rows)
    out = t.groupby(["page_source", "outcome", "trace_minus_page_months"], dropna=False).agg(
        n_deals=("size_m", "size"), usd_m=("size_m", "sum")).reset_index()
    return out.sort_values(["page_source", "outcome", "trace_minus_page_months"]).reset_index(drop=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--as-of", default=AS_OF)
    ap.add_argument("--impute", choices=("flat", "vintage"), default="flat",
                    help="term for deals with no maturity: flat class medians (default) "
                         "or the size-weighted mean known term of the issue year")
    ap.add_argument("--trace-maturities", default="auto", metavar="PATH",
                    help="the analysis repository's bridge.csv (deal_url, cusip_id, "
                         "trace_maturity_date); default: %s when it exists" % TRACE_DEFAULT)
    ap.add_argument("--no-trace-maturities", action="store_true",
                    help="run on page maturities and imputation alone")
    args = ap.parse_args()
    trace_path = None if args.no_trace_maturities else args.trace_maturities
    book, losses, flows = build(args.as_of, exclude_mortgage=True, impute=args.impute, trace_path=trace_path)
    yearly = outstanding_by_year(flows, args.as_of)
    theirs = ns.dashboard_series()[["year", "artemis_issued", "artemis_outstanding"]]
    cmpd = yearly.merge(theirs, on="year", how="left")
    cmpd["issued_diff"] = cmpd.issued - cmpd.artemis_issued
    cmpd["outstanding_diff"] = cmpd.outstanding - cmpd.artemis_outstanding
    var = legacy_variants(book, flows, args.as_of)
    cmpd = cmpd.merge(var.reset_index(), on="year", how="left")
    cmpd["double_subtraction_m"] = cmpd.netted - cmpd.no_netting
    cmpd["legacy_gap"] = cmpd.legacy_3y - cmpd.artemis_outstanding
    cmpd["carried_open_m"] = [
        book[(book.extension_month > m) & book["flags"].str.contains("extension_open")].extended_m.sum()
        for m in cmpd.measured_at]

    cov = coverage(book)
    pd.set_option("display.width", 250)
    print("=== roll-forward, ex-mortgage, as of %s: %d deals in the book ===" % (args.as_of, len(book)))
    tc = trace_check(book)
    if book.attrs.get("trace_path"):
        print("TRACE maturities from %s: %d deals in the book bridged" % (book.attrs["trace_path"], int(book.trace_maturity_month.notna().sum())))
        print(tc.groupby(["page_source", "outcome"]).agg(n_deals=("n_deals", "sum"), usd_m=("usd_m", "sum")).round(0).to_string())
    else:
        print("TRACE maturities: off")
    print("loss rows: %s" % losses.link_method.value_counts().to_dict())
    lk = losses[losses.is_settled == "True"].assign(m=lambda d: pd.to_numeric(d.loss_amount_derived, errors="coerce") / 1e6).groupby("link_method").m.sum().round(0).to_dict()
    print("settled written-down $m by link method: %s" % lk)
    print("\ncoverage of the maturity leg by issued dollars:")
    print(cov.round(1).to_string(index=False))
    print("\nyear by year ($m):")
    cols = ["year", "measured_at", "issued", "artemis_issued", "written_down", "recovered", "repaid", "repaid_after_extension",
            "carried_open_m", "outstanding", "artemis_outstanding", "outstanding_diff", "legacy_3y", "legacy_gap",
            "no_netting", "netted", "double_subtraction_m"]
    print(cmpd[cols][cmpd.year >= 2010].round(0).to_string(index=False))
    print("\nflags on deals in the book:")
    print(book["flags"].str.split(";").explode().replace("", pd.NA).dropna().value_counts().to_string())

    OUT.mkdir(exist_ok=True); DASH_OUT.mkdir(exist_ok=True)
    cmpd.to_csv(OUT / "outstanding_rollforward.csv", index=False)
    book.drop(columns=["events"]).to_csv(OUT / "outstanding_deals.csv", index=False)
    tracked = cmpd[["year", "measured_at", "issued", "artemis_issued", "written_down", "recovered", "repaid",
                    "repaid_after_extension", "carried_open_m", "outstanding", "artemis_outstanding",
                    "outstanding_diff", "legacy_3y", "legacy_gap", "no_netting", "netted",
                    "double_subtraction_m"]].copy()
    for _, r in cov.iterrows():
        tracked["cov_%s_pct" % r.maturity_source] = round(r.share_pct, 2)
    tracked.round(3).to_csv(DASH_OUT / "outstanding.csv", index=False)
    tc.round(3).to_csv(DASH_OUT / "trace_maturities.csv", index=False)

    up = upcoming_maturities(book, args.as_of)
    q = up.pivot_table(index="quarter", columns="kind", values="m", aggfunc="sum").fillna(0.0)
    for c in ("scheduled", "extended_stated", "carried_open"):
        if c not in q.columns:
            q[c] = 0.0
    mat = publisher_maturities().merge(q.reset_index(), on="quarter", how="outer").fillna({"scheduled": 0.0, "extended_stated": 0.0, "carried_open": 0.0})
    mat["our_scheduled_m"] = mat.scheduled + mat.extended_stated
    mat["our_carried_open_m"] = mat.carried_open
    mat = mat[["quarter", "artemis_maturing_m", "our_scheduled_m", "our_carried_open_m"]]
    mat["diff_m"] = mat.our_scheduled_m - mat.artemis_maturing_m
    mat["qsort"] = [int(x.split()[1]) * 4 + int(x[1]) for x in mat.quarter]
    mat = mat.sort_values("qsort").drop(columns="qsort")
    mat.round(3).to_csv(DASH_OUT / "maturities.csv", index=False)
    inwin = mat.dropna(subset=["artemis_maturing_m"])
    print("\nupcoming maturities by quarter, publisher vs our scheduled remainder (carried open extensions shown apart):")
    print(inwin.round(0).to_string(index=False))
    print("window total: publisher %.0f, ours %.0f; mean |quarterly diff| %.0f"
          % (inwin.artemis_maturing_m.sum(), inwin.our_scheduled_m.sum(), inwin.diff_m.abs().mean()))
    print("\nwrote data/outstanding_rollforward.csv, data/outstanding_deals.csv, "
          "data/validation_dashboards/outstanding.csv, data/validation_dashboards/maturities.csv, "
          "data/validation_dashboards/trace_maturities.csv")


if __name__ == "__main__":
    main()
