"""Experiment 2's new ranking-policy surface: pure model order and the
feasibility cap, plus a regression guard that the new
``RankingPolicy.feasibility_missing_cap`` field does not change what the
policies that don't set it (``EFFORT_FIRST``, ``BLENDED``) already do.

See docs/research/recsys/experiment-plan-ranker-service-catalog.md
("Эксперимент 2") and docs/research/recsys/experiment-2-service-logic-report.md.
"""

from __future__ import annotations

from datetime import datetime, timezone

from recsys.experimental.contracts import (
    FulfillmentOption,
    InventoryProduct,
    ModelRecommendation,
    Receipt,
    ReceiptItem,
    Recipe,
    RecipeIngredient,
    RecipeRecommendation,
    RecommendationMode,
    RecommendationRequest,
    SafetyStatus,
    UserProfile,
)
from recsys.experimental.safety import SafetyPolicy
from recsys.experimental.service import (
    BLENDED,
    EFFORT_FIRST,
    FEASIBILITY_MISSING_CAP,
    FEASIBLE_MODEL_ORDER,
    MAX_EFFORT_MISSING_COUNT,
    MODEL_ORDER,
    RecommendationService,
)

NOW = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)


def _recipe(recipe_id: str, n_ingredients: int) -> Recipe:
    """A recipe whose every ingredient is missing from the receipt and buyable
    from inventory, so ``missing_count`` is controlled exactly by ``n_ingredients``."""
    return Recipe(
        recipe_id=recipe_id,
        title=recipe_id,
        ingredients=[
            RecipeIngredient(
                ingredient_id=f"{recipe_id}_ing_{i}",
                name=f"{recipe_id} ingredient {i}",
                category="pantry",
                required=True,
            )
            for i in range(n_ingredients)
        ],
    )


def _inventory_for(recipe: Recipe) -> list[InventoryProduct]:
    return [
        InventoryProduct(
            sku_id=f"{ingredient.ingredient_id}_sku",
            name=ingredient.name,
            category=ingredient.category,
            ingredient_ids={ingredient.ingredient_id},
            store_id="store_1",
            distance_km=1.0,
            price=100.0,
        )
        for ingredient in recipe.ingredients
    ]


def _request(recipes: list[Recipe]) -> RecommendationRequest:
    receipt = Receipt(
        receipt_id="r1",
        purchased_at=NOW,
        store_id="store_1",
        items=[
            ReceiptItem(
                sku_id="anchor",
                name="anchor item",
                category="pantry",
                quantity=1,
                unit_price=10.0,
            )
        ],
    )
    inventory = [product for recipe in recipes for product in _inventory_for(recipe)]
    return RecommendationRequest(
        user=UserProfile(user_id="u1", radius_km=5.0),
        current_receipt=receipt,
        recipe_catalog=recipes,
        inventory_snapshot=inventory,
        now=NOW,
        limit=10,
    )


class FakeEngine:
    """Ranks by an explicit, caller-supplied score per recipe id.

    ``recsys.experimental.model.MLRecommendationEngine`` is deliberately not used here:
    these tests are about what ``RecommendationService``/``RankingPolicy`` do
    with a fixed ``model_score``, the same fixation the real experiment 2
    script relies on, so the score has to be a dial, not a trained output.
    """

    def __init__(self, scores: dict[str, float]) -> None:
        self._scores = scores

    def rank(self, request: RecommendationRequest) -> list[ModelRecommendation]:
        return [
            ModelRecommendation(
                recipe_id=recipe.recipe_id,
                mode=RecommendationMode.EXPLORE,
                score=self._scores[recipe.recipe_id],
                reason_codes=["personalized_discovery"],
            )
            for recipe in request.recipe_catalog
        ]


def _service(scores: dict[str, float], policy) -> RecommendationService:
    return RecommendationService(
        engine=FakeEngine(scores), safety_policy=SafetyPolicy(), ranking_policy=policy
    )


# --- MODEL_ORDER ----------------------------------------------------------


def test_model_order_sorts_purely_by_model_score() -> None:
    """The recipe with more missing ingredients wins if the model scores it
    higher — the opposite of what EFFORT_FIRST would do, and the entire point
    of this policy: no effort gating at all."""
    light = _recipe("light", 1)
    heavy = _recipe("heavy", 5)
    request = _request([light, heavy])
    service = _service({"light": 0.4, "heavy": 0.9}, MODEL_ORDER)

    response = service.recommend(request)

    assert [r.recipe_id for r in response.recommendations] == ["heavy", "light"]
    assert response.filtered_candidates == 0


