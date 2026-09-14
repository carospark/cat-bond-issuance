"""Typed money mentions: classify every amount once, by kind.

WHY THIS EXISTS
---------------
The size path grew as a stack of vetoes: reject amounts near "deductible",
near "attachment", near "layer", near "term loan", equal to the deal total,
at the high end of a range. Each was added after a reviewer found the instance
it covers. Measured on 60 RANDOM deals, the classes recurred anyway:

    market-re 2014-4   tier1 $30m,  tranches $22m + $30m   deal total leaked
    alamo-re 2015-1    tranches "$2.6 billion" + $250m     loss level read as size
    east-lane-vii      tier1 $150m, tranches $150m x 2     one tranche counted twice

Both the leak and the loss-level misread are classes we had already "fixed"
twice. A veto only ever covers the phrasing that prompted it, so the class
survives on the next unseen page.

The fix is representational rather than another veto. Every money mention is
classified ONCE against the cue that governs it, and consumers ask for the kind
they want. An attachment point stops being a size candidate structurally, not
because someone remembered to exclude that wording.

Kinds are deliberately mutually exclusive and ordered by cue specificity: a
mention adjacent to "exhaustion point of" is an exhaustion, never a size, even
if the sentence also says "in size".
"""

import re

# Cue -> kind, most specific first. The FIRST match wins, so ordering is the
# classification policy and belongs in one visible place.
# An optional third element BEFORE marks a cue that governs only the amount
# AFTER it. "targets $175 million in coverage, attaching lower down at $650
# million" (Torrey Pines 2025-1): the bridged attachment cue sits in the
# $175m's after-window and must not claim it.
BEFORE = "before_only"
KIND_CUES = [
    ("exhaustion", r"exhaust(?:ion|s|ing)?\s*(?:point)?\s*(?:of|at)|up to an exhaustion"),
    ("attachment", r"attach(?:ment|es|ing)?\s*(?:point)?\s*(?:of|at)"),
    # "attach lower down at $1.795 billion" (Kilimanjaro III 2026-2): allow a
    # few words between the verb and its preposition, before the amount only.
    ("attachment", r"attach(?:ment|es|ing)?\s*(?:point)?(?:\s+\w+){1,3}\s*(?:of|at)\b", BEFORE),
    ("deductible", r"deductible"),
    ("retention", r"\bretention\b|\bfranchise\b"),
    ("term_loan", r"term loan"),
    ("layer", r"\blayer\b|\breinsurance towers?\b"),
    ("payout", r"payout|paid out|principal reduction|loss(?:es)? of"),
    ("trigger", r"trigger point|trigger value|trigger level|index value|"
                r"index level|index trigger"),
    # Amounts that are somebody else's capital, not this deal's size. Each
    # cue is a real page: Finca 2025-1's "$10 billion" was the index
    # THRESHOLD; Meadows 2025-1's "$8 billion" was the investor's AUM;
    # FloodSmart 2020-1's "$1.1 billion" was FEMA's total cover AFTER the
    # deal; Muteki's "US$ 1bn" was the programme's aggregate volume;
    # Kilimanjaro III 2026-2's "$530 million" was a target ACROSS two series;
    # Power Protective 2021-1's "$50 million" was its predecessor's size.
    ("threshold", r"threshold"),
    ("aum", r"assets under management|in assets|of assets|under management|\bAUM\b"),
    # "across the two series" is deliberately NOT here: whether that is
    # another deal's total depends on how many series THIS entry covers,
    # which only the parser knows (CUMULATIVE_RE in parse_deal).
    # "after this deal is issued" is sentence-level (CUMULATIVE_RE), not here.
    # bare "alongside" hit "marketed to investors, alongside their preliminary
    # ratings: $92.0 million Class M-1A" (Bellemeade 2020-2); bind it to "sit".
    ("other_capital", r"\bsit(?:s|ting)? (?:\w+ )?alongside|traditional (?:sources of )?reinsurance|"
                      r"reinsurance towers?|programme|aggregate volume|"
                      r"future issuances"),
    ("predecessor", r"(?:first|previous|prior|earlier|last|predecessor|original|"
                    r"maturing|inaugural|debut)\s+(?:[\w'\u2019-]+\s+){0,3}"
                    r"(?:cat bonds?|deals?|transactions?|issuances?|bonds?)\b"
                    r"[^$\u20ac\u00a3]{0,30}\b(?:which|that|was|were)\b"),
    ("size", r"in size|size of|sized at|tranche of|of notes|of cat bond notes|"
             r"issuance of|of reinsurance|of protection|of capital|"
             r"secure|seeking|sought|targeted|priced at|settled at|finalis"),
]

