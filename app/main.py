import os

from fastapi import HTTPException

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.contracts import (
    HealthResponse,
    KitchenSnapshot,
    ProgressSnapshot,
    RecipeCompletionRequest,
    RecipeCompletionResponse,
    RecipeDetails,
    RecommendationRequest,
    RecommendationResponse,
    ReceiptProgressRequest,
    ReceiptProgressResponse,
    ReferralEvaluationRequest,
    ReferralEvaluationResponse,
)
from app.fraud import ReceiptFraudPolicy, ReferralFraudPolicy
from app.mock_recipes import MOCK_RECIPE_DETAILS
from app.progress import ProgressService
from app.recommender import DeterministicMockEngine, RecommendationEngine
from app.referral import ReferralService
from app.safety import SafetyPolicy
from app.service import RecommendationService
from app.state import InMemoryStateRepository


def _build_recommendation_engine() -> RecommendationEngine:
    """Select the recommendation engine via `RECOMMENDATION_ENGINE` (default:
    unchanged `mock` behavior). `model` opts into the ML/Recsys adapter
    (`recsys.model.MLRecommendationEngine`); on import failure it falls back
    to the deterministic mock, matching the documented fallback behavior in
    docs/technical-design.md §9 ("model недоступен → переключиться на
    deterministic mock только в demo mode")."""
    engine_choice = os.environ.get("RECOMMENDATION_ENGINE", "mock").strip().lower()
    if engine_choice == "model":
        try:
            from recsys.model import MLRecommendationEngine

            return MLRecommendationEngine()
        except Exception:  # pragma: no cover - defensive demo fallback
            return DeterministicMockEngine()
    return DeterministicMockEngine()


app = FastAPI(
    title="X5 Domovoi PoC API",
    version="0.1.0",
    description="Recipe-first recommendation, integration and safety contract.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

recommendation_service = RecommendationService(
    engine=_build_recommendation_engine(),
    safety_policy=SafetyPolicy(),
)
state_repository = InMemoryStateRepository()
progress_service = ProgressService(
    repository=state_repository,
    fraud_policy=ReceiptFraudPolicy(),
)
referral_service = ReferralService(
    repository=state_repository,
    fraud_policy=ReferralFraudPolicy(),
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post(
    "/api/v1/recommendations",
    response_model=RecommendationResponse,
)
def create_recommendations(
    request: RecommendationRequest,
) -> RecommendationResponse:
    return recommendation_service.recommend(request)


@app.post(
    "/api/v1/events/receipts",
    response_model=ReceiptProgressResponse,
)
def process_receipt(
    request: ReceiptProgressRequest,
) -> ReceiptProgressResponse:
    return progress_service.process_receipt(request)


@app.get(
    "/api/v1/progress/{user_id}",
    response_model=ProgressSnapshot,
)
def get_progress(user_id: str) -> ProgressSnapshot:
    return progress_service.get_progress(user_id)


@app.get(
    "/api/v1/kitchen/{user_id}",
    response_model=KitchenSnapshot,
)
def get_kitchen(user_id: str) -> KitchenSnapshot:
    return progress_service.get_kitchen(user_id)


@app.post(
    "/api/v1/events/recipes/completed",
    response_model=RecipeCompletionResponse,
)
def complete_recipe(request: RecipeCompletionRequest) -> RecipeCompletionResponse:
    recipe = MOCK_RECIPE_DETAILS.get(request.recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="recipe not found in PoC catalog")
    if request.ingredient_ids != recipe.ingredient_ids:
        raise HTTPException(
            status_code=422,
            detail="ingredient_ids must match the synthetic recipe definition",
        )
    return progress_service.complete_recipe(request)


@app.get(
    "/api/v1/recipes/{recipe_id}",
    response_model=RecipeDetails,
)
def get_recipe_details(recipe_id: str) -> RecipeDetails:
    recipe = MOCK_RECIPE_DETAILS.get(recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="recipe not found in PoC catalog")
    return recipe


@app.post(
    "/api/v1/referrals/evaluate",
    response_model=ReferralEvaluationResponse,
)
def evaluate_referral(
    request: ReferralEvaluationRequest,
) -> ReferralEvaluationResponse:
    return referral_service.evaluate(request)
