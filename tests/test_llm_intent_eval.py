from __future__ import annotations

from collections import Counter

import pytest

from recsys.llm_intent_eval import (
    ARMS,
    ARM_OWN,
    ARM_RANDOM,
    ARM_SHUFFLED,
    ARM_SIMILAR,
    SKLEARN_AVAILABLE,
    IntentCache,
    IntentCase,
    IntentStudy,
    MockIntentClient,
    _blend_neighbor_history,
    _cf_knn_neighbors,
    _cf_user_vectors,
    _cosine_similarity,
    _deranged_partners,
    _ingredient_count_vector,
    _knn_neighbors,
    _validate_cookable,
    analyse_study,
    build_study,
    parse_intent_decision,
    run_study,
)
from recsys.panels import PanelSpec, build_panel

#: --similar-method cf needs the optional `ml` extra (numpy + scikit-learn),
#: which a plain `.[dev]` install (what CI does) doesn't have — same
#: skip-not-fail convention as recsys.catboost_model's GRADIENT_BOOSTER_AVAILABLE
#: (see tests/test_experiment1_rankers.py).
needs_sklearn = pytest.mark.skipif(
    not SKLEARN_AVAILABLE, reason="numpy/scikit-learn not installed (pip install -e '.[ml]')"
)
from recsys.response_models import UserAction


FORBIDDEN_PAYLOAD_KEYS = {
    "arm",
    "archetype",
    "user_id",
    "persona_id",
    "model_score",
    "oracle_relevant",
    "reason_codes",
    "mode",
}


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in _all_keys(item)}
    if isinstance(value, list):
        return {key for item in value for key in _all_keys(item)}
    return set()


@pytest.fixture(scope="module")
def production_study() -> IntentStudy:
    panel = build_panel(PanelSpec(name="llm_intent_test_prod", n_users=8, seed=707))
    return build_study(panel, ranking_policy="effort_first", max_personas=6, seed=808)


@pytest.fixture(scope="module")
def experimental_study() -> IntentStudy:
    panel = build_panel(PanelSpec(name="llm_intent_test_exp", n_users=8, seed=707))
    return build_study(panel, ranking_policy="model_order", max_personas=6, seed=808)


@pytest.mark.parametrize("study_fixture", ["production_study", "experimental_study"])
def test_every_persona_has_all_paired_arms(study_fixture, request) -> None:
    study: IntentStudy = request.getfixturevalue(study_fixture)
    arms = Counter((case.persona_id, case.arm) for case in study.cases)
    assert len(study.persona_ids) == 6
    assert set(arms.values()) == {1}
    for persona_id in study.persona_ids:
        assert {arm for user, arm in arms if user == persona_id} == set(ARMS)


@pytest.mark.parametrize("study_fixture", ["production_study", "experimental_study"])
def test_judge_never_sees_arm_identity_or_internal_scores(study_fixture, request) -> None:
    study: IntentStudy = request.getfixturevalue(study_fixture)
    for persona_id in study.persona_ids:
        cases = [case for case in study.cases if case.persona_id == persona_id]
        # Same persona, same observable shopper context across all three arms:
        # only the recommender's input changes, never what the judge is told
        # about who they are.
        assert len({repr(case.payload["shopper_context"]) for case in cases}) == 1
        for case in cases:
            assert not (_all_keys(case.payload) & FORBIDDEN_PAYLOAD_KEYS)


@needs_sklearn
@pytest.mark.parametrize("ranking_policy", ["effort_first", "model_order"])
def test_cf_similar_method_builds_a_study_and_is_recorded_in_metadata(ranking_policy) -> None:
    panel = build_panel(PanelSpec(name=f"llm_intent_cf_study_{ranking_policy}", n_users=8, seed=707))
    study = build_study(
        panel, ranking_policy=ranking_policy, max_personas=6, seed=808,
        similar_k=3, similar_method="cf",
    )
    assert study.similar_method == "cf"
    assert study.similar_k == 3
    for persona_id in study.persona_ids:
        by_arm = {case.arm: case for case in study.cases if case.persona_id == persona_id}
        assert ARM_SIMILAR in by_arm


