"""Systematic cross-field validation.

Written because per-field confidence is structurally blind to a whole class of
error: every value individually plausible, the RELATIONSHIPS between them
wrong. Both size bugs found so far (FloodSmart's swapped tranches, Kilimanjaro's
Class E holding the deal total) were of this kind, and both were catchable by
arithmetic on values already in hand.

The rule this encodes: enumerate every relationship that MUST hold, up front,
rather than adding one invariant per incident.

Sources of truth we can play off each other:
  index.csv vs detail page   the same deal published twice -- free cross-check
  parts vs whole             tranche sizes against the deal size
  arithmetic identities      EL = AP x severity, so EL <= AP
  economic necessity         spread must exceed EL or the note loses money
  self-description           prose says "two tranches"; we should find two
"""

import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from parse_deal import _money_to_number, _currency, sentences   # noqa: E402

WORD_COUNT = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}


def _pct(v):
    if not v:
        return None
    m = re.search(r"([\d.]+)\s*%", str(v))
    return float(m.group(1)) if m else None


def _same_money(a, b, tol=0.01):
    na, nb = _money_to_number(a or ""), _money_to_number(b or "")
    if not na or not nb:
        return None
    if _currency(a or "") != _currency(b or ""):
        return None
    return abs(na - nb) / nb <= tol


