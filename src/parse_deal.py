"""Extract as much as possible from an Artemis deal page, with provenance.

Every field comes back as a record, never a bare value:

    {"value", "confidence", "method", "evidence", "flags"}

Confidence rubric — grounded in *how* the value was obtained, not in how
plausible it looks:

    high    Tier 1. Read from an explicitly labelled <li><strong>Key:</strong>
            block. Deterministic; only wrong if Artemis itself is wrong.
    medium  Tier 2, matched by a strongly anchored pattern ("expected loss of
            2.48%") with exactly one distinct candidate on the page.
    low     Tier 2, but something is off: several distinct candidates and a
            rule chose one, or only a loose fallback pattern hit.
    None    Not found. `flags` says "not_found"; never silently absent.

Tier 2 never writes into a Tier-1 field. Artemis writes deal prose
incrementally as a deal markets, so the body preserves launch-time terms while
the summary box holds final terms. That gap is signal, not error, so it is
reported as a `size_change` record rather than suppressed.
"""

import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch import fetch
from mentions import classify, extract, solve_tranche_sizes

LABEL_MAP = {
    "issuer": "issuer",
    "cedent / sponsor": "cedent_sponsor",
    "placement / structuring agent/s": "placement_structuring_agents",
    "risk modelling / calculation agents etc": "risk_modeller",
    "risks / perils covered": "perils_covered",
    "size": "size",
    "trigger type": "trigger_type",
    "ratings": "ratings",
    "date of issue": "date_of_issue",
}
TIER1_KEYS = list(LABEL_MAP.values())

# At-a-glance rows that are navigation, not data ("Articles discussing X from
# Artemis.bm"). Found by the extra_fields discovery hook during the era pilot.
# Listed explicitly so they stop raising unmapped_label page flags, while a
# genuinely new label still announces itself.
IGNORED_LABELS = {"artemis.bm news coverage"}

# Longest-first so "June" matches before "Jun". A closed vocabulary is the
# whole point: an open [A-Z][a-z]+ token matched stopwords like "the"/"new".
MONTHS = (r"(?:January|February|March|April|August|September|October|November|"
          r"December|June|July|Sept|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|"
          r"Nov|Dec)")

# A settled-price anchor must not accept the first endpoint of a range.
NOT_RANGE = r"(?!\s*(?:to|and|[-\u2013])\s*\d+(?:[.,]\d+)?\s*%)"

# name -> (pattern, strength). "strong" patterns carry an explicit anchor
# phrase; "weak" ones are fallbacks and are always downgraded to low.
TIER2_PATTERNS = {
    "expected_loss": [
        (r"(?:initial )?expected loss of (?:approximately |around |about )?(\d+(?:[.,]\d+)?\s*%)", "strong"),
        # A % followed by of/for is a SHARE of the expected loss ("New York
        # 42.7% of expected losses", "99.55% for the Class A notes"), not the
        # loss itself. Only the weak fallback needs the guard: the strong
        # forms put "of" before the number.
        # ...and "lines contribute the largest percentage to the deals expected
        # loss, at 61.3%" / "Area B contributes 22.6%" are CONTRIBUTIONS to the
        # EL, not the EL. Any contribution wording between the cue and the
        # number disqualifies the capture.
        (r"expected loss(?:(?!contribut)[^.%]){0,30}?(\d+(?:[.,]\d+)?\s*%)"
         r"(?!\s*(?:of|for)\b)", "weak"),
    ],
    "attachment_probability": [
        (r"attachment probability (?:for the notes )?(?:of|is|at|to be) "
         r"(?:approximately |around |about |said to be )?(\d+(?:[.,]\d+)?\s*%)", "strong"),
        # Artemis sometimes writes "attachment point of 2.47%" for the
        # probability (Finca). A percentage is never a monetary point.
        (r"attachment point (?:at|of) (\d+(?:[.,]\d+)?\s*%)", "weak"),
    ],
    "exhaustion_probability": [
        (r"exhaustion probability of (?:approximately |around )?(\d+(?:[.,]\d+)?\s*%)", "strong"),
    ],
    "attachment_point": [
        (r"attach(?:es|ment)?(?: point)? (?:at|of) ([$\u20ac\u00a3][\d,.]+\s*(?:million|billion|m|bn)?)", "strong"),
    ],
    # Only settled-price anchors live here. The old weak fallback
    # `(?:spread|coupon)[^.%]{0,40}?([\d.]+%)` grabbed whichever percentage sat
    # nearest the word and was indistinguishable from a correct hit, so it is
    # deleted rather than repaired: an honest None beats a plausible wrong
    # number. Guidance ranges belong in price_guidance / spread_history.
    "spread_risk_margin": [
        (r"(?:pricing|spread)[^.%]{0,60}?settled[^.%]{0,60}?at (\d+(?:[.,]\d+)?\s*%)", "strong"),
        (r"priced to pay (?:investors )?an? (?:initial )?risk (?:margin|interest spread) of (\d+(?:[.,]\d+)?\s*%)" + NOT_RANGE + r"", "strong"),
        # "settled to offer investors a yield of 2.25%" (Lion I)
        (r"(?:settled|priced|closed) to (?:offer|pay) (?:investors )?an? (?:initial )?"
         r"(?:yield|coupon|spread|risk margin) of (\d+(?:[.,]\d+)?\s*%)" + NOT_RANGE + r"", "strong"),
        (r"final(?:ised|ized)? (?:pricing|spread|risk margin)[^.%]{0,30}?(\d+(?:[.,]\d+)?\s*%)", "strong"),
        # Settlement language first. "guide pricing of 11.25% to 12.25%" used to
        # match the generic form and return the range's LOWER BOUND as if it
        # were the settled spread; the lookahead now rejects range endpoints.
        (r"(?:pricing|spread)[^.%]{0,60}?settled[^.%]{0,40}?at (\d+(?:[.,]\d+)?\s*%)", "strong"),
        (r"(?:pricing|spread)[^.%]{0,60}?fixed at (\d+(?:[.,]\d+)?\s*%)", "strong"),
        # "priced at 91.5% of the original principal amount" is a DISCOUNT
        # PRICE, not a spread. Reject when the percent is of principal/par/face.
        (r"(?:priced|pricing) (?:at|of) (\d+(?:[.,]\d+)?\s*%)"
         r"(?!\s*(?:to|and|[-\u2013])\s*\d+(?:[.,]\d+)?\s*%)"
         r"(?!\s*of\s+(?:the\s+)?(?:original\s+)?(?:principal|par|face))", "strong"),
        # Every settled-price anchor rejects a range endpoint. "coupon of
        # 2.25% to 2.5%" returned 2.25% -- right on Lion I by luck only.
        (r"(?:initial )?risk (?:margin|interest spread) of (\d+(?:[.,]\d+)?\s*%)" + NOT_RANGE + r"", "strong"),
        (r"priced to pay (?:investors )?a spread of (\d+(?:[.,]\d+)?\s*%)" + NOT_RANGE + r"", "strong"),
        (r"coupon of (\d+(?:[.,]\d+)?\s*%)" + NOT_RANGE + r"", "strong"),
    ],
    "price_guidance": [
        (r"guidance[^.]{0,80}?(\d+(?:[.,]\d+)?\s*%\s*(?:to|and|[-–])\s*\d+(?:[.,]\d+)?\s*%)", "strong"),
    ],
    "maturity_date": [
        # Closed month vocabulary: an open [A-Z][a-z]+ token happily matched
        # stopwords ("this new 2024", "the 2024") and filled the field with
        # nonsense at medium confidence. A fixed alternation cannot.
        (r"matur\w+[^.]{0,40}?(" + MONTHS + r"\s+\d{4})", "strong"),
    ],
    # NOTE: \d+ does not cross a decimal point, so "a 12.5-year term" matched
    # the "5" and reported a 5-year term. Ground-truth labelling caught this;
    # no invariant could, because 5 years is a perfectly plausible term.
    "term_length": [
        # "a three-year term" puts the number *before* the anchor, so the
        # original forward-looking pattern could never see it.
        (r"((?:\w+|\d+(?:\.\d+)?)[-\s](?:year|month)s?)\s+term", "strong"),
        (r"term of ((?:\w+|\d+(?:\.\d+)?)[-\s](?:year|month)s?)", "strong"),
        (r"(?:term|covering|run(?:ning)? across)[^.]{0,30}?"
         r"((?:\w+|\d+(?:\.\d+)?)[-\s](?:hurricane seasons|wind seasons|years|year))", "strong"),
    ],
    "payout_floor": [
        (r"minimum of (\d+(?:[.,]\d+)?\s*%)[^.]{0,40}principal", "strong"),
    ],
}

# Resize vocabulary, learned the hard way: the first draft looked only for
# "upsiz|increas|target size" and missed "now targeting", "grew in size by
# two-thirds", "set its sights on the upper-end issuance size".
RESIZE_RE = re.compile(
    r"upsiz|downsiz|increas|decreas|reduc|target|grew|grow|lift|rais|expand|"
    r"secur|set its sights|now seeking|doubl|shrank|shrunk|upper-end|lower-end",
    re.IGNORECASE)

# A money figure only counts as a deal size if its own sentence talks about
# sizing. "$10m of limit was ceded per line of business" is a treaty term, not
# a launch size, and previously produced a bogus +585% upsize.
SIZING_CTX_RE = re.compile(
    r"tranche|offering|issuance|target|seeking|notes|size|sponsorship|"
    r"protection|upsiz|secured|priced|cat bond|deal", re.IGNORECASE)

# A deal-level size state must not be a component's size. Two discriminators,
# both learned from real pages:
#   class-scoped   "$100 million class A variable-rate notes" (Atlantic) and
#                  "The Class D tranche ... grew to $300 million" (Kilimanjaro)
#                  are tranche facts; taking them as the deal state produced a
#                  +200% phantom launch and hid Kilimanjaro's real $625m update.
#   enumerated     "Two tranches, one of $25m and one of $20m" (Mosaic) lists
#                  components with no total; the first is not the deal size.
# Note the word "tranche" alone is NOT a discriminator: Kilimanjaro's genuine
# launch reads "comes out of the blocks at $300m in size, split into two
# tranches", which is deal-scoped despite naming them.
CLASS_SCOPED_RE = re.compile(r"\bClass\s+[A-Z0-9]", re.IGNORECASE)

