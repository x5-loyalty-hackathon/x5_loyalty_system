"""The synthetic basket must stay anchored to the real X5 price distribution.

``recsys.catalog.BASE_PRICE_RUB`` is hand-written per ingredient, but a
recommendation shows it next to an observed ready-meal price, so it may not
drift into a band no real basket occupies. The reference it is checked against
is rebuilt by ``python -m recsys.calibrate_prices``.
"""

from __future__ import annotations

import statistics
from pathlib import Path

from recsys.catalog import (
    BASE_PRICE_RUB,
    PRICE_ERA_MULTIPLIER_BAND,
    PRICE_REFERENCE,
    REFERENCE_MEDIAN_PRICE_RUB,
    observed_price_era_multiplier,
)


def _percentile(values: list[float], percentile: int) -> float:
    ordered = sorted(values)
    return ordered[min(int(len(ordered) * percentile / 100), len(ordered) - 1)]


def test_reference_came_from_a_real_and_large_sample() -> None:
    assert PRICE_REFERENCE["usable_unit_prices"] > 1_000_000
    assert PRICE_REFERENCE["era"] == "2018-2019"
    assert "Retail Hero" in PRICE_REFERENCE["source"]
    percentiles = PRICE_REFERENCE["percentiles_rub"]
    ordered = [percentiles[key] for key in ("10", "25", "50", "75", "90", "99")]
    assert ordered == sorted(ordered)
    assert REFERENCE_MEDIAN_PRICE_RUB == percentiles["50"]


def test_catalog_median_sits_in_the_calibrated_band() -> None:
    catalog_median = statistics.median(BASE_PRICE_RUB.values())
    ratio = catalog_median / REFERENCE_MEDIAN_PRICE_RUB
    low, high = PRICE_ERA_MULTIPLIER_BAND
    assert low <= ratio <= high, (
        f"catalog median {catalog_median} is {ratio:.2f}x the 2018-2019 "
        f"reference {REFERENCE_MEDIAN_PRICE_RUB}, outside {PRICE_ERA_MULTIPLIER_BAND}"
    )


def test_catalog_spread_matches_the_reference_shape() -> None:
    """A basket of staples plus a few premium items, not a flat price list."""
    values = list(BASE_PRICE_RUB.values())
    reference = PRICE_REFERENCE["percentiles_rub"]
    low, high = PRICE_ERA_MULTIPLIER_BAND
    for percentile in (25, 50, 75, 90):
        ratio = _percentile(values, percentile) / reference[str(percentile)]
        assert low <= ratio <= high, f"p{percentile} is {ratio:.2f}x the reference"


def test_no_ingredient_is_priced_absurdly() -> None:
    ceiling = PRICE_REFERENCE["percentiles_rub"]["99"] * PRICE_ERA_MULTIPLIER_BAND[1]
    for ingredient_id, price in BASE_PRICE_RUB.items():
        assert price > 0, ingredient_id
        assert price <= ceiling, f"{ingredient_id} at {price} exceeds {ceiling}"


def test_the_multiplier_is_computed_not_transcribed() -> None:
    """The generated catalog doc must quote the live ratio, not a memory of it.

    docs/recipe-catalog.md carried the literal "×2.4" while the catalog had
    drifted to ×2.31. The band test above could not catch it: the band spans
    1.8-3.0, so both numbers pass it and the prose was free to be wrong.
    """
    assert observed_price_era_multiplier() == statistics.median(
        BASE_PRICE_RUB.values()
    ) / REFERENCE_MEDIAN_PRICE_RUB

    doc = Path("docs/recipe-catalog.md").read_text(encoding="utf-8")
    quoted = f"×{observed_price_era_multiplier():.2f}"
    assert quoted in doc, (
        f"docs/recipe-catalog.md does not quote the current ratio {quoted} — "
        "regenerate it with `python -m recsys.generate_recipe_doc`"
    )


def test_generated_catalog_preserves_research_serving_boundary() -> None:
    from recsys.generate_recipe_doc import build

    generated = build()
    assert "> Код стенда использует `recsys.experimental`" in generated
    assert "HTTP API 1.3 такого поля нет" in generated
    assert "из `recsys/experimental/recipes.py`" in generated
