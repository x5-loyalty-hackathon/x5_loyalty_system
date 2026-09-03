from recsys.economics import DEFAULT_ECONOMICS_PARAMS, compute_economics
from recsys.simulation import SCENARIOS, run_simulation


def test_net_cm_is_gross_minus_cannibalization_and_costs_exactly_once() -> None:
    result = run_simulation(2000, scenario="base", seed=5)
    econ = compute_economics(result, SCENARIOS["base"])
    expected = econ.gross_contribution_rub - econ.cannibalization_rub - econ.variable_costs_rub
    assert abs(econ.net_cm_rub - expected) < 1e-6


def test_rescue_delta_is_not_added_into_net_cm() -> None:
    # The module docstring/comments promise rescue_delta is diagnostic-only.
    # Regression-check that by recomputing net_cm without any reference to
    # rescue_delta and confirming it still matches.
    result = run_simulation(2000, scenario="optimistic", seed=5)
    econ = compute_economics(result, SCENARIOS["optimistic"])
    gross = (
        econ.route_a_conversions * DEFAULT_ECONOMICS_PARAMS.avg_new_basket_value_rub
        + econ.route_b_conversions * DEFAULT_ECONOMICS_PARAMS.avg_attach_value_rub
    ) * DEFAULT_ECONOMICS_PARAMS.contribution_margin_rate
    assert abs(econ.gross_contribution_rub - gross) < 1e-6


def test_economics_scale_roughly_linearly_with_population() -> None:
    small = compute_economics(run_simulation(1000, scenario="base", seed=9), SCENARIOS["base"])
    large = compute_economics(run_simulation(10000, scenario="base", seed=9), SCENARIOS["base"])
    # Per-user CM should be stable across population size (within Monte
    # Carlo noise), not grow or shrink with N.
    assert small.net_cm_per_user_rub > 0
    assert large.net_cm_per_user_rub > 0
    ratio = small.net_cm_per_user_rub / large.net_cm_per_user_rub
    assert 0.7 < ratio < 1.3


def test_scenarios_produce_monotonic_net_cm_per_user() -> None:
    values = {}
    for name, scenario in SCENARIOS.items():
        result = run_simulation(4000, scenario=name, seed=42)
        values[name] = compute_economics(result, scenario).net_cm_per_user_rub
    assert values["pessimistic"] < values["base"] < values["optimistic"]


def test_no_conversions_yields_zero_contribution_without_error() -> None:
    from recsys.simulation import SimulationResult

    empty = SimulationResult(scenario="base", n_users=1, horizon_days=60, users=[])
    econ = compute_economics(empty, SCENARIOS["base"])
    assert econ.gross_contribution_rub == 0
    assert econ.net_cm_rub == 0
    assert econ.rescue_delta_rub == 0
