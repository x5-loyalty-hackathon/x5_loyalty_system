"""1-10k user funnel simulation.

This operates at a different granularity than ``recsys.generate_examples``
and ``recsys.evaluation``: those two run the *real* ``RecommendationService``
(model + safety + fulfillment resolution) against a handful to a few hundred
full synthetic profiles, because that's what "5-10 profiles with real
recommendations" and "hit rate on 30-50 profiles" need. Doing that for 10,000
users would mean materializing full ``InventoryProduct``/``Recipe`` graphs
per user for no analytical benefit.

The 1-10k simulation is instead the aggregate funnel/economics simulation the
product docs actually describe (``docs/research/persona_vxofi/rescue-domovoi-concept.md
§13/§18``: impression -> open -> save -> list -> purchase -> repeat, purchase
days, contribution) — a Monte Carlo over archetype-level rates, which is both
the right granularity for "does this remain internally consistent at
population scale" and the only way 10k users runs in seconds rather than
minutes.

Base case is deliberately zero-uplift (``rescue-domovoi-concept.md §18``:
"Base-case не предполагает uplift: Δpurchase_days = 0"): the recommender
never manufactures an extra shopping trip (`route A`) unless a sensitivity
scenario explicitly turns that dial up. This file does not prove causal
uplift; it checks that the funnel and economics stay internally consistent
under stated, labeled assumptions — see
``docs/research/recsys/economics-and-simulation.md`` for what this can and
cannot claim.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from recsys.profiles import ARCHETYPES, ArchetypeParams

HORIZON_DAYS = 60

# All rates below are illustrative demo constants (see
# docs/research/recsys/economics-and-simulation.md), not measured X5 data.
BASE_OPEN_RATE = 0.55
BASE_SAVE_RATE_GIVEN_OPEN = 0.40
BASE_CONVERT_RATE_GIVEN_SAVE = 0.55
BASE_MARKDOWN_SHARE_OF_CONVERSIONS = 0.45
BASE_ROUTE_A_PROBABILITY = 0.0  # base case: no induced extra purchase day


@dataclass(frozen=True)
class ScenarioParams:
    name: str
    relevance_multiplier: float  # scales open/save rates
    markdown_availability_multiplier: float  # scales markdown share and convert rate
    route_a_probability: float  # P(a conversion becomes a genuinely new purchase day)
    fallback_full_price_rate: float  # share of "would-be-markdown" conversions that fall back to full price
    cannibalization_rate: float  # share of route-B contribution assumed to displace organic full-price margin


SCENARIOS: dict[str, ScenarioParams] = {
    "pessimistic": ScenarioParams(
        name="pessimistic",
        relevance_multiplier=0.7,
        markdown_availability_multiplier=0.6,
        route_a_probability=0.0,
        fallback_full_price_rate=0.55,
        cannibalization_rate=0.5,
    ),
    "base": ScenarioParams(
        name="base",
        relevance_multiplier=1.0,
        markdown_availability_multiplier=1.0,
        route_a_probability=BASE_ROUTE_A_PROBABILITY,
        fallback_full_price_rate=0.35,
        cannibalization_rate=0.3,
    ),
    "optimistic": ScenarioParams(
        name="optimistic",
        relevance_multiplier=1.25,
        markdown_availability_multiplier=1.3,
        route_a_probability=0.06,
        fallback_full_price_rate=0.2,
        cannibalization_rate=0.15,
    ),
}


@dataclass
class UserFunnelResult:
    archetype: str
    impressions: int = 0
    opens: int = 0
    saves: int = 0
    conversions: int = 0
    route_a_conversions: int = 0
    route_b_conversions: int = 0
    markdown_conversions: int = 0
    full_price_conversions: int = 0
    baseline_purchase_days: int = 0
    extra_purchase_days: int = 0

    @property
    def total_purchase_days(self) -> int:
        return self.baseline_purchase_days + self.extra_purchase_days


@dataclass
class SimulationResult:
    scenario: str
    n_users: int
    horizon_days: int
    users: list[UserFunnelResult] = field(default_factory=list)

    def funnel_totals(self) -> dict[str, int]:
        totals = {"impressions": 0, "opens": 0, "saves": 0, "conversions": 0}
        for u in self.users:
            totals["impressions"] += u.impressions
            totals["opens"] += u.opens
            totals["saves"] += u.saves
            totals["conversions"] += u.conversions
        return totals

    def mean_purchase_days(self) -> float:
        return sum(u.total_purchase_days for u in self.users) / len(self.users)

    def mean_extra_purchase_days(self) -> float:
        return sum(u.extra_purchase_days for u in self.users) / len(self.users)

    def p_days_at_least(self, n: int) -> float:
        return sum(1 for u in self.users if u.total_purchase_days >= n) / len(self.users)

    def markdown_conversion_share(self) -> float:
        total_conv = sum(u.conversions for u in self.users)
        if total_conv == 0:
            return 0.0
        return sum(u.markdown_conversions for u in self.users) / total_conv


def _sample_impressions(rng: random.Random, params: ArchetypeParams, horizon_days: int) -> int:
    mean = horizon_days / params.cadence_days_mean
    std = math.sqrt(max(mean, 1e-6))
    return max(0, round(rng.gauss(mean, std)))


def simulate_user(
    rng: random.Random,
    params: ArchetypeParams,
    scenario: ScenarioParams,
    *,
    horizon_days: int = HORIZON_DAYS,
) -> UserFunnelResult:
    impressions = _sample_impressions(rng, params, horizon_days)
    result = UserFunnelResult(archetype=params.name, impressions=impressions, baseline_purchase_days=impressions)

    open_rate = min(1.0, BASE_OPEN_RATE * scenario.relevance_multiplier)
    # Archetypes with higher discovery acceptance engage a bit more with a
    # daily recipe feed; this is an illustrative tilt, not a measured effect.
    open_rate = min(1.0, open_rate * (0.85 + 0.3 * params.discovery_acceptance))
    save_rate = min(1.0, BASE_SAVE_RATE_GIVEN_OPEN * scenario.relevance_multiplier)
    convert_rate = min(1.0, BASE_CONVERT_RATE_GIVEN_SAVE * scenario.markdown_availability_multiplier)
    markdown_share = min(
        1.0,
        BASE_MARKDOWN_SHARE_OF_CONVERSIONS
        * scenario.markdown_availability_multiplier
        * (0.6 + 0.8 * params.markdown_affinity),
    )
    markdown_share *= 1.0 - scenario.fallback_full_price_rate

    for _ in range(impressions):
        if rng.random() >= open_rate:
            continue
        result.opens += 1
        if rng.random() >= save_rate:
            continue
        result.saves += 1
        if rng.random() >= convert_rate:
            continue
        result.conversions += 1

        if rng.random() < scenario.route_a_probability:
            result.route_a_conversions += 1
            result.extra_purchase_days += 1
        else:
            result.route_b_conversions += 1

        if rng.random() < markdown_share:
            result.markdown_conversions += 1
        else:
            result.full_price_conversions += 1

    return result


def sample_archetype(
    rng: random.Random, archetypes: dict[str, ArchetypeParams] | None = None
) -> ArchetypeParams:
    table = archetypes if archetypes is not None else ARCHETYPES
    names = list(table)
    weights = [table[n].population_share for n in names]
    return table[rng.choices(names, weights=weights, k=1)[0]]


def run_simulation(
    n_users: int,
    *,
    scenario: str = "base",
    seed: int = 2026,
    horizon_days: int = HORIZON_DAYS,
) -> SimulationResult:
    """Deterministic given (n_users, scenario, seed, horizon_days)."""
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario {scenario!r}, expected one of {list(SCENARIOS)}")
    rng = random.Random(seed)
    params = SCENARIOS[scenario]
    users = [simulate_user(rng, sample_archetype(rng), params, horizon_days=horizon_days) for _ in range(n_users)]
    return SimulationResult(scenario=scenario, n_users=n_users, horizon_days=horizon_days, users=users)


if __name__ == "__main__":
    for n in (1_000, 10_000):
        print(f"=== N={n} ===")
        for scenario_name in SCENARIOS:
            result = run_simulation(n, scenario=scenario_name)
            totals = result.funnel_totals()
            print(
                f"[{scenario_name:>11}] impressions={totals['impressions']:>7} "
                f"opens={totals['opens']:>6} saves={totals['saves']:>6} "
                f"conversions={totals['conversions']:>6} "
                f"mean_purchase_days={result.mean_purchase_days():.2f} "
                f"mean_extra_days={result.mean_extra_purchase_days():.3f} "
                f"P(days>=10)={result.p_days_at_least(10):.0%} "
                f"markdown_share={result.markdown_conversion_share():.0%}"
            )
        print()
