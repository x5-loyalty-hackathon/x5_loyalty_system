"""The assumption sweep, and the metric trap it uncovered."""

from __future__ import annotations

import pytest

from recsys.benchmark import Arm, RandomEngine, run_benchmark
from recsys.inventory import (
    DEFAULT_INVENTORY_ASSUMPTIONS,
    InventoryAssumptions,
    generate_inventory,
)
from recsys.profiles import ARCHETYPES
from recsys.regimes import NEUTRAL_REGIME, REGIMES
from recsys.response_models import EconomicResponder, RuleBasedResponder
from recsys.sensitivity import (
    CLAIMS,
    DIALS,
    Observation,
    Setting,
    ToleranceShiftedRegime,
    fragile_claims,
    run_sweep,
    sensitivity_arms,
)

SMALL_REGIMES = REGIMES[:2]
RESPONDERS = (RuleBasedResponder(), EconomicResponder())


# --- the dials themselves -------------------------------------------------


def test_every_dial_brackets_the_shipped_value() -> None:
    """A sweep without the current setting has nothing to compare against."""
    for dial in DIALS:
        assert len(dial.settings) >= 3
        baselines = [s for s in dial.settings if "наш" in s.label]
        assert len(baselines) == 1, f"{dial.name} needs exactly one baseline"
        assert dial.question.endswith("?")


def test_dial_names_are_unique() -> None:
    names = [d.name for d in DIALS]
    assert len(names) == len(set(names))


def test_claim_keys_are_unique() -> None:
    keys = [c.key for c in CLAIMS]
    assert len(keys) == len(set(keys))


# --- assumptions actually reach the generated world -----------------------


def test_inventory_assumptions_change_the_shelf() -> None:
    import random
    from datetime import datetime, timezone

    now = datetime(2026, 9, 5, tzinfo=timezone.utc)

    def shelf(assumptions: InventoryAssumptions):
        return generate_inventory(
            random.Random(1),
            now=now,
            home_store_id="s",
            user_radius_km=3.0,
            assumptions=assumptions,
        )

    base = shelf(DEFAULT_INVENTORY_ASSUMPTIONS)
    scarce = shelf(InventoryAssumptions(markdown_offered=0.02, no_product_at_all=0.5))
    assert len(scarce) < len(base)
    assert sum(1 for p in scarce if p.is_markdown) < sum(
        1 for p in base if p.is_markdown
    )

    dear = shelf(InventoryAssumptions(price_level=4.0))
    assert min(p.price for p in dear) > min(p.price for p in base)


def test_defaults_reproduce_the_shipped_behaviour() -> None:
    import random
    from datetime import datetime, timezone

    now = datetime(2026, 9, 5, tzinfo=timezone.utc)
    kwargs = dict(now=now, home_store_id="s", user_radius_km=3.0)
    without = generate_inventory(random.Random(3), **kwargs)
    with_defaults = generate_inventory(
        random.Random(3), assumptions=DEFAULT_INVENTORY_ASSUMPTIONS, **kwargs
    )
    assert [p.sku_id for p in without] == [p.sku_id for p in with_defaults]
    assert [p.price for p in without] == [p.price for p in with_defaults]


# --- tolerance dial -------------------------------------------------------


def test_tolerance_shift_moves_every_archetype_and_clamps_at_zero() -> None:
    up = ToleranceShiftedRegime(NEUTRAL_REGIME, 2).archetypes()
    for name, params in up.items():
        assert params.max_missing_tolerance == ARCHETYPES[name].max_missing_tolerance + 2

    floored = ToleranceShiftedRegime(NEUTRAL_REGIME, -99).archetypes()
    assert all(p.max_missing_tolerance == 0 for p in floored.values())


def test_shifted_regime_keeps_the_regime_name() -> None:
    """run_benchmark keys cells by name; a shift must not fork the identity."""
    shifted = ToleranceShiftedRegime(NEUTRAL_REGIME, 1)
    assert shifted.name == NEUTRAL_REGIME.name


# --- the metric trap ------------------------------------------------------


def test_per_card_and_per_user_metrics_can_disagree() -> None:
    """Scarcity raises conversion per card while lowering dinners per user.

    Fewer products means fewer recipes survive assembly, and the survivors are
    the easy ones. Comparing supply settings on the per-card rate would have
    reported a shortage as an improvement.
    """
    arms = (Arm(name="a", engine=RandomEngine()),)
    kwargs = dict(regimes=SMALL_REGIMES, responders=RESPONDERS, users_per_regime=12)

    base = run_benchmark(arms, **kwargs)
    scarce = run_benchmark(
        arms, inventory_assumptions=InventoryAssumptions(no_product_at_all=0.5), **kwargs
    )

    base_cards = sum(c.n_cards for c in base.cells)
    scarce_cards = sum(c.n_cards for c in scarce.cells)
    assert scarce_cards < base_cards, "scarcity must reduce the number of cards"

    for cell in base.cells:
        expected = cell.cook_conversion_rate * cell.cards_per_user
        assert cell.cooks_per_user == pytest.approx(expected)


def test_cooks_per_user_counts_only_cooking() -> None:
    from recsys.response_models import UserAction

    result = run_benchmark(
        (Arm(name="a", engine=RandomEngine()),),
        regimes=SMALL_REGIMES,
        responders=RESPONDERS,
        users_per_regime=8,
    )
    for cell in result.cells:
        buys = cell.counts.get(UserAction.BUY.value, 0)
        assert cell.cooks_per_user == pytest.approx(buys / cell.n_users)


# --- sweep mechanics ------------------------------------------------------


def test_identical_settings_are_computed_once_and_reused() -> None:
    """The shipped setting repeats across dials; recomputing it is pure waste."""
    observations = run_sweep(
        dials=DIALS[:2], regimes=SMALL_REGIMES, users=6, progress=False
    )
    baselines = [o for o in observations if o.is_baseline]
    assert len(baselines) == 2
    assert baselines[0].claims == baselines[1].claims
    assert baselines[0].arm_means == baselines[1].arm_means


def test_sweep_covers_every_dial_and_setting() -> None:
    observations = run_sweep(
        dials=DIALS[:2], regimes=SMALL_REGIMES, users=6, progress=False
    )
    assert len(observations) == sum(len(d.settings) for d in DIALS[:2])
    for observation in observations:
        assert set(observation.claims) == {c.key for c in CLAIMS}
        assert observation.arm_means
        assert observation.arm_cooks_per_user


def test_fragile_claims_names_the_dial_that_flipped_it() -> None:
    def obs(dial, setting, baseline, value):
        return Observation(
            dial=dial,
            setting=setting,
            is_baseline=baseline,
            claims={c.key: value for c in CLAIMS},
            arm_means={"a": 0.1},
            arm_cooks_per_user={"a": 0.2},
        )

    stable = [obs("d1", "наше", True, True), obs("d1", "low", False, True)]
    assert all(not v for v in fragile_claims(stable).values())

    flipped = stable + [obs("d2", "high", False, False)]
    for dials in fragile_claims(flipped).values():
        assert dials == ["d2"]


def test_sensitivity_arms_include_both_controls() -> None:
    arms = sensitivity_arms()
    controls = [a.name for a in arms if a.is_control]
    assert "random/effort" in controls
    assert "random/relevance" in controls
    assert len([a for a in arms if not a.is_control]) >= 2


def test_setting_defaults_are_the_shipped_assumptions() -> None:
    setting = Setting("наше допущение")
    assert setting.assumptions == DEFAULT_INVENTORY_ASSUMPTIONS
    assert setting.time_value_rub_per_hour is None
    assert setting.tolerance_shift == 0
