"""Independent LLM audit of the three handwritten user responders.

The LLM is an observer, never an oracle.  In particular it receives only
``ResponseFeatures`` (the same structural boundary as every responder) and
``--dry-run`` is the default safe way to exercise the complete audit pipeline.
It uses a deterministic local mock and never reads an API key or opens a
network connection.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import time
import urllib.error
import urllib.request
import uuid
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable, Protocol

from recsys.experimental.recommender import DeterministicMockEngine
from recsys.experimental.safety import SafetyPolicy
from recsys.experimental.service import EFFORT_FIRST, RecommendationService
from recsys.benchmark import TOP_K, _build_request, stable_seed
from recsys.experimental.inventory import generate_inventory
from recsys.experimental.profiles import SyntheticProfile, generate_population
from recsys.ready_food_pairs import ready_meal_options
from recsys.experimental.recipes import RECIPES
from recsys.regimes import REGIMES, Regime
from recsys.response_models import (
    EconomicResponder,
    LLMResponder,
    ProbabilisticResponder,
    ResponseContext,
    ResponseFeatures,
    RuleBasedResponder,
    UserAction,
    extract_features,
)

PROMPT_VERSION = "v1"
DEFAULT_MODEL = "gpt-4.1-mini"
DEFAULT_OPENROUTER_MODEL = "openai/gpt-4.1-mini"
DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"
DEFAULT_CACHE = Path(".cache/llm_audit.json")
INDEPENDENT_RESPONDERS = (RuleBasedResponder(), ProbabilisticResponder(), EconomicResponder())

OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"
OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
DEEPSEEK_ENDPOINT = "https://api.deepseek.com/chat/completions"
#: OpenCode Go: one $10/mo key, many open-weight models — chat/completions-
#: shaped ones only (GLM/Kimi/DeepSeek-V4/LongCat/MiMo/Hy3/Hy4/Omen). Grok,
#: GPT-5.6-Luna and Muse Spark use /v1/responses; MiniMax and Qwen use
#: /v1/messages (Anthropic-shaped) — neither is this wire format, don't point
#: --model at one of those through this endpoint.
OPENCODE_GO_ENDPOINT = "https://opencode.ai/zen/go/v1/chat/completions"
DEFAULT_OPENCODE_GO_MODEL = "glm-5.2"
PROVIDER_KEY_ENV = {
    "openai": "OPENAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "opencode_go": "OPENCODE_GO_API_KEY",
}
PROVIDER_ENDPOINT = {
    "openai": OPENAI_ENDPOINT,
    "openrouter": OPENROUTER_ENDPOINT,
    "deepseek": DEEPSEEK_ENDPOINT,
    "opencode_go": OPENCODE_GO_ENDPOINT,
}
#: Providers where a plain {"type": "json_object"} is the safe choice —
#: either the API doesn't support OpenAI's strict json_schema format
#: (deepseek), or it fronts multiple backends with no single guarantee they
#: all do (opencode_go). See OpenAICompatibleClient.complete_json.
_JSON_OBJECT_ONLY_PROVIDERS = frozenset({"deepseek", "opencode_go"})


@dataclass(frozen=True)
class AuditCard:
    card_id: str
    regime_name: str
    user_index: int
    arm_name: str
    recipe_id: str
    missing_count: int
    has_ready_meal_alternative: bool
    features: ResponseFeatures
    context: ResponseContext

    @property
    def stratum(self) -> tuple[str, int, bool]:
        return (self.regime_name, self.missing_count, self.has_ready_meal_alternative)


@dataclass(frozen=True)
class LLMDecision:
    action: UserAction
    confidence: float
    reason_code: str


class LLMClient(Protocol):
    model: str

    def decide(self, features: ResponseFeatures) -> LLMDecision: ...


def card_id(regime_name: str, user_index: int, arm_name: str, recipe_id: str) -> str:
    """Stable card identity; do not replace this with Python's randomized hash()."""
    return f"card-{stable_seed(regime_name, user_index, arm_name, recipe_id):08x}"


