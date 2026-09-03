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
from app.recommender import DeterministicMockEngine
from app.referral import ReferralService
from app.safety import SafetyPolicy
from app.service import RecommendationService
from app.state import InMemoryStateRepository


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
    engine=DeterministicMockEngine(),
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