MONEY = re.compile(
    r"(?P<sym>[$€£¥]|\b(?:USD|EUR|GBP|CHF|JPY|CAD|AUD|NZD)\b)\s?"
    r"(?P<num>[\d,]+(?:\.\d+)?)\s*"
    r"(?P<mult>million|billion|bn|m\b|b\b)?", re.IGNORECASE)

MULT = {"m": 1e6, "million": 1e6, "bn": 1e9, "b": 1e9, "billion": 1e9}
SYMBOL = {"USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥"}

# A range states two bounds of ONE quantity; both are tagged so a consumer can
# pick the bound it means rather than whichever the regex reached first.
RANGE_RE = re.compile(r"between\s|from\s|\bto\b|\band\b")

CLASS_RE = re.compile(r"\bClass\s+([A-Z]{1,3}-\d+[A-Z]?|[A-Z]{1,3}\b|\d{1,2}\b)",
                      re.IGNORECASE)

WINDOW = 60          # chars either side searched for a governing cue

# "The attachment point ... is at $800 million" (PoleStar 2024-3) and "the
# layer of SafePoint's tower where this cat bond will feature is $200 million
# in size" (Nature Coast 2024-1): the governing noun is the clause SUBJECT,
# further back than any window, and the nearest cue after the amount ("in
# size") says the opposite. When the amount is the predicate of a copula, the
# earliest noun of the clause is what is being measured.
SUBJECT_NOUNS = [
    ("attachment", r"attachment point|attaches"),
    ("exhaustion", r"exhaustion point"),
    ("threshold", r"threshold"),
    ("trigger", r"trigger (?:point|value|level)|index (?:value|level)"),
    ("deductible", r"deductible"),
    ("retention", r"\bretention\b|\bfranchise\b"),
    # NOT bare "tower": Winston 2026-1's sponsor is Tower Hill Insurance.
    ("layer", r"\blayers?\b|\b(?:reinsurance|insurance) towers?\b"),
    ("size", r"\b(?:deal|transaction|issuance|offering|notes|cat bond|"
             r"tranche|class|series|target|size|placement)\b"),
]
CLAUSE_CUT_RE = re.compile(r"[.;:,]\s|\b(?:and|but|while|whereas)\s")
COPULA_TAIL_RE = re.compile(
    r"\b(?:is|was|are|were|be|being|sits?|sat|stands?|stood|set|placed|"
    r"comes? in|sitting)\b(?:\s+at)?(?:\s+(?:around|about|approximately|"
    r"some|roughly|just|almost|nearly|only|now|currently))*\s*$", re.IGNORECASE)


def _subject_kind(text, pos):
    """Kind named by the subject of "<subject> is [at] $X", or None."""
    span = text[max(0, pos - 160):pos]
    cuts = list(CLAUSE_CUT_RE.finditer(span))
    if cuts:
        span = span[cuts[-1].end():]
    if not COPULA_TAIL_RE.search(span):
        return None
    # "Class B layer" needs no special case: "class" is a size noun and
    # precedes "layer", so the tranche wins. (A dedicated exemption was
    # dead code and was mutation-tested out.)
    best = None
    for kind, pattern in SUBJECT_NOUNS:
        for m in re.finditer(pattern, span, re.IGNORECASE):
            if best is None or m.start() < best[0]:
                best = (m.start(), kind)
    return best[1] if best and best[1] != "size" else None


def _numeric(num, mult):
    try:
        v = float(num.replace(",", ""))
    except ValueError:
        return None
    return v * MULT.get((mult or "").lower(), 1.0)