def _feature_payload(features: ResponseFeatures) -> dict[str, object]:
    # Explicit allowlist: profile, request, model score and arm never cross it.
    return asdict(features) | {"mode": features.mode.value}


def cache_key(features: ResponseFeatures, *, model: str, prompt_version: str = PROMPT_VERSION) -> str:
    payload = json.dumps(
        {"features": _feature_payload(features), "model": model, "prompt_version": prompt_version},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    # stable_seed is the repository's required stable primitive; SHA only makes
    # the disk filename collision-resistant and readable by other processes.
    stable = stable_seed(payload.decode("utf-8"))
    return f"{stable:08x}-{hashlib.sha256(payload).hexdigest()}"


class JsonCache:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.data: dict[str, dict[str, object]] = (
            json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        )

    def get(self, key: str) -> LLMDecision | None:
        value = self.data.get(key)
        if value is None:
            return None
        return parse_decision(value)

    def put(self, key: str, decision: LLMDecision) -> None:
        self.data[key] = {"action": decision.action.value, "confidence": decision.confidence, "reason_code": decision.reason_code}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def parse_decision(raw: object) -> LLMDecision:
    if not isinstance(raw, dict):
        raise ValueError("LLM response must be an object")
    try:
        action = UserAction(str(raw["action"]).strip().lower())
        confidence = float(raw["confidence"])
        reason_code = str(raw["reason_code"]).strip()
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("LLM response needs valid action, confidence and reason_code") from error
    if not 0 <= confidence <= 1 or not reason_code:
        raise ValueError("LLM confidence must be 0..1 and reason_code non-empty")
    return LLMDecision(action, confidence, reason_code)


class MockLLMClient:
    """Free deterministic stand-in used exclusively by dry-run and tests."""
    model = "mock"

    def decide(self, features: ResponseFeatures) -> LLMDecision:
        if features.ready_is_cheaper:
            action = UserAction.SUBSTITUTE
            reason = "ready_meal_value"
        elif features.missing_count == 0 or features.is_saved:
            action = UserAction.BUY
            reason = "low_effort_or_saved"
        elif features.missing_count <= 2:
            action = UserAction.SAVE
            reason = "manageable_list"
        elif features.prep_minutes > 45:
            action = UserAction.IGNORE
            reason = "high_effort"
        else:
            action = UserAction.CLICK
            reason = "needs_detail"
        return LLMDecision(action, 0.70, reason)


class OpenAICompatibleClient:
    """Minimal JSON client for OpenAI-compatible chat-completion APIs.

    ``provider`` is part of the public identity because the same model name
    routed through two providers is not the same experimental condition.
    OpenRouter uses the same wire format, but a different endpoint, key and
    optional attribution headers. No key is ever accepted by a CLI argument
    or written to the cache.
    """

    def __init__(
        self,
        model: str,
        api_key: str,
        endpoint: str = OPENAI_ENDPOINT,
        *,
        provider: str = "openai",
        extra_headers: dict[str, str] | None = None,
        timeout: float = 120.0,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.endpoint = endpoint
        self.provider = provider
        self.extra_headers = dict(extra_headers or {})
        #: Read timeout for one call. Was a hardcoded 45s — too short for some
        #: opencode_go backends (GLM-5.2 answered a trivial one-word prompt
        #: with 830 completion tokens in manual testing); _with_retries still
        #: retries 3x, so a genuinely dead connection fails in ~3x this, not
        #: hangs forever.
        self.timeout = timeout

    @property
    def cache_identity(self) -> str:
        return f"{self.provider}:{self.endpoint}:{self.model}"

    @classmethod
    def from_provider(
        cls,
        provider: str,
        model: str,
        api_key: str,
        *,
        endpoint: str | None = None,
    ) -> "OpenAICompatibleClient":
        if provider not in PROVIDER_ENDPOINT:
            raise ValueError(f"unknown provider {provider!r}")
        headers: dict[str, str] = {}
        if provider == "openrouter":
            if referer := os.environ.get("OPENROUTER_HTTP_REFERER"):
                headers["HTTP-Referer"] = referer
            if title := os.environ.get("OPENROUTER_APP_TITLE"):
                headers["X-OpenRouter-Title"] = title
        elif provider == "opencode_go":
            # OpenCode Go's abuse filter explicitly requires a real User-Agent
            # (urllib's default "Python-urllib/x.y" is exactly the generic
            # value it flags) and an x-opencode-session header for prompt-
            # cache routing; requests without both were observed failing with
            # HTTP 403. One session id per client instance, stable across
            # every call a live run makes — not per-request, since these
            # calls share one system prompt and are the closest thing this
            # script has to one logical session.
            headers["User-Agent"] = (
                "x5-loyalty-recsys-llm-intent-eval/1.0 "
                "(+https://github.com/x5-loyalty-hackathon/x5_loyalty_system)"
            )
            headers["x-opencode-session"] = f"llm-intent-eval-{uuid.uuid4()}"
        return cls(
            model,
            api_key,
            endpoint or PROVIDER_ENDPOINT[provider],
            provider=provider,
            extra_headers=headers,
        )

    def complete_json(
        self,
        *,
        system_prompt: str,
        payload: object,
        response_schema: dict[str, object] | None = None,
        schema_name: str = "decision",
        temperature: float = 0.0,
        seed: int | None = None,
    ) -> dict[str, object]:
        """Return one parsed JSON object, optionally constrained by schema."""
        response_format: dict[str, object]
        if response_schema is None or self.provider in _JSON_OBJECT_ONLY_PROVIDERS:
            # The direct DeepSeek API supports JSON mode, but not OpenAI's
            # JSON-schema response format. opencode_go fronts many different
            # open-weight backends behind one endpoint, with no single
            # guarantee all of them honor strict json_schema the same way an
            # OpenAI model does. The caller still validates every field
            # locally, so malformed or semantically invalid answers are
            # retried instead of entering the experiment.
            response_format = {"type": "json_object"}
        else:
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": response_schema,
                },
            }
        body: dict[str, object] = {
            "model": self.model,
            "temperature": temperature,
            "response_format": response_format,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
        }
        if seed is not None and self.provider not in _JSON_OBJECT_ONLY_PROVIDERS:
            body["seed"] = seed
        if response_schema is not None and self.provider == "openrouter":
            # OpenRouter may route a model through several providers. Refuse
            # a route that would silently ignore the JSON-schema requirement.
            body["provider"] = {"require_parameters": True}
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            **self.extra_headers,
        }
        request = urllib.request.Request(
            self.endpoint, data=json.dumps(body).encode(), headers=headers
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:  # nosec B310: explicit user opt-in
            data = json.loads(response.read())
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content) if isinstance(content, str) else content
        if not isinstance(parsed, dict):
            raise ValueError("LLM response content must be a JSON object")
        return parsed

    def decide(self, features: ResponseFeatures) -> LLMDecision:
        raw = self.complete_json(
            system_prompt=(
                "Choose one action: ignore, click, save, buy, substitute. "
                "Return JSON action, confidence 0..1, reason_code. Use only "
                "the supplied visible card features."
            ),
            payload=_feature_payload(features),
        )
        return parse_decision(raw)


