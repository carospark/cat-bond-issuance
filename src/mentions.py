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
KIND_CUES = [
    ("exhaustion", r"exhaust(?:ion|s)?\s*(?:point)?\s*(?:of|at)|up to an exhaustion"),
    ("attachment", r"attach(?:ment|es|ing)?\s*(?:point)?\s*(?:of|at)"),
    ("deductible", r"deductible"),
    ("retention", r"\bretention\b|\bfranchise\b"),
    ("term_loan", r"term loan"),
    ("layer", r"\blayer\b"),
    ("payout", r"payout|paid out|principal reduction|loss(?:es)? of"),
    ("trigger", r"trigger point|index value"),
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
    for hay, conf, dist in ((before, "high", lambda m: len(before) - m.end()),
                            (after, "medium", lambda m: m.start())):
        # NEAREST cue wins, not the highest-priority one. Priority alone made
        # "offering $50m of notes ... the layer sits above" classify as a
        # layer, because `layer` outranks `size` in the list while sitting 20
        # characters further from the amount. Priority survives as a tiebreak.
        best = None
        for rank, (kind, pattern) in enumerate(KIND_CUES):
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
