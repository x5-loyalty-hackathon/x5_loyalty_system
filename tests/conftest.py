import pytest

from app.main import state_repository


@pytest.fixture(autouse=True)
def reset_demo_state() -> None:
    """Keep API tests deterministic despite the process-local demo repository."""
    state_repository.reset()
    yield
    state_repository.reset()


@pytest.fixture(scope="session")
def ml_engine():
    """Train recsys.model.MLRecommendationEngine once per test session.

    Training is deterministic (fixed seed) and takes ~1s; sharing one
    instance across recsys tests avoids retraining it per test function.
    """
    from recsys.model import MLRecommendationEngine

    return MLRecommendationEngine()
