"""Blinded LLM-as-user evaluation of own, shuffled and random recipe feeds.

This is a simulation of stated intent, not evidence about real customers or
causal uplift. Its useful claim is narrower: holding a persona, today's
receipt and the shelf fixed, does the feed produced from the persona's own
history elicit more simulated recipe commitment than a feed produced from a
different person's history or a random ranker?

The LLM always sees the *original* shopper's observable history. Shuffled
history is supplied only to the recommender. Showing the shuffled history to
the judge would change both treatment and judge and make the comparison say
nothing about personalization.

Two worlds, on purpose
----------------------
``--ranking-policy effort_first`` (the primary, product-level estimand) runs
the *real* ``app.service.RecommendationService.recommend_meals`` — the same
code path ``/api/v1/meal-recommendations`` serves today, cook/ready routing
included. ``--ranking-policy model_order`` (a ranker-only diagnostic) runs
``recsys.experimental.service`` with the ``MODEL_ORDER`` policy, which does
not exist in production any more: ``app/service.py`` now hardcodes
effort-first sorting, and the pluggable ``RankingPolicy`` abstraction lives
only in the ``recsys.experimental`` sandbox (see ``recsys/model.py``'s module
docstring). The two arms are therefore never mixed inside one run: each
``--ranking-policy`` choice picks one self-consistent world end to end
(contracts, engine, service, safety), never a blend of production and sandbox
types.

Personas, receipts and inventory are drawn once from the same materialized
``recsys.panels`` panel (which is ``recsys.experimental``-typed) for both
worlds. For the production arm they are converted into ``app.contracts``
objects by the small bridge in this module (``_bridge_*``); nothing about the
underlying persona, history or receipt changes, only the Python type carrying
it. The production ``RecommendationRequest`` has no ``ready_meal_options``
field — ready routes there come from prepared-food ``InventoryProduct``
entries instead, so the bridge also synthesizes those from
``recsys.ready_food_pairs.ready_meal_options`` (see
``_production_ready_templates``); this is a deliberate, documented synthesis
step, not observed data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import timezone
from pathlib import Path
from typing import Protocol

# --- production world (app.service.recommend_meals, API 1.3) ---------------
from app.contracts import (
    FulfillmentOption as AppFulfillmentOption,
    IngredientSource as AppIngredientSource,
    InventoryProduct as AppInventoryProduct,
    ModelRecommendation as AppModelRecommendation,
    Receipt as AppReceipt,
    ReceiptItem as AppReceiptItem,
    Recipe as AppRecipe,
    RecommendationMode as AppRecommendationMode,
    RecommendationRequest as AppRecommendationRequest,
    UserProfile as AppUserProfile,
)
from app.recommender import RecommendationEngine as AppRecommendationEngine
from app.safety import SafetyPolicy as AppSafetyPolicy
from app.service import RecommendationService as AppRecommendationService
from recsys.catalog_freeze import recipe_content_hash as app_recipe_content_hash
from recsys.model import MLRecommendationEngine as AppMLRecommendationEngine
from recsys.recipes import RECIPES as APP_SERVING_CATALOG

# --- experimental world (ranker-only diagnostic, recsys.experimental) ------
from recsys.experimental.contracts import (
    IngredientSource as ExpIngredientSource,
    RecipeRecommendation as ExpRecipeRecommendation,
    RecommendationRequest as ExpRecommendationRequest,
    UserProfile as ExpUserProfile,
)
from recsys.experimental.model import (
    MLRecommendationEngine as ExpMLRecommendationEngine,
    compute_user_stats as exp_compute_user_stats,
)
from recsys.experimental.catalog_freeze import (
    baseline_catalog as exp_baseline_catalog,
    recipe_content_hash as exp_recipe_content_hash,
)
from recsys.experimental.safety import SafetyPolicy as ExpSafetyPolicy
from recsys.experimental.service import (
    MODEL_ORDER,
    RecommendationService as ExpRecommendationService,
)
from recsys.model import compute_user_stats as app_compute_user_stats

# --- shared infrastructure ---------------------------------------------------
from recsys._seeds import stable_seed
from recsys.benchmark import RandomEngine as ExpRandomEngine
from recsys.experimental.profiles import SyntheticProfile
from recsys.llm_audit import (
    DEFAULT_DEEPSEEK_MODEL,
    DEFAULT_OPENCODE_GO_MODEL,
    DEFAULT_OPENROUTER_MODEL,
    PROVIDER_KEY_ENV,
    OpenAICompatibleClient,
    _with_retries,
)
from recsys.panels import Panel, development_splits
from recsys.ready_food_pairs import ready_meal_options
from recsys.response_models import UserAction

# --similar-method cf's NMF embeddings need the optional `ml` extra
# (numpy + scikit-learn). Import once, at module load, so both the engine
# code and its tests can branch on one flag instead of each catching
# ImportError separately — same pattern as recsys.catboost_model's
# GRADIENT_BOOSTER_AVAILABLE. Never installed by CI's `pip install -e
# '.[dev]'`, so --similar-method cf (and its tests) are exercised locally,
# not in CI, exactly like recsys.catboost_model's sklearn fallback already is.
try:
    import numpy as _np
    from sklearn.decomposition import NMF as _NMF

    SKLEARN_AVAILABLE = True
except ImportError:
    _np = None
    _NMF = None
    SKLEARN_AVAILABLE = False


PROMPT_VERSION = "intent-v3"
DEFAULT_CACHE = Path(".cache/llm_intent_eval.json")
DEFAULT_OUTPUT = Path(".cache/llm_intent_report.json")
ARM_OWN = "own"
ARM_SHUFFLED = "shuffled"
ARM_RANDOM = "random"
ARM_SIMILAR = "similar"
ARMS = (ARM_OWN, ARM_SHUFFLED, ARM_RANDOM, ARM_SIMILAR)
RANKING_POLICY_WORLD = {"effort_first": "production", "model_order": "experimental"}

#: Distance and store used for synthetic prepared-food inventory in the
#: production bridge. 5 cm inside every plausible ``radius_km`` on purpose:
#: this experiment is not testing whether a ready meal is nearby.
READY_MEAL_STORE_ID = "ready_meal_virtual_store"
READY_MEAL_DISTANCE_KM = 0.05

COOK_HORIZONS = ("no", "maybe", "yes")
REASON_CODES = (
    "taste_match",
    "familiar_recipe",
    "new_recipe_interest",
    "low_topup_effort",
    "high_topup_effort",
    "too_expensive",
    "too_slow",
    "ready_meal_better",
    "poor_history_fit",
    "insufficient_information",
    "other",
)

SYSTEM_PROMPT = """You simulate the grocery shopper described in the input.
Choose what this shopper would genuinely do when shown this three-card recipe
feed after today's receipt. Judge from their observed shopping history and the
visible offer only; do not act as a food critic and do not assume that the feed
is personalized.

Actions:
- ignore: do nothing;
- click: open one recipe, with no stronger commitment;
- save: save one recipe for later;
- buy: add the missing ingredients for one recipe now, intending to cook it
  within seven days. Only valid when the chosen card has "cookable": true —
  some cards have no recipe at all, only a ready-made alternative, and cannot
  be bought-and-cooked;
- substitute: buy the shown ready-made alternative instead of cooking.

