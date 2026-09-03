from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.contracts import (
    HealthResponse,
    RecommendationRequest,
    RecommendationResponse,
)
from app.recommender import DeterministicMockEngine
from app.safety import SafetyPolicy
from app.service import RecommendationService


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
