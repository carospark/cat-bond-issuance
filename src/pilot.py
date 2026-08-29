"""Stratified era pilot: 5 deals per decade, to find template breaks.

The one thing that would force a structural change mid-crawl is Artemis having
used a different page template in earlier eras. This samples across decades and
reports fill rates and page-level flags per era, so an era branch (if needed)
is discovered on 20 requests rather than 1,311.
"""

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from fetch import fetch                                   # noqa: E402
from parse_deal import parse_deal, parse_tranches, TIER1_KEYS, FIELD_TIER  # noqa: E402

PER_DECADE = 5
CORE_T2 = ["expected_loss", "attachment_probability", "spread_risk_margin",
           "maturity_scheduled", "term_length"]


def main():
    q = pd.read_csv(ROOT / "data" / "queue.csv", keep_default_na=False, dtype=str)
    q["decade"] = q.decade.astype(int)
    picks = []
    for dec, grp in q.groupby("decade"):
        idx = [int(round(i)) for i in
               pd.Series(range(len(grp))).quantile(
                   [j / (PER_DECADE - 1) for j in range(PER_DECADE)]).tolist()]
        picks.append(grp.iloc[sorted(set(idx))])
    sample = pd.concat(picks)
    print("pilot sample: %d deals across %d decades\n"
          % (len(sample), sample.decade.nunique()))

    rows = []
    for _, r in sample.iterrows():
        rec = parse_deal(fetch(r.deal_url), deal_url=r.deal_url)
        t1 = sum(1 for k in TIER1_KEYS if rec[k]["value"])
        t1_raw = sum(1 for k in TIER1_KEYS if rec[k].get("raw_value"))
        t2 = sum(1 for k in CORE_T2 if rec[k]["value"])
        tr = parse_tranches(rec)
        rows.append({
            "decade": r.decade, "date": r.date_text, "deal": r.issuer_name[:38],
            "tier1": f"{t1}/{len(TIER1_KEYS)}", "t1_present": t1_raw,
            "core_t2": f"{t2}/{len(CORE_T2)}", "tranches": len(tr),
            "prose_chars": rec["_meta"]["prose_chars"],
            "page_flags": ";".join(rec["_meta"]["page_flags"])[:46],
        })

    df = pd.DataFrame(rows)
    with pd.option_context("display.width", 220, "display.max_colwidth", 40):
        print(df.to_string(index=False))

    print("\n=== BY DECADE ===")
    df["t1n"] = df.tier1.str.split("/").str[0].astype(int)
    df["t2n"] = df.core_t2.str.split("/").str[0].astype(int)
    agg = df.groupby("decade").agg(
        deals=("deal", "size"),
        tier1_filled=("t1n", "mean"),
        tier1_labels_present=("t1_present", "mean"),
        core_t2_filled=("t2n", "mean"),
        prose_chars=("prose_chars", "mean"),
        no_glance=("page_flags", lambda s: sum("no_at_a_glance" in x for x in s)))
    print(agg.round(1).to_string())
    flags = [f for s in df.page_flags for f in s.split(";") if f]
    print("\npage flags seen:", pd.Series(flags).value_counts().to_dict() or "none")


if __name__ == "__main__":
    main()