# Money governed by a loss-level noun is never a SIZE. Finca's "$15 million
# event deductible" became the deal's launch size and a +400% phantom upsize.
# Checked LOCALLY around the amount: a sentence-level test is useless because
# that sentence also says "notes" and "protection".
LOSS_LEVEL_RE = re.compile(
    r"deductible|attachment|attaches|exhaust|franchise|retention|"
    r"limit per|per[- ]event limit|trigger point|term loan",
    re.IGNORECASE)
# "a $2.5 billion layer" / "this higher layer being $100m" are layer widths,
# not sizes. Checked in a TIGHT window: a +-45 test on "layer" vetoed Citrus's
# genuine "$50m of notes, but this higher layer ..." sentence.
LAYER_RE = re.compile(r"\b(?:layer|tower)\b", re.IGNORECASE)

# "did not change in size" matched RESIZE_RE (change, size) and was accepted as
# evidence FOR a resize. Negation must be checked before corroboration.
NEGATED_RESIZE_RE = re.compile(
    r"\b(?:did not|does not|will not|has not|have not|was not|were not)\s+"
    r"(?:change|increase|decrease|grow|upsiz\w*|alter\w*)|\bunchanged\b|"
    r"\bremains?\s+(?:at|unchanged|the same)\b|"
    r"\bremained?\s+(?:at|the same)\b|\bsame size\b", re.IGNORECASE)


TRANCHE_LAYER_RE = re.compile(
    r"Class\s+[A-Z0-9-]{1,4}\s+layer|layer\s+tranche", re.IGNORECASE)


def _governed_by_loss_level(text, start, end):
    """True if this amount is NOT usable as a size.

    Was a veto list -- deductible, attachment, exhaust, layer, term loan --
    grown one entry per reviewer-found instance. Measured on 60 RANDOM deals
    the classes recurred anyway: Alamo's "$2.6 billion" was still read as a
    tranche size after two rounds of widening, because a veto only ever covers
    the phrasing that prompted it.

    Now asks the classifier what the amount IS and accepts only a size or an
    unclassified amount. `unknown` is deliberately admitted: the existing
    discovery machinery has better recall than any single cue list and this
    must not make it worse. The veto regexes are kept as a belt-and-braces
    first check since they are strictly narrower than the classifier.
    """
    window = text[max(0, start - 45):end + 45]
    # "layer" is overloaded: "$2.5 billion layer" is a loss level, but Artemis
    # also calls a tranche itself a layer -- "the Class B layer tranche remains
    # with a target of $25 million". Bound to a class label, with no other
    # loss-level word present, it is a tranche noun and the amount is a size.
    # Checked FIRST because the classifier branch below also cues on "layer".
    if (TRANCHE_LAYER_RE.search(window)
            and not re.search(r"deductible|attach|exhaust|retention",
                              window, re.IGNORECASE)):
        return False
    if LOSS_LEVEL_RE.search(window):
        return True
    if (LAYER_RE.search(text[end:end + 12])
            or LAYER_RE.search(text[max(0, start - 25):start])):
        return True
    kind, _cue, _conf = classify(text, start, end)
    return kind not in ("size", "unknown")
AGGREGATE_RE = re.compile(r"\btotal|combined|aggregate|altogether|in all\b",
                          re.IGNORECASE)

# Source placeholders. Artemis writes these where it has no data; they are
# nulls wearing a value's clothes and previously sat in the table at HIGH
# confidence, making "the source is silent" indistinguishable from "our parser
# worked". Confidence stays high -- we are confident the source said nothing.
PLACEHOLDERS = {"unknown", "?", "n/a", "na", "-", "\u2013", "\u2014",
                "tbc", "tbd", "not issued", "none", "not known"}

# "Not issued" is not missing data -- it is a terminal fact. Collapsing it into
# the same None as "Unknown" let _size_single read the absent Tier-1 final as
# permission to promote a prose TARGET to issued principal, so cancelled
# Gateway Re 2024-3 reported $100m of principal.
TERMINAL_STATUS = {"not issued": "not_issued"}
CANCELLED_RE = re.compile(
    r"\b(?:has been cancelled|was cancelled|been (?:pulled|withdrawn)|"
    r"was withdrawn|did not (?:proceed|complete)|was not completed|"
    r"not to proceed|will not (?:be issued|proceed))\b", re.IGNORECASE)

PRIVATE_RE = re.compile(
    r"\bprivate(?:ly)?[- ](?:placed|placement|cat(?:astrophe)? bond|ILS|offering|"
    r"deal|transaction|issuance)|\bSection 4\(2\)|\bunregistered private|"
    r"\bsegregated account|\btransformer\b", re.IGNORECASE)

# core fields are expected on essentially every deal, so a low fill rate is a
# bug. opportunistic fields are published only on a minority (mostly World Bank
# and public-entity issues); 0/8 there is not a defect and should not be
# triaged as one.
FIELD_TIER = {
    "payout_structure": "opportunistic", "investor_distribution": "opportunistic",
    "geographic_distribution": "opportunistic", "oversubscribed": "opportunistic",
    "payout_floor": "opportunistic", "exhaustion_probability": "opportunistic",
    "attachment_point": "opportunistic", "price_guidance": "opportunistic",
}

WORD_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
            "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twelve": 12}

# ONE money grammar. Symbols, prefixed symbols (C$, NZ$, US$) and ISO codes as
# words: Operational Re is written entirely in "CHF105m", Crystal Credit in
# "EUR 252 million", and "C$115m" used to read as USD. Every other money regex
# in the package is built from CCY / MONEY_RE so they cannot drift apart.
CCY = (r"(?<![A-Za-z])(?:C\$|NZ\$|A\$|US\$|HK\$|S\$|[$\u20ac\u00a3\u00a5]|"
       r"EUR|USD|GBP|CHF|JPY|AUD|CAD|NZD)")
MONEY_RE = re.compile(CCY + r"\s?[\d,]+(?:\.\d+)?\s*(?:million|billion|bn|m\b|b\b)?", re.I)
MULTIPLIER = {"m": 1e6, "million": 1e6, "bn": 1e9, "b": 1e9, "billion": 1e9}
CCY_CODE = {"$": "USD", "US$": "USD", "USD": "USD", "\u20ac": "EUR", "EUR": "EUR",
            "\u00a3": "GBP", "GBP": "GBP", "\u00a5": "JPY", "JPY": "JPY",
            "CHF": "CHF", "C$": "CAD", "CAD": "CAD", "NZ$": "NZD", "NZD": "NZD",
            "A$": "AUD", "AUD": "AUD", "HK$": "HKD", "S$": "SGD"}
# "(approx $687m)", "(EUR 80m)", "(US$222 million)": a conversion of the amount
# just before it, never a second amount. Stripped before amounts are counted.
PAREN_CONVERSION_RE = re.compile(
    r"\((?:approx\.?|around|about|roughly|circa|c\.|~|US|or)?\s*" + CCY +
    r"\s?[\d,.]+\s*(?:million|billion|bn|m|b)?[^()]{0,20}\)", re.I)
# ISO 4217 code of the state's headline currency, used to pick the right
# amount when a sentence quotes both a native figure and its conversion.
TRANCHE_ONLY = {"expected_loss", "attachment_probability", "exhaustion_probability",
                "spread_risk_margin", "conditional_severity"}


def _clean(t):
    return re.sub(r"\s+", " ", t).strip()


def _field(value=None, confidence=None, method=None, evidence=None, flags=None):
    return {
        "value": value,
        "confidence": confidence,
        "method": method,
        "evidence": evidence,
        "flags": flags or ([] if value is not None else ["not_found"]),
    }


def _pct_to_float(raw):
    """Percentage string -> float, honouring a decimal comma.

    Artemis is inconsistent: "an expected loss of 2,23%" appears alongside
    "2.92%" on the same page (Kilimanjaro II 2017-1). The old grammar
    `[\d.]+%` captured only "23" from that, reporting EL=23% against AP=2.92%
    -- arithmetically impossible, and caught by the EL<=AP invariant.

    Widening the grammar alone made it worse: the captured "2,23" then went
    through `float(re.sub(r"[^\d.]", "", ...))`, which DELETES the comma and
    yields 223.0. Capture and conversion had to change together.

    A percentage in this corpus never carries a thousands separator, so a comma
    is always a decimal point.
    """
    if raw is None:
        return None
    m = re.search(r"\d+(?:[.,]\d+)?", str(raw))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", "."))
    except ValueError:
        return None


def _money_to_number(text):
    """Rough numeric value of a money string, for comparison/flagging only."""
    # Require a leading digit: "[\d,]+" matched a bare comma, so a stray "$,"
    # reached float("") and crashed the parse. Permissive numeric grammars were
    # flagged in review as a class; this is the instance that bit.
    m = re.search(r"(\d[\d,]*(?:\.\d+)?)\s*(million|billion|bn|m|b)?", text, re.I)
    if not m:
        return None
    try:
        num = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    unit = (m.group(2) or "").lower()
    return num * MULTIPLIER.get(unit, 1.0)


def _normalise_placeholder(value):
    """Map a source placeholder to None, preserving the raw string."""
    if value is not None and value.strip().lower().rstrip(".") in PLACEHOLDERS:
        return None, ["source_placeholder:%s" % value.strip()]
    return value, []


def _currency(text):
    """ISO code of the first currency token in a money string, or None."""
    m = re.search(CCY, text or "", re.I)
    return CCY_CODE.get(m.group(0).upper(), m.group(0).upper()) if m else None


def _term_to_years(text):
    """'three-year' / 'four hurricane seasons' / '3 years' -> int years."""
    if not text:
        return None
    m = re.match(r"(\w+|\d+)", text.strip())
    if not m:
        return None
    tok = m.group(1).lower()
    return int(tok) if tok.isdigit() else WORD_NUM.get(tok)


def _add_years(month_year, years):
    m = re.match(MONTHS + r"\s+(\d{4})", month_year or "", re.IGNORECASE)
    if not m or years is None:
        return None
    return f"{m.group(0).split()[0]} {int(m.group(1)) + years}"


UPDATE_HEAD_RE = re.compile(
    r"(\bUpdate\s*\d*\s*(?:\([^)]{0,40}\)|,[^:\n]{0,30})?\s*:)", re.IGNORECASE)
