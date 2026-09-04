"""The recommendation model adapter.

``MLRecommendationEngine`` implements the exact ``RecommendationEngine``
Protocol from ``app/recommender.py`` (``rank(request) -> list[ModelRecommendation]``)
so it's a drop-in replacement for ``DeterministicMockEngine`` — same input,
same output schema, no changes to ``app.service``/``app.safety``. Safety and
availability are applied *after* this model, unchanged, and this model never
sees or influences them (``app/safety.py``, `app/service.py`` are untouched
by this package).

Scoring implements the ``recipe_score`` formula the team already agreed on in
``docs/research/persona_vxofi/rescue-domovoi-concept.md §7``:

    relevance + current-basket coverage + repeat/discovery fit + time/budget
    fit + save/edit feedback − missing_count penalty − missing_cost penalty
    − constraint violations

as a small logistic regression over engineered features
(``recsys._logistic.LogisticRegression``), fit once at construction time on
implicit preference labels *derived from* the same archetype rules used to
generate the synthetic population (``recsys.profiles.ARCHETYPES``). This is
an honest bootstrap, not real user feedback: the model is trained to
approximate and generalize a hand-authored, auditable rule in continuous
feature space, not to fit ground truth we don't have. See
``docs/research/recsys/recommender-design.md`` for the full writeup.

At inference time (``rank``) the model only uses fields that exist on the
real ``RecommendationRequest`` — it never reads the synthetic archetype
label, which is generation-time-only ground truth, not part of the API
contract.
"""

from __future__ import annotations

import random
from datetime import datetime

from app.contracts import ModelRecommendation, Recipe, RecommendationMode, RecommendationRequest
from recsys._logistic import LogisticRegression
from recsys.catalog import BASE_PRICE_RUB, CATEGORIES
from recsys.profiles import ARCHETYPES, generate_population

FEATURE_NAMES: tuple[str, ...] = (
    "coverage",
    "history_affinity",
    "ingredient_affinity",
    "is_saved",
    "novelty",
    "time_fit",
    "missing_ratio",
    "missing_cost_norm",
    "markdown_supply_signal",
)

MISSING_COST_NORMALIZER_RUB = 500.0
LOW_MISSING_COUNT_THRESHOLD = 2
HIGH_HISTORY_AFFINITY = 0.3
HIGH_COVERAGE = 0.34
NOVELTY_THRESHOLD = 0.15
DISCOVERY_BREADTH_THRESHOLD = 5 / len(CATEGORIES)


def _receipt_ingredient_ids(request: RecommendationRequest) -> set[str]:
    return {
        ingredient_id
        for item in request.current_receipt.items
        if not item.is_prepared_food
        for ingredient_id in item.ingredient_ids
    }


def _history_categories(request: RecommendationRequest) -> set[str]:
    categories = set(request.user.history_categories)
    categories.update(item.category for r in request.purchase_history for item in r.items)
    return categories


def _history_ingredient_ids(request: RecommendationRequest) -> set[str]:
    """Ingredient-level history signal, sparser and more discriminative than
    category-level affinity (7 broad categories vs. ~30 ingredients) — this
    is what actually drives the own-vs-shuffled-history evaluation gap,
    since ``purchase_history`` is exactly what gets swapped in that test."""
    return {
        ingredient_id
        for receipt in request.purchase_history
        for item in receipt.items
        if not item.is_prepared_food
        for ingredient_id in item.ingredient_ids
    }


def _avg_receipt_total(request: RecommendationRequest) -> float:
    receipts = request.purchase_history or [request.current_receipt]
    totals = [sum(item.quantity * item.unit_price for item in r.items) for r in receipts]
    return sum(totals) / len(totals) if totals else 0.0


def _markdown_supply_signal(request: RecommendationRequest, missing_ids: set[str]) -> float:
    if not missing_ids:
        return 0.0
    covered = 0
    for ingredient_id in missing_ids:
        for product in request.inventory_snapshot:
            if (
                product.is_markdown
                and not product.is_prepared_food
                and ingredient_id in product.ingredient_ids
                and product.distance_km <= request.user.radius_km
            ):
                covered += 1
                break
    return covered / len(missing_ids)


