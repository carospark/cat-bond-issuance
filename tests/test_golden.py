"""Golden tests over the cached pages in raw/. No network: fetch() is cache-first.

Two kinds of assertion:
  EXPECT   a verified value, read off the source by hand.
  GUARD    an invariant that must hold on every page, forever. Guards are the
           point: every bug so far was a regex that fixed one page and quietly
           broke another.

Run:  ./.venv/bin/python tests/test_golden.py

Two tiers:
  UNIT     pure predicates, regexes and parsers on synthetic text. Run anywhere.
  GOLDEN   anything that parses a cached page in raw/ (or needs data/queue.csv,
           itself derived from raw/). Skipped, with a printed count, when raw/
           is not present; run in full, unchanged, when it is.

The suite is offline by construction: ARTEMIS_OFFLINE is forced on and
requests.get is replaced with a function that raises, so a cache miss can never
reach the network.
"""

import os
import re
import sys
from pathlib import Path

# Must precede any import that might fetch. fetch() reads this at call time.
os.environ["ARTEMIS_OFFLINE"] = "1"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import requests                  # noqa: E402


def _no_network(*args, **kwargs):
    raise RuntimeError("network access attempted during tests")


requests.get = requests.post = requests.request = _no_network
requests.Session.request = _no_network

from fetch import fetch, _cache_path  # noqa: E402
from validate import validate  # noqa: E402
from sibling_registry import SiblingRegistry  # noqa: E402
from fetch import DEAL_DIRECTORY_URL as BASE  # noqa: E402
from parse_deal import (_is_backward_reference, sentences,  # noqa: E402
                        _pct_to_float, _series_tokens, CUMULATIVE_RE,
                        _cites_only_foreign_series, _deal_cancelled,
                        SPECULATIVE_SIZE_RE, TRANCHE_OF_RE)
from mentions import canon_label, classify  # noqa: E402
from net_supply import usd_millions, convert_size, issue_month, load_fx  # noqa: E402
import roll_forward as rf  # noqa: E402
from parse_deal import (parse_deal, parse_tranches, check_tranche_sum,  # noqa: E402
                        MONTHS, TIER1_KEYS, MONEY_RE, NEGATED_RESIZE_RE,
                        CANCELLED_RE, TIER2_PATTERNS, TRANCHE_SIZE_RES,
                        _governed_by_loss_level, _bindings_by_label,
                        _launch_final, _apply_patterns, _currency,
                        _segment_prose_dated, _tranche_windows,
                        _separate_series_totals)
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
    "merna-re-ii-ltd-series-2022-2",    # $500m belongs to two separately indexed series
    "merna-re-ii-ltd-series-2022-3",    # same duplicated dual-series placement page
    "merna-re-ii-ltd-series-2025-1",    # $1.55bn belongs to four separate series
    "merna-re-ii-ltd-series-2025-2",    # own $300m launch survives programme-total veto
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
    # Settled-spread recall round (2026-11-18): the band-of-guidance form,
    # verb+at/of, the offered coupon, zero-coupon equivalents stated number
    # first, the per-class "; coupon X%" list, four-letter class labels, and
    # the expectation sentence that must stay None.
    "tailwind-re-ltd-series-2022-1",         # "fixed at the low-end of guidance, at 6.75%" x4 classes
    "black-kite-re-limited-series-2022-1",   # "priced to pay investors a 6.9% coupon"
    "phoenician-re-ltd-series-2020-2",       # "priced its $95 million of notes at 2.9%"; sibling's 3% excluded
    "bonanza-re-ltd-series-2020-2",          # "settled at 88% of par, so a roughly 12% coupon equivalent"
    "ursa-re-ii-ltd-series-2022-2",          # "the initial risk interest spread to be paid to investors is 7%"
    "hexagon-ii-reinsurance-dac-series-2019-1",  # "a 5.9% attachment probability"; "settle at the lowest-end"
    "metrocat-re-ltd-series-2020-1",         # "attachment probability and expected loss of 0.888%"
    "ibrd-car-130-jamaica",                  # "pricing at the 4.4% risk margin"
    "gateway-re-ltd-series-2026-1",          # Class AAAA is a label; its 3.5% is not Class A's
    "residential-reinsurance-2019-limited-series-2019-1",  # "looks set to settle at 8.25%" is not settled
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
    # Recall round 2026-11-18: the number before the cue, and one number
    # stated for both fields.
    "hexagon-ii-reinsurance-dac-series-2019-1": {
        "attachment_probability": "5.9%", "expected_loss": "3.65%",
        "spread_risk_margin": "5.15%",   # "pricing settle at the lowest-end of guidance, at 5.15%"
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
    "merna-re-ii-ltd-series-2022-2": {"size_history": "separate_series_total_excluded=3_sentence(s)"},
    "merna-re-ii-ltd-series-2022-3": {"size_history": "separate_series_total_excluded=3_sentence(s)"},
    "merna-re-ii-ltd-series-2025-1": {"size_history": "separate_series_total_excluded=2_sentence(s)"},
    "merna-re-ii-ltd-series-2025-2": {"size_history": "separate_series_total_excluded=2_sentence(s)"},
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
    # Gateway 2025-1 Class A: was pinned None while no anchor read "their
    # pricing was finalised at 10.5%"; the point of the pin was that Class
    # AA's 93.75% price never reaches it. Class C-1's 9.5% is Class C 2's
    # (a label with a space inside, not yet a window) and stays unpinned.
    "gateway-re-ltd-series-2025-1": {"Class A": {"spread_risk_margin": "10.5%"}},
    # Settled-spread recall round (2026-11-18).
    "tailwind-re-ltd-series-2022-1": {
        "Class A": {"spread_risk_margin": "6.75%"}, "Class B": {"spread_risk_margin": "8.75%"},
        "Class C": {"spread_risk_margin": "11.75%"}, "Class D": {"spread_risk_margin": "14.75%"},
    },
    "black-kite-re-limited-series-2022-1": {"Class A": {"spread_risk_margin": "6.9%"}},
    "phoenician-re-ltd-series-2020-2": {"Class A": {"spread_risk_margin": "2.9%"}},
    "bonanza-re-ltd-series-2020-2": {
        "Class A": {"spread_risk_margin": "4.75%"},   # "settled at the initial mid-point of 4.75%"
        "Class B": {"spread_risk_margin": "12%"},     # "88% of par, so a roughly 12% coupon equivalent"
        "Class C": {"spread_risk_margin": None},
    },
    "ursa-re-ii-ltd-series-2022-2": {
        "Class AA": {"spread_risk_margin": "7%", "attachment_probability": "1.13%"},
        "Class B": {"spread_risk_margin": "10.25%", "attachment_probability": "2.43%"},
    },
    "metrocat-re-ltd-series-2020-1": {"Class A": {"attachment_probability": "0.888%",
                                                  "expected_loss": "0.888%"}},
    "ibrd-car-130-jamaica": {"Class A": {"spread_risk_margin": "4.4%"}},
    "gateway-re-ltd-series-2026-1": {
        "Class AAAA": {"spread_risk_margin": "3.5%", "expected_loss": "0.57%"},
        "Class A": {"spread_risk_margin": "10%", "expected_loss": "3.98%"},
    },
    # "we're told pricing looks set to settle at 8.25%" is an expectation;
    # Class 13's "coupon of 3.25%" is a 2018 deal's (foreign reference).
    "residential-reinsurance-2019-limited-series-2019-1": {
        "Class 12": {"spread_risk_margin": None}, "Class 13": {"spread_risk_margin": None},
    },
    # The per-class list "Class 11 - $35 million; coupon 12.5%."
    "residential-reinsurance-2022-limited-series-2022-1": {
        "Class 10": {"tranche_size_final": None},   # withdrawn: no size
        "Class 11": {"spread_risk_margin": "12.5%"}, "Class 12": {"spread_risk_margin": "7.5%"},
        "Class 13": {"spread_risk_margin": "5.25%"}, "Class 14": {"spread_risk_margin": "4%"},
    },
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
    "merna-re-ii-ltd-series-2022-2": [("update_1", "$200 million")],
    "merna-re-ii-ltd-series-2022-3": [("update_1", "$300 million")],
    "merna-re-ii-ltd-series-2025-1": [("launch", "$200 million")],
    "merna-re-ii-ltd-series-2025-2": [("launch", "$300 million")],
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
    # Issue-month FX. The table is tracked (src/fx_monthly_usd.csv); these pin
    # the source series (ECB monthly average, BoE XUMAUSS), the cross-rate
    # direction (USD per unit, so CAD and NZD are below 1), and that a month
    # without a rate yields an honest None with the local amount kept.
    fx = load_fx()
    for ccy, month, want in [("EUR", "2005-11", 1.178573), ("GBP", "2025-03", 1.2911),
                             ("CAD", "2025-01", 0.694709), ("NZD", "2023-05", 0.621662)]:
        got = fx.get((ccy, month))
        check(got is not None and abs(got - want) < 1e-6,
              f"UNIT fx table {ccy} {month}", f"want={want} got={got}")
    check(("EUR", "1998-12") not in fx and ("GBP", "1998-12") in fx,
          "UNIT fx table coverage: ECB from 1999-01, BoE from 1996-01")
    for text, want in [("Nov 2005", "2005-11"), ("November 2005", "2005-11"),
                       ("12 June 2024", "2024-06"), ("2005-11-03", "2005-11"),
                       ("", None), ("Unknown", None)]:
        got = issue_month(text)
        check(got == want, f"UNIT issue_month {text!r}", f"want={want} got={got}")
    for size, date, want in [
        ("EUR200m", "Nov 2005", ("usd_converted", 235.7146, 200.0, "EUR", 1.178573)),
        ("\u00a3100m", "Mar 2025", ("usd_converted", 129.11, 100.0, "GBP", 1.2911)),
        ("C$150m", "Jan 2025", ("usd_converted", 104.20635, 150.0, "CAD", 0.694709)),
        ("NZ$225m", "May 2023", ("usd_converted", 139.87395, 225.0, "NZD", 0.621662)),
        ("\u20ac190m ($262m)", "Apr 2014", ("usd_equiv", 262.0, 190.0, "EUR", None)),
        ("$1.5 billion", "Jun 2020", ("usd", 1500.0, None, "USD", None)),
        ("$473.18", "Feb 2019", ("unit_missing", None, None, None, None)),
        ("Not issued", "Jan 2020", ("excluded", None, None, None, None)),
        ("EUR 50m", "Jan 1998", ("fx_rate_missing", None, 50.0, "EUR", None)),
        ("\u20ac100m", "", ("fx_rate_missing", None, 100.0, "EUR", None)),
    ]:
        c = convert_size(size, date)
        got = (c["basis"], None if c["usd_m"] is None else round(c["usd_m"], 5),
               c["local_m"], c["currency"], c["fx_usd_per_unit"])
        check(got == want, f"UNIT convert_size {size!r} {date!r}", f"want={want} got={got}")
    unit_roll_forward()
    unit_trace_maturities()
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
    # The cue is a deal fact only when the sentence is about this deal as a
    # whole: the five false positives of 2026-10-25 and the two true ones.
    for text, iy, name, want in [
        ("Update 2: In an interesting turn of events, and slightly unsual for a cat bond issuance, "
         "this deal has now shrunk slightly and one tranche of notes has been pulled completely.",
         2013, "Atlas IX Capital Limited (Series 2013-1)", False),
        ("Update 1: One of the four tranches of notes has been withdrawn from the issuance and the "
         "other three now have preliminary sizes which in total add up to $180m.",
         2013, "Tradewynd Re Ltd. (Series 2013-2)", False),
        ("The Series 2024-2 notes that were initially offered have been withdrawn and won\u2019t now be issued.",
         2024, "Everglades Re II Ltd. (Series 2024-1)", False),
        ("However, that issuance was cancelled, due to conditions in the ILS market and broader capital "
         "markets, as well as the effect this had on investor appetite and UnipolSai\u2019s 2022 cat bond was "
         "one of those that suffered, so the company elected to halt that issue.",
         2024, "Azzurro Re II DAC (Series 2024-1)", False),
        ("This Titania Re 2024-1 issuance sees the company looking to issue a deal that was not completed "
         "earlier this year, when in May 2024 Ariel Re stepped back from completing the issuance.",
         2024, "Titania Re Ltd. (Series 2024-1)", False),
        ("Update: We learned from sources that this Gateway Re 2024-3 catastrophe bond issuance has been "
         "cancelled, as the sponsors made a commercial decision not to proceed with placing the transaction.",
         2024, "Gateway Re Ltd. (Series 2024-3)", True),
        ("The Queen Street X Re Ltd. cat bond issuance was not completed.", 2015, "Queen Street X Re Ltd.", True),
        ("Both tranches of notes were withdrawn and the deal did not proceed.", 2020, "Z Re Ltd. (Series 2020-1)", True),
        ("The Class B notes were pulled and the deal has been upsized.", 2020, "Z Re Ltd. (Series 2020-1)", False),
    ]:
        own = _series_tokens(name)
        got = _deal_cancelled(text, iy, own)
        check(got == want, f"UNIT deal-cancelled {text[:44]!r}", f"want={want} got={got}")
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
                        _spread_is_price, TIER2_PATTERNS, MATURITY_EXCLUDE_RE, _strip_day, _term_to_years,
                        _series_tokens, LC_ZERO_RE, LC_SPECULATIVE_RE, _bindings_by_label,
                        TRANCHE_DROPPED_RE, _per_tranche_amount, TRANCHE_WITHDRAWN_RE, CLASS_STOPWORDS)
