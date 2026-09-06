"""Merge #8 must preserve API 1.3 and the provenance of offline experiments."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from pydantic import ValidationError

from app.contracts import CONTRACT_VERSION, RecommendationRequest
from recsys.catalog_freeze import baseline_catalog, recipe_content_hash
from recsys.model import TRAINING_INDEX_OFFSET
from recsys.profiles import generate_population

ROOT = Path(__file__).resolve().parents[1]


def request():
    return RecommendationRequest.model_validate_json(
        (ROOT / "mobile/src/fixtures/mealRequest.json").read_text()
    )


def test_runtime_scores_ignore_inventory_and_use_frozen_training_catalog(ml_engine):
    value = request()
    before = ml_engine.rank(value)
    value.inventory_snapshot = []
    # Supply-related internal explanations may change. The preference scores
    # and their order must not; public explanations are rebuilt by app.service.
    assert [(r.recipe_id, r.score, r.mode) for r in ml_engine.rank(value)] == [
        (r.recipe_id, r.score, r.mode) for r in before
    ]
    assert ml_engine._include_availability is False
    assert ml_engine._pantry_policy.enabled is False
    assert ml_engine.training_catalog_hash == recipe_content_hash(baseline_catalog())
    assert len(ml_engine._recipe_catalog_for_training) == 37
    # The three mobile recipes need not be present in the training catalog.
    assert {item.recipe_id for item in before} == {
        recipe.recipe_id for recipe in value.recipe_catalog
    }


def test_runtime_training_population_has_no_future_purchases():
    for profile in generate_population(200, seed=999, index_offset=TRAINING_INDEX_OFFSET):
        assert profile.current_receipt.purchased_at <= profile.now
        assert all(
            receipt.purchased_at < profile.current_receipt.purchased_at
            for receipt in profile.purchase_history
        )


def test_research_fields_are_not_silently_added_to_http_contract():
    assert CONTRACT_VERSION == "1.3"
    payload = request().model_dump(mode="json")
    payload["ready_meal_options"] = []
    with pytest.raises(ValidationError, match="extra_forbidden"):
        RecommendationRequest.model_validate(payload)


def test_serving_model_does_not_import_experimental_backend():
    source = """
import sys
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as client:
    health = client.get('/health').json()
assert health['recommendation_engine'] == 'model', health
assert health['model_fallback'] is False, health
assert not [name for name in sys.modules if name.startswith('recsys.experimental')]
"""
    subprocess.run(
        [sys.executable, "-c", source], cwd=ROOT, check=True,
        capture_output=True, text=True, timeout=30,
        env={**os.environ, "RECOMMENDATION_ENGINE": "model"},
    )


def test_experimental_catalog_retains_original_frozen_hash():
    from recsys.experimental.catalog_freeze import baseline_catalog, recipe_content_hash

    assert recipe_content_hash(baseline_catalog()) == "dda665585c844cfc"


def test_experimental_panels_reproduce_committed_manifests_without_writing():
    # Rebuild inputs and verify provenance only: no model selection, holdout
    # scoring, human answers, dataset replacement, or report regeneration.
    from recsys.panels import build_panel, standard_specs

    for name, spec in standard_specs().items():
        expected = json.loads(
            (ROOT / "recsys/data/panels" / name / "manifest.json").read_text()
        )
        actual = build_panel(spec).manifest.to_json()
        assert actual == expected, name