UPDATE_DATE_RE = re.compile(
    MONTHS + r"\.?\s+(?:\d{1,2}(?:st|nd|rd|th)?,?\s+)?\d{4}|\d{1,2}(?:st|nd|rd|th)?\s+"
    + MONTHS + r"\.?\s+\d{4}", re.IGNORECASE)


def _segment_prose_dated(prose):
    """([(label, text)], {label: date_text}) -- launch, then each Update block.

    Artemis writes "Update:", "Update 2:", "Update 2 (May 4th 2016):" and
    "Update, May 2018:". Labels are POSITIONAL ordinals (update_1, update_2 ..)
    so they sort and never collide; the heading's date, when it carries one,
    is returned separately rather than mangled into the label.
    """
    parts = UPDATE_HEAD_RE.split(prose)
    segments, dates = [("launch", parts[0])], {}
    for i in range(1, len(parts) - 1, 2):
        head = _clean(parts[i]).rstrip(":")
        label = "update_%d" % len(segments)
        m_d = UPDATE_DATE_RE.search(head)
        dates[label] = _clean(m_d.group(0)) if m_d else None
        segments.append((label, parts[i + 1]))
    keep = [(label, text) for label, text in segments if _clean(text)]
    return keep, {k: v for k, v in dates.items() if k in dict(keep)}


def _segment_prose(prose):
    """Split narrative into ordered states: launch, then each Update block."""
    return _segment_prose_dated(prose)[0]


# ---------------------------------------------------------------------------
# Sentence segmentation
#
# `sentences(text)` fires on every abbreviation: 37 of 409 split
# points across the cached corpus sit inside "U.S.", "Ltd." or "Inc.". Every
# sentence-scoped rule -- label scoping, sizing context, backward-reference
# detection, stated-count validation, sibling auditing -- then runs on
# fragments. One helper, used everywhere, so the definition of "sentence" is
# the same in all of them.
#
# A blanket "never split after Ltd." is wrong: "Windmill I Re Ltd. (Series
# 2013-1)" is a continuation but "Radnor Re 2020-2 Ltd. The SPI has issued..."
# is a genuine boundary. So company suffixes split only before a new uppercase
# subject, while U.S./U.K./D.C. never split -- "U.S. Virgin Islands" and
# "U.S. Treasury" are far more common here than a sentence starting after them.
# ---------------------------------------------------------------------------

ALWAYS_NONTERMINAL = re.compile(
    r"(?:^|\s)(?:U\.S|U\.K|D\.C|N\.V|S\.A|e\.g|i\.e)\.$", re.IGNORECASE)
SUFFIX_NONTERMINAL = re.compile(
    r"(?:^|\s)(?:Inc|Ltd|Co|Cos|Corp|plc|No|St|Mr|Ms|Dr|approx|Bros)\.$",
    re.IGNORECASE)

_SPAN_CACHE = {}


def _sentence_spans(text):
    """[(start, end)] of sentences, abbreviation-aware."""
    if text in _SPAN_CACHE:
        return _SPAN_CACHE[text]
    spans, start = [], 0
    for m in re.finditer(r"\.\s+", text):
        head = text[start:m.start() + 1]
        nxt = text[m.end():m.end() + 1]
        if ALWAYS_NONTERMINAL.search(head):
            continue
        if SUFFIX_NONTERMINAL.search(head) and not nxt.isupper():
            continue  # "Ltd. (Series ..." / "Ltd. catastrophe ..." continues
        spans.append((start, m.start() + 1))
        start = m.end()
    if start < len(text):
        spans.append((start, len(text)))
    if len(_SPAN_CACHE) < 64:
        _SPAN_CACHE[text] = spans
    return spans


def sentences(text):
    """Sentences of text, abbreviation-aware. The one splitter to use."""
    return [text[a:b] for a, b in _sentence_spans(text or "") if text[a:b].strip()]


def _sentence_at(text, pos):
    """The sentence containing character offset `pos`."""
    for a, b in _sentence_spans(text):
        if a <= pos < b:
            return text[a:b]
    return text


def _series_tokens(text):
    """Series identifiers like 2024-1 / 2015-2 mentioned in text."""
    return set(re.findall(r"\b((?:19|20)\d\d-\d+[A-Za-z]?)\b", text or ""))


def _is_backward_reference(sentence, issue_year, own_series=frozenset()):
    """True if the sentence cites a year earlier than this deal's issuance.

    Artemis prose compares a deal to its predecessors ("the notes issued by
    Ursa Re in 2014, which priced at 5%"; "that maturing 2017 Windmill Re cat
    bond was also only roughly $46 million"). Figures in such a sentence belong
    to a different deal.

    Direction matters: only *backward* references are comparisons. Forward
    years are legitimate (maturity, term end) -- an earlier symmetric version
    of this rule flagged Jamaica's "May 2030" maturity and produced nothing but
    false positives.
    """
    # A sentence naming a DIFFERENT series of the same programme is about
    # another deal, whatever its year. This is the same-year case the year
    # test cannot see (Citrus Re 2014-2 citing 2014-1, Gateway 2024-3 citing
    # 2024-1).
    # Strip parenthetical asides first. Comparative references to sibling deals
    # live there -- ResRe 2026 says its deductible "is higher than the $50
    # million in USAA's 2025-1 aggregate cat bonds" -- and excluding the whole
    # sentence on that basis threw away THIS deal's $150m launch size with it.
    main_clause = re.sub(r"\([^)]*\)", " ", sentence)
    cited = _series_tokens(main_clause)
    if cited and own_series and (cited - set(own_series)):
        return True
    if not issue_year:
        return False
    # Strictly earlier than the issue year. The previous `< issue_year - 1`
    # let the immediately preceding year through, so Residential Reinsurance
    # 2020 adopted the 2019-1 bond's 8.25% coupon as its own.
    #
    # Judged on the main clause for the same reason as the series test: a
    # parenthetical comparison to an older deal must not condemn the sentence
    # that carries THIS deal's terms.
    return any(int(y) < issue_year
               for y in re.findall(r"\b(19\d\d|20\d\d)\b", main_clause))


# Percent fields where a "medical benefit ratio" percentage is a different
# unit entirely (Vitality's health deals attach at ~96-102% MBR) and must not
# be captured as a probability or a loss.
BENEFIT_RATIO_RE = re.compile(r"benefit ratio", re.IGNORECASE)
RATIO_GUARDED = {"expected_loss", "attachment_probability", "exhaustion_probability"}


def _apply_patterns(name, patterns, text, issue_year=None, own_series=frozenset()):
    """Run every pattern, collect distinct candidates, and grade the result."""
    hits, strength_used = [], None
    dropped = []
    for pattern, strength in patterns:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            value = _clean(m.group(1))
            if (name in RATIO_GUARDED
                    and BENEFIT_RATIO_RE.search(text[max(0, m.start() - 45):m.start()])):
                dropped.append(value + " (benefit ratio)")
                continue
            # "lines of business contribute the largest percentage to the
            # deals expected loss, at 61.3%": contribution wording BEFORE the
            # cue, so the between-cue-and-number guard cannot see it.
            if (name == "expected_loss"
                    and re.search(r"contribut", text[max(0, m.start() - 80):m.start()],
                                  re.IGNORECASE)):
                dropped.append(value + " (contribution share)")
                continue
            if _is_backward_reference(_sentence_at(text, m.start()), issue_year, own_series):
                dropped.append(value)
                continue
            if value not in [h[0] for h in hits]:
                start, end = max(0, m.start() - 60), min(len(text), m.end() + 60)
                hits.append((value, _clean(text[start:end]), strength))
        if hits and strength_used is None:
            strength_used = strength
            break  # a strong tier matched; don't fall through to weak patterns

    if not hits:
        f = _field(flags=["not_found"])
        if dropped:
            f["flags"].append("foreign_deal_reference_excluded=%s" % dropped)
        return f

    value, evidence, strength = hits[0]
    flags = []
    confidence = "medium" if strength == "strong" else "low"
    if strength == "weak":
        flags.append("weak_pattern")
    if len(hits) > 1:
        confidence = "low"
        flags.append("multiple_candidates")
        flags.append(f"candidates={[h[0] for h in hits]}")
    if dropped:
        flags.append("foreign_deal_reference_excluded=%s" % dropped)
    return _field(value, confidence, f"regex:{name}:{strength}", evidence, flags)