def validate(rec, tranches, index_row=None):
    """Return a list of findings. severity: VIOLATION | WARN | info."""
    out = []

    def add(sev, name, detail):
        out.append({"severity": sev, "check": name, "detail": detail})

    # --- 1. cross-source: the index published the same deal ----------------
    if index_row is not None:
        same = _same_money(rec["size"]["value"], index_row.size_text)
        if same is False:
            add("VIOLATION", "index_size_agrees",
                "detail=%s index=%s" % (rec["size"]["value"], index_row.size_text))
        if rec["date_of_issue"]["value"] and \
                rec["date_of_issue"]["value"].strip() != index_row.date_text.strip():
            add("VIOLATION", "index_date_agrees",
                "detail=%s index=%s" % (rec["date_of_issue"]["value"], index_row.date_text))
        det_sp = (rec["cedent_sponsor"].get("raw_value")
                  or rec["cedent_sponsor"]["value"] or "").strip()
        if det_sp and index_row.sponsor.strip() and det_sp != index_row.sponsor.strip():
            add("WARN", "index_sponsor_agrees",
                "detail=%r index=%r" % (det_sp[:40], index_row.sponsor[:40]))

    # --- 2. parts vs whole --------------------------------------------------
    for label, key in (("final", "tranche_size_final"),
                       ("launch", "tranche_size_at_launch")):
        sizes = [t.get(key) for t in tranches]
        if tranches and all(sizes) and len({_currency(s) for s in sizes}) == 1:
            whole = (rec["size"]["value"] if label == "final" else
                     next((h["value"] for h in (rec["size_history"]["value"] or [])
                           if h["state"] == "launch"), None))
            if whole and _currency(whole) == _currency(sizes[0]):
                total = sum(_money_to_number(s) or 0 for s in sizes)
                w = _money_to_number(whole) or 0
                if w and abs(total - w) / w > 0.01:
                    add("VIOLATION", "tranche_sum_%s" % label,
                        "sum=%.0f %s=%.0f delta=%+.1f%%"
                        % (total, whole, w, (total - w) / w * 100))

    # --- 2b. completeness: labelled tranches must all have sizes -----------
    # check_tranche_sum returns n/a when any size is missing, so an incomplete
    # extraction bypassed parts-vs-whole validation entirely. Say so instead.
    labelled = [t for t in tranches if t.get("tranche_id")]
    if labelled and rec["size"]["value"]:
        # A tranche the page says was never issued has no size as a matter of
        # fact, not of extraction. ResRe 2020: "The higher risk Class 12
        # tranche of notes will not be issued at all".
        missing = [t["tranche_id"] for t in labelled
                   if not t.get("tranche_size_final")
                   and "tranche_not_issued" not in (t.get("tranche_size_flags") or "")
                   and "no_final_size" not in (t.get("tranche_size_flags") or "")]
        if missing:
            add("VIOLATION", "tranche_sizes_complete",
                "%d/%d labelled tranches have no size: %s"
                % (len(missing), len(labelled), missing))

    # --- 2c. monetary layer bounds must be ordered -------------------------
    ap_pt = rec.get("attachment_point", {}).get("value")
    ex_pt = rec.get("exhaustion_point", {}).get("value")
    if ap_pt and ex_pt:
        a, b = _money_to_number(ap_pt), _money_to_number(ex_pt)
        if a and b and a >= b:
            add("VIOLATION", "attachment<exhaustion", "attach=%s exhaust=%s" % (ap_pt, ex_pt))

    # --- 3. prose self-description -----------------------------------------
    prose = rec["_meta"]["full_details_text"] or ""
    # Plural only, and never preceded by a digit or hyphen -- "Series 2021-21
    # tranche" is a series number, not a count. Skip sentences that describe a
    # SIBLING deal ("the two tranches from the Gateway Re 2024-1 deal"): note
    # that a same-year sibling defeats the year heuristic entirely, which is
    # why the sibling registry exists.
    for sent in sentences(prose):
        m = re.search(r"(?<![\d-])\b(one|two|three|four|five|six|\d{1,2})\s+tranches\b",
                      sent, re.I)
        if not (m and tranches):
            continue
        # Skip only if the sentence names a series OTHER than this deal's.
        # "Radnor Re 2020-2 ... has issued five tranches" is about itself;
        # "the two tranches from the Gateway Re 2024-1 deal" is not. A bare
        # 20\d\d-\d test cannot tell them apart, and filtering on it lost a
        # real 5-vs-3 undercount on Radnor.
        own = set(re.findall(r"\b(20\d\d-\d+)\b",
                             (index_row.issuer_name if index_row is not None else "")
                             + " " + (rec["deal_name"]["value"] or "")))
        cited = set(re.findall(r"\b(20\d\d-\d+)\b", sent))
        if (cited - own) or re.search(r"\bfrom the\b|\bprevious\b|\bprior\b",
                                      sent, re.I):
            continue  # describes another deal
        tok = m.group(1).lower()
        stated = int(tok) if tok.isdigit() else WORD_COUNT.get(tok)
        if stated and stated != len(tranches):
            sev = "VIOLATION" if stated > len(tranches) else "WARN"
            add(sev, "tranche_count_matches_prose",
                "prose says %d, parsed %d%s" % (
                    stated, len(tranches),
                    " (no Class labels to split on)" if not any(
                        t.get("tranche_id") for t in tranches) else ""))
        break

    # --- 4. per-tranche arithmetic and economics ---------------------------
    for t in tranches:
        tid = t.get("tranche_id") or "-"
        el, ap = _pct(t.get("expected_loss")), _pct(t.get("attachment_probability"))
        ep, sp = _pct(t.get("exhaustion_probability")), _pct(t.get("spread_risk_margin"))
        if el and ap and el > ap:
            add("VIOLATION", "EL<=attachment_probability", "%s EL=%s AP=%s" % (tid, el, ap))
        if ep and el and ep > el:
            add("VIOLATION", "exhaustion<=EL", "%s EP=%s EL=%s" % (tid, ep, el))
        if el and sp and sp <= el:
            # NOT a hard invariant. Total investor return also includes the
            # collateral/risk-free yield, and Artemis EL and quoted spread can
            # reflect different model vintages or timing. EL 5% / spread 4% /
            # collateral 3% is still positive expected gross return. Worth a
            # look, not a correctness claim.
            add("WARN", "spread>EL_plausibility", "%s spread=%s EL=%s multiple=%.2f"
                % (tid, sp, el, sp / el))
        cs = t.get("conditional_severity")
        if cs is not None and cs > 1:
            add("VIOLATION", "severity<=1", "%s severity=%s" % (tid, cs))

    # --- 5. risk ordering across tranches (soft: structures differ) --------
    ranked = [(t.get("tranche_id"), _pct(t.get("attachment_probability")),
               _pct(t.get("spread_risk_margin"))) for t in tranches]
    ranked = [r for r in ranked if r[1] and r[2]]
    for i in range(len(ranked)):
        for j in range(len(ranked)):
            if i != j and ranked[i][1] > ranked[j][1] and ranked[i][2] < ranked[j][2]:
                add("WARN", "riskier_tranche_pays_more",
                    "%s AP=%s spread=%s vs %s AP=%s spread=%s"
                    % (ranked[i][0], ranked[i][1], ranked[i][2],
                       ranked[j][0], ranked[j][1], ranked[j][2]))
    return out
