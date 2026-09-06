"""Rebuild ``recsys/data/availability_reference.json`` from a collected snapshot.

``recsys.inventory.P_NO_PRODUCT_AT_ALL = 0.08`` — "8% of the time the shop does
not carry the item at all" — was invented. Nobody measured it, and it turned
out to matter more than anything else in the pipeline: it sits underneath a
multiplicative veto, so a recipe with six required ingredients survives with
probability ``p**6``.

We do have one real assortment measurement, from our own collection: which of a
chain's products are actually present in a given store. This script extracts
it so the constant can at least be argued with instead of asserted.

What this can and cannot say
---------------------------
It measures **ready food**, which is the most localised category there is —
made in store or delivered daily, and visibly different city to city. Staples
like flour, milk and eggs are almost certainly stocked far more uniformly, so
the number here is **not** the right value for recipe ingredients.

It does **not** calibrate ``P_NO_PRODUCT_AT_ALL``. That parameter describes
recipe ingredients, whereas this file measures a different category with a
different replenishment model. The result is evidence that we need real
ingredient-level assortment data; until that exists, ingredient sensitivity
settings remain explicit assumptions and must not be relabelled as observed.

Usage::

    python -m recsys.extract_availability [path/to/x5_ready_food.sqlite]
"""

from __future__ import annotations

import json
import sqlite3
import statistics
import sys
from pathlib import Path
from typing import Any

SNAPSHOT_IDS: tuple[str, ...] = (
    "2026-09-04T22:52:34+00:00",
    "2026-09-04T23:38:22+00:00",
)

DEFAULT_DB = Path(
    "x5_ready_food_collector/data/x5_ready_food_2026/x5_ready_food.sqlite"
)
REFERENCE_PATH = Path(__file__).with_name("data") / "availability_reference.json"


def extract(db_path: Path) -> dict[str, Any]:
    connection = sqlite3.connect(db_path)

    chain_catalog: dict[str, int] = {
        chain: count
        for chain, count in connection.execute(
            """
            SELECT chain, count(DISTINCT product_key)
            FROM assortment WHERE snapshot_ts IN (?, ?) GROUP BY chain
            """,
            SNAPSHOT_IDS,
        )
    }

    stores: list[dict[str, Any]] = []
    for chain, city, store_id, present in connection.execute(
        """
        SELECT chain, city, store_id, count(DISTINCT product_key)
        FROM assortment WHERE snapshot_ts IN (?, ?)
        GROUP BY chain, city, store_id
        """,
        SNAPSHOT_IDS,
    ):
        total = chain_catalog[chain]
        stores.append(
            {
                "chain": chain,
                "city": city,
                "store_id": store_id,
                "products_present": present,
                "chain_catalog": total,
                "share_present": round(present / total, 4),
            }
        )
    stores.sort(key=lambda s: -s["share_present"])

    shares = [s["share_present"] for s in stores]
    by_chain: dict[str, list[float]] = {}
    for store in stores:
        by_chain.setdefault(store["chain"], []).append(store["share_present"])

    return {
        "source": "own collection, ready-food assortment",
        "snapshot_ids": list(SNAPSHOT_IDS),
        "category_caveat": (
            "Ready food only — the most localised category in the shop. Staples "
            "are very likely stocked far more uniformly, so this is not the "
            "value to use for recipe ingredients. It bounds the direction, not "
            "the number."
        ),
        "n_stores": len(stores),
        "share_present": {
            "min": round(min(shares), 4),
            "median": round(statistics.median(shares), 4),
            "max": round(max(shares), 4),
        },
        "share_present_by_chain": {
            chain: {
                "n_stores": len(values),
                "median": round(statistics.median(values), 4),
                "min": round(min(values), 4),
                "max": round(max(values), 4),
            }
            for chain, values in sorted(by_chain.items())
        },
        #: The quantity ``recsys.inventory.P_NO_PRODUCT_AT_ALL`` claims to be.
        "observed_not_carried_median": round(1 - statistics.median(shares), 4),
        "invented_constant": 0.08,
        "stores": stores,
    }


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    db_path = Path(argv[1]) if len(argv) > 1 else DEFAULT_DB
    if not db_path.exists():
        print(f"snapshot database not found: {db_path}", file=sys.stderr)
        return 1

    reference = extract(db_path)
    REFERENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    REFERENCE_PATH.write_text(
        json.dumps(reference, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"{reference['n_stores']} stores -> {REFERENCE_PATH}")
    print(
        f"  median share of chain catalog present in a store: "
        f"{reference['share_present']['median']:.0%}"
    )
    print(
        f"  => not carried: {reference['observed_not_carried_median']:.0%}, "
        f"against an invented {reference['invented_constant']:.0%}"
    )
    for chain, stats in reference["share_present_by_chain"].items():
        print(
            f"  {chain:14} median {stats['median']:.0%} "
            f"(min {stats['min']:.0%}, max {stats['max']:.0%}, "
            f"{stats['n_stores']} stores)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
