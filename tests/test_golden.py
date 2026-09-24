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
                        _pct_to_float, _series_tokens, CUMULATIVE_RE,
                        _cites_only_foreign_series,
                        SPECULATIVE_SIZE_RE, TRANCHE_OF_RE)
from mentions import canon_label, classify  # noqa: E402
from net_supply import usd_millions  # noqa: E402
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
    "home-re-2022-1-ltd",                    # five classes in a rating listing
    "kilimanjaro-ii-re-ltd-series-2017-1",   # decimal-comma percentages
    "blue-halo-re-ltd-series-2020-1",        # "Class B layer tranche" = tranche noun
    "east-lane-re-vi-ltd-series-2014-1",     # "42.7% of expected losses" = a share
    # Pages that each exposed a wrong output in adversarial review.
    "atlantic-western-re-ltd",          # lowercase "class A" labels
    "hoplon-ii-insurance-ltd",          # guidance endpoint sold as settled
    "mosaic-re-ii-ltd",                 # stated-multi given single-tranche size
    "triangle-re-2019-1-ltd",           # "$X tranche of Class Y" phrasing
    "residential-reinsurance-2020-limited-series-2020-1",  # predecessor coupon
    "citrus-re-ltd-series-2014-2",
    "citrus-re-ltd-series-2015-1",           # pilot deal: lifecycle fields      # same-year sibling contamination
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
    # Size-change validation round (2026-09): launch sizes that were not
    # sizes, or not this deal's. Each is a distinct mechanism; see the
    # KIND_CUES / SUBJECT_NOUNS comments in mentions.py and CUMULATIVE_RE /
    # SPECULATIVE_SIZE_RE / TRANCHE_OF_RE in parse_deal.py.
    "finca-re-ltd-series-2025-1",       # "$10 billion" index threshold
    "meadows-ltd-series-2025-1",        # "$8 billion" investor AUM
    "everglades-re-ii-ltd-series-2020-1-2020-2",  # "$900m" traditional towers
    "everglades-re-ii-ltd-series-2023-1-2023-2",  # one entry, two series: "across the two series" is OURS
    "longpoint-re-ii-ltd",              # "$2.25b" index trigger value
    "nature-coast-re-ltd-series-2024-1",  # "the layer ... is $200 million in size"
    "polestar-re-ltd-series-2024-3",    # "the attachment point ... is at $800 million"; speculative max
    "muteki-ltd",                       # programme aggregate volume
    "floodsmart-re-ltd-series-2020-1",  # "$1.1 billion ... after this deal is issued"
    "sanders-re-iii-ltd-series-2022-2", # "(Series 2022-1)" parenthetical is a NAME
    "kilimanjaro-iii-re-ltd-series-2026-2",  # "$530m across the two series" -> no launch
    "kilimanjaro-re-ltd-series-2014-1", # "$250m split evenly between the two tranches" IS a launch
    "radnor-re-2019-1-ltd",             # Tier-1 "Size: $473.18", unit lost
    "power-protective-re-ltd-series-2021-1",  # predecessor "which was $50m"; "maximum ... would be"
    "herbie-re-ltd-series-2020-2",      # "tranche of Cklass B notes" (sic)
    "blue-ridge-re-ltd-series-2025-1",  # "across the Series 2025-1 issuance" is its OWN series
    "winston-re-ltd-series-2026-1",     # sponsor "Tower Hill" is not a tower
    "isosceles-insurance-ltd-series-2023-a-c-g",  # letter series "2023-A, C, G"
    "mystic-re-ii-ltd-series-2009-1",   # "$50 billion" industry trigger level
    "akibare-re-pte-ltd-series-2020-1", # predecessor's "Class B" grew a phantom row
    # Size-change round two (2026-09-15): launch sizes that were ONE
    # COMPONENT's, or a predecessor's. See LABELLED_NOTES_RE, _each_scoped,
    # COUNTED_TRANCHES_RE, TRANCHE_PRONOUN_RE, AGGREGATE_RE and
    # PREDECESSOR_ANAPHORA_RE in parse_deal.py.
    "kilimanjaro-ii-re-ltd-series-2025-1",   # "$125 million across the ... A-1 and ... A-2 notes"
    "kilimanjaro-iii-re-ltd-series-2021-1",  # "A-1 and A-2 tranches ... each targets $150 million"
    "residential-reinsurance-2016-ltd-series-2016-1",  # "each tranche having a preliminary size of $50m"
    "acorn-re-ltd-series-2024-1",            # "each currently sized at $200 million"; "$225 million each"
    "3264-re-ltd-series-2024-1",             # "Two $50 million tranches of notes"
    "residential-reinsurance-2013-ltd-series-2013-2",  # "This tranche is being marketed ... $50m"
    "tar-heel-re-ltd-series-2013-1",         # "the $100m industry loss" is a trigger level
    "atlas-vi-capital-ltd-series-2011-1",    # "Ltd. Series 2011-1 Class A" split; "That deal afforded them $200m"
    "caelus-re-vi-ltd-series-2020-1-2020-2", # "annual aggregate" is a trigger, not a total
    # ... and the genuine deal-level sentences those vetoes must let through.
    "eclipse-re-ltd-series-2018-01a",        # "totaling $53.3 million and with each tranche"
    "sakura-re-ltd-series-2021-1",           # "each tranche ... $200 million ... for total ... of $400 million"
    "kilimanjaro-re-ltd-series-2018-1",      # "each series now targeting $262.5 million" is OURS
    "atlas-vi-capital-ltd-series-2010-1",    # "initially marketed at €60m but closed at €75m"
    "tradewynd-re-ltd-series-2013-1",        # "The tranche of notes ... grown by 25% to $125m", single tranche
    "mayflower-re-ltd-series-2026-1",        # "remain $75 million in size each"
    # Spread bias round (2026-09-15, backlog 9): zero-coupon prices of par
    # in the spread column. See _spread_is_price in parse_deal.py.
    "residential-reinsurance-2019-limited-series-2019-2",  # "priced at 77.25%, so a coupon equivalent of 22.75%"
    "matterhorn-re-ltd-series-2020-3",       # "settled at 90.5% of par"
    "gateway-re-ltd-series-2025-1",          # "zero-coupon pricing ... 93.75%"
    # Maturity recall round (2026-09-15, backlog 3): five more phrasings,
    # and the sentences that must NOT become the scheduled maturity.
    "johnston-re-ltd",                       # "three year deal which will run until May 2013"
    "successor-x-ltd-series-2011-3",         # "term of four years from November 2011 until November 2015"
    "residential-reinsurance-2010-ltd",      # "three year deal due to end in June 2013"
    "dodeka-ii",                             # "zero-coupon bond that expires in December 2014"
    "gold-eagle-capital-ltd",                # "risk period runs through March 31st, 2001" -> day stripped
    "residential-reinsurance-2014-ltd-series-2014-1",  # "maturity extended again to December 6th 2018"
    "lakeside-re-ii-ltd",                    # "Lakeside Re I ... expires at the end of Dec 2009 so this deal seeks to replace it"
    "residential-reinsurance-2024-limited-series-2024-1",  # "Class 11 tranche ... to the end of May 2025, while the other two"
    # Backlog 1 pages (2026-09-15): the attachment-probability object clause,
    # and a differently numbered vehicle cited without a year.
    "queen-street-vi-re-ltd",                # "attachment probability for the transaction is 3.87%"
    "mythen-re-ltd-series-2012-2",           # "... for the Class A tranche of notes is 2.16%"
    "vitality-re-vii-ltd-series-2016-1",     # "the Vitality Re II notes ... attachment probability of 0.03%"
    # Backlog 4 (lifecycle): a single unlabelled tranche, settled total loss.
    "artex-sac-limited-silver-crane-notes",  # "attached the notes and eroded their full principal"
    "ibrd-car-111-112",                      # "would face a 100% loss of principal" is a forecast, not a loss
    # Backlog 2 (2026-09-15): the deal total is never a tranche without a
    # dropped-class cue; an unlabelled "each tranche ... $X" fits every class.
    "chartwell-re-ltd-series-2025-1",        # Class C read the $330m headline
    "compass-re-ii-ltd-series-2015-1",       # Class A read the $300m headline
    "sakura-re-ltd-series-2021-1",           # "each tranche now targeting $200 million"
    "blue-ridge-re-ltd-series-2023-1",       # same, via the solver
    "tomoni-re-pte-ltd-series-2024-1",       # "Both tranches of notes priced at $100 million in size, while the Class A ..."
    "hypatia-ltd-series-2020-1",             # "the two $150 million tranches of notes"
    # ... and finals the label binder did not read (mentions.py size cues /
    # sentence-scoped, forward-first class scope).
    "3264-re-ltd-series-2025-1",             # "The Class A notes were priced to provide $100 million of cover"
    "tailwind-re-ltd-series-2017-1",         # "this tranche has now grown to $150 million", 130 chars after its label
    "bonanza-re-ltd-series-2023-1",          # "$70 million ... from the Class A ... notes, and $65 million from the Class B notes"
    # Phantom and withdrawn tranches (2026-09-15).
    "integrity-re-ltd-series-2022-1",        # "Class B tranche of notes being pulled and not being issued"
    "residential-reinsurance-2022-limited-series-2022-1",  # "Class 10 ... was pulled from the issuance"
    "kilimanjaro-re-ltd-series-2018-1",      # bare "Class A"/"Class B" beside A-1/A-2/B-1/B-2
    "sanders-re-iii-ltd-series-2022-1",      # "class is as yet unsized" grew a "Class IS" row
    # Unfinished 2026-09-15 patch recovered on takeover: compact class labels
    # and percentage changes that looked like settled spreads.
    "integrity-re-iii-ltd-series-2025-1",    # A1/A2/B1/B2 are distinct classes; no bleed into C
    "bellemeade-re-2020-1-ltd",              # M1-A and M-1A are the same class
    "ibis-re-ii-ltd-series-2013-1",          # "increase in pricing of 6.7%" is not a spread
    "everglades-re-ii-ltd-series-2015-1",   # "upsized by 20%" is not a spread
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
    # The tranche called a "layer": both its $25m statements were vetoed as
    # loss levels and the deal total backfilled in their place.
    "blue-halo-re-ltd-series-2020-1": {
        "Class A": ("$75 million", "$150 million"),
        "Class B": ("$25 million", "$25 million"),
    },
    # Enumerated as "$159.8 million Class M-1A (DBRS rated ...) $53.3 million
    # Class M-1B (...)": the word "tranche" appears once at the head of the
    # list, so requiring note-wording near every label found only two of five.
    "home-re-2022-1-ltd": {
        "Class M-1A": ("$159.8 million", "$159.8 million"),
        "Class M-1B": ("$53.3 million", "$53.3 million"),
        "Class M-1C": ("$183.5 million", "$183.5 million"),
        "Class M-2": ("$47.4 million", "$47.4 million"),
        "Class B-1": ("$29.6 million", "$29.6 million"),
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
    # Vitality Re II's attachment probability, cited on Vitality Re VII's page
    "vitality-re-vii-ltd-series-2016-1": {"attachment_probability": "0.03%"},
    # the U.S. hurricane peril's AP, not the transaction's 3.87%
    "queen-street-vi-re-ltd": {"attachment_probability": "1.8%"},
    # Maturity round: an extension, a predecessor's expiry, one class's term.
    "residential-reinsurance-2014-ltd-series-2014-1": {"maturity_date": "December 2018"},
    "lakeside-re-ii-ltd": {"maturity_date": "Dec 2009"},
    "residential-reinsurance-2024-limited-series-2024-1": {"maturity_date": "May 2025"},
    # the 2019-1 predecessor's coupon, adopted as this deal's spread
    "residential-reinsurance-2020-limited-series-2020-1": {"spread_risk_margin": "8.25%"},
    # the LOW END of "guide pricing of 11.25% to 12.25%", not the settled 12%
    "hoplon-ii-insurance-ltd": {"spread_risk_margin": "11.25%"},
    # $200m/$350m are the Citrus 2014-1 layer bounds, not 2014-2's
    "citrus-re-ltd-series-2014-2": {"attachment_point": "$200m"},
    # "New York 42.7% of expected losses" is a geographic SHARE of the EL.
    "east-lane-re-vi-ltd-series-2014-1": {"expected_loss": "42.7%"},
    # Medical benefit ratios (~96-102%) are a different unit, never EL/AP.
    "vitality-re-v-ltd-series-2014-1": {"expected_loss": "99.55%",
                                        "attachment_probability": "96%"},
    # Akibare 2018-1's EL, cited "for comparison" on the 2020-1 page.
    "akibare-re-pte-ltd-series-2020-1": {"expected_loss": "0.99%"},
    # A cancelled deal must never report issued principal.
    "gateway-re-ltd-series-2024-3": {"size": "$100 million"},
    # "coupon of 2.25% to 2.5%" is a range; 2.25% must come from the settled
    # sentence, and the evidence must not be the range.
    "lion-i-re-ltd": {"price_guidance": "2.25%"},
}