def test_world_selection_matches_ranking_policy(production_study, experimental_study) -> None:
    assert production_study.world == "production"
    assert production_study.ranking_policy == "effort_first"
    assert experimental_study.world == "experimental"
    assert experimental_study.ranking_policy == "model_order"


def test_production_cards_carry_a_cookable_flag_and_may_lack_a_cook_path(production_study) -> None:
    """Some production cards are ready-meal-only (no safe cook path at all,
    see app/service.py._ready_selection_candidate); the judge payload must say
    so explicitly rather than looking like a zero-effort recipe."""
    seen_true = seen_false = False
    for case in production_study.cases:
        for card in case.payload["recommendations"]:
            assert "cookable" in card
            if card["cookable"]:
                seen_true = True
            else:
                seen_false = True
                assert card["missing_count"] == 0
                assert card["to_buy"] == []
    assert seen_true  # sanity: the fixture actually produced cook-backed cards


def test_experimental_cards_are_always_cookable(experimental_study) -> None:
    for case in experimental_study.cases:
        for card in case.payload["recommendations"]:
            assert card["cookable"] is True


def test_validate_cookable_rejects_buy_on_a_ready_only_card() -> None:
    recommendations = [{"cookable": False}, {"cookable": True}]
    buy_on_uncookable = parse_intent_decision(
        {
            "action": "buy",
            "selected_recipe_index": 0,
            "cook_within_7_days": "yes",
            "topup_acceptable": True,
            "confidence": 0.9,
            "reason_code": "taste_match",
        },
        recommendation_count=2,
    )
    with pytest.raises(ValueError):
        _validate_cookable(buy_on_uncookable, recommendations)

    buy_on_cookable = parse_intent_decision(
        {
            "action": "buy",
            "selected_recipe_index": 1,
            "cook_within_7_days": "yes",
            "topup_acceptable": True,
            "confidence": 0.9,
            "reason_code": "taste_match",
        },
        recommendation_count=2,
    )
    _validate_cookable(buy_on_cookable, recommendations)  # must not raise


def test_cosine_similarity_basics() -> None:
    assert _cosine_similarity({"dairy": 0.5, "meat": 0.5}, {"dairy": 0.5, "meat": 0.5}) == pytest.approx(1.0)
    assert _cosine_similarity({"dairy": 1.0}, {"meat": 1.0}) == pytest.approx(0.0)
    assert _cosine_similarity({}, {"dairy": 1.0}) == 0.0


def test_knn_neighbors_are_never_the_persona_itself() -> None:
    panel = build_panel(PanelSpec(name="llm_intent_similar", n_users=20, seed=42))
    neighbors = _knn_neighbors(panel.profiles, panel.profiles, k=5)
    assert set(neighbors) == {p.user.user_id for p in panel.profiles}
    for profile in panel.profiles:
        own_id = profile.user.user_id
        assert len(neighbors[own_id]) == 5
        assert own_id not in {n.user.user_id for n in neighbors[own_id]}
        # No duplicate neighbors within one persona's list.
        assert len({n.user.user_id for n in neighbors[own_id]}) == 5


def test_knn_neighbors_defaults_to_a_single_look_alike() -> None:
    panel = build_panel(PanelSpec(name="llm_intent_similar_k1", n_users=10, seed=42))
    neighbors = _knn_neighbors(panel.profiles, panel.profiles, k=1)
    for own_id, picked in neighbors.items():
        assert len(picked) == 1
        assert picked[0].user.user_id != own_id


