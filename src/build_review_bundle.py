"""Build a human-reviewable CSV bundle over every cached page.

Emits, into data/:
  deals.csv          one row per deal, wide (value + __conf + __flags per field)
  tranches.csv       one row per tranche
  review_long.csv    ONE ROW PER EXTRACTED FIELD -- the sheet to eyeball
  data_dictionary.csv what every column and flag means
"""

import hashlib
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from fetch import fetch, _cache_path                           # noqa: E402
from parse_deal import (parse_deal, parse_tranches, check_tranche_sum,  # noqa: E402
                        TIER1_KEYS, FIELD_TIER)

TRANCHE_ONLY = {"expected_loss", "attachment_probability", "exhaustion_probability",
                "spread_risk_margin", "conditional_severity"}


def cached_urls():
    """Queue rows whose page is already cached, in crawl order.

    Asks fetch() for the cache path rather than recomputing the hash: this
    duplicated the key derivation, so normalising the URL in fetch() silently
    made every lookup miss and the builder emitted zero rows.
    """
    q = pd.read_csv(ROOT / "data" / "queue.csv", keep_default_na=False, dtype=str)
    return [r for _, r in q.iterrows() if _cache_path(r.deal_url).exists()]


def main():
    deals, tranches, long_rows = [], [], []
    for r in cached_urls():
        rec = parse_deal(fetch(r.deal_url), deal_url=r.deal_url)
        trs = parse_tranches(rec)
        slug = r.deal_url.rstrip("/").rsplit("/", 1)[-1]
        ok, detail = check_tranche_sum(rec, trs)

        row = {"deal_slug": slug, "family": r.family, "family_seq": r.family_seq,
               "date_text": r.date_text, "index_issuer_name": r.issuer_name}
        for key, f in rec.items():
            if key == "_meta" or key in TRANCHE_ONLY:
                continue
            row[key] = f["value"]
            row[key + "__conf"] = f["confidence"]
            row[key + "__flags"] = ";".join(str(x) for x in f["flags"] if x != "not_found")
            if f.get("raw_value") not in (None, f["value"]):
                row[key + "__raw"] = f["raw_value"]

            long_rows.append({
                "deal_slug": slug, "date_text": r.date_text, "family": r.family,
                "level": "deal", "tranche_id": "", "field": key,
                "value": f["value"], "raw_value": f.get("raw_value"),
                "confidence": f["confidence"], "field_tier": FIELD_TIER.get(key, "core"),
                "source": "tier1" if key in TIER1_KEYS else "tier2",
                "method": f["method"],
                "flags": ";".join(str(x) for x in f["flags"] if x != "not_found"),
                "evidence": (str(f["evidence"])[:160] if f["evidence"] else ""),
                "deal_url": r.deal_url,
            })
        row["tranche_sum_check"] = {True: "OK", False: "MISMATCH", None: "n/a"}[ok]
        row["tranche_sum_detail"] = detail
        row["_page_flags"] = ";".join(rec["_meta"]["page_flags"])
        row["_prose_chars"] = rec["_meta"]["prose_chars"]
        row["_prose_states"] = ";".join(rec["_meta"]["prose_states"])
        deals.append(row)

        for t in trs:
            tranches.append({"deal_slug": slug, "family": r.family,
                             "date_text": r.date_text, **t})
            for k, v in t.items():
                if k in ("tranche_id",) or k.endswith(("__conf", "__flags")):
                    continue
                long_rows.append({
                    "deal_slug": slug, "date_text": r.date_text, "family": r.family,
                    "level": "tranche", "tranche_id": t["tranche_id"], "field": k,
                    "value": v, "raw_value": None,
                    "confidence": t.get(k + "__conf"), "field_tier": "core",
                    "source": "tier2", "method": "tranche",
                    "flags": t.get(k + "__flags", "") or t.get("tranche_flags", ""),
                    "evidence": "", "deal_url": r.deal_url,
                })

    d, t = pd.DataFrame(deals), pd.DataFrame(tranches)
    lg = pd.DataFrame(long_rows)
    d.to_csv(ROOT / "data" / "deals.csv", index=False, encoding="utf-8")
    t.to_csv(ROOT / "data" / "tranches.csv", index=False, encoding="utf-8")
    lg.to_csv(ROOT / "data" / "review_long.csv", index=False, encoding="utf-8")
    print("deals.csv       %d rows x %d cols" % d.shape)
    print("tranches.csv    %d rows x %d cols" % t.shape)
    print("review_long.csv %d rows x %d cols" % lg.shape)
    print("\nconfidence mix (review_long, values present only):")
    print(lg[lg.value.notna() & (lg.value.astype(str) != "")]
          .confidence.value_counts(dropna=False).to_string())
    print("\ntranche_sum_check:", d.tranche_sum_check.value_counts().to_dict())
    return d, t, lg


if __name__ == "__main__":
    main()
