import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.contracts import (
    CookingConfirmationRequest,
    HealthResponse,
    MealPlanCompletionResponse,
    MealPlanSaveRequest,
    MealPlanSaveResponse,
    MealRecommendationResponse,
    ProgressSnapshot,
    RecommendationRequest,
    RecommendationResponse,
    ReceiptProgressRequest,
    ReceiptProgressResponse,
    ReferralEvaluationRequest,
    ReferralEvaluationResponse,
    SavedRecipeCollection,
    SavedRecipeSaveRequest,
    SavedRecipeSaveResponse,
)
from app.fraud import ReceiptFraudPolicy, ReferralFraudPolicy
from app.meal_plan import MealPlanService
from app.progress import ProgressService
from app.recipe_book import RecipeBookService
from app.recommender import DeterministicMockEngine, RecommendationEngine
from app.referral import ReferralService
from app.safety import SafetyPolicy
from app.service import RecommendationService
from app.state import InMemoryStateRepository


logger = logging.getLogger(__name__)


def _build_recommendation_engine() -> tuple[RecommendationEngine, str, bool]:
    """Select the recommendation engine via `RECOMMENDATION_ENGINE` (default:
    unchanged `mock` behavior). `model` opts into the ML/Recsys adapter
    (`recsys.model.MLRecommendationEngine`); on import failure it logs the
    error and returns observable fallback metadata together with the mock,
    matching the documented fallback behavior in
    docs/technical-design.md §9 ("model недоступен → переключиться на
    deterministic mock только в demo mode")."""
    engine_choice = os.environ.get("RECOMMENDATION_ENGINE", "mock").strip().lower()
    if engine_choice == "model":
        try:
            from recsys.model import MLRecommendationEngine

            return MLRecommendationEngine(), "model", False
        except Exception:  # pragma: no cover - defensive demo fallback
            logger.exception(
                "model recommendation engine unavailable; using deterministic mock"
            )
            return DeterministicMockEngine(), "mock", True
    if engine_choice != "mock":
        logger.warning(
            "unknown RECOMMENDATION_ENGINE=%s; using deterministic mock",
            engine_choice,
        )
        return DeterministicMockEngine(), "mock", True
    return DeterministicMockEngine(), "mock", False


app = FastAPI(
    title="X5 Domovoi PoC API",
    version="0.1.0",
    description="Recipe-first recommendation, integration and safety contract.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000", "http://localhost:5173",
        "http://localhost:8081", "http://127.0.0.1:8081",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

recommendation_engine, recommendation_engine_name, model_fallback = (
    _build_recommendation_engine()
)
state_repository = InMemoryStateRepository()
recommendation_service = RecommendationService(
    engine=recommendation_engine,
    safety_policy=SafetyPolicy(),
    saved_recipe_provider=state_repository,
)
progress_service = ProgressService(
    repository=state_repository,
    fraud_policy=ReceiptFraudPolicy(),
)
meal_plan_service = MealPlanService(repository=state_repository)
recipe_book_service = RecipeBookService(repository=state_repository)
referral_service = ReferralService(
    repository=state_repository,
    fraud_policy=ReferralFraudPolicy(),
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        recommendation_engine=recommendation_engine_name,
        model_fallback=model_fallback,
    )


@app.post(
    "/api/v1/recommendations",
    response_model=RecommendationResponse,
)
def create_recommendations(
    request: RecommendationRequest,
) -> RecommendationResponse:
    return recommendation_service.recommend(request)


@app.post(
    "/api/v1/meal-recommendations",
    response_model=MealRecommendationResponse,
)
def create_meal_recommendations(
    request: RecommendationRequest,
) -> MealRecommendationResponse:
    return recommendation_service.recommend_meals(request)


@app.post(
    "/api/v1/saved-recipes",
    response_model=SavedRecipeSaveResponse,
)
def save_recipe(request: SavedRecipeSaveRequest) -> SavedRecipeSaveResponse:
    return recipe_book_service.save(request)


@app.get(
    "/api/v1/saved-recipes/{user_id}",
    response_model=SavedRecipeCollection,
)
def list_saved_recipes(user_id: str) -> SavedRecipeCollection:
    return recipe_book_service.list(user_id)


@app.post(
    "/api/v1/meal-plans",
    response_model=MealPlanSaveResponse,
)
def save_meal_plan(request: MealPlanSaveRequest) -> MealPlanSaveResponse:
    return meal_plan_service.save(request)


@app.post(
    "/api/v1/meal-plans/{plan_id}/complete-cook",
    response_model=MealPlanCompletionResponse,
)
def complete_cook_meal_plan(
    plan_id: str,
    request: CookingConfirmationRequest,
) -> MealPlanCompletionResponse:
    return meal_plan_service.confirm_cooking(plan_id=plan_id, request=request)


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


@app.post(
    "/api/v1/referrals/evaluate",
    response_model=ReferralEvaluationResponse,
)
def evaluate_referral(
    request: ReferralEvaluationRequest,
) -> ReferralEvaluationResponse:
    return referral_service.evaluate(request)
