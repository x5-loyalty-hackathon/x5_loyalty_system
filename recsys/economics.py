"""Economics on top of ``recsys.simulation`` output.

Implements the current recipe-first formulas from
``docs/research/persona_vxofi/rescue-domovoi-concept.md §12`` — *not* the
older reservation/bundle economics in
``docs/research/monetization/rescue-basket-economics.md``, which that
document itself scope-notes as superseded by the recipe-first pivot.

Route A (new purchase day) and route B (attached to an already-planned day)
contribute to ``ΔCM_user`` once each; cannibalization and variable costs are
then deducted once. ``Δrescue_item`` is reported separately as a *diagnostic*
on the markdown share only (borrowing the mutually-exclusive-baseline idea
from the older economics doc, at PoC-illustrative granularity) — it is not
added a second time into ``ΔCM_user``, matching the explicit no-double-count
warning in the source doc ("нельзя отдельно сложить маржу каждого
ингредиента и маржу всей корзины, если это один и тот же эффект").

Every rate below is a labeled illustrative demo constant pending X5 category
margin data (see the open questions in
``docs/research/persona_vxofi/rescue-domovoi-concept.md §20`` and
``docs/research/monetization/rescue-basket-economics.md §14``), not a
measured business figure — this module computes *internal consistency*
under stated assumptions, not a business case.
"""

from __future__ import annotations

from dataclasses import dataclass

from recsys.simulation import ScenarioParams, SimulationResult


@dataclass(frozen=True)
class EconomicsParams:
    contribution_margin_rate: float = 0.22  # illustrative grocery CM rate on realized revenue
    avg_new_basket_value_rub: float = 850.0  # route A: a whole additional shopping trip
    avg_attach_value_rub: float = 180.0  # route B: incremental missing-ingredient top-up
    markdown_baseline_sale_probability: float = 0.55  # P(unit sells anyway via the existing markdown shelf)
    variable_cost_per_conversion_rub: float = 8.0  # serving/data/support/fraud cost proxy


DEFAULT_ECONOMICS_PARAMS = EconomicsParams()


@dataclass
class EconomicsResult:
    scenario: str
    n_users: int
    horizon_days: int
    route_a_conversions: int
    route_b_conversions: int
    markdown_conversions: int
    full_price_conversions: int
    gross_contribution_rub: float
    cannibalization_rub: float
    variable_costs_rub: float
    net_cm_rub: float
    rescue_delta_rub: float  # diagnostic only — see module docstring

    @property
    def net_cm_per_user_rub(self) -> float:
        return self.net_cm_rub / self.n_users if self.n_users else 0.0

    @property
    def rescue_delta_per_markdown_conversion_rub(self) -> float:
        return self.rescue_delta_rub / self.markdown_conversions if self.markdown_conversions else 0.0

    def summary(self) -> str:
        return "\n".join(
            [
                f"scenario: {self.scenario}, users: {self.n_users}, horizon: {self.horizon_days}d",
                f"conversions: route_a={self.route_a_conversions} route_b={self.route_b_conversions} "
                f"(markdown={self.markdown_conversions}, full_price={self.full_price_conversions})",
                f"gross_contribution: {self.gross_contribution_rub:,.0f} RUB",
                f"cannibalization: -{self.cannibalization_rub:,.0f} RUB, "
                f"variable_costs: -{self.variable_costs_rub:,.0f} RUB",
                f"net_CM: {self.net_cm_rub:,.0f} RUB "
                f"({self.net_cm_per_user_rub:,.2f} RUB/eligible user over {self.horizon_days}d)",
                f"rescue_delta (diagnostic, markdown only): {self.rescue_delta_rub:,.0f} RUB "
                f"({self.rescue_delta_per_markdown_conversion_rub:,.1f} RUB/markdown conversion)",
            ]
        )


def compute_economics(
    result: SimulationResult,
    scenario: ScenarioParams,
    params: EconomicsParams = DEFAULT_ECONOMICS_PARAMS,
) -> EconomicsResult:
    total_route_a = sum(u.route_a_conversions for u in result.users)
    total_route_b = sum(u.route_b_conversions for u in result.users)
    total_markdown = sum(u.markdown_conversions for u in result.users)
    total_full_price = sum(u.full_price_conversions for u in result.users)

    route_a_contribution = total_route_a * params.avg_new_basket_value_rub * params.contribution_margin_rate
    route_b_contribution = total_route_b * params.avg_attach_value_rub * params.contribution_margin_rate
    gross_contribution = route_a_contribution + route_b_contribution

    total_conversions = total_route_a + total_route_b
    variable_costs = total_conversions * params.variable_cost_per_conversion_rub
    cannibalization = scenario.cannibalization_rate * gross_contribution

    net_cm = gross_contribution - cannibalization - variable_costs

    markdown_realized_value = total_markdown * params.avg_attach_value_rub * params.contribution_margin_rate
    markdown_baseline_value = (
        total_markdown
        * params.markdown_baseline_sale_probability
        * params.avg_attach_value_rub
        * params.contribution_margin_rate
    )
    rescue_delta = markdown_realized_value - markdown_baseline_value

    return EconomicsResult(
        scenario=scenario.name,
        n_users=result.n_users,
        horizon_days=result.horizon_days,
        route_a_conversions=total_route_a,
        route_b_conversions=total_route_b,
        markdown_conversions=total_markdown,
        full_price_conversions=total_full_price,
        gross_contribution_rub=gross_contribution,
        cannibalization_rub=cannibalization,
        variable_costs_rub=variable_costs,
        net_cm_rub=net_cm,
        rescue_delta_rub=rescue_delta,
    )


if __name__ == "__main__":
    from recsys.simulation import SCENARIOS, run_simulation

    for n in (1_000, 10_000):
        print(f"=== N={n} ===")
        for name, scenario in SCENARIOS.items():
            result = run_simulation(n, scenario=name)
            econ = compute_economics(result, scenario)
            print(econ.summary())
            print()