Select at most one recipe. selected_recipe_index is its zero-based index in
recommendations, or null for ignore. Return only one JSON object, with exactly
these six keys and no markdown:
{
  "action": "ignore|click|save|buy|substitute",
  "selected_recipe_index": 0,
  "cook_within_7_days": "no|maybe|yes",
  "topup_acceptable": true,
  "confidence": 0.0,
  "reason_code": "taste_match|familiar_recipe|new_recipe_interest|low_topup_effort|high_topup_effort|too_expensive|too_slow|ready_meal_better|poor_history_fit|insufficient_information|other"
}
For action=ignore selected_recipe_index must be null. For any other action it
must be an index of a shown recipe. action=buy requires cook_within_7_days=yes;
action=substitute must not have cook_within_7_days=yes. Check all six keys
before responding.
"""

INTENT_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": [action.value for action in UserAction]},
        "selected_recipe_index": {"type": ["integer", "null"], "minimum": 0},
        "cook_within_7_days": {"type": "string", "enum": list(COOK_HORIZONS)},
        "topup_acceptable": {"type": "boolean"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "reason_code": {"type": "string", "enum": list(REASON_CODES)},
    },
    "required": [
        "action",
        "selected_recipe_index",
        "cook_within_7_days",
        "topup_acceptable",
        "confidence",
        "reason_code",
    ],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class IntentDecision:
    action: UserAction
    selected_recipe_index: int | None
    cook_within_7_days: str
    topup_acceptable: bool
    confidence: float
    reason_code: str

    def to_json(self) -> dict[str, object]:
        return {
            "action": self.action.value,
            "selected_recipe_index": self.selected_recipe_index,
            "cook_within_7_days": self.cook_within_7_days,
            "topup_acceptable": self.topup_acceptable,
            "confidence": self.confidence,
            "reason_code": self.reason_code,
        }


def parse_intent_decision(raw: object, *, recommendation_count: int) -> IntentDecision:
    if not isinstance(raw, dict):
        raise ValueError("intent response must be an object")
    try:
        action = UserAction(str(raw["action"]).strip().lower())
        selected_raw = raw["selected_recipe_index"]
        if selected_raw is not None and type(selected_raw) is not int:
            raise TypeError("selected_recipe_index must be an integer or null")
        selected = selected_raw
        horizon = str(raw["cook_within_7_days"]).strip().lower()
        topup = raw["topup_acceptable"]
        confidence = float(raw["confidence"])
        reason = str(raw["reason_code"]).strip()
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("intent response has missing or invalid fields") from error

    if selected is not None and not 0 <= selected < recommendation_count:
        raise ValueError("selected_recipe_index is outside the shown feed")
    if action == UserAction.IGNORE and selected is not None:
        raise ValueError("ignore requires selected_recipe_index=null")
    if action != UserAction.IGNORE and selected is None:
        raise ValueError("a non-ignore action requires a selected recipe")
    if horizon not in COOK_HORIZONS:
        raise ValueError(f"cook_within_7_days must be one of {COOK_HORIZONS}")
    if type(topup) is not bool:
        raise ValueError("topup_acceptable must be boolean")
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be between 0 and 1")
    if reason not in REASON_CODES:
        raise ValueError(f"reason_code must be one of {REASON_CODES}")
    if action == UserAction.BUY and horizon != "yes":
        raise ValueError("buy means intent to cook within seven days")
    if action == UserAction.SUBSTITUTE and horizon == "yes":
        raise ValueError("substitute is not recipe-cooking intent")
    return IntentDecision(action, selected, horizon, topup, confidence, reason)


def _validate_cookable(decision: IntentDecision, recommendations: list) -> None:
    """A card with ``cookable: false`` has no recipe, only a ready-made
    alternative — the model must not claim it will buy-and-cook it."""
    if decision.action != UserAction.BUY or decision.selected_recipe_index is None:
        return
    card = recommendations[decision.selected_recipe_index]
    if isinstance(card, dict) and not card.get("cookable", True):
        raise ValueError("buy selected on a card with no cook path (cookable=false)")


class IntentClient(Protocol):
    model: str
    cache_identity: str

    def decide(self, payload: dict[str, object], *, seed: int) -> IntentDecision: ...


class OpenAICompatibleIntentClient:
    """Intent adapter over the repository's existing compatible client."""

    def __init__(self, transport: OpenAICompatibleClient) -> None:
        self.transport = transport
        self.model = transport.model
        self.cache_identity = transport.cache_identity

    def decide(self, payload: dict[str, object], *, seed: int) -> IntentDecision:
        raw = self.transport.complete_json(
            system_prompt=SYSTEM_PROMPT,
            payload=payload,
            response_schema=INTENT_SCHEMA,
            schema_name="recipe_intent",
            temperature=0.0,
            seed=seed,
        )
        recommendations = payload.get("recommendations", [])
        decision = parse_intent_decision(raw, recommendation_count=len(recommendations))
        _validate_cookable(decision, recommendations)
        return decision


class MockIntentClient:
    """Deterministic plumbing check. Its scores are not an eval result."""

    model = "mock-intent"
    cache_identity = "mock:local:mock-intent"

    def decide(self, payload: dict[str, object], *, seed: int) -> IntentDecision:
        del seed
        recommendations = payload["recommendations"]
        shopper = payload["shopper_context"]
        assert isinstance(recommendations, list) and isinstance(shopper, dict)
        if not recommendations:
            return IntentDecision(
                UserAction.IGNORE, None, "no", False, 1.0, "insufficient_information"
            )
        top_categories = {item["category"] for item in shopper["top_categories"]}
        scored: list[tuple[float, int]] = []
        for index, card in enumerate(recommendations):
            assert isinstance(card, dict)
            overlap = len(top_categories & set(card["ingredient_categories"]))
            score = (
                1.2 * overlap
                - 0.35 * float(card["missing_count"])
                - float(card["missing_cost_rub"]) / 500.0
                - float(card["prep_minutes"] or 0) / 120.0
            )
            scored.append((score, index))
        best_score, selected = max(scored, key=lambda value: (value[0], -value[1]))
        best = recommendations[selected]
        if best_score >= 0.8 and best["missing_count"] <= 4:
            return IntentDecision(UserAction.BUY, selected, "yes", True, 0.7, "taste_match")
        if best_score >= 0.2:
            return IntentDecision(
                UserAction.SAVE, selected, "maybe", True, 0.65, "new_recipe_interest"
            )
        return IntentDecision(UserAction.IGNORE, None, "no", False, 0.65, "poor_history_fit")


@dataclass(frozen=True)
class IntentCase:
    case_id: str
    persona_id: str
    archetype: str
    arm: str
    recipe_ids: tuple[str, ...]
    payload: dict[str, object]


@dataclass(frozen=True)
class IntentStudy:
    cases: tuple[IntentCase, ...]
    panel_name: str
    panel_profiles_checksum: str
    #: Separate from panel_profiles_checksum on purpose: the inventory
    #: generator changed (docs/research/recsys/llm-intent-eval.md §11.1) while
    #: personas did not, so profiles_checksum alone would make two reports
    #: look identically-sourced when only the shelf each persona faced
    #: actually differed.
    panel_inventories_checksum: str
    catalog_hash: str
    ranking_policy: str
    world: str
    top_k: int
    seed: int
    #: Set only for the production world: the engine trains on the frozen
    #: 37-recipe baseline (``recsys.model.MLRecommendationEngine`` default,
    #: matching ``app/main.py``) while requests serve the live 47-recipe
    #: catalog (``catalog_hash``, ``recsys.recipes.RECIPES``) — the same split
    #: ``scripts/serving_review_pack.py`` records as
    #: ``training_catalog_hash``/``serving_catalog_hash``. ``None`` in the
    #: experimental world, which trains and serves the same frozen catalog.
    training_catalog_hash: str | None = None
    #: "default" (shipped) or "ingredient_idf" (opt-in hypothesis, production
    #: world only — see recsys.model.ingredient_idf).
    model_variant: str = "default"
    #: Neighbors blended into the `similar` arm (see _knn_neighbors). 1 was
    #: the original single-look-alike design; a k-NN blend is the product
    #: hypothesis proposed after v3.1 (docs/research/recsys/llm-intent-eval.md).
    similar_k: int = 1
    #: "category" (shipped v3.2/v3.3: cosine over 7-category purchase share)
    #: or "cf" (NMF-learned user embeddings over ~90 ingredients — see
    #: _cf_user_vectors). Untested hypothesis proposed after the k-NN blend
    #: win: a properly-learned taste embedding instead of a hand-picked
    #: 7-dimensional vector, the direct analogue of Spotify/Yandex Music's
    #: collaborative filtering.
    similar_method: str = "category"

    @property
    def persona_ids(self) -> tuple[str, ...]:
        return tuple(sorted({case.persona_id for case in self.cases}))