def test_effort_first_would_have_ordered_the_same_pair_differently() -> None:
    """Same candidates and scores as above, shipped policy: proves the two
    policies genuinely disagree rather than coincidentally agreeing above."""
    light = _recipe("light", 1)
    heavy = _recipe("heavy", 5)
    request = _request([light, heavy])
    service = _service({"light": 0.4, "heavy": 0.9}, EFFORT_FIRST)

    response = service.recommend(request)

    assert [r.recipe_id for r in response.recommendations] == ["light", "heavy"]


# --- feasibility_missing_cap / FEASIBLE_MODEL_ORDER ------------------------


def test_feasibility_cap_drops_over_cap_recipes_and_counts_them() -> None:
    light = _recipe("light", 1)
    heavy = _recipe("heavy", FEASIBILITY_MISSING_CAP + 2)
    request = _request([light, heavy])
    service = _service({"light": 0.5, "heavy": 0.9}, FEASIBLE_MODEL_ORDER)

    response = service.recommend(request)

    assert [r.recipe_id for r in response.recommendations] == ["light"]
    assert response.filtered_candidates == 1
    assert any("missing_count_exceeds_cap" in w for w in response.warnings)


def test_feasibility_cap_keeps_pure_model_order_among_survivors() -> None:
    a = _recipe("a", 1)
    b = _recipe("b", 2)
    request = _request([a, b])
    service = _service({"a": 0.3, "b": 0.8}, FEASIBLE_MODEL_ORDER)

    response = service.recommend(request)

    assert [r.recipe_id for r in response.recommendations] == ["b", "a"]
    assert response.filtered_candidates == 0


def test_feasibility_cap_boundary_is_inclusive() -> None:
    """missing_count == cap survives; only strictly-over-cap is dropped."""
    at_cap = _recipe("at_cap", FEASIBILITY_MISSING_CAP)
    over_cap = _recipe("over_cap", FEASIBILITY_MISSING_CAP + 1)
    request = _request([at_cap, over_cap])
    service = _service({"at_cap": 0.5, "over_cap": 0.5}, FEASIBLE_MODEL_ORDER)

    response = service.recommend(request)

    assert [r.recipe_id for r in response.recommendations] == ["at_cap"]


def test_all_candidates_over_cap_yields_empty_recommendations() -> None:
    """Emptying the response is expected only for the feasibility-cap
    variant, by construction — this is what makes that possible."""
    heavy = _recipe("heavy", FEASIBILITY_MISSING_CAP + 3)
    request = _request([heavy])
    service = _service({"heavy": 0.9}, FEASIBLE_MODEL_ORDER)

    response = service.recommend(request)

    assert response.recommendations == []
    assert response.filtered_candidates == 1


# --- regression: the new field must not change existing policies ----------


def test_existing_policies_default_to_no_feasibility_cap() -> None:
    assert EFFORT_FIRST.feasibility_missing_cap is None
    assert BLENDED.feasibility_missing_cap is None


def test_effort_first_sort_key_is_unchanged_by_the_new_field() -> None:
    item = RecipeRecommendation(
        recipe_id="x",
        title="x",
        mode=RecommendationMode.EXPLORE,
        model_score=0.77,
        missing_count=3,
        reason_codes=["personalized_discovery"],
        ingredients=[],
        fulfillment_options={FulfillmentOption.DELIVERY},
        safety_status=SafetyStatus.APPROVED,
    )
    # Exactly the formula from before feasibility_missing_cap existed.
    assert EFFORT_FIRST.sort_key(item) == (3, -0.77, "x")


def test_blended_sort_key_is_unchanged_by_the_new_field() -> None:
    item = RecipeRecommendation(
        recipe_id="y",
        title="y",
        mode=RecommendationMode.EXPLORE,
        model_score=0.6,
        missing_count=4,
        reason_codes=["personalized_discovery"],
        ingredients=[],
        fulfillment_options={FulfillmentOption.DELIVERY},
        safety_status=SafetyStatus.APPROVED,
    )
    expected_effort_score = 1.0 - min(4, MAX_EFFORT_MISSING_COUNT) / MAX_EFFORT_MISSING_COUNT
    expected_blended = 0.5 * 0.6 + 0.5 * expected_effort_score
    assert BLENDED.sort_key(item) == (-round(expected_blended, 6), 4, "y")


def test_no_cap_variant_never_drops_on_missing_count_alone() -> None:
    """EFFORT_FIRST/BLENDED/MODEL_ORDER never invoke the cap filter: a recipe
    with a large missing_count is reordered, never dropped, unless a policy
    actually sets feasibility_missing_cap."""
    heavy = _recipe("heavy", FEASIBILITY_MISSING_CAP + 5)
    request = _request([heavy])
    for policy in (EFFORT_FIRST, BLENDED, MODEL_ORDER):
        service = _service({"heavy": 0.5}, policy)
        response = service.recommend(request)
        assert [r.recipe_id for r in response.recommendations] == ["heavy"]
        assert response.filtered_candidates == 0
