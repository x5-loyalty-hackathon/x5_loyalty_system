"""A/B bench for recommenders across many worlds and many simulated users.

What this is for
----------------
Not to predict uplift. A synthetic bench cannot do that: it has no way to tell
which of two plausible worlds resembles the real chain, and the winner can flip
between them (see ``recsys.regimes``). What it *can* do is kill bad ideas
cheaply and say how fragile a good one is.

So the output is deliberately not "B gives +4.2%". It is:

    B beats A in 78% of (world x simulated-user) cells, including under every
    independent simulator, and loses only where <condition>.

Three properties make that claim worth anything, and all three are enforced
here rather than left to discipline:

*Paired comparison.* Every arm sees the same profiles and the same inventory
snapshot for a given world. Arms differ only in how they rank. Regenerating
inventory per arm would let supply noise masquerade as a ranking effect.

*Shared cards across simulators.* A recommendation is produced once per
(world, user, arm) and then judged by all simulators. Every simulator therefore
argues about identical evidence.

*A negative control.* ``RandomEngine`` is run as an arm. A bench that cannot
show random ranking losing is not measuring ranking, and ``verdict()`` says so
out loud instead of leaving the reader to check.

Cost
----
Work scales with ``regimes x users x arms`` — the simulators are cheap and ride
along on cards already computed. ``DEFAULT_USERS_PER_REGIME`` is small enough
for the test suite; ``python -m recsys.benchmark`` runs the full grid.
"""

from __future__ import annotations

import random
import statistics
from collections import Counter
from dataclasses import dataclass, field

from recsys.experimental.contracts import (
    IngredientSource,
    ModelRecommendation,
    Recipe,
    RecommendationMode,
    RecommendationRequest,
)
from recsys.experimental.recommender import DeterministicMockEngine, RecommendationEngine
from recsys.experimental.safety import SafetyPolicy
from recsys.experimental.service import (
    BLENDED,
    EFFORT_FIRST,
    RELEVANCE_FIRST,
    RankingPolicy,
    RecommendationService,
)
from recsys._seeds import stable_seed
from recsys.experimental.inventory import (
    DEFAULT_INVENTORY_ASSUMPTIONS,
    InventoryAssumptions,
    generate_inventory,
)
from recsys.experimental.pantry import DISABLED_PANTRY, PantryPolicy
from recsys.experimental.profiles import ARCHETYPES, SyntheticProfile, generate_population
from recsys.ready_food_pairs import ready_meal_options
from recsys.experimental.recipes import RECIPES
from recsys.regimes import REGIMES, Regime
from recsys.true_pantry import true_pantry
from recsys.response_models import (
    CONVERTING_ACTIONS,
    DEFAULT_RESPONDERS,
    ENGAGED_ACTIONS,
    INDEPENDENT_RESPONDER_NAMES,
    ResponseContext,
    ResponseModel,
    UserAction,
    extract_features,
)

DEFAULT_USERS_PER_REGIME = 40
DEFAULT_SEED = 20260905
TOP_K = 3

#: What a robustness claim is made on. See ``CellOutcome.cook_conversion_rate``
#: for why substitutions are excluded.
PRIMARY_METRIC = "cook_conversion_rate"


class RandomEngine:
    """Negative control: ranks by coin flip, ignoring the request entirely.

    Present so a run can demonstrate the bench has discriminating power. If a
    challenger cannot beat this, the metric is not measuring ranking quality.
    """

    def __init__(self, seed: int = 0) -> None:
        self._seed = seed

    def rank(self, request: RecommendationRequest) -> list[ModelRecommendation]:
        rng = random.Random(stable_seed(self._seed, request.current_receipt.receipt_id))
        ranked = [
            ModelRecommendation(
                recipe_id=recipe.recipe_id,
                mode=RecommendationMode.EXPLORE,
                score=round(rng.random(), 4),
                reason_codes=["personalized_discovery"],
            )
            for recipe in request.recipe_catalog
            if recipe.verified
        ]
        return sorted(ranked, key=lambda item: (-item.score, item.recipe_id))


