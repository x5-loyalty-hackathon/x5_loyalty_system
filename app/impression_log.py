"""What must be written down at serve time so the log is still useful later.

The one thing that cannot be added afterwards
---------------------------------------------
Every other gap in this project is repairable: features can be recomputed,
labels re-derived, panels rebuilt. Logging is not. If the service ships,
serves for three months and logs only "user U was shown recipe R and clicked",
then in month four every question worth asking is unanswerable:

* *Would policy B have done better?* Needs the candidates B would have picked,
  and their probability of having been shown. Not in the log.
* *Was the model or the ranking policy responsible?* Needs the scores before
  the policy reordered them. Not in the log.
* *Did people ignore position 3 because it was bad, or because it was third?*
  Needs positions. Not in the log.

None of it can be reconstructed later, because the data was never created.
This module is the schema that prevents that, plus the estimator that proves
the schema is sufficient — a schema nobody has run an estimator against is a
guess.

Propensity is the part teams get wrong
--------------------------------------
Off-policy estimation divides by the probability the logging policy had of
showing what it showed. A deterministic top-3 assigns probability 1 to three
recipes and 0 to everything else, so the estimator either divides by zero or
silently evaluates only the arm you already ran — which is not an evaluation.

The fix has to be in the *serving* path, not in the analysis: a small share of
traffic must be randomised, and the randomisation probability logged. That is a
product decision (a few percent of users see a slightly worse slate) bought in
exchange for being able to evaluate every future model without a new A/B.
``ExplorationPolicy`` below makes that trade explicit and computable rather
than leaving it as an intention.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

CONTRACT_VERSION = "1.0"


class LogModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScoredCandidate(LogModel):
    """One recipe the ranker considered — shown or not.

    Unshown candidates are logged too. They are what makes a counterfactual
    question answerable: "policy B would have picked recipe 7" is only checkable
    if recipe 7's score was recorded when it lost.
    """

    recipe_id: str = Field(min_length=1)
    #: The ranker's raw score, before any policy reordering.
    model_score: float
    #: Position in the final served slate, 0-based. ``None`` when not shown.
    position: int | None = Field(default=None, ge=0)
    #: Probability the logging policy had of showing this recipe at all. The
    #: denominator of every off-policy estimate; never 0 for a shown item.
    propensity: float = Field(gt=0.0, le=1.0)
    missing_count: int = Field(ge=0)
    #: Why the service dropped it, when it did. ``app.service`` already
    #: produces these strings; logging them turns "the slate was short" into
    #: "the slate was short because 12 recipes had no safe product".
    filtered_reason: str | None = None
    #: The feature vector as of decision time. Logged rather than recomputed:
    #: a recomputation months later runs different code against different
    #: reference data and quietly answers a different question.
    features: dict[str, float] = Field(default_factory=dict)


class ImpressionEvent(LogModel):
    """One request, everything the ranker saw, and everything it chose."""

    contract_version: str = CONTRACT_VERSION
    request_id: str = Field(min_length=1)
    #: Pseudonymous. The join key for outcomes, not an identity.
    user_ref: str = Field(min_length=1)
    served_at: datetime
    #: What produced the scores, and what reordered them. Two separate axes —
    #: ADR-002 exists because they were conflated once already.
    model_version: str = Field(min_length=1)
    ranking_policy: str = Field(min_length=1)
    #: True when this request was served by the randomised branch.
    is_exploration: bool = False
    exploration_rate: float = Field(ge=0.0, le=1.0)
    candidates: list[ScoredCandidate] = Field(min_length=1)
    #: Empty slate is a real, common outcome (measured at 35% under scarcity),
    #: so it must be representable rather than an absent row.
    shown_recipe_ids: list[str] = Field(default_factory=list)

    @property
    def is_empty_slate(self) -> bool:
        return not self.shown_recipe_ids


class OutcomeEvent(LogModel):
    """What happened afterwards, joined back by ``request_id``.

    Separate from the impression because it arrives later — a cook happens days
    after the card was shown. A schema that expects the outcome at serve time
    forces the join to be lost.
    """

    contract_version: str = CONTRACT_VERSION
    request_id: str = Field(min_length=1)
    recipe_id: str = Field(min_length=1)
    occurred_at: datetime
    #: "click", "add_to_cart", "purchase", "cooked", ... Free-form on purpose:
    #: the vocabulary will grow, and a closed enum forces a migration to add
    #: one event.
    action: str = Field(min_length=1)
    #: Monetary value where one exists, so revenue-weighted estimates are
    #: possible without a second pipeline.
    value_rub: float | None = Field(default=None, ge=0)


@dataclass(frozen=True)
class ExplorationPolicy:
    """Serve the ranked slate, except sometimes on purpose serve a random one.

    ``rate`` is the share of requests served randomly. It buys the only thing
    that makes future models evaluable without a fresh experiment; it costs
    those users a worse slate. At 0.0 the log is still readable but
    off-policy estimation is impossible, and ``propensities`` says so by
    returning 0 for everything unshown.
    """

    rate: float = 0.05
    slate_size: int = 3

    def propensities(
        self, ranked_recipe_ids: list[str], *, n_eligible: int
    ) -> dict[str, float]:
        """P(recipe is shown) for every eligible recipe under this policy.

        Mixture of two branches: with probability ``1 - rate`` the top-k is
        served deterministically, with probability ``rate`` a uniform sample of
        k from the eligible set. So a top-k recipe carries almost all of its
        mass from the greedy branch, and everything else carries a small but
        crucially **non-zero** mass from the random one.
        """
        if n_eligible <= 0:
            return {}
        k = min(self.slate_size, n_eligible)
        uniform = k / n_eligible
        top = set(ranked_recipe_ids[:k])
        return {
            recipe_id: (1.0 - self.rate) * (1.0 if recipe_id in top else 0.0)
            + self.rate * uniform
            for recipe_id in ranked_recipe_ids
        }

    def choose(
        self, ranked_recipe_ids: list[str], rng: random.Random
    ) -> tuple[list[str], bool]:
        """The slate actually served, and whether this was an exploration draw."""
        k = min(self.slate_size, len(ranked_recipe_ids))
        if rng.random() < self.rate:
            return rng.sample(ranked_recipe_ids, k=k), True
        return ranked_recipe_ids[:k], False


# --- off-policy estimation -------------------------------------------------


@dataclass
class OffPolicyEstimate:
    """What a logged period says a *different* policy would have scored."""

    ips: float
    #: Self-normalised IPS. Lower variance and far less prone to the blow-ups
    #: plain IPS produces when a new policy likes something the logger rarely
    #: showed. Report both: a large gap between them is itself the warning that
    #: the estimate rests on a handful of high-weight records.
    snips: float
    n_impressions: int
    n_matched: int
    #: Share of the estimate carried by the single heaviest record. Above ~0.1
    #: the number is one user's opinion wearing a mean's clothing.
    max_weight_share: float
    effective_sample_size: float
    warnings: list[str] = field(default_factory=list)


def estimate_policy_value(
    impressions: list[ImpressionEvent],
    outcomes: list[OutcomeEvent],
    new_policy_slate: dict[str, list[str]],
    *,
    rewarded_actions: frozenset[str] = frozenset({"cooked"}),
    weight_clip: float = 10.0,
) -> OffPolicyEstimate:
    """Inverse-propensity estimate of a policy that was never served.

    ``new_policy_slate`` maps ``request_id`` to what the candidate policy would
    have shown for that same request — computed offline by replaying the logged
    candidates through it.

    Weights are clipped. Unclipped IPS is unbiased and useless in practice: one
    record with propensity 0.01 contributes a weight of 100 and the "estimate"
    becomes that record. Clipping trades a little bias for an answer that does
    not move when one user sneezes.
    """
    reward_by_request: dict[str, dict[str, float]] = {}
    for outcome in outcomes:
        if outcome.action not in rewarded_actions:
            continue
        bucket = reward_by_request.setdefault(outcome.request_id, {})
        bucket[outcome.recipe_id] = bucket.get(outcome.recipe_id, 0.0) + 1.0

    weights: list[float] = []
    weighted_rewards: list[float] = []
    matched = 0
    warnings: list[str] = []

    for impression in impressions:
        target_slate = new_policy_slate.get(impression.request_id)
        if target_slate is None:
            continue
        matched += 1
        propensity_by_recipe = {c.recipe_id: c.propensity for c in impression.candidates}
        rewards = reward_by_request.get(impression.request_id, {})

        for recipe_id in impression.shown_recipe_ids:
            propensity = propensity_by_recipe.get(recipe_id)
            if propensity is None or propensity <= 0.0:
                warnings.append(
                    f"{impression.request_id}: shown recipe {recipe_id} has no "
                    f"usable propensity — this record cannot be reweighted"
                )
                continue
            target_indicator = 1.0 if recipe_id in target_slate else 0.0
            weight = min(target_indicator / propensity, weight_clip)
            weights.append(weight)
            weighted_rewards.append(weight * rewards.get(recipe_id, 0.0))

    n = len(weights)
    if not n:
        return OffPolicyEstimate(
            ips=0.0,
            snips=0.0,
            n_impressions=len(impressions),
            n_matched=matched,
            max_weight_share=0.0,
            effective_sample_size=0.0,
            warnings=[*warnings, "no reweightable records: is exploration switched on?"],
        )

    total_weight = sum(weights)
    if total_weight <= 0.0:
        # Every weight is zero: the challenger's picks were logged, but never
        # *shown*, so no record carries evidence about them. Distinct from
        # "no matching records" above and it has the same cause — a logging
        # policy that never deviated from its own ranking.
        return OffPolicyEstimate(
            ips=0.0,
            snips=0.0,
            n_impressions=len(impressions),
            n_matched=matched,
            max_weight_share=0.0,
            effective_sample_size=0.0,
            warnings=[
                *warnings,
                "the challenger's picks were never shown: this log supports no "
                "counterfactual — is exploration switched on?",
            ],
        )

    ips = sum(weighted_rewards) / n
    snips = sum(weighted_rewards) / total_weight
    max_share = max(weights) / total_weight
    # Kish effective sample size: how many equally-weighted records this
    # weighted sample is actually worth.
    ess = (total_weight**2) / sum(w * w for w in weights)

    if max_share > 0.1:
        warnings.append(
            f"one record carries {max_share:.0%} of the weight — the estimate is "
            f"not a population mean"
        )
    if ess < 0.1 * n:
        warnings.append(
            f"effective sample size {ess:.0f} against {n} records: variance is "
            f"dominated by a few high-weight impressions"
        )
    return OffPolicyEstimate(
        ips=ips,
        snips=snips,
        n_impressions=len(impressions),
        n_matched=matched,
        max_weight_share=max_share,
        effective_sample_size=ess,
        warnings=warnings,
    )


def build_impression_event(
    *,
    request_id: str,
    user_ref: str,
    served_at: datetime,
    model_version: str,
    ranking_policy: str,
    ranked: list,
    response,
    policy: ExplorationPolicy,
    shown_recipe_ids: list[str],
    is_exploration: bool,
    features_by_recipe: dict[str, dict[str, float]] | None = None,
) -> ImpressionEvent:
    """Turn one real serve into one log record.

    ``ranked`` is the engine's own output (``list[ModelRecommendation]``) — the
    order *before* ``RankingPolicy`` touched it — and ``response`` is what the
    service actually returned. Both are needed: the difference between them is
    precisely the service-logic effect experiment 2 had to reconstruct after
    the fact, and logging both means nobody has to reconstruct it again.
    """
    filter_reasons: dict[str, str] = {}
    for warning in getattr(response, "warnings", []):
        # ``app.service`` emits "recipe <id> filtered: <reason>".
        if warning.startswith("recipe ") and " filtered: " in warning:
            body = warning[len("recipe ") :]
            recipe_id, _, reason = body.partition(" filtered: ")
            filter_reasons[recipe_id] = reason

    assembled = {card.recipe_id: card for card in response.recommendations}
    ranked_ids = [item.recipe_id for item in ranked]
    propensities = policy.propensities(ranked_ids, n_eligible=len(ranked_ids))
    position_of = {recipe_id: i for i, recipe_id in enumerate(shown_recipe_ids)}

    candidates = [
        ScoredCandidate(
            recipe_id=item.recipe_id,
            model_score=item.score,
            position=position_of.get(item.recipe_id),
            # Floor rather than 0: a shown item with propensity 0 is
            # unusable, and a silent 0 becomes a division by zero months
            # later in someone else's notebook.
            propensity=max(propensities.get(item.recipe_id, 0.0), 1e-6),
            missing_count=(
                assembled[item.recipe_id].missing_count
                if item.recipe_id in assembled
                else 0
            ),
            filtered_reason=filter_reasons.get(item.recipe_id),
            features=(features_by_recipe or {}).get(item.recipe_id, {}),
        )
        for item in ranked
    ]
    return ImpressionEvent(
        request_id=request_id,
        user_ref=user_ref,
        served_at=served_at,
        model_version=model_version,
        ranking_policy=ranking_policy,
        is_exploration=is_exploration,
        exploration_rate=policy.rate,
        candidates=candidates,
        shown_recipe_ids=list(shown_recipe_ids),
    )


def log_completeness(impressions: list[ImpressionEvent]) -> dict[str, float]:
    """Is this log actually usable for off-policy work, or only for dashboards?

    Meant to run as a monitor. Every field it checks is one that cannot be
    backfilled, so a regression here has a deadline: it is only fixable before
    the next batch of traffic is served, never after.
    """
    if not impressions:
        return {}
    total = len(impressions)
    explored = sum(1 for i in impressions if i.is_exploration)
    with_features = sum(
        1 for i in impressions if any(c.features for c in i.candidates)
    )
    with_unshown = sum(
        1 for i in impressions if any(c.position is None for c in i.candidates)
    )
    degenerate = sum(
        1
        for i in impressions
        for c in i.candidates
        if c.position is not None and c.propensity >= 1.0
    )
    return {
        "exploration_share": explored / total,
        "features_logged_share": with_features / total,
        "unshown_candidates_share": with_unshown / total,
        "empty_slate_share": sum(1 for i in impressions if i.is_empty_slate) / total,
        "deterministic_shown_records": float(degenerate),
    }
