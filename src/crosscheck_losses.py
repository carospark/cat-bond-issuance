"""Cross-check the losses table against page-derived tranche lifecycle.

`data/losses.csv` is the publisher's settled-loss table (one row per loss
event, `loss_pct_derived` where the row states enough to derive it).
`apply_tranche_lifecycle` reads the SAME facts from the deal page's prose.
Where both exist they must agree; where the page is silent, the sentence that
should have carried it is the next pattern to write (backlog 4).

Writes data/validation_dashboards/losses_crosscheck.csv, one row per settled
loss: table pct, page pct(s), verdict in {agree, disagree, page_silent}.
"""

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from fetch import fetch                                   # noqa: E402
from parse_deal import parse_deal, parse_tranches         # noqa: E402

BASE = "https://www.artemis.bm/deal-directory/"


def main():
    losses = pd.read_csv(ROOT / "data" / "losses.csv", keep_default_na=False, dtype=str)
    losses = losses[(losses.deal_slug != "") & (losses.is_settled == "True")]
    out = []
    for _, r in losses.iterrows():
        rec = parse_deal(fetch(BASE + r.deal_slug + "/"), deal_url=BASE + r.deal_slug + "/")
        rows = parse_tranches(rec)
        page = [(t["tranche_id"], t["principal_loss_pct"], t.get("lifecycle_evidence") or "")
                for t in rows if t.get("principal_loss_pct") is not None]
        table = float(r.loss_pct_derived) if r.loss_pct_derived else None
        if not page:
            verdict = "page_silent"
        elif table is not None and any(abs(p[1] - table) < 1 for p in page):
            verdict = "agree"
        else:
            verdict = "disagree"
        out.append({"deal_slug": r.deal_slug, "loss_status": r.loss_status,
                    "table_pct": r.loss_pct_derived,
                    "page_pct": ";".join("%s=%s" % (p[0], p[1]) for p in page),
                    "page_evidence": page[0][2][:140] if page else "",
                    "verdict": verdict})
    df = pd.DataFrame(out)
    path = ROOT / "data" / "validation_dashboards" / "losses_crosscheck.csv"
    df.to_csv(path, index=False, encoding="utf-8")
    print("wrote %s (%d settled losses): %s" % (path, len(df), df.verdict.value_counts().to_dict()))


if __name__ == "__main__":
    main()
