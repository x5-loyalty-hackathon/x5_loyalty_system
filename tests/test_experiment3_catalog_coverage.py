"""Tests for the 10 recipes added by experiment 3 (catalog coverage) and for
the measurement helpers in ``recsys.experiment3_catalog_coverage``.

Mirrors ``tests/test_recsys_expanded_recipe_catalog.py``'s pattern for the
price/SKU-mapping check rather than duplicating it against the whole catalog.
"""

from __future__ import annotations

import pytest

from app.contracts import FulfillmentOption, RecommendationRequest
from recsys.catalog import BASE_PRICE_RUB, INGREDIENTS
from recsys.experiment3_catalog_coverage import (
    DEFICIT_LEVELS,
    NEW_RECIPE_IDS,
    abstract_missing_count,
    build_panel,
    coverage_shares,
    constrained_missing_count,
    evaluate_panel,
    new_catalog,
    old_catalog,
    stable_seed,
)
from recsys.recipes import RECIPES, RECIPES_BY_ID
from recsys.sku_mapping import INGREDIENT_SKU_MAPPINGS


def test_new_recipes_are_in_the_catalog() -> None:
    assert NEW_RECIPE_IDS.issubset(RECIPES_BY_ID)
    assert len(RECIPES) == len(old_catalog()) + len(NEW_RECIPE_IDS)


def test_every_new_recipe_ingredient_has_price_and_synthetic_sku_mapping() -> None:
    # All 10 recipes deliberately reuse existing recsys.catalog ingredients
    # (no new vocabulary) -- this checks that claim rather than assuming it.
    ingredient_ids = {
        ingredient.ingredient_id
        for recipe_id in NEW_RECIPE_IDS
        for ingredient in RECIPES_BY_ID[recipe_id].ingredients
    }
    assert ingredient_ids.issubset(INGREDIENTS)
    assert ingredient_ids.issubset(BASE_PRICE_RUB)
    assert ingredient_ids.issubset(INGREDIENT_SKU_MAPPINGS)


def test_new_recipes_are_short_and_have_at_most_one_seasoning_heavy_variant() -> None:
    """The whole point of these 10 recipes is being short (see the report's
    finding that the closest recipe for every uncovered basket had exactly 4
    ingredients) -- this pins that property so it cannot silently regress."""
    for recipe_id in NEW_RECIPE_IDS:
        recipe = RECIPES_BY_ID[recipe_id]
        assert len(recipe.ingredients) <= 7, recipe_id
        required = [i for i in recipe.ingredients if i.required]
        assert 2 <= len(required) <= 4, recipe_id


def test_cutlet_semi_finished_now_has_a_recipe() -> None:
    # recsys.catalog carried this ingredient with zero recipes before this
    # experiment -- pin that the gap is actually closed, not just claimed in
    # the report prose.
    used_by = [
        recipe.recipe_id
        for recipe in RECIPES
        if any(i.ingredient_id == "cutlet_semi_finished" for i in recipe.ingredients)
    ]
    assert used_by == ["pan_fried_semi_finished_cutlets"]


def test_old_catalog_helper_excludes_exactly_the_new_recipes() -> None:
    old_ids = {r.recipe_id for r in old_catalog()}
    new_ids = {r.recipe_id for r in new_catalog()}
    assert new_ids - old_ids == NEW_RECIPE_IDS
    assert old_ids == set(RECIPES_BY_ID) - NEW_RECIPE_IDS


def test_stable_seed_is_deterministic_and_order_sensitive() -> None:
    assert stable_seed("a", "b") == stable_seed("a", "b")
    assert stable_seed("a", "b") != stable_seed("b", "a")


@pytest.fixture(scope="module")
def panels():
    """Built once per module.

    build_panel() regenerates inventories for every user at all three deficit
    levels, so calling it per test cost about six minutes for this file alone.
    Nothing here mutates the panels, so sharing one is safe; tests that need to
    corrupt a panel build their own (see tests/test_panels.py).
    """
    return build_panel()


