"""Optional: refit archetype parameters from a real, locally-downloaded
Kaggle grocery dataset instead of the literature-informed defaults in
``recsys.profiles.ARCHETYPES``.

This script is intentionally **not imported by any runtime or test code** —
the core `recsys` package (profiles/recipes/inventory/model/evaluation/
simulation/economics) has zero dependency beyond what `pyproject.toml`'s
`dev` extra already installs, so a fresh clone always runs. This script adds
`pandas`/`scikit-learn` (`pip install -e '.[ml]'`) only for people who want
to run it.

## What it does

Expects the Kaggle "Instacart Market Basket Analysis" files
(https://www.kaggle.com/c/instacart-market-basket-analysis) under
``data/kaggle/instacart/`` (gitignored — see .gitignore; never commit the raw
CSVs, both per CONTRIBUTING.md and Kaggle's own redistribution terms):

    orders.csv, order_products__prior.csv, products.csv, departments.csv

For each user it computes:
  - cadence_days: mean `days_since_prior_order`
  - basket_size: mean items per order
  - department_diversity: distinct departments touched / total departments
  - reorder_ratio: mean `reordered` flag across order_products

...then runs k-means (k=4, matching the four archetypes already named in
``docs/research/persona_vxofi/rescue-domovoi-concept.md §6``) and prints
per-cluster summary statistics.

## What it deliberately does NOT do

It does not overwrite ``recsys.profiles.ARCHETYPES`` automatically. Product
and economic parameters get team review before they change
(``docs/decisions/001-recipe-first-poc.md``) — this script's job is to
produce numbers a maintainer can look at and decide to update by hand, not to
silently re-parametrize the model.

Run: ``python -m recsys.calibration.fit_from_kaggle [--data-dir PATH]``
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REQUIRED_FILES = ("orders.csv", "order_products__prior.csv", "products.csv", "departments.csv")


def _require_deps():
    try:
        import pandas as pd  # noqa: F401
        from sklearn.cluster import KMeans  # noqa: F401
        from sklearn.preprocessing import StandardScaler  # noqa: F401
    except ImportError as exc:  # pragma: no cover - exercised manually, not in CI
        raise SystemExit(
            "pandas/scikit-learn are required for calibration: "
            "install with `pip install -e '.[ml]'`."
        ) from exc


def _check_data_dir(data_dir: Path) -> None:
    missing = [f for f in REQUIRED_FILES if not (data_dir / f).exists()]
    if missing:
        raise SystemExit(
            f"Missing Kaggle files in {data_dir}: {missing}.\n"
            "Download 'Instacart Market Basket Analysis' from "
            "https://www.kaggle.com/c/instacart-market-basket-analysis, "
            f"unzip into {data_dir} (gitignored), and re-run."
        )


def compute_user_features(data_dir: Path):
    import pandas as pd

    orders = pd.read_csv(data_dir / "orders.csv")
    order_products = pd.read_csv(data_dir / "order_products__prior.csv")
    products = pd.read_csv(data_dir / "products.csv")
    departments = pd.read_csv(data_dir / "departments.csv")

    prior_orders = orders[orders["eval_set"] == "prior"] if "eval_set" in orders.columns else orders

    op = order_products.merge(prior_orders[["order_id", "user_id"]], on="order_id", how="inner")
    op = op.merge(products[["product_id", "department_id"]], on="product_id", how="left")

    n_departments = departments["department_id"].nunique() or 1

    basket_size = op.groupby("order_id").size().rename("basket_size")
    order_user = prior_orders.set_index("order_id")["user_id"]
    basket_by_user = basket_size.to_frame().join(order_user).groupby("user_id")["basket_size"].mean()

    cadence_by_user = prior_orders.groupby("user_id")["days_since_prior_order"].mean()
    reorder_by_user = op.groupby("user_id")["reordered"].mean()
    diversity_by_user = op.groupby("user_id")["department_id"].nunique() / n_departments

    features = pd.DataFrame(
        {
            "cadence_days": cadence_by_user,
            "basket_size": basket_by_user,
            "reorder_ratio": reorder_by_user,
            "department_diversity": diversity_by_user,
        }
    ).dropna()
    return features


def fit_clusters(features, k: int = 4, seed: int = 42):
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import StandardScaler

    scaler = StandardScaler()
    scaled = scaler.fit_transform(features.values)
    model = KMeans(n_clusters=k, random_state=seed, n_init=10)
    labels = model.fit_predict(scaled)
    return labels


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data/kaggle/instacart"),
        help="Directory containing the Instacart CSV files (default: data/kaggle/instacart)",
    )
    parser.add_argument("--k", type=int, default=4, help="Number of clusters (default: 4, one per archetype)")
    args = parser.parse_args()

    _require_deps()
    _check_data_dir(args.data_dir)

    features = compute_user_features(args.data_dir)
    if len(features) < args.k:
        raise SystemExit(f"Only {len(features)} users with complete features — not enough to cluster.")

    labels = fit_clusters(features, k=args.k)
    features = features.assign(cluster=labels)

    print(f"Fitted {args.k} clusters on {len(features)} users from {args.data_dir}\n")
    summary = features.groupby("cluster").agg(["mean", "count"])
    total = len(features)
    for cluster_id, row in summary.iterrows():
        share = row[("cadence_days", "count")] / total
        print(f"cluster {cluster_id}: population_share~={share:.2f}")
        print(f"  cadence_days_mean   = {row[('cadence_days', 'mean')]:.2f}")
        print(f"  basket_size_mean    = {row[('basket_size', 'mean')]:.2f}")
        print(f"  reorder_ratio_mean  = {row[('reorder_ratio', 'mean')]:.2f}  (proxy for repeat_probability)")
        print(f"  department_diversity= {row[('department_diversity', 'mean')]:.2f}  (proxy for discovery_acceptance)")
        print()
    print(
        "These are candidate parameters for recsys.profiles.ARCHETYPES — "
        "update them by hand after team review, this script does not write "
        "them automatically."
    )


if __name__ == "__main__":
    sys.exit(main() or 0)
