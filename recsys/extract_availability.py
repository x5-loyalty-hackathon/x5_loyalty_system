"""Rebuild ``recsys/data/availability_reference.json`` from a collected snapshot.

``recsys.experimental.inventory.P_NO_PRODUCT_AT_ALL`` — "the shop does not
carry the item at all" — was invented, not measured. It turned out to matter
more than anything else in the pipeline: it sits underneath a multiplicative
veto, so a recipe with six required ingredients survives with probability
``p**6`` (this is what motivated lowering it from 0.08 to 0.02 — see
``recsys/experimental/inventory.py`` and
``docs/research/recsys/llm-intent-eval.md`` §11.1 — but that revision is
*also* a guess, reasoned from "a regular store usually carries a staple in
some form", not from this or any other measurement).

We do have one real assortment measurement, from our own collection: which of
a chain's products are actually present in a given store. This script
extracts it so the constant can at least be argued with instead of asserted.
``invented_constant`` below reads the live module constant rather than a
copied-in literal specifically so this file cannot go stale the way it did
once already: written when the shipped value was 0.08, left unchanged when
it moved to 0.02, so the printed comparison quietly argued against a number
nothing shipped any more.

What this can and cannot say
---------------------------
It measures **ready food**, which is the most localised category there is —
made in store or delivered daily, and visibly different city to city. Staples
like flour, milk and eggs are almost certainly stocked far more uniformly, so
the number here is **not** the right value for recipe ingredients — and
notably it points in the *opposite* direction from the 0.08->0.02 revision:
the measured "not carried" share for ready food is ~79%, an order of
magnitude past even the original 0.08. That doesn't argue recipe-ingredient
availability is anywhere near 79% either — ready food and bulk staples are
different economics — but it is a reason not to treat 0.02 as more than a
guess: the one real number we have, even heavily caveated, moved the wrong
way for that story.

What it does establish is direction and order of magnitude: the one real
assortment figure we have is nowhere near either invented constant. So
neither should be defended, and the sensitivity sweep must cover a range
that contains this measurement rather than stopping short of it.

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

from recsys.experimental.inventory import P_NO_PRODUCT_AT_ALL

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
        #: The quantity ``recsys.experimental.inventory.P_NO_PRODUCT_AT_ALL`` claims to be.
        "observed_not_carried_median": round(1 - statistics.median(shares), 4),
        "invented_constant": P_NO_PRODUCT_AT_ALL,
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
