"""Explainable, conservative name matching for the static PoC snapshot.

Scores are heuristics, not probabilities. Recipe ingredients are an assumption
about a similarly named meal, never the manufacturer's ingredient declaration.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from functools import lru_cache

from recsys.offline.foodru_composition import proxy_ingredients, split_composition

VERSION = "foodru-name-v2"

_CYR = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
                ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "i", "k", "l",
                 "m", "n", "o", "p", "r", "s", "t", "u", "f", "h", "c", "ch", "sh",
                 "shch", "", "y", "", "e", "ju", "ja"]))


def latin(text: str) -> str:
    text = "".join(_CYR.get(c, c) for c in text.lower())
    # Food.ru slugs use both historical -ia/-ya and current -ja spellings.
    return (text.replace("shh", "shch").replace("kh", "h")
            .replace("ya", "a").replace("ja", "a").replace("ia", "a")
            .replace("yu", "u").replace("ju", "u").replace("iu", "u"))


_BRANDS = re.compile(
    r"перекр[её]сток\s*(?:select)?|пят[её]рочка\s*кафе|вкус\s*&?\s*польза|"
    r"золотой петушок|горячая штучка|сибирская коллекция|санта бремор|люди любят|"
    r"global village|graf ewgraf|cook chart|mr\.?\s*food|fitdelice|cheeseberry|"
    r"rostic'?s|papa boba|трайфл[ -]суши|класс\s*продукт|зимняя радуга|"
    r"останкино|мираторг|фросток|моремания|стародворье|альтерно|маркет|пр!ст|"
    r"alvalle|йуми|фэг|фег|шеф\b|с пылу с жару|красная цена|сытный край|"
    r"handmade|балтийский берег|creme le mare|формула госта|dostaевский|"
    r"asiatique|delis frost|hanok|махеевъ|слимкафе|звездное соло|топ\s+шеф", re.I,
)


def clean_product_name(text: str) -> str:
    # Long brand names must be removed before their short constituent "шеф".
    text = re.sub(r"топ\s+шеф", " ", text.lower().replace("ё", "е"))
    text = _BRANDS.sub(" ", text)
    text = re.sub(r"\b\d+(?:[.,]\d+)?\s*(?:кг|гр|г|мл|л|шт)\b", " ", text)
    text = re.sub(r"замороженн\w*|охлажденн\w*|готовые|готовый|п/ф", " ", text)
    return " ".join(re.findall(r"[а-яa-z0-9]+", text))


# Prefixes encode Russian inflections and a few real dish synonyms. The same
# normalization is used for Cyrillic titles and transliterated sitemap slugs.
_GROUPS = {
    "chicken": "куриц курин цыпл курочк", "beef": "говяд говяж телят теляч",
    "pork": "свин", "turkey": "индей индюш", "lamb": "баран ягнят",
    "shrimp": "кревет шримп", "salmon": "лосос семг", "pink_salmon": "горбуш",
    "tuna": "тунц тунец", "squid": "кальмар", "crab": "краб",
    "herring": "сельд селед", "pollock": "минтай минта", "cod": "треск",
    "ham": "ветчин", "bacon": "бекон", "sausage": "колбас сосиск", "buzhenina": "буженин",
    "meat": "мясн мясо фарш", "mushroom": "гриб шампинь", "potato": "картоф картош",
    "rice": "рисов рис", "buckwheat": "греч", "carrot": "морков",
    "cabbage": "капуст", "beet": "свек", "cucumber": "огур",
    "tomato": "томат помид", "pepper": "перец перц", "onion": "лук",
    "cheese": "сыр моцарел брынз буррат сулугун пармезан гауда", "cottage_cheese": "творо",
    "cream": "сливоч сливки", "sourcream": "сметан", "milk": "молок молоч",
    "apple": "яблок яблоч", "cherry": "вишн", "raisin": "изюм", "prune": "чернослив",
    "apricot": "кураг абрикос", "pear": "груш", "peach": "персик",
    "currant": "смород", "strawberry": "клубнич клубник",
    "raspberry": "малин", "banana": "банан", "coconut": "кокос",
    "pumpkin": "тыкв", "spinach": "шпинат", "asparagus": "спарж",
    "vegetable": "овощ", "oat": "овсян овес", "millet": "пшен",
    "wheat": "пшенич", "garlic": "чесно", "poppy": "маков мак",
    "chocolate": "шоколад", "sugar": "сахар", "sorrel": "щавел",
    "cinnamon": "кориц", "herbs": "зелен укроп петруш",
    "pineapple": "ананас", "cocoa": "какао", "nuts": "орех",
    "flour": "мук", "oil": "масл", "olive_oil": "оливков",
    "beans": "фасол", "breast": "грудк", "thigh": "бедр",
    "pea": "горох", "lentil": "чечевиц", "bulgur": "булгур",
    "pancake": "блин налистник", "syrniki": "сырник сырнич",
    "fritter": "олад хашбраун", "cutlet": "котлет биточ", "meatball": "тефтел фрикадел",
    "schnitzel": "шницел", "nugget": "наггетс круггетс стрипс",
    "salad": "салат", "soup": "суп", "borsch": "борщ борш",
    "solyanka": "солян", "kharcho": "харчо", "gazpacho": "гаспач",
    "sandwich": "сэндвич сендвич сандвич бутерброд тост панини",
    "roll": "ролл", "shawarma": "шаурм шаверм", "onigiri": "онигири",
    "pasta": "паста макарон спагет фузилл фарфал фетуч", "noodles": "лапш удон", "wok": "вок",
    "lasagna": "лазань лазан", "pilaf": "плов", "porridge": "каша каши",
    "omelette": "омлет скрэмбл", "bake": "запекан", "pizza": "пицц",
    "hummus": "хумус", "vinegret": "винегрет", "olivier": "оливье столичн",
    "caesar": "цезар", "carbonara": "карбонар", "bolognese": "болоньез болоньез",
    "teriyaki": "терияк", "korean": "корейск", "pesto": "песто",
    "mash": "пюре", "sauce": "соус", "khachapuri": "хачапур",
    "pie": "пирог пирож", "puff": "слойк", "croissant": "круассан",
    "samsa": "самса самсы", "burek": "бурек", "cheburek": "чебурек",
    "dumpling": "пельмен бульмен чебупел", "vareniki": "вареник",
    "manti": "манты мантов", "kebab": "кебаб шашлык",
    "beefstroganoff": "бефстроган", "azu": "азу", "patty": "паштет",
    "bread": "хлеб багет чиабат", "bun": "булоч булк", "donut": "пончик донат",
    "cheesecake": "чизкейк", "soup_tomyam": "томям", "poke": "поке боул",
    "pepperoni": "пепперони пеперони", "california": "калифорн", "philadelphia": "филадельф",
}
_PREFIXES = sorted([(latin(p), key) for key, values in _GROUPS.items()
                    for p in values.split()], key=lambda x: -len(x[0]))
_STOP = {latin(x) for x in (
    "с со и из в на по под для без от к за а или г кг мл л шт п ф "
    "классический классические домашний домашние вкусный вкусные простой простые "
    "нежный нежные сочный сочные жареный жареные запеченный запеченные "
    "натуральный натуральные рецепт рецепту филе кусочки "
    "начинка начинкой начинки белоногими балтийской рубленый имитированным двойной двойные мини клаб"
).split()}
_ENDINGS = ("ennymi", "ennye", "ennyi", "annyi", "icheskie", "icheskij", "ovymi",
            "ovoi", "ovyi", "ovym", "nymi", "nogo", "kami", "ami", "ogo", "omu",
            "ovoe", "ovye", "ovki", "naya", "naja", "nym", "noi", "nyi", "nue",
            "oe", "ye", "oi", "yi", "ym", "om", "ah", "ov", "ami", "ei", "a", "y", "i", "u", "e")
_DECORATIVE_PREFIXES = tuple(latin(x) for x in (
    "нежн", "сочн", "вкусн", "домашн", "классическ", "аппетитн", "сытн", "быстр", "хрустящ",
))


@lru_cache(maxsize=250_000)
def tokens(text: str) -> frozenset[str]:
    # With an explicit ingredient clause the generic "деревенский" label is
    # decorative. Preserve it in a bare named dish such as "Салат Деревенский".
    if re.search(r"\b(?:с|со|из)\s+", text, re.I):
        text = re.sub(r"\bдеревенск\w*\b", "", text, flags=re.I)
    text = latin(text)
    text = re.sub(r"tom[- ]+(?:am|yam|jam)", "tomam", text)
    text = re.sub(r"fo[- ]+bo\b", "phobo", text)
    text = re.sub(r"(?:4|chetyre|chetyreh)[- ]+syr[a-z]*", "fourcheese", text)
    found = set()
    for word in re.findall(r"[a-z]+", text):
        if word in _STOP or len(word) < 3 or word.startswith(_DECORATIVE_PREFIXES):
            continue
        if word == "tomam":
            found.add("soup_tomyam")
            continue
        group = next((key for prefix, key in _PREFIXES if word.startswith(prefix)), None)
        if group:
            found.add(group)
            continue
        for ending in _ENDINGS:
            if word.endswith(ending) and len(word) - len(ending) >= 4:
                word = word[:-len(ending)]
                break
        found.add(word)
    return frozenset(found)


_FAMILY_ORDER = [
    ("sandwich", {"sandwich", "shawarma"}), ("onigiri", {"onigiri"}),
    ("roll", {"roll"}), ("pizza", {"pizza"}), ("salad", {"salad", "vinegret", "olivier", "caesar"}),
    ("pancake", {"pancake"}), ("syrniki", {"syrniki"}), ("fritter", {"fritter"}),
    ("soup", {"soup", "borsch", "solyanka", "kharcho", "gazpacho", "soup_tomyam"}),
    ("lasagna", {"lasagna"}), ("pilaf", {"pilaf"}), ("porridge", {"porridge"}),
    ("omelette", {"omelette"}), ("bake", {"bake"}), ("cutlet", {"cutlet"}),
    ("meatball", {"meatball"}), ("schnitzel", {"schnitzel"}), ("nugget", {"nugget"}),
    ("beefstroganoff", {"beefstroganoff"}), ("azu", {"azu"}), ("kebab", {"kebab"}),
    ("pasta", {"pasta", "carbonara", "bolognese"}),
    ("noodles", {"noodles"}),
] + [(x, {x}) for x in ["hummus", "khachapuri", "pie", "puff", "croissant", "samsa", "burek",
                       "cheburek", "dumpling", "vareniki", "manti", "patty", "bread", "bun",
                       "donut", "cheesecake", "poke", "wok", "sauce"]]
PROTEINS = frozenset("chicken beef pork turkey lamb shrimp salmon pink_salmon tuna squid crab herring pollock cod ham bacon sausage buzhenina".split())
IDENTITY = frozenset(_GROUPS) - {"cream", "sourcream", "milk", "sauce", "onion", "pepper", "vegetable", "herbs", "garlic", "wheat", "sugar"}
_GENERIC_DISH_MARKERS = frozenset({"salad", "soup", "pasta", "sandwich"})
_FAMILY_GENERIC_MARKER = {name: {name} for name in _GENERIC_DISH_MARKERS}
_TITLE_DECORATION = tokens("авторскому рецепту ужин обед завтрак специи пряности классика мини")
_CARD_FAMILIES = {
    "Салат": {"salad"}, "Суп": {"soup"}, "Блины": {"pancake"},
    "Каша": {"porridge"}, "Оладьи": {"fritter"}, "Запеканка": {"bake"},
    "Паста": {"pasta", "noodles", "wok"}, "Роллы": {"roll"}, "Пицца": {"pizza"},
    "Сэндвич-ролл": {"sandwich", "roll"}, "Сэндвич": {"sandwich", "roll"},
}


def family(ts: frozenset[str]) -> str | None:
    found = next((name for name, markers in _FAMILY_ORDER if markers & ts), None)
    if found is None and "korean" in ts and ts & {"carrot", "cabbage", "asparagus", "beet"}:
        return "salad"
    return found


def ingredient_tokens(ingredients: list[dict]) -> frozenset[str]:
    result: set[str] = set()
    for ingredient in ingredients:
        name = ingredient["name"]
        ts = set(tokens(name))
        # A chicken egg is not chicken meat; butter (масло) is not мясо.
        # Likewise chicken stock alone cannot confirm a chicken main course.
        if re.search(r"яйц|яич|бульон|жир\b", name, re.I):
            ts -= PROTEINS | {"meat"}
        if re.search(r"томат\w*\s+паст", name, re.I):
            ts.discard("pasta")
        result.update(ts)
    return frozenset(result)


NAMED_INGREDIENTS = PROTEINS | frozenset(
    "meat mushroom potato rice buckwheat carrot cabbage beet cucumber tomato cheese cottage_cheese "
    "apple cherry raisin prune apricot pear peach currant strawberry raspberry banana coconut pumpkin "
    "spinach asparagus oat millet wheat garlic poppy chocolate sugar sorrel cinnamon herbs pineapple "
    "nuts pea lentil bulgur flour beans breast thigh".split()
)


def composition_for_product(recipe: dict, query: frozenset[str]) -> dict:
    composition = split_composition(recipe)
    # A garnish explicitly named in the retail product is part of that product,
    # even if food.ru calls it serving. Unnamed coffee/ice cream stays excluded.
    explicitly_named = []
    allowed_serving = {"herbs"}
    # Sour cream served on the side cannot confirm a sour-cream sauce.
    if "sauce" not in query:
        allowed_serving.add("sourcream")
    if family(query) in {"cutlet", "meatball", "schnitzel", "nugget", "kebab", "beefstroganoff", "azu"}:
        allowed_serving |= {"potato", "rice", "buckwheat", "pasta", "mash"}
    if family(query) == "pasta":
        allowed_serving |= {"cheese"}
    for i in composition["excluded_serving_indices"]:
        named = ingredient_tokens([recipe["ingredients"][i]])
        if named and named <= query and named <= allowed_serving:
            explicitly_named.append(i)
    composition["included_named_serving_indices"] = explicitly_named
    composition["included_indices"] = sorted(composition["included_indices"] + explicitly_named)
    composition["excluded_serving_indices"] = [i for i in composition["excluded_serving_indices"] if i not in explicitly_named]
    return composition


class NameIndex:
    def __init__(self, items: list[dict], title_key: str = "title") -> None:
        self.items = items
        self.token_sets = [tokens(x[title_key]) for x in items]
        self.postings: dict[str, set[int]] = defaultdict(set)
        for i, ts in enumerate(self.token_sets):
            for token in ts:
                self.postings[token].add(i)
        self.weights = {t: 1 + math.log(1 + len(items) / len(ids)) for t, ids in self.postings.items()}

    def score(self, query: frozenset[str], i: int) -> float:
        ts = self.token_sets[i]
        overlap = sum(self.weights.get(t, 1) for t in sorted(query & ts))
        coverage = overlap / max(sum(self.weights.get(t, 1) for t in sorted(query)), 1)
        precision = overlap / max(sum(self.weights.get(t, 1) for t in sorted(ts)), 1)
        return .78 * coverage + .22 * precision

    def candidates(self, name: str, limit: int = 5) -> list[tuple[float, int]]:
        query = tokens(clean_product_name(name))
        candidates = set().union(*(self.postings[t] for t in query))
        qfamily = family(query)
        ranked = []
        for i in candidates:
            ts = self.token_sets[i]
            other_family = family(ts)
            if qfamily and other_family and qfamily != other_family:
                continue
            if query & PROTEINS and ts & PROTEINS and not (query & PROTEINS <= ts & PROTEINS):
                continue
            ranked.append((self.score(query, i), i))
        return sorted(ranked, key=lambda x: (-x[0], self.items[x[1]].get("source_id", x[1])))[:limit]


def assess_candidate(product: dict, index: NameIndex, i: int) -> dict:
    query = tokens(clean_product_name(product["name"]))
    meat_name = re.sub(r"\b\w+\s+(?:бульон\w*|яйц\w*)", "", product["name"], flags=re.I)
    required_proteins = tokens(clean_product_name(meat_name)) & PROTEINS
    qfamily = family(query)
    score = index.score(query, i)
    recipe = index.items[i]
    title_tokens = index.token_sets[i]
    composition = composition_for_product(recipe, query)
    components = ingredient_tokens(proxy_ingredients(recipe, composition))
    supported = title_tokens | components
    # Unknown name terms are evidence too: dropping e.g. "чернослив" just
    # because it is outside a hand-written lexicon creates false matches.
    missing = sorted(query - supported - (_FAMILY_GENERIC_MARKER.get(qfamily, set()) if qfamily == family(title_tokens) else set()))
    reasons = []
    component_title = re.match(r"^(фарш|начинка|тесто|маринад|соус)\b.*\bдля\b", recipe["title"].lower())
    if component_title and not clean_product_name(product["name"]).startswith(component_title[1]):
        reasons.append("component_recipe_not_whole_dish")
    if re.search(r"шримп[ -]ролл", product["name"], re.I) and not product.get("dish_type"):
        reasons.append("ambiguous_roll_format")
    product_bread = next((form for form in ("багет", "чиабатт") if form in product["name"].lower()), None)
    recipe_bread = next((form for form in ("багет", "чиабатт") if form in recipe["title"].lower()), None)
    if product_bread and recipe_bread and product_bread != recipe_bread:
        reasons.append("bread_form_conflict")
    if composition["unresolved_indices"]:
        reasons.append("mixed_ingredient_group")
    if query & PROTEINS and title_tokens & PROTEINS and not query & PROTEINS <= title_tokens & PROTEINS:
        reasons.append("title_protein_conflict")
    exact_name = query == title_tokens or (query <= title_tokens and title_tokens - query <= _TITLE_DECORATION)
    if not exact_name and (qfamily is None or qfamily != family(title_tokens)):
        reasons.append("dish_family_unconfirmed")
    card_families = _CARD_FAMILIES.get(product.get("dish_type"))
    if card_families and family(title_tokens) and family(title_tokens) not in card_families:
        reasons.append("retailer_dish_type_conflict")
    if missing:
        reasons.append("missing_named_components")
    allowed_additions = _GENERIC_DISH_MARKERS | _TITLE_DECORATION | {
        "cream", "sourcream", "milk", "sauce", "onion", "pepper", "vegetable", "herbs", "garlic", "wheat", "sugar"
    }
    if "chocolate" in query:
        allowed_additions |= {"cocoa"}
    # Refining a named ingredient is not adding a different ingredient.
    refinements = set()
    if query & PROTEINS:
        allowed_additions |= {"meat"}
        refinements |= {"meat"}
        if not query & {"breast", "thigh"}:
            allowed_additions |= {"breast", "thigh"}
            refinements |= {"breast", "thigh"}
    if "wheat" in query:
        allowed_additions |= {"flour"}
        refinements |= {"flour"}
    if "oil" in query:
        allowed_additions |= {"olive_oil"}
        refinements |= {"olive_oil"}
    if "vegetable" in missing and components & {"onion", "carrot", "cabbage", "tomato", "cucumber", "beans"}:
        missing.remove("vegetable")
        if not missing:
            reasons.remove("missing_named_components")
    serving_only = ingredient_tokens([recipe["ingredients"][j] for j in composition["excluded_serving_indices"]]) - components
    extra = sorted(title_tokens - query - allowed_additions - serving_only)
    if not missing and qfamily is None and family(title_tokens) is None and title_tokens - query <= refinements | _TITLE_DECORATION:
        # Extra words that merely refine a declared ingredient do not require
        # an entry in the dish-family dictionary.
        if "dish_family_unconfirmed" in reasons:
            reasons.remove("dish_family_unconfirmed")
    if extra:
        reasons.append("extra_recipe_components")
    if re.search(r"паста.*(?:санта бремор|криль|creme le mare)", product["name"], re.I):
        reasons.append("retail_spread_not_pasta")
    if "без сахара" in product["name"].lower() and "sugar" in components:
        reasons.append("excluded_ingredient_present")
    required_components = (query & NAMED_INGREDIENTS) - (PROTEINS - required_proteins)
    if "без сахара" in product["name"].lower():
        required_components -= {"sugar"}
    confirmed = components | ({"chocolate"} if "cocoa" in components else set())
    if components & {"chicken", "beef", "pork", "turkey", "lamb", "ham", "bacon", "sausage", "buzhenina"}:
        confirmed |= {"meat"}
    missing_ingredients = sorted(required_components - confirmed)
    if missing_ingredients:
        reasons.append("named_ingredient_unconfirmed")
    sauce_clause = re.search(r"\b(?:в|с|со)\s+([а-яё-]+)\s+соус", product["name"], re.I)
    sauce_ingredients = [item for item in proxy_ingredients(recipe, composition)
                         if "соус" in (item.get("group") or "").lower()]
    if sauce_clause:
        sauce_components = tokens(sauce_clause[1]) & {"tomato", "cheese", "sourcream", "cream", "garlic"}
        sauce_evidence = ingredient_tokens(sauce_ingredients) if sauce_ingredients else components
        if not sauce_components <= sauce_evidence:
            reasons.append("named_sauce_component_unconfirmed")
    if required_proteins and not required_proteins <= components:
        reasons.append("protein_unconfirmed_in_ingredients")
    if "meat" in query and not components & (PROTEINS | {"meat"}):
        reasons.append("meat_unconfirmed_in_ingredients")
    if qfamily == "salad" and not query & (PROTEINS | {"meat", "olivier", "caesar"}):
        if components & (PROTEINS | {"meat"}):
            reasons.append("unexpected_protein_in_ingredients")
    side = re.search(r"\b(?:с|со)\s+(картоф\w*|рис\w*|греч\w*|макарон\w*|спагет\w*|пюре)", product["name"], re.I)
    if qfamily in {"cutlet", "meatball", "schnitzel", "nugget", "kebab", "beefstroganoff", "azu"} and side:
        recipe_side = re.search(r"\b(?:с|со)\s+(картоф\w*|рис\w*|греч\w*|макарон\w*|спагет\w*|пюре)", recipe["title"], re.I)
        if not recipe_side or tokens(side[1]) != tokens(recipe_side[1]):
            reasons.append("side_dish_unconfirmed")
    if "без начинки" in product["name"].lower() and (
        title_tokens & IDENTITY - {"pancake"}
    ):
        reasons.append("filling_conflict")
    if qfamily == "pancake":
        fillings = PROTEINS | {"meat", "cottage_cheese", "cheese", "apple", "cherry", "raisin", "apricot",
                               "pear", "peach", "currant", "strawberry", "raspberry", "banana", "poppy", "mushroom", "potato"}
        if not query & fillings and (components & fillings or re.search(r"с\s+начинк", recipe["title"], re.I)):
            reasons.append("unrequested_pancake_filling")
        if re.search(r"с маков\w* начинк", product["name"], re.I) and not re.search(r"с мак|начинк", recipe["title"], re.I):
            reasons.append("filling_not_batter")
    if score < .72:
        reasons.append("low_name_score")
    return {"recipe_id": recipe["recipe_id"], "title": recipe["title"],
                       "source_url": recipe["source_url"], "score": round(score, 4),
                       "missing_named_components": missing, "review_reasons": reasons,
                       "extra_recipe_components": extra,
                       "rating_count": (recipe.get("rating") or {}).get("count") or 0,
                       "missing_recipe_ingredients": missing_ingredients, "composition": composition}


def match_product(product: dict, index: NameIndex, top_k: int = 3) -> dict:
    # Evaluate all name-compatible recipes in this small static pool before
    # choosing candidates. A valid candidate is not lost at an arbitrary top-20.
    candidates = [assess_candidate(product, index, i)
                  for _, i in index.candidates(product["name"], limit=len(index.items))]
    # Validation takes precedence over lexical score; ratings only break ties
    # among similarly named candidates, never justify a different dish.
    candidates.sort(key=lambda x: (bool(x["review_reasons"]), -x["score"], -x["rating_count"], x["recipe_id"]))
    candidates = candidates[:top_k]
    accepted = candidates and not candidates[0]["review_reasons"]
    return {"chain": product["chain"], "plu": product["plu"], "name": product["name"],
            "normalized_name": clean_product_name(product["name"]),
            "status": "matched" if accepted else "review" if candidates else "unmatched",
            "recipe_id": candidates[0]["recipe_id"] if accepted else None,
            "candidates": candidates}
