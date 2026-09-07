"""Wallpaper unlocks use the existing server rewards, never client XP."""
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
import pytest

from app.home_decoration import HomeDecorationItemLocked
from app.main import app, state_repository
from app.state import InMemoryStateRepository, UserProgressRecord
from tests import test_game_rewards as rewards


client = TestClient(app)
BASE = "/api/v1/home-decoration"
DEFAULT = "wallpaper_default"
MINT = "wallpaper_mint"
SUNSET = "wallpaper_sunset"
SKY = "wallpaper_sky"
NIGHT = "wallpaper_night"
BERRY = "wallpaper_berry"
CATALOG = [DEFAULT, MINT, SUNSET, SKY, NIGHT, BERRY]


def get_decoration(user_id: str = "decor-user") -> dict:
    response = client.get(f"{BASE}/{user_id}")
    assert response.status_code == 200, response.text
    return response.json()


def choose(action: str, item_id: str | None, user_id: str = "decor-user") -> dict:
    response = client.post(f"{BASE}/{user_id}/{action}", json={"item_id": item_id})
    assert response.status_code == 200, response.text
    return response.json()


def seed_earned_rewards(user_id: str, count: int = 3) -> None:
    # Test-only ledger fixture: production rewards still require their own
    # existing evidence flows. The integration scenario below uses real HTTP.
    state_repository._users[user_id] = UserProgressRecord(
        user_id=user_id, referral_rewards=count,
    )


def unlocked_ids(snapshot: dict) -> list[str]:
    return [item["item_id"] for item in snapshot["items"] if item["unlocked"]]


def test_snapshot_has_exact_contract_and_complete_demo_catalog() -> None:
    snapshot = get_decoration()
    assert set(snapshot) == {
        "user_id", "avatar_xp", "avatar_level", "goal_item_id", "applied_item_id", "items",
    }
    assert snapshot["user_id"] == "decor-user"
    assert snapshot["avatar_xp"] == 0
    assert snapshot["avatar_level"] == 1
    assert snapshot["goal_item_id"] is None
    assert snapshot["applied_item_id"] == DEFAULT
    assert [item["item_id"] for item in snapshot["items"]] == CATALOG
    assert [item["unlock_level"] for item in snapshot["items"]] == [1, 2, 2, 2, 3, 4]
    assert [item["required_xp"] for item in snapshot["items"]] == [0, 50, 50, 50, 100, 150]
    assert [item["title"] for item in snapshot["items"]] == [
        "Тёплый дом", "Мятное утро", "Персиковый закат", "Небесная кухня",
        "Звёздный вечер", "Ягодный уют",
    ]
    assert all(set(item) == {
        "item_id", "title", "description", "unlock_level", "required_xp", "unlocked",
    } for item in snapshot["items"])
    assert unlocked_ids(snapshot) == [DEFAULT]
    assert get_decoration() == snapshot
    assert client.get("/health").json()["contract_version"] == "1.3"


@pytest.mark.parametrize("xp,level,available", [
    (49, 1, [DEFAULT]),
    (50, 2, [DEFAULT, MINT, SUNSET, SKY]),
    (99, 2, [DEFAULT, MINT, SUNSET, SKY]),
    (100, 3, [DEFAULT, MINT, SUNSET, SKY, NIGHT]),
    (149, 3, [DEFAULT, MINT, SUNSET, SKY, NIGHT]),
    (150, 4, CATALOG),
])
def test_exact_server_xp_boundaries(monkeypatch, xp, level, available) -> None:
    # Actual rewards come in 20-XP increments; patch only the ledger projection
    # in this isolated repository to exercise otherwise unreachable boundaries.
    repository = InMemoryStateRepository()
    repository._users["boundary"] = UserProgressRecord(user_id="boundary")
    monkeypatch.setattr(UserProgressRecord, "avatar_xp", property(lambda self: xp))
    snapshot = repository.home_decoration("boundary")
    assert snapshot.avatar_xp == xp
    assert snapshot.avatar_level == level == repository.snapshot("boundary").avatar_level
    assert unlocked_ids(snapshot.model_dump()) == available
    for item_id in CATALOG:
        goal = repository.set_home_decoration_goal(user_id="boundary", item_id=item_id)
        if item_id in available:
            applied = repository.apply_home_decoration(user_id="boundary", item_id=item_id)
            assert applied.applied_item_id == applied.goal_item_id == item_id
            assert applied.avatar_xp == xp
        else:
            with pytest.raises(HomeDecorationItemLocked):
                repository.apply_home_decoration(user_id="boundary", item_id=item_id)
            assert repository.home_decoration("boundary") == goal


