import random

from app.contracts import InventoryProduct, RecipeIngredient, UserProfile
from app.safety import SafetyPolicy
from recsys.inventory import generate_inventory
from recsys.profiles import DEFAULT_NOW


def test_generated_products_validate_against_the_real_contract_schema() -> None:
    inventory = generate_inventory(
        random.Random(1), now=DEFAULT_NOW, home_store_id="store_1", user_radius_km=3.0
    )
    assert inventory
    for product in inventory:
        assert isinstance(product, InventoryProduct)
        if product.is_markdown:
            assert product.original_price is not None
            assert product.price <= product.original_price


def test_inventory_exercises_multiple_safety_policy_branches() -> None:
    # Pool many draws so low-probability branches (expired, ineligible) show
    # up at least once, then assert the safety policy genuinely rejects some
    # and approves others — i.e. this isn't a trivially-all-pass fixture.
    policy = SafetyPolicy()
    user = UserProfile(user_id="u1", radius_km=3.0)
    reasons: set[str] = set()
    approved = 0
    total = 0
    for seed in range(30):
        inventory = generate_inventory(
            random.Random(seed), now=DEFAULT_NOW, home_store_id="store_1", user_radius_km=3.0
        )
        for product in inventory:
            ingredient = RecipeIngredient(
                ingredient_id=next(iter(product.ingredient_ids)),
                name=product.name,
                category=product.category,
            )
            decision = policy.evaluate_product(
                product=product, ingredient=ingredient, user=user, now=DEFAULT_NOW
            )
            total += 1
            if decision.approved:
                approved += 1
            else:
                assert decision.reason is not None
                reasons.add(decision.reason)

    assert 0 < approved < total, "expected a genuine mix of approved/rejected products"
    assert "outside_user_radius" in reasons
    assert reasons & {"expired", "not_safety_eligible", "out_of_stock"}


def test_markdown_only_offered_for_rescue_categories() -> None:
    inventory = generate_inventory(
        random.Random(5), now=DEFAULT_NOW, home_store_id="store_1", user_radius_km=5.0
    )
    from app.safety import RESCUE_CATEGORIES

    for product in inventory:
        if product.is_markdown:
            assert product.category in RESCUE_CATEGORIES


def test_generation_is_deterministic_given_a_seed() -> None:
    a = generate_inventory(random.Random(42), now=DEFAULT_NOW, home_store_id="s", user_radius_km=3.0)
    b = generate_inventory(random.Random(42), now=DEFAULT_NOW, home_store_id="s", user_radius_km=3.0)
    assert [p.sku_id for p in a] == [p.sku_id for p in b]
    assert [p.price for p in a] == [p.price for p in b]


def test_generation_normalizes_caller_ingredient_order() -> None:
    ids = ["milk", "egg", "tomato"]
    a = generate_inventory(
        random.Random(42),
        now=DEFAULT_NOW,
        home_store_id="s",
        user_radius_km=3.0,
        ingredient_ids=ids,
    )
    b = generate_inventory(
        random.Random(42),
        now=DEFAULT_NOW,
        home_store_id="s",
        user_radius_km=3.0,
        ingredient_ids=reversed(ids),
    )

    assert a == b