def parse_deal(html, deal_url=None):
    soup = BeautifulSoup(html, "lxml")
    main = soup.find("main") or soup
    record, page_flags = {}, []

    h1 = main.find("h1")
    record["deal_name"] = _field(
        _clean(h1.get_text()) if h1 else None, "high" if h1 else None, "h1")
    record["deal_url"] = _field(deal_url, "high", "input")

    # ---- Tier 1 ----------------------------------------------------------
    glance = main.find(lambda t: t.name in ("h2", "h3")
                       and "at a glance" in t.get_text().lower())
    ul = glance.find_next("ul") if glance else None
    for key in TIER1_KEYS:
        record[key] = _field(flags=["not_found"])
    extra_fields = {}

    if ul is None:
        page_flags.append("no_at_a_glance_block")
    else:
        for li in ul.find_all("li"):
            label_el = li.find("strong") or li.find("b")
            if not label_el:
                continue
            label = _clean(label_el.get_text()).rstrip(":").lower()
            value = _clean(li.get_text()[len(label_el.get_text()):].lstrip(" :")) or None
            key = LABEL_MAP.get(label)
            if key is None:
                if label in IGNORED_LABELS:
                    continue
                extra_fields[label] = value
                page_flags.append(f"unmapped_label:{label}")
            else:
                normalised, ph_flags = _normalise_placeholder(value)
                f = _field(
                    normalised,
                    "high" if value else None,  # confident the source is silent
                    "tier1_label", label,
                    ph_flags or ([] if value else ["empty_label_value"]))
                f["raw_value"] = value
                record[key] = f

    # ---- Tier 2 ----------------------------------------------------------
    details = main.find(lambda t: t.name in ("h2", "h3")
                        and "full details" in t.get_text().lower())
    prose_parts, node = [], details
    while node is not None:
        node = node.find_next_sibling()
        if node is None or node.name == "h2":
            break
        prose_parts.append(node.get_text(" ", strip=True))
    prose = _clean(" ".join(prose_parts))
    if not prose:
        page_flags.append("no_full_details_prose")

    issue_year = None
    m_iy = re.search(r"(19\d\d|20\d\d)", record["date_of_issue"]["value"] or "")
    if m_iy:
        issue_year = int(m_iy.group(1))
    own_series = _series_tokens(record["deal_name"]["value"] or "") | _series_tokens(deal_url or "")

    for name, patterns in TIER2_PATTERNS.items():
        record[name] = (_apply_patterns(name, patterns, prose, issue_year, own_series)
                        if prose else _field())

    segments, segment_dates = (_segment_prose_dated(prose) if prose else ([], {}))
    # Guidance, attachment point and the spread series are TRANCHE facts. On a
    # multi-tranche page the deal-level column silently held tranche 1's value
    # (IBRD 111-112: guidance = Class B's 12.25-13%, spread = Class A's 6.9%).
    n_windows = len(_tranche_windows(prose)) if prose else 0
    if n_windows > 1:
        for name in ("price_guidance", "attachment_point"):
            record[name] = _field(flags=["not_found", "tranche_level_only:n=%d" % n_windows])
    headline_ccy = _currency(record["size"]["value"] or "")

    # ---- Time series: how terms moved while marketing --------------------
    size_history, skipped_backref = [], 0
    for label, text in segments:
        for sentence in sentences(text):
            if _is_backward_reference(sentence, issue_year, own_series):
                if MONEY_RE.search(sentence):
                    skipped_backref += 1
                continue  # figure belongs to a predecessor deal
            if not SIZING_CTX_RE.search(sentence):
                continue  # money here is not a deal size
            if CLASS_SCOPED_RE.search(sentence):
                continue  # a tranche's size, not the deal's
            # "$90 million (EUR 80m)": one amount and its conversion. Count
            # the native figure only, but prefer whichever currency the
            # Tier-1 headline uses so launch and final are comparable.
            conversions = [_clean(x.group(0)) for x in PAREN_CONVERSION_RE.finditer(sentence)]
            main = PAREN_CONVERSION_RE.sub(" ", sentence)
            m_first = MONEY_RE.search(main)
            if m_first and _governed_by_loss_level(main, m_first.start(),
                                                   m_first.end()):
                continue  # a deductible/attachment level, not a size
            amounts = [x for x in MONEY_RE.findall(main)
                       if (_money_to_number(x) or 0) >= 1e6]
            kind = "stated"
            m_rng = SIZE_RANGE_RE.search(main)
            low = _amount_group(m_rng) if m_rng else None
            g = next((i for i in range(1, m_rng.re.groups + 1) if m_rng.group(i)), 1) if m_rng else 1
            if (low and (_money_to_number(low) or 0) >= 1e6
                    and not _governed_by_loss_level(main, m_rng.start(g), m_rng.end(g))):
                m, kind = m_rng, "range_low"      # low end is the launch figure
                value = _clean(low)
            else:
                if len(amounts) > 1 and not AGGREGATE_RE.search(main):
                    continue  # components enumerated with no stated total
                m = MONEY_RE.search(main)
                if not (m and (_money_to_number(_clean(m.group(0))) or 0) >= 1e6):
                    continue
                value = _clean(m.group(0))
                if re.search(r"up to\s*$", main[max(0, m.start() - 8):m.start()], re.I):
                    kind = "cap"
            if conversions and headline_ccy and _currency(value) != headline_ccy:
                alt = next((MONEY_RE.search(c).group(0) for c in conversions
                            if _currency(c) == headline_ccy), None)
                if alt:
                    value, kind = _clean(alt), kind + ":converted"
            size_history.append({"state": label, "value": value, "kind": kind})
            break
    # Capital raised beside the notes. Merna's Tier-1 "$1.18bn" is $1,058.6m of
    # notes PLUS $122m of term loans; IBRD 111-112 sold $105m of swaps beside
    # $320m of notes. The headline is not always note principal, and
    # parts-vs-whole must know which instruments it is summing.
    other = []
    for sentence in sentences(prose) if prose else []:
        if _is_backward_reference(sentence, issue_year, own_series):
            continue
        for m_o in MONEY_RE.finditer(sentence):
            after = sentence[m_o.end():m_o.end() + 40]
            # "$94 million tranche A term loan", "$105 million of pandemic
            # linked catastrophe swaps" -- but NOT "$155 million Three tranches
            # of term loan notes were also issued", which is Class C's size.
            m_k = re.match(r"\s*(?:tranche\s+[A-Z]\s+)?(?:of\s+)?"
                           r"(?:(?!tranches|classes|notes)[\w-]+\s+){0,3}?(term loans?|swaps?)\b", after, re.I)
            if m_k and (_money_to_number(m_o.group(0)) or 0) >= 1e6:
                kind = "term_loan" if "loan" in m_k.group(1).lower() else "swap"
                other.append({"kind": kind, "value": _clean(m_o.group(0))})
    record["other_instruments"] = _field(
        other or None, "low" if other else None, "regex:instrument_noun_after_amount",
        "%d mention(s)" % len(other) if other else None,
        ["not_note_principal"] if other else ["not_found"])
    sh_flags = [] if size_history else ["not_found"]
    if skipped_backref:
        sh_flags.append("foreign_deal_reference_excluded=%d_sentence(s)" % skipped_backref)
    record["size_history"] = _field(
        size_history or None, "medium" if size_history else None,
        "segmented_prose", f"{len(segments)} state(s)", sh_flags)

    spread_history = []
    for label, text in segments:
        for pattern, kind in [
            (r"priced to pay (?:investors )?an? (?:initial )?risk margin of (\d+(?:[.,]\d+)?\s*%)", "priced"),
            (r"guidance[^.]{0,80}?(\d+(?:[.,]\d+)?\s*%\s*(?:to|and|[-–])\s*\d+(?:[.,]\d+)?\s*%)", "guidance"),
            (r"(?:initial )?risk margin of (\d+(?:[.,]\d+)?\s*%)" + NOT_RANGE, "risk_margin"),
        ]:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                spread_history.append(
                    {"state": label, "kind": kind, "value": _clean(m.group(1))})
                break
    record["spread_history"] = _field(
        spread_history or None, "medium" if spread_history else None,
        "segmented_prose", f"{len(segments)} state(s)",
        [] if spread_history else ["not_found"])

    # ---- Derived: what changed, how much, why ----------------------------
    final_size = record["size"]["value"]
    launch = next((s for s in size_history if s["state"] == "launch"), None)
    change = None
    if final_size and launch:
        a, b = _money_to_number(launch["value"]), _money_to_number(final_size)
        cur_a, cur_b = _currency(launch["value"]), _currency(final_size)
        if a and b and cur_a and cur_b and cur_a != cur_b:
            # Windmill II: launch quoted in USD, final in EUR. Comparing the
            # bare numbers produced a fictitious +11.1%.
            change = None
            page_flags.append(f"VIOLATION:size_currency_mismatch:{cur_a}vs{cur_b}")
        elif a and b and abs(a - b) / a > 0.01:
            reason = next(
                (_clean(t)[:200] for lbl, t in segments
                 if lbl != "launch" and RESIZE_RE.search(t)
                 and not NEGATED_RESIZE_RE.search(t)), None)
            if reason is None:
                # No explicit resize language anywhere: almost certainly the
                # "launch" figure was never a size at all. Refuse to invent it.
                page_flags.append("uncorroborated_size_change_suppressed")
            change = None if reason is None else {
                "size_at_launch": launch["value"],
                "size_final": final_size,
                "delta_abs": b - a,
                "delta_pct": round((b - a) / a * 100, 1),
                "direction": "upsized" if b > a else "downsized",
                "reason_evidence": reason,
            }
    record["size_change"] = _field(
        change, "medium" if change else None, "tier1_vs_tier2_launch",
        None,
        ["expected_launch_vs_final_gap"] if change else ["no_size_change_detected"])

    # ---- Validation: maturity must postdate issue -------------------------
    # Same shape as the EP <= EL <= AP check: a cheap cross-field ordering that
    # catches regex drift no single-field score can see.
    def _month_ord(text):
        if not text:
            return None
        m = re.search(MONTHS + r"\s+(\d{4})", text, re.IGNORECASE)
        if not m:
            return None
        month = re.match(MONTHS, m.group(0), re.IGNORECASE).group(0)[:3].lower()
        names = ["jan", "feb", "mar", "apr", "may", "jun",
                 "jul", "aug", "sep", "oct", "nov", "dec"]
        return int(m.group(1)) * 12 + names.index(month)

    issue_ord = _month_ord(record["date_of_issue"]["value"])
    mat_ord = _month_ord(record["maturity_date"]["value"])
    if issue_ord and mat_ord and mat_ord <= issue_ord:
        record["maturity_date"]["flags"].append("VIOLATION:maturity_not_after_issue")
        record["maturity_date"]["confidence"] = "low"

    # ---- Derived: layer severity -----------------------------------------
    # Attachment probability is P(layer is hit at all); EL is the average loss
    # across the whole distribution. So EL = AP x (mean fraction of the layer
    # lost when hit), which makes EL / AP the *conditional severity*: how much
    # of the layer typically burns once it attaches.
    #
    # Invariant: exhaustion_prob <= EL <= attachment_prob. EL above AP is
    # arithmetically impossible, so a violation means a mis-parse, not an
    # exotic structure -- exactly the case a confidence score must catch.
    def _pct(key):
        raw = record[key]["value"]
        if not raw:
            return None
        try:
            return _pct_to_float(raw)
        except ValueError:
            return None

    ap, el, ep = (_pct("attachment_probability"), _pct("expected_loss"),
                  _pct("exhaustion_probability"))
    RANK = {"high": 3, "medium": 2, "low": 1, None: 0}
    UNRANK = {3: "high", 2: "medium", 1: "low", 0: None}

    severity, sev_flags = None, []
    if ap and el and ap > 0:
        severity = round(el / ap, 4)
        sev_flags.append(f"conditional_severity={severity:.1%}_of_layer_burns_when_hit")
        if el > ap:
            sev_flags.append("VIOLATION:EL_exceeds_attachment_probability")
        if ep is not None and not (ep <= el <= ap):
            sev_flags.append("VIOLATION:expected_exhaustion<=EL<=attachment")

    # A derived value is never more trustworthy than its weakest input.
    conf = UNRANK[min(RANK[record["expected_loss"]["confidence"]],
                      RANK[record["attachment_probability"]["confidence"]])]
    if any(f.startswith("VIOLATION") for f in sev_flags):
        conf = "low"
    record["conditional_severity"] = _field(
        severity, conf if severity is not None else None,
        "derived:EL/attachment_probability",
        f"EL={record['expected_loss']['value']} AP={record['attachment_probability']['value']}",
        sev_flags or ["not_found"])

    # ---- Derived: scheduled maturity from issue + term --------------------
    # Many pages state a term but never a maturity date (FloodSmart: "across a
    # three-year term"). Issue + term is a sound inference, but it is a
    # *different fact* from a stated date, so it gets its own column and never
    # backfills maturity_date. It is also the SCHEDULED maturity: cat bonds
    # carry extension periods (often 24-36 months on indemnity deals) to allow
    # loss development, so final maturity can be materially later.
    years = _term_to_years(record["term_length"]["value"])
    derived_mat = _add_years(record["date_of_issue"]["value"], years)
    record["maturity_date_derived"] = _field(
        derived_mat, "low" if derived_mat else None,
        "derived:date_of_issue+term_length",
        f"{record['date_of_issue']['value']} + {record['term_length']['value']}",
        ["scheduled_not_final", "extension_period_not_modelled"]
        if derived_mat else ["not_found"])

    stated = record["maturity_date"]["value"]
    record["maturity_scheduled"] = _field(
        stated or derived_mat,
        record["maturity_date"]["confidence"] if stated
        else record["maturity_date_derived"]["confidence"],
        "stated" if stated else ("derived" if derived_mat else None))
    if stated and derived_mat and stated != derived_mat:
        record["maturity_scheduled"]["flags"].append(
            f"stated_derived_mismatch:{stated}!={derived_mat}")
        record["maturity_scheduled"]["confidence"] = "low"

    # ---- Narrative extras -------------------------------------------------
    for name, pattern in [
        ("tranche_structure", r"[^.]*\btranche[s]?\b[^.]*\."),
        ("payout_structure", r"[^.]*\bpayout[s]?\b[^.]*sliding scale[^.]*\."),
        ("investor_distribution", r"[^.]*(?:went to|distribution)[^.]*ILS funds[^.]*\."),
        ("geographic_distribution", r"[^.]*geographic distribution[^.]*\."),
    ]:
        m = re.search(pattern, prose, re.IGNORECASE) if prose else None
        record[name] = _field(
            _clean(m.group(0)) if m else None, "low" if m else None,
            f"sentence:{name}", None,
            ["sentence_not_parsed_to_fields"] if m else ["not_found"])

    record["oversubscribed"] = _field(
        True if prose and re.search(r"\boversubscribed\b", prose, re.I) else None,
        "medium" if prose and re.search(r"\boversubscribed\b", prose, re.I) else None,
        "keyword")

    raw_size = (record["size"].get("raw_value") or "").strip().lower()
    status = TERMINAL_STATUS.get(raw_size)
    if status is None and prose:
        # Deal-scoped only. "The higher risk Class 12 tranche ... will not be
        # issued at all" is a TRANCHE fact; reading it as a deal cancellation
        # marked the issued ResRe 2020 as never issued.
        for sent in sentences(prose):
            if CANCELLED_RE.search(sent) and not CLASS_SCOPED_RE.search(sent):
                status = "cancelled"
                break
    record["deal_status"] = _field(
        status or "issued",
        "high" if status else "medium",
        "tier1_raw+prose", raw_size or None,
        ["terminal_status"] if status else [])

    if status in ("not_issued", "cancelled"):
        # A deal that never issued has no maturity. Gateway 2024-3 reported
        # "Jun 2027" derived from a term it never started.
        for name in ("maturity_date_derived", "maturity_scheduled"):
            record[name] = _field(flags=["not_found", "no_maturity:%s" % status])

    # "Private" means the page SAYS so. Counting Tier-1 placeholders flagged
    # Merna (a rated 144A deal with a sparse 2007 summary box) as private and
    # missed Beazley ("private Section 4(2) cat bond"). The placeholder count
    # is still reported, as what it is: sparseness.
    placeholder_hits = [k for k in TIER1_KEYS
                        if any(str(x).startswith("source_placeholder")
                               for x in record[k]["flags"])]
    m_priv = PRIVATE_RE.search(prose) if prose else None
    record["deal_is_private"] = _field(
        True if m_priv else None, "medium" if m_priv else None,
        "keyword:private_placement",
        _clean(_sentence_at(prose, m_priv.start()))[:160] if m_priv else None,
        (["tier1_placeholders=%d" % len(placeholder_hits)] if placeholder_hits else [])
        + ([] if m_priv else ["not_found"]))

    # Derived entities from the verbatim agents cell. The cell is canonical
    # ("Willis Capital Markets & Advisory are sole structuring agent and
    # bookrunner.") but joins and labelling want the names alone. Strip the
    # role clause, then split coordinated names -- on " and " only, since "&"
    # binds inside a name.
    agents_raw = (record["placement_structuring_agents"].get("raw_value")
                  or record["placement_structuring_agents"]["value"] or "")
    ent = re.sub(r"\s+(?:are|is)\s+(?:the\s+)?(?:sole|joint)?\s*(?:structuring|"
                 r"placement|co-)?\s*(?:agents?|bookrunners?|managers?)\b.*$",
                 "", agents_raw).strip(" .")
    ents = ([e.strip(" .") for e in re.split(r",| and ", ent) if e.strip(" .")]
            if ent and ent.lower() not in ("unknown", "?") else [])
    record["agents_entities"] = _field(
        ents or None, "medium" if ents else None,
        "derived:tier1_cell", agents_raw[:80] or None,
        [] if ents else ["not_found"])

    record["_meta"] = {
        "page_flags": page_flags,
        "extra_fields": extra_fields,
        "prose_chars": len(prose),
        "prose_states": [s[0] for s in segments],
        "prose_state_dates": segment_dates,
        "field_tier": FIELD_TIER,
        "full_details_text": prose or None,
    }
    return record


