"""Network-free regressions for source parsing and risky meal-name matches."""

import json
import gzip
import hashlib
import io
from pathlib import Path
from types import SimpleNamespace

import pytest

from recsys.offline.foodru import Fetcher, build
from recsys.offline.foodru_composition import proxy_ingredients, split_composition
from recsys.offline.foodru_evaluate import evaluate, metrics
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
    ("Чебуреки со свининой и говядиной", "Чебуреки с фаршем из свинины и говядины", ["Свино-говяжий фарш", "Мука"]),
    ("Блины пшеничные", "Блины из пшеничной муки", ["Пшеничная мука", "Молоко"]),
    ("Курица терияки на рисе", "Нежная курочка терияки с рисом", ["Курица", "Рис", "Соус терияки"]),
    ("Винегрет овощной с маслом", "Винегрет с овощами на оливковом масле", ["Картошка", "Свекла", "Оливковое масло"]),
    ("Лапша с курицей терияки Asiatique, 280г", "Курица терияки с лапшой", ["Куриное филе", "Лапша", "Терияки"]),
    ("Хашбраун картофельный", "Хашбраун (картофельные оладьи)", ["Картошка", "Мука"]),
])
def test_reported_false_rejections_are_fixed(meal, title, ingredients):
    assert match_product(product(meal), NameIndex([recipe(title, ingredients)]))["status"] == "matched"


def test_ingredient_roles_keep_filling_dough_and_sauce_but_separate_serving():
    source = recipe("Круассан с ветчиной и сыром", [])
    source["ingredients"] = [
        {"name": "Мука", "group": "Для теста"},
        {"name": "Ветчина", "group": "Для начинки"},
        {"name": "Сыр", "group": "Для соуса"},
        {"name": "Кофе", "group": "Для подачи"},
    ]
    composition = split_composition(source)
    assert [x["name"] for x in proxy_ingredients(source, composition)] == ["Мука", "Ветчина", "Сыр"]
    assert composition["excluded_serving_indices"] == [3]


def test_mixed_serving_and_sauce_group_is_not_silently_dropped_or_copied():
    source = recipe("Спаржа по-корейски", ["Спаржа"])
    source["ingredients"] += [{"name": "Соевый соус", "group": "Для заправки и подачи"},
                              {"name": "Рис", "group": "Для заправки и подачи"}]
    match = match_product(product("Спаржа по-корейски"), NameIndex([source]))
    assert match["status"] == "review"
    assert "mixed_ingredient_group" in match["candidates"][0]["review_reasons"]


def test_title_cannot_confirm_an_ingredient_absent_from_recipe():
    source = recipe("Макароны с сыром и зеленью", ["Макароны", "Сыр"])
    match = match_product(product("Макароны с сыром и зеленью"), NameIndex([source]))
    assert match["status"] == "review"
    assert match["candidates"][0]["missing_recipe_ingredients"] == ["herbs"]


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
    ("Бульмени с мясом", "Фарш для пельменей", ["Говядина", "Свинина"]),
    ("Икра Санта Бремор классическая", "Икра из овощей", ["Кабачок", "Морковь"]),
    ("Шримп-ролл", "Роллы с креветками", ["Креветки", "Рис", "Нори"]),
    ("Биточек куриный со спагетти в томатном соусе", "Котлеты куриные в томатном соусе", ["Куриный фарш", "Томатная паста"]),
    ("Курица терияки с рисом и овощами", "Курица терияки с рисом", ["Курица", "Рис", "Терияки", "Черный перец молотый"]),
    ("Мини багет", "Чиабатта", ["Пшеничная мука", "Вода"]),
])
def test_false_friends_never_copy_ingredients(meal, title, ingredients):
    match = match_product(product(meal), NameIndex([recipe(title, ingredients)]))
    assert match["status"] != "matched"
    assert match["recipe_id"] is None


def test_tomatoes_served_alongside_cannot_confirm_tomato_filling():
    source = recipe("Кутабы с сыром", ["Мука", "Сыр"])
    source["ingredients"].append({"name": "Помидор", "group": "Для подачи"})
    match = match_product(product("Кутабы с сыром и помидорами"), NameIndex([source]))
    assert match["status"] == "review"
    assert "tomato" in match["candidates"][0]["missing_recipe_ingredients"]


def test_explicit_herb_garnish_is_kept_in_proxy():
    source = recipe("Макароны с сыром и зеленью", ["Макароны", "Сыр"])
    source["ingredients"].append({"name": "Зелень", "group": "Для подачи"})
    match = match_product(product("Макароны с сыром и зеленью"), NameIndex([source]))
    assert match["status"] == "matched"
    assert match["candidates"][0]["composition"]["included_named_serving_indices"] == [2]


