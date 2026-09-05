"""The logging schema, and the claim that makes it worth having.

The load-bearing test here is
``test_a_deterministic_log_cannot_evaluate_anything_else``: it demonstrates,
rather than asserts, that logging without exploration produces data that can
only re-measure the policy that produced it. Everything else in this file
supports that one.
"""

from __future__ import annotations

import random
from datetime import timedelta

from app.impression_log import (
    ExplorationPolicy,
    ImpressionEvent,
    OutcomeEvent,
    ScoredCandidate,
    build_impression_event,
    estimate_policy_value,
    log_completeness,
)
from app.recommender import DeterministicMockEngine
from app.safety import SafetyPolicy
from app.service import EFFORT_FIRST, RecommendationService
from app.contracts import RecommendationRequest
from recsys.catalog_freeze import baseline_catalog
from recsys.panels import PanelSpec, build_panel
from recsys.profiles import DEFAULT_NOW

RECIPES = [f"r{i}" for i in range(10)]


def _impression(
    request_id: str,
    *,
    policy: ExplorationPolicy,
    ranked: list[str] = RECIPES,
    rng: random.Random,
) -> ImpressionEvent:
    shown, explored = policy.choose(ranked, rng)
    propensities = policy.propensities(ranked, n_eligible=len(ranked))
    position_of = {r: i for i, r in enumerate(shown)}
    return ImpressionEvent(
        request_id=request_id,
        user_ref=f"u_{request_id}",
        served_at=DEFAULT_NOW,
        model_version="ml-v1",
        ranking_policy="effort_first",
        is_exploration=explored,
        exploration_rate=policy.rate,
        candidates=[
            ScoredCandidate(
                recipe_id=r,
                model_score=1.0 - 0.05 * i,
                position=position_of.get(r),
                propensity=max(propensities[r], 1e-6),
                missing_count=i % 4,
                features={"coverage": 0.1 * i},
            )
            for i, r in enumerate(ranked)
        ],
        shown_recipe_ids=shown,
    )


# --- propensities ----------------------------------------------------------


def test_every_eligible_recipe_keeps_a_nonzero_chance_of_being_shown() -> None:
    """The whole point: without this, the denominator of every off-policy
    estimate is zero for anything the logging policy disliked."""
    policy = ExplorationPolicy(rate=0.05, slate_size=3)
    propensities = policy.propensities(RECIPES, n_eligible=len(RECIPES))
    assert all(p > 0 for p in propensities.values())
    # Top-of-slate still carries almost all its mass from the greedy branch.
    assert propensities["r0"] > 0.9
    assert 0.0 < propensities["r9"] < 0.05


def test_switching_exploration_off_makes_unshown_recipes_unreachable() -> None:
    propensities = ExplorationPolicy(rate=0.0).propensities(
        RECIPES, n_eligible=len(RECIPES)
    )
    assert propensities["r0"] == 1.0
    assert propensities["r9"] == 0.0


def test_exploration_actually_reorders_sometimes() -> None:
    policy = ExplorationPolicy(rate=0.5, slate_size=3)
    rng = random.Random(7)
    slates = {tuple(policy.choose(RECIPES, rng)[0]) for _ in range(50)}
    assert len(slates) > 1


# --- the load-bearing claim ------------------------------------------------


def test_a_deterministic_log_cannot_evaluate_anything_else() -> None:
    """Log without exploration, then ask what a different policy would score.

    The answer comes back empty — not wrong, *unanswerable* — because the
    challenger's picks were never shown and carry no propensity mass. This is
    the failure that arrives three months after launch and cannot be repaired,
    since the data to repair it was never written.
    """
    rng = random.Random(1)
    policy = ExplorationPolicy(rate=0.0, slate_size=3)
    impressions = [_impression(f"q{i}", policy=policy, rng=rng) for i in range(200)]
    outcomes = [
        OutcomeEvent(
            request_id=i.request_id,
            recipe_id=i.shown_recipe_ids[0],
            occurred_at=DEFAULT_NOW + timedelta(days=1),
            action="cooked",
        )
        for i in impressions[:60]
    ]
    # A challenger that prefers the tail — exactly what the greedy logger never showed.
    challenger = {i.request_id: ["r7", "r8", "r9"] for i in impressions}

    estimate = estimate_policy_value(impressions, outcomes, challenger)
    assert estimate.ips == 0.0
    assert estimate.snips == 0.0
    assert any("exploration" in w for w in estimate.warnings)