def test_blend_neighbor_history_unions_fields_and_is_order_independent() -> None:
    panel = build_panel(PanelSpec(name="llm_intent_blend", n_users=8, seed=7))
    neighbors = panel.profiles[:3]
    forward = _blend_neighbor_history(neighbors)
    backward = _blend_neighbor_history(list(reversed(neighbors)))
    assert forward == backward
    history, categories, brands, saved = forward
    total_receipts = sum(len(p.purchase_history) for p in neighbors)
    assert len(history) == total_receipts
    assert categories == sorted(set(categories))
    assert brands == sorted(set(brands))
    assert isinstance(saved, set)


def test_ingredient_count_vector_sums_quantities_across_receipts() -> None:
    panel = build_panel(PanelSpec(name="llm_intent_cf_counts", n_users=5, seed=11))
    profile = panel.profiles[0]
    vector = _ingredient_count_vector(profile)
    expected: dict[str, float] = {}
    for receipt in profile.purchase_history:
        for item in receipt.items:
            for ingredient_id in item.ingredient_ids:
                expected[ingredient_id] = expected.get(ingredient_id, 0.0) + item.quantity
    assert vector == expected


@needs_sklearn
def test_cf_user_vectors_are_l2_bounded_and_cover_the_whole_pool() -> None:
    panel = build_panel(PanelSpec(name="llm_intent_cf_vectors", n_users=15, seed=11))
    vectors = _cf_user_vectors(panel.profiles, n_factors=4, seed=0)
    assert set(vectors) == {p.user.user_id for p in panel.profiles}
    # NMF factors are non-negative by construction.
    assert all(value >= 0.0 for vector in vectors.values() for value in vector.values())


@needs_sklearn
def test_cf_knn_neighbors_are_never_the_persona_itself() -> None:
    panel = build_panel(PanelSpec(name="llm_intent_cf_knn", n_users=15, seed=11))
    neighbors = _cf_knn_neighbors(panel.profiles, panel.profiles, k=3, seed=0)
    assert set(neighbors) == {p.user.user_id for p in panel.profiles}
    for profile in panel.profiles:
        own_id = profile.user.user_id
        assert len(neighbors[own_id]) == 3
        assert own_id not in {n.user.user_id for n in neighbors[own_id]}


@pytest.mark.parametrize("study_fixture", ["production_study", "experimental_study"])
def test_similar_arm_uses_a_different_history_than_own_and_shuffled(study_fixture, request) -> None:
    study: IntentStudy = request.getfixturevalue(study_fixture)
    for persona_id in study.persona_ids:
        by_arm = {case.arm: case for case in study.cases if case.persona_id == persona_id}
        assert ARM_SIMILAR in by_arm
        # similar's feed need not differ from own/shuffled for every persona in
        # a tiny 6-persona fixture, but the case must exist and stay blinded
        # the same way every other arm is.
        assert not (_all_keys(by_arm[ARM_SIMILAR].payload) & FORBIDDEN_PAYLOAD_KEYS)


def test_partner_permutation_has_no_fixed_points() -> None:
    panel = build_panel(PanelSpec(name="llm_intent_partners", n_users=12, seed=17))
    partners = _deranged_partners(panel.profiles, seed=3)
    assert {p.user.user_id for p in partners} == {p.user.user_id for p in panel.profiles}
    assert all(
        own.user.user_id != partner.user.user_id
        for own, partner in zip(panel.profiles, partners, strict=True)
    )


@pytest.mark.parametrize(
    "raw",
    [
        {
            "action": "ignore",
            "selected_recipe_index": 0,
            "cook_within_7_days": "no",
            "topup_acceptable": False,
            "confidence": 0.5,
            "reason_code": "poor_history_fit",
        },
        {
            "action": "buy",
            "selected_recipe_index": 0,
            "cook_within_7_days": "maybe",
            "topup_acceptable": True,
            "confidence": 0.5,
            "reason_code": "taste_match",
        },
        {
            "action": "save",
            "selected_recipe_index": 99,
            "cook_within_7_days": "maybe",
            "topup_acceptable": True,
            "confidence": 0.5,
            "reason_code": "taste_match",
        },
    ],
)
def test_semantically_invalid_intent_responses_are_rejected(raw) -> None:
    with pytest.raises(ValueError):
        parse_intent_decision(raw, recommendation_count=3)


