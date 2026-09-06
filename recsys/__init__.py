"""ML/Recsys & Evaluation contour: synthetic data, recommendation model,
evaluation, simulation and economics for the recipe-first X5 Domovoi PoC.

The serving modules use ``app.contracts`` (API 1.2) and implement the
``app.recommender.RecommendationEngine`` protocol. Offline benchmark drivers
use the isolated ``recsys.experimental`` compatibility layer instead; their
results are not evaluations of the serving API. See docs/integration-handoff.md.
"""
