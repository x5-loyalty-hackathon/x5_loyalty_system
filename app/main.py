import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.contracts import (
    HealthResponse,
    ProgressSnapshot,
    RecommendationRequest,
    RecommendationResponse,
    ReceiptProgressRequest,
    ReceiptProgressResponse,
    ReferralEvaluationRequest,
    ReferralEvaluationResponse,
)
from app.fraud import ReceiptFraudPolicy, ReferralFraudPolicy
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
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8081",  # Expo web dev server
    ],
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


@app.post(
    "/api/v1/referrals/evaluate",
    response_model=ReferralEvaluationResponse,
)
def evaluate_referral(
    request: ReferralEvaluationRequest,
) -> ReferralEvaluationResponse:
    return referral_service.evaluate(request)