def test_a_randomised_log_can_evaluate_a_policy_that_never_ran() -> None:
    """Same setup, exploration on: the challenger becomes measurable."""
    rng = random.Random(1)
    policy = ExplorationPolicy(rate=0.3, slate_size=3)
    impressions = [_impression(f"q{i}", policy=policy, rng=rng) for i in range(400)]

    # World where only r9 ever leads to cooking. A greedy logger would barely
    # see it; the randomised branch does.
    outcomes = [
        OutcomeEvent(
            request_id=i.request_id,
            recipe_id="r9",
            occurred_at=DEFAULT_NOW + timedelta(days=1),
            action="cooked",
        )
        for i in impressions
        if "r9" in i.shown_recipe_ids
    ]
    challenger = {i.request_id: ["r9", "r8", "r7"] for i in impressions}
    incumbent = {i.request_id: ["r0", "r1", "r2"] for i in impressions}

    good = estimate_policy_value(impressions, outcomes, challenger)
    bad = estimate_policy_value(impressions, outcomes, incumbent)
    assert good.snips > bad.snips
    assert good.n_matched == len(impressions)


def test_the_estimate_says_when_it_rests_on_a_handful_of_records() -> None:
    """A thin exploration branch makes the answer depend on a few impressions.

    The estimator has to say so. An off-policy number that looks like a mean but
    is carried by three records is how a team ships a model that was never
    really evaluated.
    """
    rng = random.Random(3)
    policy = ExplorationPolicy(rate=0.02, slate_size=3)
    impressions = [_impression(f"q{i}", policy=policy, rng=rng) for i in range(300)]
    outcomes = [
        OutcomeEvent(
            request_id=i.request_id,
            recipe_id="r9",
            occurred_at=DEFAULT_NOW,
            action="cooked",
        )
        for i in impressions
        if "r9" in i.shown_recipe_ids
    ]
    estimate = estimate_policy_value(
        impressions, outcomes, {i.request_id: ["r9"] for i in impressions}
    )
    # r9 is only ever shown by the 2% random branch, so the surviving weight
    # sits on a tiny fraction of the records.
    assert 0 < estimate.effective_sample_size < 0.1 * len(impressions)
    assert any("effective sample size" in w or "weight" in w for w in estimate.warnings)


def test_weights_are_clipped_so_one_rare_record_cannot_own_the_answer() -> None:
    rng = random.Random(5)
    policy = ExplorationPolicy(rate=0.01, slate_size=3)
    impressions = [_impression(f"q{i}", policy=policy, rng=rng) for i in range(100)]
    outcomes = [
        OutcomeEvent(
            request_id=i.request_id,
            recipe_id=r,
            occurred_at=DEFAULT_NOW,
            action="cooked",
        )
        for i in impressions
        for r in i.shown_recipe_ids
    ]
    challenger = {i.request_id: RECIPES[-3:] for i in impressions}
    tight = estimate_policy_value(impressions, outcomes, challenger, weight_clip=2.0)
    loose = estimate_policy_value(impressions, outcomes, challenger, weight_clip=1000.0)
    assert tight.ips <= loose.ips


# --- outcomes and completeness --------------------------------------------


def test_outcomes_join_later_by_request_id() -> None:
    """A cook happens days after the card. A schema that wants the outcome at
    serve time loses the join."""
    rng = random.Random(11)
    policy = ExplorationPolicy(rate=0.2)
    impressions = [_impression(f"q{i}", policy=policy, rng=rng) for i in range(50)]
    late = [
        OutcomeEvent(
            request_id=i.request_id,
            recipe_id=i.shown_recipe_ids[0],
            occurred_at=i.served_at + timedelta(days=6),
            action="cooked",
            value_rub=420.0,
        )
        for i in impressions
    ]
    estimate = estimate_policy_value(
        impressions, late, {i.request_id: i.shown_recipe_ids for i in impressions}
    )
    assert estimate.n_matched == 50
    assert estimate.snips > 0


