"""Three defects found while auditing the ML, and the guards against their return.

Each test names the measurement that justified the fix, so a future reader can
tell a deliberate constraint from an arbitrary one.
"""

from __future__ import annotations

import random

from app.contracts import RecommendationRequest
from recsys.catalog_freeze import baseline_catalog, candidate_catalog, recipe_content_hash
from recsys.inventory import generate_inventory
from recsys.model import (
    AVAILABILITY_FEATURE_NAMES,
    FEATURE_NAMES,
    TRAINING_INDEX_OFFSET,
    MLRecommendationEngine,
    _feature_vector,
    compute_features,
)
from recsys.panels import COHORT_INDEX_OFFSET, PanelSpec, build_panel
from recsys.profiles import generate_population
from recsys.recipes import RECIPES


def _request(profile, inventory, catalog):
    return RecommendationRequest(
        user=profile.user,
        current_receipt=profile.current_receipt,
        purchase_history=profile.purchase_history,
        recipe_catalog=catalog,
        inventory_snapshot=inventory,
        now=profile.now,
        limit=3,
    )


# --- #4: the catalog must not retrain the model ---------------------------


def test_the_engine_trains_on_the_frozen_baseline_by_default() -> None:
    """Training samples six recipes per profile, so a longer catalog fits
    different weights — measured at up to 0.25 of weight movement when ten
    candidates were added. A catalog comparison would otherwise measure the
    catalog plus a retrained model."""
    engine = MLRecommendationEngine()
    assert engine.training_catalog_hash == recipe_content_hash(baseline_catalog())


def test_adding_candidate_recipes_does_not_move_the_default_model() -> None:
    assert len(RECIPES) > len(baseline_catalog())  # candidates are in the live catalog
    first = MLRecommendationEngine()
    second = MLRecommendationEngine()
    assert first._classifier.weights == second._classifier.weights
    assert first.training_catalog_hash == second.training_catalog_hash


def test_training_on_a_different_catalog_is_visible_rather_than_silent() -> None:
    baseline = MLRecommendationEngine()
    extended = MLRecommendationEngine(
        recipe_catalog=baseline_catalog() + candidate_catalog()
    )
    assert extended.training_catalog_hash != baseline.training_catalog_hash


def test_a_recipe_absent_from_training_is_still_scorable() -> None:
    """The model scores features, not recipe ids, so pinning the training
    catalog costs nothing at inference."""
    engine = MLRecommendationEngine()
    panel = build_panel(PanelSpec(name="isolation_panel", n_users=3))
    profile, inventory = panel.pairs()[0]
    full = baseline_catalog() + candidate_catalog()
    scored = {r.recipe_id for r in engine.rank(_request(profile, inventory, full))}
    assert {r.recipe_id for r in candidate_catalog()} <= scored


# --- #5: the preference model must not read the shelf ---------------------


def test_the_score_does_not_depend_on_todays_inventory() -> None:
    """The same person and the same dish must score the same whatever is in
    stock. Before the fix this moved by 0.0027 across six inventory draws."""
    engine = MLRecommendationEngine()
    panel = build_panel(PanelSpec(name="isolation_panel", n_users=3))
    profile, _ = panel.pairs()[0]
    catalog = baseline_catalog()

    scores = []
    for seed in range(6):
        inventory = generate_inventory(
            random.Random(seed),
            now=profile.now,
            home_store_id=profile.current_receipt.store_id,
            user_radius_km=profile.user.radius_km,
        )
        ranked = engine.rank(_request(profile, inventory, catalog))
        scores.append({r.recipe_id: r.score for r in ranked}["borsch"])
    assert len(set(scores)) == 1


def test_availability_features_are_zeroed_not_dropped() -> None:
    """Zeroing keeps one vector length across variants, so weight indices stay
    comparable between models — the same trick EFFORT_FEATURE_NAMES uses."""
    panel = build_panel(PanelSpec(name="isolation_panel", n_users=3))
    profile, inventory = panel.pairs()[0]
    request = _request(profile, inventory, baseline_catalog())
    features = compute_features(request, baseline_catalog()[0])

    off = _feature_vector(features, include_availability=False)
    on = _feature_vector(features, include_availability=True)
    assert len(off) == len(on) == len(FEATURE_NAMES)
    for name in AVAILABILITY_FEATURE_NAMES:
        assert off[FEATURE_NAMES.index(name)] == 0.0


def test_reading_the_shelf_remains_possible_but_must_be_asked_for() -> None:
    contaminated = MLRecommendationEngine(include_availability_features=True)
    clean = MLRecommendationEngine()
    assert contaminated._classifier.weights != clean._classifier.weights


# --- #7: identities must not collide across populations -------------------


def test_training_ids_never_collide_with_panel_ids() -> None:
    """Measured before the offset: 87 shared ids holding different people's
    data, which makes "was this user trained on?" unanswerable."""
    training = {
        p.user.user_id
        for p in generate_population(300, seed=999, index_offset=TRAINING_INDEX_OFFSET)
    }
    panel = {
        p.user.user_id
        for p in build_panel(PanelSpec(name="isolation_panel", n_users=200)).profiles
    }
    assert not training & panel


def test_the_training_range_is_clear_of_every_panel_cohort() -> None:
    assert TRAINING_INDEX_OFFSET not in COHORT_INDEX_OFFSET.values()
    assert all(
        TRAINING_INDEX_OFFSET - offset >= 100_000
        for offset in COHORT_INDEX_OFFSET.values()
    )


def test_index_offset_shifts_identity_without_changing_the_draw() -> None:
    """The offset must rename people, not resample them — otherwise it would
    silently change what the model trains on."""
    plain = generate_population(20, seed=5)
    shifted = generate_population(20, seed=5, index_offset=TRAINING_INDEX_OFFSET)
    assert [p.user.user_id for p in plain] != [p.user.user_id for p in shifted]
    assert [p.archetype for p in plain] == [p.archetype for p in shifted]
    assert [
        [(i.sku_id.split("_")[0], i.unit_price) for i in p.current_receipt.items]
        for p in plain
    ] == [
        [(i.sku_id.split("_")[0], i.unit_price) for i in p.current_receipt.items]
        for p in shifted
    ]
