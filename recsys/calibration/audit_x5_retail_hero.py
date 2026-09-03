"""Data audit for X5 Retail Hero (clients.csv, products.csv, purchases.csv).

Not on any runtime/test import path — same status as fit_from_kaggle.py.
Needs `pip install -e '.[ml]'` (pandas only; no sklearn needed here).

Why this script discovers rather than assumes: two independent research
passes (see docs/research/recsys/x5-retail-hero-data-audit.md) produced
detailed but *unverified* schemas for products.csv/purchases.csv — our own
spot-checks could only independently confirm a handful of fields
(clients.csv: client_id, first_issue_date, first_redeem_date, gender, age;
purchases.csv: transaction_datetime; products.csv: netto). Rather than
hard-coding the researched column list and silently breaking or silently
mis-mapping if it's wrong, this script prints the *real* schema first, then
runs checks defensively (skipping/warning on any column it expected but
doesn't find, instead of crashing).

Run: ``python -m recsys.calibration.audit_x5_retail_hero [--data-dir PATH]``
Expects clients.csv, products.csv, purchases.csv under
``data/kaggle/x5_retail_hero/raw/`` (gitignored, never commit the raw files).

Writes a JSON report next to the input (``<data-dir>/audit_report.json``) so
the numbers can be pulled into docs without re-running the script.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REQUIRED_FILES = ("clients.csv", "products.csv", "purchases.csv")

# Our project's own eligibility filter, already used as the working
# assumption in docs/research/recsys/synthetic-data-and-segments.md.
MIN_TRANSACTIONS_PER_CLIENT = 10
MIN_HISTORY_SPAN_DAYS = 90

# Our existing app.contracts / recsys.catalog taxonomy, for a side-by-side
# comparison against X5's real category depth — not used to filter/rename
# anything here.
OUR_CATEGORY_COUNT = 7


def _require_pandas():
    try:
        import pandas as pd  # noqa: F401
    except ImportError as exc:  # pragma: no cover - exercised manually
        raise SystemExit("pandas is required: install with `pip install -e '.[ml]'`.") from exc


def _check_data_dir(data_dir: Path) -> None:
    missing = [f for f in REQUIRED_FILES if not (data_dir / f).exists()]
    if missing:
        raise SystemExit(
            f"Missing X5 Retail Hero files in {data_dir}: {missing}.\n"
            "Get retailhero-uplift.zip from https://ods.ai/competitions/x5-retailhero-uplift-modeling/data, "
            f"unzip clients.csv/products.csv/purchases.csv into {data_dir} (gitignored), and re-run."
        )


def _describe_schema(df, name: str) -> dict:
    import pandas as pd

    n_rows = len(df)
    columns = {}
    for col in df.columns:
        series = df[col]
        entry = {
            "dtype": str(series.dtype),
            "null_count": int(series.isna().sum()),
            "null_rate": round(float(series.isna().mean()), 4),
            "n_unique": int(series.nunique(dropna=True)),
        }
        if pd.api.types.is_numeric_dtype(series):
            entry["min"] = None if series.dropna().empty else float(series.min())
            entry["max"] = None if series.dropna().empty else float(series.max())
            entry["mean"] = None if series.dropna().empty else round(float(series.mean()), 4)
        columns[col] = entry
    print(f"\n=== {name}: {n_rows:,} rows, {len(df.columns)} columns ===")
    for col, info in columns.items():
        print(f"  {col:<28} dtype={info['dtype']:<10} null={info['null_rate']:>6.2%}  n_unique={info['n_unique']:,}")
    return {"n_rows": n_rows, "columns": columns}


def _find_col(df, candidates: list[str]) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    return None


def audit(data_dir: Path) -> dict:
    import pandas as pd

    report: dict = {"data_dir": str(data_dir)}

    clients = pd.read_csv(data_dir / "clients.csv")
    products = pd.read_csv(data_dir / "products.csv")
    purchases = pd.read_csv(data_dir / "purchases.csv")

    report["clients_schema"] = _describe_schema(clients, "clients.csv")
    report["products_schema"] = _describe_schema(products, "products.csv")
    report["purchases_schema"] = _describe_schema(purchases, "purchases.csv")

    client_col = _find_col(purchases, ["client_id", "customer_id"])
    txn_col = _find_col(purchases, ["transaction_id"])
    ts_col = _find_col(purchases, ["transaction_datetime", "transaction_ts", "datetime"])
    product_col = _find_col(purchases, ["product_id"])
    qty_col = _find_col(purchases, ["product_quantity", "quantity"])
    basket_sum_col = _find_col(purchases, ["purchase_sum"])

    if not all([client_col, txn_col, ts_col]):
        print("\n[warn] could not find client/transaction/timestamp columns by the expected "
              "names — skipping cohort/cadence analysis. Check the schema dump above and "
              "update _find_col candidates.")
        report["cohort_analysis"] = None
    else:
        purchases[ts_col] = pd.to_datetime(purchases[ts_col])
        per_client = purchases.groupby(client_col).agg(
            n_transactions=(txn_col, "nunique"),
            n_rows=(txn_col, "size"),
            first_ts=(ts_col, "min"),
            last_ts=(ts_col, "max"),
            n_distinct_products=(product_col, "nunique") if product_col else (txn_col, "size"),
        )
        per_client["history_span_days"] = (per_client["last_ts"] - per_client["first_ts"]).dt.days
        basket_size = purchases.groupby(txn_col).size()

        eligible = per_client[
            (per_client["n_transactions"] >= MIN_TRANSACTIONS_PER_CLIENT)
            & (per_client["history_span_days"] >= MIN_HISTORY_SPAN_DAYS)
        ]

        report["cohort_analysis"] = {
            "n_clients_total": int(len(per_client)),
            "n_clients_eligible": int(len(eligible)),
            "eligible_share": round(len(eligible) / len(per_client), 4) if len(per_client) else None,
            "eligibility_rule": f">={MIN_TRANSACTIONS_PER_CLIENT} transactions, "
            f">={MIN_HISTORY_SPAN_DAYS} days span",
            "transactions_per_client": _quantiles(per_client["n_transactions"]),
            "history_span_days": _quantiles(per_client["history_span_days"]),
            "distinct_products_per_client": _quantiles(per_client["n_distinct_products"]),
            "basket_size_items": _quantiles(basket_size),
            "date_range": [str(purchases[ts_col].min()), str(purchases[ts_col].max())],
        }
        print(f"\n=== cohort analysis ===")
        print(json.dumps(report["cohort_analysis"], indent=2, default=str))

    if basket_sum_col and txn_col:
        # Report 1's own suggested sanity check: do per-line monetary fields
        # sum to the basket total, or are they something else entirely
        # (e.g. loyalty-points-adjusted, not raw price)?
        money_cols = [c for c in ["trn_sum_from_iss", "trn_sum_from_red"] if c in purchases.columns]
        if money_cols:
            per_txn_sum = purchases.groupby(txn_col)[money_cols[0]].sum()
            basket_total = purchases.groupby(txn_col)[basket_sum_col].first()
            joined = per_txn_sum.to_frame("line_sum").join(basket_total)
            diff = (joined["line_sum"] - joined[basket_sum_col]).abs()
            report["price_field_invariant_check"] = {
                "compared_column": money_cols[0],
                "median_abs_diff": float(diff.median()),
                "share_within_1_rub": float((diff <= 1.0).mean()),
                "interpretation": (
                    "high share_within_1_rub means this column really is a reliable "
                    "per-line price/amount field; low share means it is NOT a simple "
                    "per-line price and missing_cost_norm calibration needs another source"
                ),
            }
            print("\n=== price field invariant check ===")
            print(json.dumps(report["price_field_invariant_check"], indent=2))

    if product_col and "product_id" in products.columns:
        matched = purchases[product_col].isin(products["product_id"]).mean()
        report["product_join_coverage"] = round(float(matched), 4)
        print(f"\nproduct_id join coverage (purchases -> products): {matched:.2%}")

    name_like_cols = [
        c for c in products.columns
        if any(k in c.lower() for k in ("name", "title", "descr", "barcode", "ean", "gtin", "upc"))
    ]
    report["human_readable_product_field_candidates"] = name_like_cols
    print(f"\nColumns in products.csv that might be human-readable names/barcodes: {name_like_cols or 'NONE FOUND'}")

    return report


def _quantiles(series) -> dict:
    q = series.quantile([0.1, 0.25, 0.5, 0.75, 0.9, 0.99]).round(2).to_dict()
    return {
        "min": float(series.min()),
        "p10": q[0.1], "p25": q[0.25], "p50": q[0.5], "p75": q[0.75], "p90": q[0.9], "p99": q[0.99],
        "max": float(series.max()),
        "mean": round(float(series.mean()), 2),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir", type=Path, default=Path("data/kaggle/x5_retail_hero/raw"),
        help="Directory containing clients.csv/products.csv/purchases.csv",
    )
    args = parser.parse_args()

    _require_pandas()
    _check_data_dir(args.data_dir)

    report = audit(args.data_dir)
    out_path = args.data_dir.parent / "audit_report.json"
    out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    sys.exit(main() or 0)