def collect_cards(*, users_per_regime: int = 40, seed: int = 20260905, regimes: tuple[Regime, ...] = REGIMES) -> list[AuditCard]:
    """Generate cards with the explicit shipped arm: heuristic/effort."""
    arm_name = "heuristic/effort"
    service = RecommendationService(engine=DeterministicMockEngine(), safety_policy=SafetyPolicy(), ranking_policy=EFFORT_FIRST)
    recipes = list(RECIPES)
    recipe_by_id = {recipe.recipe_id: recipe for recipe in recipes}
    meals = ready_meal_options(recipe_by_id)
    cards: list[AuditCard] = []
    for regime_index, regime in enumerate(regimes):
        params_by_name = regime.archetypes()
        profiles = generate_population(users_per_regime, seed=seed + regime_index, archetypes=params_by_name)
        inventory_rng = random.Random(seed + 100_000 + regime_index)
        for user_index, profile in enumerate(profiles):
            inventory = generate_inventory(inventory_rng, now=profile.now, home_store_id=profile.current_receipt.store_id, user_radius_km=profile.user.radius_km)
            request = _build_request(profile, recipes, inventory, meals)
            for card in service.recommend(request).recommendations:
                recipe = recipe_by_id[card.recipe_id]
                features = extract_features(card, recipe, is_saved=card.recipe_id in profile.user.saved_recipe_ids)
                cards.append(AuditCard(card_id(regime.name, user_index, arm_name, recipe.recipe_id), regime.name, user_index, arm_name, recipe.recipe_id, card.missing_count, card.ready_meal_alternative is not None, features, ResponseContext(profile, params_by_name[profile.archetype], recipe, features, request, random.Random(stable_seed(seed, regime.name, user_index, card.recipe_id)))))
    return cards