@dataclass(frozen=True)
class Arm:
    """One end-to-end configuration under test.

    An arm is a *ranker plus a ranking policy*, not just a model. The policy
    belongs here because measuring it revealed it matters more than the model
    does: with the shipped ``effort_first`` policy the engine's score is only a
    tiebreaker, so swapping the model changes almost nothing.
    """

    name: str
    engine: RecommendationEngine
    ranking_policy: RankingPolicy = EFFORT_FIRST
    #: Whether the arm credits the shopper with stock inferred from history.
    #: Off by default, like the shipped service: turning it on is a product
    #: decision that has to earn its place here first.
    pantry_policy: PantryPolicy = DISABLED_PANTRY
    #: A control arm is reported but excluded from robustness claims.
    is_control: bool = False


@dataclass(frozen=True)
class CellOutcome:
    """One (arm, world, simulator) cell."""

    arm: str
    regime: str
    responder: str
    n_users: int
    n_cards: int
    counts: dict[str, int]
    #: Cards the user committed to and could not finish, because the card
    #: claimed an ingredient was already at home and it was not. Counted
    #: separately from ``counts`` because the *decision* was still BUY — the
    #: world refused afterwards.
    failed_cooks: int = 0

    def action_rate(self, action: UserAction) -> float:
        return self.counts.get(action.value, 0) / self.n_cards if self.n_cards else 0.0

    @property
    def cook_conversion_rate(self) -> float:
        """Cards the user actually cooked from. The primary metric.

        Failed cooks are subtracted. Without that, inferring pantry stock is a
        free win: it shrinks ``missing_count``, every simulator buys more, and
        the *optimistic* policy scores best of all. A metric where assuming
        more always wins measures the assumption, not the product.

        Deliberately excludes ``SUBSTITUTE``. A substitution happens when the
        ready meal beats the shopping basket, which is most likely exactly when
        the recipe was a *bad* suggestion — an early version of this bench used
        BUY+SUBSTITUTE and duly ranked a random ranker first, because random
        recommendations drove people to the ready-meal shelf.
        """
        if not self.n_cards:
            return 0.0
        successful = self.counts.get(UserAction.BUY.value, 0) - self.failed_cooks
        return max(successful, 0) / self.n_cards

    @property
    def failed_cook_rate(self) -> float:
        """Share of cards that promised a dinner and did not deliver one."""
        return self.failed_cooks / self.n_cards if self.n_cards else 0.0

    @property
    def substitute_rate(self) -> float:
        if not self.n_cards:
            return 0.0
        return self.counts.get(UserAction.SUBSTITUTE.value, 0) / self.n_cards

    @property
    def retail_conversion_rate(self) -> float:
        """Any sale, cooked or ready-made.

        Meaningful to the retailer, useless for judging recipe ranking — see
        ``cook_conversion_rate``. Reported, never used as the primary.
        """
        if not self.n_cards:
            return 0.0
        return sum(self.counts.get(a.value, 0) for a in CONVERTING_ACTIONS) / self.n_cards

    @property
    def engagement_rate(self) -> float:
        if not self.n_cards:
            return 0.0
        return sum(self.counts.get(a.value, 0) for a in ENGAGED_ACTIONS) / self.n_cards

    @property
    def cards_per_user(self) -> float:
        return self.n_cards / self.n_users if self.n_users else 0.0

    @property
    def cooks_per_user(self) -> float:
        """Cooked dinners per user, not per card.

        The per-card rates are the right way to compare arms *inside* one
        setting, because every arm there sees the same inventory and the same
        number of cards. They are the wrong way to compare *across* supply
        settings: scarcer shelves produce fewer cards, and the few that survive
        are the easy ones, so the per-card rate goes up while people cook less.

        Measured: at ``no_product_at_all`` 0.08 the bench shows 2.42 cards per
        user at 0.084 conversion (0.203 dinners); at 0.35 it shows 1.42 cards at
        0.111 (0.158 dinners). The rate improved, the outcome got worse. This
        metric is the one that survives that comparison.
        """
        successful = self.counts.get(UserAction.BUY.value, 0) - self.failed_cooks
        return max(successful, 0) / self.n_users if self.n_users else 0.0


@dataclass(frozen=True)
class CellDelta:
    regime: str
    responder: str
    baseline_value: float
    challenger_value: float

    @property
    def delta(self) -> float:
        return self.challenger_value - self.baseline_value

    @property
    def challenger_wins(self) -> bool:
        return self.delta > 0