def compute_features(request: RecommendationRequest, recipe: Recipe) -> dict[str, float]:
    receipt_ids = _receipt_ingredient_ids(request)
    home_ids = request.user.home_ingredient_ids
    history_categories = _history_categories(request)
    history_ingredient_ids = _history_ingredient_ids(request)

    ingredient_ids = {i.ingredient_id for i in recipe.ingredients}
    categories = {i.category for i in recipe.ingredients}
    total = max(len(recipe.ingredients), 1)

    current_hits = len(ingredient_ids & receipt_ids)
    covered_ids = receipt_ids | home_ids
    missing_ids = ingredient_ids - covered_ids
    history_hits = len(categories & history_categories)
    ingredient_history_hits = len(ingredient_ids & history_ingredient_ids)

    coverage = min(current_hits / total, 1.0)
    history_affinity = min(history_hits / total, 1.0)
    ingredient_affinity = min(ingredient_history_hits / total, 1.0)
    # Ingredient-level overlap is the more specific, more discriminative
    # signal (see _history_ingredient_ids); category-level is a coarser
    # fallback so a recipe with no exact-ingredient repeat isn't treated as
    # fully novel just because the taxonomy only has 7 categories.
    combined_affinity = 0.65 * ingredient_affinity + 0.35 * history_affinity
    is_saved = 1.0 if recipe.recipe_id in request.user.saved_recipe_ids else 0.0
    novelty = 1.0 - combined_affinity

    if recipe.preparation_minutes is None:
        time_fit = 1.0
    elif recipe.preparation_minutes <= 30:
        time_fit = 1.0
    else:
        time_fit = max(0.0, 1.0 - (recipe.preparation_minutes - 30) / 90)

    missing_ratio = len(missing_ids) / total
    missing_cost = sum(BASE_PRICE_RUB.get(i, 150.0) for i in missing_ids)
    missing_cost_norm = min(missing_cost / MISSING_COST_NORMALIZER_RUB, 2.0)
    markdown_signal = _markdown_supply_signal(request, missing_ids)

    return {
        "coverage": coverage,
        "history_affinity": history_affinity,
        "ingredient_affinity": ingredient_affinity,
        "is_saved": is_saved,
        "novelty": novelty,
        "time_fit": time_fit,
        "missing_ratio": missing_ratio,
        "missing_cost_norm": missing_cost_norm,
        "markdown_supply_signal": markdown_signal,
        # not used as model input, only for mode/reason-code derivation and
        # oracle judgment below
        "_combined_affinity": combined_affinity,
        "_current_hits": float(current_hits),
        "_missing_count": float(len(missing_ids)),
        "_history_hits": float(history_hits),
        "_missing_cost": missing_cost,
    }


def _feature_vector(features: dict[str, float]) -> list[float]:
    return [features[name] for name in FEATURE_NAMES]


def _label_for_pair(
    rng: random.Random,
    *,
    features: dict[str, float],
    archetype_name: str,
    recipe: Recipe,
) -> float:
    """Implicit-preference label derived from the archetype's own generative
    rule (docs/research/persona_vxofi/rescue-domovoi-concept.md §6-7), not
    real user feedback. See module docstring."""
    params = ARCHETYPES[archetype_name]
    missing_count = int(features["_missing_count"])
    tolerance = params.max_missing_tolerance
    if features["markdown_supply_signal"] >= 0.5 and rng.random() < params.markdown_affinity:
        # Markdown-sensitive archetypes tolerate one extra missing item when
        # rescue supply for this recipe looks good — gives the classifier a
        # real (non-degenerate) reason to weight markdown_supply_signal.
        tolerance += 1
    if missing_count > tolerance:
        return 0.0
    if (
        params.time_limit_minutes is not None
        and recipe.preparation_minutes is not None
        and recipe.preparation_minutes > params.time_limit_minutes
    ):
        return 0.0
    if features["is_saved"] >= 1.0:
        return 1.0
    if features["coverage"] >= HIGH_COVERAGE:
        return 1.0
    if features["_combined_affinity"] < NOVELTY_THRESHOLD:  # novel/explore-leaning candidate
        return 1.0 if rng.random() < params.discovery_acceptance else 0.0
    return 1.0 if features["_combined_affinity"] >= HIGH_HISTORY_AFFINITY else 0.0


