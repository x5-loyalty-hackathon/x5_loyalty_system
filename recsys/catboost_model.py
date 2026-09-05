"""Gradient-boosted challenger to ``recsys.model.MLRecommendationEngine``.

Reuses ``recsys.model``'s exact training pipeline — the same
``compute_features``/``_feature_vector``/``_label_for_pair``/``generate_population``
calls, the same synthetic profiles, the same labels — so the *only*
difference from the shipped logistic-regression ranker is the classifier.
If the ranking quality differs, that difference is attributable to model
capacity, not to a different dataset.

Tries ``catboost`` first. If it is not installed (no network, no wheel for
this platform), this module does **not** silently fall back to something
else and call it CatBoost: it substitutes
``sklearn.ensemble.GradientBoostingClassifier`` and exposes
``GRADIENT_BOOSTER_BACKEND`` so callers (and the experiment 1 report) can
say plainly which one actually ran.
"""

from __future__ import annotations

import random

from app.contracts import ModelRecommendation, RecommendationMode, RecommendationRequest
from recsys.catalog import CATEGORIES
from recsys.model import (
    MLRecommendationEngine,
    _feature_vector,
    _history_categories,
    _label_for_pair,
    compute_features,
    compute_user_stats,
)
from recsys.pantry import DISABLED_PANTRY, PantryPolicy
from recsys.profiles import generate_population

try:
    from catboost import CatBoostClassifier as _Booster

    GRADIENT_BOOSTER_BACKEND = "catboost"
except ImportError:
    from sklearn.ensemble import GradientBoostingClassifier as _Booster

    GRADIENT_BOOSTER_BACKEND = "sklearn_gbm_substitute"


def _make_booster(seed: int):
    if GRADIENT_BOOSTER_BACKEND == "catboost":
        return _Booster(
            iterations=200,
            depth=4,
            learning_rate=0.1,
            loss_function="Logloss",
            random_seed=seed,
            verbose=False,
            allow_writing_files=False,
        )
    return _Booster(n_estimators=200, max_depth=3, learning_rate=0.1, random_state=seed)


def _train_booster(*, seed: int, n_profiles: int, recipe_catalog: list) -> object:
    """Mirrors ``recsys.model._train_classifier`` row for row, on purpose:
    see module docstring for why the datasets must be identical."""
    from recsys.inventory import generate_inventory

    rng = random.Random(seed)
    training_profiles = generate_population(n_profiles, seed=seed)
    X: list[list[float]] = []
    y: list[float] = []
    for profile in training_profiles:
        inventory = generate_inventory(
            rng,
            now=profile.now,
            home_store_id=profile.current_receipt.store_id,
            user_radius_km=profile.user.radius_km,
        )
        request = RecommendationRequest(
            user=profile.user,
            current_receipt=profile.current_receipt,
            purchase_history=profile.purchase_history,
            recipe_catalog=recipe_catalog,
            inventory_snapshot=inventory,
            now=profile.now,
            limit=10,
        )
        sampled_recipes = rng.sample(recipe_catalog, k=min(6, len(recipe_catalog)))
        for recipe in sampled_recipes:
            features = compute_features(request, recipe)
            X.append(_feature_vector(features, include_effort=True))
            y.append(
                _label_for_pair(
                    rng, features=features, archetype_name=profile.archetype, recipe=recipe
                )
            )
    booster = _make_booster(seed)
    booster.fit(X, y)
    return booster


class CatBoostRecommendationEngine:
    """Trained adapter implementing ``RecommendationEngine``, same feature
    pipeline as ``MLRecommendationEngine``, gradient-boosted classifier
    instead of logistic regression. See ``GRADIENT_BOOSTER_BACKEND`` for
    which library actually trained it in this environment."""

    def __init__(
        self,
        *,
        recipe_catalog: list | None = None,
        seed: int = 999,
        training_profiles: int = 300,
        pantry_policy: PantryPolicy = DISABLED_PANTRY,
    ) -> None:
        from recsys.recipes import RECIPES

        self._recipe_catalog_for_training = list(recipe_catalog or RECIPES)
        self._pantry_policy = pantry_policy
        self.backend = GRADIENT_BOOSTER_BACKEND
        self._booster = _train_booster(
            seed=seed,
            n_profiles=training_profiles,
            recipe_catalog=self._recipe_catalog_for_training,
        )

    def rank(self, request: RecommendationRequest) -> list[ModelRecommendation]:
        history_categories_breadth = _history_breadth(request)
        user_stats = compute_user_stats(request)

        verified_recipes = [r for r in request.recipe_catalog if r.verified]
        all_features = [
            compute_features(request, recipe, user_stats, pantry_policy=self._pantry_policy)
            for recipe in verified_recipes
        ]
        # Batched: one predict_proba call over all rows instead of one per
        # recipe. A tree ensemble's per-call Python overhead dominates at
        # this row count, so this is ~N times fewer round trips per request.
        rows = [_feature_vector(f, include_effort=True) for f in all_features]
        scores = (
            [s[1] for s in self._booster.predict_proba(rows)] if rows else []
        )

        ranked: list[ModelRecommendation] = []
        for recipe, features, raw_score in zip(verified_recipes, all_features, scores, strict=True):
            score = max(0.0, min(1.0, float(raw_score)))
            mode = _mode_for(request, recipe, features)
            reason_codes = MLRecommendationEngine._reason_codes(
                request=request,
                recipe=recipe,
                features=features,
                mode=mode,
                history_breadth=history_categories_breadth,
            )
            ranked.append(
                ModelRecommendation(
                    recipe_id=recipe.recipe_id,
                    mode=mode,
                    score=round(score, 4),
                    reason_codes=reason_codes,
                )
            )
        return sorted(ranked, key=lambda item: (-item.score, item.recipe_id))


def _history_breadth(request: RecommendationRequest) -> float:
    return len(_history_categories(request)) / len(CATEGORIES)


def _mode_for(request: RecommendationRequest, recipe, features: dict[str, float]) -> RecommendationMode:
    if recipe.recipe_id in request.user.saved_recipe_ids:
        return RecommendationMode.REPEAT
    if features["_current_hits"] > 0:
        return RecommendationMode.CURRENT
    return RecommendationMode.EXPLORE