def _report(record):
    order = [k for k in record if k != "_meta"]
    badge = {"high": "HIGH  ", "medium": "MEDIUM", "low": "LOW   ", None: "NONE  "}
    print(f"\n{'FIELD':<30} {'CONF':<7} VALUE / FLAGS")
    print("-" * 108)
    for key in order:
        f = record[key]
        val = f["value"]
        if isinstance(val, list):
            shown = f"{len(val)} states: " + " -> ".join(
                f"{d['state']}={d.get('value')}" for d in val)
        elif isinstance(val, dict):
            shown = (f"{val['size_at_launch']} -> {val['size_final']} "
                     f"({val['direction']} {val['delta_pct']:+}%)")
        else:
            shown = str(val)
        if len(shown) > 62:
            shown = shown[:59] + "..."
        warn = [x for x in f["flags"] if x != "not_found"]
        print(f"{key:<30} {badge[f['confidence']]:<7} {shown}")
        if warn:
            print(f"{'':<38} ! {'; '.join(warn)[:66]}")

    counts = {}
    for key in order:
        counts[record[key]["confidence"]] = counts.get(record[key]["confidence"], 0) + 1
    print("-" * 108)
    print("confidence mix:", {str(k): v for k, v in counts.items()})
    print("page flags:", record["_meta"]["page_flags"] or "none")
    print("prose states:", record["_meta"]["prose_states"])


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else (
        "https://www.artemis.bm/deal-directory/ibrd-car-jamaica-2026/")
    _report(parse_deal(fetch(url), deal_url=url))


# ---------------------------------------------------------------------------
# Tranche-level extraction
#
# EL, attachment/exhaustion probability and spread are properties of a
# *tranche*, not of a deal. Holding them in deal-level columns was a category
# error: on a 3-tranche deal the scalar silently reported tranche 1's number as
# the deal's. Splitting the record inverts the old failure -- `multiple
# candidates` stops being an error and becomes the signal that N tranches
# exist, and conditional severity finally divides an EL by an AP that is
# guaranteed to come from the same tranche.
# ---------------------------------------------------------------------------

# Anchored size phrasings. Bare "first money in the sentence" was too blunt:
# it read attachment points as sizes, so it needed an attach/exhaust sentence
# veto, which in turn discarded Kilimanjaro's Class E launch size because that
# sentence carries the size AND the attachment point. Matching the size idiom
# directly removes the need for the veto.
_M = r"(" + CCY + r"\s?[\d,.]+\s*(?:million|billion|bn|m)?)"
# "between $25m and $100m", "from $150 million to $200 million", "$150m to
# $250m of notes": a target SPAN. Its low end is a launch figure; neither end
# is ever a final. Group 1 = low end.
# A sizing word must govern the span: Citrus's "protection would run from
# $200m to $450m of its tower" is a layer, not a target.
SIZE_RANGE_RE = re.compile(
    r"(?:target\w*|aim\w*|seek\w*|secur\w*|sized?|set|offer\w*|issu\w*|rais\w*|expect\w*)\s+"
    r"(?:\w+\s+){0,3}?(?:between|from)\s+" + _M + r"\s+(?:and|to)\s+" + CCY + r"\s?[\d,.]+|"
    + _M + r"\s+(?:to|[-\u2013])\s+" + CCY + r"\s?[\d,.]+\s*(?:million|billion|bn|m)?"
    r"\s+(?:of|in)\s+(?:notes|size|cover|reinsurance|protection)\b",
    re.IGNORECASE)


def _amount_group(m):
    """The amount captured by a match whose pattern has alternatives."""
    return next((g for g in m.groups() if g), None)
