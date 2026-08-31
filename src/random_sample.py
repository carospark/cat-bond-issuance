"""Measure the parser on a RANDOM sample, not a hand-picked one.

Every page tested so far was chosen because it was tricky, or because a
reviewer flagged it. That biases every violation count upward and means the
boring middle of the corpus has never been seen. This samples uniformly from
the uncached deals and reports a rate.
"""

import random
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from fetch import fetch, _cache_path                      # noqa: E402
from parse_deal import parse_deal, parse_tranches, TIER1_KEYS  # noqa: E402
from validate import validate                             # noqa: E402

N = int(sys.argv[1]) if len(sys.argv) > 1 else 60
SEED = 20260831


def main():
    q = pd.read_csv(ROOT / "data" / "queue.csv", keep_default_na=False, dtype=str)
    # Sample from ALL deals, not the uncached ones. Sampling the uncached pool
    # meant the set changed every run -- the first 60 became cached and the
    # next run measured a different 60, so before/after was never comparable.
    pool = [r for _, r in q.iterrows()]
    random.seed(SEED)
    sample = random.sample(pool, min(N, len(pool)))
    n_new = sum(1 for r in sample if not _cache_path(r.deal_url).exists())
    print("sampling %d of %d deals (seed %d); %d not yet cached\n"
          % (len(sample), len(pool), SEED, n_new))

    rows, findings = [], []
    for i, r in enumerate(sample, 1):
        try:
            rec = parse_deal(fetch(r.deal_url), deal_url=r.deal_url)
            trs = parse_tranches(rec)
        except Exception as exc:                            # noqa: BLE001
            rows.append({"slug": r.deal_url.rstrip("/").rsplit("/", 1)[-1][:40],
                         "year": r.date_text[-4:], "crashed": type(exc).__name__,
                         "t1": 0, "tranches": 0, "viol": 0, "warn": 0})
            continue
        f = validate(rec, trs, r)
        for x in f:
            findings.append({"slug": r.deal_url.rstrip("/").rsplit("/", 1)[-1][:34], **x})
        rows.append({
            "slug": r.deal_url.rstrip("/").rsplit("/", 1)[-1][:40],
            "year": r.date_text[-4:], "crashed": "",
            "t1": sum(1 for k in TIER1_KEYS if rec[k]["value"]),
            "tranches": len(trs),
            "viol": sum(1 for x in f if x["severity"] == "VIOLATION"),
            "warn": sum(1 for x in f if x["severity"] == "WARN"),
        })
        if i % 10 == 0:
            print("  ...%d/%d" % (i, len(sample)))

    df = pd.DataFrame(rows)
    df.to_csv(ROOT / "data" / "random_sample.csv", index=False)
    pd.DataFrame(findings).to_csv(ROOT / "data" / "random_sample_findings.csv", index=False)

    print("\n=== RESULT over %d random deals ===" % len(df))
    print("crashes:                %d" % (df.crashed != "").sum())
    print("deals with a VIOLATION: %d (%.0f%%)" % ((df.viol > 0).sum(),
                                                   100 * (df.viol > 0).mean()))
    print("violations per deal:    %.2f" % df.viol.mean())
    print("warnings per deal:      %.2f" % df.warn.mean())
    print("mean Tier-1 fill:       %.1f/9" % df.t1.mean())
    print("\nby decade:")
    df["dec"] = df.year.astype(int) // 10 * 10
    print(df.groupby("dec").agg(deals=("slug", "size"), t1=("t1", "mean"),
                                viol=("viol", "mean")).round(2).to_string())
    if findings:
        print("\nviolation types:")
        print(pd.DataFrame(findings).groupby(["severity", "check"]).size().to_string())


if __name__ == "__main__":
    main()
