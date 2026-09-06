"""How a simulated user reacts to a recommendation — several ways, on purpose.

Why more than one
-----------------
A synthetic A/B needs something to play the user. Whatever we pick becomes the
ground truth, and the winner is then a property of that choice as much as of the
recommender. ``recsys.experimental.evaluation.oracle_relevant`` already shows the failure
mode in miniature: it shares its rule structure with the label generator that
trained ``recsys.experimental.model``, so a good score there partly measures the model
agreeing with its own teacher.

The fix is not a better single simulator — there is no way to validate one
without real users. The fix is several simulators with *deliberately different
functional forms*, and a result that only counts when they agree. If arm B wins
under a threshold rule, a stochastic utility model and a pure cost calculator,
that is evidence about B. If B wins only under the oracle it shares ancestry
with, that is evidence about the oracle.

The four below disagree by construction:

``RuleBasedResponder``
    Hard thresholds, no randomness. Buys when the basket is small enough and
    the clock allows.
``ProbabilisticResponder``
    Linear utility per action, softmax, sampled. Never certain about anything.
``EconomicResponder``
    Ignores taste, history and novelty entirely. Compares roubles per serving
    and minutes. It is the adversarial reading of the product: a user who only
    asks "is this cheaper than buying it ready?".
``OracleResponder``
    The incumbent rule from ``recsys.experimental.evaluation``. Kept precisely *because* it
    is self-referential — it is the control that shows what a compromised
    simulator looks like next to the others.

``LLMResponder`` is the seat for a language model. It holds no model and fakes
no answers: it wraps a caller-supplied ``decide`` callable and validates that
whatever comes back is one of the five actions. Wiring a real model in is the
caller's job, so nothing here can quietly become "we asked an LLM" when we did
not.

What a responder may look at
----------------------------
Only what a user could see: the recipe, the missing ingredients and their
prices, the prep time, whether they had saved it, and the ready-made
alternative. Never ``model_score`` or the arm's identity — a simulator that can
see which recommender produced a card can trivially manufacture a winner, and
``tests/test_response_models.py`` enforces the ban.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Protocol

from recsys.experimental.contracts import (
    IngredientSource,
    Recipe,
    RecipeRecommendation,
    RecommendationMode,
    RecommendationRequest,
)
from recsys.experimental.profiles import ArchetypeParams, SyntheticProfile


class UserAction(str, Enum):
    """What the simulated user does with one recommendation card."""

    IGNORE = "ignore"
    CLICK = "click"
    SAVE = "save"
    BUY = "buy"
    #: Bought the ready-made counterpart instead of cooking. Still a sale for
    #: the retailer, which is why it is tracked separately rather than folded
    #: into IGNORE.
    SUBSTITUTE = "substitute"


#: Actions that put money in the till.
CONVERTING_ACTIONS: frozenset[UserAction] = frozenset(
    {UserAction.BUY, UserAction.SUBSTITUTE}
)

#: Actions that show the card did something at all.
ENGAGED_ACTIONS: frozenset[UserAction] = frozenset(
    {UserAction.CLICK, UserAction.SAVE, UserAction.BUY, UserAction.SUBSTITUTE}
)


@dataclass(frozen=True)
class ResponseFeatures:
    """What the user can see on the card, and nothing else."""

    missing_count: int
    missing_cost_rub: float
    has_markdown: bool
    prep_minutes: int
    servings: int
    is_saved: bool
    mode: RecommendationMode
    ready_meal_price_rub: float | None

    @property
    def cook_cost_per_serving_rub(self) -> float:
        return self.missing_cost_rub / max(self.servings, 1)

    @property
    def ready_is_cheaper(self) -> bool:
        """Per portion, is buying it ready cheaper than the missing basket?"""
        if self.ready_meal_price_rub is None:
            return False
        return self.ready_meal_price_rub < self.cook_cost_per_serving_rub


def extract_features(
    recommendation: RecipeRecommendation, recipe: Recipe, *, is_saved: bool
) -> ResponseFeatures:
    missing_cost = 0.0
    has_markdown = False
    for ingredient in recommendation.ingredients:
        if not ingredient.product_options:
            continue
        if ingredient.source not in (
            IngredientSource.MARKDOWN,
            IngredientSource.FULL_PRICE,
        ):
            continue
        cheapest = min(option.price for option in ingredient.product_options)
        missing_cost += cheapest
        has_markdown = has_markdown or ingredient.source == IngredientSource.MARKDOWN
    alternative = recommendation.ready_meal_alternative
    return ResponseFeatures(
        missing_count=recommendation.missing_count,
        missing_cost_rub=round(missing_cost, 2),
        has_markdown=has_markdown,
        prep_minutes=recipe.preparation_minutes or 0,
        servings=recipe.servings,
        is_saved=is_saved,
        mode=recommendation.mode,
        ready_meal_price_rub=alternative.price if alternative else None,
    )


@dataclass
class ResponseContext:
    """Everything a simulator is allowed to condition on."""

    profile: SyntheticProfile
    #: The user's traits *in the current regime*, not the global defaults.
    params: ArchetypeParams
    recipe: Recipe
    features: ResponseFeatures
    request: RecommendationRequest
    rng: random.Random


class ResponseModel(Protocol):
    name: str

    def respond(self, ctx: ResponseContext) -> UserAction: ...


class RuleBasedResponder:
    """Thresholds only. Deterministic given the context.

    The plainest reading of the product: a person cooks if the shopping list is
    short enough and they have time, takes the ready meal if it is clearly
    cheaper, and otherwise scrolls past.
    """

    name = "rule_based"

    def respond(self, ctx: ResponseContext) -> UserAction:
        f = ctx.features
        params = ctx.params

        tolerance = params.max_missing_tolerance
        if f.has_markdown and params.markdown_affinity >= 0.5:
            tolerance += 1

        over_budget = f.missing_count > tolerance
        out_of_time = (
            params.time_limit_minutes is not None
            and f.prep_minutes > params.time_limit_minutes
        )

        # A ready meal rescues a card the user would otherwise drop, but only
        # for someone who actually reacts to price.
        if (over_budget or out_of_time) and f.ready_is_cheaper:
            if params.markdown_affinity >= 0.5:
                return UserAction.SUBSTITUTE
            return UserAction.IGNORE
        if over_budget or out_of_time:
            return UserAction.IGNORE

        if f.is_saved:
            return UserAction.BUY
        if f.missing_count <= 1:
            return UserAction.BUY
        if f.mode == RecommendationMode.EXPLORE and params.discovery_acceptance < 0.4:
            return UserAction.CLICK
        if f.missing_count <= tolerance - 1:
            return UserAction.SAVE
        return UserAction.CLICK


class ProbabilisticResponder:
    """Linear utility per action, softmax, sampled.

    Same inputs as the rule-based model, entirely different shape: nothing is a
    hard cutoff, so a long shopping list lowers the odds of a purchase instead
    of forbidding it. Where the two agree, the finding is not an artefact of
    either one's thresholds.
    """

    name = "probabilistic"

    #: Utility weights. Illustrative, not fitted — their job is to be a
    #: different functional form, not a better one.
    TEMPERATURE = 1.0

    def respond(self, ctx: ResponseContext) -> UserAction:
        f = ctx.features
        p = ctx.params

        missing_pressure = f.missing_count / max(p.max_missing_tolerance, 1)
        cost_pressure = min(f.cook_cost_per_serving_rub / 250.0, 3.0)
        time_pressure = (
            0.0
            if p.time_limit_minutes is None
            else max(0.0, f.prep_minutes - p.time_limit_minutes) / 60.0
        )
        novelty_pull = (
            p.discovery_acceptance if f.mode == RecommendationMode.EXPLORE else 0.0
        )
        markdown_pull = p.markdown_affinity if f.has_markdown else 0.0

        utilities = {
            UserAction.IGNORE: 0.6 + 1.1 * missing_pressure + 1.4 * time_pressure,
            UserAction.CLICK: 0.9 + 0.6 * novelty_pull - 0.2 * missing_pressure,
            UserAction.SAVE: 0.4
            + 1.2 * p.repeat_probability
            + 0.5 * novelty_pull
            - 0.4 * missing_pressure,
            UserAction.BUY: 0.3
            + 1.6 * float(f.is_saved)
            + 1.0 * markdown_pull
            - 0.9 * missing_pressure
            - 0.5 * cost_pressure
            - 1.2 * time_pressure,
            UserAction.SUBSTITUTE: (
                -3.0
                if f.ready_meal_price_rub is None
                else (
                    -0.4
                    + 1.3 * float(f.ready_is_cheaper)
                    + 0.9 * p.markdown_affinity
                    + 0.8 * time_pressure
                    + 0.4 * missing_pressure
                )
            ),
        }
        actions = list(utilities)
        weights = [math.exp(utilities[a] / self.TEMPERATURE) for a in actions]
        return ctx.rng.choices(actions, weights=weights, k=1)[0]


class EconomicResponder:
    """Roubles and minutes only. No taste, no history, no novelty.

    The adversarial user: they do not care that the recipe suits them, only
    whether cooking beats buying. A recommender that wins here is winning on
    basket economics rather than on personalisation, which is worth being able
    to tell apart.
    """

    name = "economic"

    #: Rouble value the simulated user puts on an hour of cooking. Invented,
    #: and one of the assumptions ``recsys.sensitivity`` sweeps: it sets how
    #: readily this simulator prefers a ready meal over cooking.
    DEFAULT_TIME_VALUE_RUB_PER_HOUR = 300.0

    def __init__(self, time_value_rub_per_hour: float | None = None) -> None:
        self.time_value_rub_per_hour = (
            self.DEFAULT_TIME_VALUE_RUB_PER_HOUR
            if time_value_rub_per_hour is None
            else time_value_rub_per_hour
        )

    def respond(self, ctx: ResponseContext) -> UserAction:
        f = ctx.features
        cook_cost = f.cook_cost_per_serving_rub
        effort_cost = (
            self.time_value_rub_per_hour * f.prep_minutes / 60.0 / max(f.servings, 1)
        )
        total_cook = cook_cost + effort_cost

        if f.ready_meal_price_rub is not None and f.ready_meal_price_rub < total_cook:
            return UserAction.SUBSTITUTE
        if f.missing_count == 0:
            return UserAction.BUY
        if total_cook <= 150.0:
            return UserAction.BUY
        if total_cook <= 300.0:
            return UserAction.SAVE
        if total_cook <= 450.0:
            return UserAction.CLICK
        return UserAction.IGNORE


class OracleResponder:
    """The incumbent relevance rule from ``recsys.experimental.evaluation``.

    Included as a *control*, not as a peer. It descends from the same archetype
    rules that generated ``recsys.experimental.model``'s training labels, so an arm built on
    that model has a structural advantage here that it does not have anywhere
    else. Watching it disagree with the other three is the point.
    """

    name = "oracle_selfref"

    def respond(self, ctx: ResponseContext) -> UserAction:
        from recsys.experimental.evaluation import oracle_relevant

        relevant = oracle_relevant(ctx.profile, ctx.recipe, ctx.request)
        if not relevant:
            if ctx.features.ready_is_cheaper:
                return UserAction.SUBSTITUTE
            return UserAction.IGNORE
        return UserAction.BUY if ctx.features.is_saved else UserAction.SAVE


class LLMResponder:
    """Seat for a language-model simulator. Holds no model.

    ``decide`` receives the context and must return a ``UserAction`` or its
    string value; anything else raises. There is no built-in fallback on
    purpose: a stub that silently returned plausible actions would let a run be
    reported as "validated against an LLM" when no model was ever called.
    """

    def __init__(
        self, decide: Callable[[ResponseContext], UserAction | str], name: str = "llm"
    ) -> None:
        self.name = name
        self._decide = decide

    def respond(self, ctx: ResponseContext) -> UserAction:
        raw = self._decide(ctx)
        if isinstance(raw, UserAction):
            return raw
        try:
            return UserAction(str(raw).strip().lower())
        except ValueError as error:
            raise ValueError(
                f"{self.name} returned {raw!r}; expected one of "
                f"{[a.value for a in UserAction]}"
            ) from error


#: The simulators a default benchmark run uses. ``OracleResponder`` is last so
#: reports list the trustworthy ones first.
DEFAULT_RESPONDERS: tuple[ResponseModel, ...] = (
    RuleBasedResponder(),
    ProbabilisticResponder(),
    EconomicResponder(),
    OracleResponder(),
)

#: Responders whose verdict is not structurally entangled with any arm. A
#: robustness claim must hold on these; the oracle is reported beside them.
INDEPENDENT_RESPONDER_NAMES: frozenset[str] = frozenset(
    {"rule_based", "probabilistic", "economic"}
)