def test_tomatoes_elsewhere_do_not_confirm_a_tomato_sauce():
    source = recipe("Голубцы в сметанном соусе", [])
    source["ingredients"] = [{"name": "Мясной фарш", "group": "Для блюда"},
                             {"name": "Помидор", "group": "Для блюда"},
                             {"name": "Сметана", "group": "Для соуса"}]
    match = match_product(product("Голубцы в томатно-сметанном соусе"), NameIndex([source]))
    assert match["status"] == "review"
    assert "named_sauce_component_unconfirmed" in match["candidates"][0]["review_reasons"]


@pytest.mark.parametrize("title", ["Голубцы в томатном соусе", "Голубцы в томатно-сметанном соусе"])
def test_served_sourcream_cannot_confirm_a_sourcream_sauce(title):
    source = recipe(title, ["Мясной фарш", "Капуста", "Помидоры"])
    source["ingredients"].append({"name": "Сметана", "group": "Для подачи"})
    match = match_product(product("Голубцы в томатно-сметанном соусе"), NameIndex([source]))
    assert match["status"] == "review"
    assert "named_sauce_component_unconfirmed" in match["candidates"][0]["review_reasons"]


def test_quality_metrics_count_errors_and_exclude_uncertain_labels():
    rows = [{"label": label, "prediction": prediction} for label, prediction in
            [(True, True), (True, False), (False, True), (False, False), (None, True)]]
    assert metrics(rows, "prediction") == {"tp": 1, "fp": 1, "tn": 1, "fn": 1,
        "labelled_pairs": 4, "sample_precision": .5, "sample_recall": .5}
    assert metrics([], "prediction")["sample_precision"] is None


def test_snapshot_separates_serving_without_erasing_cooking_ingredients():
    snapshot = Path(__file__).resolve().parents[1] / "recsys/data/foodru"
    recipes = {r["recipe_id"]: r for r in json.loads((snapshot / "recipes.json").read_text(encoding="utf-8"))["recipes"]}
    products = {f"{p['chain']}:{p['plu']}": p for p in
                json.loads((snapshot / "enriched_catalog.json").read_text(encoding="utf-8"))["products"]}
    for key, serving in [("perekrestok:4310836", "Кофе"), ("perekrestok:4372008", "Мороженое")]:
        enriched = products[key]
        assert serving not in {i["name"] for i in enriched["assumed_ingredients"]}
        assert serving in {i["name"] for i in enriched["excluded_serving_ingredients"]}
        source = recipes[enriched["foodru_match"]["recipe_id"]]
        assert serving in {i["name"] for i in source["ingredients"]}
    # Tea is used to cook the sprats: role, not a drink-name blacklist, matters.
    assert any("чай" in i["name"].lower()
               for i in products["perekrestok:4261613"]["assumed_ingredients"])


def test_curated_snapshot_keeps_pizza_base_and_soup_noodles_and_rejects_ambiguous_sides():
    snapshot = Path(__file__).resolve().parents[1] / "recsys/data/foodru"
    products = {f"{p['chain']}:{p['plu']}": p for p in
                json.loads((snapshot / "enriched_catalog.json").read_text(encoding="utf-8"))["products"]}
    pizza = products["pyaterochka:4391323"]["assumed_ingredients"]
    assert any("тесто" in i["name"].lower() or "мука" in i["name"].lower() for i in pizza)
    soup = products["perekrestok:4442431"]["assumed_ingredients"]
    assert any("лапш" in i["name"].lower() for i in soup)
    assert products["perekrestok:4364439"]["assumed_ingredients"] is None


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


def test_evaluation_binds_results_to_current_files_and_rejects_stale_inputs(tmp_path):
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps({"products": [product("Сырники")]}))
    (tmp_path / "recipes.json").write_text(json.dumps({"recipes": [recipe("Сырники", ["Творог"])]}))
    build(SimpleNamespace(catalog=catalog_path, output=tmp_path, overrides=None))
    baseline = json.loads((tmp_path / "matches.json").read_text())
    summary = json.loads((tmp_path / "summary.json").read_text())
    cases = {"label_origin": "test", "sampling": "test", "pairs": [
        {"product_key": "perekrestok:42", "recipe_id": "foodru_1", "label": True}]}
    report = evaluate(tmp_path, catalog_path, baseline, summary, cases)
    assert report["matches_sha256"] == hashlib.sha256((tmp_path / "matches.json").read_bytes()).hexdigest()
    assert report["current_pair_metrics"]["tp"] == 1
    catalog_path.write_text(catalog_path.read_text() + "\n")
    with pytest.raises(ValueError, match="Input changed since build"):
        evaluate(tmp_path, catalog_path, baseline, summary, cases)


