"""Behavioural regimes: the *worlds* a recommender is judged in.

Why this exists
---------------
``recsys.experimental.profiles`` defines one population — four archetypes with fixed
parameters. Any A/B run against that single population answers "which arm wins
**in this one world**", and we have no way to know whether that world resembles
Пятёрочка. Two equally plausible worlds can rank recommenders in opposite
orders: in a high-novelty world a discovery-heavy recommender wins, in a
high-repeat world a conservative one does, and both A/B runs produce a
beautiful p-value. That is the identifiability problem, and no amount of extra
synthetic users fixes it — 10,000 users drawn from one world still describe one
world.

The response is to stop trying to pick the true world and instead sweep a grid
of them, then ask a different question: *in how many plausible worlds does B
beat A, and does the answer survive changing who is simulating the user?* A
result that holds across the grid is a robustness claim, which is what a
synthetic bench can honestly support. A result that holds in one cell is a
coincidence.

The grid
--------
Three dials, three levels each, fully crossed — 27 regimes. The dials are the
behavioural quantities that actually flip which recommender should win:

``novelty``
    Willingness to accept an unfamiliar recipe. Scales
    ``ArchetypeParams.discovery_acceptance``.
``promo``
    Sensitivity to markdown/price. Scales ``ArchetypeParams.markdown_affinity``.
``repeat``
    Strength of repeat-purchase behaviour. Scales
    ``ArchetypeParams.repeat_probability``.

Deliberately *not* varied: the archetype mixture itself. Moving both the
per-archetype parameters and the population weights at once makes a losing cell
uninterpretable — you cannot tell whether B lost because people got more
novelty-seeking or because there were simply more explorers. Mixture sweeps
belong in a separate, explicitly labelled experiment.

Level multipliers are wide on purpose (0.4x–2.0x). The grid is not a belief
about where the truth lies; it is a stress range chosen to *contain* it.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, replace

from recsys.experimental.profiles import ARCHETYPES, ArchetypeParams, ArchetypeTable

#: dial -> level -> multiplier applied to that dial's archetype parameter.
DIALS: dict[str, dict[str, float]] = {
    "novelty": {"low": 0.4, "mid": 1.0, "high": 2.0},
    "promo": {"low": 0.5, "mid": 1.0, "high": 1.6},
    "repeat": {"low": 0.5, "mid": 1.0, "high": 1.4},
}

#: The level every dial takes in the regime that reproduces ``ARCHETYPES``.
NEUTRAL_LEVEL = "mid"


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


@dataclass(frozen=True)
class Regime:
    """One behavioural world: a labelled point on the dial grid."""

    levels: tuple[tuple[str, str], ...]

    @property
    def name(self) -> str:
        return "/".join(f"{dial}={level}" for dial, level in self.levels)

    @property
    def level_map(self) -> dict[str, str]:
        return dict(self.levels)

    @property
    def is_neutral(self) -> bool:
        return all(level == NEUTRAL_LEVEL for _, level in self.levels)

    def multiplier(self, dial: str) -> float:
        return DIALS[dial][self.level_map[dial]]

    def archetypes(self) -> ArchetypeTable:
        """``ARCHETYPES`` as it looks inside this world.

        Only the three dialled parameters move; cadence, basket size, core
        categories and the population shares are held fixed so a cell's result
        is attributable to the dials and nothing else.
        """
        novelty = self.multiplier("novelty")
        promo = self.multiplier("promo")
        repeat = self.multiplier("repeat")
        return {
            name: replace(
                params,
                discovery_acceptance=_clamp(params.discovery_acceptance * novelty),
                markdown_affinity=_clamp(params.markdown_affinity * promo),
                repeat_probability=_clamp(params.repeat_probability * repeat),
            )
            for name, params in ARCHETYPES.items()
        }


def build_regimes() -> tuple[Regime, ...]:
    """The full crossed grid, neutral world first."""
    dial_names = tuple(DIALS)
    combos = itertools.product(*(DIALS[dial] for dial in dial_names))
    regimes = [
        Regime(levels=tuple(zip(dial_names, combo, strict=True))) for combo in combos
    ]
    regimes.sort(key=lambda regime: (not regime.is_neutral, regime.name))
    return tuple(regimes)


REGIMES: tuple[Regime, ...] = build_regimes()

NEUTRAL_REGIME: Regime = REGIMES[0]


def regimes_where(dial: str, level: str) -> tuple[Regime, ...]:
    """Every regime holding ``dial`` at ``level`` — the slice for a dial effect."""
    if dial not in DIALS:
        raise KeyError(f"unknown dial {dial!r}, expected one of {list(DIALS)}")
    if level not in DIALS[dial]:
        raise KeyError(f"unknown level {level!r} for dial {dial!r}")
    return tuple(r for r in REGIMES if r.level_map[dial] == level)


def archetype_for(regime: Regime, archetype_name: str) -> ArchetypeParams:
    return regime.archetypes()[archetype_name]