def _deranged_partners(profiles: list[SyntheticProfile], *, seed: int) -> list[SyntheticProfile]:
    """Sattolo cycle: deterministic and with no fixed point for n > 1."""
    partners = list(profiles)
    rng = random.Random(stable_seed("llm_intent_partners", seed))
    for index in range(len(partners) - 1, 0, -1):
        swap = rng.randrange(index)
        partners[index], partners[swap] = partners[swap], partners[index]
    return partners


def _category_share_vector(profile: SyntheticProfile) -> dict[str, float]:
    """Same category-share computation as ``compute_user_stats``, but directly
    on a ``SyntheticProfile`` — no ``RecommendationRequest``/world needed, so
    it can be computed once and reused for both worlds' "similar" arm."""
    receipts = list(profile.purchase_history) or [profile.current_receipt]
    items = [item for receipt in receipts for item in receipt.items]
    n_items = len(items) or 1
    counts: dict[str, int] = {}
    for item in items:
        counts[item.category] = counts.get(item.category, 0) + 1
    return {category: count / n_items for category, count in counts.items()}


def _cosine_similarity(a: dict[str, float], b: dict[str, float]) -> float:
    keys = set(a) | set(b)
    dot = sum(a.get(k, 0.0) * b.get(k, 0.0) for k in keys)
    norm_a = sum(v * v for v in a.values()) ** 0.5
    norm_b = sum(v * v for v in b.values()) ** 0.5
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


def _knn_neighbors_from_vectors(
    targets: list[SyntheticProfile],
    pool: list[SyntheticProfile],
    *,
    k: int,
    vectors: dict[str, dict[str, float]],
) -> dict[str, list[SyntheticProfile]]:
    """For each of ``targets``, the ``k`` most similar *other* profiles in
    ``pool`` by cosine similarity over a precomputed per-user vector —
    "shoppers like you", blended, as opposed to ``shuffled``'s single
    uniformly-random partner or a single 1-nearest-neighbor look-alike (noisy:
    one neighbor's idiosyncratic history is not obviously more representative
    than the target's own).

    ``pool`` should be the full panel, not just the sampled ``targets``, so a
    small ``--personas`` run still gets a meaningful neighborhood to search.
    Ties broken by (score desc, user_id asc) for determinism.
    """
    if k < 1:
        raise ValueError("k must be >= 1")
    by_id = {profile.user.user_id: profile for profile in pool}
    neighbors: dict[str, list[SyntheticProfile]] = {}
    for profile in targets:
        own_id = profile.user.user_id
        own_vector = vectors[own_id]
        scored = sorted(
            (
                (-_cosine_similarity(own_vector, candidate_vector), candidate_id)
                for candidate_id, candidate_vector in vectors.items()
                if candidate_id != own_id
            )
        )
        neighbors[own_id] = [by_id[candidate_id] for _, candidate_id in scored[:k]]
    return neighbors


def _knn_neighbors(
    targets: list[SyntheticProfile], pool: list[SyntheticProfile], *, k: int
) -> dict[str, list[SyntheticProfile]]:
    """Baseline "similar": cosine similarity over 7-category purchase share —
    a hand-picked, coarse vector. See ``_cf_knn_neighbors`` for the learned
    alternative.
    """
    vectors = {profile.user.user_id: _category_share_vector(profile) for profile in pool}
    return _knn_neighbors_from_vectors(targets, pool, k=k, vectors=vectors)


def _ingredient_count_vector(profile: SyntheticProfile) -> dict[str, float]:
    """Implicit-feedback counts per ingredient — the item space collaborative
    filtering factors over, analogous to a listener's per-track play counts."""
    counts: dict[str, float] = {}
    for receipt in profile.purchase_history:
        for item in receipt.items:
            for ingredient_id in item.ingredient_ids:
                counts[ingredient_id] = counts.get(ingredient_id, 0.0) + item.quantity
    return counts


def _cf_user_vectors(
    pool: list[SyntheticProfile], *, n_factors: int = 16, seed: int = 0
) -> dict[str, dict[str, float]]:
    """Collaborative-filtering user embeddings via NMF on the user x
    ingredient implicit-count matrix — the learned analogue of a Spotify-style
    latent taste vector, in place of ``_category_share_vector``'s hand-picked
    7-category share. Ingredients (~90) are a far richer item space than the
    7 broad categories the baseline "similar" compares on, and the factors
    are fit from co-purchase structure across the whole panel rather than
    read off one user's marginal frequencies.

    Requires the optional ``ml`` extra (numpy + scikit-learn; see
    pyproject.toml's ``[project.optional-dependencies]``) — the default
    ("category") method stays dependency-free.
    """
    if not SKLEARN_AVAILABLE:
        raise RuntimeError(
            "--similar-method cf needs numpy + scikit-learn: "
            "pip install -e '.[ml]'"
        )

    ingredient_counts = [_ingredient_count_vector(profile) for profile in pool]
    ingredient_ids = sorted({ingredient_id for counts in ingredient_counts for ingredient_id in counts})
    if not ingredient_ids:
        return {profile.user.user_id: {} for profile in pool}
    index = {ingredient_id: position for position, ingredient_id in enumerate(ingredient_ids)}
    matrix = _np.zeros((len(pool), len(ingredient_ids)))
    for row, counts in enumerate(ingredient_counts):
        for ingredient_id, count in counts.items():
            matrix[row, index[ingredient_id]] = count

    n_components = max(1, min(n_factors, len(pool) - 1, len(ingredient_ids)))
    model = _NMF(n_components=n_components, init="nndsvda", random_state=seed, max_iter=500)
    user_factors = model.fit_transform(matrix)
    return {
        profile.user.user_id: {f"f{i}": float(value) for i, value in enumerate(user_factors[row])}
        for row, profile in enumerate(pool)
    }


def _cf_knn_neighbors(
    targets: list[SyntheticProfile],
    pool: list[SyntheticProfile],
    *,
    k: int,
    n_factors: int = 16,
    seed: int = 0,
) -> dict[str, list[SyntheticProfile]]:
    """"similar", with neighbors found in a learned NMF taste-embedding space
    instead of the raw 7-category share vector. See ``_cf_user_vectors``."""
    vectors = _cf_user_vectors(pool, n_factors=n_factors, seed=seed)
    return _knn_neighbors_from_vectors(targets, pool, k=k, vectors=vectors)


SIMILAR_METHODS = ("category", "cf")


