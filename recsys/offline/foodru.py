"""Build static food.ru recipes and X5 ready-meal matches (stdlib only).

    python -m recsys.offline.foodru collect
    python -m recsys.offline.foodru build

The first command accesses public HTML/sitemaps; the second is fully offline.
Neither command modifies the original catalog or the application's recipe pool.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import re
import threading
import time
import xml.etree.ElementTree as ET
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from recsys.offline.foodru_composition import proxy_ingredients, split_composition
from recsys.offline.foodru_matching import VERSION, NameIndex, clean_product_name, composition_for_product, match_product, tokens
from recsys.offline.foodru_parser import parse_recipe

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG = ROOT / "recsys/data/ready_food_catalog.json"
DEFAULT_OUTPUT = ROOT / "recsys/data/foodru"
DEFAULT_CACHE = ROOT / "artifacts/foodru/cache"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


class Fetcher:
    def __init__(self, cache: Path, interval: float = 1.0) -> None:
        self.cache = cache
        cache.mkdir(parents=True, exist_ok=True)
        self.interval = interval
        self.lock = threading.Lock()
        self.next_request = 0.0

    def get(self, url: str) -> tuple[str, str]:
        if urlparse(url).hostname != "food.ru" or urlparse(url).scheme != "https":
            raise ValueError(f"Unexpected source URL: {url}")
        key = hashlib.sha256(url.encode()).hexdigest()
        payload, metadata = self.cache / f"{key}.html.gz", self.cache / f"{key}.json"
        if payload.exists() and metadata.exists():
            return gzip.decompress(payload.read_bytes()).decode("utf-8"), json.loads(metadata.read_text())["fetched_at"]
        for attempt in range(3):
            with self.lock:
                time.sleep(max(0, self.next_request - time.monotonic()))
                self.next_request = time.monotonic() + self.interval
            try:
                request = Request(url, headers={"User-Agent": "X5-Hackathon-Offline-Recipe-PoC/1.0",
                                                "Accept-Encoding": "gzip"})
                with urlopen(request, timeout=60) as response:
                    if urlparse(response.url).hostname != "food.ru":
                        raise ValueError(f"Unexpected redirect: {response.url}")
                    body = response.read()
                    if response.headers.get("Content-Encoding") == "gzip":
                        body = gzip.decompress(body)
                html = body.decode("utf-8")
                fetched_at = now()
                payload.write_bytes(gzip.compress(body, mtime=0))
                write_json(metadata, {"url": url, "fetched_at": fetched_at,
                                      "sha256": hashlib.sha256(body).hexdigest()})
                return html, fetched_at
            except HTTPError as error:
                if error.code not in {429, 500, 502, 503, 504} or attempt == 2:
                    raise
                retry = error.headers.get("Retry-After", "")
                delay = 5 * (attempt + 1)
                if retry.isdigit():
                    delay = float(retry)
                elif retry:
                    try:
                        delay = max(0, (parsedate_to_datetime(retry) - datetime.now(timezone.utc)).total_seconds())
                    except (ValueError, TypeError):
                        pass
                # Shared cooldown across workers. Stop instead of retrying
                # earlier than a long server-requested delay.
                if delay > 60:
                    raise
                with self.lock:
                    self.next_request = max(self.next_request, time.monotonic() + delay)
            except (URLError, TimeoutError):
                if attempt == 2:
                    raise
                time.sleep(2 * (attempt + 1))
        raise RuntimeError(url)


def discover(fetcher: Fetcher, products: list[dict], per_product: int, maximum: int) -> list[dict]:
    sitemap, _ = fetcher.get("https://food.ru/sitemap.xml")
    maps = [x.text for x in ET.fromstring(sitemap).iter() if x.tag.endswith("}loc")
            and re.search(r"/sitemaps/recipes-\d+\.xml$", x.text or "")]
    urls = set()
    for url in maps:
        # Also accept the exploratory download, avoiding a second download.
        local = fetcher.cache / url.rsplit("/", 1)[-1]
        data = local.read_text() if local.exists() else fetcher.get(url)[0]
        urls.update(x.text for x in ET.fromstring(data).iter() if x.tag.endswith("}loc")
                    and re.search(r"^https://food.ru/recipes/\d+-", x.text or ""))
    items = [{"url": url, "source_id": int(re.search(r"/recipes/(\d+)", url)[1]),
              "title": re.sub(r"^\d+-", "", url.rsplit("/", 1)[-1]).replace("-", " ")}
             for url in sorted(urls)]
    print(f"Sitemap: {len(items)} recipe URLs; ranking against {len(products)} products", flush=True)
    index = NameIndex(items)
    per_item = [index.candidates(p["name"], per_product) for p in products]
    selected = {}
    # Round-robin gives every product its best candidate before second choices.
    for rank in range(per_product):
        for product, candidates in zip(products, per_item):
            if len(candidates) <= rank:
                continue
            score, i = candidates[rank]
            if score < .35:
                continue
            item = items[i]
            if item["url"] not in selected and len(selected) >= maximum:
                continue
            row = selected.setdefault(item["url"], {**item, "products": [], "discovery_score": round(score, 4)})
            row["products"].append(f"{product['chain']}:{product['plu']}")
    return list(selected.values())


def collect(args: argparse.Namespace) -> None:
    fetcher = Fetcher(args.cache, args.interval)
    catalog = json.loads(args.catalog.read_text())
    plan_path = args.cache.parent / "discovery.json"
    if args.urls:
        plan = [{"url": x.strip()} for x in args.urls.read_text().splitlines()
                if x.strip() and not x.startswith("#")]
    elif plan_path.exists() and not args.rediscover:
        plan = json.loads(plan_path.read_text())["recipes"]
    else:
        plan = discover(fetcher, catalog["products"], args.per_product, args.max_recipes)
        write_json(plan_path, {"generated_at": now(), "recipes": plan})
    recipes, errors = {}, []

    def scrape(item: dict) -> dict:
        html, fetched_at = fetcher.get(item["url"])
        return parse_recipe(html, item["url"], fetched_at)

    print(f"Collecting {len(plan)} recipes (cache/resume enabled)", flush=True)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(scrape, item): item for item in plan}
        for n, future in enumerate(as_completed(futures), 1):
            item = futures[future]
            try:
                recipe = future.result()
                recipes[recipe["recipe_id"]] = recipe
            except (ValueError, URLError, TimeoutError, OSError) as error:
                errors.append({"url": item["url"], "error": str(error)})
                print(f"FAILED {item['url']}: {error}", flush=True)
            if n % 25 == 0 or n == len(plan):
                write_json(args.cache.parent / "collection_progress.json", {
                    "schema_version": 1, "source": "https://food.ru", "generated_at": now(),
                    "planned": len(plan), "errors": errors,
                    "recipes": sorted(recipes.values(), key=lambda x: x["source_id"]),
                })
                print(f"{n}/{len(plan)}: {len(recipes)} recipes, {len(errors)} errors", flush=True)
    if not recipes:
        raise SystemExit("No valid recipes collected; inspect errors/cache")
    write_json(args.output / "recipes.json", {
        "schema_version": 1, "source": "https://food.ru", "generated_at": now(),
        "planned": len(plan), "errors": errors,
        "recipes": sorted(recipes.values(), key=lambda x: x["source_id"]),
    })
    build(args)


def build(args: argparse.Namespace) -> None:
    catalog_bytes = args.catalog.read_bytes()
    catalog = json.loads(catalog_bytes)
    snapshot = json.loads((args.output / "recipes.json").read_text())
    recipes = snapshot["recipes"]
    index = NameIndex(recipes)
    matches = [match_product(product, index) for product in catalog["products"]]
    by_id = {r["recipe_id"]: r for r in recipes}
    overrides_path = args.overrides or args.output / "reviewed_overrides.json"
    if args.overrides and not overrides_path.is_file():
        raise ValueError(f"Override file does not exist: {overrides_path}")
    overrides_bytes = overrides_path.read_bytes() if overrides_path.is_file() else None
    overrides = json.loads(overrides_bytes) if overrides_bytes is not None else {}
    known_products = {f"{p['chain']}:{p['plu']}" for p in catalog["products"]}
    if set(overrides) - known_products:
        raise ValueError("Override contains products absent from the input catalog")
    for match in matches:
        key = f"{match['chain']}:{match['plu']}"
        if key in overrides:
            override = overrides[key]
            if not override.get("reason"):
                raise ValueError(f"Override must include a reason: {key}")
            recipe_id = override.get("recipe_id")
            if recipe_id is not None and recipe_id not in by_id:
                raise ValueError(f"Unknown override recipe_id: {recipe_id}")
            status = "matched" if recipe_id else override.get("status", "unmatched")
            if recipe_id is None and status not in {"review", "unmatched"}:
                raise ValueError(f"Rejected override must use review or unmatched: {key}")
            match.update(status=status, recipe_id=recipe_id,
                         manual_override=override)
    enriched, options = [], []
    for product, match in zip(catalog["products"], matches):
        recipe = by_id.get(match["recipe_id"])
        composition = composition_for_product(recipe, tokens(clean_product_name(product["name"]))) if recipe else None
        if composition and composition["unresolved_indices"]:
            raise ValueError(f"Override requires ingredient-group review: {match['chain']}:{match['plu']}")
        enriched.append({**product, "foodru_match": match,
                         "assumed_ingredients": proxy_ingredients(recipe, composition) if recipe else None,
                         "excluded_serving_ingredients": [recipe["ingredients"][i] for i in composition["excluded_serving_indices"]] if recipe else None,
                         "ingredient_provenance": {
                             "kind": "recipe_name_proxy", "manufacturer_verified": False,
                             "recipe_id": recipe["recipe_id"], "source_url": recipe["source_url"],
                             "quantities_scope": "whole_recipe_not_retail_package",
                             "composition": composition,
                         } if recipe else None})
        if recipe:
            options.append({"chain": product["chain"], "plu": product["plu"], "name": product["name"],
                            "recipe_ids": [recipe["recipe_id"]], "price": product["median_price_rub"],
                            "dish_type": product.get("dish_type"), "cuisine": product.get("cuisine")})
    common = {"schema_version": 2, "matcher_version": VERSION,
              "overrides_sha256": hashlib.sha256(overrides_bytes).hexdigest() if overrides_bytes is not None else None,
              "catalog_sha256": hashlib.sha256(catalog_bytes).hexdigest(),
              "recipe_snapshot_sha256": hashlib.sha256((args.output / "recipes.json").read_bytes()).hexdigest(),
              "snapshot_ids": catalog.get("snapshot_ids", []), "city": catalog.get("city")}
    write_json(args.output / "matches.json", {**common, "matches": matches})
    write_json(args.output / "enriched_catalog.json", {**common, "products": enriched})
    write_json(args.output / "ready_meal_options.json", options)
    (args.output / "recipe_urls.txt").write_text(
        "".join(r["source_url"] + "\n" for r in recipes), encoding="utf-8"
    )
    counts = Counter(x["status"] for x in matches)
    summary = {**common, "products": len(matches), "recipes": len(recipes),
               "status_counts": {status: counts[status] for status in ("matched", "review", "unmatched")},
               "matched_unique_recipes": len({m["recipe_id"] for m in matches if m["recipe_id"]}),
               "recipes_with_rating": sum(r["rating"] is not None for r in recipes),
               "recipes_with_reviews": sum(bool(r["reviews"]) for r in recipes),
               "reviews_collected": sum(len(r["reviews"]) for r in recipes),
               "review_completeness": dict(Counter(r["reviews_status"] for r in recipes)),
               "collection_errors": len(snapshot.get("errors", []))}
    summary["recipes_with_mixed_ingredient_groups"] = sum(bool(split_composition(r)["unresolved_indices"]) for r in recipes)
    summary["matched_products_with_excluded_serving"] = sum(bool(p["excluded_serving_ingredients"]) for p in enriched)
    summary["matched_by_decision"] = {
        "automatic": sum(m["status"] == "matched" and "manual_override" not in m for m in matches),
        "reviewed_override": sum(m["status"] == "matched" and "manual_override" in m for m in matches),
    }
    write_json(args.output / "summary.json", summary)
    with (args.output / "review.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["chain", "plu", "product_name", "status", "rank", "recipe_id", "recipe_title", "score", "missing_components", "extra_components", "missing_recipe_ingredients", "mixed_ingredient_groups", "review_reasons", "source_url", "selected_recipe_id", "decision", "override_reason"])
        for match in matches:
            for rank, candidate in enumerate(match["candidates"], 1):
                writer.writerow([match["chain"], match["plu"], match["name"], match["status"], rank,
                                 candidate["recipe_id"], candidate["title"], candidate["score"],
                                 ", ".join(candidate["missing_named_components"]),
                                 ", ".join(candidate["extra_recipe_components"]),
                                 ", ".join(candidate["missing_recipe_ingredients"]),
                                 ", ".join(candidate["composition"]["mixed_groups"]),
                                 ", ".join(candidate["review_reasons"]), candidate["source_url"],
                                 match["recipe_id"], "reviewed_override" if "manual_override" in match else "automatic",
                                 match.get("manual_override", {}).get("reason", "")])
            if not match["candidates"]:
                writer.writerow([match["chain"], match["plu"], match["name"], match["status"]])
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["collect", "build"])
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--urls", type=Path, help="Optional explicit recipe URLs, one per line")
    parser.add_argument("--overrides", type=Path, help="Reviewed chain:plu → {recipe_id, reason} JSON")
    parser.add_argument("--per-product", type=int, default=2)
    parser.add_argument("--max-recipes", type=int, default=700)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--interval", type=float, default=1.0, help="Global minimum seconds between HTTP requests")
    parser.add_argument("--rediscover", action="store_true")
    args = parser.parse_args()
    if args.interval < .5 or not 1 <= args.workers <= 4 or args.per_product < 1 or args.max_recipes < 1:
        parser.error("interval >= 0.5, workers 1..4, positive per-product/max-recipes required")
    (collect if args.command == "collect" else build)(args)


if __name__ == "__main__":
    main()
