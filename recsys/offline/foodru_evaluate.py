"""Compare static matching results and evaluate fixed, agent-labelled pairs.

No HTTP requests. Default baseline is the committed v1 result; alternatively
pass a directory with the original matches.json and summary.json.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path

from recsys.offline.foodru import DEFAULT_CATALOG, DEFAULT_OUTPUT, ROOT, write_json
from recsys.offline.foodru_matching import NameIndex, assess_candidate


def metrics(rows: list[dict], prediction: str) -> dict:
    counts = Counter()
    for row in rows:
        if row["label"] is None:
            continue
        expected, actual = row["label"], row[prediction]
        counts["tp" if expected and actual else "fn" if expected else "fp" if actual else "tn"] += 1
    tp, fp, fn = counts["tp"], counts["fp"], counts["fn"]
    return {**{key: counts[key] for key in ("tp", "fp", "tn", "fn")},
            "labelled_pairs": sum(counts.values()),
            "sample_precision": round(tp / (tp + fp), 4) if tp + fp else None,
            "sample_recall": round(tp / (tp + fn), 4) if tp + fn else None}


def evaluate(output: Path, catalog_path: Path, baseline: dict, baseline_summary: dict, cases: dict) -> dict:
    catalog = json.loads(catalog_path.read_text())["products"]
    recipes = json.loads((output / "recipes.json").read_text())["recipes"]
    matches = json.loads((output / "matches.json").read_text())["matches"]
    summary = json.loads((output / "summary.json").read_text())
    for field, path in (("catalog_sha256", catalog_path),
                        ("recipe_snapshot_sha256", output / "recipes.json")):
        if hashlib.sha256(path.read_bytes()).hexdigest() != summary[field]:
            raise ValueError("Input changed since build; rebuild before evaluation")
    if summary["catalog_sha256"] != baseline_summary["catalog_sha256"]:
        raise ValueError("Comparisons require the same product catalog")
    if summary["recipe_snapshot_sha256"] != baseline_summary["recipe_snapshot_sha256"]:
        raise ValueError("Comparisons require the same recipe snapshot")
    key = lambda row: f"{row['chain']}:{row['plu']}"
    old = {key(m): m for m in baseline["matches"]}
    products = {key(p): p for p in catalog}
    index = NameIndex(recipes)
    indices = {r["recipe_id"]: i for i, r in enumerate(recipes)}
    audit = []
    for case in cases["pairs"]:
        previous = old[case["product_key"]]
        # Cases were frozen from the top candidate of the baseline snapshot.
        if previous["candidates"][0]["recipe_id"] != case["recipe_id"]:
            raise ValueError("Evaluation cases do not belong to this baseline")
        candidate = assess_candidate(products[case["product_key"]], index, indices[case["recipe_id"]])
        audit.append({**case, "baseline_accept": previous["status"] == "matched",
                      "current_accept": not candidate["review_reasons"],
                      "current_reasons": candidate["review_reasons"],
                      "missing_recipe_ingredients": candidate["missing_recipe_ingredients"]})
    transitions = Counter()
    changes = []
    for match in matches:
        before = old[key(match)]
        transition = f"{before['status']}->{match['status']}"
        transitions[transition] += 1
        recipe_changed = before["recipe_id"] != match["recipe_id"]
        if before["status"] != match["status"] or recipe_changed:
            changes.append({"product_key": key(match), "name": match["name"], "transition": transition,
                            "old_recipe_id": before["recipe_id"], "new_recipe_id": match["recipe_id"],
                            "old_candidate": before["candidates"][0]["title"] if before["candidates"] else None,
                            "new_candidate": match["candidates"][0]["title"] if match["candidates"] else None,
                            "review_reasons": match["candidates"][0]["review_reasons"] if match["candidates"] else []})
    report = {
        "schema_version": 1, "baseline_version": baseline_summary["matcher_version"],
        "current_version": summary["matcher_version"],
        "catalog_sha256": summary["catalog_sha256"], "recipe_snapshot_sha256": summary["recipe_snapshot_sha256"],
        "matches_sha256": hashlib.sha256((output / "matches.json").read_bytes()).hexdigest(),
        "case_set_sha256": hashlib.sha256(json.dumps(cases, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
        "label_origin": cases["label_origin"], "independent_human_evaluation": False,
        "sampling": cases["sampling"],
        "limitation": "Diagnostic development sample of fixed candidate pairs; not a holdout, not an estimate of accuracy of all selected products or manufacturer ingredients.",
        "baseline_counts": baseline_summary["status_counts"], "current_counts": summary["status_counts"],
        "transitions": dict(sorted(transitions.items())),
        "retained_matches_with_changed_recipe": sum(c["transition"] == "matched->matched" for c in changes),
        "baseline_pair_metrics": metrics(audit, "baseline_accept"),
        "current_pair_metrics": metrics(audit, "current_accept"),
        "unlabelled_pairs": sum(row["label"] is None for row in audit),
        "audit_pairs": audit, "changes": changes,
    }
    write_json(output / "quality_report.json", report)
    with (output / "changes.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(changes[0]) if changes else ["product_key", "transition"], lineterminator="\n")
        writer.writeheader()
        for row in changes:
            writer.writerow({**row, "review_reasons": ", ".join(row["review_reasons"])})
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--baseline-ref", default="cf140c7")
    args = parser.parse_args()

    def load_baseline(name: str) -> dict:
        if args.baseline:
            return json.loads((args.baseline / name).read_text())
        return json.loads(subprocess.check_output(
            ["git", "show", f"{args.baseline_ref}:recsys/data/foodru/{name}"], cwd=ROOT))

    report = evaluate(args.output, args.catalog, load_baseline("matches.json"), load_baseline("summary.json"),
                      json.loads((args.output / "evaluation_cases.json").read_text()))
    print(json.dumps({key: value for key, value in report.items() if key not in {"audit_pairs", "changes"}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
