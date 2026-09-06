from copy import deepcopy
import csv
import json

from fastapi.testclient import TestClient
import pytest

import app.main as main
from app.contracts import MealRecommendationResponse, RecommendationRequest
from app.safety import SafetyPolicy
from app.service import RecommendationService
from scripts.serving_review_pack import build_pack, content_hash, generate_requests, llm_inputs, review_rows, write_pack


def test_pack_uses_real_model_meal_api_and_keeps_labels_empty(monkeypatch, ml_engine):
    monkeypatch.setattr(main, "recommendation_service", RecommendationService(
        engine=ml_engine, safety_policy=SafetyPolicy(), saved_recipe_provider=main.state_repository))
    monkeypatch.setattr(main, "recommendation_engine_name", "model")
    monkeypatch.setattr(main, "model_fallback", False)
    client = TestClient(main.app)
    first = build_pack(client, n_profiles=4)
    second = build_pack(client, n_profiles=4)
    assert first == second  # opaque random offer IDs don't alter the archive
    assert first["manifest"]["quality_status"] == "not_assessed"
    assert first["manifest"]["cases_sha256"] == content_hash(first["cases"])
    assert first["diagnostics"]["profiles_with_results"] + first["diagnostics"]["empty_profiles"] == 4
    for case in first["cases"]:
        request = RecommendationRequest.model_validate(case["request"])
        response = MealRecommendationResponse.model_validate(case["response"])
        assert request.purchase_history and request.shopping_context.radius_km == .75
        assert response.user_id == request.user.user_id
        assert all(meal.offer_id is None for meal in response.recommendations)
        progress = client.get(f"/api/v1/progress/{response.user_id}").json()
        assert progress["avatar_xp"] == progress["verified_receipts"] == 0
    assert all(row["relevance_label"] == row["reviewer"] == row["criterion_version"] == ""
               for row in review_rows(first))
    original_pack = deepcopy(first)
    inputs = llm_inputs(first)
    assert first == original_pack  # projection must not strip the audit archive
    assert inputs == llm_inputs(second)
    for source, item in zip(first["cases"], inputs):
        assert "archetype" not in item
        assert item["context"]["purchase_history"] == source["request"]["purchase_history"]
        assert item["context"]["current_receipt"] == source["request"]["current_receipt"]
        assert [meal["meal_id"] for meal in item["recommendations"]] == [
            meal["meal_id"] for meal in source["response"]["recommendations"]]
        for meal in item["recommendations"]:
            assert not {"model_score", "offer_id", "safety_status", "reason_codes",
                        "route_reason_codes"}.intersection(meal)
        assert all("verified" not in recipe for recipe in item["recipes"])
        recipes = {recipe["recipe_id"] for recipe in item["recipes"]}
        expected = set(source["request"]["user"]["saved_recipe_ids"])
        expected.update(meal["cook_variant"]["recipe_id"] for meal in item["recommendations"]
                        if meal["cook_variant"])
        assert recipes == expected.intersection(
            recipe["recipe_id"] for recipe in source["request"]["recipe_catalog"])


def test_pack_rejects_mock_or_fallback_instead_of_publishing_as_model(monkeypatch):
    monkeypatch.setattr(main, "recommendation_engine_name", "mock")
    with pytest.raises(RuntimeError, match="Unexpected engine"):
        build_pack(TestClient(main.app), n_profiles=1)
    monkeypatch.setattr(main, "recommendation_engine_name", "model")
    monkeypatch.setattr(main, "model_fallback", True)
    with pytest.raises(RuntimeError, match="fallback"):
        build_pack(TestClient(main.app), n_profiles=1)


def test_empty_results_remain_in_review_sheet_and_previous_labels_are_not_overwritten(tmp_path):
    case_id, archetype, request = next(generate_requests(1, 606))
    pack = {"manifest": {"limitations": []}, "cases": [{
        "case_id": case_id, "archetype": archetype,
        "request": request.model_dump(mode="json"), "response": {"recommendations": []},
    }]}
    rows = review_rows(pack)
    assert len(rows) == 1 and rows[0]["row_kind"] == "empty_response"
    assert rows[0]["relevance_label"] == ""
    output = tmp_path / "review"
    write_pack(pack, output)
    original = (output / "review.csv").read_bytes()
    with pytest.raises(FileExistsError):
        write_pack(deepcopy(pack), output)
    assert (output / "review.csv").read_bytes() == original
    with (output / "review.csv").open(encoding="utf-8-sig", newline="") as handle:
        assert len(list(csv.DictReader(handle))) == 1
    assert json.loads((output / "responses.json").read_text(encoding="utf-8"))["cases"][0]["case_id"] == case_id
    inputs = [
        json.loads(line)
        for line in (output / "llm_inputs.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(inputs) == 1 and inputs[0]["recommendations"] == []
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["llm_inputs_sha256"] == content_hash(inputs)
    assert manifest["full_archive_included"] is True
    compact = tmp_path / "compact"
    write_pack(pack, compact, full_archive=False)
    assert not (compact / "responses.json").exists()
    assert (compact / "llm_inputs.jsonl").read_bytes() == (output / "llm_inputs.jsonl").read_bytes()
    assert json.loads((compact / "manifest.json").read_text(encoding="utf-8"))["full_archive_included"] is False


@pytest.mark.parametrize("count", [0, 51])
def test_profile_count_is_bounded(count):
    with pytest.raises(ValueError):
        list(generate_requests(count, 606))