# Stated scheduled maturity, normalised to "Month YYYY".
MATURITY = {
    "johnston-re-ltd": "May 2013",
    "successor-x-ltd-series-2011-3": "November 2015",
    "residential-reinsurance-2010-ltd": "June 2013",
    "dodeka-ii": "December 2014",
    "gold-eagle-capital-ltd": "March 2001",     # "March 31st, 2001"
    "residential-reinsurance-2014-ltd-series-2014-1": None,
    "lakeside-re-ii-ltd": None,
    "residential-reinsurance-2024-limited-series-2024-1": None,
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
    # 2026-09 size-change round. A None here means the page states no launch
    # size for THIS deal; the value it used to report is in SIZE_LAUNCH_REJECT.
    "finca-re-ltd-series-2025-1": None,
    "meadows-ltd-series-2025-1": ("upsized", 8.0),         # $125m -> $135m
    "polestar-re-ltd-series-2024-3": ("upsized", 180.0),   # $75m -> $210m
    "floodsmart-re-ltd-series-2020-1": ("upsized", 33.3),  # $300m -> $400m
    "sanders-re-iii-ltd-series-2022-2": ("upsized", 15.0), # $250m -> $287.5m
    "everglades-re-ii-ltd-series-2023-1-2023-2": ("upsized", 275.0),
    "blue-ridge-re-ltd-series-2025-1": ("upsized", 53.8),  # $325m -> $500m
    "kilimanjaro-re-ltd-series-2014-1": ("upsized", 80.0), # $250m -> $450m
    "isosceles-insurance-ltd-series-2023-a-c-g": None,     # $87.6m -> $87.6m
    "radnor-re-2019-1-ltd": None,
    "power-protective-re-ltd-series-2021-1": None,
    "nature-coast-re-ltd-series-2024-1": None,
    "longpoint-re-ii-ltd": None,
    "muteki-ltd": None,
    "everglades-re-ii-ltd-series-2020-1-2020-2": None,
    "kilimanjaro-iii-re-ltd-series-2026-2": None,
    "herbie-re-ltd-series-2020-2": None,
    "mystic-re-ii-ltd-series-2009-1": None,
    # 2026-09-15 round two. Tar Heel's page says "increased in size by 150%".
    "tar-heel-re-ltd-series-2013-1": ("upsized", 150.0),   # $200m -> $500m, was +400% off "$100m industry loss"
    "kilimanjaro-ii-re-ltd-series-2025-1": None,           # was +300% off one pair's $125m
    "kilimanjaro-iii-re-ltd-series-2021-1": None,          # was +113% off "each targets $150 million"
    "residential-reinsurance-2016-ltd-series-2016-1": None,  # was +400% off "each tranche ... $50m"
    "acorn-re-ltd-series-2024-1": None,                    # was +125% for a +12.5% deal
    "3264-re-ltd-series-2024-1": None,                     # was +180% for a +40% deal
    "residential-reinsurance-2013-ltd-series-2013-2": None,  # was +200% off "This tranche ... $50m"
    "atlas-vi-capital-ltd-series-2011-1": None,            # was +574% off Class A's $50m
    "caelus-re-vi-ltd-series-2020-1-2020-2": None,         # was +145% for a +44% deal
}