def _select_neighbors(
    similar_method: str,
    profiles: list[SyntheticProfile],
    pool: list[SyntheticProfile],
    *,
    k: int,
    seed: int,
) -> dict[str, list[SyntheticProfile]]:
    if similar_method == "cf":
        return _cf_knn_neighbors(profiles, pool, k=k, seed=seed)
    if similar_method == "category":
        return _knn_neighbors(profiles, pool, k=k)
    raise ValueError(f"unknown similar_method {similar_method!r}, expected one of {SIMILAR_METHODS}")


def _blend_neighbor_history(neighbors: list[SyntheticProfile]) -> tuple[list, list[str], list[str], set[str]]:
    """Combine k neighbors' history-derived fields into one pseudo-history:
    concatenated receipts (so category-share/basket-size/cadence stats
    reflect the whole neighborhood, not one person), union of history
    categories, brands and saved recipes. Order is stable (by user_id) so the
    result is deterministic regardless of neighbor list order.
    """
    ordered = sorted(neighbors, key=lambda profile: profile.user.user_id)
    purchase_history = [receipt for profile in ordered for receipt in profile.purchase_history]
    history_categories = sorted({c for profile in ordered for c in profile.user.history_categories})
    preferred_brands = sorted({b for profile in ordered for b in profile.user.preferred_brands})
    saved_recipe_ids = {rid for profile in ordered for rid in profile.user.saved_recipe_ids}
    return purchase_history, history_categories, preferred_brands, saved_recipe_ids


def _selected_pairs(panel: Panel, max_personas: int | None, *, seed: int):
    pairs = panel.pairs()
    if max_personas is None or max_personas >= len(pairs):
        return pairs
    if max_personas <= 0:
        return []
    by_archetype: dict[str, list[tuple[SyntheticProfile, list]]] = defaultdict(list)
    for pair in pairs:
        by_archetype[pair[0].archetype].append(pair)
    rng = random.Random(stable_seed("llm_intent_personas", seed))
    for group in by_archetype.values():
        group.sort(key=lambda pair: pair[0].user.user_id)
        rng.shuffle(group)
    selected = []
    names = sorted(by_archetype)
    while len(selected) < max_personas and any(by_archetype.values()):
        for name in names:
            if by_archetype[name] and len(selected) < max_personas:
                selected.append(by_archetype[name].pop())
    return selected


def _case_id(persona_id: str, arm: str, recipe_ids: tuple[str, ...]) -> str:
    material = "|".join((persona_id, arm, *recipe_ids))
    return "intent_" + hashlib.sha256(material.encode()).hexdigest()[:12]


def _aware(dt):
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


# --- experimental-world case construction (model_order diagnostic) ---------


def _shuffled_user_experimental(own: ExpUserProfile, partner: ExpUserProfile) -> ExpUserProfile:
    return ExpUserProfile(
        user_id=own.user_id,
        radius_km=own.radius_km,
        excluded_categories=own.excluded_categories,
        excluded_ingredient_ids=own.excluded_ingredient_ids,
        saved_recipe_ids=partner.saved_recipe_ids,
        history_categories=partner.history_categories,
        preferred_brands=partner.preferred_brands,
    )


def _blended_user_experimental(
    own: ExpUserProfile, *, history_categories: list[str], preferred_brands: list[str], saved_recipe_ids: set[str]
) -> ExpUserProfile:
    return ExpUserProfile(
        user_id=own.user_id,
        radius_km=own.radius_km,
        excluded_categories=own.excluded_categories,
        excluded_ingredient_ids=own.excluded_ingredient_ids,
        saved_recipe_ids=saved_recipe_ids,
        history_categories=history_categories,
        preferred_brands=preferred_brands,
    )


def _exp_request(profile, *, user, purchase_history, catalog, inventory, meals, top_k):
    return ExpRecommendationRequest(
        user=user,
        current_receipt=profile.current_receipt,
        purchase_history=purchase_history,
        recipe_catalog=catalog,
        inventory_snapshot=inventory,
        ready_meal_options=meals,
        now=profile.now,
        limit=top_k,
    )


def _shopper_payload_experimental(profile, own_request, recipe_lookup) -> dict[str, object]:
    stats = exp_compute_user_stats(own_request)
    return _shopper_payload_common(profile, stats, recipe_lookup)


def _shopper_payload_common(profile, stats, recipe_lookup) -> dict[str, object]:
    top_categories = sorted(stats.category_share.items(), key=lambda item: (-item[1], item[0]))[:5]
    recent = sorted(profile.purchase_history, key=lambda receipt: receipt.purchased_at, reverse=True)[:3]
    return {
        "today_basket": sorted({item.name for item in profile.current_receipt.items}),
        "top_categories": [
            {"category": category, "share": round(share, 3)}
            for category, share in top_categories
            if share > 0
        ],
        "mean_basket_items": round(stats.mean_basket_size, 1),
        "visit_cadence_days": round(stats.mean_cadence_days, 1),
        "markdown_share": round(stats.markdown_share, 3),
        "preferred_brands": sorted(profile.user.preferred_brands),
        "saved_recipes": sorted(
            recipe_lookup[recipe_id].title
            for recipe_id in profile.user.saved_recipe_ids
            if recipe_id in recipe_lookup
        ),
        "recent_baskets": [sorted({item.name for item in receipt.items}) for receipt in recent],
    }


def _recommendation_payload_experimental(served: ExpRecipeRecommendation, recipe) -> dict[str, object]:
    already_have: list[str] = []
    to_buy: list[dict[str, object]] = []
    for ingredient in served.ingredients:
        if ingredient.source in (ExpIngredientSource.RECEIPT, ExpIngredientSource.PANTRY_LIKELY):
            already_have.append(ingredient.name)
            continue
        if not ingredient.product_options:
            continue
        cheapest = min(ingredient.product_options, key=lambda option: option.price)
        to_buy.append(
            {
                "name": ingredient.name,
                "price_rub": round(cheapest.price),
                "markdown": ingredient.source == ExpIngredientSource.MARKDOWN,
            }
        )
    ready = served.ready_meal_alternative
    return {
        "title": served.title,
        "dish_type": recipe.dish_type,
        "cuisine": recipe.cuisine,
        "prep_minutes": recipe.preparation_minutes,
        "servings": recipe.servings,
        "ingredient_categories": sorted({item.category for item in recipe.ingredients}),
        "already_have": sorted(already_have),
        "to_buy": to_buy,
        "missing_count": served.missing_count,
        "missing_cost_rub": round(sum(float(item["price_rub"]) for item in to_buy)),
        "ready_meal_alternative": None if ready is None else {"name": ready.name, "price_rub": ready.price},
        # Always true in this world: recsys.experimental never assembles a
        # candidate without a cook path (see recsys/experimental/service.py).
        "cookable": True,
    }


