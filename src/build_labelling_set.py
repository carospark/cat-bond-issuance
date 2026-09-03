"""Emit a BLIND labelling sheet for ground-truth accuracy measurement.

Violations only count what validate.py knows to check, and the constraint layer
now actively selects values that satisfy one of those checks, so a wrong value
satisfying every invariant is invisible to the benchmark. This produces the
sheet needed to measure accuracy directly.

Nothing here touches the parser. The sheet contains the deal URL, the field
names, and empty cells. In particular the TRANCHE rows are fixed blank slots
rather than one row per parsed tranche: emitting the parser's tranche count
would tell the labeller the answer to one of the things being measured.

    ./.venv/bin/python src/build_labelling_set.py [n_deals] [tranche_slots]

Fill in `true_value` from the page. Leave it empty only where the page does
not state the value; write NOT_STATED so an absence is distinguishable from an
unlabelled row. Then score with src/score_labels.py.
"""

import random
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from fetch import _cache_path                     # noqa: E402

SEED = 20260903
N = int(sys.argv[1]) if len(sys.argv) > 1 else 12
# Most deals are single-tranche, so slots are mostly blank. Four covers the
# large majority; a deal with more is rare and can be noted in `note`.
TRANCHE_SLOTS = int(sys.argv[2]) if len(sys.argv) > 2 else 4

DEAL_FIELDS = [
    "size", "cedent_sponsor", "date_of_issue", "trigger_type",
    "expected_loss", "attachment_probability", "spread_risk_margin",
    "maturity_scheduled", "term_length",
]
TRANCHE_FIELDS = [
    "tranche_id", "tranche_size_final", "expected_loss",
    "attachment_probability", "spread_risk_margin",
]


def main():
    q = pd.read_csv(ROOT / "data" / "queue.csv", keep_default_na=False, dtype=str)
    q = q[[_cache_path(r.deal_url).exists() for _, r in q.iterrows()]]
    q["decade"] = q.date_text.str[-4:].astype(int) // 10 * 10

    # Stratify by decade so the sheet is not all recent deals; era drives how
    # much prose exists and therefore how hard extraction is.
    random.seed(SEED)
    picked, per = [], max(1, N // max(1, q.decade.nunique()))
    for _, grp in q.groupby("decade"):
        rows = [r for _, r in grp.iterrows()]
        picked += random.sample(rows, min(per, len(rows)))
    pool = [r for _, r in q.iterrows() if r.deal_url not in {p.deal_url for p in picked}]
    picked += random.sample(pool, min(N - len(picked), len(pool)))

    out = []
    for r in picked:
        slug = r.deal_url.rstrip("/").rsplit("/", 1)[-1]
        for f in DEAL_FIELDS:
            out.append({"deal_slug": slug, "deal_url": r.deal_url,
                        "level": "deal", "slot": "", "field": f,
                        "true_value": "", "note": ""})
        for i in range(1, TRANCHE_SLOTS + 1):
            for f in TRANCHE_FIELDS:
                out.append({"deal_slug": slug, "deal_url": r.deal_url,
                            "level": "tranche", "slot": i, "field": f,
                            "true_value": "", "note": ""})

    df = pd.DataFrame(out)
    path = ROOT / "data" / "labels_blank.csv"
    df.to_csv(path, index=False, encoding="utf-8")
    print("wrote %s" % path)
    print("  %d deals across %d decades" % (len(picked), len({p.decade for p in picked})))
    print("  %d rows to label (%d deal-level, %d tranche slots)"
          % (len(df), (df.level == "deal").sum(), (df.level == "tranche").sum()))
    print("\nfill `true_value` from the page; use NOT_STATED where the page is")
    print("silent, and leave tranche slots blank beyond the number that exist.")
    print("\ndeals:")
    for p in sorted(picked, key=lambda x: x.date_text[-4:]):
        print("  %-46s %s" % (p.issuer_name[:46], p.date_text))


if __name__ == "__main__":
    main()