# Launch sizes that were reported and are NOT this deal's launch size. A
# REJECT for the launch state specifically: the whole-history expectations
# below pin the positive; this pins the mechanism each page exposed.
SIZE_LAUNCH_REJECT = {
    "finca-re-ltd-series-2025-1": "$10 billion",        # index threshold
    "meadows-ltd-series-2025-1": "$8 billion",          # investor AUM
    "everglades-re-ii-ltd-series-2020-1-2020-2": "$900 million",  # traditional towers
    "longpoint-re-ii-ltd": "$2.25b",                    # index trigger value
    "nature-coast-re-ltd-series-2024-1": "$200 million",  # the layer's width
    "polestar-re-ltd-series-2024-3": "$800 million",    # attachment point
    "muteki-ltd": "US$ 1bn",                            # programme volume
    "floodsmart-re-ltd-series-2020-1": "$1.1 billion",  # cover after this deal
    "sanders-re-iii-ltd-series-2022-2": "$550 million", # Series 2022-1's size
    "kilimanjaro-iii-re-ltd-series-2026-2": "$530 million",  # across two series
    "power-protective-re-ltd-series-2021-1": "$50 million",  # predecessor's size
    "herbie-re-ltd-series-2020-2": "$125 million",      # Series 2020-1's size
    "mystic-re-ii-ltd-series-2009-1": "$50 billion",    # industry trigger level
    # 2026-09-15 round two: one component's size, or a predecessor's.
    "kilimanjaro-ii-re-ltd-series-2025-1": "$125 million",   # the A-1/A-2 pair's target
    "kilimanjaro-iii-re-ltd-series-2021-1": "$150 million",  # "each targets"
    "residential-reinsurance-2016-ltd-series-2016-1": "$50m",  # "each tranche having"
    "acorn-re-ltd-series-2024-1": "$200 million",       # "each currently sized at"
    "3264-re-ltd-series-2024-1": "$50 million",         # "Two $50 million tranches"
    "residential-reinsurance-2013-ltd-series-2013-2": "$50m",  # "This tranche"
    "tar-heel-re-ltd-series-2013-1": "$100m",           # "the $100m industry loss"
    "atlas-vi-capital-ltd-series-2011-1": "$50m",       # Class A's size, split off by "Ltd."
    "caelus-re-vi-ltd-series-2020-1-2020-2": "$200 million",  # Series 2020-1's component
}

# Exact tranche row count. Akibare 2020-1 is "a single tranche of Series
# 2020-1 Class A notes"; the Class B it mentions belongs to Series 2018-1.
TRANCHE_COUNT = {"akibare-re-pte-ltd-series-2020-1": 1,
                 "kilimanjaro-re-ltd-series-2018-1": 4,   # A-1, A-2, B-1, B-2; not the parent labels
                 "sanders-re-iii-ltd-series-2022-1": 3,   # A, B, C; not "Class IS"
                 "bellemeade-re-2020-1-ltd": 3}           # M-1A, M-1B, B-1; no spelling duplicates

# Flags that must be present: the "why" beside an honest None.
FLAGS = {
    "radnor-re-2019-1-ltd": {"size": "unit_missing"},
    "kilimanjaro-iii-re-ltd-series-2026-2": {"size_history": "launch_target_shared_across_series"},
}

