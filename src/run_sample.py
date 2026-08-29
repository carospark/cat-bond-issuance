"""Run parse_deal over a small sample, save data/sample.csv, report fill rates.

Diagnostic only: reports suspected parse failures, fixes nothing.
"""

import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch import fetch
from parse_deal import parse_deal

ROOT = Path(__file__).resolve().parent.parent
URLS = [u.strip() for u in (Path(sys.argv[1]).read_text().split()) if u.strip()]


def main():
    records = []
    for url in URLS:
        rec = parse_deal(fetch(url), deal_url=url)
        flat = {"deal_slug": url.rstrip("/").rsplit("/", 1)[-1][:38]}
        for key, f in rec.items():
            if key == "_meta":
                flat["_page_flags"] = ";".join(f["page_flags"]) or ""
                flat["_prose_states"] = ";".join(f["prose_states"])
                flat["_prose_chars"] = f["prose_chars"]
                continue
            flat[key] = f["value"]
            flat[f"{key}__conf"] = f["confidence"]
            flat[f"{key}__flags"] = ";".join(str(x) for x in f["flags"] if x != "not_found")
        records.append(flat)

    df = pd.DataFrame(records)
    out = ROOT / "data" / "sample.csv"
    df.to_csv(out, index=False, encoding="utf-8")
    print(f"\nwrote {out}  ({len(df)} rows x {len(df.columns)} cols)")
    return df


if __name__ == "__main__":
    main()
