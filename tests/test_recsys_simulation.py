from recsys.simulation import SCENARIOS, run_simulation


def test_base_and_pessimistic_scenarios_have_zero_induced_purchase_days() -> None:
    # docs/research/persona_vxofi/rescue-domovoi-concept.md §18: base case
    # assumes Δpurchase_days = 0.
    for scenario in ("base", "pessimistic"):
        result = run_simulation(500, scenario=scenario, seed=1)
        assert result.mean_extra_purchase_days() == 0.0


def test_optimistic_scenario_allows_positive_induced_purchase_days() -> None:
    result = run_simulation(2000, scenario="optimistic", seed=1)
    assert result.mean_extra_purchase_days() > 0.0


def test_simulation_is_deterministic_given_a_seed() -> None:
    a = run_simulation(300, scenario="base", seed=77)
    b = run_simulation(300, scenario="base", seed=77)
    assert a.funnel_totals() == b.funnel_totals()
    assert a.mean_purchase_days() == b.mean_purchase_days()


def test_funnel_stages_never_increase_down_the_funnel() -> None:
    result = run_simulation(500, scenario="optimistic", seed=3)
    for user in result.users:
        assert user.impressions >= user.opens >= user.saves >= user.conversions
        assert user.conversions == user.route_a_conversions + user.route_b_conversions
        assert user.conversions == user.markdown_conversions + user.full_price_conversions


def test_scales_to_ten_thousand_users_without_error() -> None:
    result = run_simulation(10_000, scenario="base", seed=2026)
    assert len(result.users) == 10_000
    assert result.mean_purchase_days() > 0


def test_scenarios_are_monotonic_in_relevance_and_availability() -> None:
    results = {name: run_simulation(4000, scenario=name, seed=42) for name in SCENARIOS}
    totals = {name: r.funnel_totals() for name, r in results.items()}
    assert totals["pessimistic"]["conversions"] < totals["base"]["conversions"] < totals["optimistic"]["conversions"]
    assert (
        results["pessimistic"].markdown_conversion_share()
        < results["base"].markdown_conversion_share()
        < results["optimistic"].markdown_conversion_share()
    )