# Per-tranche values that are NOT deal facts. IBRD 111-112's deal-level
# guidance was Class B's while its spread was Class A's.
TRANCHE_FIELDS = {
    "ibrd-car-111-112": {"Class A": {"price_guidance": "7.25% to 8%", "spread_risk_margin": "6.9%"},
                         "Class B": {"price_guidance": "12.25% to 13%", "spread_risk_margin": "11.5%"}},
    "floodsmart-re-ltd-series-2024-1": {"Class A": {"attachment_point": "$9 billion"},
                                        "Class B": {"attachment_point": "$8 billion"}},
    # "probability of attachment of 21.38%": the other word order.
    "residential-reinsurance-2013-ltd-series-2013-2": {"Class 1": {"attachment_probability": "21.38%"}},
    # Not the "5.2%" energy share from "4% of expected losses, followed by
    # energy at 5.2%"; that capture put EL above AP.
    "tradewynd-re-ltd-series-2013-1": {"Class 1": {"expected_loss": "1.43%"}},
    # Zero-coupon notes: the price of par is not the spread. Residential Re
    # states the equivalent; Matterhorn's "similar to a 9% to 9.75% coupon
    # range" is a range, so honest None.
    "residential-reinsurance-2019-limited-series-2019-2": {"Class 1": {"spread_risk_margin": "22.75%"},
                                                           "Class 2": {"spread_risk_margin": "11.5%"}},
    "matterhorn-re-ltd-series-2020-3": {"Class C": {"spread_risk_margin": None}},
    "gateway-re-ltd-series-2025-1": {"Class A": {"spread_risk_margin": None}},
    # "attachment probability for the Class A tranche of notes is 2.16%", not
    # the UK mortality peril's 0.36% (EL 1.7% sat above it).
    "mythen-re-ltd-series-2012-2": {"Class A": {"attachment_probability": "2.16%"}},
    "vitality-re-vii-ltd-series-2016-1": {"Class A": {"attachment_probability": None}},
    # Lifecycle: settled total loss on a one-tranche page with no Class label;
    # a hedged "would face a 100% loss" must stay None.
    "artex-sac-limited-silver-crane-notes": {None: {"principal_loss_pct": 100.0}},
    "ibrd-car-111-112": {"Class B": {"principal_loss_pct": None}},
    # Backlog 2: parts-vs-whole.
    "chartwell-re-ltd-series-2025-1": {"Class C": {"tranche_size_final": None}},
    "compass-re-ii-ltd-series-2015-1": {"Class A": {"tranche_size_final": None}},
    "sakura-re-ltd-series-2021-1": {"Class A": {"tranche_size_final": "$200 million"},
                                    "Class B": {"tranche_size_final": "$200 million"}},
    "blue-ridge-re-ltd-series-2023-1": {"Class A": {"tranche_size_final": "$200 million"}},
    "tomoni-re-pte-ltd-series-2024-1": {"Class A": {"tranche_size_final": "$100 million"},
                                        "Class B": {"tranche_size_final": "$100 million"}},
    "hypatia-ltd-series-2020-1": {"Class A": {"tranche_size_final": "$150 million"},
                                  "Class B": {"tranche_size_final": "$150 million"}},
    "3264-re-ltd-series-2025-1": {"Class A": {"tranche_size_final": "$100 million"},
                                  "Class B": {"tranche_size_final": "$100 million"}},
    "tailwind-re-ltd-series-2017-1": {"Class A": {"tranche_size_final": "$150 million"},
                                      "Class C": {"tranche_size_final": "$100 million"}},
    "bonanza-re-ltd-series-2023-1": {"Class A": {"tranche_size_final": "$70 million"},
                                     "Class B": {"tranche_size_final": "$65 million"}},
    # "expected loss of 17.43%, were eventually confirmed as $37.5 million in
    # size": a modelled loss is not a payout cue; 150 + 100 + 37.5 = 287.5.
    "sanders-re-iii-ltd-series-2022-2": {"Class C": {"tranche_size_final": "$37.5 million"}},
    # Withdrawn classes carry no size and the sum check counts them as zero.
    "integrity-re-ltd-series-2022-1": {"Class B": {"tranche_size_final": None}},
    "residential-reinsurance-2022-limited-series-2022-1": {"Class 10": {"tranche_size_final": None}},
    # Compact labels are canonicalised before windows bind tranche facts.
    "integrity-re-iii-ltd-series-2025-1": {
        "Class A-1": {"spread_risk_margin": "8%"},
        "Class A-2": {"spread_risk_margin": "8%"},
        "Class B-1": {"spread_risk_margin": "9.75%"},
        "Class B-2": {"spread_risk_margin": "9.75%"},
        "Class C": {"spread_risk_margin": "12.25%"},
        "Class D": {"spread_risk_margin": "25.5%"},
    },
    "bellemeade-re-2020-1-ltd": {
        "Class M-1A": {"tranche_size_final": "$252.124m"},
        "Class M-1B": {"tranche_size_final": "$171.5m"},
        "Class B-1": {"tranche_size_final": "$26.43m"},
    },
    # The false percentages are rejected. Where no precise settled-price
    # idiom matches, an honest None is preferred to a plausible wrong value.
    "ibis-re-ii-ltd-series-2013-1": {
        "Class A": {"spread_risk_margin": None},
        "Class B": {"spread_risk_margin": "4.5%"},
        "Class C": {"spread_risk_margin": None},
    },
    "everglades-re-ii-ltd-series-2015-1": {
        "Class A": {"spread_risk_margin": "5.15%"},
    },
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
    # 2026-09-15 round two. Empty lists are assertions: Kilimanjaro III 2021-1
    # and Atlas VI 2011-1 state no deal-level size at all ("That deal afforded
    # them $200m" is the 2010 bond's). Acorn's "$225 million each" is gone too.
    "kilimanjaro-ii-re-ltd-series-2025-1": [("update_1", "$900 million"), ("update_2", "$900 million")],
    "kilimanjaro-iii-re-ltd-series-2021-1": [],
    "atlas-vi-capital-ltd-series-2011-1": [],
    "tar-heel-re-ltd-series-2013-1": [("launch", "$200m"), ("update_1", "$500m")],
    "acorn-re-ltd-series-2024-1": [("update_1", "$450 million"),
                                   ("update_2", "$450 million")],  # the total, not "$225 million each"
    "3264-re-ltd-series-2024-1": [("update_1", "$140 million")],
    "residential-reinsurance-2016-ltd-series-2016-1": [("update_3", "$250m")],
    "caelus-re-vi-ltd-series-2020-1-2020-2": [("update_2", "$490 million")],
    "eclipse-re-ltd-series-2018-01a": [("launch", "$53.3 million")],  # not "up to $250 million of losses"
    "sakura-re-ltd-series-2021-1": [("update_1", "$400 million")],    # the total, not the $200m per tranche
    "kilimanjaro-re-ltd-series-2018-1": [("update_1", "$262.5 million")],
    "atlas-vi-capital-ltd-series-2010-1": [("launch", "\u20ac60m")],
    "tradewynd-re-ltd-series-2013-1": [("update_1", "$125m")],
    "mayflower-re-ltd-series-2026-1": [("update_3", "$150 million")],  # not the $75m "in size each"
    # 2026-09 size-change round.
    "finca-re-ltd-series-2025-1": [("update_1", "$125 million")],
    "meadows-ltd-series-2025-1": [("launch", "$125 million"), ("update_1", "$135 million"),
                                  ("update_2", "$135 million"), ("update_3", "$135 million")],
    "everglades-re-ii-ltd-series-2020-1-2020-2": [],
    "everglades-re-ii-ltd-series-2023-1-2023-2": [
        ("launch", "$200 million"), ("update_1", "$600 million"),   # "across the two series" = this entry
        ("update_2", "$775 million"), ("update_3", "$750 million")],
    "longpoint-re-ii-ltd": [],
    "nature-coast-re-ltd-series-2024-1": [("update_1", "$50 million")],
    "polestar-re-ltd-series-2024-3": [("launch", "$75 million"), ("update_1", "$200 million"),
                                      ("update_2", "$210 million")],
    "muteki-ltd": [],
    "floodsmart-re-ltd-series-2020-1": [("launch", "$300 million"), ("update_2", "$400 million")],
    "sanders-re-iii-ltd-series-2022-2": [("launch", "$250 million"), ("update_1", "$275 million"),
                                         ("update_2", "$287.5 million")],
    "kilimanjaro-iii-re-ltd-series-2026-2": [],
    "kilimanjaro-re-ltd-series-2014-1": [("launch", "$250m"), ("update_2", "$200m")],
    "radnor-re-2019-1-ltd": [("launch", "$44 million"), ("update_1", "$473.2 million")],
    "power-protective-re-ltd-series-2021-1": [("update_2", "$30 million")],
    "herbie-re-ltd-series-2020-2": [("update_1", "$225 million"), ("update_2", "$275 million")],
    "blue-ridge-re-ltd-series-2025-1": [("launch", "$325 million"), ("update_2", "$475 million"),
                                        ("update_3", "$500 million")],
    "winston-re-ltd-series-2026-1": [("launch", "$225 million"), ("update_1", "$375 million"),
                                     ("update_2", "$375 million"), ("update_3", "$375 million")],
    "isosceles-insurance-ltd-series-2023-a-c-g": [("launch", "$87.6 million")],
    "mystic-re-ii-ltd-series-2009-1": [],
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
        # ... but "(Series 2022-1)" after an issuer name is the NAME of another
        # deal, not an aside (Sanders Re III 2022-2 adopted 2022-1's $550m).
        ("the insurer secured $550 million from a Sanders Re III Ltd. (Series 2022-1) transaction.",
         2022, frozenset({"2022-2"}), True),
        # own_series carries the vehicle token too (from the deal name / slug)
        ("a $250 million or greater Sanders Re III Ltd. (Series 2022-2) issuance now in the market.",
         2022, frozenset({"2022-2", "RE III"}), False),
        # a letter-series entry citing one of its own series
        ("$27.15955 million Series 2023-C notes due June 7, 2024.",
         2023, frozenset({"2023-A", "2023-C", "2023-G"}), False),
    ]
    # Tranche labels that live only in a sentence about ANOTHER series are
    # that deal's tranches (Akibare 2020-1's "Class B ... (Series 2018-1)");
    # a sentence naming both series is about both (twin Kilimanjaro).
    for sentence, own, want in [
        ("the $100 million Class B tranche of notes from Akibare Re Ltd. (Series 2018-1) catastrophe",
         {"2020-1"}, True),
        ("The Series 2018-1 Class A-1 and Series 2018-2 Class A-2 notes will target $50 million",
         {"2018-1"}, False),
        ("$21.854m Class B-1 notes, unrated.", {"2021-3"}, False),
        ("The Class 13 tranche is similar to a Class 5 tranche from Residential Reinsurance 2012 Ltd. (Series 2012-1) cat bond.",
         {"2014-1"}, True),
    ]:
        got = _cites_only_foreign_series(sentence, own)
        check(got == want, f"UNIT foreign-series-only {sentence[:40]!r}", f"want={want} got={got}")
    for text, want in [
        ("Isosceles Insurance Ltd. (Series 2023-A, C, G)", {"2023-A", "2023-C", "2023-G"}),
        ("isosceles-insurance-ltd-series-2023-a-c-g", {"2023-A", "2023-C", "2023-G"}),
        ("everglades-re-ii-ltd-series-2020-1-2020-2", {"2020-1", "2020-2", "RE II"}),
        ("eclipse-re-ltd-series-2019-03a", {"2019-03A"}),
        ("no series here, matures in 2027", set()),
    ]:
        got = _series_tokens(text)
        check(got == want, f"UNIT series_tokens {text[:40]!r}", f"want={want} got={got}")
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
    # Amount kinds added in the 2026-09 size-change round, one page each.
    for text, amount, want in [
        ("to be above a threshold of $10 billion to qualify during each annual risk period",
         "$10 billion", "threshold"),
        ("One William Street Capital Management has around US $8 billion in assets under management",
         "US $8 billion", "aum"),
        ("sit alongside traditional sources of reinsurance spanning some $900 million of its two reinsurance towers",
         "$900 million", "other_capital"),
        ("there will be an initial index trigger value of $2.25b.", "$2.25b", "trigger"),
        ("a weighted insured industry loss trigger level of $50 billion, based on", "$50 billion", "trigger"),
        ("through future issuances for an aggregate volume of up to US$ 1bn.", "US$ 1bn", "other_capital"),
        # each other_capital cue alone, so a redundant neighbour cannot mask it
        ("for an aggregate volume of up to US$ 1bn.", "US$ 1bn", "other_capital"),
        ("Vita Capital III is a shelf-offering programme allowing Swiss Re to issue up to USD 2 billion of securities",
         "USD 2 billion", "other_capital"),
        ("with the $200 million or so likely to sit alongside its other cover", "$200 million", "other_capital"),
        ("Zenkyoren can transfer more risk through future issuances of up to US$ 1bn from the vehicle",
         "US$ 1bn", "other_capital"),
        # subject rule: "Class B layer" is a tranche noun, so the next noun
        # ("tranche") governs and the amount is a size
        ("The Class B layer tranche sitting above the A notes to provide aggregate cover for the sponsor is $25 million in size",
         "$25 million", "size"),
        # subject rule needs a copula: without "is/was/sits", an early loss
        # noun in the clause does not govern a later amount
        ("Given the attachment point the sponsor selected the offering will seek $150 million of notes",
         "$150 million", "size"),
        # the bridged attachment cue governs only the amount AFTER it: here
        # it sits in $175m's after-window and must not claim it
        ("A Series 2025-1 Class B tranche targets $175 million in coverage for Palomar, attaching lower down at $650 million and exhausting coverage at",
         "$175 million", "unknown"),
        ("A Series 2025-1 Class B tranche targets $175 million in coverage for Palomar, attaching lower down at $650 million and exhausting coverage at",
         "$650 million", "attachment"),
        ("will attach their coverage at $3 billion of losses and exhausting at $3.75 billion, which gives them",
         "$3.75 billion", "exhaustion"),
        # "alongside" only when something SITS alongside; not "marketed
        # to investors, alongside their preliminary ratings: $92.0 million"
        ("being marketed to investors, alongside their preliminary ratings from DBRS Morningstar: $92.0 million Class M-1A at BBB",
         "$92.0 million", "unknown"),
        ("at least as big as the first LADWP cat bond, which was $50 million in size.",
         "$50 million", "predecessor"),
        # clause SUBJECT governs a copula predicate
        ("So the layer of SafePoints reinsurance tower where this new Nature Coast Re 2024-1 cat bond will feature is $200 million in size, suggesting",
         "$200 million", "layer"),
        ("This time though, the attachment point for the PoleStar Re 2024-3 cyber cat bond notes is at $800 million, sitting atop",
         "$800 million", "attachment"),
        ("These notes will also provide per-occurrence protection, but attach lower down at $1.795 billion.",
         "$1.795 billion", "attachment"),
        # ... and must not fire on these
        # unknown is admitted; the point is that "Tower" is not a tower
        ("Tower Hill Insurance Exchange is now fixed on the $375 million target, while pricing",
         "$375 million", "unknown"),
        ("the deal is $150 million in size, with an attachment point of $2 billion", "$150 million", "size"),
        ("comes out of the blocks at $300m in size, split into two tranches", "$300m", "size"),
        ("with a target issuance size of $125 million or more.", "$125 million", "size"),
    ]:
        i = text.index(amount)
        got = classify(text, i, i + len(amount))[0]
        check(got == want, f"UNIT classify {text[:40]!r}", f"want={want} got={got}")
    # Sentence-level vetoes on the deal-size loop.
    for text, want in [
        ("Across the two series offered, Everest is at first targeting at least $530 million of retrocession.", True),
        ("FEMA will benefit from at least $1.1 billion of catastrophe bond backed flood reinsurance coverage after this deal is issued.", True),
        ("Both Series target $500m of fully collateralised reinsurance protection each", True),
        ("At launch the cat bond is being marketed as a $250m transaction split evenly between the two tranches of notes", False),
        ("the initial target is for $325 million of protection across the Series 2025-1 issuance.", False),
    ]:
        got = bool(CUMULATIVE_RE.search(text))
        check(got == want, f"UNIT cumulative {text[:40]!r}", f"want={want} got={got}")
    for text, want in [
        ("That suggests the maximum size of this cat bond would be $150 million, to cover the entire layer", True),
        ("That could suggest a maximum size of $400 million were investor appetite to prove strong enough", True),
        ("Florida Citizens has significantly increased its target size for these new catastrophe bonds, with as much as $600 million in reinsurance now sought", False),
        ("The deal is targeting $300 million of flood reinsurance protection for FEMA", False),
    ]:
        got = bool(SPECULATIVE_SIZE_RE.search(text))
        check(got == want, f"UNIT speculative {text[:40]!r}", f"want={want} got={got}")
    for text, want in [
        ("An also $75 million tranche of Cklass B notes have an initial expected loss of 3.61%", True),
        ("Seaside Re will issue a $50 million tranche of notes to investors", False),
    ]:
        got = bool(TRANCHE_OF_RE.search(text))
        check(got == want, f"UNIT tranche-of {text[:40]!r}", f"want={want} got={got}")
    for text, want in [("$473.18", (None, "unit_missing")), ("$473.18m", (473.18, "usd")),
                       ("$1.5 billion", (1500.0, "usd")), ("$298.89", (None, "unit_missing"))]:
        got = usd_millions(text)
        check(got == want, f"UNIT usd_millions {text!r}", f"want={want} got={got}")
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
    for raw, want in [("A1", "A-1"), ("A-1", "A-1"),
                      ("M1-A", "M-1A"), ("M-1A", "M-1A"),
                      ("A", "A"), ("10", "10")]:
        check(canon_label(raw) == want, f"UNIT canonical class label {raw}",
              f"want={want!r} got={canon_label(raw)!r}")
    got = [label for label, _ in _tranche_windows(
        "A $50 million Class A1 tranche of notes. "
        "A $75 million Class A2 tranche of notes. "
        "The Class C tranche was $25 million.")]
    check(got == ["Class A-1", "Class A-2", "Class C"],
          "UNIT compact class labels split windows", repr(got))
    for text, want in [
        ("At final pricing the cat bond upsized by 20% to reach $300m in size.", None),
        ("an increase in pricing of 6.7% from the mid-point of the original range.", None),
        ("The notes were priced at 5.15%.", "5.15%"),
        ("The Class A notes are $50 million and their pricing was fixed at 8%.", "8%"),
    ]:
        got = _apply_patterns("spread_risk_margin", TIER2_PATTERNS["spread_risk_margin"], text)["value"]
        check(got == want, f"UNIT settled spread {text[:38]!r}",
              f"want={want!r} got={got!r}")
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


