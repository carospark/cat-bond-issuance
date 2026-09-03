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
from sibling_registry import SiblingRegistry  # noqa: E402
from fetch import DEAL_DIRECTORY_URL as BASE  # noqa: E402
from parse_deal import (_is_backward_reference, sentences,  # noqa: E402
                        _pct_to_float)
from parse_deal import (parse_deal, parse_tranches, check_tranche_sum,  # noqa: E402
                        MONTHS, TIER1_KEYS, MONEY_RE, NEGATED_RESIZE_RE,
                        CANCELLED_RE, TIER2_PATTERNS, TRANCHE_SIZE_RES,
                        _governed_by_loss_level, _bindings_by_label,
                        _launch_final, _apply_patterns, _currency,
                        _segment_prose_dated, _tranche_windows)
PAGES = [
    # Radnor: mortgage-ILS suffixed class labels (M-1A vs M-1).
    # Trinity: prose states a count it never breaks down -- must be flagged.
    "radnor-re-2020-2-ltd", "trinity-re-ltd",
    "kilimanjaro-ii-re-ltd-series-2017-1",   # decimal-comma percentages
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
    # Round 3/4: the pages whose defects motivated fixes that no test pinned.
    "finca-re-ltd-series-2022-1",       # deductible as launch size; "did not change"
    "merna-reinsurance-ltd",            # "Class A – $X" forward binding; term loans
    "everglades-re-ltd-series-2014-1",  # "$2.5 billion layer" as launch size
    "ibrd-car-111-112",                 # range low end as FINAL; per-tranche guidance
    "operational-re-ltd",               # CHF; dated Update headings
    "queen-street-x-re-ltd",            # "not completed / withdrawn"
    "baltic-pcc-limited-series-2025-1", # GBP; "remains at ... in size"
    "lion-i-re-ltd",                    # "coupon of 2.25% to 2.5%" low end
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
    "baltic-pcc-limited-series-2025-1": {
        "size": "\u00a3100m", "expected_loss": "2.54%", "attachment_probability": "2.75%",
        "spread_risk_margin": "5.9%", "maturity_date": "March 2028",
    },
    "lion-i-re-ltd": {
        "spread_risk_margin": "2.25%",   # "settled to offer investors a yield of 2.25%"
        "expected_loss": "1%", "attachment_probability": "2.1%",
        "exhaustion_probability": "0.45%",
    },
    "everglades-re-ltd-series-2014-1": {
        "attachment_probability": "2.89%",   # "attachment probability for the notes is"
        "spread_risk_margin": "7.5%",        # "pricing settled at the upper end ..., at 7.5%"
        "expected_loss": "2.3%",
    },
    "queen-street-x-re-ltd": {"size": None, "deal_status": "not_issued"},
    # A deal that never issued has no maturity, derived or otherwise.
    "gateway-re-ltd-series-2024-3": {"size": None, "maturity_scheduled": None,
                                     "deal_status": "not_issued"},
    # "attachment point of 2.47%" is a probability, not a monetary point.
    "finca-re-ltd-series-2022-1": {"attachment_probability": "2.47%",
                                   "attachment_point": None, "term_length": "three-year"},
    "operational-re-ltd": {"term_length": "five-year"},
    # "Private" means the prose says so; a sparse 2007 summary box does not.
    "merna-reinsurance-ltd": {"deal_is_private": None},
    "beazley-cyber-cat-bond-cairney": {"deal_is_private": True},
    # Multi-tranche: guidance is a tranche fact, never a deal column.
    "ibrd-car-111-112": {"price_guidance": None, "attachment_point": None},
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
        "Class M-1C": ("$93,137,000", "$93,137,000"),   # genuinely equal to M-1B
        "Class M-2": ("$99,790,000", "$99,790,000"),
        "Class B-1": ("$33,263,000", "$33,263,000"),
    },
    # "Class A – $256 million Class B – $647.6 million Class C – $155 million":
    # amount FOLLOWS its label. The backward regex shifted every size one
    # class along (B=$256m, C=$647.6m, A missing).
    "merna-reinsurance-ltd": {
        "Class A": ("$256 million", "$256 million"),
        "Class B": ("$647.6 million", "$647.6 million"),
        "Class C": ("$155 million", "$155 million"),
    },
    # Class A: "targeting at least $75 million" -> "priced to offer $225
    # million of notes". Class B: "targets $25 million" -> "between $25m and
    # $100m in size" (a range, never a final) -> "priced offering $95 million".
    "ibrd-car-111-112": {
        "Class A": ("$75 million", "$225 million"),
        "Class B": ("$25 million", "$95 million"),
    },
    # Written entirely in CHF: "a CHF105m Class A-1 tranche, a CHF5m Class A-2
    # tranche ... a CHF110m Class B set of notes".
    "operational-re-ltd": {
        "Class A-1": ("CHF105m", "CHF105m"),
        "Class A-2": ("CHF5m", "CHF5m"),
        "Class B": ("CHF110m", "CHF110m"),
    },
    "finca-re-ltd-series-2022-1": {"Class A": ("$75 million", "$75m")},
    # Single unlabelled tranche: launch from prose, final from Tier 1.
    "everglades-re-ltd-series-2014-1": {None: ("$400m", "$1.5bn")},
    "baltic-pcc-limited-series-2025-1": {None: ("\u00a3100 million", "\u00a3100m")},
    "lion-i-re-ltd": {None: ("\u20ac150m", "\u20ac190m ($262m)")},
}