def classify(text, pos, end):
    """(kind, cue, confidence) for the amount spanning [pos, end)."""
    before = text[max(0, pos - WINDOW):pos]
    after = text[end:end + WINDOW]
    # A cue BEFORE the amount governs it more reliably than one after
    # ("attachment point of $9 billion" vs "$9 billion of losses").
    # Order: cue before the amount; then the clause subject (see
    # SUBJECT_NOUNS); then a cue after the amount. The subject sits between
    # because "the layer ... is $200 million in size" has its true governor
    # before the amount and a misleading cue after it.
    for hay, conf, dist in ((before, "high", lambda m: len(before) - m.end()),
                            (None, "medium", None),
                            (after, "medium", lambda m: m.start())):
        if hay is None:
            subj = _subject_kind(text, pos)
            if subj:
                return subj, "subject", "medium"
            continue
        # NEAREST cue wins, not the highest-priority one. Priority alone made
        # "offering $50m of notes ... the layer sits above" classify as a
        # layer, because `layer` outranks `size` in the list while sitting 20
        # characters further from the amount. Priority survives as a tiebreak.
        best = None
        for rank, entry in enumerate(KIND_CUES):
            kind, pattern = entry[0], entry[1]
            if len(entry) > 2 and entry[2] == BEFORE and hay is after:
                continue
            for m in re.finditer(pattern, hay, re.IGNORECASE):
                key = (dist(m), rank)
                if best is None or key < best[0]:
                    best = (key, kind, m.group(0).strip())
        if best:
            return best[1], best[2], conf
    return "unknown", None, None


def scope_of(text, pos):
    """The Class label governing this position, or None for deal scope."""
    before = text[max(0, pos - 120):pos]
    hits = list(CLASS_RE.finditer(before))
    return ("Class " + hits[-1].group(1).upper()) if hits else None


def extract(text, state="launch"):
    """Every money mention in `text`, typed. Order is document order."""
    out = []
    for m in MONEY.finditer(text or ""):
        value = _numeric(m.group("num"), m.group("mult"))
        if value is None:
            continue
        sym = m.group("sym").upper()
        kind, cue, conf = classify(text, m.start(), m.end())
        seg = text[max(0, m.start() - 90):m.end() + 90]
        out.append({
            "text": m.group(0).strip(),
            "value": value,
            "currency": SYMBOL.get(sym, m.group("sym")),
            "kind": kind,
            "cue": cue,
            "kind_confidence": conf,
            "scope": scope_of(text, m.start()),
            "state": state,
            "start": m.start(),
            "in_range": bool(re.search(r"between\s+[^.]{0,40}$", text[:m.start()])),
            "evidence": re.sub(r"\s+", " ", seg).strip(),
        })
    return out


def sizes(mentions, scope="any"):
    """Mentions usable as a SIZE. The whole point: ask for the kind you want."""
    ok = [x for x in mentions if x["kind"] == "size"]
    if scope == "deal":
        ok = [x for x in ok if x["scope"] is None]
    elif scope not in ("any", None):
        ok = [x for x in ok if x["scope"] == scope]
    return ok


# ---------------------------------------------------------------------------
# Constraint selection
#
# Typing alone cannot resolve every case: Market Re's deal total appears in a
# sentence beside Class B, and "$30m ... of notes" is a genuine size cue. What
# rules it out is arithmetic - Class A $22m + Class B $8m = the $30m total.
#
# So the invariant that used to CHECK the answer now helps CHOOSE it. Where
# several typed candidates exist per tranche, prefer the combination whose
# parts equal the whole. Where none does, say so: an unresolved deal is a
# better output than a confident wrong one, and it was already the rule
# everywhere else in this parser.
# ---------------------------------------------------------------------------

import itertools


def solve_tranche_sizes(mentions, deal_total, tolerance=0.01, max_combos=20000):
    """{label: value} chosen so the parts equal the whole, or None.

    Returns (solution, candidates, reason). `reason` explains a None so the
    caller can flag it rather than silently fall back.
    """
    scoped = [m for m in mentions if m["kind"] == "size" and m["scope"]]
    by_label = {}
    for m in scoped:
        by_label.setdefault(m["scope"], []).append(m)
    if not by_label:
        return None, by_label, "no scoped size mentions"
    if not deal_total:
        return None, by_label, "no deal total to constrain against"

    labels = sorted(by_label)
    choices = [sorted({m["value"] for m in by_label[l]}) for l in labels]
    total_combos = 1
    for c in choices:
        total_combos *= len(c)
    if total_combos > max_combos:
        return None, by_label, "too many combinations (%d)" % total_combos

    best = None
    for combo in itertools.product(*choices):
        if abs(sum(combo) - deal_total) / deal_total <= tolerance:
            # Prefer the combination using the most distinct values: repeating
            # one amount across tranches is usually the same figure counted
            # twice (East Lane reported $150m for both of two tranches).
            if best is None or len(set(combo)) > len(set(best)):
                best = combo
    if best is None:
        return None, by_label, "no combination sums to the deal total"
    return dict(zip(labels, best)), by_label, None