def test_goal_apply_retry_and_reload_preserve_progress_and_rank() -> None:
    seed_earned_rewards("decor-user")
    seed_earned_rewards("other", count=1)
    before = {user: state_repository.snapshot(user) for user in ("decor-user", "other")}
    goal = choose("goal", MINT)
    assert choose("goal", MINT) == goal
    for item_id in [MINT, SUNSET, SKY, DEFAULT, MINT]:
        applied = choose("apply", item_id)
        assert applied["applied_item_id"] == item_id
        assert applied["goal_item_id"] == MINT
        assert choose("apply", item_id) == applied
        assert get_decoration() == applied
    cleared = choose("goal", None)
    assert cleared["goal_item_id"] is None
    assert cleared["applied_item_id"] == MINT
    assert choose("goal", None) == cleared
    assert {user: state_repository.snapshot(user) for user in before} == before


def test_decor_only_visitors_do_not_join_rank_or_earn_rewards() -> None:
    seed_earned_rewards("ranked-user")
    before = state_repository.snapshot("ranked-user")
    for user_id in ("visitor-a", "visitor-b"):
        get_decoration(user_id)
        choose("goal", BERRY, user_id)
        choose("apply", DEFAULT, user_id)
        choose("goal", None, user_id)
        assert state_repository.snapshot(user_id).avatar_xp == 0
        assert user_id not in state_repository._users
    assert state_repository.snapshot("ranked-user") == before


def test_profiles_are_isolated_and_reset_restores_defaults() -> None:
    seed_earned_rewards("owner")
    owner = choose("goal", NIGHT, "owner")
    owner = choose("apply", MINT, "owner")
    other = choose("goal", BERRY, "other")
    denied = client.post(f"{BASE}/other/apply", json={"item_id": MINT})
    assert denied.status_code == 409
    assert get_decoration("other") == other
    assert get_decoration("owner") == owner
    assert get_decoration("new-user")["goal_item_id"] is None
    state_repository.reset()
    for user_id in ("owner", "other"):
        reset = get_decoration(user_id)
        assert reset["avatar_xp"] == 0
        assert reset["goal_item_id"] is None
        assert reset["applied_item_id"] == DEFAULT
        assert unlocked_ids(reset) == [DEFAULT]
    assert InMemoryStateRepository().home_decoration("owner").model_dump() == get_decoration("owner")


@pytest.mark.parametrize("action,item_id,status", [
    ("goal", "unknown", 404),
    ("apply", "unknown", 404),
    ("goal", "other-user/wallpaper_mint", 404),
    ("apply", "other-user/wallpaper_mint", 404),
    ("apply", NIGHT, 409),
    ("apply", BERRY, 409),
])
def test_invalid_or_locked_items_leave_saved_state_and_rewards_unchanged(action, item_id, status) -> None:
    seed_earned_rewards("decor-user")
    choose("goal", MINT)
    before = choose("apply", SKY)
    progress = state_repository.snapshot("decor-user")
    for _ in range(2):
        response = client.post(f"{BASE}/decor-user/{action}", json={"item_id": item_id})
        assert response.status_code == status, response.text
        assert get_decoration() == before
        assert state_repository.snapshot("decor-user") == progress