def _build_experimental_study(
    panel: Panel, *, top_k: int, seed: int, max_personas: int | None,
    similar_k: int = 1, similar_method: str = "category",
) -> IntentStudy:
    catalog = exp_baseline_catalog()
    recipe_lookup = {recipe.recipe_id: recipe for recipe in catalog}
    meals = ready_meal_options(recipe_lookup)
    model = ExpMLRecommendationEngine(recipe_catalog=catalog)
    ranked_service = ExpRecommendationService(
        engine=model, safety_policy=ExpSafetyPolicy(), ranking_policy=MODEL_ORDER
    )
    random_service = ExpRecommendationService(
        engine=ExpRandomEngine(seed=seed), safety_policy=ExpSafetyPolicy(), ranking_policy=MODEL_ORDER
    )

    selected = _selected_pairs(panel, max_personas, seed=seed)
    profiles = [profile for profile, _ in selected]
    partners = _deranged_partners(profiles, seed=seed)
    neighbors = _select_neighbors(similar_method, profiles, panel.profiles, k=similar_k, seed=seed)
    cases: list[IntentCase] = []
    for (profile, inventory), partner in zip(selected, partners, strict=True):
        neighbor_history, neighbor_categories, neighbor_brands, neighbor_saved = _blend_neighbor_history(
            neighbors[profile.user.user_id]
        )
        own = _exp_request(
            profile, user=profile.user, purchase_history=profile.purchase_history,
            catalog=catalog, inventory=inventory, meals=meals, top_k=top_k,
        )
        shuffled = _exp_request(
            profile,
            user=_shuffled_user_experimental(profile.user, partner.user),
            purchase_history=partner.purchase_history,
            catalog=catalog, inventory=inventory, meals=meals, top_k=top_k,
        )
        similar = _exp_request(
            profile,
            user=_blended_user_experimental(
                profile.user, history_categories=neighbor_categories,
                preferred_brands=neighbor_brands, saved_recipe_ids=neighbor_saved,
            ),
            purchase_history=neighbor_history,
            catalog=catalog, inventory=inventory, meals=meals, top_k=top_k,
        )
        shopper = _shopper_payload_experimental(profile, own, recipe_lookup)
        arm_requests = {
            ARM_OWN: (ranked_service, own),
            ARM_SHUFFLED: (ranked_service, shuffled),
            ARM_RANDOM: (random_service, own),
            ARM_SIMILAR: (ranked_service, similar),
        }
        for arm, (service, request) in arm_requests.items():
            served = service.recommend(request).recommendations
            recipe_ids = tuple(card.recipe_id for card in served)
            payload = {
                "shopper_context": shopper,
                "recommendations": [
                    _recommendation_payload_experimental(card, recipe_lookup[card.recipe_id])
                    for card in served
                ],
            }
            cases.append(
                IntentCase(
                    case_id=_case_id(profile.user.user_id, arm, recipe_ids),
                    persona_id=profile.user.user_id,
                    archetype=profile.archetype,
                    arm=arm,
                    recipe_ids=recipe_ids,
                    payload=payload,
                )
            )
    return IntentStudy(
        cases=tuple(cases),
        panel_name=panel.manifest.spec.name,
        panel_profiles_checksum=panel.manifest.profiles_checksum,
        panel_inventories_checksum=panel.manifest.inventories_checksum,
        catalog_hash=exp_recipe_content_hash(catalog),
        ranking_policy=MODEL_ORDER.name,
        world="experimental",
        top_k=top_k,
        seed=seed,
        similar_k=similar_k,
        similar_method=similar_method,
    )


# --- production-world case construction (real app.service.recommend_meals) -


def _bridge_receipt_item(item) -> AppReceiptItem:
    return AppReceiptItem(
        sku_id=item.sku_id,
        name=item.name,
        category=item.category,
        ingredient_ids=set(item.ingredient_ids),
        brand=item.brand,
        quantity=item.quantity,
        unit_price=item.unit_price,
        is_markdown=item.is_markdown,
        is_prepared_food=False,
        original_unit_price=item.original_unit_price,
    )


def _bridge_receipt(receipt) -> AppReceipt:
    return AppReceipt(
        receipt_id=receipt.receipt_id,
        purchased_at=_aware(receipt.purchased_at),
        store_id=receipt.store_id,
        items=[_bridge_receipt_item(item) for item in receipt.items],
    )


def _bridge_user(user: ExpUserProfile) -> AppUserProfile:
    return AppUserProfile(
        user_id=user.user_id,
        radius_km=user.radius_km,
        excluded_categories=set(user.excluded_categories),
        excluded_ingredient_ids=set(user.excluded_ingredient_ids),
        saved_recipe_ids=set(user.saved_recipe_ids),
        history_categories=list(user.history_categories),
        preferred_brands=list(user.preferred_brands),
    )


def _shuffled_user_production(own: ExpUserProfile, partner: ExpUserProfile) -> AppUserProfile:
    return AppUserProfile(
        user_id=own.user_id,
        radius_km=own.radius_km,
        excluded_categories=set(own.excluded_categories),
        excluded_ingredient_ids=set(own.excluded_ingredient_ids),
        saved_recipe_ids=set(partner.saved_recipe_ids),
        history_categories=list(partner.history_categories),
        preferred_brands=list(partner.preferred_brands),
    )


def _blended_user_production(
    own: ExpUserProfile, *, history_categories: list[str], preferred_brands: list[str], saved_recipe_ids: set[str]
) -> AppUserProfile:
    return AppUserProfile(
        user_id=own.user_id,
        radius_km=own.radius_km,
        excluded_categories=set(own.excluded_categories),
        excluded_ingredient_ids=set(own.excluded_ingredient_ids),
        saved_recipe_ids=set(saved_recipe_ids),
        history_categories=list(history_categories),
        preferred_brands=list(preferred_brands),
    )


def _bridge_inventory_product(product) -> AppInventoryProduct:
    return AppInventoryProduct(
        sku_id=product.sku_id,
        name=product.name,
        category=product.category,
        ingredient_ids=set(product.ingredient_ids),
        store_id=product.store_id,
        distance_km=product.distance_km,
        price=product.price,
        original_price=product.original_price,
        brand=product.brand,
        is_markdown=product.is_markdown,
        is_prepared_food=False,
        safety_eligible=product.safety_eligible,
        expires_at=None if product.expires_at is None else _aware(product.expires_at),
        available_quantity=product.available_quantity,
        fulfillment_options={AppFulfillmentOption(option.value) for option in product.fulfillment_options},
    )


def _production_ready_templates(catalog: list[AppRecipe]) -> list[AppInventoryProduct]:
    """Synthetic prepared-food inventory so ``recommend_meals`` can offer a
    ready route at all. Production ``RecommendationRequest`` has no
    ``ready_meal_options`` field: a ready route is discovered from
    prepared-food ``InventoryProduct`` entries whose ``meal_intent_ids``
    match ``recipe.meal_intent_id or recipe.recipe_id`` (``app/safety.py``).
    Grounded in the same curated pair table as the experimental world
    (``recsys.ready_food_pairs``), not invented prices; the placement
    (store, distance) is synthetic and documented, not observed.
    """
    recipe_lookup = {recipe.recipe_id: recipe for recipe in catalog}
    templates: list[AppInventoryProduct] = []
    for option in ready_meal_options([recipe.recipe_id for recipe in catalog]):
        if option.price is None:
            continue
        recipe_ids = sorted(rid for rid in option.recipe_ids if rid in recipe_lookup)
        if not recipe_ids:
            continue
        contained_categories = {
            ingredient.category
            for recipe_id in recipe_ids
            for ingredient in recipe_lookup[recipe_id].ingredients
        }
        if not contained_categories:
            continue
        templates.append(
            AppInventoryProduct(
                sku_id=f"ready_{option.chain}_{option.plu}",
                name=option.name,
                category="ready_meal",
                store_id=READY_MEAL_STORE_ID,
                distance_km=READY_MEAL_DISTANCE_KM,
                price=option.price,
                is_markdown=False,
                is_prepared_food=True,
                meal_intent_ids=set(recipe_ids),
                contained_categories=contained_categories,
                safety_eligible=True,
                available_quantity=1,
            )
        )
    return templates


def _placed_ready_products(templates: list[AppInventoryProduct], *, store_id: str) -> list[AppInventoryProduct]:
    return [template.model_copy(update={"store_id": store_id}) for template in templates]