@dataclass
class Comparison:
    """Challenger vs baseline over every world and simulator."""

    baseline: str
    challenger: str
    metric: str
    deltas: tuple[CellDelta, ...]

    def _subset(self, responders: frozenset[str] | None) -> tuple[CellDelta, ...]:
        if responders is None:
            return self.deltas
        return tuple(d for d in self.deltas if d.responder in responders)

    def win_rate(self, responders: frozenset[str] | None = None) -> float:
        subset = self._subset(responders)
        if not subset:
            return 0.0
        return sum(1 for d in subset if d.challenger_wins) / len(subset)

    @property
    def independent_win_rate(self) -> float:
        """Win rate excluding the self-referential oracle."""
        return self.win_rate(INDEPENDENT_RESPONDER_NAMES)

    def win_rate_by_responder(self) -> dict[str, float]:
        names = sorted({d.responder for d in self.deltas})
        return {name: self.win_rate(frozenset({name})) for name in names}

    @property
    def is_unanimous_across_responders(self) -> bool:
        """Does the challenger win a majority under *every* independent simulator?

        The property a robustness claim actually needs: winning on average can
        be one enthusiastic simulator outvoting two sceptical ones.
        """
        by_responder = self.win_rate_by_responder()
        independent = [
            rate
            for name, rate in by_responder.items()
            if name in INDEPENDENT_RESPONDER_NAMES
        ]
        return bool(independent) and all(rate > 0.5 for rate in independent)

    def delta_quantiles(self) -> dict[str, float]:
        values = sorted(d.delta for d in self._subset(INDEPENDENT_RESPONDER_NAMES))
        if not values:
            return {}
        return {
            "p10": values[int(len(values) * 0.10)],
            "median": statistics.median(values),
            "p90": values[min(int(len(values) * 0.90), len(values) - 1)],
            "worst": values[0],
            "best": values[-1],
        }

    def losing_cells(self) -> tuple[CellDelta, ...]:
        return tuple(
            d
            for d in self._subset(INDEPENDENT_RESPONDER_NAMES)
            if not d.challenger_wins
        )


@dataclass
class BenchmarkResult:
    cells: tuple[CellOutcome, ...]
    arms: tuple[Arm, ...]
    n_regimes: int
    users_per_regime: int
    seed: int
    inventory_assumptions: InventoryAssumptions = DEFAULT_INVENTORY_ASSUMPTIONS
    responder_names: tuple[str, ...] = field(default_factory=tuple)

    def cell(self, arm: str, regime: str, responder: str) -> CellOutcome | None:
        for cell in self.cells:
            if (
                cell.arm == arm
                and cell.regime == regime
                and cell.responder == responder
            ):
                return cell
        return None

    def compare(
        self, baseline: str, challenger: str, metric: str = PRIMARY_METRIC
    ) -> Comparison:
        deltas: list[CellDelta] = []
        for cell in self.cells:
            if cell.arm != challenger:
                continue
            other = self.cell(baseline, cell.regime, cell.responder)
            if other is None:
                continue
            deltas.append(
                CellDelta(
                    regime=cell.regime,
                    responder=cell.responder,
                    baseline_value=getattr(other, metric),
                    challenger_value=getattr(cell, metric),
                )
            )
        return Comparison(
            baseline=baseline,
            challenger=challenger,
            metric=metric,
            deltas=tuple(deltas),
        )

    def arm_means(
        self, metric: str = PRIMARY_METRIC, *, independent_only: bool = True
    ) -> dict[str, float]:
        """Mean metric per arm.

        Averages over the independent simulators only by default. Including
        ``oracle_selfref`` would let a change to the oracle move every arm's
        headline number, which happened once already: repairing the relevance
        label shifted even the random control, because a quarter of its cells
        were judged by the oracle.
        """
        by_arm: dict[str, list[float]] = {}
        for cell in self.cells:
            if independent_only and cell.responder not in INDEPENDENT_RESPONDER_NAMES:
                continue
            by_arm.setdefault(cell.arm, []).append(getattr(cell, metric))
        return {arm: statistics.mean(values) for arm, values in by_arm.items()}

    def control_arms(self) -> tuple[str, ...]:
        return tuple(arm.name for arm in self.arms if arm.is_control)

    def candidate_arms(self) -> tuple[str, ...]:
        return tuple(arm.name for arm in self.arms if not arm.is_control)

    def discrimination_check(
        self, metric: str = PRIMARY_METRIC
    ) -> dict[str, float]:
        """Best win rate any candidate arm achieves against each control.

        Establishes whether the bench can tell good ranking from noise at all.
        This is a property of the *bench*, so it is measured over the strongest
        candidate — asking whether one particular arm beats a control conflates
        "the bench is blind" with "this arm is no better than noise", and those
        are opposite conclusions.
        """
        out: dict[str, float] = {}
        for control in self.control_arms():
            out[control] = max(
                (
                    self.compare(control, candidate, metric).independent_win_rate
                    for candidate in self.candidate_arms()
                ),
                default=0.0,
            )
        return out

    @property
    def bench_discriminates(self) -> bool:
        checks = self.discrimination_check()
        return bool(checks) and any(rate > 0.6 for rate in checks.values())