from mentions import extract as mentions_extract  # noqa: E402


def unit_roll_forward():
    """The deal-level principal ledger on synthetic deals: every convention
    the module documents is pinned here, and each was mutation-tested."""
    import pandas as pd

    def deals(rows):
        cols = ["deal_slug", "index_issuer_name", "size", "date_of_issue", "maturity_date",
                "maturity_date_derived", "maturity_scheduled", "deal_is_private", "deal_status"]
        return pd.DataFrame([dict(zip(cols, r)) for r in rows], columns=cols, dtype=str).fillna("")

    def losses(rows):
        cols = ["cat_bond", "deal_slug", "orig_size", "loss_amount", "date_of_loss",
                "loss_status", "loss_amount_derived", "is_settled"]
        return pd.DataFrame([dict(zip(cols, r)) for r in rows], columns=cols, dtype=str).fillna("")

    def stock(book, year, as_of="2026-08"):
        f = rf.monthly_flows(book)
        y = rf.outstanding_by_year(f, as_of).set_index("year")
        return round(float(y.outstanding.get(year, 0.0)), 3)

    # 1. Dates and names.
    for text, want in [("Sep 2022", ("2022-09", False)), ("2017 / 18", ("2017-12", True)),
                       ("2020/21", ("2020-12", True)), ("2024 / 2025 risk period", ("2024-12", True)),
                       ("TBC", (None, None))]:
        got = rf.loss_month(text)
        check(got == want, f"UNIT loss_month {text!r}", f"want={want} got={got}")
    for a, b in [("Caelus Re V Ltd. (Series 2018-1) Class B", "Caelus Re V Ltd. (Series 2018-1)"),
                 ("Residential Reinsurance 2017 Limited (Series 2017-1) Class 11", "Residential Reinsurance 2017 Limited (Series 2017-1)"),
                 ("Seaside Re 2018-2", "Seaside Re (Series 2018-2)"),
                 ("Vega Capital Ltd. (Series 2010-1) Class D", "Vega Capital Ltd. (Series 2010-I)"),
                 ("Kelvin Ltd. (First event notes)", "Kelvin Ltd.")]:
        check(rf._norm_name(a) == rf._norm_name(b), f"UNIT loss name links {a[:34]!r}",
              f"{rf._norm_name(a)!r} vs {rf._norm_name(b)!r}")
    check(rf._norm_name("Caelus Re V Ltd. (Series 2018-1)") != rf._norm_name("Caelus Re V Ltd. (Series 2017-1)"),
          "UNIT loss name keeps series apart")

    # 2. A plain deal: outstanding from issue to its stated maturity, then gone.
    d = deals([("a", "A Re Ltd.", "$100m", "Jun 2020", "June 2023", "", "June 2023", "", "issued")])
    b = rf.deal_book(d, losses([]))
    check(b.maturity_source.iat[0] == "stated" and b['flags'].iat[0] == "", "UNIT roll-forward stated maturity, no flags", repr(b['flags'].iat[0]))
    check((stock(b, 2020), stock(b, 2022), stock(b, 2023)) == (100.0, 100.0, 0.0),
          "UNIT roll-forward plain deal in then out", str((stock(b, 2020), stock(b, 2022), stock(b, 2023))))

    # 3. Written down $40m in 2021: leaves at the loss date, and only $60m matures
    #    (no double subtraction), so the stock never goes negative.
    L = losses([("A Re Ltd. (Series 1) Class A", "a", "$100m", "$40m", "2021", "stated_amount", "40000000.0", "True")])
    b = rf.deal_book(d, L)
    check((b.written_down_m.iat[0], round(b.remainder_m.iat[0], 6)) == (40.0, 60.0),
          "UNIT roll-forward write-down nets the maturing amount", str((b.written_down_m.iat[0], b.remainder_m.iat[0])))
    check((stock(b, 2021), stock(b, 2022), stock(b, 2023)) == (60.0, 60.0, 0.0),
          "UNIT roll-forward write-down then maturity sums to zero", str((stock(b, 2021), stock(b, 2022), stock(b, 2023))))
    check("loss_month_imputed" in b['flags'].iat[0], "UNIT roll-forward year-only loss date is flagged", b['flags'].iat[0])

    # 4. The loss settled after the scheduled maturity: the remainder leaves at
    #    settlement, not before (an implicit extension).
    L = losses([("A Re Ltd.", "a", "$100m", "$40m", "Mar 2024", "stated_amount", "40000000.0", "True")])
    b = rf.deal_book(d, L)
    check(b.repay_month.iat[0] == "2024-03" and "repay_after_maturity_loss_settlement" in b['flags'].iat[0],
          "UNIT roll-forward remainder waits for a later settlement", f"{b.repay_month.iat[0]} {b['flags'].iat[0]}")
    check((stock(b, 2023), stock(b, 2024)) == (100.0, 0.0), "UNIT roll-forward late settlement keeps stock through 2023",
          str((stock(b, 2023), stock(b, 2024))))

    # 5. A stated extension carries the extended portion to its date.
    L = losses([("A Re Ltd. Class A", "a", "$100m", "$70m returned to investors. Maturity extended to June 2025 for remaining $30m.",
                 "Sep 2022", "extended", "", "False")])
    b = rf.deal_book(d, L)
    check((b.extended_m.iat[0], b.extension_month.iat[0], round(b.remainder_m.iat[0], 6)) == (30.0, "2025-06", 70.0),
          "UNIT roll-forward stated extension amount and month", str((b.extended_m.iat[0], b.extension_month.iat[0], b.remainder_m.iat[0])))
    check((stock(b, 2023), stock(b, 2024), stock(b, 2025)) == (30.0, 30.0, 0.0),
          "UNIT roll-forward extended portion outstanding until its date", str((stock(b, 2023), stock(b, 2024), stock(b, 2025))))

    # 6. An unresolved loss with no date is carried, but no further than the cap.
    L = losses([("A Re Ltd. Class A", "a", "$100m", "TBC. Mark to market implied 50% loss.", "Sep 2022", "marked_to_market", "", "False")])
    b = rf.deal_book(d, L, as_of="2030-08")
    check(b.extension_month.iat[0] == "2026-06" and "extension_open_capped_36m" in b['flags'].iat[0],
          "UNIT roll-forward open extension capped at 36 months", f"{b.extension_month.iat[0]} {b['flags'].iat[0]}")
    check((stock(b, 2025, "2030-08"), stock(b, 2026, "2030-08")) == (100.0, 0.0),
          "UNIT roll-forward capped carry leaves at the cap", str((stock(b, 2025, "2030-08"), stock(b, 2026, "2030-08"))))
    b = rf.deal_book(d, L, as_of="2024-08")
    check(b.extension_month.iat[0] == "2024-09" and "extension_open_carried_to_as_of" in b['flags'].iat[0],
          "UNIT roll-forward open extension still outstanding at as-of", f"{b.extension_month.iat[0]} {b['flags'].iat[0]}")

    # 7. Principal "returned to investors" is the remainder repaid, not a
    #    recovery (2026-11-17): the loss amount already nets it. Only a stated
    #    reversal of a write-down is added back.
    L = losses([("A Re Ltd.", "a", "$100m", "$40m paid out; $15m returned to investors after subrogation.",
                 "Jun 2021", "partial_loss", "40000000.0", "True")])
    b = rf.deal_book(d, L)
    check((b.written_down_m.iat[0], b.recovered_m.iat[0], round(b.remainder_m.iat[0], 6)) == (40.0, 0.0, 60.0)
          and "principal_returned_to_investors" in b['flags'].iat[0],
          "UNIT roll-forward returned principal is not added back", str((b.written_down_m.iat[0], b.recovered_m.iat[0], b.remainder_m.iat[0], b['flags'].iat[0])))
    check(stock(b, 2022) == 60.0 and stock(b, 2023) == 0.0, "UNIT roll-forward returned principal in the stock", str((stock(b, 2022), stock(b, 2023))))
    L = losses([("A Re Ltd.", "a", "$100m", "Principal reduced by $40m; the write-down was reversed and $15m returned to investors.",
                 "Jun 2021", "partial_loss", "40000000.0", "True")])
    b = rf.deal_book(d, L)
    check((b.written_down_m.iat[0], b.recovered_m.iat[0], round(b.remainder_m.iat[0], 6)) == (40.0, 15.0, 75.0)
          and "recovery_to_investors" in b['flags'].iat[0],
          "UNIT roll-forward a stated reversal is added back", str((b.written_down_m.iat[0], b.recovered_m.iat[0], b.remainder_m.iat[0])))
    check(stock(b, 2022) == 75.0 and stock(b, 2023) == 0.0, "UNIT roll-forward reversal in the stock", str((stock(b, 2022), stock(b, 2023))))

    # 8. No maturity on the page: imputed term by class, flagged; a "cancelled"
    #    status does not remove the deal but is flagged.
    d2 = deals([("p", "P Re Ltd.", "$100m", "Jun 2020", "", "", "", "", "cancelled"),
                ("q", "Q Notes", "$10m", "Jun 2020", "", "", "", "True", "issued")])
    b = rf.deal_book(d2, losses([]))
    check(list(b.maturity_source) == ["imputed_public_36m", "imputed_private_12m"]
          and list(b.maturity_month) == ["2023-06", "2021-06"],
          "UNIT roll-forward imputed terms by class", f"{list(b.maturity_source)} {list(b.maturity_month)}")
    check("term_imputed" in b['flags'].iat[0] and "deal_status_cancelled_ignored" in b['flags'].iat[0],
          "UNIT roll-forward imputation and status flags", b['flags'].iat[0])
    d3 = deals([("p", "P Re Ltd.", "$100m", "Jun 2020", "", "", "", "", "cancelled"),
                ("m", "Bellemeade Re Ltd.", "$100m", "Jun 2020", "", "", "", "", "issued"),
                ("n", "N Re Ltd.", "Not issued", "Jun 2020", "", "", "", "", "not_issued")])
    sel = rf.select_book(rf.deal_book(d3, losses([])), exclude_mortgage=True)
    check(list(sel.slug) == ["p"], "UNIT roll-forward book keeps a 'cancelled' deal, drops mortgage and sizeless",
          str(list(sel.slug)))
    b = rf.deal_book(d2, losses([]), term_months={"public": {2020: 48}, "private": 12})
    check(b.maturity_month.iat[0] == "2024-06" and b.maturity_source.iat[0] == "imputed_public_vintage",
          "UNIT roll-forward vintage imputation map", f"{b.maturity_month.iat[0]} {b.maturity_source.iat[0]}")
    cov = rf.coverage(b)
    check(abs(cov.share_pct.sum() - 100) < 1e-9 and set(cov.maturity_source) == {"imputed_public_vintage", "imputed_private_12m"},
          "UNIT roll-forward coverage shares sum to 100", cov.to_string())

    # 9. Legacy decomposition: no_netting - netted equals the written-down amount
    #    once the deal has matured.
    L = losses([("A Re Ltd.", "a", "$100m", "$40m", "2021", "stated_amount", "40000000.0", "True")])
    b = rf.deal_book(d, L)
    v = rf.legacy_variants(b, rf.monthly_flows(b))
    check(round(v.loc[2023, "netted"] - v.loc[2023, "no_netting"], 6) == 40.0 and round(v.loc[2023, "no_netting"], 6) == -40.0,
          "UNIT roll-forward legacy double subtraction equals the write-down", v.loc[2023].to_dict().__repr__())


