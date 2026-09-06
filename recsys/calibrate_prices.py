"""Rebuild ``recsys/data/price_reference.json`` from real X5 transactions.

``recsys.catalog.BASE_PRICE_RUB`` has to put a rouble figure on a home-cooked
basket. Those figures were hand-written, and the "cook it or buy it ready"
offer puts them next to a *real* ready-meal price from
``recsys/data/ready_food_catalog.json`` — so an invented number on one side of
the comparison and an observed one on the other is a problem worth fixing.

This script grounds the invented side. It reads the X5 Retail Hero transaction
dump in ``data/kaggle/x5_retail_hero/raw/purchases.csv`` (4.4 GB, not
committed) and derives the real per-unit price distribution from
``trn_sum_from_iss / product_quantity``, writing a small percentile summary
next to the ready-food catalog.

What this does and does not buy us:

* It **does** establish the price band a real X5 basket lives in, from millions
  of real receipt lines, so the synthetic catalog can be checked against it —
  see ``tests/test_price_calibration.py``.
* It does **not** give per-ingredient truth. ``product_id`` and every category
  level in that dataset are hashed (``c3d3a8e8c6``), so "молоко" cannot be tied
  to a row. The reference is a distribution anchor, nothing more.
* The dump is from 2018–2019, so it is not directly comparable to a 2026 price.
  ``recsys.catalog`` records the observed ratio rather than pretending the eras
  match.

Usage::

    python -m recsys.calibrate_prices [--rows 3000000] [--purchases PATH]
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

DEFAULT_PURCHASES = Path("data/kaggle/x5_retail_hero/raw/purchases.csv")
REFERENCE_PATH = Path(__file__).with_name("data") / "price_reference.json"

#: Rows read from the head of the dump. The file is 4.4 GB and the price
#: distribution is stable long before the end of it; raise it to re-check.
DEFAULT_ROWS = 3_000_000

PERCENTILES: tuple[int, ...] = (10, 25, 50, 75, 90, 99)

#: Line prices outside this range are data errors, not groceries.
MIN_PLAUSIBLE_UNIT_PRICE = 1.0
MAX_PLAUSIBLE_UNIT_PRICE = 100_000.0


def unit_prices(purchases_path: Path, max_rows: int) -> list[float]:
    prices: list[float] = []
    with purchases_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for index, row in enumerate(reader):
            if index >= max_rows:
                break
            try:
                quantity = float(row["product_quantity"])
                line_total = float(row["trn_sum_from_iss"])
            except (TypeError, ValueError, KeyError):
                continue
            if quantity <= 0 or line_total <= 0:
                continue
            price = line_total / quantity
            if MIN_PLAUSIBLE_UNIT_PRICE <= price <= MAX_PLAUSIBLE_UNIT_PRICE:
                prices.append(price)
    prices.sort()
    return prices


def summarize(prices: list[float], rows_read: int) -> dict:
    if not prices:
        raise ValueError("no usable unit prices found")
    return {
        "source": "X5 Retail Hero (Kaggle) purchases.csv",
        "era": "2018-2019",
        "rows_read": rows_read,
        "usable_unit_prices": len(prices),
        "percentiles_rub": {
            str(p): round(prices[min(int(len(prices) * p / 100), len(prices) - 1)], 2)
            for p in PERCENTILES
        },
        "mean_rub": round(sum(prices) / len(prices), 2),
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--purchases", type=Path, default=DEFAULT_PURCHASES)
    parser.add_argument("--rows", type=int, default=DEFAULT_ROWS)
    args = parser.parse_args(argv[1:])

    if not args.purchases.exists():
        print(f"transaction dump not found: {args.purchases}", file=sys.stderr)
        return 1

    prices = unit_prices(args.purchases, args.rows)
    reference = summarize(prices, args.rows)
    REFERENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    REFERENCE_PATH.write_text(
        json.dumps(reference, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(
        f"{reference['usable_unit_prices']} unit prices -> {REFERENCE_PATH} "
        f"(median {reference['percentiles_rub']['50']} RUB, {reference['era']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
