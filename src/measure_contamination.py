"""Measure cross-deal reference contamination on the cached pages.

Offline diagnostic. No network, no fixes. Answers one question: how often does
Artemis prose reference a *different* deal, and how often does a value we
currently extract sit inside such a sentence?

Three signals, scored per sentence:
  A past_year      a year token EARLIER than the deal's issue year. Forward
                   years are legitimate (maturity, term end) -- the first
                   draft flagged them and produced only false positives.
  B comparative     "previous", "last year", "which eventually", ...
  C foreign_name    a deal family name from index.csv that isn't this deal's
"""

import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from fetch import fetch                              # noqa: E402
from parse_deal import parse_deal, parse_tranches, TIER2_PATTERNS, sentences  # noqa: E402

BASE = "https://www.artemis.bm/deal-directory/"
PAGES = ["ibrd-car-jamaica-2026", "floodsmart-re-ltd-series-2024-1",
         "residential-reinsurance-2026-limited-series-2026-1",
         "seaside-re-series-2026-61", "windmill-ii-re-dac-2020",
         "kilimanjaro-re-ltd-series-2015-1", "gateway-re-ltd-series-2024-3",
         "george-town-re-ltd", "ursa-re-ltd-series-2015-1"]

COMPARATIVE = re.compile(
    r"\b(previous|prior|predecessor|last year|earlier|compared to|"
    r"which eventually|its (?:first|second|third)|the 20\d\d (?:deal|bond|issuance))\b",
    re.IGNORECASE)

FIGURE = re.compile(r"[$€£][\d,.]+|\d+(?:\.\d+)?\s*%")


def family(name):
    """Reduce 'Ursa Re Ltd. (Series 2015-1)' -> 'Ursa Re'."""
    n = re.sub(r"\(.*?\)", " ", str(name))
    n = re.sub(r"\bSeries\b.*", " ", n)
    n = re.sub(r"\b(Ltd|Limited|DAC|dac|Inc|SAC|plc|N\.V)\b\.?", " ", n)
    n = re.sub(r"[–—-]\s*$", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def main():
    idx = pd.read_csv(ROOT / "data" / "index.csv", keep_default_na=False, dtype=str)
    idx["slug"] = idx.deal_url.str.rstrip("/").str.rsplit("/", n=1).str[-1]
    idx["family"] = idx.issuer_name.map(family)
    # Gazetteer: distinct family names long enough to be unambiguous.
    gaz = sorted({f for f in idx.family if len(f) >= 8}, key=len, reverse=True)
    print(f"gazetteer: {len(gaz)} distinct deal families from {len(idx)} deals\n")

    rows, value_rows = [], []
    for slug in PAGES:
        rec = parse_deal(fetch(BASE + slug + "/"), deal_url=BASE + slug + "/")
        prose = rec["_meta"]["full_details_text"] or ""
        meta = idx[idx.slug == slug]
        own_family = family(meta.iloc[0].issuer_name) if len(meta) else ""
        sponsor = meta.iloc[0].sponsor if len(meta) else ""
        issue_year = int(re.search(r"(\d{4})", rec["date_of_issue"]["value"] or "0").group(1))

        sentences = sentences(prose)
        flagged = []
        for sent in sentences:
            years = {int(y) for y in re.findall(r"\b(19\d\d|20\d\d)\b", sent)}
            # Backwards only: a comparison is always to a PRIOR deal.
            a = any(y < issue_year - 1 for y in years)
            b = bool(COMPARATIVE.search(sent))
            foreign = [g for g in gaz
                       if g != own_family and g not in sponsor and g in sent]
            c = bool(foreign)
            if a or b or c:
                flagged.append((sent, a, b, c, foreign[:2]))

        with_fig = [f for f in flagged if FIGURE.search(f[0])]
        rows.append({
            "deal": slug[:34], "sentences": len(sentences),
            "flagged": len(flagged), "flagged_w_figure": len(with_fig),
            "A_year": sum(1 for f in flagged if f[1]),
            "B_comp": sum(1 for f in flagged if f[2]),
            "C_name": sum(1 for f in flagged if f[3]),
        })

        # Does any value we currently extract live in a flagged sentence?
        flagged_text = {f[0] for f in flagged}
        checks = [(f, rec[f]["value"]) for f in TIER2_PATTERNS]
        for t in parse_tranches(rec):
            for f in ("tranche_size_at_launch", "tranche_size_final",
                      "expected_loss", "attachment_probability",
                      "spread_risk_margin"):
                checks.append((f"{t['tranche_id']}:{f}", t.get(f)))
        for field, val in checks:
            if not val:
                continue
            hosts = [s for s in sentences if val in s]
            if hosts and all(h in flagged_text for h in hosts):
                sig = next(f for f in flagged if f[0] == hosts[0])
                value_rows.append({
                    "deal": slug[:30], "field": field, "value": val,
                    "signals": "".join(x for x, on in
                                       zip("ABC", (sig[1], sig[2], sig[3])) if on),
                    "foreign": ",".join(sig[4]) or "-",
                    "sentence": hosts[0][:88],
                })

    df = pd.DataFrame(rows)
    print(df.to_string(index=False))
    tot_s, tot_f = df.sentences.sum(), df.flagged.sum()
    print(f"\nTOTAL: {tot_f}/{tot_s} sentences flagged ({tot_f/tot_s:.0%}); "
          f"{df.flagged_w_figure.sum()} carry a figure "
          f"({df.flagged_w_figure.sum()/tot_s:.0%} of all sentences)")
    print(f"signal coverage: A_year={df.A_year.sum()} B_comp={df.B_comp.sum()} "
          f"C_name={df.C_name.sum()}")

    print("\n=== EXTRACTED VALUES SOURCED ONLY FROM FLAGGED SENTENCES ===")
    if value_rows:
        v = pd.DataFrame(value_rows)
        with pd.option_context("display.width", 240, "display.max_colwidth", 90):
            print(v.to_string(index=False))
        print(f"\n{len(v)} contaminated value(s) across {v.deal.nunique()} deal(s)")
    else:
        print("none")


if __name__ == "__main__":
    main()