def _build_request(
    profile: SyntheticProfile,
    recipes: list[Recipe],
    inventory,
    meals,
) -> RecommendationRequest:
    return RecommendationRequest(
        user=profile.user,
        current_receipt=profile.current_receipt,
        purchase_history=profile.purchase_history,
        recipe_catalog=recipes,
        inventory_snapshot=inventory,
        ready_meal_options=meals,
        now=profile.now,
        limit=TOP_K,
    )


def run_benchmark(
    arms: tuple[Arm, ...],
    *,
    regimes: tuple[Regime, ...] = REGIMES,
    responders: tuple[ResponseModel, ...] = DEFAULT_RESPONDERS,
    users_per_regime: int = DEFAULT_USERS_PER_REGIME,
    seed: int = DEFAULT_SEED,
    recipes: list[Recipe] | None = None,
    inventory_assumptions: InventoryAssumptions = DEFAULT_INVENTORY_ASSUMPTIONS,
    world_consumption_multiplier: float = 1.0,
) -> BenchmarkResult:
    """Run every arm through every world, judged by every simulator.

    Deterministic given ``(arms, regimes, responders, users_per_regime, seed)``.
    """
    recipe_catalog = list(recipes if recipes is not None else RECIPES)
    recipe_lookup = {r.recipe_id: r for r in recipe_catalog}
    meals = ready_meal_options(recipe_lookup)
    service_by_arm = {
        arm.name: RecommendationService(
            engine=arm.engine,
            safety_policy=SafetyPolicy(),
            ranking_policy=arm.ranking_policy,
            pantry_policy=arm.pantry_policy,
        )
        for arm in arms
    }

    counters: dict[tuple[str, str, str], Counter[str]] = {}
    card_totals: dict[tuple[str, str, str], int] = {}
    failures: dict[tuple[str, str, str], int] = {}

    for regime_index, regime in enumerate(regimes):
        profiles = generate_population(
            users_per_regime,
            seed=seed + regime_index,
            archetypes=regime.archetypes(),
        )
        regime_archetypes = regime.archetypes()

        # One inventory snapshot per (regime, user), shared by every arm: arms
        # must differ only in ranking, never in what was on the shelf.
        inventory_rng = random.Random(seed + 100_000 + regime_index)
        inventories = [
            generate_inventory(
                inventory_rng,
                now=profile.now,
                home_store_id=profile.current_receipt.store_id,
                user_radius_km=profile.user.radius_km,
                assumptions=inventory_assumptions,
            )
            for profile in profiles
        ]

        # The world's own answer about every kitchen, computed once and shared
        # by all arms so a claim can be checked rather than trusted.
        truths = [
            true_pantry(
                _build_request(p, recipe_catalog, [], []),
                consumption_multiplier=world_consumption_multiplier,
            )
            for p in profiles
        ]

        for arm in arms:
            service = service_by_arm[arm.name]
            for user_index, (profile, inventory, truth) in enumerate(
                zip(profiles, inventories, truths, strict=True)
            ):
                request = _build_request(profile, recipe_catalog, inventory, meals)
                response = service.recommend(request)
                for card_index, card in enumerate(response.recommendations):
                    recipe = recipe_lookup[card.recipe_id]
                    # Ingredients the card said were already at home, that the
                    # world says are not. An arm without pantry inference never
                    # makes such a claim and so can never fail this way.
                    false_claims = [
                        ingredient.ingredient_id
                        for ingredient in card.ingredients
                        if ingredient.source == IngredientSource.PANTRY_LIKELY
                        and not truth.has(ingredient.ingredient_id)
                    ]
                    features = extract_features(
                        card,
                        recipe,
                        is_saved=card.recipe_id in profile.user.saved_recipe_ids,
                    )
                    for responder in responders:
                        # Seeded per card, not per run: a stochastic simulator
                        # must see the same coin flips for every arm, so a win
                        # cannot come from luckier randomness.
                        rng = random.Random(
                            stable_seed(
                                seed,
                                regime_index,
                                user_index,
                                card_index,
                                responder.name,
                            )
                        )
                        action = responder.respond(
                            ResponseContext(
                                profile=profile,
                                params=regime_archetypes[profile.archetype],
                                recipe=recipe,
                                features=features,
                                request=request,
                                rng=rng,
                            )
                        )
                        key = (arm.name, regime.name, responder.name)
                        counters.setdefault(key, Counter())[action.value] += 1
                        card_totals[key] = card_totals.get(key, 0) + 1
                        if action == UserAction.BUY and false_claims:
                            failures[key] = failures.get(key, 0) + 1

    cells = tuple(
        CellOutcome(
            arm=arm_name,
            regime=regime_name,
            responder=responder_name,
            n_users=users_per_regime,
            n_cards=card_totals[(arm_name, regime_name, responder_name)],
            counts=dict(counter),
            failed_cooks=failures.get((arm_name, regime_name, responder_name), 0),
        )
        for (arm_name, regime_name, responder_name), counter in sorted(counters.items())
    )
    return BenchmarkResult(
        cells=cells,
        arms=arms,
        n_regimes=len(regimes),
        users_per_regime=users_per_regime,
        seed=seed,
        inventory_assumptions=inventory_assumptions,
        responder_names=tuple(r.name for r in responders),
    )