# (pattern, kind). kind is what the idiom asserts about the amount:
#   range   a span; low end reported, never a final
#   priced  a settled figure ("priced to offer $225 million of notes")
#   stated  any other anchored size idiom
TRANCHE_SIZE_RES = [(re.compile(x, re.IGNORECASE), k) for x, k in (
    (SIZE_RANGE_RE.pattern, "range"),
    (r"priced\s+(?:to\s+offer|offering)\s+" + _M, "priced"),
    (r"(?:settled|finalis\w+|finaliz\w+|sized|closed)\s+(?:to|at|as)\s+" + _M, "priced"),
    (r"size of " + _M, "stated"),
    (_M + r"\s+in size", "stated"),
    (r"(?:grew|upsiz\w+|target\w+|offered|priced)"
     r"\s+(?:to|at|as)\s+(?:up to |between )?" + _M, "stated"),
    # "targeting at least $75 million", "aiming for $150m", "seeking $X"
    (r"(?:target\w*|aim\w*|seek\w*|sought)\s+(?:for\s+|at\s+least\s+|up\s+to\s+)?" + _M, "stated"),
    # "remains with a target of $25 million" -- Blue Halo's Class B stayed
    # invisible while the deal's upsized total leaked into its window.
    (r"target of " + _M, "stated"),
    (_M + r"\s+Class\s+[A-Z0-9]+", "stated"),
    (r"(?:tranche|notes)[^.]{0,40}?of " + _M, "stated"),
    # "$134,574,000 tranche of Class M-1 notes" -- amount precedes the noun.
    (_M + r"\s+tranche of", "stated"),
    # "targeted to secure $150 million in reinsurance", "$95 million of notes"
    (_M + r"\s+(?:of|in) (?:reinsurance|protection|cover(?:age)?|notes)\b", "stated"),
    (r"(?:secure|provide)\s+(?:up to |between )?" + _M, "stated"),
    # "will seek to issue a $75 million or larger tranche" (Finca)
    (r"(?:issue|issuing|sell|selling)\s+(?:a\s+|an\s+|up\s+to\s+|at\s+least\s+|roughly\s+|around\s+)?" + _M, "stated"),
)]

# Hyphenated form FIRST: mortgage ILS uses Class M-1A / M-1B / M-1C / M-2 /
# B-1, and a narrower pattern truncated "M-1A" to "M-1", silently collapsing
# five tranches into three on Radnor Re 2020-2.
# Case-insensitive: Artemis writes "class A variable-rate notes" lowercase on
# older pages (Atlantic & Western 2005), which a capitalised-only pattern
# silently dropped, collapsing a two-tranche deal into one.
CLASS_RE = re.compile(r"\bClass\s+([A-Z]{1,3}-\d+[A-Z]?|[A-Z]{1,3}\b|\d{1,2}\b)",
                      re.IGNORECASE)

# ...but "Class 3 Bermuda-based insurer" is a regulatory class, not a tranche.
# A label only counts if some occurrence sits next to note/tranche language.
CLASS_CONTEXT_RE = re.compile(
    r"(?:notes?|tranche|securities|bonds?)", re.IGNORECASE)

# A money amount immediately BEFORE a class label, or a rating immediately
# after it, is decisive evidence of a tranche on its own. Pages enumerate them
# that way -- "$159.8 million Class M-1A (DBRS rated BBB) $53.3 million Class
# M-1B (...)" -- with the word "tranche" appearing once at the head of the
# list. Requiring note/tranche wording near EVERY label dropped four of Home Re
# 2022-1's five classes.
CLASS_EVIDENCE_RE = re.compile(
    r"[$\u20ac\u00a3\u00a5][\d,.]+\s*(?:m|million|bn|billion)?\s*$",
    re.IGNORECASE)
CLASS_RATING_RE = re.compile(
    r"^\s*\(?(?:DBRS|Moody|Fitch|S&P|Standard|KBRA|AM Best)|^\s*\(?rated\b",
    re.IGNORECASE)

REGULATORY_CLASS_RE = re.compile(
    r"\s+(?:Bermuda|insurer|reinsurer|licen[cs]e|regulated|segregated)", re.IGNORECASE)

# Case-insensitivity admits ordinary English: "each class of notes" produced a
# tranche called "Class OF". Tranche identifiers are letters/digits, never words.
CLASS_STOPWORDS = {"OF", "THE", "AND", "FOR", "ARE", "WAS", "ITS", "ALL", "ANY",
                   "NEW", "ONE", "TWO", "NOT", "HAS", "CAN", "MAY", "BUT", "OUR",
                   "SIZE", "WAS", "HAD", "WILL"}

# The prose usually states its own structure. When we can find fewer tranches
# than it claims, say so loudly rather than reporting the shortfall as fact.
STATED_COUNT_RE = re.compile(
    r"(?<![\d-])\b(one|two|three|four|five|six|seven|eight|\d{1,2})\s+"
    r"(?:tranches|classes)\b", re.IGNORECASE)
COUNT_WORDS = WORD_NUM   # one vocabulary; validate.py imports it too

RISK_METRICS = ("expected_loss", "attachment_probability",
                "exhaustion_probability", "spread_risk_margin")
TRANCHE_PATTERNS = {
    "expected_loss": TIER2_PATTERNS["expected_loss"],
    "attachment_probability": TIER2_PATTERNS["attachment_probability"],
    "exhaustion_probability": TIER2_PATTERNS["exhaustion_probability"],
    "spread_risk_margin": TIER2_PATTERNS["spread_risk_margin"],
    "price_guidance": TIER2_PATTERNS["price_guidance"],
    "attachment_point": TIER2_PATTERNS["attachment_point"],
}


def _sentence_start(text, pos):
    for a, b in _sentence_spans(text):
        if a <= pos < b:
            return a
    return 0


def _clause_start(text, pos):
    """Start of the clause holding pos: after the previous '.' or ';'.

    Artemis writes the amount BEFORE the label, and often lists every tranche
    in one semicolon-separated sentence ("$79,832,000 Class M-1A Notes ...;
    $93,137,000 Class M-1B Notes ..."). Snapping only to sentence starts made
    every label after the first fall back to its raw offset, discarding the
    amount immediately before it -- four of Radnor's five sizes vanished, with
    no flag.
    """
    return max(_sentence_start(text, pos), text.rfind("; ", 0, pos) + 2)


def _tranche_windows(prose):
    """Group prose into one text window per Class label, in first-seen order.

    Windows start at the beginning of the *sentence* holding the label, not at
    the label itself: Artemis writes the size before the class name ("A $300
    million Class A tranche of notes"), so a label-anchored window swallowed the
    NEXT tranche's leading size and silently swapped sizes between tranches.
    EL / attachment / spread all follow the label, which is why only size was
    affected.
    """
    hits = list(CLASS_RE.finditer(prose))
    # Keep only labels that appear at least once beside note/tranche language,
    # and never a regulatory class: "Class 3 Bermuda-based insurer ... Kaith Re
    # Ltd. has issued a $14.94 million ... notes" is on every Seaside page.
    by_label = {}
    for m in hits:
        ident = m.group(1).upper()
        if ident in CLASS_STOPWORDS:
            continue
        if REGULATORY_CLASS_RE.match(prose, m.end()):
            continue
        by_label.setdefault("Class " + ident, []).append(m)
    real = set()
    for label, ms in by_label.items():
        for m in ms:
            window = prose[max(0, m.start() - 60):m.end() + 60]
            before = prose[max(0, m.start() - 30):m.start()]
            after = prose[m.end():m.end() + 30]
            if (CLASS_CONTEXT_RE.search(window)
                    or CLASS_EVIDENCE_RE.search(before)
                    or CLASS_RATING_RE.search(after)):
                real.add(label)
                break
    hits = [m for m in hits if "Class " + m.group(1).upper() in real]
    if not hits:
        return []

    # Snap each boundary back to its sentence start, unless that would collide
    # with the previous label (two labels in one sentence, e.g. "Class 14 and
    # Class 15"), in which case keep the raw label offset.
    starts = []
    for i, m in enumerate(hits):
        snapped = _clause_start(prose, m.start())
        if i and snapped <= starts[-1]:
            snapped = m.start()
        starts.append(snapped)

    windows, order = {}, []
    for i, m in enumerate(hits):
        label = "Class " + m.group(1).upper()
        end = starts[i + 1] if i + 1 < len(hits) else len(prose)
        if label not in windows:
            windows[label] = []
            order.append(label)
        if end > starts[i]:
            windows[label].append(prose[starts[i]:end])
    return [(label, " ".join(windows[label])) for label in order]


# ---------------------------------------------------------------------------
# Tranche resolution
#
# Shared context -> shared metric extraction -> ONE explicit branch on tranche
# count. The branch is real, not incidental:
#
#   single   the tranche IS the deal, so Tier 1 answers the size outright and
#            no prose mining is needed for it
#   multiple size must be mined per window, and Tier 1 becomes a *constraint*
#            (no tranche equals the whole) rather than an answer
#
# Risk metrics (EL, attachment, exhaustion, spread, severity) are identical on
# both paths and are extracted once, before the branch. Keeping the split
# explicit stops single-tranche rules from being bolted on afterwards, which is
# how this function first grew.
# ---------------------------------------------------------------------------

def _tranche_context(record):
    """Everything both branches need, resolved once."""
    m_iy = re.search(r"(19\d\d|20\d\d)", record["date_of_issue"]["value"] or "")
    hist = record["size_history"]["value"] or []
    return {
        "prose": record["_meta"]["full_details_text"] or "",
        "issue_year": int(m_iy.group(1)) if m_iy else None,
        "deal_size": record["size"]["value"],
        "deal_total": _money_to_number(record["size"]["value"] or "") or None,
        "deal_launch": next((h["value"] for h in hist
                             if h["state"] == "launch"), None),
        "own_series": (_series_tokens(record["deal_name"]["value"] or "")
                       | _series_tokens(record["deal_url"]["value"] or "")),
        "deal_status": record.get("deal_status", {}).get("value"),
        "bindings": _bindings_by_label(record["_meta"]["full_details_text"] or ""),
    }


def _extract_tranche_metrics(text, ctx):
    """SHARED. Risk metrics and derived severity, identical on both branches."""
    row = {}
    for name, patterns in TRANCHE_PATTERNS.items():
        # own_series too: the deal-level path excludes same-year sibling
        # sentences by series token; the tranche path silently did not.
        f = _apply_patterns(name, patterns, text, ctx["issue_year"],
                            ctx.get("own_series", frozenset()))
        row[name] = f["value"]
        row[name + "__conf"] = f["confidence"]
        row[name + "__flags"] = ";".join(str(x) for x in f["flags"]
                                         if x != "not_found")

    def num(key):
        v = row[key]
        return _pct_to_float(v)

    el, ap, ep = (num("expected_loss"), num("attachment_probability"),
                  num("exhaustion_probability"))
    flags = []
    row["conditional_severity"] = None
    if el and ap and ap > 0:
        row["conditional_severity"] = round(el / ap, 4)
        if el > ap:
            flags.append("VIOLATION:EL_exceeds_attachment_probability")
        if ep is not None and not (ep <= el <= ap):
            flags.append("VIOLATION:expected_exhaustion<=EL<=attachment")
    row["_metric_flags"] = flags
    return row