def test_panel_split_is_deterministic_and_disjoint() -> None:
    """The split is now the protocol's, not a local parity trick."""
    first = build_panel()
    second = build_panel()
    train_ids = {p.user.user_id for p, _ in first["train"]["база"]}
    held_ids = {p.user.user_id for p, _ in first["validation"]["база"]}
    assert train_ids == {p.user.user_id for p, _ in second["train"]["база"]}
    assert not train_ids & held_ids


def test_deficit_levels_actually_change_the_shelf(panels) -> None:
    """The previous helper monkeypatched module constants generate_inventory no
    longer reads, so low/base/high were three draws at base scarcity: measured
    108/107/111 products. Real scarcity has to shrink the shelf."""
    train = panels["train"]
    counts = {
        label: sum(len(inv) for _, inv in pairs) for label, pairs in train.items()
    }
    assert counts["низкий"] > counts["база"] > counts["высокий"]


def test_the_same_people_face_every_deficit_level(panels) -> None:
    """Otherwise a deficit comparison is not paired."""
    ids = [[p.user.user_id for p, _ in pairs] for pairs in panels["train"].values()]
    assert all(x == ids[0] for x in ids)


def test_abstract_missing_count_ignores_inventory(panels) -> None:
    """Two requests differing only in inventory_snapshot must score identically
    -- this is the defining property of the "without store constraints" metric."""
    profile, non_empty_inventory = panels["train"]["база"][0]
    recipe = RECIPES_BY_ID["cottage_cheese_with_sour_cream"]
    assert non_empty_inventory  # sanity: the fixture actually varies
    request_empty_inventory = RecommendationRequest(
        user=profile.user,
        current_receipt=profile.current_receipt,
        purchase_history=profile.purchase_history,
        recipe_catalog=list(RECIPES),
        inventory_snapshot=[],
        now=profile.now,
        limit=3,
    )
    request_full_inventory = request_empty_inventory.model_copy(
        update={"inventory_snapshot": non_empty_inventory}
    )
    assert abstract_missing_count(request_empty_inventory, recipe) == abstract_missing_count(
        request_full_inventory, recipe
    )


def test_constrained_missing_count_never_below_zero_and_none_means_unreachable(panels) -> None:
    for profile, _ in panels["train"]["база"][:5]:
        request = RecommendationRequest(
            user=profile.user,
            current_receipt=profile.current_receipt,
            purchase_history=profile.purchase_history,
            recipe_catalog=list(RECIPES),
            inventory_snapshot=[],  # no products at all -> every required gap is unreachable
            now=profile.now,
            limit=3,
        )
        for recipe in RECIPES:
            result = constrained_missing_count(request, recipe)
            receipt_ids = {
                i for item in profile.current_receipt.items for i in item.ingredient_ids
            }
            has_required_gap = any(
                ing.required and ing.ingredient_id not in receipt_ids
                for ing in recipe.ingredients
            )
            if has_required_gap:
                # Empty inventory_snapshot: no ingredient has a valid product.
                assert result is None, recipe.recipe_id
            else:
                assert result is not None and result >= 0


def test_coverage_shares_are_monotonic_in_threshold(panels) -> None:
    outcomes = evaluate_panel(panels["train"]["база"][:30], list(RECIPES))
    abstract = coverage_shares(outcomes, constrained=False)
    constrained = coverage_shares(outcomes, constrained=True)
    assert abstract[0] <= abstract[1] <= abstract[2]
    assert constrained[0] <= constrained[1] <= constrained[2]


def test_deficit_levels_match_the_calibrated_sensitivity_values() -> None:
    assert DEFICIT_LEVELS["низкий"].no_product_at_all == 0.02
    assert DEFICIT_LEVELS["база"].no_product_at_all == 0.08
    assert DEFICIT_LEVELS["высокий"].no_product_at_all == 0.35
    assert DEFICIT_LEVELS["низкий"].out_of_stock == 0.02
    assert DEFICIT_LEVELS["база"].out_of_stock == 0.10
    assert DEFICIT_LEVELS["высокий"].out_of_stock == 0.35


def test_common_fulfillment_default_matches_the_service() -> None:
    from recsys.experiment3_catalog_coverage import _COMMON_FULFILLMENT_DEFAULT

    assert _COMMON_FULFILLMENT_DEFAULT == frozenset(
        {FulfillmentOption.DELIVERY, FulfillmentOption.NEXT_VISIT}
    )