def pantry_arms() -> tuple[Arm, ...]:
    """Same rankers, with and without inferred pantry stock.

    The comparison the product decision needs: crediting the shopper with what
    they probably already have shrinks the shopping list (measured 3.43 -> 2.60
    items per card), but a wrong belief strands them mid-recipe. Whether the
    trade is worth taking is what these arms measure.
    """
    from recsys.experimental.model import MLRecommendationEngine

    ml = MLRecommendationEngine()
    heuristic = DeterministicMockEngine()
    return (
        Arm(name="heuristic/effort", engine=heuristic, ranking_policy=EFFORT_FIRST),
        Arm(
            name="heuristic/effort+pantry",
            engine=heuristic,
            ranking_policy=EFFORT_FIRST,
            pantry_policy=PantryPolicy.confident(),
        ),
        Arm(
            name="heuristic/effort+pantry_opt",
            engine=heuristic,
            ranking_policy=EFFORT_FIRST,
            pantry_policy=PantryPolicy.optimistic(),
        ),
        Arm(name="ml/effort", engine=ml, ranking_policy=EFFORT_FIRST),
        Arm(
            name="ml/effort+pantry",
            engine=ml,
            ranking_policy=EFFORT_FIRST,
            pantry_policy=PantryPolicy.confident(),
        ),
        Arm(
            name="random/effort",
            engine=RandomEngine(),
            ranking_policy=EFFORT_FIRST,
            is_control=True,
        ),
        Arm(
            name="random/relevance",
            engine=RandomEngine(),
            ranking_policy=RELEVANCE_FIRST,
            is_control=True,
        ),
    )