class _ProductionRandomEngine:
    """Negative control for the production world: ranks by coin flip.

    Mirrors ``recsys.benchmark.RandomEngine`` exactly (same seeding scheme),
    typed against ``app.contracts`` because ``RandomEngine`` itself is typed
    against ``recsys.experimental.contracts`` and the two are not
    interchangeable pydantic models.
    """

    def __init__(self, seed: int = 0) -> None:
        self._seed = seed

    def rank(self, request: AppRecommendationRequest) -> list[AppModelRecommendation]:
        rng = random.Random(stable_seed(self._seed, request.current_receipt.receipt_id))
        ranked = [
            AppModelRecommendation(
                recipe_id=recipe.recipe_id,
                mode=AppRecommendationMode.EXPLORE,
                score=round(rng.random(), 4),
                reason_codes=["personalized_discovery"],
            )
            for recipe in request.recipe_catalog
            if recipe.verified
        ]
        return sorted(ranked, key=lambda item: (-item.score, item.recipe_id))


def _app_request(profile, *, user, purchase_history, catalog, inventory, top_k) -> AppRecommendationRequest:
    return AppRecommendationRequest(
        user=user,
        current_receipt=_bridge_receipt(profile.current_receipt),
        purchase_history=[_bridge_receipt(receipt) for receipt in purchase_history],
        recipe_catalog=catalog,
        inventory_snapshot=inventory,
        now=_aware(profile.now),
        limit=top_k,
    )


def _shopper_payload_production(profile, own_request, recipe_lookup) -> dict[str, object]:
    stats = app_compute_user_stats(own_request)
    return _shopper_payload_common(profile, stats, recipe_lookup)


def _recommendation_payload_production(meal, recipe_lookup) -> dict[str, object]:
    cook = meal.cook_variant
    ready = meal.ready_variant
    already_have: list[str] = []
    to_buy: list[dict[str, object]] = []
    ingredient_categories: list[str] = []
    missing_count = 0
    prep_minutes = None
    if cook is not None:
        prep_minutes = cook.preparation_minutes
        ingredient_categories = sorted({item.category for item in cook.ingredients})
        missing_count = cook.missing_count
        for ingredient in cook.ingredients:
            if ingredient.source in (AppIngredientSource.RECEIPT, AppIngredientSource.HOME):
                already_have.append(ingredient.name)
                continue
            if not ingredient.product_options:
                continue
            cheapest = min(ingredient.product_options, key=lambda option: option.price)
            to_buy.append(
                {
                    "name": ingredient.name,
                    "price_rub": round(cheapest.price),
                    "markdown": ingredient.source == AppIngredientSource.MARKDOWN,
                }
            )
    elif meal.meal_id in recipe_lookup:
        ingredient_categories = sorted({item.category for item in recipe_lookup[meal.meal_id].ingredients})

    ready_meal_alternative = None
    if ready is not None and ready.product_options:
        cheapest = min(ready.product_options, key=lambda option: option.price)
        ready_meal_alternative = {"name": cheapest.name, "price_rub": round(cheapest.price)}

    return {
        "title": meal.title,
        "dish_type": None,
        "cuisine": None,
        "prep_minutes": prep_minutes,
        "servings": None,
        "ingredient_categories": ingredient_categories,
        "already_have": sorted(already_have),
        "to_buy": to_buy,
        "missing_count": missing_count,
        "missing_cost_rub": round(sum(float(item["price_rub"]) for item in to_buy)),
        "ready_meal_alternative": ready_meal_alternative,
        # False for a ready-only meal (app.service found no safe cook path
        # and only offers the prepared alternative): "buy and cook within 7
        # days" is not an option this card can actually deliver.
        "cookable": cook is not None,
    }


def _build_production_study(
    panel: Panel, *, top_k: int, seed: int, max_personas: int | None,
    model_variant: str = "default", similar_k: int = 1, similar_method: str = "category",
) -> IntentStudy:
    # Same split app/main.py's default construction produces: MLRecommendationEngine()
    # with no recipe_catalog argument trains on the frozen 37-recipe baseline
    # (recsys.model.MLRecommendationEngine's own default), but a request can
    # carry any catalog for the engine to *score* — the live app is served the
    # full 47-recipe catalog (recsys.recipes.RECIPES), not the training set.
    # scripts/serving_review_pack.py (docs/eval/serving-40-seed606) records
    # both hashes for exactly this reason; conflating the two here would test
    # production code against a catalog no real user is actually shown today.
    catalog = list(APP_SERVING_CATALOG)
    recipe_lookup = {recipe.recipe_id: recipe for recipe in catalog}
    ready_templates = _production_ready_templates(catalog)
    # "ingredient_idf" is the untested hypothesis from
    # docs/research/recsys/llm-intent-eval.md §10: down-weight ingredients
    # common across the whole catalog (salt, onion, egg...) in
    # ingredient_affinity, so matching on them stops reading as taste-specific
    # personalization. "content_affinity" (§12.2) adds a content-based
    # feature scored against the user's *saved* recipes, independent of
    # purchase history. Both opt-in, off by default
    # (recsys.model.MLRecommendationEngine).
    model = AppMLRecommendationEngine(
        use_ingredient_idf=model_variant == "ingredient_idf",
        use_content_affinity=model_variant == "content_affinity",
    )
    ranked_service = AppRecommendationService(engine=model, safety_policy=AppSafetyPolicy())
    random_service = AppRecommendationService(
        engine=_ProductionRandomEngine(seed=seed), safety_policy=AppSafetyPolicy()
    )

    selected = _selected_pairs(panel, max_personas, seed=seed)
    profiles = [profile for profile, _ in selected]
    partners = _deranged_partners(profiles, seed=seed)
    neighbors = _select_neighbors(similar_method, profiles, panel.profiles, k=similar_k, seed=seed)
    cases: list[IntentCase] = []
    for (profile, inventory), partner in zip(selected, partners, strict=True):
        neighbor_history, neighbor_categories, neighbor_brands, neighbor_saved = _blend_neighbor_history(
            neighbors[profile.user.user_id]
        )
        bridged_inventory = [_bridge_inventory_product(product) for product in inventory]
        ready_products = _placed_ready_products(
            ready_templates, store_id=profile.current_receipt.store_id
        )
        full_inventory = bridged_inventory + ready_products

        own = _app_request(
            profile, user=_bridge_user(profile.user), purchase_history=profile.purchase_history,
            catalog=catalog, inventory=full_inventory, top_k=top_k,
        )
        shuffled = _app_request(
            profile,
            user=_shuffled_user_production(profile.user, partner.user),
            purchase_history=partner.purchase_history,
            catalog=catalog, inventory=full_inventory, top_k=top_k,
        )
        similar = _app_request(
            profile,
            user=_blended_user_production(
                profile.user, history_categories=neighbor_categories,
                preferred_brands=neighbor_brands, saved_recipe_ids=neighbor_saved,
            ),
            purchase_history=neighbor_history,
            catalog=catalog, inventory=full_inventory, top_k=top_k,
        )
        shopper = _shopper_payload_production(profile, own, recipe_lookup)
        arm_requests = {
            ARM_OWN: (ranked_service, own),
            ARM_SHUFFLED: (ranked_service, shuffled),
            ARM_RANDOM: (random_service, own),
            ARM_SIMILAR: (ranked_service, similar),
        }
        for arm, (service, request) in arm_requests.items():
            served = service.recommend_meals(request).recommendations
            recipe_ids = tuple(meal.meal_id for meal in served)
            payload = {
                "shopper_context": shopper,
                "recommendations": [
                    _recommendation_payload_production(meal, recipe_lookup) for meal in served
                ],
            }
            cases.append(
                IntentCase(
                    case_id=_case_id(profile.user.user_id, arm, recipe_ids),
                    persona_id=profile.user.user_id,
                    archetype=profile.archetype,
                    arm=arm,
                    recipe_ids=recipe_ids,
                    payload=payload,
                )
            )
    return IntentStudy(
        cases=tuple(cases),
        panel_name=panel.manifest.spec.name,
        panel_profiles_checksum=panel.manifest.profiles_checksum,
        panel_inventories_checksum=panel.manifest.inventories_checksum,
        catalog_hash=app_recipe_content_hash(catalog),
        training_catalog_hash=model.training_catalog_hash,
        model_variant=model_variant,
        ranking_policy="effort_first",
        world="production",
        top_k=top_k,
        seed=seed,
        similar_k=similar_k,
        similar_method=similar_method,
    )


