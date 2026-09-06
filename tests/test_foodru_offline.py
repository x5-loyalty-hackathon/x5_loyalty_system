"""Network-free regressions for source parsing and risky meal-name matches."""

import json
import gzip
import io
from pathlib import Path
from types import SimpleNamespace

import pytest

from recsys.offline.foodru import Fetcher, build
from recsys.offline.foodru_matching import NameIndex, match_product, tokens
from recsys.offline.foodru_parser import RecipeParseError, parse_recipe

URL = "https://food.ru/recipes/123-syrniki"


def page(ld=None, state=None):
    return (
        '<html><script type="application/ld+json">'
        + json.dumps(ld or {"@graph": [{"@type": ["Recipe"], "name": "Сырники",
                                     "recipeIngredient": ["Творог 200 г"]}]})
        + '</script><script id="__NEXT_DATA__" type="application/json">'
        + json.dumps({"props": {"pageProps": {"changed-store-hash": state or {}}}})
        + "</script></html>"
    )


def test_structured_ingredients_rating_and_comments_are_bound_to_recipe():
    html = page(state={
        "detail": {"id": 123, "title": "Сырники", "measure_count": 2,
                   "main_ingredients_block": {"title": "Для блюда", "products": [
                       {"id": 11, "title": "Творог", "custom_measure_count": 200,
                        "custom_measure": "г", "weight": 200},
                       {"id": 12, "title": "Соль", "custom_measure_count": 0,
                        "custom_measure": "по вкусу", "weight": 0},
                   ]}},
        "rating": {"material_id": 123, "material_type": "recipe", "total_rating": "4,7", "rating_count": 8},
        "related_rating": {"material_id": 999, "material_type": "recipe", "total_rating": 5, "rating_count": 900},
        "comments": {"total_count": 12, "comments": [
            {"id": 7, "material_id": 123, "material_type": "recipe", "created_at": "2026-01-01",
             "user": {"x5id": "DO-NOT-COPY", "first_name": "DO-NOT-COPY"},
             "content": {"type": "document", "children": [{"type": "paragraph", "children": [
                 {"type": "text", "content": "Вкусно!"}]}]}},
        ]},
        "other_comments": {"total_count": 1, "comments": [
            {"id": 8, "material_id": 999, "material_type": "recipe", "content": "Unrelated"}]},
    })
    recipe = parse_recipe(html, URL, "2026-09-06")
    assert recipe["ingredients"][0]["weight_g"] == 200
    assert recipe["ingredients"][1]["quantity"] is None
    assert recipe["ingredients"][1]["weight_g"] is None
    assert recipe["rating"] == {"value": 4.7, "count": 8, "best": 5.0}
    assert recipe["reviews_collected"] == 1
    assert recipe["reviews_total"] == 12
    assert recipe["reviews_status"] == "partial"
    assert recipe["reviews"][0]["text"] == "Вкусно!"
    assert "DO-NOT-COPY" not in json.dumps(recipe)


def test_json_ld_fallback_preserves_unknowns_and_original_ingredient_text():
    recipe = parse_recipe(page(), URL, "2026-09-06")
    assert recipe["ingredient_lines"] == ["Творог 200 г"]
    assert recipe["ingredients"][0]["quantity"] is None
    assert recipe["rating"] is None
    assert recipe["reviews_total"] is None
    assert recipe["reviews_status"] == "not_exposed"


def test_zero_votes_are_not_a_zero_star_rating():
    recipe = parse_recipe(page(state={"material_id": 123, "material_type": "recipe",
                                      "total_rating": 0, "rating_count": 0}), URL, "today")
    assert recipe["rating"] is None


def test_blocked_or_malformed_pages_are_not_empty_recipes():
    with pytest.raises(RecipeParseError):
        parse_recipe("<html>Access denied</html>", URL, "today")


def test_canonical_recipe_id_is_used_after_redirect():
    result = parse_recipe(page(ld={"@type": "Recipe", "name": "Сырники",
                                   "url": "https://food.ru/recipes/456-new-slug",
                                   "recipeIngredient": ["Творог"]}), URL, "today")
    assert result["recipe_id"] == "foodru_456"


def test_fetch_cache_is_reused_without_network(tmp_path, monkeypatch):
    body = "<html>Рецепт</html>".encode()
    response = io.BytesIO(gzip.compress(body))
    response.url = URL
    response.headers = {"Content-Encoding": "gzip"}
    monkeypatch.setattr("recsys.offline.foodru.urlopen", lambda *a, **kw: response)
    first = Fetcher(tmp_path, interval=0).get(URL)

    def fail(*args, **kwargs):
        raise AssertionError("Cached retrieval must not use the network")

    monkeypatch.setattr("recsys.offline.foodru.urlopen", fail)
    assert Fetcher(tmp_path, interval=0).get(URL) == first
    assert first[0] == body.decode()


