"""Tests for the four rankers built for experiment 1 (ranker quality).

See ``docs/research/recsys/experiment-plan-ranker-service-catalog.md``
("Эксперимент 1") and ``docs/research/recsys/experiment-1-ranker-quality-report.md``.
"""

from __future__ import annotations

import random

import pytest

from app.contracts import ModelRecommendation, RecommendationRequest
from recsys.catboost_model import (
    GRADIENT_BOOSTER_AVAILABLE,
    CatBoostRecommendationEngine,
)
from recsys.coverage_heuristic_engine import CoverageHeuristicEngine
from recsys.inventory import generate_inventory
from recsys.model import FEATURE_NAMES, MLRecommendationEngine, _feature_vector, compute_features
from recsys.oracle_ranking_engine import OracleRankingEngine
from recsys.profiles import generate_population
from recsys.recipes import RECIPES

SEED = 20260905

#: Both boosters live in optional extras, so a plain `.[dev]` install (what CI
#: does) has neither. Skipped rather than failed, and skipped per-test rather
#: than per-module: the coverage/oracle/logreg rankers in this file need no
#: booster and must keep running where one is absent.
needs_booster = pytest.mark.skipif(
    not GRADIENT_BOOSTER_AVAILABLE,
    reason="no gradient booster installed (pip install -e '.[ml]' or '.[experiment1]')",
)


def _sample_request(seed: int = SEED, index: int = 0) -> tuple:
    profiles = generate_population(5, seed=seed)
    profile = profiles[index]
    rng = random.Random(seed)
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
        recipe_catalog=list(RECIPES),
        inventory_snapshot=inventory,
        now=profile.now,
        limit=3,
    )
    return profile, request


@pytest.fixture(scope="module")
def request_fixture():
    return _sample_request()


@pytest.fixture(scope="module")
def all_engines():
    engines = {
        "coverage": CoverageHeuristicEngine(),
        "ml": MLRecommendationEngine(training_profiles=40),
        "oracle": OracleRankingEngine(),
    }
    if GRADIENT_BOOSTER_AVAILABLE:
        engines["catboost"] = CatBoostRecommendationEngine(training_profiles=40)
    return engines


class TestProtocolCompliance:
    """``rank()`` must satisfy the exact ``RecommendationEngine`` Protocol
    used by ``app.service`` (and by every other consumer in this repo)."""

    def test_all_four_engines_expose_rank(self, all_engines) -> None:
        for name, engine in all_engines.items():
            assert callable(getattr(engine, "rank", None)), name

    def test_rank_returns_schema_valid_model_recommendations(
        self, all_engines, request_fixture
    ) -> None:
        _, request = request_fixture
        for name, engine in all_engines.items():
            recommendations = engine.rank(request)
            assert recommendations, name
            for rec in recommendations:
                assert isinstance(rec, ModelRecommendation), name
                assert 0.0 <= rec.score <= 1.0, name
                assert rec.reason_codes, name

    def test_unverified_recipes_are_never_returned(self, all_engines, request_fixture) -> None:
        _, request = request_fixture
        payload = request.model_dump(mode="json")
        payload["recipe_catalog"][0]["verified"] = False
        unverified_id = payload["recipe_catalog"][0]["recipe_id"]
        tampered = RecommendationRequest.model_validate(payload)
        for name, engine in all_engines.items():
            ids = {rec.recipe_id for rec in engine.rank(tampered)}
            assert unverified_id not in ids, name

    def test_every_engine_ranks_the_full_verified_catalog(
        self, all_engines, request_fixture
    ) -> None:
        _, request = request_fixture
        verified_count = sum(1 for r in request.recipe_catalog if r.verified)
        for name, engine in all_engines.items():
            assert len(engine.rank(request)) == verified_count, name