def default_arms() -> tuple[Arm, ...]:
    """The grid that separates "which model" from "which ranking policy".

    Both factors are crossed on purpose: without the policy axis a run only
    shows that the models tie, without showing *why* they tie.
    """
    from recsys.experimental.model import MLRecommendationEngine

    ml = MLRecommendationEngine()
    # Effort features zeroed: the policy is supposed to supply the effort term,
    # so this arm tests whether accounting for it once beats accounting twice.
    ml_pref = MLRecommendationEngine(include_effort_features=False)
    return (
        # Shipped configuration.
        Arm(name="heuristic/effort", engine=DeterministicMockEngine(), ranking_policy=EFFORT_FIRST),
        Arm(name="ml/effort", engine=ml, ranking_policy=EFFORT_FIRST),
        # Same models, policy that actually lets the score through.
        Arm(name="ml/blended", engine=ml, ranking_policy=BLENDED),
        Arm(name="ml/relevance", engine=ml, ranking_policy=RELEVANCE_FIRST),
        Arm(name="heuristic/blended", engine=DeterministicMockEngine(), ranking_policy=BLENDED),
        Arm(name="ml_pref/blended", engine=ml_pref, ranking_policy=BLENDED),
        Arm(name="ml_pref/relevance", engine=ml_pref, ranking_policy=RELEVANCE_FIRST),
        # Controls: random ranking under both the shipped and the permissive
        # policy. The second is the one a working bench must clearly reject.
        Arm(name="random/effort", engine=RandomEngine(), ranking_policy=EFFORT_FIRST, is_control=True),
        Arm(name="random/relevance", engine=RandomEngine(), ranking_policy=RELEVANCE_FIRST, is_control=True),
    )


def verdict(result: BenchmarkResult, comparison: Comparison) -> str:
    """A claim the bench can actually support, and the caveat it comes with."""
    lines: list[str] = []
    win = comparison.independent_win_rate
    by_responder = comparison.win_rate_by_responder()
    quantiles = comparison.delta_quantiles()

    lines.append(
        f"{comparison.challenger} vs {comparison.baseline} on {comparison.metric}: "
        f"wins {win:.0%} of (world x simulator) cells, excluding the "
        f"self-referential oracle."
    )
    lines.append(
        "per simulator: "
        + ", ".join(f"{name} {rate:.0%}" for name, rate in sorted(by_responder.items()))
    )
    if quantiles:
        lines.append(
            f"effect spread across cells: p10 {quantiles['p10']:+.3f}, "
            f"median {quantiles['median']:+.3f}, p90 {quantiles['p90']:+.3f} "
            f"(worst {quantiles['worst']:+.3f}, best {quantiles['best']:+.3f})"
        )
    lines.append(
        "unanimous across independent simulators: "
        + ("yes" if comparison.is_unanimous_across_responders else "NO")
    )

    checks = result.discrimination_check(comparison.metric)
    lines.append(
        "bench discriminating power (best candidate vs each control): "
        + ", ".join(f"{control} {rate:.0%}" for control, rate in sorted(checks.items()))
    )
    if not result.bench_discriminates:
        lines.append(
            "WARNING: no candidate arm clearly beats any control. The metric is "
            "not measuring ranking quality — treat every number above as void."
        )
    for control in result.control_arms():
        control_cmp = result.compare(control, comparison.challenger, comparison.metric)
        rate = control_cmp.independent_win_rate
        if rate <= 0.6 and result.bench_discriminates:
            lines.append(
                f"FINDING: {comparison.challenger} beats control '{control}' in only "
                f"{rate:.0%} of cells, while the bench does discriminate elsewhere. "
                f"That is a result about this arm, not about the bench: under this "
                f"configuration the ranker is no better than noise."
            )

    lines.append(
        "This is a robustness statement over assumed worlds, not a forecast. "
        "It does not estimate uplift on real customers, and the cell counts are "
        "not a p-value: the worlds were chosen by us, not sampled from reality."
    )
    return "\n".join(lines)


def main() -> int:
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    arms = default_arms()
    result = run_benchmark(arms)
    print(
        f"arms={[a.name for a in arms]} regimes={result.n_regimes} "
        f"users/regime={result.users_per_regime} "
        f"simulators={list(result.responder_names)} "
        f"cells={len(result.cells)}"
    )
    print()
    print(f"mean {PRIMARY_METRIC} by arm (substitutions excluded):")
    for arm, value in sorted(result.arm_means().items(), key=lambda kv: -kv[1]):
        subst = statistics.mean(
            c.substitute_rate for c in result.cells if c.arm == arm
        )
        print(f"  {arm:20} cook={value:.3f}  substitute={subst:.3f}")
    print()
    for baseline, challenger in (
        ("heuristic/effort", "ml/effort"),
        ("ml/effort", "ml/blended"),
        ("ml/effort", "ml/relevance"),
    ):
        print(f"--- {challenger} vs {baseline} ---")
        print(verdict(result, result.compare(baseline, challenger)))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
