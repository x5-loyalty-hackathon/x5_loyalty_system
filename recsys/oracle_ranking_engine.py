"""A ranking ceiling *given the features a ranker can see*, not an absolute one.

``recsys.experimental.evaluation.oracle_relevant`` is a binary verdict, not an order, and
two of its three branches key on quantities a ``RecommendationEngine`` can
actually observe: ``is_saved`` and ``coverage >= HIGH_COVERAGE``. The third
branch (novel vs. familiar) further depends on ``ArchetypeParams.discovery_acceptance``,
which is generation-time-only ground truth — no ``RecommendationRequest``
field exposes it, so no real ranker (including this one) can use it. This
engine keeps the two observable gates as discrete precedence tiers, matching
``oracle_relevant``'s own precedence, and falls back to the continuous
``_combined_affinity`` — the quantity ``oracle_relevant``'s remaining
branches threshold — everywhere else.

This is therefore self-referential in the same way ``oracle_relevant`` is
(see its docstring and ADR-003): both come from the same archetype rule.
Use it as a *relative* ceiling for the other three rankers under this
label, not as evidence of real-user relevance.
"""

from __future__ import annotations

from recsys.experimental.contracts import ModelRecommendation, RecommendationMode, RecommendationRequest
from recsys.experimental.model import HIGH_COVERAGE, compute_features, compute_user_stats

#: Discrete precedence tiers mirroring oracle_relevant's own if/elif order:
#: a saved recipe always outranks a merely-high-coverage one, which always
#: outranks anything scored on affinity alone.
_SAVED_TIER = 2.0
_HIGH_COVERAGE_TIER = 1.0
_TIER_COUNT = _SAVED_TIER + 1.0


def _oracle_score(features: dict[str, float]) -> float:
    if features["is_saved"] >= 1.0:
        tier = _SAVED_TIER
    elif features["coverage"] >= HIGH_COVERAGE:
        tier = _HIGH_COVERAGE_TIER
    else:
        tier = 0.0
    # _combined_affinity is already in [0, 1], so this stays within
    # [0, _TIER_COUNT] and the normalization below stays in [0, 1].
    return tier + features["_combined_affinity"]


class OracleRankingEngine:
    """Continuous stand-in for ``oracle_relevant``, for ranking rather than
    classification. See module docstring for what it cannot see."""

    def rank(self, request: RecommendationRequest) -> list[ModelRecommendation]:
        user_stats = compute_user_stats(request)
        ranked: list[ModelRecommendation] = []

        for recipe in request.recipe_catalog:
            if not recipe.verified:
                continue
            features = compute_features(request, recipe, user_stats)
            score = _oracle_score(features) / _TIER_COUNT

            if recipe.recipe_id in request.user.saved_recipe_ids:
                mode = RecommendationMode.REPEAT
                reason_codes = ["saved_recipe_repeat"]
            elif features["_current_hits"] > 0:
                mode = RecommendationMode.CURRENT
                reason_codes = ["current_receipt_overlap"]
            else:
                mode = RecommendationMode.EXPLORE
                reason_codes = ["personalized_discovery"]

            ranked.append(
                ModelRecommendation(
                    recipe_id=recipe.recipe_id,
                    mode=mode,
                    score=round(min(max(score, 0.0), 1.0), 4),
                    reason_codes=reason_codes,
                )
            )
        return sorted(ranked, key=lambda item: (-item.score, item.recipe_id))