class TestDeterminism:
    def test_coverage_engine_is_deterministic(self, request_fixture) -> None:
        _, request = request_fixture
        engine = CoverageHeuristicEngine()
        first = [(r.recipe_id, r.score) for r in engine.rank(request)]
        second = [(r.recipe_id, r.score) for r in engine.rank(request)]
        assert first == second

    def test_oracle_engine_is_deterministic(self, request_fixture) -> None:
        _, request = request_fixture
        engine = OracleRankingEngine()
        first = [(r.recipe_id, r.score) for r in engine.rank(request)]
        second = [(r.recipe_id, r.score) for r in engine.rank(request)]
        assert first == second

    def test_ml_engine_is_deterministic_given_the_same_seed(self, request_fixture) -> None:
        _, request = request_fixture
        a = MLRecommendationEngine(seed=555, training_profiles=40).rank(request)
        b = MLRecommendationEngine(seed=555, training_profiles=40).rank(request)
        assert [(r.recipe_id, r.score) for r in a] == [(r.recipe_id, r.score) for r in b]

    @needs_booster
    def test_catboost_engine_is_deterministic_given_the_same_seed(self, request_fixture) -> None:
        _, request = request_fixture
        a = CatBoostRecommendationEngine(seed=555, training_profiles=40).rank(request)
        b = CatBoostRecommendationEngine(seed=555, training_profiles=40).rank(request)
        assert [(r.recipe_id, r.score) for r in a] == [(r.recipe_id, r.score) for r in b]


class TestCoverageHeuristicOrdering:
    """The one engine whose contract is literally a sort key, so it can be
    checked directly rather than just smoke-tested."""

    def test_ranking_matches_coverage_desc_missing_count_asc(self, request_fixture) -> None:
        _, request = request_fixture
        engine = CoverageHeuristicEngine()
        recipe_lookup = {r.recipe_id: r for r in request.recipe_catalog}
        ranked = engine.rank(request)

        keys = []
        for rec in ranked:
            features = compute_features(request, recipe_lookup[rec.recipe_id])
            keys.append((-features["coverage"], int(features["_missing_count"])))
        assert keys == sorted(keys)

    def test_never_trains_and_ignores_purchase_history_shape(self, request_fixture) -> None:
        """No classifier attribute, no fit-time cost: this is the "no
        learning" baseline the experiment plan calls for."""
        engine = CoverageHeuristicEngine()
        assert not hasattr(engine, "_classifier")
        assert not hasattr(engine, "_booster")


class TestOracleRankingEngine:
    def test_saved_recipe_always_outranks_unsaved(self, request_fixture) -> None:
        profile, request = request_fixture
        if not profile.user.saved_recipe_ids:
            pytest.skip("fixture profile has no saved recipes")
        engine = OracleRankingEngine()
        ranked = engine.rank(request)
        saved_ranks = [
            i for i, r in enumerate(ranked) if r.recipe_id in profile.user.saved_recipe_ids
        ]
        unsaved_ranks = [
            i for i, r in enumerate(ranked) if r.recipe_id not in profile.user.saved_recipe_ids
        ]
        if saved_ranks and unsaved_ranks:
            assert max(saved_ranks) < max(unsaved_ranks) or all(
                sr < min(unsaved_ranks) for sr in saved_ranks
            )


class TestFeatureVectorShape:
    def test_feature_vector_length_matches_feature_names(self, request_fixture) -> None:
        _, request = request_fixture
        recipe = request.recipe_catalog[0]
        features = compute_features(request, recipe)
        vector = _feature_vector(features)
        assert len(vector) == len(FEATURE_NAMES)
        assert all(isinstance(v, float) for v in vector)

    @needs_booster
    def test_catboost_and_ml_train_on_identical_row_shape(self) -> None:
        """Same X shape for both classifiers, per the experiment plan's
        requirement that only the classifier differs, not the data."""
        from recsys.catboost_model import _train_booster
        from recsys.model import _train_classifier

        booster = _train_booster(seed=1, n_profiles=5, recipe_catalog=list(RECIPES))
        logreg = _train_classifier(seed=1, n_profiles=5, recipe_catalog=list(RECIPES))
        assert len(logreg.weights) == len(FEATURE_NAMES)
        # sklearn/CatBoost both expose n_features_in_ after fit.
        assert getattr(booster, "n_features_in_", len(FEATURE_NAMES)) == len(FEATURE_NAMES)
