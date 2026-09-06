"""The user simulators, and the guarantees that make their verdicts mean anything."""

from __future__ import annotations

import random
from dataclasses import fields
from datetime import datetime, timezone

import pytest

from recsys.experimental.contracts import (
    IngredientRecommendation,
    IngredientSource,
    ProductOption,
    ReadyMealOption,
    Receipt,
    ReceiptItem,
    RecipeRecommendation,
    RecommendationMode,
    RecommendationRequest,
    SafetyStatus,
    UserProfile,
)
from recsys.experimental.profiles import ARCHETYPES, SyntheticProfile
from recsys.experimental.recipes import RECIPES_BY_ID
from recsys.response_models import (
    CONVERTING_ACTIONS,
    DEFAULT_RESPONDERS,
    ENGAGED_ACTIONS,
    INDEPENDENT_RESPONDER_NAMES,
    EconomicResponder,
    LLMResponder,
    ProbabilisticResponder,
    ResponseContext,
    ResponseFeatures,
    RuleBasedResponder,
    UserAction,
    extract_features,
)

NOW = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
RECIPE = RECIPES_BY_ID["olivier_salad"]


def _option(price: float, markdown: bool = False) -> ProductOption:
    return ProductOption(
        sku_id="s1",
        name="x",
        category="vegetable",
        store_id="store_10",
        distance_km=1.0,
        price=price,
        original_price=price,
        brand=None,
        source=IngredientSource.MARKDOWN if markdown else IngredientSource.FULL_PRICE,
        expires_at=None,
        fulfillment_options=set(),
        price_is_estimate=True,
    )


def _card(
    *,
    missing_count: int = 2,
    option_prices: tuple[float, ...] = (100.0, 200.0),
    markdown: bool = False,
    ready_price: float | None = None,
    mode: RecommendationMode = RecommendationMode.CURRENT,
) -> RecipeRecommendation:
    ingredients = [
        IngredientRecommendation(
            ingredient_id=f"i{n}",
            name=f"i{n}",
            category="vegetable",
            source=IngredientSource.MARKDOWN if markdown else IngredientSource.FULL_PRICE,
            product_options=[_option(price, markdown)],
        )
        for n, price in enumerate(option_prices)
    ]
    alternative = (
        ReadyMealOption(
            chain="pyaterochka",
            plu="1",
            name="готовое",
            recipe_ids={RECIPE.recipe_id},
            price=ready_price,
        )
        if ready_price is not None
        else None
    )
    return RecipeRecommendation(
        recipe_id=RECIPE.recipe_id,
        title=RECIPE.title,
        mode=mode,
        model_score=0.9,
        missing_count=missing_count,
        reason_codes=["current_receipt_overlap"],
        ingredients=ingredients,
        fulfillment_options=set(),
        safety_status=SafetyStatus.APPROVED,
        ready_meal_alternative=alternative,
        ready_meal_option_count=1 if alternative else 0,
    )


def _context(card: RecipeRecommendation, archetype: str = "routine") -> ResponseContext:
    receipt = Receipt(
        receipt_id="r1",
        purchased_at=NOW,
        store_id="store_10",
        items=[
            ReceiptItem(
                sku_id="s",
                name="n",
                category="dairy",
                ingredient_ids={"milk"},
                quantity=1,
                unit_price=50.0,
            )
        ],
    )
    user = UserProfile(user_id="u1")
    profile = SyntheticProfile(
        archetype=archetype, user=user, current_receipt=receipt, purchase_history=[], now=NOW
    )
    request = RecommendationRequest(
        user=user,
        current_receipt=receipt,
        recipe_catalog=[RECIPE],
        now=NOW,
    )
    return ResponseContext(
        profile=profile,
        params=ARCHETYPES[archetype],
        recipe=RECIPE,
        features=extract_features(card, RECIPE, is_saved=False),
        request=request,
        rng=random.Random(0),
    )


# --- the guarantee that makes the bench meaningful ----------------------


def test_a_simulator_cannot_see_the_score_or_which_arm_produced_the_card() -> None:
    """A simulator that can identify the arm can manufacture any winner.

    ``ResponseFeatures`` is the whole of what a responder sees about the card,
    so the ban is structural rather than a convention someone must remember.
    """
    visible = {f.name for f in fields(ResponseFeatures)}
    for forbidden in ("model_score", "score", "arm", "engine", "policy", "reason_codes"):
        assert forbidden not in visible

    context_fields = {f.name for f in fields(ResponseContext)}
    assert "arm" not in context_fields
    assert "recommendation" not in context_fields, (
        "handing over the whole card would leak model_score"
    )


def test_features_read_the_cheapest_option_and_flag_markdown() -> None:
    card = _card(missing_count=2, option_prices=(150.0, 90.0), markdown=True)
    features = extract_features(card, RECIPE, is_saved=True)
    assert features.missing_cost_rub == 240.0
    assert features.has_markdown is True
    assert features.is_saved is True
    assert features.servings == RECIPE.servings
    assert features.cook_cost_per_serving_rub == pytest.approx(240.0 / RECIPE.servings)