def stratified_sample(cards: Iterable[AuditCard], size: int, *, seed: int = 20260905) -> list[AuditCard]:
    """Keep every non-empty stratum once, then allocate the remainder evenly.

    This intentionally oversamples rare strata; aggregate metrics must use
    ``population_weights`` to return to the generated population.
    """
    groups: dict[tuple[str, int, bool], list[AuditCard]] = defaultdict(list)
    for card in cards:
        groups[card.stratum].append(card)
    if size <= 0:
        return []
    rng = random.Random(seed)
    selected: list[AuditCard] = []
    shuffled = {key: rng.sample(items, k=len(items)) for key, items in groups.items()}
    keys = sorted(shuffled)
    # Coverage is a correctness property, so a request smaller than the number
    # of observed strata is expanded rather than silently dropping rare cells.
    target = max(size, len(keys))
    for key in keys:
        selected.append(shuffled[key].pop())
    while len(selected) < target and any(shuffled.values()):
        for key in keys:
            if shuffled[key] and len(selected) < target:
                selected.append(shuffled[key].pop())
    return selected


def population_weights(population: Iterable[AuditCard], sample: Iterable[AuditCard]) -> dict[tuple[str, int, bool], float]:
    pop, chosen = Counter(card.stratum for card in population), Counter(card.stratum for card in sample)
    total = sum(pop.values())
    return {stratum: (pop[stratum] / total) / chosen[stratum] for stratum in chosen if chosen[stratum]}


