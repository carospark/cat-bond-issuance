"""Sibling registry: evidence-based cross-deal contamination detection.

The year heuristic in parse_deal says "distrust this sentence". This says
"that figure IS Windmill I's" -- it matches extracted values against the known
values of *earlier deals in the same programme*, so a finding names its source.

Two sources of sibling truth:
  index    every earlier sibling's published size, available immediately from
           data/queue.csv with no crawl ordering required
  parsed   every field of siblings already parsed this run, which is why the
           crawl goes oldest-first within each family

A match alone is NOT proof: Windmill III 2024 and 2026 are both genuinely
EUR 100m. So a match only counts as contamination when it coincides with a
backward marker (an earlier year, or the sibling's own name) in the sentence
that carried the value. A bare match is reported as `coincidental_match` and
changes nothing.
"""

import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from parse_deal import (_money_to_number, _clean, sentences,    # noqa: E402
                        _series_tokens, MONEY_RE)

COMPARATIVE = re.compile(
    r"\b(previous|prior|predecessor|last year|earlier|maturing|compared to|"
    r"which eventually|that\s+\d{4})\b", re.IGNORECASE)

# Audited by PROVENANCE, not field name. A Tier-1 value cannot be contaminated
# by a sentence (FloodSmart's genuine $575m was flagged because its 2021-1
# sibling was also $575m), so `size` is out -- but so is any tranche final
# that merely copies Tier 1. The prose-mined launch size, which IS what
# Windmill I's $46m contaminated, is in.
CHECK_FIELDS = ["expected_loss", "attachment_probability", "spread_risk_margin",
                "maturity_date"]
TRANCHE_FIELDS = ("tranche_size_at_launch", "tranche_size_final",
                  "expected_loss", "attachment_probability", "spread_risk_margin")
PCT_RE = re.compile(r"[\d.]+\s*%")


def _numeric(text):
    """Comparable number for a money or percent string, else None."""
    if not text:
        return None
    t = str(text)
    if "%" in t:
        m = re.search(r"([\d.]+)\s*%", t)
        return float(m.group(1)) if m else None
    return _money_to_number(t)