LABEL_BOUND_RE = re.compile(
    # \s* not \s+: _M already ends with \s*, which consumed the separator, so
    # \s+ could never match and this regex silently never fired.
    _M + r"\s*(?:tranche\s+of\s+)?Class\s+([A-Z]{1,3}-\d+[A-Z]?|[A-Z]{1,3}\b|\d{1,2}\b)",
    re.IGNORECASE)


FORWARD_BOUND_RE = re.compile(
    r"Class\s+([A-Z]{1,3}-\d+[A-Z]?|[A-Z]{1,3}\b|\d{1,2}\b)\s*[\u2013\u2014:-]\s*" + _M,
    re.IGNORECASE)


def _bindings_by_label(prose):
    """{label: [amounts]} for every "AMOUNT [tranche of] Class X" in the prose.

    Computed over the WHOLE prose, deliberately. A positional check inside a
    tranche window cannot work: the window for Class M-2 ends immediately
    before "Class B-1", so the slice holds "$16,821,000 tranche of " with the
    label that owns it cut off, and M-2 reported B-1's size.
    """
    out = {}
    # Forward form FIRST: "Class A – $256 million Class B – $647.6 million"
    # (Merna) is a list where each amount FOLLOWS its label. The backward
    # regex alone read "$256 million Class B" and shifted every size one
    # class along. An amount bound forward is not available backward.
    taken = set()
    for m in FORWARD_BOUND_RE.finditer(prose or ""):
        out.setdefault(("Class " + m.group(1)).upper(), []).append(_clean(m.group(2)))
        taken.add(m.start(2))
    for m in LABEL_BOUND_RE.finditer(prose or ""):
        if m.start(1) in taken:
            continue
        out.setdefault(("Class " + m.group(2)).upper(), []).append(_clean(m.group(1)))
    # Shared-subject constructions: "Both the Class A and Class B tranche of
    # notes are sized at EUR 25m each" states ONE amount that belongs to BOTH.
    for sentence in sentences(prose or ""):
        if not re.search(r"\beach\b", sentence, re.IGNORECASE):
            continue
        labels = {("Class " + g).upper() for g in CLASS_RE.findall(sentence)
                  if g.upper() not in CLASS_STOPWORDS}
        if len(labels) < 2:
            continue
        amounts = [x for x in MONEY_RE.findall(sentence)
                   if (_money_to_number(x) or 0) >= 1e6]
        if len(amounts) == 1:
            for lab in labels:
                out.setdefault(lab, []).append(_clean(amounts[0]))
    return out


def _bound_to_other_label(cand, label, bindings):
    """True if this amount is explicitly bound to a different class."""
    if not label or not bindings:
        return False
    mine = bindings.get(label.upper(), [])
    if cand in mine:
        return False
    return any(cand in amts for lab, amts in bindings.items()
               if lab != label.upper())


def _bound_size_for(label, prose):
    """Amounts explicitly bound to this label anywhere in the prose."""
    if not label:
        return []
    out = []
    for m in LABEL_BOUND_RE.finditer(prose):
        if ("Class " + m.group(2)).upper() == label.upper():
            out.append(_clean(m.group(1)))
    return out


def _mine_sizes(label, text, ctx, exclude_total):
    """Ordered (value, kind) size mentions in one window: first is launch."""
    sizes, skipped, dropped = [], 0, 0
    label_re = (re.compile(r"\b" + re.escape(label) + r"\b", re.IGNORECASE)
                if label else None)
    # Pass 1 demands the sentence name this class. If nothing is found, pass 2
    # drops that scoping but keeps the anchored size idioms.
    for require_label in (True, False):
        for sentence in sentences(text):
            if _is_backward_reference(sentence, ctx["issue_year"],
                                      ctx.get("own_series", frozenset())):
                if require_label and MONEY_RE.search(sentence):
                    skipped += 1
                continue
            if require_label and label_re and not label_re.search(sentence):
                continue
            main = PAREN_CONVERSION_RE.sub(" ", sentence)
            for rx, kind in TRANCHE_SIZE_RES:
                m = rx.search(main)
                if not m:
                    continue
                g = next(i for i in range(1, m.re.groups + 1) if m.group(i))
                cand = _clean(m.group(g))
                num = _money_to_number(cand) or 0
                if num < 1e6:
                    continue
                if _bound_to_other_label(cand, label, ctx.get("bindings")):
                    continue  # this amount explicitly names another tranche
                if _governed_by_loss_level(main, m.start(g), m.end(g)):
                    continue  # a loss level, not a size
                if (exclude_total and ctx["deal_total"]
                        and abs(num - ctx["deal_total"]) / ctx["deal_total"] <= 0.01):
                    dropped += 1
                    continue
                sizes.append((cand, kind))
                break
        if sizes:
            break
    return sizes, skipped, dropped


def _launch_final(sizes):
    """(launch, final, flags) from ordered (value, kind) mentions.

    A range's low end is a legitimate launch state and never a final: IBRD
    111-112 Class B reported $25m as final from "between $25m and $100m"
    while the page says it priced at $95m.
    """
    if not sizes:
        return None, None, []
    flags = []
    launch = sizes[0][0]
    if sizes[0][1] == "range":
        flags.append("launch_from_range_low_end")
    settled = [v for v, k in sizes if k != "range"]
    if settled:
        final = settled[-1]
    else:
        final = None
        flags.append("no_settled_size:range_only")
    return launch, final, flags


def _size_row(launch, final, states, flags):
    a, b = _money_to_number(launch or ""), _money_to_number(final or "")
    same_ccy = _currency(launch or "") == _currency(final or "")
    delta = None
    if a and b and same_ccy and a != b:
        delta = round((b - a) / a * 100, 1)
        if abs(b - a) / a <= 0.01:
            # "$19.5 million" in prose vs "$19.451m" in the summary box is
            # rounding, not a resize; the deal-level rule uses the same 1%.
            delta = None
            flags = list(flags) + ["size_rounding_only"]
    return {
        "tranche_size_at_launch": launch,
        "tranche_size_final": final,
        "tranche_size_states": states,
        "tranche_size_delta_pct": delta,
        "tranche_size_flags": ";".join(f for f in flags if f),
    }


def _size_multi(label, text, ctx):
    """BRANCH: several tranches. Mine the window; Tier 1 constrains it."""
    sizes, skipped, dropped = _mine_sizes(label, text, ctx, exclude_total=True)
    extra = []
    if not sizes:
        # Explicit binding beats window geometry: Triangle's Class B-1 amount
        # sits outside its window entirely.
        # Use the prebuilt map, which also carries shared-subject "each"
        # distributions that a direct rescan of the prose would miss.
        cand = (ctx.get("bindings") or {}).get((label or "").upper(), [])
        sizes = []
        for v in cand:
            n = v if isinstance(v, (int, float)) else _money_to_number(str(v))
            if n and ctx.get("deal_total") and abs(n - ctx["deal_total"]) / ctx["deal_total"] <= 0.01:
                continue                    # the deal total is never one tranche
            sizes.append((v, "stated"))
        if sizes:
            extra.append("size_from_label_binding")
    if not sizes and dropped:
        # The only candidate was rejected for equalling the deal total. On
        # ResRe 2020 that total IS Class 13's size, because Class 12 "will not
        # be issued at all". Refusing to report it created a phantom gap.
        sizes, _s, _d = _mine_sizes(label, text, ctx, exclude_total=False)
        if sizes:
            extra.append("equals_deal_total_accepted")
    anchored = bool(re.search(
        r"finalis|finaliz|priced|final(?:ly)? |secured|settled", text, re.IGNORECASE))
    launch, final, flags = _launch_final(sizes)
    if len(sizes) > 1 and not anchored:
        flags.append("tranche_size_final_unanchored")
    if skipped:
        flags.append("foreign_deal_reference_excluded=%d_sentence(s)" % skipped)
    if dropped and "equals_deal_total_accepted" not in extra:
        flags.append("deal_total_excluded=%d" % dropped)
    flags.extend(extra)
    return _size_row(launch, final, len(sizes), flags)


def _size_single(label, text, ctx):
    """BRANCH: one tranche. It IS the deal, so Tier 1 answers directly."""
    sizes, skipped, _ = _mine_sizes(label, text, ctx, exclude_total=False)
    mined_launch, mined_final, flags = _launch_final(sizes)
    launch = ctx["deal_launch"] or mined_launch
    if ctx.get("deal_status") in ("not_issued", "cancelled"):
        # No Tier-1 final exists BECAUSE the deal never issued. Promoting the
        # prose target to "final" reported principal that does not exist.
        return _size_row(launch, None, len(sizes),
                         ["no_final_size:%s" % ctx["deal_status"]])
    final = ctx["deal_size"] or mined_final
    if ctx["deal_size"]:
        flags = [f for f in flags if not f.startswith("no_settled_size")]
        flags.append("final_from_tier1")
    if skipped:
        flags.append("foreign_deal_reference_excluded=%d_sentence(s)" % skipped)
    return _size_row(launch, final, len(sizes), flags)


