"""Relevance evaluation: own-history vs. shuffled-history hit rate.

Implements the exact methodology ADR-001 and ``docs/technical-design.md §10``
specify: for each profile, rank recipes once against the profile's own
history and once against a randomly-paired other profile's history (with the
*same* triggering receipt), then judge both against the profile's *own* true
preferences. The target is hit-rate-own ≥70%; the own/shuffled gap is the
more important number, because it is the direct test of "does this model
actually use personalization, not just rank generically."

Honesty note (see ``docs/research/recsys/evaluation-and-metrics.md``): the
oracle below shares its rule structure with the synthetic training-label
generator in ``recsys.model`` (both are derived from the same archetype
definitions in ``recsys.profiles``), so the absolute hit-rate-own number is
partly self-referential — it mainly shows the model fits the rule it was
bootstrapped from. The own-vs-shuffled *gap* is not self-referential in the
same way: it tests whether swapping in the wrong history measurably hurts
oracle-judged relevance, which is the actual claim this PoC needs to
support. Neither number is evidence of real-user relevance.

Scope note added after the September 2026 bench run
---------------------------------------------------
This module calls ``engine.rank()`` **directly**, so it measures the ranker in
isolation. The product does not serve that ranking: ``app.service`` re-sorts
the assembled candidates through ``RankingPolicy``, and the shipped
``EFFORT_FIRST`` policy orders by ``missing_count`` with ``model_score`` as a
tiebreaker only. A model can therefore score well here and reach the user
barely distinguishable from a random ranker — which is what
``docs/benchmark-report.md`` measured (38% win rate against a random control
under the shipped policy, against 98% under a relevance-led one).

Two consequences worth keeping in view when reading any number below:

* ``hit_rate_own`` is an upper bound on what the pipeline delivers, not an
  estimate of it. End-to-end behaviour is ``recsys.benchmark``.
* ``oracle_relevant`` is close to a function of ``missing_count``: no recipe
  with six or more missing ingredients is ever judged relevant, because
  ``ArchetypeParams.max_missing_tolerance`` caps it. Held at fixed effort, the
  trained model separates relevant from irrelevant at AUC 0.53 — see
  ``recsys.diagnostics.stratified_signal``.
"""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass

from app.contracts import ModelRecommendation, Recipe, RecommendationMode, RecommendationRequest, UserProfile
from app.recommender import RecommendationEngine
from recsys.inventory import generate_inventory
from recsys.model import HIGH_COVERAGE, HIGH_HISTORY_AFFINITY, NOVELTY_THRESHOLD, compute_features
from recsys.profiles import ARCHETYPES, SyntheticProfile


def oracle_relevant(
    profile: SyntheticProfile,
    recipe: Recipe,
    request: RecommendationRequest,
) -> bool:
    """Rule-based synthetic relevance judgment, independent of the trained
    classifier's weights (though not of its label-generation rule — see
    module docstring). Not a substitute for human/real-user judgment."""
    params = ARCHETYPES[profile.archetype]
    features = compute_features(request, recipe)
    missing_count = int(features["_missing_count"])
    tolerance = params.max_missing_tolerance
    if features["markdown_supply_signal"] >= 0.5 and params.markdown_affinity >= 0.5:
        tolerance += 1
    if missing_count > tolerance:
        return False
    if (
        params.time_limit_minutes is not None
        and recipe.preparation_minutes is not None
        and recipe.preparation_minutes > params.time_limit_minutes
    ):
        return False
    if features["is_saved"] >= 1.0:
        return True
    if features["coverage"] >= HIGH_COVERAGE:
        return True
    if features["_combined_affinity"] < NOVELTY_THRESHOLD:
        return params.discovery_acceptance >= 0.5
    return features["_combined_affinity"] >= HIGH_HISTORY_AFFINITY


def _build_request(
    *,
    user: UserProfile,
    current_receipt,
    purchase_history,
    recipe_catalog: list[Recipe],
    inventory,
    now,
) -> RecommendationRequest:
    return RecommendationRequest(
        user=user,
        current_receipt=current_receipt,
        purchase_history=purchase_history,
        recipe_catalog=recipe_catalog,
        inventory_snapshot=inventory,
        now=now,
        limit=3,
    )


def _shuffled_user(own: UserProfile, partner: UserProfile) -> UserProfile:
    """Keep the profile's own account settings (radius, exclusions) but swap
    in a different profile's history-derived preference fields."""
    return UserProfile(
        user_id=own.user_id,
        radius_km=own.radius_km,
        excluded_categories=own.excluded_categories,
        excluded_ingredient_ids=own.excluded_ingredient_ids,
        saved_recipe_ids=partner.saved_recipe_ids,
        history_categories=partner.history_categories,
        preferred_brands=partner.preferred_brands,
    )


