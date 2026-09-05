"""Taste derived from prepared-meal purchases.

These run against the **real** pair table and real PLUs from the September 2026
Moscow snapshot, not fixtures: the point of this pipeline is that it works on
retailer identifiers, and a test using invented ids would not check that.
"""

from __future__ import annotations

from datetime import timedelta

from app.contracts import Receipt, ReceiptItem
from recsys.catalog import CATEGORIES
from recsys.dish_signal import (
    DISH_FEATURE_NAMES,
    READY_MEAL_CATEGORY,
    TASTE_HALF_LIFE_DAYS,
    dish_features,
    dish_signal,
    observed_dishes,
    parse_ready_meal_ref,
    ready_meal_receipt_item,
    ready_meal_ref,
)
from recsys.profiles import DEFAULT_NOW
from recsys.ready_food_pairs import READY_FOOD_PAIRS, pairs_for_plu
from recsys.recipes import RECIPES_BY_ID


def _pair(recipe_id: str):
    return next(p for p in READY_FOOD_PAIRS if p.recipe_id == recipe_id)


def _receipt(items, *, days_ago: float, receipt_id: str = "r") -> Receipt:
    return Receipt(
        receipt_id=receipt_id,
        purchased_at=DEFAULT_NOW - timedelta(days=days_ago),
        store_id="store_10",
        items=items,
    )


def _meal_item(recipe_id: str) -> ReceiptItem:
    pair = _pair(recipe_id)
    meal = pair.cheapest_meal() or pair.meals[0]
    return ready_meal_receipt_item(
        chain=meal.chain,
        plu=meal.plu,
        name=meal.name,
        price_rub=meal.median_price_rub or 100.0,
    )


def _grocery_item(sku: str = "milk_gen_0") -> ReceiptItem:
    return ReceiptItem(
        sku_id=sku,
        name="Молоко",
        category="dairy",
        ingredient_ids={"milk"},
        quantity=1,
        unit_price=90.0,
    )


# --- identifiers -----------------------------------------------------------


def test_a_real_plu_round_trips() -> None:
    assert parse_ready_meal_ref(ready_meal_ref("perekrestok", "4452460")) == (
        "perekrestok",
        "4452460",
    )


def test_a_grocery_sku_is_not_mistaken_for_a_prepared_meal() -> None:
    assert parse_ready_meal_ref("syn_garlic_fp_3") is None
    assert parse_ready_meal_ref("") is None
    assert parse_ready_meal_ref("perekrestok:") is None


def test_the_prepared_meal_category_stays_out_of_the_ingredient_vocabulary() -> None:
    """Everything computing category shares iterates CATEGORIES; a prepared
    meal joining that tuple would silently distort ingredient features."""
    assert READY_MEAL_CATEGORY not in CATEGORIES


def test_a_prepared_meal_line_carries_no_ingredients() -> None:
    """Buying a ready lasagne is not buying its ingredients. Every coverage and
    pantry feature keys off ingredient_ids, so this set must stay empty."""
    assert _meal_item("borsch").ingredient_ids == set()


# --- resolution ------------------------------------------------------------


def test_a_real_purchase_resolves_to_its_recipe() -> None:
    signal = dish_signal([_receipt([_meal_item("borsch")], days_ago=3)], now=DEFAULT_NOW)
    assert signal.n_observations == 1
    assert signal.same_dish_affinity("borsch") == 1.0
    assert signal.same_dish_affinity("pasta_tomato") == 0.0


def test_taste_generalises_to_dish_type_and_cuisine_but_not_beyond() -> None:
    signal = dish_signal([_receipt([_meal_item("borsch")], days_ago=3)], now=DEFAULT_NOW)
    borsch = RECIPES_BY_ID["borsch"]
    other_soup = RECIPES_BY_ID["cheese_soup"]
    pasta = RECIPES_BY_ID["pasta_tomato"]

    assert dish_features(signal, borsch)["same_dish_ready_affinity"] == 1.0
    # Another soup inherits the dish-type evidence without inheriting the claim
    # that this exact dish was wanted.
    assert dish_features(signal, other_soup)["dish_type_affinity"] == 1.0
    assert dish_features(signal, other_soup)["same_dish_ready_affinity"] == 0.0
    assert dish_features(signal, pasta)["dish_type_affinity"] == 0.0