def test_expansion_evaluation_preserves_sources_and_replays_fixed_pairs(tmp_path):
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps({"products": [product("Сырники")]}))
    original = [recipe("Сырники", ["Творог"]), recipe("Классические сырники", ["Творог"], "foodru_2")]
    snapshot = tmp_path / "recipes.json"
    snapshot.write_text(json.dumps({"recipes": original}))
    args = SimpleNamespace(catalog=catalog_path, output=tmp_path, overrides=None)
    build(args)
    baseline = json.loads((tmp_path / "matches.json").read_text())
    summary = json.loads((tmp_path / "summary.json").read_text())
    # This fixed candidate is valid even though the baseline selected recipe 1.
    cases = {"label_origin": "test", "sampling": "test", "pairs": [
        {"product_key": "perekrestok:42", "recipe_id": "foodru_2", "label": True}]}
    snapshot.write_text(json.dumps({"recipes": original + [recipe("Омлет", ["Яйцо"], "foodru_3")]}))
    build(args)
    with pytest.raises(ValueError, match="explicitly allow an expansion"):
        evaluate(tmp_path, catalog_path, baseline, summary, cases)
    report = evaluate(tmp_path, catalog_path, baseline, summary, cases,
                      baseline_recipes=original, allow_expanded_snapshot=True)
    assert report["added_recipe_ids"] == ["foodru_3"]
    assert report["baseline_pair_metrics"]["tp"] == report["current_pair_metrics"]["tp"] == 1
    assert report["baseline_pair_method"] == "replayed_same_rules_on_baseline_corpus"
    changed = json.loads(snapshot.read_text())
    changed["recipes"][0]["ingredients"].append({"name": "Изюм"})
    snapshot.write_text(json.dumps(changed))
    build(args)
    with pytest.raises(ValueError, match="preserve every original recipe unchanged"):
        evaluate(tmp_path, catalog_path, baseline, summary, cases,
                 baseline_recipes=original, allow_expanded_snapshot=True)


def test_unknown_override_does_not_silently_match_to_missing_recipe(tmp_path):
    (tmp_path / "catalog.json").write_text(json.dumps({"products": [product("Сырники")]}))
    (tmp_path / "recipes.json").write_text(json.dumps({"recipes": [recipe("Сырники", ["Творог"])]}))
    (tmp_path / "overrides.json").write_text(json.dumps({"perekrestok:42": {"recipe_id": "foodru_999", "reason": "review"}}))
    with pytest.raises(ValueError, match="Unknown override"):
        build(SimpleNamespace(catalog=tmp_path / "catalog.json", output=tmp_path, overrides=tmp_path / "overrides.json"))


def test_reviewed_overrides_are_reused_and_can_keep_a_rejected_product_in_review(tmp_path):
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps({"products": [product("Cуп из тыквы"),
        {**product("Сырники"), "plu": "43"}]}))
    (tmp_path / "recipes.json").write_text(json.dumps({"recipes": [
        recipe("Суп из тыквы", ["Тыква"]), recipe("Сырники", ["Творог"], "foodru_2")]}))
    overrides_path = tmp_path / "reviewed_overrides.json"
    overrides_path.write_text(json.dumps({"perekrestok:42": {"recipe_id": "foodru_1", "reason": "Latin C in source title"},
        "perekrestok:43": {"recipe_id": None, "status": "review", "reason": "Requires composition review"}}))
    build(SimpleNamespace(catalog=catalog_path, output=tmp_path, overrides=None))
    matches = json.loads((tmp_path / "matches.json").read_text())["matches"]
    assert matches[0]["status"] == "matched" and matches[0]["recipe_id"] == "foodru_1"
    assert matches[1]["status"] == "review" and matches[1]["recipe_id"] is None
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert summary["overrides_sha256"] == hashlib.sha256(overrides_path.read_bytes()).hexdigest()
    assert summary["matched_by_decision"] == {"automatic": 0, "reviewed_override": 1}


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
    catalog = json.loads((root / "ready_food_catalog.json").read_text(encoding="utf-8"))
    snapshot = root / "foodru"
    recipes = json.loads((snapshot / "recipes.json").read_text(encoding="utf-8"))["recipes"]
    matches = json.loads((snapshot / "matches.json").read_text(encoding="utf-8"))["matches"]
    enriched = json.loads((snapshot / "enriched_catalog.json").read_text(encoding="utf-8"))["products"]
    options = [ReadyMealOption.model_validate(x) for x in json.loads((snapshot / "ready_meal_options.json").read_text(encoding="utf-8"))]
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
            source = recipes_by_id[match["recipe_id"]]
            composition = enriched_product["ingredient_provenance"]["composition"]
            assert enriched_product["assumed_ingredients"] == [source["ingredients"][i] for i in composition["included_indices"]]
            assert not composition["unresolved_indices"]
            assert set(composition["included_indices"]).isdisjoint(composition["excluded_serving_indices"])
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