@dataclass
class EvalResult:
    n_profiles: int
    top_k: int
    hit_rate_own: float
    hit_rate_shuffled: float
    coverage: float
    mode_distribution: dict[str, int]
    unique_recipes_recommended: int
    total_recipes_available: int
    # Stratified on repeat/explore recommendations only (mode != current).
    # CURRENT-mode picks are *supposed* to depend on today's receipt, not
    # history, so blending them into the headline gap understates how much
    # personalization matters for the modes that actually carry it — see
    # docs/research/recsys/evaluation-and-metrics.md.
    history_dependent_n: int
    hit_rate_own_history_dependent: float | None
    hit_rate_shuffled_history_dependent: float | None

    @property
    def personalization_gap(self) -> float:
        return self.hit_rate_own - self.hit_rate_shuffled

    @property
    def history_dependent_gap(self) -> float | None:
        if self.hit_rate_own_history_dependent is None or self.hit_rate_shuffled_history_dependent is None:
            return None
        return self.hit_rate_own_history_dependent - self.hit_rate_shuffled_history_dependent

    def summary(self) -> str:
        hd_own = "n/a" if self.hit_rate_own_history_dependent is None else f"{self.hit_rate_own_history_dependent:.0%}"
        hd_shuf = "n/a" if self.hit_rate_shuffled_history_dependent is None else f"{self.hit_rate_shuffled_history_dependent:.0%}"
        hd_gap = "n/a" if self.history_dependent_gap is None else f"{self.history_dependent_gap:+.0%}"
        lines = [
            f"profiles: {self.n_profiles}, top_k: {self.top_k}",
            f"hit_rate_own (all modes): {self.hit_rate_own:.0%} (target >= 70%)",
            f"hit_rate_shuffled (all modes): {self.hit_rate_shuffled:.0%}",
            f"personalization_gap (all modes): {self.personalization_gap:+.0%}",
            f"  -- repeat/explore only (n={self.history_dependent_n}): "
            f"own {hd_own} / shuffled {hd_shuf} / gap {hd_gap}",
            f"coverage (>=1 recommendation): {self.coverage:.0%}",
            f"unique recipes recommended: {self.unique_recipes_recommended}/{self.total_recipes_available}",
            f"mode distribution: {self.mode_distribution}",
        ]
        return "\n".join(lines)


def run_evaluation(
    engine: RecommendationEngine,
    profiles: list[SyntheticProfile],
    recipe_catalog: list[Recipe],
    *,
    top_k: int = 3,
    seed: int = 123,
) -> EvalResult:
    rng = random.Random(seed)
    recipe_lookup = {recipe.recipe_id: recipe for recipe in recipe_catalog}

    partners = list(profiles)
    rng.shuffle(partners)
    for i in range(len(profiles)):
        if partners[i] is profiles[i] and len(profiles) > 1:
            j = (i + 1) % len(profiles)
            partners[i], partners[j] = partners[j], partners[i]

    own_hits = 0
    shuffled_hits = 0
    covered = 0
    mode_counter: Counter[str] = Counter()
    unique_recipes: set[str] = set()
    hd_own_hits = 0
    hd_shuffled_hits = 0
    hd_n = 0

    for profile, partner in zip(profiles, partners):
        inventory = generate_inventory(
            rng,
            now=profile.now,
            home_store_id=profile.current_receipt.store_id,
            user_radius_km=profile.user.radius_km,
        )

        own_request = _build_request(
            user=profile.user,
            current_receipt=profile.current_receipt,
            purchase_history=profile.purchase_history,
            recipe_catalog=recipe_catalog,
            inventory=inventory,
            now=profile.now,
        )
        own_recs: list[ModelRecommendation] = engine.rank(own_request)[:top_k]
        if own_recs:
            covered += 1
        if any(oracle_relevant(profile, recipe_lookup[r.recipe_id], own_request) for r in own_recs):
            own_hits += 1
        for r in own_recs:
            mode_counter[r.mode.value if hasattr(r.mode, "value") else str(r.mode)] += 1
            unique_recipes.add(r.recipe_id)
        own_hd_recs = [r for r in own_recs if r.mode != RecommendationMode.CURRENT]

        shuffled_request = _build_request(
            user=_shuffled_user(profile.user, partner.user),
            current_receipt=profile.current_receipt,
            purchase_history=partner.purchase_history,
            recipe_catalog=recipe_catalog,
            inventory=inventory,
            now=profile.now,
        )
        shuffled_recs: list[ModelRecommendation] = engine.rank(shuffled_request)[:top_k]
        if any(oracle_relevant(profile, recipe_lookup[r.recipe_id], shuffled_request) for r in shuffled_recs):
            shuffled_hits += 1
        shuffled_hd_recs = [r for r in shuffled_recs if r.mode != RecommendationMode.CURRENT]

        # Only count this profile toward the history-dependent slice if
        # personalization actually had a repeat/explore pick to judge on at
        # least one side — otherwise there's nothing history-dependent to
        # compare and including it would silently dilute the metric.
        if own_hd_recs or shuffled_hd_recs:
            hd_n += 1
            if any(oracle_relevant(profile, recipe_lookup[r.recipe_id], own_request) for r in own_hd_recs):
                hd_own_hits += 1
            if any(
                oracle_relevant(profile, recipe_lookup[r.recipe_id], shuffled_request) for r in shuffled_hd_recs
            ):
                hd_shuffled_hits += 1

    n = len(profiles)
    return EvalResult(
        n_profiles=n,
        top_k=top_k,
        hit_rate_own=own_hits / n,
        hit_rate_shuffled=shuffled_hits / n,
        history_dependent_n=hd_n,
        hit_rate_own_history_dependent=(hd_own_hits / hd_n) if hd_n else None,
        hit_rate_shuffled_history_dependent=(hd_shuffled_hits / hd_n) if hd_n else None,
        coverage=covered / n,
        mode_distribution=dict(mode_counter),
        unique_recipes_recommended=len(unique_recipes),
        total_recipes_available=len(recipe_catalog),
    )


if __name__ == "__main__":
    from recsys.model import MLRecommendationEngine
    from recsys.profiles import generate_population
    from recsys.recipes import RECIPES

    engine = MLRecommendationEngine()
    for n in (10, 40):
        profiles = generate_population(n, seed=555)
        result = run_evaluation(engine, profiles, list(RECIPES))
        print(f"--- N={n} ---")
        print(result.summary())
        print()