def build_study(
    panel: Panel, *, ranking_policy: str, top_k: int = 3, seed: int = 20260906,
    max_personas: int | None = None, model_variant: str = "default",
    similar_k: int = 1, similar_method: str = "category",
) -> IntentStudy:
    world = RANKING_POLICY_WORLD[ranking_policy]
    if world == "production":
        return _build_production_study(
            panel, top_k=top_k, seed=seed, max_personas=max_personas,
            model_variant=model_variant, similar_k=similar_k, similar_method=similar_method,
        )
    if model_variant != "default":
        raise ValueError("model_variant is only wired up for the production world so far")
    return _build_experimental_study(
        panel, top_k=top_k, seed=seed, max_personas=max_personas,
        similar_k=similar_k, similar_method=similar_method,
    )


# --- caching, execution, analysis (world-agnostic) --------------------------


class IntentCache:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.data: dict[str, dict[str, object]] = (
            json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        )

    def get(self, key: str, *, recommendation_count: int) -> IntentDecision | None:
        raw = self.data.get(key)
        return None if raw is None else parse_intent_decision(raw, recommendation_count=recommendation_count)

    def put(self, key: str, decision: IntentDecision) -> None:
        self.data[key] = decision.to_json()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def intent_cache_key(payload: dict[str, object], *, client_identity: str, prompt_version: str, replicate: int) -> str:
    material = json.dumps(
        {"client": client_identity, "prompt_version": prompt_version, "replicate": replicate, "payload": payload},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )
    return hashlib.sha256(material.encode()).hexdigest()


