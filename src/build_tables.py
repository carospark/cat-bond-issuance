"""Build the normalised pair: data/deals.csv (one row per deal) and
data/tranches.csv (one row per tranche)."""

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from fetch import fetch                        # noqa: E402
from parse_deal import (parse_deal, parse_tranches, FIELD_TIER,   # noqa: E402
                        TIER1_KEYS, TRANCHE_ONLY)


def main(urls):
    deals, tranches = [], []
    for url in urls:
        rec = parse_deal(fetch(url), deal_url=url)
        slug = url.rstrip("/").rsplit("/", 1)[-1]

        row = {"deal_slug": slug}
        for key, f in rec.items():
            if key == "_meta" or key in TRANCHE_ONLY:
                continue
            row[key] = f["value"]
            row[key + "__conf"] = f["confidence"]
            row[key + "__flags"] = ";".join(str(x) for x in f["flags"] if x != "not_found")
            if "raw_value" in f and f["raw_value"] != f["value"]:
                row[key + "__raw"] = f["raw_value"]
        row["_page_flags"] = ";".join(rec["_meta"]["page_flags"])
        deals.append(row)

        for t in parse_tranches(rec):
            tranches.append({"deal_slug": slug, **t})

    d, t = pd.DataFrame(deals), pd.DataFrame(tranches)
    d.to_csv(ROOT / "data" / "deals.csv", index=False, encoding="utf-8")
    t.to_csv(ROOT / "data" / "tranches.csv", index=False, encoding="utf-8")
    print("deals.csv    %d rows x %d cols" % d.shape)
    print("tranches.csv %d rows x %d cols" % t.shape)
    return d, t


if __name__ == "__main__":
    urls = [u.strip() for u in Path(sys.argv[1]).read_text().split() if u.strip()]
    d, t = main(urls)
    print("\n--- tranches.csv ---")
    cols = ["deal_slug", "tranche_id", "tranche_size_at_launch",
            "tranche_size_final", "tranche_size_delta_pct", "expected_loss",
            "attachment_probability", "spread_risk_margin", "conditional_severity"]
    with pd.option_context("display.width", 220, "display.max_colwidth", 30):
        print(t[cols].to_string(index=False))
    print("\ntranches per deal:")
    print(t.groupby("deal_slug").size().to_string())