class SiblingRegistry:
    """Known values of earlier deals, keyed by deal_url."""

    def __init__(self, queue_csv=None):
        q = pd.read_csv(queue_csv or ROOT / "data" / "queue.csv",
                        keep_default_na=False, dtype=str)
        self.meta = {r.deal_url: r for _, r in q.iterrows()}
        # url -> [{"deal", "field", "raw", "num"}] contributed by earlier siblings
        self.known = {}
        for _, r in q.iterrows():
            entries = []
            for i, sz in enumerate(x for x in r.sibling_sizes.split("|") if x):
                # queue.csv lists sibling sizes oldest-first
                for part in MONEY_RE.findall(sz):
                    entries.append({"deal": "%s (sibling %d)" % (r.family, i + 1),
                                    "field": "size", "raw": _clean(part),
                                    "num": _numeric(part)})
            self.known[r.deal_url] = entries
        self._parsed = {}

    def add_parsed(self, deal_url, record):
        """Register a parsed deal so its later siblings can see its values."""
        meta = self.meta.get(deal_url)
        if meta is None:
            return
        vals = []
        for f in CHECK_FIELDS:
            v = record.get(f, {}).get("value") if isinstance(record.get(f), dict) else None
            if v and _numeric(v) is not None:
                vals.append({"deal": meta.issuer_name, "field": f,
                             "raw": v, "num": _numeric(v)})
        self._parsed.setdefault(meta.family, []).append((int(meta.family_seq), vals))

    def _siblings_for(self, deal_url):
        meta = self.meta.get(deal_url)
        entries = list(self.known.get(deal_url, []))
        if meta is not None:
            for seq, vals in self._parsed.get(meta.family, []):
                if seq < int(meta.family_seq):
                    entries.extend(vals)
        return entries

    def audit(self, deal_url, record, tranches=()):
        """Findings for one parsed deal. Reports; never mutates the record."""
        prose = record["_meta"]["full_details_text"] or ""
        sents = sentences(prose)   # not `sentences` -- that shadows the import
        meta = self.meta.get(deal_url)
        issue_year = None
        m = re.search(r"(19\d\d|20\d\d)", record["date_of_issue"]["value"] or "")
        if m:
            issue_year = int(m.group(1))
        # Transformer platforms (Seaside, Eclipse, Artex ...) share a vehicle,
        # not a programme; their prose never cites an earlier cell, and 68
        # "sibling sizes" of small round numbers would match by accident.
        if meta is not None and getattr(meta, "family_kind", "") == "platform":
            return []
        siblings = self._siblings_for(deal_url)
        if not siblings:
            return []
        own_series = _series_tokens(meta.issuer_name if meta is not None else "") \
            | _series_tokens(record["deal_name"]["value"] or "")

        candidates = [(f, record[f]["value"]) for f in CHECK_FIELDS
                      if isinstance(record.get(f), dict) and record[f]["value"]]
        launch = next((h["value"] for h in (record["size_history"]["value"] or [])
                       if h["state"] == "launch"), None)
        if launch:
            candidates.append(("size_history:launch", launch))
        for t in tranches:
            tier1_final = "final_from_tier1" in (t.get("tranche_size_flags") or "")
            for f in TRANCHE_FIELDS:
                if f == "tranche_size_final" and tier1_final:
                    continue  # copied from the summary box, not mined
                if t.get(f):
                    candidates.append(("%s:%s" % (t["tranche_id"], f), t[f]))

        findings = []
        for field, value in candidates:
            num = _numeric(value)
            if num is None:
                continue
            hits = [s for s in siblings
                    if s["num"] is not None and abs(s["num"] - num) < 1e-9]
            if not hits:
                continue
            # Hosts by NUMBER: "$4m" (summary-box form) never appears in prose
            # that says "$4 million", so a string test found no host and
            # every such verdict was silently "coincidental".
            hosts = [s for s in sents
                     if any(_numeric(tok) is not None and abs(_numeric(tok) - num) < 1e-9
                            for tok in MONEY_RE.findall(s) + PCT_RE.findall(s))]
            backward = []
            for h in hosts:
                yrs = [int(y) for y in re.findall(r"\b((?:19|20)\d\d)\b", h)]
                # Strictly earlier than the issue year -- the parser's rule.
                # `< issue_year - 1` here let ResRe 2019-1's coupon pass as
                # coincidental on the 2020 page.
                if (issue_year and any(y < issue_year for y in yrs)) \
                        or (_series_tokens(h) - own_series) \
                        or COMPARATIVE.search(h):
                    backward.append(h)
            findings.append({
                "deal": meta.issuer_name if meta is not None else deal_url,
                "family": meta.family if meta is not None else "",
                "field": field, "value": value,
                "matches_sibling": hits[0]["deal"],
                "sibling_field": hits[0]["field"],
                "verdict": "LIKELY_CONTAMINATION" if backward else "coincidental_match",
                "evidence": (backward[0][:110] if backward
                             else (hosts[0][:110] if hosts else "")),
            })
        return findings


if __name__ == "__main__":
    from fetch import fetch
    from parse_deal import parse_deal, parse_tranches

    reg = SiblingRegistry()
    q = pd.read_csv(ROOT / "data" / "queue.csv", keep_default_na=False, dtype=str)
    cached = {p.name for p in (ROOT / "raw").glob("*.html")}

    from fetch import _cache_path
    todo = [r for _, r in q.iterrows() if _cache_path(r.deal_url).exists()]
    print("auditing %d cached deals, oldest-first within family\n" % len(todo))
    all_f = []
    for r in todo:                     # queue order = ancestors first
        rec = parse_deal(fetch(r.deal_url), deal_url=r.deal_url)
        tr = parse_tranches(rec)
        all_f.extend(reg.audit(r.deal_url, rec, tr))
        reg.add_parsed(r.deal_url, rec)

    if all_f:
        df = pd.DataFrame(all_f)
        df.to_csv(ROOT / "data" / "sibling_audit.csv", index=False)
        with pd.option_context("display.width", 230, "display.max_colwidth", 46):
            print(df.to_string(index=False))
        print("\n", df.verdict.value_counts().to_dict())
    else:
        print("no sibling matches found")
