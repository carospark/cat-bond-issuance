"""Build the crawl work queue: family-grouped, chronologically ascending.

Order matters for correctness, not tidiness. Artemis prose references
*predecessor* deals ("the notes issued by Ursa Re in 2014, which priced at
5%"), so a deal must be parsed only after its older siblings. Ascending order
within each family guarantees the sibling registry is populated before the deal
that cites it.

Emits data/queue.csv with family, family_seq (1 = oldest in family) and
sibling_sizes: the sizes of every EARLIER deal in the same family, which are
exactly the figures at risk of bleeding into this page.
"""

import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from measure_contamination import family          # noqa: E402

# Programme names carry a generation marker -- "Windmill I / II / III Re",
# "Kilimanjaro Re / II / III", "Sanders Re III", "Residential Reinsurance 2015"
# -- so the raw family name splits one programme into several. Stripping the
# roman numeral and any embedded year merges them, which is the whole point:
# Windmill II's contaminating $46m IS Windmill I's size.
ROMAN = r"\b(?:I{1,3}|IV|V|VI{0,3}|IX|X)\b"


def family_root(name):
    n = family(name)
    n = re.sub(ROMAN, " ", n)
    n = re.sub(r"\b(?:19|20)\d\d\b", " ", n)
    return re.sub(r"\s+", " ", n).strip(" ,-")

MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def month_ordinal(date_text):
    parts = str(date_text).split()
    if len(parts) != 2:
        return 0
    return int(parts[1]) * 12 + MONTHS.get(parts[0], 0)


def main():
    df = pd.read_csv(ROOT / "data" / "index.csv", keep_default_na=False, dtype=str)
    df["family"] = df.issuer_name.map(family_root)
    df["ord"] = df.date_text.map(month_ordinal)
    df["year"] = df.date_text.str[-4:].astype(int)
    df["decade"] = df.year // 10 * 10

    # Families ordered by their earliest deal; deals ascending within family.
    first = df.groupby("family")["ord"].min().rename("family_first")
    df = df.join(first, on="family").sort_values(
        ["family_first", "family", "ord"], kind="stable").reset_index(drop=True)
    df["family_seq"] = df.groupby("family").cumcount() + 1
    df["family_size"] = df.groupby("family")["family"].transform("size")

    # Sizes of earlier siblings: the figures most likely to contaminate.
    sib = []
    for fam, grp in df.groupby("family", sort=False):
        seen = []
        for _, r in grp.iterrows():
            sib.append((r.deal_url, "|".join(seen)))
            seen.append(r.size_text)
    sib = dict(sib)
    df["sibling_sizes"] = df.deal_url.map(sib)

    cols = ["family", "family_seq", "family_size", "issuer_name", "sponsor",
            "size_text", "date_text", "year", "decade", "deal_url", "sibling_sizes"]
    df[cols].to_csv(ROOT / "data" / "queue.csv", index=False, encoding="utf-8")
    print("wrote data/queue.csv  %d rows" % len(df))
    print("\nfirst 8 of the queue (oldest families first):")
    print(df[["family", "family_seq", "issuer_name", "date_text"]]
          .head(8).to_string(index=False))
    multi = df[df.family_size > 1]
    print("\n%d deals in %d serial families; %d have >=1 earlier sibling"
          % (len(multi), multi.family.nunique(), (df.family_seq > 1).sum()))
    print("\nexample with sibling context:")
    w = df[df.family.str.contains("Windmill")][
        ["family", "family_seq", "issuer_name", "size_text", "sibling_sizes"]]
    print(w.to_string(index=False))


if __name__ == "__main__":
    main()
