"""Score parser output against hand-labelled ground truth.

Reports what the violation benchmark cannot:

    precision            of values EMITTED, the fraction correct
    recall               of values PRESENT on the page, the fraction found
    silent error rate    wrong AND passed validation -- the blind spot

and the question that decides whether the cheap benchmark is worth running:
does a violation actually predict a wrong value, or are the two unrelated?

    ./.venv/bin/python src/score_labels.py data/labels_filled.csv
"""

import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from fetch import fetch                                    # noqa: E402
from parse_deal import parse_deal, parse_tranches, _pct_to_float, _money_to_number  # noqa: E402
from validate import validate                              # noqa: E402

NOT_STATED = {"not_stated", "notstated", "none", "n/a", "-"}


def norm(v, field):
    """Compare on meaning, not spelling: $1.5bn == $1,500 million."""
    if v is None:
        return None
    s = str(v).strip()
    if not s or s.lower() in NOT_STATED:
        return None
    # Free-text Tier-1 fields (agents, perils, modeller) are compared on
    # normalised text: they are prose, not quantities, and an exact string
    # match would score a correct value as wrong over a comma.
    if field in ("placement_structuring_agents", "perils_covered",
                 "risk_modeller", "issuer", "cedent_sponsor", "ratings",
                 "trigger_type", "date_of_issue"):
        return ("raw", re.sub(r"[^a-z0-9 ]", " ", s.lower()))
    if "%" in s or field in ("expected_loss", "attachment_probability",
                             "spread_risk_margin"):
        n = _pct_to_float(s)
        return ("pct", round(n, 4)) if n is not None else ("raw", s.lower())
    if re.search(r"[$€£¥]|\d", s) and field in ("size", "tranche_size_final"):
        n = _money_to_number(s)
        return ("money", round(n, 2)) if n else ("raw", s.lower())
    return ("raw", re.sub(r"\s+", " ", s).strip().lower())


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "labels_filled.csv"
    lab = pd.read_csv(path, keep_default_na=False, dtype=str)
    lab = lab[lab.true_value.astype(str).str.strip() != ""]
    if lab.empty:
        print("no labelled rows in %s" % path)
        return

    rows = []
    for url, grp in lab.groupby("deal_url"):
        rec = parse_deal(fetch(url), deal_url=url)
        trs = parse_tranches(rec)
        flagged = {f["check"] for f in validate(rec, trs, None)}
        by_id = {str(t.get("tranche_id")).upper(): t for t in trs}

        for _, r in grp.iterrows():
            if r.level == "deal":
                got = rec.get(r.field, {}).get("value") if isinstance(
                    rec.get(r.field), dict) else None
            else:
                # Match the labeller's slot to a parsed tranche by its ID, which
                # the labeller supplied; slot order is not assumed to agree.
                tid = grp[(grp.slot == r.slot) & (grp.field == "tranche_id")]
                tid = tid.true_value.iloc[0].strip().upper() if len(tid) else ""
                t = by_id.get(tid if tid.startswith("CLASS") else "CLASS " + tid, {})
                got = t.get(r.field)
            rows.append({
                "deal": r.deal_slug, "level": r.level, "field": r.field,
                "truth": r.true_value, "got": got,
                "t": norm(r.true_value, r.field), "g": norm(got, r.field),
                "deal_flagged": bool(flagged),
            })

    df = pd.DataFrame(rows)
    df["emitted"] = df.g.notna()
    df["present"] = df.t.notna()
    df["correct"] = df.apply(lambda x: x.emitted and x.present and x.t == x.g, axis=1)
    df["wrong"] = df.emitted & df.present & ~df.correct
    df["missed"] = df.present & ~df.emitted
    df["invented"] = df.emitted & ~df.present
    df.to_csv(ROOT / "data" / "label_scores.csv", index=False)

    emitted, present = df.emitted.sum(), df.present.sum()
    print("=== %d labelled values across %d deals ===" % (len(df), df.deal.nunique()))
    print("  precision  %5.1f%%   (%d correct of %d emitted)"
          % (100 * df.correct.sum() / max(emitted, 1), df.correct.sum(), emitted))
    print("  recall     %5.1f%%   (%d found of %d present)"
          % (100 * df.correct.sum() / max(present, 1), df.correct.sum(), present))
    print("  wrong      %d      missed %d      invented %d"
          % (df.wrong.sum(), df.missed.sum(), df.invented.sum()))

    silent = df[df.wrong & ~df.deal_flagged]
    print("\n  SILENT ERRORS (wrong, and the deal passed validation): %d of %d wrong"
          % (len(silent), max(df.wrong.sum(), 1)))
    for _, x in silent.head(10).iterrows():
        print("     %-34s %-24s truth=%-16r got=%r"
              % (x.deal[:34], x.field, str(x.truth)[:16], str(x.got)[:16]))

    print("\n=== does a violation predict a wrong value? ===")
    per = df.groupby("deal").agg(any_wrong=("wrong", "any"),
                                 flagged=("deal_flagged", "first"))
    print(pd.crosstab(per.flagged, per.any_wrong).to_string())
    tp = ((per.flagged) & (per.any_wrong)).sum()
    print("  of %d deals with a wrong value, %d were flagged (%.0f%%)"
          % (per.any_wrong.sum(), tp, 100 * tp / max(per.any_wrong.sum(), 1)))

    print("\n=== by field ===")
    g = df.groupby("field").agg(n=("field", "size"), emitted=("emitted", "sum"),
                                correct=("correct", "sum"), wrong=("wrong", "sum"),
                                missed=("missed", "sum"))
    g["precision"] = (100 * g.correct / g.emitted.replace(0, pd.NA)).round(0)
    print(g.sort_values("wrong", ascending=False).to_string())


if __name__ == "__main__":
    main()