def recipe(title, ingredients, id="foodru_1"):
    return {"recipe_id": id, "source_id": int(id.split("_")[-1]), "title": title,
            "ingredients": [{"name": name} for name in ingredients], "rating": None,
            "source_url": "https://food.ru/recipes/" + id.split("_")[-1] + "-test",
            "reviews": [], "reviews_status": "not_exposed"}


def product(name):
    return {"chain": "perekrestok", "plu": "42", "name": name, "median_price_rub": 200,
            "dish_type": None, "cuisine": None}


def test_packaging_brands_and_inflections_do_not_prevent_good_match():
    source = recipe("Блинчики с курицей и грибами", ["Мука", "Куриное филе", "Шампиньоны"])
    match = match_product(product("Блинчики с курицей и грибами Перекрёсток Select, 160г"), NameIndex([source]))
    assert match["status"] == "matched"
    assert tokens("syrniki-s-iziumom") == tokens("Сырники с изюмом")


@pytest.mark.parametrize("meal,title,ingredients", [
    ("Сэндвич-ролл Цезарь с креветками", "Салат Цезарь с креветками", ["Креветки", "Салат"]),
    ("Плов с говядиной", "Плов с курицей", ["Курица", "Рис"]),
    ("Котлета куриная с картофельным пюре", "Котлета куриная", ["Курица", "Яйцо"]),
    ("Сырники с вишней", "Сырники с изюмом", ["Творог", "Изюм"]),
    ("Оладьи из курицы", "Оладьи из творога", ["Творог", "Мука"]),
    ("Котлеты куриные с картофельным пюре", "Картофельные котлеты из пюре", ["Картошка", "Куриное яйцо", "Сливочное масло"]),
    ("Биточки мясные с картофельным пюре", "Картофельные котлеты из пюре", ["Картошка", "Куриное яйцо", "Сливочное масло"]),
    ("Стрипсы куриные с картофелем", "Картофельно-куриные наггетсы", ["Картошка", "Куриное филе"]),
    ("Блины без начинки", "Блины с мясом", ["Молоко", "Мука", "Фарш"]),
    ("Сырники без сахара", "Сырники", ["Творог", "Сахар"]),
    ("Паста Санта Бремор из морепродуктов", "Паста с морепродуктами", ["Спагетти", "Морепродукты"]),
    ("Салат сырный", "Салат из свеклы с сыром", ["Свекла", "Сыр"]),
    ("Блины с черносливом", "Блины с творогом", ["Мука", "Творог"]),
    ("Паста 4 сыра", "Спагетти с сыром", ["Спагетти", "Сыр"]),
    ("Салат пикантный с сыром", "Салат пикантный с сыром и ананасом", ["Сыр", "Ананас"]),
    ("Блины без начинки", "Блины с начинкой", ["Мука", "Яблоки"]),
    ("Блины домашние", "Блины с начинкой", ["Мука", "Яблоки"]),
    ("Блинчики с маковой начинкой", "Маковые блины", ["Мука", "Мак"]),
    ("Салат Морковь по-корейски", "Салат с корейской морковью", ["Корейская морковь", "Куриная грудка"]),
    ("Салат сырный", "ПП салат с сыром", ["Сыр", "Куриное филе"]),
    ("Вок курица терияки-рис", "Рисовая лапша с курицей и овощами в соусе терияки", ["Рисовая лапша", "Куриное филе", "Соус терияки"]),
])
def test_false_friends_never_copy_ingredients(meal, title, ingredients):
    match = match_product(product(meal), NameIndex([recipe(title, ingredients)]))
    assert match["status"] != "matched"
    assert match["recipe_id"] is None


