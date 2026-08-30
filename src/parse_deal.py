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

# name -> (pattern, strength). "strong" patterns carry an explicit anchor
# phrase; "weak" ones are fallbacks and are always downgraded to low.
TIER2_PATTERNS = {
    "expected_loss": [
        (r"(?:initial )?expected loss of (?:approximately |around |about )?([\d.]+\s*%)", "strong"),
        (r"expected loss[^.%]{0,30}?([\d.]+\s*%)", "weak"),
    ],
    "attachment_probability": [
        (r"attachment probability of (?:approximately |around )?([\d.]+\s*%)", "strong"),
    ],
    "exhaustion_probability": [
        (r"exhaustion probability of (?:approximately |around )?([\d.]+\s*%)", "strong"),
    ],
    "attachment_point": [
        (r"attach(?:es|ment)?(?: point)? (?:at|of) ([$\u20ac\u00a3][\d,.]+\s*(?:million|billion|m|bn)?)", "strong"),
        (r"attach(?:es|ment)?(?: point)? (?:at|of) ([\d.]+\s*%)", "strong"),
    ],
    # Only settled-price anchors live here. The old weak fallback
    # `(?:spread|coupon)[^.%]{0,40}?([\d.]+%)` grabbed whichever percentage sat
    # nearest the word and was indistinguishable from a correct hit, so it is
    # deleted rather than repaired: an honest None beats a plausible wrong
    # number. Guidance ranges belong in price_guidance / spread_history.
    "spread_risk_margin": [
        (r"(?:pricing|spread)[^.%]{0,60}?settled[^.%]{0,40}?at ([\d.]+\s*%)", "strong"),
        (r"priced to pay (?:investors )?an? (?:initial )?risk (?:margin|interest spread) of ([\d.]+\s*%)", "strong"),
        (r"final(?:ised|ized)? (?:pricing|spread|risk margin)[^.%]{0,30}?([\d.]+\s*%)", "strong"),
        # Settlement language first. "guide pricing of 11.25% to 12.25%" used to
        # match the generic form and return the range's LOWER BOUND as if it
        # were the settled spread; the lookahead now rejects range endpoints.
        (r"(?:pricing|spread)[^.%]{0,60}?settled[^.%]{0,40}?at ([\d.]+\s*%)", "strong"),
        (r"(?:pricing|spread)[^.%]{0,60}?fixed at ([\d.]+\s*%)", "strong"),
        (r"(?:priced|pricing) (?:at|of) ([\d.]+\s*%)(?!\s*(?:to|and|[-\u2013])\s*[\d.]+\s*%)", "strong"),
        (r"(?:initial )?risk (?:margin|interest spread) of ([\d.]+\s*%)", "strong"),
        (r"priced to pay (?:investors )?a spread of ([\d.]+\s*%)", "strong"),
        (r"coupon of ([\d.]+\s*%)", "strong"),
    ],
    "price_guidance": [
        (r"guidance[^.]{0,80}?([\d.]+\s*%\s*(?:to|and|[-–])\s*[\d.]+\s*%)", "strong"),
    ],
    "maturity_date": [
        # Closed month vocabulary: an open [A-Z][a-z]+ token happily matched
        # stopwords ("this new 2024", "the 2024") and filled the field with
        # nonsense at medium confidence. A fixed alternation cannot.
        (r"matur\w+[^.]{0,40}?(" + MONTHS + r"\s+\d{4})", "strong"),
    ],
    "term_length": [
        # "a three-year term" puts the number *before* the anchor, so the
        # original forward-looking pattern could never see it.
        (r"((?:\w+|\d+)[-\s](?:year|month)s?)\s+term", "strong"),
        (r"term of ((?:\w+|\d+)[-\s](?:year|month)s?)", "strong"),
        (r"(?:term|covering|run(?:ning)? across)[^.]{0,30}?"
         r"((?:\w+|\d+)[-\s](?:hurricane seasons|wind seasons|years|year))", "strong"),
    ],
    "payout_floor": [
        (r"minimum of ([\d.]+\s*%)[^.]{0,40}principal", "strong"),
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
AGGREGATE_RE = re.compile(r"\btotal|combined|aggregate|altogether|in all\b",
                          re.IGNORECASE)

# Source placeholders. Artemis writes these where it has no data; they are
# nulls wearing a value's clothes and previously sat in the table at HIGH
# confidence, making "the source is silent" indistinguishable from "our parser
# worked". Confidence stays high -- we are confident the source said nothing.
PLACEHOLDERS = {"unknown", "?", "n/a", "na", "-", "\u2013", "\u2014",
                "tbc", "tbd", "not issued", "none", "not known"}

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

MONEY_RE = re.compile(r"[$€£¥]\s?[\d,]+(?:\.\d+)?\s*(?:million|billion|bn|m\b|b\b)?", re.I)
MULTIPLIER = {"m": 1e6, "million": 1e6, "bn": 1e9, "b": 1e9, "billion": 1e9}


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


def _money_to_number(text):
    """Rough numeric value of a money string, for comparison/flagging only."""
    m = re.search(r"([\d,]+(?:\.\d+)?)\s*(million|billion|bn|m|b)?", text, re.I)
    if not m:
        return None
    num = float(m.group(1).replace(",", ""))
    unit = (m.group(2) or "").lower()
    return num * MULTIPLIER.get(unit, 1.0)


def _normalise_placeholder(value):
    """Map a source placeholder to None, preserving the raw string."""
    if value is not None and value.strip().lower().rstrip(".") in PLACEHOLDERS:
        return None, ["source_placeholder:%s" % value.strip()]
    return value, []


def _currency(text):
    """Leading currency symbol of a money string, or None."""
    m = re.search(r"[$\u20ac\u00a3\u00a5]", text or "")
    return m.group(0) if m else None


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


def _segment_prose(prose):
    """Split narrative into ordered states: launch, then each Update block."""
    parts = re.split(r"(Update\s*\d*\s*:)", prose, flags=re.IGNORECASE)
    segments = [("launch", parts[0])]
    for i in range(1, len(parts) - 1, 2):
        segments.append((_clean(parts[i]).rstrip(":").lower().replace(" ", "_"),
                         parts[i + 1]))
    return [(label, text) for label, text in segments if _clean(text)]


def _sentence_at(text, pos):
    """The sentence containing character offset `pos`."""
    start = text.rfind(". ", 0, pos)
    start = 0 if start < 0 else start + 2
    end = text.find(". ", pos)
    return text[start:(end + 1 if end >= 0 else len(text))]


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


def _apply_patterns(name, patterns, text, issue_year=None, own_series=frozenset()):
    """Run every pattern, collect distinct candidates, and grade the result."""
    hits, strength_used = [], None
    dropped = []
    for pattern, strength in patterns:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            value = _clean(m.group(1))
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

    segments = _segment_prose(prose) if prose else []

    # ---- Time series: how terms moved while marketing --------------------
    size_history, skipped_backref = [], 0
    for label, text in segments:
        for sentence in re.split(r"(?<=\.)\s+", text):
            if _is_backward_reference(sentence, issue_year, own_series):
                if MONEY_RE.search(sentence):
                    skipped_backref += 1
                continue  # figure belongs to a predecessor deal
            if not SIZING_CTX_RE.search(sentence):
                continue  # money here is not a deal size
            if CLASS_SCOPED_RE.search(sentence):
                continue  # a tranche's size, not the deal's
            amounts = [x for x in MONEY_RE.findall(sentence)
                       if (_money_to_number(x) or 0) >= 1e6]
            if len(amounts) > 1 and not AGGREGATE_RE.search(sentence):
                continue  # components enumerated with no stated total
            m = MONEY_RE.search(sentence)
            if m and (_money_to_number(_clean(m.group(0))) or 0) >= 1e6:
                size_history.append({"state": label, "value": _clean(m.group(0))})
                break
    sh_flags = [] if size_history else ["not_found"]
    if skipped_backref:
        sh_flags.append("foreign_deal_reference_excluded=%d_sentence(s)" % skipped_backref)
    record["size_history"] = _field(
        size_history or None, "medium" if size_history else None,
        "segmented_prose", f"{len(segments)} state(s)", sh_flags)

    spread_history = []
    for label, text in segments:
        for pattern, kind in [
            (r"priced to pay (?:investors )?an? (?:initial )?risk margin of ([\d.]+\s*%)", "priced"),
            (r"guidance[^.]{0,80}?([\d.]+\s*%\s*(?:to|and|[-–])\s*[\d.]+\s*%)", "guidance"),
            (r"(?:initial )?risk margin of ([\d.]+\s*%)", "risk_margin"),
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
                 if lbl != "launch" and RESIZE_RE.search(t)), None)
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
            return float(re.sub(r"[^\d.]", "", raw))
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

    placeholder_hits = [k for k in TIER1_KEYS
                        if any(str(x).startswith("source_placeholder")
                               for x in record[k]["flags"])]
    record["deal_is_private"] = _field(
        len(placeholder_hits) >= 3 or None,
        "medium" if len(placeholder_hits) >= 3 else None,
        "derived:tier1_placeholder_cluster",
        ",".join(placeholder_hits) or None,
        ["placeholders=%d" % len(placeholder_hits)] if placeholder_hits else ["not_found"])

    record["_meta"] = {
        "page_flags": page_flags,
        "extra_fields": extra_fields,
        "prose_chars": len(prose),
        "prose_states": [s[0] for s in segments],
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
_M = r"([$\u20ac\u00a3\u00a5][\d,.]+\s*(?:million|billion|bn|m)?)"
TRANCHE_SIZE_RES = [re.compile(x, re.IGNORECASE) for x in (
    r"size of " + _M,
    _M + r"\s+in size",
    r"(?:grew|upsiz\w+|settled|finalis\w+|finaliz\w+|target\w+|offered|priced)"
    r"\s+(?:to|at|as)\s+(?:up to |between )?" + _M,
    _M + r"\s+Class\s+[A-Z0-9]+",
    r"(?:tranche|notes)[^.]{0,20}?of " + _M,
    # "$134,574,000 tranche of Class M-1 notes" -- amount precedes the noun.
    _M + r"\s+tranche of",
    # "targeted to secure $150 million in reinsurance", "provide $300 million"
    _M + r"\s+(?:of|in) (?:reinsurance|protection)",
    r"(?:secure|provide|seeking|sought)\s+(?:up to |between )?" + _M,
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
COUNT_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4,
               "five": 5, "six": 6, "seven": 7, "eight": 8}

TRANCHE_PATTERNS = {
    "expected_loss": TIER2_PATTERNS["expected_loss"],
    "attachment_probability": TIER2_PATTERNS["attachment_probability"],
    "exhaustion_probability": TIER2_PATTERNS["exhaustion_probability"],
    "spread_risk_margin": TIER2_PATTERNS["spread_risk_margin"],
}


def _sentence_start(text, pos):
    i = text.rfind(". ", 0, pos)
    return 0 if i < 0 else i + 2


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
    # Keep only labels that appear at least once beside note/tranche language.
    by_label = {}
    for m in hits:
        ident = m.group(1).upper()
        if ident in CLASS_STOPWORDS:
            continue
        by_label.setdefault("Class " + ident, []).append(m)
    real = set()
    for label, ms in by_label.items():
        for m in ms:
            window = prose[max(0, m.start() - 60):m.end() + 60]
            if CLASS_CONTEXT_RE.search(window):
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
    }


def _extract_tranche_metrics(text, ctx):
    """SHARED. Risk metrics and derived severity, identical on both branches."""
    row = {}
    for name, patterns in TRANCHE_PATTERNS.items():
        f = _apply_patterns(name, patterns, text, ctx["issue_year"])
        row[name] = f["value"]
        row[name + "__conf"] = f["confidence"]
        row[name + "__flags"] = ";".join(str(x) for x in f["flags"]
                                         if x != "not_found")

    def num(key):
        v = row[key]
        return float(re.sub(r"[^\d.]", "", v)) if v else None

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


def _mine_sizes(label, text, ctx, exclude_total):
    """Ordered size mentions in one window: first is launch, last is final."""
    sizes, skipped, dropped = [], 0, 0
    label_re = (re.compile(r"\b" + re.escape(label) + r"\b", re.IGNORECASE)
                if label else None)
    # Pass 1 demands the sentence name this class. If nothing is found, pass 2
    # drops that scoping but keeps the anchored size idioms.
    for require_label in (True, False):
        for sentence in re.split(r"(?<=\.)\s+", text):
            if _is_backward_reference(sentence, ctx["issue_year"]):
                if require_label and MONEY_RE.search(sentence):
                    skipped += 1
                continue
            if require_label and label_re and not label_re.search(sentence):
                continue
            for rx in TRANCHE_SIZE_RES:
                m = rx.search(sentence)
                if not m:
                    continue
                cand = _clean(m.group(1))
                num = _money_to_number(cand) or 0
                if num < 1e6:
                    continue
                if (exclude_total and ctx["deal_total"]
                        and abs(num - ctx["deal_total"]) / ctx["deal_total"] <= 0.01):
                    dropped += 1
                    continue
                sizes.append(cand)
                break
        if sizes:
            break
    return sizes, skipped, dropped


def _size_row(launch, final, states, flags):
    a, b = _money_to_number(launch or ""), _money_to_number(final or "")
    same_ccy = _currency(launch or "") == _currency(final or "")
    return {
        "tranche_size_at_launch": launch,
        "tranche_size_final": final,
        "tranche_size_states": states,
        "tranche_size_delta_pct": (round((b - a) / a * 100, 1)
                                   if a and b and same_ccy and a != b else None),
        "tranche_size_flags": ";".join(f for f in flags if f),
    }


def _size_multi(label, text, ctx):
    """BRANCH: several tranches. Mine the window; Tier 1 constrains it."""
    sizes, skipped, dropped = _mine_sizes(label, text, ctx, exclude_total=True)
    anchored = bool(re.search(
        r"finalis|finaliz|priced|final(?:ly)? |secured|settled", text, re.IGNORECASE))
    flags = []
    if len(sizes) > 1 and not anchored:
        flags.append("tranche_size_final_unanchored")
    if skipped:
        flags.append("foreign_deal_reference_excluded=%d_sentence(s)" % skipped)
    if dropped:
        flags.append("deal_total_excluded=%d" % dropped)
    return _size_row(sizes[0] if sizes else None,
                     sizes[-1] if sizes else None, len(sizes), flags)


def _size_single(label, text, ctx):
    """BRANCH: one tranche. It IS the deal, so Tier 1 answers directly."""
    sizes, skipped, _ = _mine_sizes(label, text, ctx, exclude_total=False)
    launch = ctx["deal_launch"] or (sizes[0] if sizes else None)
    final = ctx["deal_size"] or (sizes[-1] if sizes else None)
    flags = ["final_from_tier1"] if ctx["deal_size"] else []
    if skipped:
        flags.append("foreign_deal_reference_excluded=%d_sentence(s)" % skipped)
    return _size_row(launch, final, len(sizes), flags)


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
            for k in TRANCHE_PATTERNS)
        windows = [(None, ctx["prose"])]

    # What does the page say about itself? Some deals (Trinity Re 1998, Mosaic
    # Re II 1999, ResRe 2010's "Classes 1 to 3") state a tranche count but never
    # describe the tranches individually, so there is nothing to split on. We
    # do NOT fabricate rows for them -- we carry the discrepancy instead.
    stated = None
    for sent in re.split(r"(?<=\.)\s+", ctx["prose"]):
        own = set(re.findall(r"\b(20\d\d-\d+)\b", record["deal_name"]["value"] or ""))
        if set(re.findall(r"\b(20\d\d-\d+)\b", sent)) - own:
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
        elif label and not row.get("tranche_size_final"):
            # A NAMED tranche with no size is a parse failure, not an absence.
            # These previously carried an empty flag string and slipped past
            # check_tranche_sum, which returns n/a when any size is missing.
            row["tranche_size_flags"] = ";".join(
                x for x in [row.get("tranche_size_flags"),
                            "tranche_size_missing"] if x)
        row["stated_tranche_count"] = stated
        row["tranche_flags"] = ";".join(flags)
        rows.append(row)
    return rows


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
    return abs(delta) <= 0.01, (
        "tranches=%s sum=%.0f deal=%.0f delta=%+.1f%%"
        % (sizes, total, whole, delta * 100))