def _reconcile_tranche_sizes(rows, ctx):
    """Choose among candidate sizes so the parts equal the whole.

    Discovery (windows + label binding) is good at FINDING candidates and bad
    at choosing between them, which is where every veto was really aimed. The
    parts-vs-whole invariant already knew the answer -- it was just being used
    to check the result instead of to pick it.

    Candidates come from both sources: the size discovery already chose, plus
    every typed size mention scoped to that label. Applied only when a unique
    combination reconciles; otherwise the row is left alone and flagged, since
    an unresolved tranche beats a confident wrong one.
    """
    labelled = [r for r in rows if r.get("tranche_id")]
    if len(labelled) < 2 or not ctx.get("deal_total"):
        return
    mentions = extract(ctx["prose"])
    text_of, by_label = {}, {}
    for r in labelled:
        lab = r["tranche_id"]
        cands = {}
        cur = r.get("tranche_size_final")
        if cur and _money_to_number(cur):
            cands[_money_to_number(cur)] = cur
        for m in mentions:
            if m["kind"] == "size" and (m["scope"] or "").upper() == lab.upper():
                cands.setdefault(m["value"], m["text"])
        if not cands:
            return                       # incomplete: nothing to reconcile
        by_label[lab] = cands
        text_of.update(cands)

    if len({_currency(t) for c in by_label.values() for t in c.values()}) > 1:
        return                           # mixed currencies: refuse to add up

    fake = [{"kind": "size", "scope": lab, "value": v}
            for lab, c in by_label.items() for v in c]
    solution, _cands, _reason = solve_tranche_sizes(fake, ctx["deal_total"])
    if not solution:
        return
    for r in labelled:
        chosen = solution.get(r["tranche_id"])
        if chosen is None:
            continue
        current = _money_to_number(r.get("tranche_size_final") or "")
        if current is not None and abs(current - chosen) < 1e-6:
            continue                     # discovery already agreed
        r["tranche_size_final"] = text_of[chosen]
        r["tranche_size_flags"] = ";".join(
            x for x in [r.get("tranche_size_flags"), "size_from_parts_vs_whole"] if x)


def parse_tranches(record):
    """One row per tranche, falling back to a single unlabelled tranche."""
    ctx = _tranche_context(record)
    if not ctx["prose"]:
        return []

    windows = _tranche_windows(ctx["prose"])
    unresolved = False
    if not windows:
        # No class labels. If the deal-level scalars saw multiple candidates
        # there really are several tranches we cannot name -- say so rather
        # than silently reporting the first.
        unresolved = any(
            any(str(f).startswith("candidates=") for f in record[k]["flags"])
            for k in RISK_METRICS)
        windows = [(None, ctx["prose"])]

    # What does the page say about itself? Some deals (Trinity Re 1998, Mosaic
    # Re II 1999, ResRe 2010's "Classes 1 to 3") state a tranche count but never
    # describe the tranches individually, so there is nothing to split on. We
    # do NOT fabricate rows for them -- we carry the discrepancy instead.
    stated = None
    for sent in sentences(ctx["prose"]):
        if _series_tokens(sent) - ctx["own_series"]:
            continue  # describes a sibling deal
        if re.search(r"\bfrom the\b|\bprevious\b|\bprior\b", sent, re.IGNORECASE):
            continue
        m_sc = STATED_COUNT_RE.search(sent)
        if m_sc:
            tok = m_sc.group(1).lower()
            stated = int(tok) if tok.isdigit() else COUNT_WORDS.get(tok)
            break

    # A page stating more tranches than we could split out is a MULTI-tranche
    # deal we failed to resolve -- not a single-tranche deal. Treating it as
    # single handed Mosaic Re II (stated 2, $25m + $20m) the Tier-1 total $45m
    # as one row's size, a +80% fabricated resize that broke the very rule that
    # no tranche may equal the whole.
    unresolved_multi = bool(stated and stated > len(windows))
    resolve_size = (_size_multi if (len(windows) > 1 or unresolved_multi)
                    else _size_single)

    rows = []
    for label, text in windows:
        row = {"tranche_id": label}
        metrics = _extract_tranche_metrics(text, ctx)
        flags = metrics.pop("_metric_flags")
        row.update(metrics)
        row.update(resolve_size(label, text, ctx))
        if unresolved:
            flags.append("tranche_labels_unresolved")
        if stated and stated > len(windows):
            flags.append("tranche_count_understated:parsed=%d,stated=%d"
                         % (len(windows), stated))
        if unresolved_multi:
            # Sizes cannot be attributed to a named tranche; refuse to guess.
            for key in ("tranche_size_at_launch", "tranche_size_final",
                        "tranche_size_delta_pct"):
                row[key] = None
            row["tranche_size_flags"] = ";".join(
                x for x in [row.get("tranche_size_flags"),
                            "tranche_sizes_unassignable"] if x)
        elif label and not row.get("tranche_size_final") and re.search(
                re.escape(label) + r"[^.]{0,120}?will not be issued",
                ctx["prose"], re.IGNORECASE):
            row["tranche_size_flags"] = ";".join(
                x for x in [row.get("tranche_size_flags"), "tranche_not_issued"] if x)
        elif (label and not row.get("tranche_size_final")
              and "no_final_size" not in (row.get("tranche_size_flags") or "")):
            # A NAMED tranche with no size is a parse failure, not an absence.
            # These previously carried an empty flag string and slipped past
            # check_tranche_sum, which returns n/a when any size is missing.
            row["tranche_size_flags"] = ";".join(
                x for x in [row.get("tranche_size_flags"),
                            "tranche_size_missing"] if x)
        row["stated_tranche_count"] = stated
        row["tranche_flags"] = ";".join(flags)
        rows.append(row)
    _reconcile_tranche_sizes(rows, ctx)
    apply_tranche_lifecycle(rows, ctx["prose"])
    return rows


# ---------------------------------------------------------------------------
# Tranche lifecycle: extensions, actual maturity, principal loss.
#
# Found by hand-labelling, not by review: Citrus Re 2015-1's page records that
# Class A matured, Classes B and C were "extended to April 9th 2020", and
# Class C was then "allowed to mature with a balance of zero" -- a documented
# extension and a total loss -- and the parser had no field for any of it.
# This is the only place a DEAL PAGE records capital leaving, and it
# cross-checks against the losses table, which records the same events
# site-wide.
# ---------------------------------------------------------------------------

_LC_DATE = (r"((?:" + MONTHS + r")\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}"
            r"|(?:" + MONTHS + r")\s+\d{4})")
LC_EXTENDED_RE = re.compile(r"(?:maturit\w+|notes?)?\s*(?:been\s+)?extended"
                            r"(?:\s+\w+){0,3}?\s+to\s+" + _LC_DATE, re.IGNORECASE)
LC_ZERO_RE = re.compile(r"balance of zero|total loss of principal|100%\s*loss",
                        re.IGNORECASE)
LC_MATURE_RE = re.compile(r"\b(?:let|allowed)\b[^.]{0,60}?\bmature\b|"
                          r"\bmatured?\b", re.IGNORECASE)
def apply_tranche_lifecycle(rows, prose):
    """Fill maturity_extended / maturity_actual / principal_loss_pct in place.

    Clause-scoped: "Heritage has let the ... Class A ... mature, but both the
    Class B and Class C have had their maturities extended" assigns opposite
    outcomes within one sentence, so clauses split on but/while/; first.
    """
    known = {str(r.get("tranche_id")).upper(): r for r in rows if r.get("tranche_id")}
    for r in rows:
        for k in ("maturity_extended", "maturity_actual", "principal_loss_pct",
                  "loss_basis", "lifecycle_evidence"):
            r.setdefault(k, None)
    if not known or not prose:
        return
    # _segment_prose_dated already parses each update heading's date; using it
    # instead of re-deriving here -- a first draft of this function wrote its
    # own header-date regex against the ordinal labels, which carry no date,
    # and silently never matched. Same duplicated-derivation class as always.
    segments, seg_dates = _segment_prose_dated(prose)
    for label, text in segments:
        seg_date = seg_dates.get(label)
        for sent in sentences(text):
            for clause in re.split(r"\bbut\b|\bwhile\b|;", sent):
                targets = [known[("Class " + g).upper()]
                           for g in CLASS_RE.findall(clause)
                           if ("Class " + g).upper() in known]
                if not targets:
                    continue
                ev = re.sub(r"\s+", " ", clause.strip())[:140]
                m = LC_EXTENDED_RE.search(clause)
                if m:
                    for t in targets:
                        t["maturity_extended"] = _clean(m.group(1))
                        t["lifecycle_evidence"] = ev
                    continue
                if LC_ZERO_RE.search(clause):
                    for t in targets:
                        t["principal_loss_pct"] = 100.0
                        t["loss_basis"] = "stated"
                        t["maturity_actual"] = t["maturity_actual"] or seg_date
                        t["lifecycle_evidence"] = ev
                    continue
                if LC_MATURE_RE.search(clause) and not re.search(
                        r"extend|will mature|scheduled|expected", clause, re.IGNORECASE):
                    for t in targets:
                        t["maturity_actual"] = t["maturity_actual"] or seg_date
                        t["lifecycle_evidence"] = t["lifecycle_evidence"] or ev


def check_tranche_sum(record, rows):
    """Do the tranche finals add up to the Tier-1 deal size?

    A structural cross-check in the same family as EP <= EL <= AP: the parts
    must equal the whole. It caught the FloodSmart size swap (Class A and B
    sizes had been assigned to each other's tranche) and is the cheapest
    detector we have for tranche-window bleed.

    Returns (ok, detail). ok is None when the check cannot be run (missing
    sizes, placeholder size, or a currency mismatch).
    """
    deal_size = record["size"]["value"]
    if not deal_size or not rows:
        return None, "no deal size or no tranches"
    sizes = [r.get("tranche_size_final") for r in rows]
    if not all(sizes):
        return None, "incomplete tranche sizes"
    if len({_currency(s) for s in sizes} | {_currency(deal_size)}) > 1:
        return None, "currency mismatch"
    total = sum(_money_to_number(s) or 0 for s in sizes)
    whole = _money_to_number(deal_size) or 0
    if not whole:
        return None, "unparseable deal size"
    delta = (total - whole) / whole
    if abs(delta) <= 0.01:
        return True, ("basis=notes tranches=%s sum=%.0f deal=%.0f delta=%+.1f%%"
                      % (sizes, total, whole, delta * 100))
    # Does the headline include capital raised beside the notes?
    other = [o for o in (record.get("other_instruments", {}).get("value") or [])
             if _currency(o["value"]) == _currency(deal_size)]
    extra = sum(_money_to_number(o["value"]) or 0 for o in other)
    if other and abs(total + extra - whole) / whole <= 0.01:
        return True, ("basis=notes+%s tranches=%s sum=%.0f other=%.0f deal=%.0f"
                      % ("+".join(sorted({o["kind"] for o in other})), sizes, total, extra, whole))
    return False, (
        "basis=mismatch tranches=%s sum=%.0f deal=%.0f delta=%+.1f%%"
        % (sizes, total, whole, delta * 100))