from parse_deal import (_each_scoped, LABELLED_NOTES_RE, COUNTED_TRANCHES_RE,  # noqa: E402
                        TRANCHE_PRONOUN_RE, AGGREGATE_RE, PREDECESSOR_ANAPHORA_RE,
                        sentences, _is_backward_reference, INITIAL_IDIOM_RE,
                        _spread_is_price, TIER2_PATTERNS, MATURITY_EXCLUDE_RE, _strip_day,
                        _series_tokens, LC_ZERO_RE, LC_SPECULATIVE_RE, _bindings_by_label,
                        TRANCHE_DROPPED_RE, _per_tranche_amount, TRANCHE_WITHDRAWN_RE, CLASS_STOPWORDS)
from mentions import extract as mentions_extract  # noqa: E402


def unit_component_scope():
    """Pin the per-component vetoes of the 2026-09-15 size-change round.

    Each predicate on the corpus sentence that motivated it AND on a genuine
    deal-level sentence it must let through; the golden pages above only see
    the end-to-end effect.
    """
    for text, want in [
        ("with each tranche having a preliminary size of $50m.", True),
        ("two tranches of notes, each currently sized at $200 million.", True),
        ("both tranches of notes upsizing to $225 million each, for total", True),
        ("The A-1 and A-2 tranches each targets $150 million, we understand.", True),
        ("comes out of the blocks at $300m in size, split into two tranches of notes, each of which", False),
        ("marketed as a $250m transaction split evenly between the two tranches", False),
        ("notes issued, totaling $53.3 million and with each tranche corresponding to a single", False),
        ("Both tranches of notes remain $75 million in size each at this time", True),
        ("with each series now targeting $262.5 million of coverage across the two tranches", False),
    ]:
        m = MONEY_RE.search(text)
        got = _each_scoped(text, m.start(), m.end())
        check(got == want, f"UNIT each-scoped {text[:40]!r}", f"want={want} got={got}")
    for rx, text, want in [
        (LABELLED_NOTES_RE, "a target of $125 million across the four year A-1 and five year A-2 notes", True),
        (LABELLED_NOTES_RE, "seeking $200 million of Series 2025-1 notes", False),
        (LABELLED_NOTES_RE, "the IBRD CAR-120 notes for Peru", False),
        (COUNTED_TRANCHES_RE, "Two $50 million tranches of notes are being offered", True),
        (COUNTED_TRANCHES_RE, "will issue a $50 million tranche of notes", False),
        (TRANCHE_PRONOUN_RE, "This tranche is being marketed with a preliminary size of $50m.", True),
        (TRANCHE_PRONOUN_RE, "The single tranche of notes targets at least $75 million", False),
        (AGGREGATE_RE, "are targeting annual aggregate indemnity reinsurance", False),
        (AGGREGATE_RE, "for a total of $340 million across the five tranches", True),
        (AGGREGATE_RE, "$500 million in aggregate", True),
        (PREDECESSOR_ANAPHORA_RE, "That deal afforded them $200m of cover for those risks", True),
        (PREDECESSOR_ANAPHORA_RE, "This deal will see Long Point Re III Ltd. issue a single tranche", False),
    ]:
        got = bool(rx.search(text))
        check(got == want, f"UNIT {rx.pattern[:18]!r} on {text[:36]!r}", f"want={want} got={got}")
    for text, want in [
        ("must be large enough to create the $100m industry loss as well as cause", True),
        ("designed to cover U.S. Coastal up to $250 million of losses and we understand", True),
        ("seeking $200 million of loss protection from the capital markets", False),
    ]:
        m = MONEY_RE.search(text)
        got = _governed_by_loss_level(text, m.start(), m.end())
        check(got == want, f"UNIT loss-level suffix {text[:36]!r}", f"want={want} got={got}")
    for text, want in [
        ("Vitality Re VII Ltd. (Series 2016-1)", {"2016-1", "RE VII"}),
        ("As ever the Vitality Re II notes are very remote risk", {"RE II"}),
        ("the Class II notes and the Series 2012-2 issuance", {"2012-2"}),
        ("sanders-re-iii-ltd-series-2022-2", {"2022-2", "RE III"}),   # the URL slug
    ]:
        check(_series_tokens(text) == want, f"UNIT series-tokens {text[:30]!r}", repr(_series_tokens(text)))
    f = _apply_patterns("attachment_probability", TIER2_PATTERNS["attachment_probability"],
                        "The overall initial attachment probability for the transaction is 3.87%, "
                        "the expected loss is 2.71%. For U.S. hurricane the attachment probability is 1.8%.")
    check(f["value"] == "3.87%", "UNIT AP object clause 'for the transaction is'", repr(f["value"]))
    for text, want in [
        ("it attached the notes and eroded their full principal, providing", True),
        ("Jamaica would benefit from a payout of the full $150 million", True),
        ("suggesting a total loss of the $150m of principal is anticipated", True),
    ]:
        check(bool(LC_ZERO_RE.search(text)) == want, f"UNIT lc-zero {text[:30]!r}")
    for text, want in [
        ("The Class B tranche would face a 100% loss of principal, so $95m.", True),
        ("suggesting a total loss of the $150m of principal is anticipated", True),
        ("it attached the notes and eroded their full principal, providing Toa Re", False),
    ]:
        check(bool(LC_SPECULATIVE_RE.search(text)) == want, f"UNIT lc-speculative {text[:30]!r}")
    b = _bindings_by_label("The target has been doubled, with each tranche now targeting $200 million "
                           "of coverage, for total reinsurance protection of $400 million.")
    check(b.get("*EACH*") == ["$200 million"], "UNIT bindings *EACH* unlabelled per-tranche amount", repr(b))
    for text, want in [
        ("Both tranches of notes priced at $100 million in size, while the Class A notes priced at 3.25%.", "$100 million"),
        ("Convex secured the upsized $300 million of protection, with the two $150 million tranches of notes issued.", "$150 million"),
        ("the deal offers $200 million across the two tranches of notes", None),
        ("comes out of the blocks at $300m in size, split into two tranches of notes, each of which", None),
    ]:
        got = _per_tranche_amount(text)
        check(got == want, f"UNIT per-tranche amount {text[:34]!r}", f"want={want!r} got={got!r}")
    for text, want in [
        ("with $70 million of reinsurance secured from the Class A per-occurrence notes, and $65 million from the Class B notes.",
         [(70.0, "size", "Class A"), (65.0, "size", "Class B")]),
        ("The Class A notes were priced to provide $100 million of cover, at a risk interest spread of 21.25%.",
         [(100.0, "size", "Class A")]),
        ("The Class A tranche of Series 2017-1 notes were launched to investors as a $125 million offering, "
         "but this tranche has now grown to $150 million we understand.",
         [(125.0, "size", "Class A"), (150.0, "size", "Class A")]),
    ]:
        got = [(m["value"] / 1e6, m["kind"], m["scope"]) for m in mentions_extract(text)]
        check(got == want, f"UNIT mention kind/scope {text[:34]!r}", f"want={want} got={got}")
    b = _bindings_by_label("Both the Class A and Class B tranche of notes are sized at EUR 25m each.")
    check("*EACH*" not in b and b.get("CLASS A") == ["EUR 25m"], "UNIT bindings labelled each stays labelled", repr(b))
    for text, want in [
        ("resulted in the riskier Class B tranche of notes being pulled and not being issued", True),
        ("the Class 10, riskiest layer of USAA's latest catastrophe bond was pulled from the issuance", True),
        ("the two aggregate tranches have now been dropped from this issuance", True),
        ("price guidance has dropped to 5.25% for the Class A notes", False),
    ]:
        check(bool(TRANCHE_WITHDRAWN_RE.search(text)) == want, f"UNIT tranche-withdrawn {text[:30]!r}")
    check("IS" in CLASS_STOPWORDS and "TO" in CLASS_STOPWORDS, "UNIT class stopwords cover 'class is'")
    b = _bindings_by_label("Both of these Class A tranches (four-year and five-year) are now set to secure "
                           "Everest Re $62.5 million of protection each and the price guidance has plummeted.")
    check(b.get("*EACH:CLASS A*") == ["$62.5 million"], "UNIT bindings parent-group each", repr(b))
    got = [(m["value"] / 1e6, m["kind"]) for m in mentions_extract(
        "which have a particularly high initial expected loss of 17.43%, were eventually confirmed as $37.5 million in size")]
    check(got == [(37.5, "size")], "UNIT 'expected loss of' is not a payout cue", repr(got))
    for text, want in [
        ("the Class B notes were pulled from the offering", True),
        ("Class 12 notes will not be issued at all", True),
        ("the target issuance size has increased to $330 million", False),
    ]:
        check(bool(TRANCHE_DROPPED_RE.search(text)) == want, f"UNIT tranche-dropped {text[:30]!r}")
    for v, want in [("77.25%", True), ("90.5%", True), ("22.75%", False), ("6,25%", False)]:
        check(_spread_is_price(v) == want, f"UNIT spread-is-price {v}", f"want={want}")
    f = _apply_patterns("spread_risk_margin", TIER2_PATTERNS["spread_risk_margin"],
                        "The Class 1 layer of notes has now priced at 77.25%, so a coupon "
                        "equivalent of 22.75% which is around the middle of guidance.")
    check(f["value"] == "22.75%", "UNIT spread: price dropped, equivalent read", repr(f["value"]))
    check(any(x.startswith("discount_price_not_spread") for x in f["flags"]),
          "UNIT spread: dropped price is flagged", repr(f["flags"]))
    for text, want in [
        ("have had their maturity extended again to December 6th 2018.", True),
        ("cat bond expires at the end of Dec 2009 so this deal seeks to replace it.", True),
        ("It will be a three year deal due to end in June 2013.", False),
        ("The risk period runs through March 31st, 2001.", False),
    ]:
        got = bool(MATURITY_EXCLUDE_RE.search(text))
        check(got == want, f"UNIT maturity-exclude {text[:36]!r}", f"want={want} got={got}")
    for raw, want in [("December 6th 2018", "December 2018"), ("January 8, 2014", "January 2014"),
                      ("March 31st, 2001", "March 2001"), ("May 2030", "May 2030")]:
        check(_strip_day(raw) == want, f"UNIT strip-day {raw}", repr(_strip_day(raw)))
    m = INITIAL_IDIOM_RE.search("This cat bond was initially marketed at \u20ac60m but closed at \u20ac75m")
    check(m is not None and m.group(1) == "\u20ac60m", "UNIT initial-idiom launch amount", repr(m and m.group(1)))
    check(_is_backward_reference("That deal afforded them $200m of cover", 2011, frozenset({"2011-1"})),
          "UNIT backward-reference 'That deal'")
    check(not _is_backward_reference("This deal affords them $200m of cover", 2011, frozenset({"2011-1"})),
          "UNIT backward-reference 'This deal' is ours")
    got = sentences("The deal comprises $50m Atlas VI Capital Ltd. Series 2011-1 Class A notes. The cover will run.")
    check(len(got) == 2 and "Class A" in got[0], "UNIT split keeps 'Ltd. Series' together", repr(got))
    got = sentences("issued by Bermuda based SPV Tramline Re Ltd. The notes will be sold.")
    check(len(got) == 2, "UNIT split still ends at 'Ltd. The'", repr(got))


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
    unit_component_scope()
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
        # Deal-level EL and AP are the FIRST capture of each, so on a
        # multi-tranche page they can come from different tranches
        # (Residential Re 2013-2: Class 1's EL=13.06 beside Class 4's
        # AP=2.26). The ordering is only a fact within one tranche; the
        # per-tranche guard below covers the rest.
        if el and ap and len(parse_tranches(rec)) <= 1:
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

        if slug in TRANCHE_COUNT:
            check(len(rws) == TRANCHE_COUNT[slug], f"EXPECT tranche count {slug}",
                  f"want={TRANCHE_COUNT[slug]} got={len(rws)} {[r.get('tranche_id') for r in rws]}")
        if slug in MATURITY:
            got = rec["maturity_date"]["value"]
            check(got == MATURITY[slug], f"EXPECT maturity {slug}",
                  f"want={MATURITY[slug]!r} got={got!r}")
        if slug in SIZE_LAUNCH_REJECT:
            got = next((h["value"] for h in (rec["size_history"]["value"] or [])
                        if h["state"] == "launch"), None)
            check(got != SIZE_LAUNCH_REJECT[slug], f"REJECT launch {slug}",
                  f"must not be {SIZE_LAUNCH_REJECT[slug]!r}, got {got!r}")
        for key, flag in FLAGS.get(slug, {}).items():
            check(flag in rec[key]["flags"], f"EXPECT flag {slug}:{key}",
                  f"want {flag!r} in {rec[key]['flags']}")

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
        if slug == "everglades-re-ii-ltd-series-2015-1":
            probe = [dict(r) for r in rws2]
            probe[0]["spread_risk_margin"] = "20%"
            probe_findings = validate(rec, probe, None)
            check(any(f["check"] == "spread_outside_guidance" for f in probe_findings),
                  "UNIT validator catches spread far outside guidance",
                  repr(probe_findings))

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
    EXPECTED_CHECKS = 1759
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
            # GUARD: a spread of 50%+ is a zero-coupon note's price of par.
            sp = _pct_to_float(r.get("spread_risk_margin"))
            if sp is not None:
                check(sp < 50, f"GUARD spread-not-price {slug}:{r['tranche_id']}",
                      f"spread={sp}")
            if el and ap:
                check(el <= ap, f"GUARD EL<=AP {slug}:{r['tranche_id']}",
                      f"EL={el} AP={ap}")

        # GUARD: a regulatory class is not a tranche. Seaside's page says
        # "Class 3 Bermuda-based insurer"; that phantom equalled the deal total
        # so the sum check was validating an invented structure.
        if slug == "seaside-re-series-2026-61":
            ids = [r["tranche_id"] for r in parse_tranches(rec)]
            check("Class 3" not in ids, "GUARD no-regulatory-class-tranche", str(ids))

        # GUARD: the Citrus lifecycle, as hand-labelled in the pilot. A
        # documented extension and a total loss had no fields at all until a
        # human labelled the page and asked where to put them.
        if slug == "citrus-re-ltd-series-2015-1":
            lc = {r["tranche_id"]: r for r in parse_tranches(rec)}
            check(lc["Class B"].get("maturity_extended") == "April 9th 2020",
                  "EXPECT citrus B extended", str(lc["Class B"].get("maturity_extended")))
            check(lc["Class C"].get("principal_loss_pct") == 100.0,
                  "EXPECT citrus C total loss", str(lc["Class C"].get("principal_loss_pct")))
            check(lc["Class C"].get("maturity_actual") == "March 20th 2019",
                  "EXPECT citrus C actual maturity", str(lc["Class C"].get("maturity_actual")))
            check(lc["Class A"].get("maturity_actual") == "April 12th 2018",
                  "EXPECT citrus A matured", str(lc["Class A"].get("maturity_actual")))

    passed = sum(1 for ok, *_ in results if ok)
    for ok, label, detail in results:
        if not ok:
            print(f"  FAIL  {label}  {detail}")
    print(f"\n{passed}/{len(results)} checks passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