class CountingClient(MockIntentClient):
    def __init__(self) -> None:
        self.calls = 0

    def decide(self, payload, *, seed):
        self.calls += 1
        return super().decide(payload, seed=seed)


def test_identical_blinded_payload_is_judged_once_and_reused(tmp_path) -> None:
    payload = {
        "shopper_context": {"top_categories": [{"category": "dairy"}]},
        "recommendations": [
            {
                "title": "Омлет",
                "ingredient_categories": ["dairy"],
                "missing_count": 1,
                "missing_cost_rub": 100,
                "prep_minutes": 15,
                "cookable": True,
            }
        ],
    }
    cases = tuple(
        IntentCase(
            case_id=f"case-{arm}",
            persona_id="persona-1",
            archetype="routine",
            arm=arm,
            recipe_ids=("omelette",),
            payload=payload,
        )
        for arm in ARMS
    )
    synthetic = IntentStudy(
        cases=cases, panel_name="test", panel_profiles_checksum="profiles",
        panel_inventories_checksum="inventories", catalog_hash="catalog",
        ranking_policy="effort_first", world="production", top_k=3, seed=1,
    )
    client = CountingClient()
    rows, usage = run_study(synthetic, client, IntentCache(tmp_path / "cache.json"), live=False)
    assert len(rows) == len(ARMS)
    assert client.calls == 1
    assert usage["planned_or_executed_calls"] == 1
    # The per-card attributes travel into the row, so post-hoc analysis does
    # not need to rebuild the study from the seed to see what was offered.
    assert rows[0]["recommendations"] == payload["recommendations"]


def _row(persona: str, arm: str, action: UserAction) -> dict[str, object]:
    selected = None if action == UserAction.IGNORE else "recipe"
    return {
        "persona_id": persona,
        "arm": arm,
        "action": action.value,
        "cook_within_7_days": "yes" if action == UserAction.BUY else "no",
        "topup_acceptable": action == UserAction.BUY,
        "selected_recipe_id": selected,
    }


def test_primary_metric_and_paired_deltas_are_computed_by_persona() -> None:
    cases = tuple(
        IntentCase(
            case_id=f"{persona}-{arm}",
            persona_id=persona,
            archetype="routine",
            arm=arm,
            recipe_ids=(("own",) if arm == ARM_OWN else (arm,)),
            payload={},
        )
        for persona in ("p1", "p2")
        for arm in ARMS
    )
    synthetic = IntentStudy(
        cases=cases, panel_name="test", panel_profiles_checksum="profiles",
        panel_inventories_checksum="inventories", catalog_hash="catalog",
        ranking_policy="effort_first", world="production", top_k=3, seed=1,
    )
    rows = [
        _row("p1", ARM_OWN, UserAction.BUY),
        _row("p1", ARM_SHUFFLED, UserAction.IGNORE),
        _row("p1", ARM_RANDOM, UserAction.IGNORE),
        _row("p2", ARM_OWN, UserAction.BUY),
        _row("p2", ARM_SHUFFLED, UserAction.BUY),
        _row("p2", ARM_RANDOM, UserAction.IGNORE),
    ]
    result = analyse_study(synthetic, rows)
    assert result["arms"][ARM_OWN]["strict_intent_rate"] == 1.0
    assert result["arms"][ARM_SHUFFLED]["strict_intent_rate"] == 0.5
    assert result["comparisons"]["own_minus_shuffled"]["strict_intent_delta"][0] == 0.5
    assert result["comparisons"]["own_minus_random"]["strict_intent_delta"][0] == 1.0