# Deals whose tranche finals must sum to the Tier-1 deal size.
# Seaside is deliberately ABSENT: its only "tranche" is a Bermuda regulatory
# class misread as one, and because that phantom equals the deal total the sum
# check passed -- positively validating an invented structure.
TRANCHE_SUM_OK = {"triangle-re-2019-1-ltd", "atlantic-western-re-ltd",
                  "floodsmart-re-ltd-series-2024-1",
                  "residential-reinsurance-2026-limited-series-2026-1",
                  "kilimanjaro-re-ltd-series-2015-1",
                  "ursa-re-ltd-series-2015-1", "radnor-re-2020-2-ltd",
                  "ibrd-car-111-112", "everglades-re-ltd-series-2014-1",
                  "baltic-pcc-limited-series-2025-1", "lion-i-re-ltd",
                  "finca-re-ltd-series-2022-1",
                  # Tier-1 $1.18bn = $1,058.6m of notes + $122m of term loans;
                  # the check must know the headline's basis.
                  "merna-reinsurance-ltd"}

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
    # A cancelled deal must never report issued principal.
    "gateway-re-ltd-series-2024-3": {"size": "$100 million"},
    # "coupon of 2.25% to 2.5%" is a range; 2.25% must come from the settled
    # sentence, and the evidence must not be the range.
    "lion-i-re-ltd": {"price_guidance": "2.25%"},
}

# Deal-level size change: (direction, delta_pct) or None. Everglades used to
# read "$2.5 billion layer" as the launch and reported DOWNSIZED -40% with a
# reason that said "increased ... 213%".
SIZE_CHANGE = {
    "everglades-re-ltd-series-2014-1": ("upsized", 275.0),
    "windmill-ii-re-dac-2020": ("upsized", 25.0),    # EUR 80m -> EUR 100m
    "lion-i-re-ltd": ("upsized", 26.7),
    "merna-reinsurance-ltd": None,                   # "$9 million tranche C term loan"
    "citrus-re-ltd-series-2014-2": None,             # "$200m to $450m of its tower"
    "finca-re-ltd-series-2022-1": None,              # "$15 million ... deductible"
}