def unit_trace_maturities():
    """TRACE maturities from the bridge as a maturity tier: the deal-level
    rule, the precedence against the page, and the legacy fallback."""
    import tempfile
    import pandas as pd

    bridge = pd.DataFrame([
        ("https://x/a/", "A1", "2027-12-06"), ("https://x/a/", "A2", "2027-12-06"), ("https://x/a/", "A3", "2024-12-06"),
        ("https://x/b/", "B1", "2026-01-08"), ("https://x/b/", "B2", "2027-01-08"),
        ("https://x/c/", "C1", ""),
        ("https://x/d/", "D1", "2023-07-07"),
        ("https://x/s2/", "S2", "2025-06-07"), ("https://x/s3/", "S3", "2023-06-07"),
        ("https://x/s4/", "S4", "2023-07-07"), ("https://x/s6/", "S6", "2020-06-07"),
        ("https://x/s8/", "S8", "2025-08-08"),
    ], columns=["deal_url", "cusip_id", "trace_maturity_date"])
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as fh:
        bridge.to_csv(fh.name, index=False)
        path = fh.name
    tr = rf.load_trace_maturities(path).set_index("deal_url")
    a = tr.loc["https://x/a/"]
    check(a.trace_maturity_month == "2027-12" and a.trace_cusips == 3 and a.trace_distinct_months == 2 and a.trace_span_months == 36,
          "UNIT trace maturity: month shared by most CUSIPs, span kept", a.to_dict().__repr__())
    check(tr.loc["https://x/b/"].trace_maturity_month == "2027-01", "UNIT trace maturity: tie goes to the latest month",
          tr.loc["https://x/b/"].trace_maturity_month)
    check("https://x/c/" not in tr.index and tr.loc["https://x/d/"].trace_cusips == 1,
          "UNIT trace maturity: blank dates dropped, single CUSIP kept", str(list(tr.index)))
    check(rf.resolve_trace_path(None) is None and rf.resolve_trace_path("off") is None
          and rf.resolve_trace_path(path) == Path(path), "UNIT trace path resolution")
    try:
        rf.resolve_trace_path("/nonexistent/bridge.csv")
        check(False, "UNIT trace path missing raises")
    except FileNotFoundError:
        check(True, "UNIT trace path missing raises")

    cols = ["deal_slug", "deal_url", "index_issuer_name", "size", "date_of_issue", "maturity_date",
            "maturity_date__flags", "maturity_date_derived", "maturity_scheduled", "deal_is_private", "deal_status"]
    rows = [
        ("s1", "https://x/d/", "S1 Re", "$100m", "Jun 2020", "June 2023", "", "", "Jun 2023", "", "issued"),
        ("s2", "https://x/s2/", "S2 Re", "$100m", "Jun 2020", "June 2023", "", "", "Jun 2023", "", "issued"),
        ("s3", "https://x/s3/", "S3 Re", "$100m", "Jun 2020", "June 2023", "maturity_from_class_agreement=['C']", "", "Jun 2023", "", "issued"),
        ("s4", "https://x/s4/", "S4 Re", "$100m", "Jun 2020", "", "", "June 2023", "Jun 2023", "", "issued"),
        ("s5", "https://x/a/", "S5 Re", "$100m", "Jun 2020", "", "", "", "", "", "issued"),
        ("s6", "https://x/s6/", "S6 Re", "$100m", "Jun 2020", "", "", "", "", "", "issued"),
        ("s7", "https://x/none/", "S7 Re", "$100m", "Jun 2020", "", "", "", "", "", "issued"),
        ("s8", "https://x/s8/", "S8 Re", "$100m", "Jun 2024", "July 2028", "", "", "Jul 2028", "", "issued"),
    ]
    d = pd.DataFrame([dict(zip(cols, r)) for r in rows], columns=cols, dtype=str).fillna("")
    L = pd.DataFrame(columns=["cat_bond", "deal_slug", "orig_size", "loss_amount", "date_of_loss",
                              "loss_status", "loss_amount_derived", "is_settled"], dtype=str)
    trace = rf.load_trace_maturities(path)
    b = rf.deal_book(d, L, trace=trace).set_index("slug")
    check(b.loc["s1"].maturity_source == "stated" and b.loc["s1"].maturity_month == "2023-06"
          and "trace_corroborates_stated=+1m" in b.loc["s1"]["flags"],
          "UNIT trace tier: stated within tolerance kept, corroboration flagged", b.loc["s1"]["flags"])
    check(b.loc["s2"].maturity_source == "trace" and b.loc["s2"].maturity_month == "2025-06"
          and "trace_maturity_overrides_stated=+24m" in b.loc["s2"]["flags"],
          "UNIT trace tier: stated beyond tolerance replaced by TRACE", b.loc["s2"]["flags"])
    check(b.loc["s8"].maturity_source == "stated" and b.loc["s8"].maturity_month == "2028-07"
          and "page_later_than_trace=+35m" in b.loc["s8"]["flags"] and "overrides" not in b.loc["s8"]["flags"],
          "UNIT trace tier: a page date later than TRACE stands (bridge may hold short classes only)", b.loc["s8"]["flags"])
    check(b.loc["s3"].maturity_source == "trace" and "trace_maturity_overrides_stated=+0m_class_vote" in b.loc["s3"]["flags"],
          "UNIT trace tier: a per-class vote yields to TRACE", b.loc["s3"]["flags"])
    check(b.loc["s4"].maturity_source == "trace" and b.loc["s4"].maturity_month == "2023-07"
          and "trace_maturity_replaces_derived=+1m" in b.loc["s4"]["flags"],
          "UNIT trace tier: term-derived replaced by TRACE", b.loc["s4"]["flags"])
    check(b.loc["s5"].maturity_source == "trace" and b.loc["s5"].maturity_month == "2027-12"
          and "trace_maturity_replaces_imputed" in b.loc["s5"]["flags"] and "term_imputed" not in b.loc["s5"]["flags"],
          "UNIT trace tier: no page maturity takes TRACE, nothing imputed", b.loc["s5"]["flags"])
    check("trace_maturity_tranches_disagree=36m" in b.loc["s5"]["flags"],
          "UNIT trace tier: CUSIPs on different months flagged with the span", b.loc["s5"]["flags"])
    check(b.loc["s6"].maturity_source == "imputed_public_36m" and "trace_maturity_rejected_not_after_issue" in b.loc["s6"]["flags"],
          "UNIT trace tier: TRACE maturity at or before issue rejected, term imputed", b.loc["s6"]["flags"])
    check(b.loc["s7"].maturity_source == "imputed_public_36m" and b.loc["s7"].trace_maturity_month is None,
          "UNIT trace tier: unbridged deal imputed as before", b.loc["s7"]["flags"])
    check((b.loc["s4"].page_maturity_month, b.loc["s4"].page_maturity_source) == ("2023-06", "derived_from_term")
          and b.loc["s5"].page_maturity_source is None and b.loc["s2"].trace_vs_page_months == 24,
          "UNIT trace tier: page maturity and difference kept beside the choice",
          str((b.loc["s4"].page_maturity_month, b.loc["s4"].page_maturity_source, b.loc["s2"].trace_vs_page_months)))
    nb = rf.deal_book(d.drop(columns=["deal_url"]), L, trace=trace).set_index("slug")
    check(nb.loc["s5"].maturity_source == "imputed_public_36m" and nb.loc["s1"].maturity_source == "stated",
          "UNIT trace tier: without deal_url the bridge is ignored", str(list(nb.maturity_source)))
    bb = b.reset_index()
    v = rf.legacy_variants(bb, rf.monthly_flows(bb))
    book5 = bb[bb.slug == "s5"]
    v5 = rf.legacy_variants(book5, rf.monthly_flows(book5))
    check(round(v5.loc[2023, "legacy_3y"], 6) == 0.0 and round(v5.loc[2023, "netted"], 6) == 100.0
          and round(v5.loc[2022, "legacy_3y"], 6) == 100.0,
          "UNIT trace tier: legacy_3y still imputes 36 months where the page had nothing", v5.to_string())
    book2 = bb[bb.slug == "s2"]
    v2 = rf.legacy_variants(book2, rf.monthly_flows(book2))
    check(round(v2.loc[2024, "legacy_3y"], 6) == 0.0 and round(v2.loc[2024, "netted"], 6) == 100.0,
          "UNIT trace tier: legacy_3y keeps the page's stated month where TRACE replaced it", v2.to_string())
    cov = rf.coverage(bb)
    check(abs(cov.share_pct.sum() - 100) < 1e-9 and "trace" in set(cov.maturity_source)
          and float(cov.set_index("maturity_source").loc["trace"].n_deals) == 4
          and float(cov.set_index("maturity_source").loc["stated"].n_deals) == 2,
          "UNIT trace tier: coverage counts the TRACE tier", cov.to_string())
    tc = rf.trace_check(bb)
    got = tc.groupby("outcome").n_deals.sum().to_dict()
    check(got == {"stated_kept": 1, "stated_kept_page_later": 1, "trace_overrides_stated": 1,
                  "trace_overrides_stated_class_vote": 1, "trace_replaces_derived": 1,
                  "trace_replaces_imputed": 1, "trace_rejected": 1},
          "UNIT trace tier: check table outcomes", str(got))
    os.unlink(path)


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
    merna = ("Two series were issued at the same time, this $200 million Merna Re II "
             "Series 2022-2, while a $300 million Merna Re II Series 2022-3 issuance "
             "came to market at the same time.")
    check(_separate_series_totals(merna, {"2022-2", "RE II"}) == {500_000_000.0},
          "UNIT separate-series total is derived", repr(_separate_series_totals(merna, {"2022-2", "RE II"})))
    check(_separate_series_totals(merna, {"2022-2", "2022-3", "RE II"}) == set(),
          "UNIT multi-series entry keeps its aggregate", repr(_separate_series_totals(
              merna, {"2022-2", "2022-3", "RE II"})))
    for v, want in [("77.25%", True), ("90.5%", True), ("22.75%", False), ("6,25%", False)]:
        check(_spread_is_price(v) == want, f"UNIT spread-is-price {v}", f"want={want}")
    f = _apply_patterns("spread_risk_margin", TIER2_PATTERNS["spread_risk_margin"],
                        "The Class 1 layer of notes has now priced at 77.25%, so a coupon "
                        "equivalent of 22.75% which is around the middle of guidance.")
    check(f["value"] == "22.75%", "UNIT spread: price dropped, equivalent read", repr(f["value"]))
    check(any(x.startswith("discount_price_not_spread") for x in f["flags"]),
          "UNIT spread: dropped price is flagged", repr(f["flags"]))
    for text, want in [
        ("cat bond expires at the end of Dec 2009 so this deal seeks to replace it.", True),
        ("It will be a three year deal due to end in June 2013.", False),
        ("The risk period runs through March 31st, 2001.", False),
        # The extension veto moved out of this regex and became positional
        # (2026-11-17): see unit_maturity_recall_round3.
        ("have had their maturity extended again to December 6th 2018.", False),
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


def unit_maturity_class_scoped():
    """Per-class maturities (backlog 3): agree -> deal-level, disagree -> None.

    Synthetic sentences only. The class-scoped veto drops every sentence that
    names a Class, which is right when classes differ (one class of three
    running to a different date) and wrong when every class carries the SAME
    date ("Notes due <date>" per class). The rule: adopt the date when at
    least two distinct classes state maturities and all resolve to one
    Month YYYY. One class alone proves nothing about the others.
    """
    def mat(text, issue_year=None):
        f = _apply_patterns("maturity_date", TIER2_PATTERNS["maturity_date"],
                            text, issue_year)
        return f["value"], f["flags"]

    agree = ("Class A notes due March 15, 2028. Class B notes due March 15, 2028. "
             "Class C notes due March 15, 2028.")
    v, fl = mat(agree)
    check(v == "March 2028", "UNIT class-maturity all classes agree", repr((v, fl)))
    check(any(str(x).startswith("maturity_from_class_agreement") for x in fl),
          "UNIT class-maturity agreement is flagged", repr(fl))

    # Different days, same Month YYYY: still agreement (day is stripped).
    v, _ = mat("Class A notes due March 3, 2028. Class B notes due March 20, 2028.")
    check(v == "March 2028", "UNIT class-maturity agree across different days", repr(v))

    # Other maturity phrasings go through the same rule (class of problem).
    v, _ = mat("The Class A notes mature in June 2027. The Class B notes mature in "
               "June 2027.")
    check(v == "June 2027", "UNIT class-maturity agree, 'mature in' phrasing", repr(v))

    # Lowercase labels, as some pages write them.
    v, _ = mat("class A notes due May 2029. class B notes due May 2029.")
    check(v == "May 2029", "UNIT class-maturity agree, lowercase labels", repr(v))

    # Disagreement: current behaviour, no deal-level value.
    v, fl = mat("Class A notes due March 15, 2028. Class B notes due March 15, 2030.")
    check(v is None, "UNIT class-maturity disagree -> no deal-level value",
          repr((v, fl)))
    check(not any(str(x).startswith("maturity_from_class_agreement") for x in fl),
          "UNIT class-maturity disagree carries no agreement flag", repr(fl))

    # Disagreement inside ONE sentence.
    v, _ = mat("Class A notes are due March 2028 and Class B notes are due March 2030.")
    check(v is None, "UNIT class-maturity disagree within one sentence", repr(v))

    # A single class-scoped maturity is one class's term, not the deal's,
    # when the page has other tranches ("the other two"). Since 2026-11-17 a
    # page whose ONLY class states the date adopts it, flagged; the plural
    # here is the guard that keeps this one out.
    v, _ = mat("The riskier Class 11 tranche has protection to the end of May 2025, "
               "while the other two tranches run longer.")
    check(v is None, "UNIT class-maturity single class -> no deal-level value", repr(v))
    v, fl = mat("The Class A notes due March 2028.")
    check(v == "March 2028" and "maturity_from_single_class=A" in fl,
          "UNIT class-maturity single class, 'notes due' (one-class page adopts)", repr((v, fl)))
    # Same class stated twice is still one class, and a one-class page.
    v, _ = mat("Class A notes due March 2028. The Class A notes mature in March 2028.")
    check(v == "March 2028", "UNIT class-maturity one class stated twice", repr(v))

    # A class with no date beside a dated class: not evidence of agreement.
    v, _ = mat("Class A notes due March 2028, while the Class B notes are floating rate.")
    check(v is None, "UNIT class-maturity dated class beside undated class", repr(v))

    # A deal-level statement wins over any per-class one.
    v, _ = mat("The notes are due in April 2029. Class A notes due March 2028. "
               "Class B notes due March 2028.")
    check(v == "April 2029", "UNIT class-maturity deal-level still wins", repr(v))

    # Extensions and predecessors stay excluded, and do not join the vote.
    v, _ = mat("Class A notes due March 2028. Class B notes due March 2028. "
               "Class C maturity extended to June 2029.")
    check(v == "March 2028", "UNIT class-maturity extension does not break agreement",
          repr(v))
    v, _ = mat("Class A notes due March 2028. Class B notes due March 2028, "
               "which replaces the prior notes.")
    check(v is None, "UNIT class-maturity replacement sentence is not a vote", repr(v))

    # Backward references (dates before the issue year) are not this deal's.
    v, _ = mat("Class A notes due March 2019. Class B notes due March 2019.",
               issue_year=2024)
    check(v is None, "UNIT class-maturity backward reference excluded", repr(v))


def unit_maturity_recall_round3():
    """Recall round 2026-11-17 (backlog 3): the single-class rule, the
    series-scoped veto, the positional extension veto, "April, 2015", the
    "running from X to Y" maturity, and the term phrasings read from the
    audit-sample deals the earlier patterns missed. Synthetic sentences that
    quote the pages."""
    def mat(text, own=frozenset(), issue_year=None):
        f = _apply_patterns("maturity_date", TIER2_PATTERNS["maturity_date"], text,
                            issue_year, own)
        return f["value"], f["flags"]

    def term(text):
        return _apply_patterns("term_length", TIER2_PATTERNS["term_length"], text)["value"]

    # (a) single-tranche class vote (Herbie Re 2025-1).
    herbie = ("Fidelis is aiming to secure at least $75 million of retrocessional protection "
              "through the issuance of a single tranche of Series 2025-1 cat bond notes. The "
              "single tranche of Class A notes will provide retro reinsurance protection across "
              "a two-year term and two annual risk periods to the end of May 2027, sources told us.")
    v, fl = mat(herbie, frozenset({"2025-1"}))
    check(v == "May 2027" and "maturity_from_single_class=A" in fl,
          "UNIT single-class page adopts its one class's maturity", repr((v, fl)))
    # A second class label, undated, blocks it: that tranche's term is unknown.
    v, _ = mat(herbie + " The Class B notes are floating rate.", frozenset({"2025-1"}))
    check(v is None, "UNIT single-class rule needs exactly one label on the page", repr(v))
    # A stated count above one blocks it.
    v, _ = mat("Two tranches of notes are on offer. The Class A notes due March 2028.")
    check(v is None, "UNIT single-class rule blocked by a stated count of two", repr(v))
    # A sibling deal's sentence does not count against the page.
    v, _ = mat("The Class A notes due March 2028. The 2024-1 deal had three tranches.",
               frozenset({"2025-1"}))
    check(v == "March 2028", "UNIT single-class rule ignores a sibling's plural", repr(v))

    # (b) series-scoped veto on a multi-series page (Isosceles 2023-A/C/G).
    iso = ("$20.7m Series 2023-A Class A notes due May 10, 2024. $27.15955 million Series "
           "2023-C notes due June 7, 2024. $3.65625 million Series 2023-G Class E notes due "
           "June 7, 2024.")
    v, fl = mat(iso, frozenset({"2023-A", "2023-C", "2023-G"}))
    check(v is None, "UNIT series-scoped date on a multi-series page is vetoed", repr((v, fl)))
    # Series that agree vote like classes do.
    v, fl = mat("The Series 2023-1 notes mature in June 2026. The Series 2023-2 notes mature "
                "in June 2026.", frozenset({"2023-1", "2023-2"}))
    check(v == "June 2026" and any("class_agreement" in str(x) for x in fl),
          "UNIT agreeing series on a multi-series page adopt", repr((v, fl)))
    # On a single-series page a sentence naming the series is deal-level.
    v, _ = mat("The Series 2023-1 notes mature in June 2026.", frozenset({"2023-1"}))
    check(v == "June 2026", "UNIT series mention on a one-series page is deal-level", repr(v))

    # Positional extension veto (Blue Fin Series 3 vs Residential Re 2014-1).
    v, _ = mat("The deal is due to run until May 2013 with the possibility to extend in three "
               "month increments to allow for loss development and reporting.")
    check(v == "May 2013", "UNIT extension AFTER the date does not veto it", repr(v))
    v, _ = mat("The notes have had their maturity extended again to December 6th 2018.")
    check(v is None, "UNIT extension BEFORE the date vetoes it", repr(v))
    v, _ = mat("The notes had already had their maturity extended through to January 2027, "
               "but the reinsurer elected an early redemption at the end of 2025.")
    check(v is None, "UNIT 'extended through to' vetoed (Matterhorn 2020-2)", repr(v))

    # "April, 2015" (Mythen 2012-1): three classes agree.
    v, fl = mat("$50m Series 2012-1 Class A Notes due April, 2015. $100m Series 2012-1 Class E "
                "Notes due April, 2015. $250m Series 2012-1 Class H Notes due April, 2015.",
                frozenset({"2012-1"}))
    check(v == "April 2015", "UNIT 'April, 2015' reads as April 2015 across classes", repr((v, fl)))
    check(_strip_day("April, 2015") == "April 2015", "UNIT strip-day drops a bare comma")

    # "running from June 2017 to the end of December 2019" (Bonanza 2016-1).
    v, _ = mat("The term of the coverage would be two and a half years, running from June 2017 "
               "to the end of December 2019.")
    check(v == "December 2019", "UNIT 'running from X to the end of Y' reads Y", repr(v))
    v, _ = mat("designed to provide SCOR with fully collateralized cover on an annual-aggregate "
               "basis for European windstorms and Japanese earthquakes from December 2010 until "
               "April 2014.")
    check(v == "April 2014", "UNIT 'cover ... from X until Y' reads Y (Atlas VI 2010-1)", repr(v))
    v, _ = mat("the reinsurance it provides will cover a portfolio of existing mortgage insurance "
               "policies that have been underwritten from January 2019 through September 2019.")
    check(v is None, "UNIT an origination window is not a maturity (Triangle Re 2019-1)", repr(v))
    v, _ = mat("reinsurance protection, covering an existing portfolio of mortgage insurance "
               "policies written primarily from April 1, 2021 through September 30, 2021.")
    check(v is None, "UNIT a policy window is not a maturity (Oaktown Re VII)", repr(v))
    v, _ = mat("Covered mortgage loans have an effective date from January 1st 2021 to May 28th "
               "2021, with the pool made up of 181,727 mortgage loans.")
    check(v is None, "UNIT a loan effective-date window is not a maturity (Home Re 2021-2)", repr(v))
    # Slug tokens that are not series ids must not make a one-series page
    # look multi-series (Residential Re 2011-2's "2011-L", Vision 2039's
    # "2039-2025").
    v, _ = mat("This Series 2011-2 issuance will provide USAA with cover, scheduled to run for "
               "just over four years with maturity slated for 6th December 2015.",
               _series_tokens("Residential Reinsurance 2011 Ltd. (Series 2011-2)")
               | _series_tokens("https://www.artemis.bm/deal-directory/residential-reinsurance-2011-ltd-series-2011-2/"))
    check(v == "December 2015", "UNIT a non-series slug token is not a second series", repr(v))
    v, _ = mat("The Vision 2039 - Series 2025-1 notes will provide Flood Re with three years of "
               "retrocessional UK flood reinsurance to the end of March 2028.",
               frozenset({"2039-2025", "2025-1"}))
    check(v == "March 2028", "UNIT 'Vision 2039 - 2025-1' is one series", repr(v))
    check("2011-L" not in _series_tokens("residential-reinsurance-2011-ltd-series-2011-2"),
          "UNIT slug '2011-ltd' is not a letter series")
    check(_series_tokens("isosceles-insurance-ltd-series-2023-a-c-g") >= {"2023-A", "2023-C", "2023-G"},
          "UNIT letter-series slug still enumerates")
    check("2020-C1" in _series_tokens("Isosceles Insurance Ltd. (Series 2020-C1)")
          and "2020-A1" in _series_tokens("a $16.5 million Isosceles Insurance Ltd. (Series 2020-A1) arrangement"),
          "UNIT letter-plus-digit series ids are tokens")
    check("2020-X" not in _series_tokens("segregated account Randolph Re 2020-XX"),
          "UNIT '2020-XX' placeholder is not a series")
    check(term("provide coverage across the Atlantic hurricane season of 2016") is None,
          "UNIT 'Atlantic hurricane season' is not a term")

    # Term phrasings.
    for text, want in [
        ("a source of parametric cover for earthquakes in Mexico over a three-year period", "three-year"),
        ("This $200m, 3 year deal has been issued by Atlas Reinsurance V Ltd.", "3 year"),
        ("This three year deal comprises two tranches.", "three year"),
        ("This $180m issue will provide three years of cover for U.S. windstorm", "three years"),
        ("will provide three years of coverage for calendar years 2026 through 2028", "three years"),
        ("seeking three years of both annual aggregate and per-occurrence retrocessional "
         "reinsurance protection", "three years"),
        ("will provide Kin with a three hurricane season source of reinsurance", "three hurricane season"),
        ("with coverage running across three annual risk periods from calendar year 2024", "three annual risk periods"),
        ("the market has been quiet this year and the deal is the first of its kind", None),
        ("the sponsor returns for the first time in five years with a new deal", None),
    ]:
        got = term(text)
        check(got == want, f"UNIT term recall {text[:40]!r}", f"want={want!r} got={got!r}")
    for text, years in [("three hurricane season", 3), ("three annual risk periods", 3), ("3 year", 3)]:
        check(_term_to_years(text) == years, f"UNIT term-to-years {text!r}", repr(_term_to_years(text)))


def unit_spread_recall():
    """Settled-spread recall round (2026-11-18). Synthetic sentences quoting
    the pages, one per anchor, and one per guard the anchors carry."""
    def sp(text, issue_year=2021, own=frozenset()):
        return _apply_patterns("spread_risk_margin", TIER2_PATTERNS["spread_risk_margin"],
                               text, issue_year, own)["value"]

    def ap(text):
        return _apply_patterns("attachment_probability", TIER2_PATTERNS["attachment_probability"],
                               text, 2021)["value"]

    for text, want in [
        # (a) the band of guidance
        ("but with coupon pricing now fixed at the upper-end of initial guidance, at 5.5%.", "5.5%"),
        ("while the pricing settled at the top-end of guidance, at 4.75%.", "4.75%"),
        ("notes priced at the low-end of reduced guidance, at a 6.75% initial coupon spread.", "6.75%"),
        ("the pricing fell to below the low-end of guidance, settling at 5.75%.", "5.75%"),
        ("the pricing settled at the low-end of guidance, to offer investors a 6.75% coupon.", "6.75%"),
        ("remained at $45 million in size and priced at the top of elevated guidance, at 16%.", "16%"),
        ("sources said the pricing was fixed in the bottom-half of guidance at 4.75%.", "4.75%"),
        ("the coupon was eventually fixed at the top-end of the already revised upwards guidance, at 19%.", "19%"),
        ("with pricing at the mid-point of 8.75%.", "8.75%"),
        # (b) verb then at/of
        ("while their coupon was finalised at 5%, so above the initial range.", "5%"),
        ("with the coupon fixed at 5.5%.", "5.5%"),
        ("while the pricing settled with a coupon spread of 10% to be paid to investors.", "10%"),
        ("eventually priced its $95 million of notes at 2.9%, so above the mid-point.", "2.9%"),
        ("moved to the top-end of guidance and was finalised at the 8.5% coupon level.", "8.5%"),
        ("with the pricing at the fixed level of a 14% coupon, the top-end of initial guidance.", "14%"),
        # (c), (d)
        ("with the coupon now suggested at a fixed 7.75%.", "7.75%"),
        ("eventually priced to pay investors a 6.9% coupon, so above the initial guidance.", "6.9%"),
        ("the pricing eventually settled down some 16% from the initial midpoint of spread "
         "guidance, to offer a 6% coupon.", "6%"),
        ("The pricing was finalised at a raised level though, to provide a 5.1% coupon to investors.", "5.1%"),
        # (e)
        ("with pricing at the 4.4% risk margin, so the low end of the raised guidance range.", "4.4%"),
        ("and we\u2019re told the initial risk interest spread to be paid to investors is 7%.", "7%"),
        ("Class 11 \u2013 $35 million; coupon 12.5%.", "12.5%"),
        # (f) zero-coupon equivalents
        ("the pricing has now been fixed at the high-end of guidance at 88% of par, so a "
         "roughly 12% coupon equivalent.", "12%"),
        ("fixed at the upper-end of guidance, with a coupon equivalent price of 26%, or 74% of par.", "26%"),
        ("and priced at 91.75%, so an 8.25% equivalent spread and at the bottom of the range.", "8.25%"),
        # Guards. A per-class pricing list is not one tranche's spread.
        ("The pricing was eventually finalised at 11.25% for the A-1 notes, 4.5% for the B-1 "
         "notes and 4.25% for the C-1 notes.", None),
        # The change in price after the spread is not read; the spread is.
        ("was fixed at the low-end of reduced guidance, at 2.25%, which represents a 25% drop "
         "in price from the initial mid-point.", "2.25%"),
        # Expectation language is not a settlement.
        ("and we\u2019re told pricing looks set to settle at 8.25%, so just above the mid-point.", None),
        ("we\u2019re now told the pricing looks likely to end up at the top-end, of 4.5%.", None),
        # A range endpoint, a change, a price of par: still rejected.
        ("The Class A notes are being offered with a coupon price guidance range of 10% to 10.75%.", None),
        ("At final pricing the cat bond upsized by 20% to reach $300m in size.", None),
        ("pricing guidance offered at 85% to 86% of par value, and we\u2019re told eventually "
         "priced at 86.25%, so effectively below the initial range.", None),
        ("with pricing of both tranches settling at the revised 4.25% for the $235 million "
         "Class A tranche and 6.5% for the $70 million Class B tranche of notes.", None),
        # "pricing of 6.7%" is a change when "from the mid-point" follows.
        ("an increase in pricing of 6.7% from the mid-point of the original range.", None),
        # Expectation before the verb, with a band after it.
        ("pricing looks set to settle at the top-end of guidance, at 5%.", None),
        # A probability or loss between the verb and the number is a
        # different field ("expected loss" is also caught as expectation).
        ("The notes priced with a probability of attachment of 2%.", None),
        ("The notes priced at $50 million, with an expected loss of 2%.", None),
    ]:
        got = sp(text)
        check(got == want, f"UNIT spread recall {text[:40]!r}", f"want={want!r} got={got!r}")
    # A predecessor's settled coupon is still a foreign reference.
    got = sp("The Series 2020-1 notes, which have an expected loss of 0.33%, priced recently "
             "with a 3% coupon, which was the mid-point of guidance.", 2020, frozenset({"2020-2"}))
    check(got is None, "UNIT spread recall: sibling series' coupon excluded", repr(got))
    for text, want in [
        ("We\u2019re told that this equates to a 5.9% attachment probability and a 3.65% expected loss.", "5.9%"),
        ("will have an initial annual modelled attachment probability and expected loss of 0.888%.", "0.888%"),
        # Never the tail of a range, nor the tail of a number.
        ("guidance of 5% to 5.9% attachment probability", None),
    ]:
        got = ap(text)
        check(got == want, f"UNIT AP recall {text[:40]!r}", f"want={want!r} got={got!r}")


def unit_class_repayment():
    """Class-level repayment for multi-term deals (2026-11-17): the class
    loader, the split rule and its guards, the scaling with write-downs, and
    the flows and upcoming maturities it produces."""
    import tempfile
    import pandas as pd

    bridge = pd.DataFrame([
        ("https://x/a/", "A1", "2025-06-07"), ("https://x/a/", "A2", "2028-06-07"), ("https://x/a/", "A3", "2028-06-07"),
        ("https://x/b/", "B1", "2025-06-07"), ("https://x/b/", "B2", "2028-06-07"),
    ], columns=["deal_url", "cusip_id", "trace_maturity_date"])
    classes = pd.DataFrame([
        ("A1", "https://x/a/", "A", "True"), ("A2", "https://x/a/", "B", "True"), ("A3", "https://x/a/", "B", "True"),
        ("B1", "https://x/b/", "A", "True"), ("B2", "https://x/b/", "B", "False"),
    ], columns=["cusip_id", "deal_url", "class_label", "unanimous"])
    with tempfile.TemporaryDirectory() as td:
        bp, cp = Path(td) / "bridge.csv", Path(td) / "classes.csv"
        bridge.to_csv(bp, index=False); classes.to_csv(cp, index=False)
        cm = rf.load_class_maturities(bp, cp)
        tr = rf.load_trace_maturities(bp)
    got = {(r.deal_url, r.class_label): (r.class_month, r.class_cusips) for r in cm.itertuples(index=False)}
    check(got == {("https://x/a/", "A"): ("2025-06", 1), ("https://x/a/", "B"): ("2028-06", 2),
                  ("https://x/b/", "A"): ("2025-06", 1)},
          "UNIT class loader: unanimous labels only, month per class", repr(got))
    check(rf._norm_class("Class A-1") == "A1" and rf._norm_class("a1") == "A1" and rf._norm_class("") == "",
          "UNIT class label normalisation")

    # The split rule.
    cls = {"A": ("2025-06", False, 1), "B": ("2028-06", False, 2)}
    off, flag = rf.class_split(cls, {"A": 100.0, "B": 200.0}, 300.0, "2028-06", 3)
    check(off == [("A", "2025-06", 100.0)] and flag == "maturity_split=class_level:2_of_2_classes",
          "UNIT class split: only the class off the majority month leaves separately", repr((off, flag)))
    off, flag = rf.class_split(cls, {"A": 100.0}, 300.0, "2028-06", 3)
    check(off == [("A", "2025-06", 100.0)] and "unlabelled_remainder" in flag,
          "UNIT class split: a class without a size leaves the remainder unlabelled", repr((off, flag)))
    off, flag = rf.class_split(cls, {"A": 200.0, "B": 200.0}, 300.0, "2028-06", 3)
    check(off == [] and flag.startswith("maturity_split=fallback_class_sizes_exceed_deal"),
          "UNIT class split: sizes above the deal fall back", repr((off, flag)))
    off, flag = rf.class_split(cls, {"A": 100.5, "B": 200.5}, 300.0, "2028-06", 3)
    check(len(off) == 1 and abs(off[0][2] - 100.5 * 300 / 301) < 1e-9,
          "UNIT class split: sizes within tolerance are capped to the deal", repr(off))
    off, flag = rf.class_split({}, {"A": 100.0}, 300.0, "2028-06", 3)
    check(off == [] and flag == "maturity_split=majority_no_class_labels", "UNIT class split: no labels -> majority", flag)
    off, flag = rf.class_split(cls, {"C": 100.0}, 300.0, "2028-06", 3)
    check(off == [] and flag == "maturity_split=majority_no_class_size_match", "UNIT class split: no size match -> majority", flag)
    off, flag = rf.class_split({"A": ("2025-06", True, 1), "B": ("2028-06", False, 2)}, {"A": 100.0, "B": 200.0}, 300.0, "2028-06", 3)
    check("class_months_disagree=A" in flag, "UNIT class split: a class whose CUSIPs disagree is flagged", flag)
    off, flag = rf.class_split({"A": ("2025-06", False, 1), "B": ("2028-06", False, 1)}, {"A": 100.0, "B": 200.0}, 300.0, "2028-06", 3)
    check("unlabelled_remainder" in flag, "UNIT class split: a bridged CUSIP without a label marks the remainder", flag)
    off, flag = rf.class_split({"A": ("2025-06", True), "B": ("2028-06", False)}, {"A": 100.0, "B": 200.0}, 300.0, "2028-06", 2)
    check("class_months_disagree=A" in flag, "UNIT class split: a class whose CUSIPs disagree is flagged", flag)

    # Through the book: deal a, $300m, classes A ($100m, 2025-06) and B ($200m, 2028-06).
    def deals(rows):
        cols = ["deal_slug", "index_issuer_name", "size", "date_of_issue", "maturity_date",
                "maturity_date_derived", "maturity_scheduled", "deal_is_private", "deal_status", "deal_url"]
        return pd.DataFrame([dict(zip(cols, r)) for r in rows], columns=cols, dtype=str).fillna("")

    def losses(rows):
        cols = ["cat_bond", "deal_slug", "orig_size", "loss_amount", "date_of_loss",
                "loss_status", "loss_amount_derived", "is_settled", "time_to_resolution"]
        return pd.DataFrame([dict(zip(cols, r)) for r in rows], columns=cols, dtype=str).fillna("")

    tranches = pd.DataFrame([("a", "Class A", "$100m"), ("a", "Class B", "$200 million")],
                            columns=["deal_slug", "tranche_id", "tranche_size_final"])
    d = deals([("a", "A Re Ltd.", "$300m", "Jun 2022", "", "", "", "", "issued", "https://x/a/")])
    b = rf.deal_book(d, losses([]), trace=tr, classes=cm, tranches=tranches)
    row = b.iloc[0]
    check(row.maturity_month == "2028-06" and "trace_maturity_tranches_disagree=36m" in row["flags"]
          and "maturity_split=class_level:2_of_2_classes" in row["flags"],
          "UNIT class repayment: majority month kept, split flagged", row["flags"])
    check(row.class_repay == [("A", "2025-06", 100.0)], "UNIT class repayment: class A leaves at its own month", repr(row.class_repay))
    f = rf.monthly_flows(b)
    check(abs(f.loc["2025-06", "repaid"] - 100.0) < 1e-9 and abs(f.loc["2028-06", "repaid"] - 200.0) < 1e-9,
          "UNIT class repayment: flows split 100 / 200", repr(f.repaid.to_dict()))
    y = rf.outstanding_by_year(f, "2028-08").set_index("year").outstanding
    check((y[2024], y[2025], y[2027], y[2028]) == (300.0, 200.0, 200.0, 0.0),
          "UNIT class repayment: stock steps down at each class", repr(y.to_dict()))
    up = rf.upcoming_maturities(b, "2024-12")
    check(sorted(zip(up.month, up.m)) == [("2025-06", 100.0), ("2028-06", 200.0)],
          "UNIT class repayment: upcoming maturities per class", repr(up.to_dict("records")))
    # A $60m write-down scales both classes: 240 remaining -> A 80, B 160.
    L = losses([("A Re Ltd. (Series 1) Class A", "a", "$100m", "$60m", "Jan 2024", "stated_amount", "60000000.0", "True", "3 months")])
    b = rf.deal_book(d, L, trace=tr, classes=cm, tranches=tranches)
    f = rf.monthly_flows(b)
    check(abs(f.loc["2025-06", "repaid"] - 80.0) < 1e-9 and abs(f.loc["2028-06", "repaid"] - 160.0) < 1e-9
          and abs(f.loc["2024-01", "written_down"] - 60.0) < 1e-9,
          "UNIT class repayment: a write-down scales every class", repr(f.to_dict()))
    # Without the classes file the deal leaves whole at the majority month.
    b = rf.deal_book(d, losses([]), trace=tr)
    check(b.iloc[0].class_repay == [] and "maturity_split" not in b.iloc[0]["flags"]
          and abs(rf.monthly_flows(b).loc["2028-06", "repaid"] - 300.0) < 1e-9,
          "UNIT class repayment: off without the classes file", b.iloc[0]["flags"])
    # Classes present but no labels for this deal: flagged, whole at majority.
    b = rf.deal_book(d, losses([]), trace=tr, classes=cm[cm.deal_url == "https://x/b/"], tranches=tranches)
    check("maturity_split=majority_no_class_labels" in b.iloc[0]["flags"] and b.iloc[0].class_repay == [],
          "UNIT class repayment: no labels for the deal -> majority, flagged", b.iloc[0]["flags"])
    check(rf.resolve_classes_path(None) is None and rf.resolve_classes_path("off") is None,
          "UNIT classes path resolution")


def unit_loss_timing():
    """--loss-timing settlement (2026-11-17): the settlement month read from
    the row, and the ledger moving the write-down to it; the default is
    unchanged."""
    import pandas as pd

    class R:
        def __init__(self, ttr, text=""):
            self.time_to_resolution, self.loss_amount = ttr, text

    for ttr, text, lm, want in [
        ("Approx. 18 months", "", "2017-09", ("2019-03", "loss_timing=settlement:+18m")),
        ("Roughly 34 months", "", "2017-12", ("2020-10", "loss_timing=settlement:+34m")),
        ("Approx. two years", "", "2018-10", ("2020-10", "loss_timing=settlement:+24m")),
        ("Approx. 53 months, principal reduced to zero at end of Feb 2023", "", "2018-10", ("2023-02", "loss_timing=settlement:dated")),
        ("Approx. 19 months (Irma Sept. 2017, to notes delisted with zero balance Mar. 2019)", "", "2017-09", ("2019-03", "loss_timing=settlement:dated")),
        ("Paid out in 2020", "", "2018-12", ("2020-12", "loss_timing=settlement:year")),
        ("Loss payments finished in 2020", "", "2017-12", ("2020-12", "loss_timing=settlement:year")),
        ("Ongoing", "Principal steadily reduced down to $25m, then redeemed in April 2026", "2020-12", ("2026-04", "loss_timing=settlement:dated")),
        ("Ongoing", "", "2022-09", ("2022-09", "loss_settlement_unknown")),
        ("5 weeks", "", "2022-09", ("2022-09", "loss_settlement_unknown")),
        ("3 months", "", None, (None, "loss_settlement_unknown")),
    ]:
        got = rf.settlement_month(R(ttr, text), lm)
        check(got == want, f"UNIT settlement month {ttr[:30]!r}", f"want={want} got={got}")

    def deals(rows):
        cols = ["deal_slug", "index_issuer_name", "size", "date_of_issue", "maturity_date",
                "maturity_date_derived", "maturity_scheduled", "deal_is_private", "deal_status"]
        return pd.DataFrame([dict(zip(cols, r)) for r in rows], columns=cols, dtype=str).fillna("")

    def losses(rows):
        cols = ["cat_bond", "deal_slug", "orig_size", "loss_amount", "date_of_loss",
                "loss_status", "loss_amount_derived", "is_settled", "time_to_resolution"]
        return pd.DataFrame([dict(zip(cols, r)) for r in rows], columns=cols, dtype=str).fillna("")

    d = deals([("a", "A Re Ltd.", "$100m", "Jun 2020", "June 2023", "", "June 2023", "", "issued")])
    L = losses([("A Re Ltd. (Series 1) Class A", "a", "$100m", "$40m", "Sep 2021", "stated_amount", "40000000.0", "True", "Approx. 18 months")])
    f_loss = rf.monthly_flows(rf.deal_book(d, L))
    f_set = rf.monthly_flows(rf.deal_book(d, L, loss_timing="settlement"))
    check(abs(f_loss.loc["2021-09", "written_down"] - 40.0) < 1e-9 and "2023-03" not in f_loss.index,
          "UNIT loss timing: default writes down at the loss month", repr(f_loss.written_down.to_dict()))
    check(abs(f_set.loc["2023-03", "written_down"] - 40.0) < 1e-9 and "2021-09" not in f_set.index,
          "UNIT loss timing: settlement writes down 18 months later", repr(f_set.written_down.to_dict()))
    b = rf.deal_book(d, L, loss_timing="settlement")
    check("loss_timing=settlement:+18m" in b.iloc[0]["flags"], "UNIT loss timing: flagged", b.iloc[0]["flags"])
    y_loss = rf.outstanding_by_year(f_loss, "2024-08").set_index("year").outstanding
    y_set = rf.outstanding_by_year(f_set, "2024-08").set_index("year").outstanding
    check((y_loss[2021], y_loss[2022], y_loss[2023]) == (60.0, 60.0, 0.0) and (y_set[2021], y_set[2022], y_set[2023]) == (100.0, 100.0, 0.0),
          "UNIT loss timing: the stock holds the amount until settlement", repr((y_loss.to_dict(), y_set.to_dict())))
    try:
        rf.deal_book(d, L, loss_timing="never")
        check(False, "UNIT loss timing: bad value raises")
    except ValueError:
        check(True, "UNIT loss timing: bad value raises")


def unit_parse_losses():
    """The losses table's derived loss amount, on the cell phrasings the
    2026-11-17 read found mis-derived or underived (synthetic table)."""
    import parse_losses as pl

    def table(rows):
        body = "".join(
            "<tr>" + "".join("<td>%s</td>" % c for c in r) + "</tr>" for r in rows)
        return ("<html><body><table id='tablepress-2'><tr>" + "<th>h</th>" * 7
                + "</tr>" + body + "</table></body></html>")

    rows = [
        ("Blue Halo Re Ltd. (Series 2016-1) Class B", "Allianz", "$55m", "Hurricanes",
         "$47.87m reduction in principal", "Approx. 20 months", "2017"),
        ("Frontline Re Ltd. (Series 2018-1) - Class A", "Frontline", "$250m", "Hurricanes",
         "~$200m paid out. $25.5m+ returned to investors. Remaining $16.6m marked at around 30 to 40 cents on the dollar.", "Ongoing", "2018"),
        ("Residential Reinsurance 2015 Limited (Series 2015-1) Class 11", "USAA", "$100m", "Hurricanes",
         "Principal reduced to $19.55m (priced for a further 15% loss of principal)", "Ongoing", "2017"),
        ("Residential Reinsurance 2016 Limited (Series 2016-1) Class 11", "USAA", "$75m", "Hurricanes",
         "Principal reduced to ~$74.67m (priced for ~15% loss)", "Ongoing", "2017"),
        ("Residential Reinsurance 2016 Limited (Series 2016-1) Class 10", "USAA", "$65m", "Hurricanes",
         "Loss payments reduced by wildfire subrogation. ~$14m returned to investors, the rest recovered by sponsor under reinsurance.", "Roughly 34 months", "2017"),
        ("Matterhorn Re Ltd. (Series 2020-2) - Class A", "Swiss Re", "$80m", "Hurricanes",
         "Approx. $33m recovered by sponsor. Just over $46.9m of principal returned to investors.", "Ongoing", "2021"),
        ("Residential Reinsurance 2019 Limited (Series 2019-1) - Class 12", "USAA", "$60m", "Hurricanes",
         "50% of principal returned, leaving $30m extended. Mark to market implied ~20% loss of remaining principal.", "Ongoing", "2020"),
        ("Sanders Re III Ltd. (Series 2022-2) - Class B", "Allstate", "$100m", "Hurricanes",
         "Recovered to par", "Resolved", "2023"),
        ("IBRD CAR Jamaica 2024", "Jamaica", "$150m", "Hurricane Melissa",
         "100% loss of principal confirmed", "10 days", "October 2025"),
        ("Some Re (Series 2020-1) Class A", "X", "$100m", "Hurricanes",
         "$60m - 30% loss of principal", "Resolved", "2021"),
    ]
    df = pl.parse_losses(table(rows)).set_index("cat_bond")
    got = {k: (df.loc[k, "loss_amount_derived"], df.loc[k, "loss_amount_basis"], df.loc[k, "loss_status"])
           for k in df.index}
    want = {
        rows[0][0]: (47.87e6, "paid_out", "partial_loss"),
        rows[1][0]: (200e6, "paid_out", "partial_loss"),
        rows[2][0]: (80.45e6, "orig_minus_remaining", "partial_loss"),
        rows[3][0]: (0.33e6, "orig_minus_remaining", "partial_loss"),
        rows[4][0]: (51e6, "orig_minus_returned", "partial_loss"),
        rows[5][0]: (33e6, "paid_out", "partial_loss"),
        rows[6][0]: (None, None, "partial_loss"),
        rows[7][0]: (None, None, "repaid_in_full"),
        rows[8][0]: (150e6, "orig_minus_remaining", "total_loss"),
        rows[9][0]: (60e6, "stated", "stated_amount"),
    }
    for k, (amt, basis, status) in want.items():
        g_amt, g_basis, g_status = got[k]
        ok = ((g_amt is None or (isinstance(g_amt, float) and g_amt != g_amt)) if amt is None
              else (g_amt is not None and abs(float(g_amt) - amt) < 1.0))
        check(ok and (g_basis == basis or (basis is None and (g_basis is None or g_basis != g_basis)))
              and g_status == status,
              f"UNIT losses derive {k[:40]!r}", f"want={(amt, basis, status)} got={got[k]}")
    check(pl._pct_range("50% of principal returned, leaving $30m") == (None, None),
          "UNIT losses '% of principal returned' is not a loss percent")
    check(pl._remaining_principal("Principal reduced to ~$74.67m") == "$74.67m",
          "UNIT losses remaining principal reads through a tilde")


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


def golden_available():
    """True when every golden page is cached. False when raw/ is absent.

    A PARTIAL cache is an error, not a skip: silently running a subset would
    change the check count and could hide a regression behind a green run.
    """
    missing = [s for s in PAGES if not _cache_path(BASE + s + "/").exists()]
    if len(missing) == len(PAGES):
        return False
    if missing:
        raise SystemExit(
            f"raw/ is present but {len(missing)}/{len(PAGES)} golden pages are "
            f"missing from the cache (first: {missing[0]}). Refusing to run a "
            "partial golden suite.")
    if not (ROOT / "data" / "queue.csv").exists():
        raise SystemExit("raw/ is present but data/queue.csv is not; the "
                         "sibling-registry checks need it.")
    return True


def main():
    golden = golden_available()
    unit_percent_parsing()
    unit_predicates()
    unit_component_scope()
    unit_sentences()
    unit_backward_reference()
    unit_maturity_class_scoped()
    unit_maturity_recall_round3()
    unit_parse_losses()
    unit_class_repayment()
    unit_loss_timing()
    unit_spread_recall()
    n_unit = len(results)
    if golden:
        unit_registry_rules()       # parses pages; reads data/queue.csv
        unit_sibling_registry()     # parses pages; reads data/queue.csv
    for slug in (PAGES if golden else []):
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
    # Pin the total. Guards are conditional on extracted data, so a regression
    # that empties a field silently removes its checks and the suite still
    # reports "all passed" on a smaller suite.
    # 1759 = 192 unit + 1567 golden when the golden pin was measured over raw/
    # (2026-09-23). Since then 18 UNIT checks were added (class maturity and
    # separate-series totals),
    # 340 golden checks were revived (2026-10-02): the per-tranche pct/spread/
    # EL<=AP, Seaside and Citrus guards had sat inside the check-count failure
    # branch, after the page loop, so they ran only when the count was already
    # wrong, and then only over the last page. Four Merna pages added 58 golden
    # checks when the separate-series-total rule was pinned (2026-10-21).
    # Settled-spread recall round (2026-11-18): 41 unit checks; ten golden
    # pages and 368 new spread values (each spread value adds per-tranche
    # guard checks) took the golden count 1965 -> 2192.
    # The tiers are pinned separately so unit checks can be added without
    # touching the golden pin, which has only ever been measured over raw/.
    EXPECTED_UNIT_CHECKS = 419
    EXPECTED_GOLDEN_CHECKS = 2192
    n_golden = len(results) - n_unit
    if n_unit != EXPECTED_UNIT_CHECKS:
        results.append((False, "GUARD unit-check-count",
                        f"expected {EXPECTED_UNIT_CHECKS} unit checks, ran "
                        f"{n_unit} - update EXPECTED_UNIT_CHECKS deliberately"))
    if not golden:
        print(f"{n_unit} UNIT checks ran; {EXPECTED_GOLDEN_CHECKS} golden "
              "checks skipped: raw/ not present")
    elif n_golden != EXPECTED_GOLDEN_CHECKS:
        results.append((False, "GUARD check-count",
                        f"expected {EXPECTED_GOLDEN_CHECKS} golden checks, ran "
                        f"{n_golden}"
                        " - update EXPECTED_GOLDEN_CHECKS deliberately"))

    passed = sum(1 for ok, *_ in results if ok)
    for ok, label, detail in results:
        if not ok:
            print(f"  FAIL  {label}  {detail}")
    print(f"\n{passed}/{len(results)} checks passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
