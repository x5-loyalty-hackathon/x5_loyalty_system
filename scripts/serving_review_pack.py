"""Export real meal-serving responses for review, never invent quality labels.

Run in an isolated process: python -m scripts.serving_review_pack --output NEW_DIR
Uses existing synthetic generators and the actual FastAPI handlers. No LLM,
external API or production server; the evaluation method is not selected here.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import date, datetime
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
from typing import Any

from pydantic import BaseModel

from app.contracts import CONTRACT_VERSION, MealRecommendationResponse, RecommendationRequest, ShoppingContext
from recsys.catalog_freeze import baseline_catalog, recipe_content_hash
from recsys.inventory import generate_inventory
from recsys.profiles import generate_population
from recsys.recipes import RECIPES

ROOT = Path(__file__).resolve().parents[1]
REVIEW_FIELDS = (
    "case_id", "user_id", "archetype", "row_kind", "rank", "meal_id", "title",
    "mode", "default_route", "missing_count", "reviewer", "criterion_version",
    "relevance_label", "comment",
)
LIMITATIONS = [
    "Synthetic profiles and inventory; not representative measurements of X5 customers.",
    "Full current serving catalog, not the mobile three-recipe demo or a new training baseline.",
    "Cooking profiles only; this inventory generator has no prepared-food SKU. Ready quality is not evaluated.",
    "Default meal feed after safety, single-store feasibility and selector; no forced mode quotas.",
    "Empty responses are retained. Quality labels, baseline comparison and hit rate are not computed (D3 pending).",
    "Offer tokens are replaced with null in the archive; it cannot activate tasks or replay rewards.",
    "No purchases or rewards are submitted. Purchase history in a request is not verified purchase evidence.",
    "No causal uplift or economics is measured by this export.",
]


def normalized(value: Any) -> Any:
    """Stable JSON without reordering ranked lists or losing set semantics."""
    if isinstance(value, BaseModel):
        return normalized(value.model_dump(mode="python"))
    if isinstance(value, Enum):
        return normalized(value.value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): normalized(item) for key, item in value.items()}
    if isinstance(value, (set, frozenset)):
        return sorted((normalized(item) for item in value), key=lambda item: json.dumps(item, sort_keys=True))
    if isinstance(value, (list, tuple)):
        return [normalized(item) for item in value]
    return value


def content_hash(value: Any) -> str:
    payload = json.dumps(normalized(value), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def generate_requests(n_profiles: int, seed: int):
    if not 1 <= n_profiles <= 50:
        raise ValueError("n_profiles must be between 1 and 50; use 30–50 for the review pack")
    inventory_rng = random.Random(seed + 1)
    # Disjoint IDs from model training; sampling rules themselves are unchanged.
    profiles = generate_population(n_profiles, seed=seed, index_offset=2_000_000)
    for index, profile in enumerate(profiles):
        user = profile.user.model_copy(update={"radius_km": 0.75}, deep=True)
        request = RecommendationRequest(
            user=user, current_receipt=profile.current_receipt,
            purchase_history=profile.purchase_history, recipe_catalog=list(RECIPES),
            shopping_context=ShoppingContext(
                anchor_type="home", anchor_id=f"review-home-{index}", radius_km=0.75,
                preferred_store_ids=[profile.current_receipt.store_id],
            ),
            inventory_snapshot=generate_inventory(
                inventory_rng, now=profile.now, home_store_id=profile.current_receipt.store_id,
                user_radius_km=0.75,
            ),
            now=profile.now, limit=3,
        )
        yield f"case-{index + 1:03d}", profile.archetype, request


def build_pack(client, *, n_profiles: int = 40, seed: int = 606, expected_engine: str = "model") -> dict:
    health_response = client.get("/health")
    health_response.raise_for_status()
    health = health_response.json()
    if (health["contract_version"] != CONTRACT_VERSION or health["model_fallback"]
            or health["recommendation_engine"] != expected_engine):
        raise RuntimeError(f"Unexpected engine/version or fallback: {health}")
    cases = []
    for case_id, archetype, request in generate_requests(n_profiles, seed):
        result = client.post("/api/v1/meal-recommendations", json=normalized(request))
        result.raise_for_status()
        response = MealRecommendationResponse.model_validate(result.json())
        for meal in response.recommendations:
            if not meal.offer_id:
                raise RuntimeError("HTTP response did not issue a server offer")
            meal.offer_id = None  # intentionally unusable, explicitly documented archive
        cases.append({"case_id": case_id, "archetype": archetype,
                      "request": normalized(request), "response": normalized(response)})
    return {
        "manifest": {
            "format_version": "1", "contract_version": CONTRACT_VERSION,
            "engine": health["recommendation_engine"], "model_fallback": False,
            "seed": seed, "n_profiles": len(cases), "radius_km": 0.75,
            "training_catalog_hash": recipe_content_hash(baseline_catalog()),
            "serving_catalog_hash": recipe_content_hash(list(RECIPES)),
            "serving_catalog_size": len(RECIPES), "cases_sha256": content_hash(cases),
            "quality_status": "not_assessed", "limitations": LIMITATIONS,
        },
        "diagnostics": {
            "archetype_counts": dict(Counter(case["archetype"] for case in cases)),
            "profiles_with_results": sum(bool(case["response"]["recommendations"]) for case in cases),
            "empty_profiles": sum(not case["response"]["recommendations"] for case in cases),
            "returned_meals": sum(len(case["response"]["recommendations"]) for case in cases),
        },
        "cases": cases,
    }


def review_rows(pack: dict) -> list[dict]:
    rows = []
    for case in pack["cases"]:
        meals = case["response"]["recommendations"]
        for rank, meal in enumerate(meals or [None], 1):
            row = dict.fromkeys(REVIEW_FIELDS, "")
            row.update(case_id=case["case_id"], user_id=case["request"]["user"]["user_id"],
                       archetype=case["archetype"], row_kind="meal" if meal else "empty_response")
            if meal:
                row.update(rank=rank, meal_id=meal["meal_id"], title=meal["title"],
                           mode=meal["mode"], default_route=meal["default_route"],
                           missing_count=(meal["cook_variant"]["missing_count"] if meal["cook_variant"] else ""))
            rows.append(row)
    return rows


def llm_inputs(pack: dict) -> list[dict]:
    """One profile/feed per call, without generator labels or model verdicts.

    This is a documented projection, not a request that can be replayed against
    the API. The full archive retains inventory, scores and explanations for
    separate diagnostics. Lists preserve the actual serving order.
    """
    inputs = []
    for case in pack["cases"]:
        request, response = case["request"], case["response"]
        recipe_ids = set(request["user"]["saved_recipe_ids"])
        for meal in response["recommendations"]:
            if meal.get("cook_variant"):
                recipe_ids.add(meal["cook_variant"]["recipe_id"])
        inputs.append({
            "case_id": case["case_id"],
            "context": {key: request[key] for key in (
                "user", "current_receipt", "purchase_history", "shopping_context", "now",
            )},
            "recipes": [
                {key: recipe[key] for key in (
                    "recipe_id", "title", "ingredients", "preparation_minutes", "meal_intent_id",
                )}
                for recipe in request["recipe_catalog"] if recipe["recipe_id"] in recipe_ids
            ],
            "recommendations": [
                {key: meal[key] for key in (
                    "meal_id", "title", "mode", "default_route", "available_routes",
                    "cook_variant", "ready_variant", "warnings",
                )}
                for meal in response["recommendations"]
            ],
            "warnings": response.get("warnings", []),
        })
    return inputs


def write_pack(pack: dict, output: Path, *, full_archive: bool = True) -> None:
    inputs = llm_inputs(pack)
    manifest = {
        **pack["manifest"], "diagnostics": pack.get("diagnostics", {}),
        "llm_input_format": "profile-feed-v1", "llm_inputs_sha256": content_hash(inputs),
        "full_archive_included": full_archive,
    }
    # Never overwrite a team's existing labels or a previous result directory.
    output.mkdir(parents=True, exist_ok=False)
    if full_archive:
        (output / "responses.json").write_text(
            json.dumps(pack, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "llm_inputs.jsonl").write_text(
        "".join(json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
                for item in inputs), encoding="utf-8")
    with (output / "review.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_FIELDS)
        writer.writeheader()
        writer.writerows(review_rows(pack))
    (output / "README.md").write_text(
        "# Meal API review pack — NOT a quality result\n\n"
        + ("responses.json contains each complete synthetic request and final API response.\n"
           if full_archive else "Compact handoff: full requests/responses are NOT included; regenerate the full archive for diagnostics.\n")
        + "llm_inputs.jsonl has one profile and final feed per line; keep empty feeds.\n"
        "It omits archetype, model_score, safety verdict, recipe verified flag and top-level reason codes.\n"
        "It retains purchase history, explicit preferences, actual offers and saved/offered recipe definitions.\n"
        "It is not an API-replay request; stock outside the shown offers is omitted.\n"
        "manifest.json identifies source code, inputs and diagnostic counts.\n"
        "review.csv is a blank review sheet; keep empty_response rows.\n"
        "Do not pass the review CSV or manifest to the LLM as profile evidence.\n"
        "Agree rubric, reviewer, baseline and denominators before computing hit rate.\n"
        "Returned-meal counts are diagnostics, not relevance or causal uplift.\n\n"
        + "\n".join(f"- {item}" for item in pack["manifest"]["limitations"]) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New directory; existing output is never overwritten")
    parser.add_argument("--profiles", type=int, choices=range(30, 51), default=40)
    parser.add_argument("--seed", type=int, default=606)
    parser.add_argument("--handoff-only", action="store_true",
                        help="Only compact LLM inputs, manifest and blank review sheet; omit full response archive")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists; choose a new directory to preserve previous results/labels")
    # Fresh CLI process only; no existing running demo server is reset or contacted.
    os.environ["RECOMMENDATION_ENGINE"] = "model"
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as client:
        pack = build_pack(client, n_profiles=args.profiles, seed=args.seed)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True)
    pack["manifest"]["git_head"] = commit.stdout.strip() if commit.returncode == 0 else None
    # HEAD alone does not identify uncommitted code. These explicit content
    # fingerprints supplement the complete input/output hashes; not a full SBOM.
    sources = ["app/contracts.py", "app/main.py", "app/service.py", "app/safety.py",
               "recsys/model.py", "recsys/profiles.py", "recsys/inventory.py",
               "recsys/recipes.py", "recsys/catalog.py", "scripts/serving_review_pack.py"]
    pack["manifest"]["source_sha256"] = {
        path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in sources
    }
    write_pack(pack, args.output, full_archive=not args.handoff_only)
    print(json.dumps({"output": str(args.output), "quality_status": "not_assessed",
                      **pack["diagnostics"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
