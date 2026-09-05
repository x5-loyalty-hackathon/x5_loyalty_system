"""The synthetic basket must stay anchored to the real X5 price distribution.

``recsys.catalog.BASE_PRICE_RUB`` is hand-written per ingredient, but a
recommendation shows it next to an observed ready-meal price, so it may not
drift into a band no real basket occupies. The reference it is checked against
is rebuilt by ``python -m recsys.calibrate_prices``.
"""

from __future__ import annotations

import statistics

from recsys.catalog import (
    BASE_PRICE_RUB,
    PRICE_ERA_MULTIPLIER_BAND,
    PRICE_REFERENCE,
    REFERENCE_MEDIAN_PRICE_RUB,
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