def test_ready_is_cheaper_compares_per_serving() -> None:
    card = _card(option_prices=(400.0,), ready_price=50.0)
    assert extract_features(card, RECIPE, is_saved=False).ready_is_cheaper is True
    card = _card(option_prices=(40.0,), ready_price=500.0)
    assert extract_features(card, RECIPE, is_saved=False).ready_is_cheaper is False


def test_ingredients_already_in_the_receipt_cost_nothing() -> None:
    card = _card(option_prices=(100.0,))
    card.ingredients.append(
        IngredientRecommendation(
            ingredient_id="have",
            name="have",
            category="dairy",
            source=IngredientSource.RECEIPT,
        )
    )
    assert extract_features(card, RECIPE, is_saved=False).missing_cost_rub == 100.0


# --- individual simulators ---------------------------------------------


@pytest.mark.parametrize("responder", DEFAULT_RESPONDERS, ids=lambda r: r.name)
def test_every_responder_returns_a_valid_action(responder) -> None:
    for missing in (0, 2, 8):
        for ready in (None, 40.0, 900.0):
            action = responder.respond(
                _context(_card(missing_count=missing, ready_price=ready))
            )
            assert isinstance(action, UserAction)


def test_rule_based_is_deterministic() -> None:
    responder = RuleBasedResponder()
    card = _card(missing_count=2)
    first = responder.respond(_context(card))
    assert all(responder.respond(_context(card)) == first for _ in range(5))


def test_rule_based_ignores_a_basket_beyond_tolerance() -> None:
    responder = RuleBasedResponder()
    huge = _card(missing_count=ARCHETYPES["routine"].max_missing_tolerance + 3)
    assert responder.respond(_context(huge)) == UserAction.IGNORE


def test_rule_based_substitutes_when_the_ready_meal_rescues_a_lost_card() -> None:
    responder = RuleBasedResponder()
    # value shoppers are the promo-sensitive archetype
    card = _card(
        missing_count=ARCHETYPES["value"].max_missing_tolerance + 3,
        option_prices=(400.0, 400.0),
        ready_price=20.0,
    )
    assert responder.respond(_context(card, "value")) == UserAction.SUBSTITUTE


def test_probabilistic_is_stochastic_but_seed_reproducible() -> None:
    responder = ProbabilisticResponder()
    card = _card(missing_count=3)

    def draw(seed: int) -> UserAction:
        ctx = _context(card)
        ctx.rng = random.Random(seed)
        return responder.respond(ctx)

    assert draw(1) == draw(1)
    outcomes = {draw(seed) for seed in range(40)}
    assert len(outcomes) > 1, "a stochastic responder that never varies is not stochastic"


def test_probabilistic_never_substitutes_without_an_alternative() -> None:
    responder = ProbabilisticResponder()
    card = _card(ready_price=None)
    for seed in range(200):
        ctx = _context(card)
        ctx.rng = random.Random(seed)
        assert responder.respond(ctx) != UserAction.SUBSTITUTE


def test_economic_responder_ignores_taste_entirely() -> None:
    """Same numbers, different archetype: the answer must not move."""
    responder = EconomicResponder()
    card = _card(missing_count=2, option_prices=(80.0, 80.0))
    actions = {responder.respond(_context(card, name)) for name in ARCHETYPES}
    assert len(actions) == 1


def test_economic_responder_takes_the_cheaper_ready_meal() -> None:
    responder = EconomicResponder()
    assert (
        responder.respond(_context(_card(option_prices=(900.0,), ready_price=30.0)))
        == UserAction.SUBSTITUTE
    )


def test_responders_disagree_with_each_other() -> None:
    """If every simulator agreed always, running several would prove nothing."""
    cards = [
        _card(missing_count=m, option_prices=p, ready_price=r)
        for m, p, r in (
            (1, (60.0,), None),
            (3, (250.0, 250.0), 90.0),
            (6, (400.0, 400.0, 400.0), 120.0),
            (0, (), None),
        )
    ]
    disagreements = 0
    for card in cards:
        actions = {r.respond(_context(card)) for r in DEFAULT_RESPONDERS}
        if len(actions) > 1:
            disagreements += 1
    assert disagreements >= 2


def test_independent_responders_exclude_the_self_referential_oracle() -> None:
    names = {r.name for r in DEFAULT_RESPONDERS}
    assert "oracle_selfref" in names
    assert "oracle_selfref" not in INDEPENDENT_RESPONDER_NAMES
    assert INDEPENDENT_RESPONDER_NAMES < names


# --- the LLM seat --------------------------------------------------------


def test_llm_responder_accepts_an_action_or_its_string() -> None:
    ctx = _context(_card())
    assert LLMResponder(lambda _: UserAction.BUY).respond(ctx) == UserAction.BUY
    assert LLMResponder(lambda _: " Buy ").respond(ctx) == UserAction.BUY


def test_llm_responder_refuses_to_invent_an_answer() -> None:
    """No silent fallback: a run must not look validated when nothing answered."""
    responder = LLMResponder(lambda _: "maybe later")
    with pytest.raises(ValueError, match="expected one of"):
        responder.respond(_context(_card()))


def test_action_groupings_are_coherent() -> None:
    assert CONVERTING_ACTIONS < ENGAGED_ACTIONS
    assert UserAction.IGNORE not in ENGAGED_ACTIONS
    assert UserAction.SUBSTITUTE in CONVERTING_ACTIONS