def test_only_rewarded_actions_count() -> None:
    rng = random.Random(2)
    policy = ExplorationPolicy(rate=0.2)
    impressions = [_impression(f"q{i}", policy=policy, rng=rng) for i in range(30)]
    clicks = [
        OutcomeEvent(
            request_id=i.request_id,
            recipe_id=i.shown_recipe_ids[0],
            occurred_at=DEFAULT_NOW,
            action="click",
        )
        for i in impressions
    ]
    estimate = estimate_policy_value(
        impressions, clicks, {i.request_id: i.shown_recipe_ids for i in impressions}
    )
    assert estimate.snips == 0.0


def test_completeness_flags_a_log_that_cannot_support_off_policy_work() -> None:
    rng = random.Random(4)
    deterministic = [
        _impression(f"q{i}", policy=ExplorationPolicy(rate=0.0), rng=rng)
        for i in range(20)
    ]
    report = log_completeness(deterministic)
    assert report["exploration_share"] == 0.0
    assert report["deterministic_shown_records"] > 0

    randomised = [
        _impression(f"p{i}", policy=ExplorationPolicy(rate=0.3), rng=rng)
        for i in range(20)
    ]
    assert log_completeness(randomised)["exploration_share"] > 0.0
    assert log_completeness(randomised)["unshown_candidates_share"] == 1.0


def test_an_empty_slate_is_representable() -> None:
    """35% of users get nothing under scarcity. An absent row would erase them."""
    event = ImpressionEvent(
        request_id="q",
        user_ref="u",
        served_at=DEFAULT_NOW,
        model_version="ml-v1",
        ranking_policy="effort_first",
        exploration_rate=0.05,
        candidates=[
            ScoredCandidate(
                recipe_id="r0",
                model_score=0.4,
                propensity=0.05,
                missing_count=9,
                filtered_reason="no_safe_product:beef",
            )
        ],
        shown_recipe_ids=[],
    )
    assert event.is_empty_slate
    assert log_completeness([event])["empty_slate_share"] == 1.0


# --- against the real service ---------------------------------------------


def test_a_real_serve_produces_a_complete_record() -> None:
    """Wired to the actual service, not a mock: the emitter has to survive the
    real response shape, including its filter warnings."""
    panel = build_panel(PanelSpec(name="log_test_panel", n_users=6))
    catalog = baseline_catalog()
    engine = DeterministicMockEngine()
    service = RecommendationService(
        engine=engine, safety_policy=SafetyPolicy(), ranking_policy=EFFORT_FIRST
    )
    policy = ExplorationPolicy(rate=0.1)
    rng = random.Random(0)

    profile, inventory = panel.pairs()[0]
    request = RecommendationRequest(
        user=profile.user,
        current_receipt=profile.current_receipt,
        purchase_history=profile.purchase_history,
        recipe_catalog=catalog,
        inventory_snapshot=inventory,
        now=profile.now,
        limit=3,
    )
    ranked = engine.rank(request)
    response = service.recommend(request)
    shown, explored = policy.choose([r.recipe_id for r in ranked], rng)

    event = build_impression_event(
        request_id="req-1",
        user_ref="pseudo-1",
        served_at=profile.now,
        model_version="heuristic-v1",
        ranking_policy=EFFORT_FIRST.name,
        ranked=ranked,
        response=response,
        policy=policy,
        shown_recipe_ids=shown,
        is_exploration=explored,
        features_by_recipe={r.recipe_id: {"coverage": 0.5} for r in ranked},
    )

    assert len(event.candidates) == len(ranked)
    assert all(c.propensity > 0 for c in event.candidates)
    # Unshown candidates are kept — that is what makes a counterfactual possible.
    assert any(c.position is None for c in event.candidates)
    assert any(c.features for c in event.candidates)
    assert event.ranking_policy == "effort_first"