def test_groceries_contribute_nothing_to_taste() -> None:
    signal = dish_signal([_receipt([_grocery_item()], days_ago=3)], now=DEFAULT_NOW)
    assert signal.n_observations == 0
    assert not signal.has_signal


def test_an_ambiguous_product_splits_its_evidence() -> None:
    """"Плов с курицей" stands in for both pilaf recipes. Counting it once per
    recipe would let one ambiguous purchase outweigh an unambiguous one."""
    ambiguous = [
        (pair, meal)
        for pair in READY_FOOD_PAIRS
        for meal in pair.meals
        if len(pairs_for_plu(meal.chain, meal.plu)) > 1
    ]
    if not ambiguous:  # pragma: no cover - depends on the snapshot
        return
    _, meal = ambiguous[0]
    matched = pairs_for_plu(meal.chain, meal.plu)
    item = ready_meal_receipt_item(
        chain=meal.chain, plu=meal.plu, name=meal.name, price_rub=100.0
    )
    signal = dish_signal([_receipt([item], days_ago=1)], now=DEFAULT_NOW)
    total = sum(signal.recipe_weight.values())
    per_recipe = [signal.recipe_weight[p.recipe_id] for p in matched]
    assert all(abs(w - total / len(matched)) < 1e-9 for w in per_recipe)


# --- time ------------------------------------------------------------------


def test_recent_taste_outweighs_old_taste() -> None:
    recent = dish_signal([_receipt([_meal_item("borsch")], days_ago=1)], now=DEFAULT_NOW)
    old = dish_signal(
        [_receipt([_meal_item("borsch")], days_ago=TASTE_HALF_LIFE_DAYS * 3)],
        now=DEFAULT_NOW,
    )
    assert sum(recent.recipe_weight.values()) > sum(old.recipe_weight.values())


def test_taste_decays_far_slower_than_perishable_stock() -> None:
    """Liking borsch does not expire on the dairy clock.

    ``recsys.pantry`` models whether food is physically gone — dairy at five
    days, meat at four. This models whether a preference still holds, which is
    a different quantity on a different scale, and the two must not be
    accidentally tuned to the same number.
    """
    from recsys.pantry import CATEGORY_HALF_LIFE_DAYS

    perishables = [CATEGORY_HALF_LIFE_DAYS[c] for c in ("dairy", "meat", "vegetable")]
    assert TASTE_HALF_LIFE_DAYS > 5 * max(perishables)


def test_a_purchase_after_now_is_not_a_feature() -> None:
    """A feature computed "as of now" must not read the future — the same leak
    that was found in the history generator."""
    future = _receipt([_meal_item("borsch")], days_ago=-10)
    assert observed_dishes([future])  # the line exists
    assert dish_signal([future], now=DEFAULT_NOW).n_observations == 0


# --- feature contract ------------------------------------------------------


def test_features_match_the_declared_names() -> None:
    signal = dish_signal([_receipt([_meal_item("borsch")], days_ago=2)], now=DEFAULT_NOW)
    features = dish_features(signal, RECIPES_BY_ID["borsch"])
    assert tuple(features) == DISH_FEATURE_NAMES


def test_no_signal_is_flagged_rather_than_read_as_dislike() -> None:
    """Without the guard, a shopper who never bought prepared food looks
    identical to one whose purchases all missed this dish."""
    empty = dish_signal([], now=DEFAULT_NOW)
    features = dish_features(empty, RECIPES_BY_ID["borsch"])
    assert features["has_dish_signal"] == 0.0
    assert features["same_dish_ready_affinity"] == 0.0

    present = dish_signal([_receipt([_meal_item("syrniki")], days_ago=2)], now=DEFAULT_NOW)
    assert dish_features(present, RECIPES_BY_ID["borsch"])["has_dish_signal"] == 1.0


def test_ready_meal_share_measures_how_much_they_buy_prepared() -> None:
    mixed = _receipt(
        [_meal_item("borsch"), _grocery_item("a"), _grocery_item("b"), _grocery_item("c")],
        days_ago=2,
    )
    signal = dish_signal([mixed], now=DEFAULT_NOW)
    assert abs(signal.ready_meal_share - 0.25) < 1e-9