@pytest.mark.parametrize("action", ["goal", "apply"])
@pytest.mark.parametrize("body", [
    {}, [], {"item_id": ""}, {"item_id": 42}, {"item_id": {"value": MINT}},
    {"item_id": MINT, "avatar_xp": 10000},
    {"item_id": MINT, "avatar_level": 999},
    {"item_id": MINT, "xp": 10000},
    {"item_id": MINT, "unlocked": True},
    {"item_id": MINT, "user_id": "owner"},
])
def test_bad_bodies_and_forged_client_authority_are_rejected(action, body) -> None:
    before = choose("goal", NIGHT)
    progress = state_repository.snapshot("decor-user")
    response = client.post(f"{BASE}/decor-user/{action}", json=body)
    assert response.status_code == 422, response.text
    assert get_decoration() == before
    assert state_repository.snapshot("decor-user") == progress
    assert "decor-user" not in state_repository._users


def test_null_cannot_be_applied_and_failed_new_user_requests_create_no_state() -> None:
    assert client.post(f"{BASE}/new/apply", json={"item_id": None}).status_code == 422
    assert client.post(f"{BASE}/new/apply", json={"item_id": MINT}).status_code == 409
    assert client.post(f"{BASE}/new/goal", json={"item_id": "invented"}).status_code == 404
    assert "new" not in state_repository._users
    assert "new" not in state_repository._home_decoration_by_user


@pytest.mark.parametrize("route", ["cook", "ready"])
def test_purchase_backed_tasks_unlock_three_options_without_spending_xp(route) -> None:
    user_id = rewards.USER
    choose("goal", MINT, user_id)
    meal = rewards.issue(rewards.payload(topup=True))
    for index, day, expected_xp in [(1, "04", 20), (2, "04", 20), (3, "04", 20),
                                   (4, "05", 40), (5, "06", 60)]:
        plan_id = f"decor-{route}-{index}"
        rewards.save(meal, plan_id, route=route)
        before_xp = get_decoration(user_id)["avatar_xp"]
        receipt = rewards.purchase(
            sku="ready" if route == "ready" else "oats", receipt_id=plan_id,
            day=day, ready=route == "ready",
        )
        bought = rewards.emit(receipt, plan_id, now="2026-09-06T13:05:00+03:00")
        if route == "cook":
            assert bought["progress"]["avatar_xp"] == before_xp
            finished = rewards.complete(plan_id, now="2026-09-06T14:00:00+03:00")
        else:
            finished = bought
        assert finished["progress"]["avatar_xp"] == expected_xp
        snapshot = get_decoration(user_id)
        assert snapshot["avatar_xp"] == expected_xp
        assert snapshot["goal_item_id"] == MINT
        assert snapshot["applied_item_id"] == DEFAULT
        if expected_xp < 50:
            assert unlocked_ids(snapshot) == [DEFAULT]
            assert client.post(f"{BASE}/{user_id}/apply", json={"item_id": MINT}).status_code == 409
        else:
            assert unlocked_ids(snapshot) == [DEFAULT, MINT, SUNSET, SKY]

    progress = client.get(f"/api/v1/progress/{user_id}").json()
    assert progress["rewarded_meals"] == progress["purchase_days"] == 3
    for item_id in [MINT, SKY, SUNSET, DEFAULT, MINT]:
        assert choose("apply", item_id, user_id)["applied_item_id"] == item_id
        assert client.get(f"/api/v1/progress/{user_id}").json() == progress
    assert get_decoration(user_id)["goal_item_id"] == MINT
    assert rewards.emit(receipt, plan_id, now="2026-09-06T13:05:00+03:00")["progress"] == progress
    if route == "cook":
        assert rewards.complete(plan_id, now="2026-09-06T14:00:00+03:00")["progress"] == progress


def test_concurrent_apply_retries_are_idempotent_and_preserve_reward_ledger() -> None:
    seed_earned_rewards("decor-user")
    choose("goal", MINT)
    progress = state_repository.snapshot("decor-user")
    with ThreadPoolExecutor(max_workers=8) as pool:
        snapshots = list(pool.map(lambda _: choose("apply", MINT), range(16)))
    assert all(snapshot == snapshots[0] for snapshot in snapshots)
    assert get_decoration() == snapshots[0]
    assert state_repository.snapshot("decor-user") == progress
