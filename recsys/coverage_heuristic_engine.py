"""The "simple coverage score" candidate for experiment 1.

Not ``app.recommender.DeterministicMockEngine`` — that heuristic blends in a
history-overlap term, so it already carries a personalization signal and
cannot stand in for "no learning, no personalization, just buy what's
closest to done". This engine is that literal baseline: no training, no
purchase history, ranked purely by
``(coverage desc, missing_count asc)`` from ``recsys.model.compute_features``.

Exists so experiment 1 (``docs/research/recsys/experiment-plan-ranker-service-catalog.md``,
"Эксперимент 1") has a floor to compare the trained rankers against.
"""

from __future__ import annotations

from app.contracts import ModelRecommendation, RecommendationMode, RecommendationRequest
from recsys.model import compute_features, compute_user_stats

#: Coverage is already 0..1; missing_count rarely exceeds this, so the
#: secondary term stays a tiebreak and never inverts the primary coverage
#: ordering.
_MISSING_COUNT_TIEBREAK_SCALE = 1e-3
_MAX_EXPECTED_MISSING_COUNT = 20.0


class CoverageHeuristicEngine:
    """Deterministic, unlearned baseline: rank by basket coverage alone."""

    def rank(self, request: RecommendationRequest) -> list[ModelRecommendation]:
        user_stats = compute_user_stats(request)
        candidates: list[tuple[float, int, str, ModelRecommendation]] = []

        for recipe in request.recipe_catalog:
            if not recipe.verified:
                continue
            features = compute_features(request, recipe, user_stats)
            coverage = features["coverage"]
            missing_count = int(features["_missing_count"])

            if recipe.recipe_id in request.user.saved_recipe_ids:
                mode = RecommendationMode.REPEAT
                reason_codes = ["saved_recipe_repeat"]
            elif features["_current_hits"] > 0:
                mode = RecommendationMode.CURRENT
                reason_codes = ["current_receipt_overlap"]
            else:
                mode = RecommendationMode.EXPLORE
                reason_codes = ["personalized_discovery"]
            if 0 < missing_count <= 2:
                reason_codes.append("low_missing_count")

            score = max(
                0.0,
                min(
                    1.0,
                    coverage
                    - _MISSING_COUNT_TIEBREAK_SCALE
                    * min(missing_count, _MAX_EXPECTED_MISSING_COUNT),
                ),
            )
            sort_key = (-coverage, missing_count, recipe.recipe_id)
            candidates.append(
                (
                    *sort_key[:2],
                    recipe.recipe_id,
                    ModelRecommendation(
                        recipe_id=recipe.recipe_id,
                        mode=mode,
                        score=round(score, 4),
                        reason_codes=reason_codes,
                    ),
                )
            )

        candidates.sort(key=lambda row: (row[0], row[1], row[2]))
        return [row[3] for row in candidates]