def cohen_kappa(left: list[UserAction], right: list[UserAction]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("kappa needs equally sized non-empty labels")
    observed = sum(a == b for a, b in zip(left, right, strict=True)) / len(left)
    left_rates, right_rates = Counter(left), Counter(right)
    expected = sum(left_rates[action] * right_rates[action] for action in UserAction) / len(left) ** 2
    return 1.0 if expected == 1.0 and observed == 1.0 else (observed - expected) / (1 - expected)


def token_estimate(features: ResponseFeatures) -> tuple[int, int]:
    # Conservative offline estimate: serialized features + fixed instruction,
    # then a tiny strict JSON response. It is deliberately tokens, not currency:
    # pricing belongs to the selected provider/model and changes over time.
    input_tokens = max(1, (len(json.dumps(_feature_payload(features), ensure_ascii=False)) + 3) // 4) + 45
    return input_tokens, 24


def _responder_actions(card: AuditCard, samples: int = 20) -> tuple[dict[str, UserAction], float]:
    actions: dict[str, UserAction] = {}
    probabilistic_self_agreement = 1.0
    for responder in INDEPENDENT_RESPONDERS:
        if responder.name == "probabilistic":
            draws = [responder.respond(ResponseContext(card.context.profile, card.context.params, card.context.recipe, card.features, card.context.request, random.Random(stable_seed(card.card_id, responder.name, i)))) for i in range(samples)]
            modal, modal_count = Counter(draws).most_common(1)[0]
            actions[responder.name] = modal
            probabilistic_self_agreement = modal_count / samples
        else:
            actions[responder.name] = responder.respond(card.context)
    # The modal probability is its per-card self-agreement ceiling: an LLM
    # cannot agree with a fresh stochastic draw more reliably than the model
    # agrees with its own distribution.
    return actions, probabilistic_self_agreement


def _with_retries(decide: Callable[[], LLMDecision], *, retries: int = 5) -> LLMDecision:
    """Retry transport/model failures, never substitute an invented action.

    ``OSError`` (not just ``TimeoutError``, one of its subclasses) is the one
    to catch here: a live run against opencode_go crashed on
    ``http.client.RemoteDisconnected`` — a plain server-closed-the-connection
    reset, not a timeout, not wrapped in ``urllib.error.URLError`` by this
    Python version's ``http.client`` — with zero retries attempted, because
    neither superclass in the old, narrower tuple covered it.

    ``retries`` was 3 (0.25s/0.5s backoff, ~0.75s total) — too thin for a
    genuinely flaky path to opencode.ai: a live run hit 3 consecutive
    ``TimeoutError: ... The handshake operation timed out`` at the TLS layer,
    a real transient-connectivity failure the old, narrower exception tuple
    would not even have caught. 5 attempts (0.25/0.5/1/2/4s, ~7.75s total)
    gives an unstable path more time to recover before this run's cache
    write-through (see ``run_study``) discards the in-flight call.
    """
    for attempt in range(retries):
        try:
            return decide()
        except (urllib.error.URLError, OSError, ValueError):
            if attempt == retries - 1:
                raise
            time.sleep(0.25 * (2**attempt))
    raise AssertionError("unreachable")


def audit_report(rows: list[dict[str, object]], *, weights_by_stratum: dict[tuple[str, int, bool], float] | None = None) -> dict[str, object]:
    """Descriptive agreement report; disagreement is a review candidate, not error."""
    actions = [action.value for action in UserAction]
    llm = [UserAction(str(row["llm_action"])) for row in rows]
    simulators = {name: [UserAction(str(row["simulators"][name])) for row in rows] for name in ("rule_based", "probabilistic", "economic")}
    base_rate = max(Counter(llm).values(), default=0) / len(llm) if llm else 0.0
    agreement: dict[str, object] = {}
    def weight(row: dict[str, object]) -> float:
        if weights_by_stratum is None:
            return 1.0
        return weights_by_stratum[(str(row["world"]), int(row["missing_count"]), bool(row["has_ready_meal_alternative"]))]
    for name, values in simulators.items():
        matrix = {left: {right: 0 for right in actions} for left in actions}
        for expected, actual in zip(values, llm, strict=True):
            matrix[expected.value][actual.value] += 1
        total_weight = sum(weight(row) for row in rows)
        weighted = sum(weight(row) for row in rows if row["llm_action"] == row["simulators"][name]) / total_weight if total_weight else 0.0
        agreement[name] = {"n": len(llm), "raw_agreement": sum(a == b for a, b in zip(values, llm, strict=True)) / len(llm) if llm else 0.0, "population_weighted_raw_agreement": weighted, "cohen_kappa": cohen_kappa(values, llm) if llm else None, "confusion_matrix": matrix}
    between = {}
    for left_name, left in simulators.items():
        for right_name, right in simulators.items():
            if left_name < right_name:
                between[f"{left_name}__{right_name}"] = {"raw_agreement": sum(a == b for a, b in zip(left, right, strict=True)) / len(llm) if llm else 0.0, "cohen_kappa": cohen_kappa(left, right) if llm else None}
    groups: dict[str, dict[str, object]] = {}
    for label, selector in (("world", lambda row: str(row["world"])), ("missing_count", lambda row: str(row["missing_count"])), ("has_ready_meal_alternative", lambda row: str(row["has_ready_meal_alternative"]))):
        partitions: dict[str, list[dict[str, object]]] = defaultdict(list)
        for row in rows:
            partitions[selector(row)].append(row)
        groups[label] = {key: {"n": len(part), "llm_vs_simulator_raw_agreement": {name: sum(row["llm_action"] == row["simulators"][name] for row in part) / len(part) for name in simulators}} for key, part in partitions.items()}
    return {"n": len(rows), "llm_most_common_action_base_rate": base_rate, "probabilistic_self_agreement_ceiling_mean": sum(float(row["probabilistic_self_agreement_ceiling"]) for row in rows) / len(rows) if rows else None, "llm_vs_simulators": agreement, "simulator_pairwise": between, "breakdowns_unweighted": groups, "interpretation": "LLM is an independent observer, not ground truth; high-disagreement groups are candidates for manual blind-spot review."}


def run_audit(cards: list[AuditCard], client: LLMClient, cache: JsonCache, *, dry_run: bool, prompt_version: str = PROMPT_VERSION) -> tuple[list[dict[str, object]], dict[str, int]]:
    rows: list[dict[str, object]] = []
    calls = input_tokens = output_tokens = hits = 0
    for card in cards:
        key = cache_key(card.features, model=client.model, prompt_version=prompt_version)
        decision = cache.get(key)
        if decision is not None:
            hits += 1
        else:
            estimated_in, estimated_out = token_estimate(card.features)
            input_tokens += estimated_in
            output_tokens += estimated_out
            calls += 1
            decision = _with_retries(lambda: client.decide(card.features))
            # LLMResponder preserves the repository's "invalid is an error" rule.
            LLMResponder(lambda _: decision.action).respond(card.context)
            if not dry_run:
                cache.put(key, decision)
        actions, probabilistic_self_agreement = _responder_actions(card)
        rows.append({"card_id": card.card_id, "world": card.regime_name, "missing_count": card.missing_count, "has_ready_meal_alternative": card.has_ready_meal_alternative, "llm_action": decision.action.value, "confidence": decision.confidence, "reason_code": decision.reason_code, "simulators": {name: action.value for name, action in actions.items()}, "probabilistic_self_agreement_ceiling": probabilistic_self_agreement})
    if not dry_run:
        cache.save()
    return rows, {"planned_live_calls": calls, "cache_hits": hits, "estimated_input_tokens": input_tokens, "estimated_output_tokens": output_tokens, "estimated_total_tokens": input_tokens + output_tokens}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LLM audit of handwritten response simulators")
    parser.add_argument("--sample", type=int, default=500)
    parser.add_argument("--users-per-regime", type=int, default=40)
    parser.add_argument("--seed", type=int, default=20260905)
    parser.add_argument("--provider", choices=tuple(PROVIDER_ENDPOINT), default="openai")
    parser.add_argument("--model", default=None)
    parser.add_argument("--endpoint", default=None, help="Override the provider endpoint (advanced).")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--prompt-version", default=PROMPT_VERSION)
    parser.add_argument("--dry-run", action="store_true", help="Run everything with a local mock; never call a provider (recommended).")
    args = parser.parse_args(argv)
    model = args.model or {
        "openai": DEFAULT_MODEL,
        "openrouter": DEFAULT_OPENROUTER_MODEL,
        "deepseek": DEFAULT_DEEPSEEK_MODEL,
        "opencode_go": DEFAULT_OPENCODE_GO_MODEL,
    }[args.provider]
    key_env = PROVIDER_KEY_ENV[args.provider]
    if not args.dry_run and not os.environ.get(key_env):
        parser.error(
            f"real {args.provider} run requires {key_env} in the environment; "
            "use --dry-run for the free audit"
        )
    population = collect_cards(users_per_regime=args.users_per_regime, seed=args.seed)
    sample = stratified_sample(population, args.sample, seed=args.seed)
    client: LLMClient = (
        MockLLMClient()
        if args.dry_run
        else OpenAICompatibleClient.from_provider(
            args.provider, model, os.environ[key_env], endpoint=args.endpoint
        )
    )
    rows, plan = run_audit(sample, client, JsonCache(args.cache), dry_run=args.dry_run, prompt_version=args.prompt_version)
    print(json.dumps({"mode": "dry-run" if args.dry_run else "live", "provider": "mock" if args.dry_run else args.provider, "sampling_arm": "heuristic/effort", "population_cards": len(population), "sample_cards": len(sample), "plan": plan, "report": audit_report(rows, weights_by_stratum=population_weights(population, sample)), "rows": rows}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
