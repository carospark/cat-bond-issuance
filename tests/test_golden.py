"""Golden tests over the cached pages in raw/. No network: fetch() is cache-first.

Two kinds of assertion:
  EXPECT   a verified value, read off the source by hand.
  GUARD    an invariant that must hold on every page, forever. Guards are the
           point: every bug so far was a regex that fixed one page and quietly
           broke another.

Run:  ./.venv/bin/python tests/test_golden.py
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from fetch import fetch          # noqa: E402
from validate import validate  # noqa: E402
from parse_deal import _is_backward_reference  # noqa: E402
from parse_deal import (parse_deal, parse_tranches, check_tranche_sum,  # noqa: E402
                        MONTHS, TIER1_KEYS)

BASE = "https://www.artemis.bm/deal-directory/"
PAGES = [
    # Radnor: mortgage-ILS suffixed class labels (M-1A vs M-1).
    # Trinity: prose states a count it never breaks down -- must be flagged.
    "radnor-re-2020-2-ltd", "trinity-re-ltd",
    # Pages that each exposed a wrong output in adversarial review.
    "atlantic-western-re-ltd",          # lowercase "class A" labels
    "hoplon-ii-insurance-ltd",          # guidance endpoint sold as settled
    "mosaic-re-ii-ltd",                 # stated-multi given single-tranche size
    "triangle-re-2019-1-ltd",           # "$X tranche of Class Y" phrasing
    "residential-reinsurance-2020-limited-series-2020-1",  # predecessor coupon
    "citrus-re-ltd-series-2014-2",      # same-year sibling contamination
    "ibrd-car-jamaica-2026", "floodsmart-re-ltd-series-2024-1",
    "residential-reinsurance-2026-limited-series-2026-1", "seaside-re-series-2026-61",
    "windmill-ii-re-dac-2020", "kilimanjaro-re-ltd-series-2015-1",
    "gateway-re-ltd-series-2024-3", "george-town-re-ltd", "ursa-re-ltd-series-2015-1",
]

# Verified by reading the source prose; see notes for provenance.
EXPECT = {
    "ibrd-car-jamaica-2026": {
        "cedent_sponsor": "Government of Jamaica", "size": "$200m",
        "trigger_type": "Parametric", "date_of_issue": "May 2026",
        "expected_loss": "2.48%", "attachment_probability": "3.86%",
        "spread_risk_margin": "6.75%",   # "priced to pay ... risk margin of 6.75%"
        "maturity_date": "May 2030",
    },
    "windmill-ii-re-dac-2020": {
        "cedent_sponsor": "Achmea Reinsurance Company N.V.",
        "size": "€100m ($113m)",
        "spread_risk_margin": "4.25%",   # "set to pay investors a coupon of 4.25%"
    },
    # Forward-looking years must survive the backward-reference exclusion.
    "ursa-re-ltd-series-2015-1": {
        "term_length": "three-year",     # "running until mid-September 2018"
        "spread_risk_margin": "5%",      # corroborated by a clean sentence
    },
    "floodsmart-re-ltd-series-2024-1": {"term_length": "three-year"},
    "george-town-re-ltd": {
        "date_of_issue": "Dec 1996", "size": "$68.5m", "cedent_sponsor": "St Paul Re",
    },
    # size is now normalised to None with the raw string preserved.
    "gateway-re-ltd-series-2024-3": {"size": None},
    "seaside-re-series-2026-61": {"issuer": "Kaith Re Ltd."},
}

# Verified tranche sizes, read off the prose by hand. FloodSmart is the case
# that exposed the window-boundary bug: Artemis writes "A $300 million Class A
# tranche", size BEFORE label, so label-anchored windows swapped the sizes.
TRANCHE_SIZES = {
    "floodsmart-re-ltd-series-2024-1": {
        "Class A": ("$300 million", "$475 million"),
        "Class B": ("$50 million", "$100 million"),
    },
    "residential-reinsurance-2026-limited-series-2026-1": {
        "Class 14": ("$150 million", "$150 million"),
        "Class 15": ("$150 million", "$175 million"),
        "Class A": ("$300 million", "$500 million"),
    },
    # Update 1/2: "Class D ... grew to $300 million ... Class E has upsized to
    # $325 million"; "the $300m Class D tranche ... and the $325m Class E".
    "kilimanjaro-re-ltd-series-2015-1": {
        "Class D": ("$125m", "$300m"),
        "Class E": ("$175m", "$325 million"),
    },
    # Lowercase "class A/B variable-rate notes" -- a capitalised-only pattern
    # collapsed this into one tranche with a fabricated +200% resize.
    "atlantic-western-re-ltd": {
        "Class A": ("$100 million", "$100 million"),
        "Class B": ("$200 million", "$200 million"),
    },
    # Three tranches in ONE comma-separated sentence. Window boundaries put
    # B-1's amount inside M-2's window, so M-2 reported B-1's size.
    "triangle-re-2019-1-ltd": {
        "Class M-1": ("$134,574,000", "$134,574,000"),
        "Class M-2": ("$151,396,000", "$151,396,000"),
        "Class B-1": ("$16,821,000", "$16,821,000"),
    },
    # "Both the Class A and Class B tranche of notes are sized at EUR 25m each"
    # -- one amount, two owners.
    "hoplon-ii-insurance-ltd": {
        "Class A": ("\u20ac25m", "\u20ac25m"),
        "Class B": ("\u20ac25m", "\u20ac25m"),
    },
    # Class 13 IS the whole deal because Class 12 "will not be issued at all",
    # so the no-tranche-equals-the-total rule must not suppress it.
    "residential-reinsurance-2020-limited-series-2020-1": {
        "Class 13": ("$100 million", "$100 million"),
    },
    # Five classes in ONE semicolon-separated sentence; four sizes were lost.
    "radnor-re-2020-2-ltd": {
        "Class M-1A": ("$79,832,000", "$79,832,000"),
        "Class M-1B": ("$93,137,000", "$93,137,000"),
        "Class M-2": ("$99,790,000", "$99,790,000"),
        "Class B-1": ("$33,263,000", "$33,263,000"),
    },
}

# Deals whose tranche finals must sum to the Tier-1 deal size.
TRANCHE_SUM_OK = {"triangle-re-2019-1-ltd", "atlantic-western-re-ltd",
                  "floodsmart-re-ltd-series-2024-1",
                  "residential-reinsurance-2026-limited-series-2026-1",
                  "kilimanjaro-re-ltd-series-2015-1",
                  "ursa-re-ltd-series-2015-1", "seaside-re-series-2026-61"}

# Known-WRONG values, each observed in production before a fix. Asserting the
# absence of a specific wrong answer is what makes these guards non-vacuous:
# "field is None" would pass on total extraction failure, and did.
REJECT = {
    # the 2019-1 predecessor's coupon, adopted as this deal's spread
    "residential-reinsurance-2020-limited-series-2020-1": {"spread_risk_margin": "8.25%"},
    # the LOW END of "guide pricing of 11.25% to 12.25%", not the settled 12%
    "hoplon-ii-insurance-ltd": {"spread_risk_margin": "11.25%"},
    # $200m/$350m are the Citrus 2014-1 layer bounds, not 2014-2's
    "citrus-re-ltd-series-2014-2": {"attachment_point": "$200m"},
}

# Deal-level size history. A state here must be the DEAL's size, never a
# component's. Empty lists are meaningful assertions: Atlantic's only sizing
# sentence is "$100 million class A variable-rate notes" and Mosaic's is "one of
# $25m and one of $20m" -- neither states a deal size, so inventing one is the
# bug. Kilimanjaro is the positive case: its class-scoped $300m used to mask the
# real $625m upsize.
SIZE_HISTORY = {
    "kilimanjaro-re-ltd-series-2015-1": [("launch", "$300m"),
                                         ("update_1", "$625 million")],
    "atlantic-western-re-ltd": [],
    "mosaic-re-ii-ltd": [],
    "ursa-re-ltd-series-2015-1": [("launch", "$150m"), ("update_1", "$250m")],
    "ibrd-car-jamaica-2026": [("launch", "$150 million"),
                              ("update_1", "$200 million"),
                              ("update_2", "$200 million")],
}

STOPWORDS = {"the", "this", "new", "a", "an", "its", "our"}
results = []


def check(ok, label, detail=""):
    results.append((ok, label, detail))


def unit_backward_reference():
    """Pin the year boundary directly.

    End-to-end guards cannot isolate this: the foreign-series rule catches the
    same sentences, so restoring the `< issue_year - 1` off-by-one left the
    whole suite green. Redundant defences are good for correctness and useless
    for localisation, so the predicate gets its own test.
    """
    NO = frozenset()
    cases = [
        # (sentence, issue_year, own_series, expected)
        ("the 2019 bond eventually priced with a coupon of 8.25%", 2020, NO, True),
        ("the 2025 deal was smaller", 2026, NO, True),          # year-1 boundary
        ("maturity is expected in May 2030", 2026, NO, False),  # forward year
        ("a four-year term running to 2030", 2026, NO, False),
        ("no years mentioned at all", 2026, NO, False),
        # series rule, independent of year
        ("the Gateway Re 2024-1 deal had two tranches", 2024,
         frozenset({"2024-3"}), True),
        ("this 2024-3 deal has one tranche", 2024, frozenset({"2024-3"}), False),
        # parenthetical asides must not condemn the sentence
        ("Class 15 targeted $150 million (higher than the $50m in the 2025-1 bond)",
         2026, frozenset({"2026-1"}), False),
    ]
    for sentence, year, own, want in cases:
        got = _is_backward_reference(sentence, year, own)
        check(got == want, f"UNIT backref {sentence[:44]!r}", f"want={want} got={got}")


def main():
    unit_backward_reference()
    for slug in PAGES:
        rec = parse_deal(fetch(BASE + slug + "/"), deal_url=BASE + slug + "/")

        for key, want in EXPECT.get(slug, {}).items():
            got = rec[key]["value"]
            check(got == want, f"EXPECT {slug}:{key}", f"want={want!r} got={got!r}")

        # GUARD: every Tier-1 field present and high-confidence.
        # GUARD: placeholders normalise to None but keep raw_value.
        for key in TIER1_KEYS:
            f = rec[key]
            if any(str(x).startswith("source_placeholder") for x in f["flags"]):
                check(f["value"] is None and f.get("raw_value"),
                      f"GUARD placeholder-normalised {slug}:{key}", str(f))

        for key in ("issuer", "cedent_sponsor", "size", "date_of_issue", "trigger_type"):
            check(rec[key]["confidence"] == "high",
                  f"GUARD tier1-high {slug}:{key}", str(rec[key]["confidence"]))

        # GUARD: maturity is a real month-year, never a stopword+year.
        mat = rec["maturity_date"]["value"]
        if mat:
            check(bool(re.fullmatch(MONTHS + r"\s+\d{4}", mat)),
                  f"GUARD maturity-shape {slug}", repr(mat))
            check(mat.split()[0].lower() not in STOPWORDS,
                  f"GUARD maturity-not-stopword {slug}", repr(mat))

        # GUARD: the deleted weak spread fallback must never come back.
        check("weak_pattern" not in rec["spread_risk_margin"]["flags"],
              f"GUARD no-weak-spread {slug}", str(rec["spread_risk_margin"]["flags"]))

        # GUARD: EL <= attachment probability (arithmetically required).
        def pct(k):
            v = rec[k]["value"]
            return float(re.sub(r"[^\d.]", "", v)) if v else None
        el, ap = pct("expected_loss"), pct("attachment_probability")
        if el and ap:
            check(el <= ap, f"GUARD EL<=AP {slug}", f"EL={el} AP={ap}")

        # GUARD: a size_change must be corroborated by explicit resize language.
        sc = rec["size_change"]["value"]
        if sc:
            check(sc.get("reason_evidence") is not None,
                  f"GUARD size-change-corroborated {slug}",
                  f"{sc['size_at_launch']}->{sc['size_final']} reason=None")

        # GUARD: tranche count matches the multi-tranche deals we verified.
        expected_tranches = {"residential-reinsurance-2026-limited-series-2026-1": 3,
                             "floodsmart-re-ltd-series-2024-1": 2,
                             "kilimanjaro-re-ltd-series-2015-1": 2}
        rows = parse_tranches(rec)
        if slug in expected_tranches:
            check(len(rows) == expected_tranches[slug],
                  f"GUARD tranche-count {slug}",
                  f"want={expected_tranches[slug]} got={len(rows)}")
        # GUARD: per-tranche EL <= AP, and severity built from one tranche.
        for r in rows:
            if r["expected_loss"] and r["attachment_probability"]:
                e = float(re.sub(r"[^\d.]", "", r["expected_loss"]))
                a = float(re.sub(r"[^\d.]", "", r["attachment_probability"]))
                check(e <= a, f"GUARD tranche EL<=AP {slug}:{r['tranche_id']}",
                      f"EL={e} AP={a}")

        # GUARD: predecessor-deal figures must never become this deal's.
        # Windmill II's prose cites the 2017 Windmill Re bond at "$46 million".
        if slug == "windmill-ii-re-dac-2020":
            for r in parse_tranches(rec):
                for key in ("tranche_size_at_launch", "tranche_size_final"):
                    check(r[key] != "$46 million",
                          f"GUARD no-predecessor-size {slug}:{key}", str(r[key]))
        # GUARD: a backward-referencing sentence never sources a value.
        iy = re.search(r"(19|20)\d\d", rec["date_of_issue"]["value"] or "")
        if iy:
            year = int(iy.group(0))
            prose = rec["_meta"]["full_details_text"] or ""
            for sent in re.split(r"(?<=\.)\s+", prose):
                # NOTE: must be `< year`, not `< year - 1`. The earlier form
                # mirrored the parser's own off-by-one, so this guard could
                # not detect the bug it existed to catch.
                yrs = [int(y) for y in re.findall(r"\b(?:19|20)\d\d\b", sent)]
                if not any(y < year for y in yrs):
                    continue
                for fld in ("expected_loss", "attachment_probability",
                            "spread_risk_margin", "maturity_date"):
                    v = rec[fld]["value"]
                    if v and v in sent and not any(
                            v in s2 for s2 in re.split(r"(?<=\.)\s+", prose)
                            if s2 != sent and not any(
                                y < year - 1
                                for y in [int(x) for x in
                                          re.findall(r"\b(?:19|20)\d\d\b", s2)])):
                        check(False, f"GUARD backref-sourced {slug}:{fld}",
                              f"{v!r} only in: {sent[:70]}")

        # GUARD: tranche sizes land on the right tranche.
        rows_by_id = {r["tranche_id"]: r for r in parse_tranches(rec)}
        for tid, (launch, final) in TRANCHE_SIZES.get(slug, {}).items():
            r = rows_by_id.get(tid)
            check(r is not None, f"EXPECT tranche-present {slug}:{tid}", "")
            if r:
                check(r["tranche_size_at_launch"] == launch,
                      f"EXPECT {slug}:{tid}:launch",
                      f"want={launch!r} got={r['tranche_size_at_launch']!r}")
                check(r["tranche_size_final"] == final,
                      f"EXPECT {slug}:{tid}:final",
                      f"want={final!r} got={r['tranche_size_final']!r}")

        # GUARD: the parts must equal the whole.
        if slug in TRANCHE_SUM_OK:
            ok, detail = check_tranche_sum(rec, parse_tranches(rec))
            check(ok is True, f"GUARD tranche-sum {slug}", detail)

        # GUARD: mortgage-ILS class labels keep their suffix (M-1A != M-1),
        # and a stated-but-unsplittable count is flagged, never silently lost.
        rws = parse_tranches(rec)
        if slug == "radnor-re-2020-2-ltd":
            ids = [r["tranche_id"] for r in rws]
            check(len(rws) == 5, f"EXPECT radnor tranche-count", f"got {len(rws)}: {ids}")
            check("Class M-1A" in ids, "EXPECT radnor keeps -1A suffix", str(ids))
        if slug == "trinity-re-ltd" and rws:
            check("tranche_count_understated" in rws[0]["tranche_flags"],
                  "GUARD trinity understated-flag", rws[0]["tranche_flags"])
        for r in rws:
            st = r.get("stated_tranche_count")
            if st and st > len(rws):
                check("tranche_count_understated" in r["tranche_flags"],
                      f"GUARD understated-flagged {slug}", r["tranche_flags"])

        # GUARD: deal-level size history holds deal sizes only.
        if slug in SIZE_HISTORY:
            got = [(h["state"], h["value"])
                   for h in (rec["size_history"]["value"] or [])]
            check(got == SIZE_HISTORY[slug], f"EXPECT size_history {slug}",
                  f"want={SIZE_HISTORY[slug]} got={got}")
        # NOTE: "no deal state may equal a tranche size" looks like an
        # invariant and is not. Kilimanjaro genuinely launched at $300m and its
        # Class D genuinely settled at $300m. Coincidence, not contamination.
        # The exact SIZE_HISTORY expectations above are the real guard.

        # GUARD: never emit a known-wrong value.
        for key, bad in REJECT.get(slug, {}).items():
            got = rec[key]["value"]
            check(got != bad, f"REJECT {slug}:{key}", f"must not be {bad!r}, got {got!r}")

        # GUARD: a stated-multi deal we could not split must not be handed
        # single-tranche economics (Mosaic got launch $25m -> final $45m,
        # the Tier-1 total, a fabricated +80%).
        rws2 = parse_tranches(rec)
        for r in rws2:
            st = r.get("stated_tranche_count")
            if st and st > len([x for x in rws2 if x.get("tranche_id")] or rws2):
                check(r["tranche_size_final"] is None,
                      f"GUARD unresolved-multi-no-size {slug}",
                      f"got {r['tranche_size_final']!r}")

        # GUARD: a NAMED tranche with no size must be flagged, never silent.
        for r in rws2:
            if r.get("tranche_id") and not r.get("tranche_size_final"):
                fl = r.get("tranche_size_flags") or ""
                # "not issued" is an explanation, not a parse failure.
                check("tranche_size_missing" in fl or "tranche_not_issued" in fl
                      or "tranche_sizes_unassignable" in fl,
                      f"GUARD missing-size-explained {slug}:{r['tranche_id']}",
                      repr(fl))

        # GUARD: the validator actually runs, and its severities are sane.
        findings = validate(rec, rws2, None)
        for f in findings:
            check(f["severity"] in ("VIOLATION", "WARN", "info"),
                  f"GUARD validator-severity {slug}", str(f))
        check(not any(f["check"] == "spread>EL" for f in findings),
              f"GUARD spread>EL-is-not-a-violation {slug}",
              "collateral yield makes this a plausibility check, not an invariant")

    passed = sum(1 for ok, *_ in results if ok)
    for ok, label, detail in results:
        if not ok:
            print(f"  FAIL  {label}  {detail}")
    print(f"\n{passed}/{len(results)} checks passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