# Per-tranche values that are NOT deal facts. IBRD 111-112's deal-level
# guidance was Class B's while its spread was Class A's.
TRANCHE_FIELDS = {
    "ibrd-car-111-112": {"Class A": {"price_guidance": "7.25% to 8%", "spread_risk_margin": "6.9%"},
                         "Class B": {"price_guidance": "12.25% to 13%", "spread_risk_margin": "11.5%"}},
    "floodsmart-re-ltd-series-2024-1": {"Class A": {"attachment_point": "$9 billion"},
                                        "Class B": {"attachment_point": "$8 billion"}},
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
    "everglades-re-ltd-series-2014-1": [("launch", "$400m"), ("update_1", "$1.25 billion"),
                                        ("update_2", "$1.5 billion")],
    "merna-reinsurance-ltd": [],          # term loans and a class list; no deal state
    "finca-re-ltd-series-2022-1": [("update_1", "$75 million")],   # not the $15m deductible
    "citrus-re-ltd-series-2014-2": [("launch", "$50m"), ("update_1", "$50m")],
    "baltic-pcc-limited-series-2025-1": [("launch", "\u00a3100 million"),
                                         ("update_1", "\u00a3100 million"),
                                         ("update_2", "\u00a3100 million")],
    "lion-i-re-ltd": [("launch", "\u20ac150m"), ("update_1", "\u20ac180m"), ("update_2", "\u20ac190m")],
    # "$90 million (EUR 80m)": the conversion in the headline currency wins.
    "windmill-ii-re-dac-2020": [("launch", "EUR 80m"),
                                ("update_1", "EUR 80 million"),   # "expected to be between EUR 80m and EUR 100m"
                                ("update_2", "EUR 100 million")],
    "operational-re-ltd": [("update_1", "CHF630m"), ("update_4", "$223m")],
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


def unit_sentences():
    """Pin the segmenter directly.

    A blanket "never split after Ltd." is wrong and a naive `(?<=\.)\s+` is
    wrong in the other direction; only the uppercase-subject rule separates
    "Ltd. (Series 2013-1)" from "Ltd. The SPI has issued".
    """
    cases = [
        ("Windmill I Re Ltd. (Series 2013-1) was the first.", 1),
        ("Radnor Re 2020-2 Ltd. The SPI has issued five tranches.", 2),
        ("issued by Finca Re Ltd. catastrophe bond notes follow.", 1),
        ("covers U.S. Virgin Islands and U.S. Treasury exposure.", 1),
        ("across the U.S. tropical cyclone belt.", 1),
        ("A first sentence. A second sentence.", 2),
        ("FEMA Inc. The layer was secured.", 2),   # Inc. + uppercase = boundary
        ("FEMA Inc. and its partners secured it.", 1),   # + lowercase = not
    ]
    for text, want in cases:
        got = len(sentences(text))
        check(got == want, f"UNIT sentences {text[:44]!r}", f"want={want} got={got}")


def unit_sibling_registry():
    """Execute the sibling registry.

    It was dead for four commits -- `sentences = sentences(prose)` shadowed the
    imported function and every audit() raised UnboundLocalError -- because no
    test ever called it. Exercising a module is the minimum bar; this also
    asserts it still identifies a known predecessor figure.
    """
    reg = SiblingRegistry()
    url = BASE + "windmill-ii-re-dac-2020/"
    rec = parse_deal(fetch(url), deal_url=url)

    try:
        clean = reg.audit(url, rec, parse_tranches(rec))
    except Exception as exc:                      # noqa: BLE001
        check(False, "UNIT sibling-registry runs", f"{type(exc).__name__}: {exc}")
        return
    check(isinstance(clean, list), "UNIT sibling-registry runs", str(type(clean)))
    check(not any(f["verdict"] == "LIKELY_CONTAMINATION" for f in clean),
          "UNIT sibling-registry clean on current output", str(clean))

    # The figure the year-rule now removes IS Windmill I's size; if it were
    # still in the output the registry must name the sibling it belongs to.
    planted = [{"tranche_id": None, "tranche_size_final": "$46 million",
                "tranche_size_at_launch": None, "expected_loss": None,
                "attachment_probability": None, "spread_risk_margin": None}]
    found = reg.audit(url, rec, planted)
    check(any(f["verdict"] == "LIKELY_CONTAMINATION" for f in found),
          "UNIT sibling-registry detects planted contamination", str(found))


def unit_predicates():
    """Pin the vetoes and idioms on the corpus sentences that motivated them.

    Mutation testing showed the deductible veto, the negation check and both
    terminal-status routes could each be deleted with the suite green, because
    the pages that motivated them were not in PAGES and no predicate had a
    direct test.
    """
    for text, want in [
        ("Yes, that\u2019s a $2.5 billion layer of Citizens reinsurance tower", True),
        ("this higher layer being $100m in size, it would be no surprise", True),
        ("With the deal currently offering $50m of notes, but this higher layer", False),
        ("must surpass an index franchise deductible of $15 million.", True),
        ("$9 million tranche C term loan.", True),
        ("comes out of the blocks at $300m in size, split into two tranches", False),
    ]:
        m = MONEY_RE.search(text)
        got = _governed_by_loss_level(text, m.start(), m.end())
        check(got == want, f"UNIT loss-level {text[:40]!r}", f"want={want} got={got}")
    for text, want in [
        ("this issuance remains at UK \u00a3100 million in size, but the spread", True),
        ("did not change in size, so will secure the company $75 million", True),
        ("Zurich\u2019s retention will remain the same size", True),
        ("The Class E tranche has upsized to $325 million", False),
    ]:
        got = bool(NEGATED_RESIZE_RE.search(text))
        check(got == want, f"UNIT negated-resize {text[:40]!r}", f"want={want} got={got}")
    for text, want in [
        ("The Queen Street X Re Ltd. cat bond issuance was not completed.", True),
        ("It was withdrawn as the capacity and price targets could not be met", True),
        ("the sponsors made a commercial decision not to proceed with placing", True),
        ("The deal has been upsized and priced at the top of guidance.", False),
    ]:
        got = bool(CANCELLED_RE.search(text))
        check(got == want, f"UNIT cancelled {text[:40]!r}", f"want={want} got={got}")
    fwd = _bindings_by_label("Class A \u2013 $256 million Class B \u2013 $647.6 million Class C \u2013 $155 million")
    check(fwd == {"CLASS A": ["$256 million"], "CLASS B": ["$647.6 million"],
                  "CLASS C": ["$155 million"]}, "UNIT forward label binding", str(fwd))
    bwd = _bindings_by_label("The $134,574,000 tranche of Class M-1 notes; $16,821,000 tranche of Class B-1 notes.")
    check(bwd == {"CLASS M-1": ["$134,574,000"], "CLASS B-1": ["$16,821,000"]},
          "UNIT backward label binding", str(bwd))
    for text, want in [
        ("is now aiming for between $25m and $100m in size, we\u2019re told.", ("$25m", "range")),
        ("priced offering $95 million of notes at a bond coupon", ("$95 million", "priced")),
        ("targeting at least $75 million of coverage", ("$75 million", "stated")),
        ("protection would run from $200m to $450m of its tower", None),
    ]:
        got = next(((rx.search(text).group(rx.search(text).lastindex or 1), k)
                    for rx, k in TRANCHE_SIZE_RES if rx.search(text)), None)
        check(got == want, f"UNIT size idiom {text[:36]!r}", f"want={want} got={got}")
    lf = _launch_final([("$25 million", "range"), ("$25m", "range"), ("$95 million", "priced")])
    check(lf[:2] == ("$25 million", "$95 million"), "UNIT range never final", str(lf))
    lf = _launch_final([("$25m", "range")])
    check(lf[1] is None and "no_settled_size:range_only" in lf[2], "UNIT range-only no final", str(lf))
    for text, want in [
        ("offered with a coupon of 2.25% to 2.5%.", None),
        ("priced to pay investors a coupon of 4% to 4.5%.", None),
        ("settled to offer investors a yield of 2.25%, which is", "2.25%"),
    ]:
        got = _apply_patterns("spread_risk_margin", TIER2_PATTERNS["spread_risk_margin"], text)["value"]
        check(got == want, f"UNIT spread range {text[:36]!r}", f"want={want} got={got}")
    for text, want in [("C$150m", "CAD"), ("EUR 252m", "EUR"), ("CHF 220m", "CHF"),
                       ("\u20ac190m ($262m)", "EUR"), ("NZ$225m", "NZD"), ("$4m", "USD")]:
        check(_currency(text) == want, f"UNIT currency {text!r}", repr(_currency(text)))
    segs, dates = _segment_prose_dated(
        "Launch. Update 2 (May 4th 2016): two. Update, December 2018: three. Update: four.")
    check([l for l, _ in segs] == ["launch", "update_1", "update_2", "update_3"]
          and dates == {"update_1": "May 4th 2016", "update_2": "December 2018", "update_3": None},
          "UNIT segment labels + dates", f"{[l for l, _ in segs]} {dates}")
    w = _tranche_windows("Class 3 Bermuda-based insurer Kaith Re Ltd. has issued a $14.94 million tranche of notes.")
    check(w == [], "UNIT regulatory class is not a tranche", str(w))
    w = _tranche_windows("A $300 million Class A tranche of notes. A $50 million Class B tranche of notes.")
    check([l for l, _ in w] == ["Class A", "Class B"], "UNIT real classes kept", str(w))


def unit_registry_rules():
    """The registry's own copies of the parser's rules, pinned.

    `< issue_year - 1` survived here after round 1 fixed it in the parser, and
    hosts were matched by string so "$4m" (summary-box form) never found its
    "$4 million" sentence.
    """
    reg = SiblingRegistry()
    url = BASE + "residential-reinsurance-2020-limited-series-2020-1/"
    rec = parse_deal(fetch(url), deal_url=url)
    reg.known[url].append({"deal": "planted 2019-1", "field": "spread_risk_margin",
                           "raw": "8.25%", "num": 8.25})
    planted = [{"tranche_id": "Class X", "spread_risk_margin": "8.25%"}]
    found = reg.audit(url, rec, planted)
    check(any(f["verdict"] == "LIKELY_CONTAMINATION" for f in found),
          "UNIT registry year-1 sibling is backward", str(found))
    url = BASE + "residential-reinsurance-2000-ltd/"
    rec = parse_deal(fetch(url), deal_url=url)
    reg.known[url].append({"deal": "planted", "field": "size", "raw": "$200m", "num": 2e8})
    planted = [{"tranche_id": None, "tranche_size_at_launch": "$200m", "tranche_size_flags": ""}]
    found = reg.audit(url, rec, planted)
    check(found and found[0]["evidence"], "UNIT registry hosts matched by number",
          str(found))


def unit_percent_parsing():
    """Pin decimal-comma percentages.

    Artemis mixes separators on one page: Kilimanjaro II 2017-1 writes "an
    expected loss of 2,23%" beside "2.92%". The old grammar captured "23",
    reporting EL=23% against AP=2.92% -- impossible, caught by EL<=AP.

    Widening the grammar ALONE made it worse: "2,23" then went through a
    strip of every non-digit-non-dot character, which DELETES the comma and
    yields 223.0. Capture and conversion are tested together for that reason.
    """
    for raw, want in [("2,23%", 2.23), ("2.92%", 2.92), ("23%", 23.0),
                      ("5.74%", 5.74), (None, None), ("%", None),
                      ("no digits here", None)]:
        got = _pct_to_float(raw)
        check(got == want, f"UNIT pct {raw!r}", f"want={want} got={got}")


def main():
    unit_percent_parsing()
    unit_predicates()
    unit_registry_rules()
    unit_sibling_registry()
    unit_sentences()
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
            return _pct_to_float(v) if v else None
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
                e = _pct_to_float(r["expected_loss"])
                a = _pct_to_float(r["attachment_probability"])
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

        # EXPECT: deal-level size change direction and magnitude.
        if slug in SIZE_CHANGE:
            sc = rec["size_change"]["value"]
            got = (sc["direction"], sc["delta_pct"]) if sc else None
            check(got == SIZE_CHANGE[slug], f"EXPECT size_change {slug}",
                  f"want={SIZE_CHANGE[slug]} got={got}")
        # GUARD: a resize's direction never contradicts its own evidence.
        sc = rec["size_change"]["value"]
        if sc and sc.get("reason_evidence"):
            ev = sc["reason_evidence"].lower()
            check(not (sc["direction"] == "downsized"
                       and re.search(r"increas|upsiz|grew|lift", ev)
                       and not re.search(r"decreas|downsiz|reduc|shrank|shrunk", ev)),
                  f"GUARD size-change-direction {slug}", f"{sc['direction']}: {ev[:80]}")

        # EXPECT: tranche-level guidance / attachment / spread.
        for tid, fields in TRANCHE_FIELDS.get(slug, {}).items():
            r = rows_by_id.get(tid)
            for k, want in fields.items():
                got = r.get(k) if r else None
                check(got == want, f"EXPECT {slug}:{tid}:{k}", f"want={want!r} got={got!r}")
        # GUARD: on a multi-tranche page the deal columns hold no tranche fact.
        if len(rows_by_id) > 1:
            for k in ("price_guidance", "attachment_point"):
                check(rec[k]["value"] is None
                      and any(str(f).startswith("tranche_level_only") for f in rec[k]["flags"]),
                      f"GUARD no-deal-level-{k} {slug}", str(rec[k]))

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
                      or "tranche_sizes_unassignable" in fl
                      or "no_final_size" in fl,
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

        # GUARD: terminal status suppresses any issued-principal figure.
        if rec.get("deal_status", {}).get("value") in ("not_issued", "cancelled"):
            for r in parse_tranches(rec):
                check(r["tranche_size_final"] is None,
                      f"GUARD no-principal-when-not-issued {slug}",
                      f"got {r['tranche_size_final']!r}")
            check(rec["size"]["value"] is None,
                  f"GUARD no-tier1-size-when-not-issued {slug}",
                  repr(rec["size"]["value"]))

    # Pin the total. Guards are conditional on extracted data, so a regression
    # that empties a field silently removes its checks and the suite still
    # reports "all passed" on a smaller suite.
    EXPECTED_CHECKS = 559
    if len(results) != EXPECTED_CHECKS:
        results.append((False, "GUARD check-count",
                        f"expected {EXPECTED_CHECKS} checks, ran {len(results)}"
                        " - update EXPECTED_CHECKS deliberately"))

        # GUARD: a decimal comma must not inflate a percentage 100x.
        for r in parse_tranches(rec):
            el = _pct_to_float(r.get("expected_loss"))
            ap = _pct_to_float(r.get("attachment_probability"))
            if el is not None:
                check(el <= 100, f"GUARD pct-in-range {slug}:{r['tranche_id']}",
                      f"EL={el}")
            if el and ap:
                check(el <= ap, f"GUARD EL<=AP {slug}:{r['tranche_id']}",
                      f"EL={el} AP={ap}")

    passed = sum(1 for ok, *_ in results if ok)
    for ok, label, detail in results:
        if not ok:
            print(f"  FAIL  {label}  {detail}")
    print(f"\n{passed}/{len(results)} checks passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