def _train_classifier(*, seed: int, n_profiles: int, recipe_catalog: list[Recipe]) -> LogisticRegression:
    from recsys.inventory import generate_inventory  # local import: no import-time cycle

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
            X.append(_feature_vector(features))
            y.append(_label_for_pair(rng, features=features, archetype_name=profile.archetype, recipe=recipe))
    model = LogisticRegression(n_features=len(FEATURE_NAMES))
    model.fit(X, y, epochs=250)
    return model


class MLRecommendationEngine:
    """Trained, explainable adapter implementing ``RecommendationEngine``."""

    def __init__(
        self,
        *,
        recipe_catalog: list[Recipe] | None = None,
        seed: int = 999,
        training_profiles: int = 300,
    ) -> None:
        from recsys.recipes import RECIPES  # local import avoids a hard import-time cycle

        self._recipe_catalog_for_training = list(recipe_catalog or RECIPES)
        self._classifier = _train_classifier(
            seed=seed,
            n_profiles=training_profiles,
            recipe_catalog=self._recipe_catalog_for_training,
        )

    def rank(self, request: RecommendationRequest) -> list[ModelRecommendation]:
        history_categories = _history_categories(request)
        breadth = len(history_categories) / len(CATEGORIES)

        ranked: list[ModelRecommendation] = []
        for recipe in request.recipe_catalog:
            if not recipe.verified:
                continue
            features = compute_features(request, recipe)
            score = self._classifier.predict_proba(_feature_vector(features))
            score = max(0.0, min(1.0, score))

            if recipe.recipe_id in request.user.saved_recipe_ids:
                mode = RecommendationMode.REPEAT
            elif features["_current_hits"] > 0:
                mode = RecommendationMode.CURRENT
            else:
                mode = RecommendationMode.EXPLORE

            reason_codes = self._reason_codes(
                request=request,
                recipe=recipe,
                features=features,
                mode=mode,
                history_breadth=breadth,
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

    @staticmethod
    def _reason_codes(
        *,
        request: RecommendationRequest,
        recipe: Recipe,
        features: dict[str, float],
        mode: RecommendationMode,
        history_breadth: float,
    ) -> list[str]:
        codes: list[str] = []
        if features["_current_hits"] > 0:
            codes.append("current_receipt_overlap")
        if mode == RecommendationMode.REPEAT:
            codes.append("saved_recipe_repeat")
        if features["history_affinity"] >= HIGH_HISTORY_AFFINITY:
            codes.append("category_history_match")
        if recipe.preparation_minutes is not None and recipe.preparation_minutes <= 30:
            codes.append("quick_recipe")
        if mode == RecommendationMode.EXPLORE:
            codes.append("personalized_discovery")
            if history_breadth >= DISCOVERY_BREADTH_THRESHOLD:
                codes.append("high_discovery_acceptance")
        if 0 < features["_missing_count"] <= LOW_MISSING_COUNT_THRESHOLD:
            codes.append("low_missing_count")
        if features["markdown_supply_signal"] >= HIGH_HISTORY_AFFINITY:
            codes.append("markdown_supply_likely")
        if request.user.preferred_brands and features["coverage"] > 0:
            codes.append("brand_affinity_match")
        if any(i.ingredient_id in request.user.home_ingredient_ids for i in recipe.ingredients):
            codes.append("home_ingredient_reuse")
        avg_total = _avg_receipt_total(request)
        if avg_total > 0 and features["_missing_cost"] <= 0.5 * avg_total:
            codes.append("usual_price_band")
        if history_breadth >= 0.6 and len({i.category for i in recipe.ingredients}) >= 3:
            codes.append("wide_basket_fit")
        if not codes:
            codes.append("personalized_discovery")
        return codes
