"""The recommendation model adapter.

Integrated from recsys-benchmark@02132c8 under API 1.2. Explicit HOME,
required-only missing counts and prepared-food boundaries are retained.
Experimental serving policies live in recsys.experimental, never app.service.
Numerical observations in inherited comments belong to the source experiments,
not measurements of this integration. See docs/integration-handoff.md.

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

from dataclasses import dataclass

from app.contracts import ModelRecommendation, Recipe, RecommendationMode, RecommendationRequest
from recsys._logistic import LogisticRegression
from recsys.catalog import BASE_PRICE_RUB, CATEGORIES
from recsys.pantry import DISABLED_PANTRY, PantryPolicy, available_ingredient_ids
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
    # --- observable user state, derived from the user's own history ---------
    # The label in ``_label_for_pair`` gates on four archetype traits
    # (tolerance, time limit, discovery acceptance, markdown affinity) that no
    # feature exposed, so the model was asked to predict a function of
    # variables it could not see and could only learn the population marginal.
    # These are proxies a real product genuinely has: they come from the
    # purchase history, never from the synthetic archetype label.
    "markdown_share_history",
    "basket_size_norm",
    "visit_cadence_norm",
    "brand_concentration",
    # --- user x item interactions ------------------------------------------
    # A linear model cannot represent "missing_count > this user's tolerance"
    # from the two terms separately; the ratio has to be handed to it.
    "missing_vs_basket",
    "prep_vs_cadence",
    #: 1.0 when the proxies above were computed from real purchase history,
    #: 0.0 when there was none and they fall back to today's receipt. Without
    #: it a brand-new user is indistinguishable from a rare shopper, because
    #: the fallback cadence is a constant that looks exactly like data.
    "history_is_known",
)

MISSING_COST_NORMALIZER_RUB = 500.0
LOW_MISSING_COUNT_THRESHOLD = 2

# Thresholds on the affinity/coverage scales, expressed as quantiles of the
# current synthetic population so the rules they gate actually split it.
#
# They were re-derived when ``history_affinity`` was redefined: the old values
# were tuned to the previous (saturated) definition and, on the new scale,
# ``HIGH_HISTORY_AFFINITY`` admitted 97% of pairs while ``HIGH_COVERAGE``
# admitted 1% — so both rules had stopped discriminating. A threshold that
# matches nothing, or everything, is not a rule.
#: ~p65 of combined affinity: "this is squarely their kind of food".
HIGH_HISTORY_AFFINITY = 0.55
#: ~p85 of coverage: "today's receipt already covers a real part of it".
HIGH_COVERAGE = 0.20
#: ~p25 of combined affinity: below this the recipe is genuinely unfamiliar.
NOVELTY_THRESHOLD = 0.43
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


@dataclass(frozen=True)
class UserStats:
    """Observable behaviour summary, computed once per request.

    Every field is derivable from ``purchase_history`` alone — nothing here
    reads ``SyntheticProfile.archetype``, which is generation-time truth and
    not part of the API contract.
    """

    markdown_share: float
    mean_basket_size: float
    mean_cadence_days: float
    brand_concentration: float
    category_share: dict[str, float]
    #: False when there was no purchase history and everything above was
    #: inferred from a single receipt. Fabricated values must be labelled as
    #: fabricated rather than flow into the model looking like measurements.
    has_history: bool = True


#: Baskets larger than this are treated as "as large as it gets" when the
#: basket size is put on a 0..1 scale.
BASKET_SIZE_NORMALIZER = 12.0

#: Visit gaps longer than this are treated as equally infrequent.
CADENCE_NORMALIZER_DAYS = 7.0




def compute_user_stats(request: RecommendationRequest) -> UserStats:
    history = list(request.purchase_history)
    has_history = len(history) >= 2
    receipts = history or [request.current_receipt]
    items = [item for receipt in receipts for item in receipt.items]
    n_items = len(items) or 1

    markdown_share = sum(1 for item in items if item.is_markdown) / n_items
    mean_basket_size = sum(len(r.items) for r in receipts) / len(receipts)

    times = sorted(r.purchased_at for r in receipts)
    if len(times) > 1:
        gaps = [
            (later - earlier).total_seconds() / 86400.0
            for earlier, later in zip(times, times[1:], strict=False)
        ]
        mean_cadence = sum(gaps) / len(gaps)
    else:
        mean_cadence = CADENCE_NORMALIZER_DAYS

    # Share of branded purchases going to the single most-used brand. The
    # obvious alternative, distinct-brands / branded-items, saturates: the
    # catalog only has four brands, so every user scored ~0.93 regardless of
    # loyalty.
    branded = [item.brand for item in items if item.brand]
    if branded:
        brand_counts: dict[str, int] = {}
        for brand in branded:
            brand_counts[brand] = brand_counts.get(brand, 0) + 1
        brand_concentration = max(brand_counts.values()) / len(branded)
    else:
        brand_concentration = 0.0

    counts: dict[str, int] = {}
    for item in items:
        counts[item.category] = counts.get(item.category, 0) + 1
    category_share = {c: counts.get(c, 0) / n_items for c in CATEGORIES}

    return UserStats(
        markdown_share=markdown_share,
        mean_basket_size=mean_basket_size,
        mean_cadence_days=mean_cadence,
        brand_concentration=brand_concentration,
        category_share=category_share,
        has_history=has_history,
    )


def _markdown_supply_signal(request: RecommendationRequest, missing_ids: set[str]) -> float:
    if not missing_ids:
        return 0.0
    covered = 0
    for ingredient_id in missing_ids:
        for product in request.inventory_snapshot:
            if (
                product.is_markdown
                and ingredient_id in product.ingredient_ids
                and product.distance_km <= request.user.radius_km
            ):
                covered += 1
                break
    return covered / len(missing_ids)


def compute_features(
    request: RecommendationRequest,
    recipe: Recipe,
    user_stats: UserStats | None = None,
    pantry_policy: PantryPolicy = DISABLED_PANTRY,
) -> dict[str, float]:
    """Features for one (request, recipe) pair.

    ``user_stats`` is recipe-independent; ``rank`` computes it once per request
    and passes it in. Callers that omit it get the same numbers, just slower.
    """
    stats = user_stats if user_stats is not None else compute_user_stats(request)
    # Current overlap is receipt-only; explicit HOME affects missing count.
    receipt_ids = _receipt_ingredient_ids(request)
    # Explicit HOME is retained from API 1.2; an inferred pantry remains opt-in.
    available_ids = available_ingredient_ids(request, policy=pantry_policy)
    history_ingredient_ids = _history_ingredient_ids(request)

    ingredient_ids = {i.ingredient_id for i in recipe.ingredients}
    categories = {i.category for i in recipe.ingredients}
    total = max(len(recipe.ingredients), 1)

    current_hits = len(ingredient_ids & receipt_ids)
    covered_ids = available_ids
    required_ids = {i.ingredient_id for i in recipe.ingredients if i.required}
    missing_ids = required_ids - covered_ids
    ingredient_history_hits = len(ingredient_ids & history_ingredient_ids)

    coverage = min(current_hits / total, 1.0)
    # How heavily this user actually buys the categories the recipe needs,
    # averaged over the recipe's distinct categories.
    #
    # The previous definition was |recipe categories & history categories| /
    # |recipe ingredients|. It divided a category count by an ingredient count,
    # and every user's history covered all seven categories, so it reduced to a
    # recipe-shape constant: measured variance was 100% between recipes and 0%
    # between users. It was the strongest "personalisation" feature in the
    # model and carried no personalisation at all.
    uniform_share = 1.0 / len(CATEGORIES)
    history_affinity = (
        sum(
            min(stats.category_share.get(c, 0.0) / (2.0 * uniform_share), 1.0)
            for c in categories
        )
        / len(categories)
        if categories
        else 0.0
    )
    ingredient_affinity = min(ingredient_history_hits / total, 1.0)
    # Ingredient-level overlap is the more specific, more discriminative
    # signal (see _history_ingredient_ids); category-level is a coarser
    # fallback so a recipe with no exact-ingredient repeat isn't treated as
    # fully novel just because the taxonomy only has 7 categories.
    combined_affinity = 0.65 * ingredient_affinity + 0.35 * history_affinity
    is_saved = 1.0 if recipe.recipe_id in request.user.saved_recipe_ids else 0.0
    novelty = 1.0 - combined_affinity

    # Deliberately a pure recipe property: how long the dish takes, on a 0..1
    # scale. It measures 100% between-recipe variance, which by the test that
    # exposed ``history_affinity`` looks like the same defect — a recipe
    # statistic posing as personalisation.
    #
    # It is not, and making it personal was tried and reverted. Two variants
    # were measured: a per-user time budget derived from visit cadence
    # (threshold form) and a smooth patience ratio. Neither moved the metric
    # that matters — within-effort AUC went 0.821 -> 0.824, noise — because the
    # personal half of the signal is already carried by ``prep_vs_cadence``,
    # which holds more user variance (0.07) than either variant of a
    # personalised ``time_fit`` (0.05 and 0.02).
    #
    # Folding recipe length and user patience into one number also hides them
    # from a linear model, which cannot weight them separately. Keeping the
    # item term clean and the interaction explicit is the better split.
    if recipe.preparation_minutes is None:
        time_fit = 1.0
    elif recipe.preparation_minutes <= 30:
        time_fit = 1.0
    else:
        time_fit = max(0.0, 1.0 - (recipe.preparation_minutes - 30) / 90)

    missing_count = len(missing_ids)
    missing_ratio = missing_count / total
    # How big this top-up is next to the user's usual basket. This is the
    # quantity the label's tolerance gate is really about, and a linear model
    # cannot build it from ``missing_ratio`` and basket size separately.
    missing_vs_basket = min(missing_count / max(stats.mean_basket_size, 1.0), 2.0)
    # Frequent shoppers behave as the time-pressed segment, so a long recipe
    # costs them more. Again an interaction the model cannot form on its own.
    prep_minutes = float(recipe.preparation_minutes or 30)
    prep_vs_cadence = min(
        (prep_minutes / 60.0) * (CADENCE_NORMALIZER_DAYS / max(stats.mean_cadence_days, 0.5)),
        3.0,
    )
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
        "markdown_share_history": min(stats.markdown_share * 3.0, 1.0),
        "basket_size_norm": min(stats.mean_basket_size / BASKET_SIZE_NORMALIZER, 1.0),
        "visit_cadence_norm": min(stats.mean_cadence_days / CADENCE_NORMALIZER_DAYS, 1.0),
        "brand_concentration": stats.brand_concentration,
        "missing_vs_basket": missing_vs_basket,
        "prep_vs_cadence": prep_vs_cadence,
        "history_is_known": 1.0 if stats.has_history else 0.0,
        # not used as model input, only for mode/reason-code derivation and
        # oracle judgment below
        "_combined_affinity": combined_affinity,
        "_current_hits": float(current_hits),
        "_missing_count": float(missing_count),
        "_missing_cost": missing_cost,
    }


#: Features that describe how much work a recipe is, rather than how much the
#: user would like it. The experimental ``RankingPolicy`` orders on exactly
#: this quantity, so a model that also encodes it is duplicating the pipeline's
#: own work — measured at r = -0.71 between ``model_score`` and missing count
#: (see ``docs/benchmark-report.md``).
EFFORT_FEATURE_NAMES: frozenset[str] = frozenset(
    {"missing_ratio", "missing_cost_norm"}
)

#: Features describing *the shop*, not the shopper or the dish.
#: ``markdown_supply_signal`` reads ``request.inventory_snapshot``, which makes
#: ``model_score`` a function of today's shelf: the same person and the same
#: recipe score differently depending on what happened to be in stock
#: (measured: 0.0027 of score movement across six inventory draws for one
#: user). Three consequences, all bad for a preference model — the score cannot
#: be cached, it cannot be compared across supply scenarios, and it quietly
#: mixes "would they want this" with "can they buy it here", which
#: ``docs/research/recsys/evaluation-protocol.md`` requires to be measured
#: apart. Availability belongs to ``app.service``, which already applies it on
#: live inventory. Same shape of defect as the effort double-count in EXP-002.
AVAILABILITY_FEATURE_NAMES: frozenset[str] = frozenset({"markdown_supply_signal"})


def _feature_vector(
    features: dict[str, float],
    *,
    include_effort: bool = True,
    include_availability: bool = False,
) -> list[float]:
    """Feature row, optionally with whole groups zeroed.

    Zeroing rather than dropping keeps the vector length equal to
    ``FEATURE_NAMES`` so every variant shares one classifier shape and one set
    of weight indices — the models stay directly comparable.
    """
    suppressed: set[str] = set()
    if not include_effort:
        suppressed |= EFFORT_FEATURE_NAMES
    if not include_availability:
        suppressed |= AVAILABILITY_FEATURE_NAMES
    return [
        0.0 if name in suppressed else features[name] for name in FEATURE_NAMES
    ]


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
    # Feasibility deliberately does NOT gate this label any more.
    #
    # It used to open with ``if missing_count > tolerance: return 0.0``, which
    # made relevance almost a function of how much shopping a recipe needed: no
    # recipe with six or more missing ingredients was ever labelled relevant, so
    # the model learned effort and nothing else (measured AUC 0.53 within
    # equal-effort strata). Whether a basket is affordable today is the job of
    # the service-side selector and the availability filter, which already
    # do it on live inventory. This label answers only "would this person want
    # this dish".
    #
    # Time is kept, because wanting a 90-minute recipe on a weeknight is a
    # preference, not a supply constraint.
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


#: Index range for the model's own training population.
#:
#: ``generate_profile`` names people ``synthetic_<archetype>_<index>``, so two
#: populations drawn over the same index range hand *different* people the same
#: id. Measured before this existed: 87 ids shared between the training draw
#: and the development panel. That is not a leak — the data differs — but it
#: makes "was this user trained on?" unanswerable by id and silently corrupts
#: any per-user join across the two. Kept clear of
#: ``recsys.panels.COHORT_INDEX_OFFSET``.
TRAINING_INDEX_OFFSET = 2_000_000


def _train_classifier(
    *,
    seed: int,
    n_profiles: int,
    recipe_catalog: list[Recipe],
    include_effort: bool = True,
    include_availability: bool = False,
) -> LogisticRegression:
    from recsys.inventory import generate_inventory  # local import: no import-time cycle

    rng = random.Random(seed)
    training_profiles = generate_population(
        n_profiles, seed=seed, index_offset=TRAINING_INDEX_OFFSET,
        saved_recipe_pool=recipe_catalog,
    )
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
            X.append(
                _feature_vector(
                    features,
                    include_effort=include_effort,
                    include_availability=include_availability,
                )
            )
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
        include_effort_features: bool = True,
        include_availability_features: bool = False,
        pantry_policy: PantryPolicy = DISABLED_PANTRY,
    ) -> None:
        """``include_effort_features=False`` trains a preference-only ranker.

        This switch comes from offline comparisons in
        ``recsys.experimental.service``. API 1.2 retains effort features and
        the accepted missing-first selector; no alternative policy is enabled.

        ``include_availability_features`` defaults to False — see
        ``AVAILABILITY_FEATURE_NAMES`` for why a preference model must not read
        the shelf.

        ``recipe_catalog`` defaults to the **frozen baseline**, not to the live
        catalog. Training samples six recipes per profile, so a longer catalog
        draws a different sample and fits different weights: adding ten
        candidate recipes moved the logistic weights by up to 0.25. A
        catalog-vs-catalog comparison run with a per-arm engine would then
        measure the catalog *and* a retrained model, and report the sum as the
        catalog's effect. Promoting a recipe into training is what
        ``recsys.catalog_freeze`` is for, and it is a deliberate act.
        """
        from recsys.catalog_freeze import baseline_catalog, recipe_content_hash

        self._recipe_catalog_for_training = list(
            recipe_catalog if recipe_catalog is not None else baseline_catalog()
        )
        #: Which catalog these weights came from, so a run can prove two arms
        #: shared one model instead of assuming it.
        self.training_catalog_hash = recipe_content_hash(
            self._recipe_catalog_for_training
        )
        self._include_effort = include_effort_features
        self._include_availability = include_availability_features
        self._pantry_policy = pantry_policy
        self._classifier = _train_classifier(
            seed=seed,
            n_profiles=training_profiles,
            recipe_catalog=self._recipe_catalog_for_training,
            include_effort=include_effort_features,
            include_availability=include_availability_features,
        )

    def rank(self, request: RecommendationRequest) -> list[ModelRecommendation]:
        history_categories = _history_categories(request)
        breadth = len(history_categories) / len(CATEGORIES)
        user_stats = compute_user_stats(request)

        ranked: list[ModelRecommendation] = []
        for recipe in request.recipe_catalog:
            if not recipe.verified:
                continue
            features = compute_features(
                request, recipe, user_stats, pantry_policy=self._pantry_policy
            )
            score = self._classifier.predict_proba(
                _feature_vector(
                    features, include_effort=self._include_effort,
                    include_availability=self._include_availability,
                )
            )
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
        avg_total = _avg_receipt_total(request)
        if avg_total > 0 and features["_missing_cost"] <= 0.5 * avg_total:
            codes.append("usual_price_band")
        if history_breadth >= 0.6 and len({i.category for i in recipe.ingredients}) >= 3:
            codes.append("wide_basket_fit")
        if not codes:
            codes.append("personalized_discovery")
        return codes