def test_build_preserves_all_products_and_exports_only_accepted_pairs(tmp_path):
    catalog = {"snapshot_ids": ["snapshot"], "city": "Москва", "products": [
        product("Сырники классические"), {**product("Сырники с вишней"), "plu": "43"}]}
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps(catalog))
    (tmp_path / "recipes.json").write_text(json.dumps({"recipes": [recipe("Сырники", ["Творог"])], "errors": []}))
    args = SimpleNamespace(catalog=catalog_path, output=tmp_path, overrides=None)
    build(args)
    enriched = json.loads((tmp_path / "enriched_catalog.json").read_text())["products"]
    options = json.loads((tmp_path / "ready_meal_options.json").read_text())
    assert len(enriched) == 2
    assert enriched[0]["assumed_ingredients"] == [{"name": "Творог"}]
    assert enriched[1]["assumed_ingredients"] is None
    assert enriched[0]["ingredient_provenance"]["manufacturer_verified"] is False
    assert len(options) == 1 and options[0]["recipe_ids"] == ["foodru_1"]
    before = (tmp_path / "matches.json").read_bytes()
    build(args)
    assert (tmp_path / "matches.json").read_bytes() == before
    assert json.loads(catalog_path.read_text()) == catalog


def test_unknown_override_does_not_silently_match_to_missing_recipe(tmp_path):
    (tmp_path / "catalog.json").write_text(json.dumps({"products": [product("Сырники")]}))
    (tmp_path / "recipes.json").write_text(json.dumps({"recipes": [recipe("Сырники", ["Творог"])]}))
    (tmp_path / "overrides.json").write_text(json.dumps({"perekrestok:42": {"recipe_id": "foodru_999", "reason": "review"}}))
    with pytest.raises(ValueError, match="Unknown override"):
        build(SimpleNamespace(catalog=tmp_path / "catalog.json", output=tmp_path, overrides=tmp_path / "overrides.json"))


def test_matching_exact_dishes_does_not_require_a_predefined_family():
    match = match_product(product("Свекольник на кефире Перекрёсток Select, 250г"),
                          NameIndex([recipe("Свекольник на кефире", ["Свекла", "Кефир"])]))
    assert match["status"] == "matched"


def test_korean_carrot_matches_with_and_without_salad_prefix():
    match = match_product(product("Салат Морковь по-корейски Пятёрочка Кафе 400г"),
                          NameIndex([recipe("Морковь по-корейски", ["Морковь"])]))
    assert match["status"] == "matched"


def test_retailer_card_can_veto_an_exact_name():
    meal = {**product("Салат Цезарь"), "dish_type": "Сэндвич-ролл"}
    match = match_product(meal, NameIndex([recipe("Салат Цезарь", ["Салат"])]))
    assert match["status"] == "review"
    assert "retailer_dish_type_conflict" in match["candidates"][0]["review_reasons"]


def test_explicit_chicken_broth_does_not_require_separate_chicken_meat():
    meal = product("Суп овощной на курином бульоне")
    match = match_product(meal, NameIndex([recipe("Овощной суп на курином бульоне", ["Куриный бульон", "Морковь"])]))
    assert match["status"] == "matched"


def test_committed_snapshot_has_no_dangling_pairs_and_preserves_original_products():
    from recsys.experimental.contracts import ReadyMealOption

    root = Path(__file__).resolve().parents[1] / "recsys/data"
    catalog = json.loads((root / "ready_food_catalog.json").read_text())
    snapshot = root / "foodru"
    recipes = json.loads((snapshot / "recipes.json").read_text())["recipes"]
    matches = json.loads((snapshot / "matches.json").read_text())["matches"]
    enriched = json.loads((snapshot / "enriched_catalog.json").read_text())["products"]
    options = [ReadyMealOption.model_validate(x) for x in json.loads((snapshot / "ready_meal_options.json").read_text())]
    recipes_by_id = {r["recipe_id"]: r for r in recipes}
    assert len(recipes_by_id) == len(recipes)
    assert len(enriched) == len(matches) == len(catalog["products"])
    accepted_keys = set()
    for product, match, enriched_product in zip(catalog["products"], matches, enriched):
        assert all(enriched_product[key] == value for key, value in product.items())
        assert (product["chain"], product["plu"]) == (match["chain"], match["plu"])
        assert all(c["recipe_id"] in recipes_by_id for c in match["candidates"])
        if match["status"] == "matched":
            accepted_keys.add((product["chain"], product["plu"]))
            assert enriched_product["assumed_ingredients"] == recipes_by_id[match["recipe_id"]]["ingredients"]
        else:
            assert match["recipe_id"] is None
            assert enriched_product["assumed_ingredients"] is None
    assert {(o.chain, o.plu) for o in options} == accepted_keys
    assert all(o.recipe_ids <= recipes_by_id.keys() for o in options)
    for recipe_data in recipes:
        assert recipe_data["ingredients"]
        assert recipe_data["reviews_collected"] == len(recipe_data["reviews"])
        assert all(set(comment) <= {"text", "source_comment_id", "published_at"}
                   for comment in recipe_data["reviews"])