def _token_estimate(payload: dict[str, object]) -> tuple[int, int]:
    input_chars = len(SYSTEM_PROMPT) + len(json.dumps(payload, ensure_ascii=False))
    return max(1, (input_chars + 3) // 4), 70


def run_study(
    study: IntentStudy,
    client: IntentClient,
    cache: IntentCache,
    *,
    live: bool,
    replicates: int = 1,
    prompt_version: str = PROMPT_VERSION,
) -> tuple[list[dict[str, object]], dict[str, int]]:
    if replicates < 1:
        raise ValueError("replicates must be >= 1")
    rows: list[dict[str, object]] = []
    local: dict[str, IntentDecision] = {}
    calls = hits = input_tokens = output_tokens = 0
    for case in study.cases:
        for replicate in range(replicates):
            key = intent_cache_key(
                case.payload, client_identity=client.cache_identity, prompt_version=prompt_version, replicate=replicate
            )
            decision = local.get(key)
            if decision is None:
                decision = cache.get(key, recommendation_count=len(case.recipe_ids))
                if decision is not None:
                    hits += 1
                else:
                    estimated_in, estimated_out = _token_estimate(case.payload)
                    input_tokens += estimated_in
                    output_tokens += estimated_out
                    calls += 1
                    call_seed = stable_seed("llm_intent", key)
                    decision = _with_retries(lambda: client.decide(case.payload, seed=call_seed))
                    if live:
                        cache.put(key, decision)
                        # Flushed after every live call, not once at the end: a
                        # crash partway through a long run (a slow model
                        # blowing the read timeout, a network blip _with_retries
                        # gave up on) must not discard every already-paid-for
                        # response made before it.
                        cache.save()
                local[key] = decision
            selected_recipe_id = (
                None if decision.selected_recipe_index is None else case.recipe_ids[decision.selected_recipe_index]
            )
            rows.append(
                {
                    "case_id": case.case_id,
                    "persona_id": case.persona_id,
                    "archetype": case.archetype,
                    "arm": case.arm,
                    "replicate": replicate,
                    "recipe_ids": list(case.recipe_ids),
                    "selected_recipe_id": selected_recipe_id,
                    # Card-level attributes for the shown feed, so a later pass
                    # can test "does buy track effort/price?" without rebuilding
                    # the study from the seed.
                    "recommendations": case.payload["recommendations"],
                    **decision.to_json(),
                }
            )
    if live:
        cache.save()
    return rows, {
        "planned_or_executed_calls": calls,
        "cache_hits": hits,
        "estimated_input_tokens": input_tokens,
        "estimated_output_tokens": output_tokens,
        "estimated_total_tokens": input_tokens + output_tokens,
    }


def _bootstrap_delta(
    deltas_by_persona: dict[str, float], *, iterations: int = 4000, seed: int = 20260906
) -> tuple[float, float, float]:
    if not deltas_by_persona:
        return 0.0, 0.0, 0.0
    values = list(deltas_by_persona.values())
    point = statistics.mean(values)
    if len(values) == 1:
        return point, point, point
    rng = random.Random(seed)
    samples = sorted(statistics.mean(rng.choice(values) for _ in values) for _ in range(iterations))
    return point, samples[int(0.025 * len(samples))], samples[min(int(0.975 * len(samples)), len(samples) - 1)]


def analyse_study(study: IntentStudy, rows: list[dict[str, object]]) -> dict[str, object]:
    by_persona_arm: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        by_persona_arm[(str(row["persona_id"]), str(row["arm"]))].append(row)

    def mean_flag(group: list[dict[str, object]], predicate) -> float:
        return statistics.mean(float(predicate(row)) for row in group) if group else 0.0

    metrics: dict[str, dict[str, float]] = {}
    primary_by_arm: dict[str, dict[str, float]] = {}
    for arm in ARMS:
        per_persona: dict[str, dict[str, float]] = {}
        for persona_id in study.persona_ids:
            group = by_persona_arm.get((persona_id, arm), [])
            if not group:
                continue
            per_persona[persona_id] = {
                "strict": mean_flag(group, lambda row: row["action"] == UserAction.BUY.value),
                "soft": mean_flag(group, lambda row: row["action"] in {UserAction.SAVE.value, UserAction.BUY.value}),
                "engaged": mean_flag(
                    group,
                    lambda row: row["action"] in {UserAction.CLICK.value, UserAction.SAVE.value, UserAction.BUY.value},
                ),
                "substitute": mean_flag(group, lambda row: row["action"] == UserAction.SUBSTITUTE.value),
                "cook_yes": mean_flag(group, lambda row: row["cook_within_7_days"] == "yes"),
                "topup": mean_flag(group, lambda row: bool(row["topup_acceptable"])),
            }
        primary_by_arm[arm] = {persona: values["strict"] for persona, values in per_persona.items()}
        metrics[arm] = {
            "n_personas": float(len(per_persona)),
            "strict_intent_rate": statistics.mean(v["strict"] for v in per_persona.values()) if per_persona else 0.0,
            "soft_intent_rate": statistics.mean(v["soft"] for v in per_persona.values()) if per_persona else 0.0,
            "recipe_engagement_rate": statistics.mean(v["engaged"] for v in per_persona.values()) if per_persona else 0.0,
            "substitute_rate": statistics.mean(v["substitute"] for v in per_persona.values()) if per_persona else 0.0,
            "cook_within_7_days_yes_rate": statistics.mean(v["cook_yes"] for v in per_persona.values()) if per_persona else 0.0,
            "topup_acceptance_rate": statistics.mean(v["topup"] for v in per_persona.values()) if per_persona else 0.0,
        }

    feeds = {(case.persona_id, case.arm): case.recipe_ids for case in study.cases}
    comparisons: dict[str, object] = {}
    for baseline in (ARM_SHUFFLED, ARM_RANDOM, ARM_SIMILAR):
        personas = sorted(set(primary_by_arm[ARM_OWN]) & set(primary_by_arm[baseline]))
        deltas = {persona: primary_by_arm[ARM_OWN][persona] - primary_by_arm[baseline][persona] for persona in personas}
        changed = {
            persona: delta
            for persona, delta in deltas.items()
            if feeds.get((persona, ARM_OWN)) != feeds.get((persona, baseline))
        }
        comparisons[f"own_minus_{baseline}"] = {
            "strict_intent_delta": _bootstrap_delta(deltas),
            "strict_intent_delta_changed_feeds": _bootstrap_delta(changed),
            "paired_personas": len(personas),
            "changed_feed_personas": len(changed),
            "changed_feed_rate": len(changed) / len(personas) if personas else 0.0,
        }

    own_random = comparisons["own_minus_random"]["strict_intent_delta"]
    own_shuffled = comparisons["own_minus_shuffled"]["strict_intent_delta"]
    own_similar = comparisons["own_minus_similar"]["strict_intent_delta"]
    warnings: list[str] = []
    if len(study.persona_ids) < 30:
        warnings.append("fewer than 30 personas: paired intervals will be wide")
    if comparisons["own_minus_shuffled"]["changed_feed_rate"] < 0.5:
        warnings.append("own and shuffled change fewer than half of feeds; the treatment is weak")
    if comparisons["own_minus_similar"]["changed_feed_rate"] < 0.5:
        warnings.append("own and similar change fewer than half of feeds; the treatment is weak")
    if own_random[1] <= 0:
        warnings.append("negative-control gate failed: own is not reliably above random")

    return {
        "primary_metric": "persona-level P(action=buy) for the shown top-k feed",
        "arms": metrics,
        "comparisons": comparisons,
        "gates": {
            "negative_control_passed": own_random[1] > 0,
            "personalization_detected": own_shuffled[1] > 0,
            "practical_personalization_gain_5pp": own_shuffled[0] >= 0.05,
            # similar (look-alike history) as an alternative to own literal
            # history: does ranking on peers who buy like you beat your own
            # history, the way shuffled (a random stranger) did in v3?
            "similar_beats_own": own_similar[2] < 0,
        },
        "warnings": warnings,
        "interpretation": (
            "LLM-simulated stated intent only; this is neither observed customer "
            "behaviour nor a causal conversion/uplift estimate."
        ),
    }


def _metadata(study: IntentStudy, client: IntentClient, *, live: bool, replicates: int) -> dict[str, object]:
    target = (
        "app.service.RecommendationService.recommend_meals (production, API 1.3)"
        if study.world == "production"
        else "recsys.experimental.service.RecommendationService (MODEL_ORDER diagnostic sandbox)"
    )
    return {
        "mode": "live" if live else "dry-run",
        "provider_model": client.cache_identity,
        "prompt_version": PROMPT_VERSION,
        "target": target,
        "world": study.world,
        "panel": study.panel_name,
        "panel_profiles_checksum": study.panel_profiles_checksum,
        "panel_inventories_checksum": study.panel_inventories_checksum,
        "catalog_hash": study.catalog_hash,
        "training_catalog_hash": study.training_catalog_hash,
        "ranking_policy": study.ranking_policy,
        "model_variant": study.model_variant,
        "similar_k": study.similar_k,
        "similar_method": study.similar_method,
        "top_k": study.top_k,
        "seed": study.seed,
        "personas": len(study.persona_ids),
        "replicates": replicates,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Blinded LLM-as-user intent eval")
    parser.add_argument("--live", action="store_true", help="Make paid network calls; default is local dry-run.")
    parser.add_argument(
        "--provider",
        choices=("deepseek", "openrouter", "openai", "opencode_go"),
        default="deepseek",
        help="opencode_go fronts many open-weight models behind one $10/mo key "
        "(GLM/Kimi/DeepSeek-V4/LongCat/MiMo/Hy3/Hy4/Omen only — see "
        "recsys.llm_audit.OPENCODE_GO_ENDPOINT); pick one with --model.",
    )
    parser.add_argument("--model", default=None)
    parser.add_argument("--endpoint", default=None, help="Override provider endpoint (advanced).")
    parser.add_argument("--personas", type=int, default=0, help="0 means every validation persona.")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument(
        "--ranking-policy",
        choices=tuple(RANKING_POLICY_WORLD),
        default="effort_first",
        help="effort_first hits the real app.service.recommend_meals (primary); "
        "model_order is a ranker-only diagnostic in recsys.experimental.",
    )
    parser.add_argument(
        "--model-variant",
        choices=("default", "ingredient_idf", "content_affinity"),
        default="default",
        help="ingredient_idf and content_affinity are untested hypotheses "
        "from docs/research/recsys/llm-intent-eval.md §10 and §12.2; "
        "production world only.",
    )
    parser.add_argument(
        "--similar-k",
        type=int,
        default=1,
        help="Neighbors blended into the `similar` arm's history (see "
        "recsys.llm_intent_eval._knn_neighbors). 1 is a single look-alike; "
        "5-10 smooths over one neighbor's idiosyncratic history.",
    )
    parser.add_argument(
        "--similar-method",
        choices=SIMILAR_METHODS,
        default="category",
        help="category (default, shipped v3.2/v3.3): cosine over 7-category "
        "purchase share. cf: NMF-learned user taste embeddings over ~90 "
        "ingredients (needs the `ml` extra: pip install -e '.[ml]') — the "
        "collaborative-filtering upgrade proposed after the k-NN blend win.",
    )
    parser.add_argument("--replicates", type=int, default=1)
    parser.add_argument("--seed", type=int, default=20260906)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    model = args.model or {
        "deepseek": DEFAULT_DEEPSEEK_MODEL,
        "openrouter": DEFAULT_OPENROUTER_MODEL,
        "openai": "gpt-4.1-mini",
        "opencode_go": DEFAULT_OPENCODE_GO_MODEL,
    }[args.provider]
    if args.live:
        key_env = PROVIDER_KEY_ENV[args.provider]
        if not os.environ.get(key_env):
            parser.error(f"--live with {args.provider} requires {key_env}")
        transport = OpenAICompatibleClient.from_provider(args.provider, model, os.environ[key_env], endpoint=args.endpoint)
        client: IntentClient = OpenAICompatibleIntentClient(transport)
    else:
        client = MockIntentClient()

    panel = development_splits()["validation"]
    study = build_study(
        panel, ranking_policy=args.ranking_policy, top_k=args.top_k, seed=args.seed,
        max_personas=args.personas or None, model_variant=args.model_variant,
        similar_k=args.similar_k, similar_method=args.similar_method,
    )
    rows, usage = run_study(study, client, IntentCache(args.cache), live=args.live, replicates=args.replicates)
    result = {
        "metadata": _metadata(study, client, live=args.live, replicates=args.replicates),
        "usage": usage,
        "analysis": analyse_study(study, rows),
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {"output": str(args.output), "metadata": result["metadata"], "usage": usage, "analysis": result["analysis"]},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
