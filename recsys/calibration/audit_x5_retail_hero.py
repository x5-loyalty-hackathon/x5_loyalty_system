"""Data audit for X5 Retail Hero (clients.csv, products.csv, purchases.csv).

Not on any runtime/test import path — same status as fit_from_kaggle.py.
Needs `pip install -e '.[ml]'` (pandas only; no sklearn needed here).

Why this script discovers rather than assumes: two independent research
passes (see docs/research/recsys/x5-retail-hero-data-audit.md) produced
detailed schemas for products.csv/purchases.csv that we could only partially
verify ahead of time. This script prints the *real* schema first, then runs
checks defensively (skipping/warning on any column it expected but doesn't
find, instead of crashing).

Memory design: purchases.csv is the real file, ~4.5 GB / 45.8M rows —
loading it with `pd.read_csv` at default dtypes is not safe on a machine with
a few GB of free RAM (verified: it needs far more than that). So this script
never holds the full purchases table in memory. It streams it in chunks and
reduces each chunk to one row per *transaction* (not per line item) before
accumulating, using a carry-over row so a transaction split across a chunk
boundary is never double-counted or truncated. The accumulated per-transaction
table is orders of magnitude smaller than the raw file and safe to analyze
normally. `distinct_products_per_client` is computed on a random sample of
clients (not all 400k) for the same reason — labeled as sampled in the
output, not silently presented as exact.

Run: ``python -m recsys.calibration.audit_x5_retail_hero [--data-dir PATH]``
Expects clients.csv, products.csv, purchases.csv under
``data/kaggle/x5_retail_hero/raw/`` (gitignored, never commit the raw files).

Writes a JSON report next to the input (``<data-dir>/audit_report.json``) so
the numbers can be pulled into docs without re-running the script.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

REQUIRED_FILES = ("clients.csv", "products.csv", "purchases.csv")

# Our project's own eligibility filter, already used as the working
# assumption in docs/research/recsys/synthetic-data-and-segments.md.
MIN_TRANSACTIONS_PER_CLIENT = 10
MIN_HISTORY_SPAN_DAYS = 90

CHUNK_SIZE = 2_000_000
PRODUCT_SAMPLE_N_CLIENTS = 3_000
SCHEMA_SAMPLE_ROWS = 1_000_000


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


def _describe_schema(df, name: str, *, sampled_rows: int | None = None) -> dict:
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
    label = f"{name} (SAMPLE of first {sampled_rows:,} rows)" if sampled_rows else name
    print(f"\n=== {label}: {n_rows:,} rows read, {len(df.columns)} columns ===")
    for col, info in columns.items():
        note = " (n_unique is sample-only)" if sampled_rows else ""
        print(f"  {col:<28} dtype={info['dtype']:<10} null={info['null_rate']:>6.2%}  n_unique={info['n_unique']:,}{note}")
    return {"n_rows_read": n_rows, "sampled_rows": sampled_rows, "columns": columns}


def _find_col(columns, candidates: list[str]) -> str | None:
    for c in candidates:
        if c in columns:
            return c
    return None


def _quantiles(series) -> dict:
    q = series.quantile([0.1, 0.25, 0.5, 0.75, 0.9, 0.99]).round(2).to_dict()
    return {
        "min": float(series.min()),
        "p10": q[0.1], "p25": q[0.25], "p50": q[0.5], "p75": q[0.75], "p90": q[0.9], "p99": q[0.99],
        "max": float(series.max()),
        "mean": round(float(series.mean()), 2),
        "n": int(series.shape[0]),
    }


def _reduce_purchases_to_transactions(
    purchases_path: Path,
    *,
    client_col: str,
    txn_col: str,
    ts_col: str,
    product_col: str | None,
    basket_sum_col: str | None,
    money_col: str | None,
    sample_client_ids: set,
):
    """Stream purchases.csv in bounded-memory chunks, collapsing each
    transaction's line items into one summary row. Returns (transactions_df,
    total_rows_seen, product_join_hits, product_join_total,
    sample_client_products: dict[client_id, set[product_id]])."""
    import pandas as pd

    usecols = [c for c in [client_col, txn_col, ts_col, product_col, basket_sum_col, money_col] if c]
    agg_spec = {"client_id": (client_col, "first"), "ts": (ts_col, "first"), "n_items": (txn_col, "size")}
    if money_col:
        agg_spec["money_sum"] = (money_col, "sum")
    if basket_sum_col:
        agg_spec["basket_total"] = (basket_sum_col, "first")

    txn_chunks = []
    carry = None
    total_rows_seen = 0
    sample_client_products: dict = {cid: set() for cid in sample_client_ids}

    reader = pd.read_csv(purchases_path, usecols=usecols, chunksize=CHUNK_SIZE)
    for i, chunk in enumerate(reader):
        total_rows_seen += len(chunk)
        if carry is not None:
            chunk = pd.concat([carry, chunk], ignore_index=True)

        if product_col and sample_client_ids:
            sub = chunk[chunk[client_col].isin(sample_client_ids)]
            for cid, pid in zip(sub[client_col], sub[product_col]):
                sample_client_products[cid].add(pid)

        # Carry the last transaction's rows over to the next chunk in case
        # they continue there — avoids truncating/double-counting a
        # transaction that straddles a chunk boundary.
        last_txn_id = chunk[txn_col].iloc[-1]
        is_last = chunk[txn_col] == last_txn_id
        carry = chunk[is_last]
        complete = chunk[~is_last]

        if len(complete):
            grouped = complete.groupby(txn_col).agg(**agg_spec)
            txn_chunks.append(grouped)
        print(f"  ...chunk {i + 1}: {total_rows_seen:,} rows read so far", file=sys.stderr)

    if carry is not None and len(carry):
        grouped = carry.groupby(txn_col).agg(**agg_spec)
        txn_chunks.append(grouped)

    transactions = pd.concat(txn_chunks) if txn_chunks else None
    return transactions, total_rows_seen, sample_client_products


def audit(data_dir: Path) -> dict:
    import pandas as pd

    report: dict = {"data_dir": str(data_dir)}

    clients = pd.read_csv(data_dir / "clients.csv")
    products = pd.read_csv(data_dir / "products.csv")
    purchases_sample = pd.read_csv(data_dir / "purchases.csv", nrows=SCHEMA_SAMPLE_ROWS)

    report["clients_schema"] = _describe_schema(clients, "clients.csv")
    report["products_schema"] = _describe_schema(products, "products.csv")
    report["purchases_schema"] = _describe_schema(
        purchases_sample, "purchases.csv", sampled_rows=SCHEMA_SAMPLE_ROWS
    )

    columns = list(purchases_sample.columns)
    client_col = _find_col(columns, ["client_id", "customer_id"])
    txn_col = _find_col(columns, ["transaction_id"])
    ts_col = _find_col(columns, ["transaction_datetime", "transaction_ts", "datetime"])
    product_col = _find_col(columns, ["product_id"])
    basket_sum_col = _find_col(columns, ["purchase_sum"])
    money_col = _find_col(columns, ["trn_sum_from_iss"])

    if not all([client_col, txn_col, ts_col]):
        print("\n[warn] could not find client/transaction/timestamp columns by the expected "
              "names — skipping cohort/cadence analysis. Check the schema dump above and "
              "update _find_col candidates.")
        report["cohort_analysis"] = None
        return report

    rng = random.Random(42)
    all_client_ids = clients[_find_col(list(clients.columns), ["client_id", "customer_id"])].tolist()
    sample_client_ids = set(rng.sample(all_client_ids, k=min(PRODUCT_SAMPLE_N_CLIENTS, len(all_client_ids))))

    print(f"\nStreaming {data_dir / 'purchases.csv'} in chunks of {CHUNK_SIZE:,} rows "
          f"(bounded memory — never loading the full 45M+ row file at once)...", file=sys.stderr)
    transactions, total_rows_seen, sample_client_products = _reduce_purchases_to_transactions(
        data_dir / "purchases.csv",
        client_col=client_col, txn_col=txn_col, ts_col=ts_col, product_col=product_col,
        basket_sum_col=basket_sum_col, money_col=money_col, sample_client_ids=sample_client_ids,
    )
    report["total_purchase_rows_seen"] = total_rows_seen

    if transactions is None or transactions.empty:
        report["cohort_analysis"] = None
        return report

    transactions["ts"] = pd.to_datetime(transactions["ts"])
    per_client = transactions.groupby("client_id").agg(
        n_transactions=("ts", "size"),
        first_ts=("ts", "min"),
        last_ts=("ts", "max"),
    )
    per_client["history_span_days"] = (per_client["last_ts"] - per_client["first_ts"]).dt.days

    eligible = per_client[
        (per_client["n_transactions"] >= MIN_TRANSACTIONS_PER_CLIENT)
        & (per_client["history_span_days"] >= MIN_HISTORY_SPAN_DAYS)
    ]

    distinct_products_sample = pd.Series({cid: len(s) for cid, s in sample_client_products.items() if s})

    report["cohort_analysis"] = {
        "n_clients_total_in_purchases": int(len(per_client)),
        "n_clients_total_in_clients_csv": int(len(clients)),
        "n_transactions_total": int(len(transactions)),
        "n_clients_eligible": int(len(eligible)),
        "eligible_share": round(len(eligible) / len(per_client), 4) if len(per_client) else None,
        "eligibility_rule": f">={MIN_TRANSACTIONS_PER_CLIENT} transactions, >={MIN_HISTORY_SPAN_DAYS} days span",
        "transactions_per_client": _quantiles(per_client["n_transactions"]),
        "history_span_days": _quantiles(per_client["history_span_days"]),
        "basket_size_items": _quantiles(transactions["n_items"]),
        "distinct_products_per_client_SAMPLE": {
            "n_clients_sampled": len(sample_client_ids),
            **(_quantiles(distinct_products_sample) if len(distinct_products_sample) else {}),
        },
        "date_range": [str(transactions["ts"].min()), str(transactions["ts"].max())],
    }
    print("\n=== cohort analysis (exact, from full file via chunked reduction) ===")
    print(json.dumps(report["cohort_analysis"], indent=2, default=str))

    if money_col and "basket_total" in transactions.columns:
        diff = (transactions["money_sum"] - transactions["basket_total"]).abs()
        report["price_field_invariant_check"] = {
            "compared_column": money_col,
            "median_abs_diff": float(diff.median()),
            "share_within_1_rub": float((diff <= 1.0).mean()),
            "interpretation": (
                "high share_within_1_rub means this column really is a reliable "
                "per-line price/amount field; low share means it is NOT a simple "
                "per-line price and missing_cost_norm calibration needs another source"
            ),
        }
        print("\n=== price field invariant check (exact) ===")
        print(json.dumps(report["price_field_invariant_check"], indent=2))

    name_like_cols = [
        c for c in products.columns
        if any(k in c.lower() for k in ("name", "title", "descr", "barcode", "ean", "gtin", "upc"))
    ]
    report["human_readable_product_field_candidates"] = name_like_cols
    print(f"\nColumns in products.csv that might be human-readable names/barcodes: {name_like_cols or 'NONE FOUND'}")

    return report


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
