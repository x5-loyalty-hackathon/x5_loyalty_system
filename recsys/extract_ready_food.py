"""Rebuild ``recsys/data/ready_food_catalog.json`` from a collected snapshot.

This is the only code that touches the raw collector database. The database
(``x5_ready_food_collector/data/x5_ready_food_2026/x5_ready_food.sqlite``, ~29
MB) is not committed, so the runtime reads the small JSON catalog this script
writes instead — see ``recsys.ready_food_pairs``.

What it takes from the raw data:

* ``plu`` — the retailer's real product number, present for 100% of rows. It is
  a point-in-time scrape, hence ``snapshot_ts`` travels with it and the runtime
  treats a PLU as evidence a product existed, not as a live assortment feed.
* ``Тип блюда`` / ``Кухня`` — read out of ``detail_json['attributes']``, the
  product card X5 serves for the item. Only the products whose card was
  captured have them, so both fields are nullable and the pairing code has to
  cope with their absence rather than assume coverage.
* the median price over the ``assortment`` rows for the product.

The snapshot covers 15 cities, but the demo is Moscow-only, so ``CITY`` filters
everything else out at extraction time: 647 products across both chains, one
store each. Nothing downstream carries a city, because within Moscow there is
no coverage dimension left to model — every row in the slice is ``available``.
Widening the demo means changing ``CITY`` and re-running, and only then does
per-city filtering become worth reintroducing.

Usage::

    python -m recsys.extract_ready_food [path/to/x5_ready_food.sqlite]
"""

from __future__ import annotations

import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

#: The two snapshots that completed. The other eight in the database are
#: truncated debugging runs (13–354 SKUs, Moscow only) and are excluded.
SNAPSHOT_IDS: tuple[str, ...] = (
    "2026-09-04T22:52:34+00:00",
    "2026-09-04T23:38:22+00:00",
)

#: The demo is Moscow-only; see the module docstring.
CITY = "Москва"

DEFAULT_DB = Path(
    "x5_ready_food_collector/data/x5_ready_food_2026/x5_ready_food.sqlite"
)
CATALOG_PATH = Path(__file__).with_name("data") / "ready_food_catalog.json"

#: Card attribute names carrying the facets we pair on.
DISH_TYPE_ATTRIBUTE = "Тип блюда"
CUISINE_ATTRIBUTE = "Кухня"

#: Categories that are not meals at all — drinks, bread, plain bakery. Keeping
#: them would only add noise no recipe can pair with.
EXCLUDED_CATEGORY_MARKERS = ("Напитки", "Горячий кофе", "До и после еды")


def _attributes(detail_json: str | None) -> dict[str, str]:
    if not detail_json:
        return {}
    try:
        detail = json.loads(detail_json)
    except (TypeError, ValueError):
        return {}
    if not isinstance(detail, dict):
        return {}
    attributes = detail.get("attributes")
    if not isinstance(attributes, list):
        return {}
    out: dict[str, str] = {}
    for attribute in attributes:
        if isinstance(attribute, dict) and attribute.get("name") and attribute.get("value"):
            out[str(attribute["name"])] = str(attribute["value"])
    return out


def extract(db_path: Path) -> list[dict[str, Any]]:
    connection = sqlite3.connect(db_path)
    rows = connection.execute(
        """
        SELECT a.chain, p.plu, p.name, a.price, a.category_path, p.detail_json
        FROM assortment a
        JOIN products p ON p.chain = a.chain AND p.product_key = a.product_key
        WHERE a.snapshot_ts IN (?, ?)
          AND a.city = ?
          AND p.plu IS NOT NULL AND p.plu != ''
        """,
        (*SNAPSHOT_IDS, CITY),
    )

    prices: dict[tuple[str, str], list[float]] = defaultdict(list)
    meta: dict[tuple[str, str], dict[str, Any]] = {}
    for chain, plu, name, price, category_path, detail_json in rows:
        if any(marker in (category_path or "") for marker in EXCLUDED_CATEGORY_MARKERS):
            continue
        key = (chain, str(plu))
        if price:
            prices[key].append(float(price))
        if key not in meta:
            attributes = _attributes(detail_json)
            meta[key] = {
                "chain": chain,
                "plu": str(plu),
                "name": name,
                "dish_type": attributes.get(DISH_TYPE_ATTRIBUTE),
                "cuisine": attributes.get(CUISINE_ATTRIBUTE),
            }

    catalog: list[dict[str, Any]] = []
    for key, entry in meta.items():
        entry_prices = sorted(prices[key])
        catalog.append(
            {
                **entry,
                "median_price_rub": (
                    round(entry_prices[len(entry_prices) // 2], 2) if entry_prices else None
                ),
            }
        )
    catalog.sort(key=lambda item: (item["chain"], item["plu"]))
    return catalog


def main(argv: list[str]) -> int:
    db_path = Path(argv[1]) if len(argv) > 1 else DEFAULT_DB
    if not db_path.exists():
        print(f"snapshot database not found: {db_path}", file=sys.stderr)
        return 1
    catalog = extract(db_path)
    CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CATALOG_PATH.write_text(
        json.dumps(
            {"snapshot_ids": list(SNAPSHOT_IDS), "city": CITY, "products": catalog},
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    with_dish_type = sum(1 for item in catalog if item["dish_type"])
    with_cuisine = sum(1 for item in catalog if item["cuisine"])
    print(
        f"{len(catalog)} products in {CITY} -> {CATALOG_PATH} "
        f"({with_dish_type} with a dish type, {with_cuisine} with a cuisine)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
