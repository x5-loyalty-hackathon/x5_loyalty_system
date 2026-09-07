from __future__ import annotations

import http.client
import subprocess
import sys
import urllib.error

import pytest

from recsys.llm_audit import (
    AuditCard,
    JsonCache,
    LLMDecision,
    MockLLMClient,
    PROMPT_VERSION,
    cache_key,
    card_id,
    cohen_kappa,
    collect_cards,
    population_weights,
    run_audit,
    stratified_sample,
    _with_retries,
)
from recsys.response_models import UserAction


@pytest.fixture(scope="module")
def cards() -> list[AuditCard]:
    return collect_cards(users_per_regime=3, seed=17)


def test_stratification_keeps_every_observed_stratum(cards: list[AuditCard]) -> None:
    sample = stratified_sample(cards, len(cards), seed=4)
    assert {card.stratum for card in sample} == {card.stratum for card in cards}
    assert {card.regime_name for card in sample} == {card.regime_name for card in cards}
    assert {card.missing_count for card in sample} == {card.missing_count for card in cards}
    assert {card.has_ready_meal_alternative for card in sample} == {card.has_ready_meal_alternative for card in cards}


def test_card_id_is_stable_across_processes() -> None:
    expected = card_id("novelty=mid/promo=mid/repeat=mid", 7, "heuristic/effort", "borsch")
    code = "from recsys.llm_audit import card_id; print(card_id('novelty=mid/promo=mid/repeat=mid', 7, 'heuristic/effort', 'borsch'))"
    actual = subprocess.check_output([sys.executable, "-c", code], text=True).strip()
    assert actual == expected


def test_cache_reuses_value_and_invalidates_model_or_prompt(cards: list[AuditCard], tmp_path) -> None:
    card = cards[0]
    cache = JsonCache(tmp_path / "audit.json")
    _, first = run_audit([card], MockLLMClient(), cache, dry_run=False)
    _, second = run_audit([card], MockLLMClient(), JsonCache(tmp_path / "audit.json"), dry_run=False)
    assert first["planned_live_calls"] == 1
    assert second["planned_live_calls"] == 0
    assert cache_key(card.features, model="another") != cache_key(card.features, model="mock")
    assert cache_key(card.features, model="mock", prompt_version="next") != cache_key(card.features, model="mock", prompt_version=PROMPT_VERSION)


def test_invalid_llm_response_raises() -> None:
    from recsys.llm_audit import parse_decision
    with pytest.raises(ValueError):
        parse_decision({"action": "later", "confidence": 0.5, "reason_code": "x"})


def test_with_retries_retries_a_server_closed_connection() -> None:
    # A live run crashed on exactly this: http.client.RemoteDisconnected (a
    # plain server-closed-the-connection reset, not a timeout) propagated
    # with zero retries because it isn't a urllib.error.URLError or
    # TimeoutError — the two exception types the old, narrower tuple caught.
    attempts = []

    def flaky() -> LLMDecision:
        attempts.append(1)
        if len(attempts) < 3:
            raise http.client.RemoteDisconnected("Remote end closed connection without response")
        return LLMDecision(UserAction.BUY, 0.9, "taste_match")

    decision = _with_retries(flaky, retries=3)
    assert decision.action == UserAction.BUY
    assert len(attempts) == 3


def test_with_retries_still_gives_up_after_exhausting_attempts() -> None:
    def always_disconnects() -> LLMDecision:
        raise http.client.RemoteDisconnected("Remote end closed connection without response")

    with pytest.raises(ConnectionError):
        _with_retries(always_disconnects, retries=2)


def test_with_retries_still_catches_url_error_and_value_error() -> None:
    calls = {"url_error": 0, "value_error": 0}

    def flaky_url_error() -> LLMDecision:
        calls["url_error"] += 1
        if calls["url_error"] < 2:
            raise urllib.error.URLError("connection refused")
        return LLMDecision(UserAction.IGNORE, 0.5, "insufficient_information")

    assert _with_retries(flaky_url_error, retries=3).action == UserAction.IGNORE

    def flaky_value_error() -> LLMDecision:
        calls["value_error"] += 1
        if calls["value_error"] < 2:
            raise ValueError("malformed JSON response")
        return LLMDecision(UserAction.SAVE, 0.5, "new_recipe_interest")

    assert _with_retries(flaky_value_error, retries=3).action == UserAction.SAVE


def test_cohen_kappa_known_cases() -> None:
    same = [UserAction.BUY, UserAction.IGNORE, UserAction.SAVE]
    assert cohen_kappa(same, same) == 1.0
    left = [UserAction.BUY, UserAction.BUY, UserAction.IGNORE, UserAction.IGNORE]
    right = [UserAction.BUY, UserAction.IGNORE, UserAction.BUY, UserAction.IGNORE]
    assert cohen_kappa(left, right) == pytest.approx(0.0)


def test_population_weights_restore_population_distribution(cards: list[AuditCard]) -> None:
    sample = stratified_sample(cards, min(len(cards), 20), seed=9)
    weights = population_weights(cards, sample)
    restored = sum(weights[card.stratum] for card in sample)
    assert restored == pytest.approx(1.0)
