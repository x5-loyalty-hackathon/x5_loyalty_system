"""The "or just buy it ready" side of a recommendation."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.contracts import (
    Receipt,
    ReceiptItem,
    ReadyMealOption,
    RecommendationRequest,
    UserProfile,
)
from app.recommender import DeterministicMockEngine
from app.safety import SafetyPolicy
from app.service import RecommendationService
from recsys.ready_food_pairs import PAIRS_BY_RECIPE_ID, ready_meal_options
from recsys.recipes import RECIPES_BY_ID

NOW = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def service() -> RecommendationService:
    return RecommendationService(
        engine=DeterministicMockEngine(), safety_policy=SafetyPolicy()
    )


def _request(**overrides) -> RecommendationRequest:
    recipe = RECIPES_BY_ID["olivier_salad"]
    receipt = Receipt(
        receipt_id="r1",
        purchased_at=NOW,
        store_id="store_10",
        items=[
            ReceiptItem(
                sku_id="s1",
                name=ingredient.name,
                category=ingredient.category,
                ingredient_ids={ingredient.ingredient_id},
                quantity=1,
                unit_price=100.0,
            )
            for ingredient in recipe.ingredients
        ],
    )
    defaults = dict(
        user=UserProfile(user_id="u1", radius_km=3.0),
        current_receipt=receipt,
        recipe_catalog=[recipe],
        now=NOW,
        limit=3,
    )
    defaults.update(overrides)
    return RecommendationRequest(**defaults)


def test_options_render_the_pair_table_as_one_flat_list() -> None:
    options = ready_meal_options(["olivier_salad"])
    assert options
    pair = PAIRS_BY_RECIPE_ID["olivier_salad"]
    assert {(o.chain, o.plu) for o in options} == {(m.chain, m.plu) for m in pair.meals}
    for option in options:
        assert option.recipe_ids == {"olivier_salad"}
        assert option.plu.isdigit()


def test_one_product_carries_every_recipe_it_stands_in_for() -> None:
    # "Плов с курицей" is a counterpart to both pilaf recipes and must appear
    # once, not twice, with both ids on it.
    options = ready_meal_options(["chicken_pilaf", "beef_pilaf"])
    keys = [(o.chain, o.plu) for o in options]
    assert len(keys) == len(set(keys))
    assert any(o.recipe_ids == {"chicken_pilaf", "beef_pilaf"} for o in options)


def test_recommendation_offers_the_cheapest_counterpart(service) -> None:
    options = ready_meal_options(["olivier_salad"])
    response = service.recommend(_request(ready_meal_options=options))
    assert response.recommendations
    recommendation = response.recommendations[0]
    assert recommendation.ready_meal_option_count == len(options)
    alternative = recommendation.ready_meal_alternative
    assert alternative is not None
    assert alternative.price == min(o.price for o in options if o.price is not None)
    assert alternative.plu.isdigit()


def test_unpriced_counterparts_sort_last_but_are_still_counted(service) -> None:
    priced = ReadyMealOption(
        chain="pyaterochka", plu="1", name="Оливье готовый",
        recipe_ids={"olivier_salad"}, price=149.99,
    )
    unpriced = ReadyMealOption(
        chain="pyaterochka", plu="2", name="Оливье весовой",
        recipe_ids={"olivier_salad"}, price=None,
    )
    response = service.recommend(_request(ready_meal_options=[unpriced, priced]))
    recommendation = response.recommendations[0]
    assert recommendation.ready_meal_option_count == 2
    assert recommendation.ready_meal_alternative.plu == "1"


def test_options_for_other_recipes_are_ignored(service) -> None:
    other = ReadyMealOption(
        chain="pyaterochka", plu="9", name="Борщ готовый",
        recipe_ids={"borsch"}, price=99.0,
    )
    response = service.recommend(_request(ready_meal_options=[other]))
    recommendation = response.recommendations[0]
    assert recommendation.ready_meal_alternative is None
    assert recommendation.ready_meal_option_count == 0


def test_a_recommendation_without_options_is_unchanged(service) -> None:
    response = service.recommend(_request())
    recommendation = response.recommendations[0]
    assert recommendation.ready_meal_alternative is None
    assert recommendation.ready_meal_option_count == 0
