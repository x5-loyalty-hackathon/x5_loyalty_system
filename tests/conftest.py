import pytest

from app.main import state_repository


@pytest.fixture(autouse=True)
def reset_demo_state() -> None:
    """Keep API tests deterministic despite the process-local demo repository."""
    state_repository.reset()
    yield
    state_repository.reset()
